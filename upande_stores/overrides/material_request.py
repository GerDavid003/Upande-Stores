import frappe
from frappe import _


def validate_no_duplicate_employees(doc, method=None):
	"""Material Request validate hook: block saving if the same employee
	appears more than once in custom_employee_data. Runs on every save (not
	just once), so a duplicate can't be introduced after the fact -- and it
	protects the Stock Entry lock/unlock logic (Task 3), which would
	otherwise have an ambiguous row to match against.
	"""
	seen = set()
	for row in doc.get("custom_employee_data") or []:
		if not row.employee:
			continue
		if row.employee in seen:
			frappe.throw(
				_("Employee {0} appears more than once in Employee Data.").format(
					frappe.bold(row.employee)
				)
			)
		seen.add(row.employee)


def unlink_ppe_replacement(doc, method=None):
	"""Material Request on_cancel/on_trash: if this MR was a PPE Issuance
	request, clear the replacement lock on any Employee PPE Assignment
	pointing at it."""
	if not doc.get("custom_ppe_issuance"):
		return
	for name in frappe.get_all(
		"Employee PPE Assignment", filters={"replacement_material_request": doc.name}, pluck="name"
	):
		frappe.db.set_value(
			"Employee PPE Assignment",
			name,
			{"replacement_requested": 0, "replacement_material_request": None},
		)
