import frappe
from frappe.model.document import Document


class PPEInspection(Document):
	def on_submit(self):
		for row in self.items_inspected:
			if not row.update_assignment or not row.employee_ppe_assignment:
				continue

			assignment = frappe.get_doc("Employee PPE Assignment", row.employee_ppe_assignment)
			assignment.last_inspection_date = self.inspection_date
			assignment.last_inspection_status = row.current_status
			assignment.last_inspection = self.name

			if row.current_status in ("Worn Out", "Lost"):
				assignment.status = "Inactive"
			elif row.current_status == "OK":
				assignment.status = "Active"

			assignment.save(ignore_permissions=True)
