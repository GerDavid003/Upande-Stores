import frappe
from frappe.model.document import Document
from frappe.utils import add_months


class EmployeePPEAssignment(Document):
	def validate(self):
		if self.issue_date and self.lifespan_months and not self.expiry_date:
			self.expiry_date = add_months(self.issue_date, int(self.lifespan_months))

	def after_insert(self):
		# NOTE: Frappe's Document base class never invokes a method named
		# "on_insert" (verified against frappe/model/document.py: insert()
		# calls run_method("after_insert") post-DB-insert, then
		# run_post_save_methods() -> run_method("on_update"); "on_insert" is
		# not a real lifecycle hook anywhere in that file). The brief's
		# original on_insert() was therefore silently dead code -- it never
		# ran, so the Employee PPE History row was never created on insert.
		# Renamed to the actual hook, after_insert.
		self._sync_history_row()

	def on_update(self):
		if "upande_hr" not in frappe.get_installed_apps():
			return
		frappe.db.set_value(
			"Employee PPE History",
			{"ppe_assignment": self.name, "parent": self.employee},
			{
				"status": self.status,
				"expiry_date": self.expiry_date,
				"last_inspection_date": self.last_inspection_date,
				"last_inspection_status": self.last_inspection_status,
				# Finding 4: keep the history row's PPE Inspection link populated --
				# it was declared on Employee PPE History but never written to.
				"ppe_inspection": self.last_inspection,
			},
		)

	def on_trash(self):
		# Finding 2: without this, deleting an assignment (e.g. when its Stock
		# Entry is cancelled) would leave an orphaned Employee PPE History row
		# with a dangling ppe_assignment link. Same upande_hr guard the rest of
		# the sync logic uses.
		if "upande_hr" in frappe.get_installed_apps():
			frappe.db.delete(
				"Employee PPE History",
				{"ppe_assignment": self.name, "parent": self.employee},
			)

		# A prior assignment's replacement_assignment can point at this one
		# (the PPE replacement flow) -- that inbound link would otherwise make
		# delete_doc's link check raise LinkExistsError, regardless of whether
		# this deletion was triggered directly (Desk UI) or indirectly (e.g.
		# Stock Entry cancel). Unset it so this assignment can actually be
		# deleted.
		referencing = frappe.get_all(
			"Employee PPE Assignment", filters={"replacement_assignment": self.name}, pluck="name"
		)
		for ref in referencing:
			frappe.db.set_value("Employee PPE Assignment", ref, "replacement_assignment", None)

		# A PPE Inspection Item child row can also hold a link to this
		# assignment -- and cancelling the PPE Inspection it belongs to does
		# NOT clear that link (PPEInspection.on_cancel only reverts the
		# assignment's status, it never touches the child row's own fields).
		# delete_doc's link check for a plain "Delete" ignores docstatus
		# entirely, so even a properly cancelled inspection's child row would
		# otherwise still block this delete. Unset the low-level field rather
		# than cascade into deleting the PPE Inspection itself -- it stays as a
		# historical record (remarks, outcome, etc.), just no longer linked to
		# the assignment being deleted.
		inspection_items = frappe.get_all(
			"PPE Inspection Item", filters={"employee_ppe_assignment": self.name}, pluck="name"
		)
		for item_name in inspection_items:
			frappe.db.set_value("PPE Inspection Item", item_name, "employee_ppe_assignment", None)

	def _sync_history_row(self):
		if "upande_hr" not in frappe.get_installed_apps():
			return
		if frappe.db.exists("Employee PPE History", {"ppe_assignment": self.name, "parent": self.employee}):
			return
		frappe.get_doc(
			{
				"doctype": "Employee PPE History",
				"parent": self.employee,
				"parenttype": "Employee",
				"parentfield": "custom_ppe_history",
				"ppe_assignment": self.name,
				"item_code": self.item_code,
				"quantity": self.quantity,
				"issue_date": self.issue_date,
				"expiry_date": self.expiry_date,
				"status": self.status,
				"stock_entry": self.stock_entry,
			}
		).insert(ignore_permissions=True)
