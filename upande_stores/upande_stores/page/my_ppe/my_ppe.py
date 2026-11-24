import frappe
from frappe import _


def _get_current_employee():
	employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
	return employee


@frappe.whitelist()
def get_my_ppe_assignments():
	employee = _get_current_employee()
	if not employee:
		return {"employee": None, "assignments": []}

	assignments = frappe.get_all(
		"Employee PPE Assignment",
		filters={"employee": employee, "status": ["in", ["Active", "Expired"]]},
		fields=[
			"name",
			"item_code",
			"item_name",
			"issue_date",
			"status",
			"last_inspection_date",
			"last_inspection_status",
			"next_inspection_due",
			"inspection_overdue",
		],
		order_by="inspection_overdue desc, next_inspection_due asc",
	)
	return {"employee": employee, "assignments": assignments}
