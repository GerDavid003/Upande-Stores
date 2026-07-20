import frappe
from frappe.tests import IntegrationTestCase

from upande_stores.tests.test_helpers import get_test_employees, make_ppe_item


class IntegrationTestEmployeePPEAssignment(IntegrationTestCase):
	def setUp(self):
		employees = get_test_employees(count=1)
		if not employees:
			self.skipTest("Need at least 1 Active Employee record on this site.")
		self.employee = employees[0]

	def test_computes_expiry_date_from_lifespan(self):
		assignment = frappe.get_doc(
			{
				"doctype": "Employee PPE Assignment",
				"employee": self.employee,
				"item_code": make_ppe_item(),
				"quantity": 1,
				"company": "_Test Company",
				"issue_date": "2026-01-01",
				"lifespan_months": 6,
				"status": "Active",
			}
		).insert(ignore_permissions=True)
		self.assertEqual(str(assignment.expiry_date), "2026-07-01")

	def test_does_not_overwrite_an_explicit_expiry_date(self):
		assignment = frappe.get_doc(
			{
				"doctype": "Employee PPE Assignment",
				"employee": self.employee,
				"item_code": make_ppe_item(),
				"quantity": 1,
				"company": "_Test Company",
				"issue_date": "2026-01-01",
				"lifespan_months": 6,
				"expiry_date": "2026-03-01",
				"status": "Active",
			}
		).insert(ignore_permissions=True)
		self.assertEqual(str(assignment.expiry_date), "2026-03-01")

	def test_syncs_to_employee_ppe_history_when_upande_hr_installed(self):
		if "upande_hr" not in frappe.get_installed_apps():
			self.skipTest("upande_hr not installed on this site.")

		assignment = frappe.get_doc(
			{
				"doctype": "Employee PPE Assignment",
				"employee": self.employee,
				"item_code": make_ppe_item(),
				"quantity": 1,
				"company": "_Test Company",
				"issue_date": "2026-01-01",
				"lifespan_months": 6,
				"status": "Active",
			}
		).insert(ignore_permissions=True)

		history_row = frappe.db.get_value(
			"Employee PPE History",
			{"ppe_assignment": assignment.name, "parent": self.employee},
			["status", "expiry_date"],
			as_dict=True,
		)
		self.assertTrue(history_row)
		self.assertEqual(history_row.status, "Active")

		assignment.status = "Inactive"
		assignment.save(ignore_permissions=True)

		self.assertEqual(
			frappe.db.get_value(
				"Employee PPE History",
				{"ppe_assignment": assignment.name, "parent": self.employee},
				"status",
			),
			"Inactive",
		)
