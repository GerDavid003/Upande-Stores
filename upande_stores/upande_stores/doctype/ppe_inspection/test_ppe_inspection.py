import frappe
from frappe.tests import IntegrationTestCase

from upande_stores.tests.test_helpers import get_test_employees, make_ppe_item


class IntegrationTestPPEInspection(IntegrationTestCase):
	def setUp(self):
		employees = get_test_employees(count=1)
		if not employees:
			self.skipTest("Need at least 1 Active Employee record on this site.")
		self.employee = employees[0]
		farm = frappe.db.get_value("Farm", {}, "name")
		if not farm:
			self.skipTest("No Farm record available on this site to run this test.")
		self.farm = farm

	def _assignment(self, status="Active"):
		return frappe.get_doc(
			{
				"doctype": "Employee PPE Assignment",
				"employee": self.employee,
				"item_code": make_ppe_item(),
				"quantity": 1,
				"company": "_Test Company",
				"issue_date": "2026-01-01",
				"lifespan_months": 6,
				"status": status,
			}
		).insert(ignore_permissions=True)

	def _submit_inspection(self, assignment, current_status):
		inspection = frappe.get_doc(
			{
				"doctype": "PPE Inspection",
				"employee": self.employee,
				"supervisor": self.employee,
				"farm": self.farm,
				"inspection_date": "2026-02-01",
				"items_inspected": [
					{
						"employee_ppe_assignment": assignment.name,
						"current_status": current_status,
						"update_assignment": 1,
					}
				],
			}
		)
		inspection.insert(ignore_permissions=True)
		inspection.submit()
		return inspection

	def test_lost_item_deactivates_assignment(self):
		assignment = self._assignment()
		inspection = self._submit_inspection(assignment, "Lost")

		assignment.reload()
		self.assertEqual(assignment.status, "Inactive")
		self.assertEqual(assignment.last_inspection_status, "Lost")
		self.assertEqual(assignment.last_inspection, inspection.name)

	def test_worn_out_item_deactivates_assignment(self):
		assignment = self._assignment()
		self._submit_inspection(assignment, "Worn Out")

		assignment.reload()
		self.assertEqual(assignment.status, "Inactive")

	def test_ok_item_reactivates_a_previously_inactive_assignment(self):
		assignment = self._assignment(status="Inactive")
		self._submit_inspection(assignment, "OK")

		assignment.reload()
		self.assertEqual(assignment.status, "Active")

	def test_skips_rows_with_update_assignment_unchecked(self):
		assignment = self._assignment()
		inspection = frappe.get_doc(
			{
				"doctype": "PPE Inspection",
				"employee": self.employee,
				"supervisor": self.employee,
				"farm": self.farm,
				"inspection_date": "2026-02-01",
				"items_inspected": [
					{
						"employee_ppe_assignment": assignment.name,
						"current_status": "Lost",
						"update_assignment": 0,
					}
				],
			}
		)
		inspection.insert(ignore_permissions=True)
		inspection.submit()

		assignment.reload()
		self.assertEqual(assignment.status, "Active")
