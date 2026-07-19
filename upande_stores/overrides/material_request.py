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
