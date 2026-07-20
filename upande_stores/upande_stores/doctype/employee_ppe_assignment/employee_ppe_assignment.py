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
			},
		)

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
