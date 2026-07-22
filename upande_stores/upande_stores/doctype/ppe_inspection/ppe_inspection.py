import frappe
from frappe import _
from frappe.model.document import Document


class PPEInspection(Document):
	def validate(self):
		# Finding 3: the employee_ppe_assignment link-query filter and the
		# employee(frm) auto-fetch handler both draw from the same broadened
		# ("Active"/"Expired") scope, so an inspector can still use the
		# dropdown to manually add a second row for an assignment already
		# auto-filled into the table. on_submit would then process that
		# assignment twice -- the second pass's previous_status capture would
		# record the already-mutated value, corrupting a later on_cancel
		# revert. Catch it here, at save time, before submit is even possible.
		seen = set()
		for row in self.items_inspected:
			if not row.employee_ppe_assignment:
				continue
			if row.employee_ppe_assignment in seen:
				frappe.throw(
					_(
						"Employee PPE Assignment {0} appears more than once in Items Inspected."
					).format(row.employee_ppe_assignment)
				)
			seen.add(row.employee_ppe_assignment)

	def before_submit(self):
		has_worn_out = any(row.current_status == "Worn Out" for row in self.items_inspected)
		if not has_worn_out:
			return

		attached = frappe.get_all(
			"File",
			filters={"attached_to_doctype": "PPE Inspection", "attached_to_name": self.name},
			limit=1,
		)
		if not attached:
			frappe.throw(
				_("Attach photo evidence before submitting — at least one item is marked Worn Out.")
			)

	def on_submit(self):
		for row in self.items_inspected:
			if not row.update_assignment or not row.employee_ppe_assignment:
				continue

			assignment = frappe.get_doc("Employee PPE Assignment", row.employee_ppe_assignment)

			# Finding 3: capture the assignment's status BEFORE we overwrite it,
			# stamping it onto this inspection's own row so on_cancel can revert
			# to exactly the pre-inspection value (not a hardcoded default).
			# on_submit runs after this document (and its child rows) are already
			# persisted with docstatus=1, so an in-memory assignment on `row`
			# wouldn't stick -- db_set writes it straight to the child row.
			row.db_set("previous_status", assignment.status)

			assignment.last_inspection_date = self.inspection_date
			assignment.last_inspection_status = row.current_status
			assignment.last_inspection = self.name

			if row.current_status in ("Worn Out", "Lost"):
				assignment.status = "Inactive"
			elif row.current_status == "OK" and assignment.status != "Expired":
				# Finding 1: an OK verdict still reactivates a previously Inactive
				# assignment, but must not flip an Expired assignment back to
				# Active -- the daily auto-expiry job would just silently undo
				# that within a day anyway. last_inspection_date/_status/_ are
				# stamped above regardless; only this status mutation is gated.
				assignment.status = "Active"

			assignment.save(ignore_permissions=True)

	def on_cancel(self):
		# Finding 3: inverse of the status change on_submit made. Revert each
		# affected assignment's status to whatever it was immediately before this
		# inspection changed it. Scope boundary: last_inspection / *_date /
		# *_status are deliberately left as whatever this inspection stamped --
		# only `status` reverts.
		for row in self.items_inspected:
			if not row.update_assignment or not row.employee_ppe_assignment:
				continue
			if not row.previous_status:
				continue

			assignment = frappe.get_doc("Employee PPE Assignment", row.employee_ppe_assignment)
			assignment.status = row.previous_status
			assignment.save(ignore_permissions=True)
