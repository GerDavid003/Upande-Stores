import frappe
from frappe.tests import IntegrationTestCase

from upande_stores.tasks import mark_expired_ppe_assignments
from upande_stores.tests.test_helpers import get_test_employees, make_ppe_item


class IntegrationTestMarkExpiredPPEAssignments(IntegrationTestCase):
	def setUp(self):
		employees = get_test_employees(count=1)
		if not employees:
			self.skipTest("Need at least 1 Active Employee record on this site.")
		self.employee = employees[0]

	def test_marks_past_expiry_active_assignment_as_expired(self):
		assignment = frappe.get_doc(
			{
				"doctype": "Employee PPE Assignment",
				"employee": self.employee,
				"item_code": make_ppe_item(),
				"quantity": 1,
				"company": "_Test Company",
				"issue_date": "2020-01-01",
				"expiry_date": "2020-07-01",
				"lifespan_months": 6,
				"status": "Active",
			}
		).insert(ignore_permissions=True)

		mark_expired_ppe_assignments()

		self.assertEqual(frappe.db.get_value("Employee PPE Assignment", assignment.name, "status"), "Expired")

	def test_syncs_employee_ppe_history_status_when_upande_hr_installed(self):
		if "upande_hr" not in frappe.get_installed_apps():
			self.skipTest("upande_hr not installed on this site.")

		assignment = frappe.get_doc(
			{
				"doctype": "Employee PPE Assignment",
				"employee": self.employee,
				"item_code": make_ppe_item(),
				"quantity": 1,
				"company": "_Test Company",
				"issue_date": "2020-01-01",
				"expiry_date": "2020-07-01",
				"lifespan_months": 6,
				"status": "Active",
			}
		).insert(ignore_permissions=True)

		self.assertEqual(
			frappe.db.get_value(
				"Employee PPE History",
				{"ppe_assignment": assignment.name, "parent": self.employee},
				"status",
			),
			"Active",
		)

		mark_expired_ppe_assignments()

		self.assertEqual(frappe.db.get_value("Employee PPE Assignment", assignment.name, "status"), "Expired")
		self.assertEqual(
			frappe.db.get_value(
				"Employee PPE History",
				{"ppe_assignment": assignment.name, "parent": self.employee},
				"status",
			),
			"Expired",
		)

	def test_leaves_future_expiry_assignment_active(self):
		assignment = frappe.get_doc(
			{
				"doctype": "Employee PPE Assignment",
				"employee": self.employee,
				"item_code": make_ppe_item(),
				"quantity": 1,
				"company": "_Test Company",
				"issue_date": frappe.utils.today(),
				"lifespan_months": 60,
				"status": "Active",
			}
		).insert(ignore_permissions=True)

		mark_expired_ppe_assignments()

		self.assertEqual(frappe.db.get_value("Employee PPE Assignment", assignment.name, "status"), "Active")
