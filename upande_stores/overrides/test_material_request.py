import frappe
from frappe.tests import IntegrationTestCase

from upande_stores.tests.test_helpers import (
	get_test_employees,
	get_test_farm_and_business_unit,
	make_material_request,
	make_ppe_item,
)


class IntegrationTestMaterialRequestEmployeeValidation(IntegrationTestCase):
	def setUp(self):
		farm, business_unit = get_test_farm_and_business_unit()
		if not farm or not business_unit:
			self.skipTest("No Farm/Business Unit record on this site to build a valid test Material Request.")
		self.employees = get_test_employees(count=2)
		if len(self.employees) < 2:
			self.skipTest("Need at least 2 Active Employee records on this site.")

	def test_rejects_duplicate_employee_in_employee_data(self):
		emp = self.employees[0]
		with self.assertRaises(frappe.ValidationError):
			make_material_request(
				employee_rows=[
					{"employee": emp},
					{"employee": emp},
				]
			)

	def test_allows_distinct_employees_in_employee_data(self):
		emp1, emp2 = self.employees
		mr = make_material_request(
			employee_rows=[
				{"employee": emp1},
				{"employee": emp2},
			]
		)
		self.assertEqual(len(mr.custom_employee_data), 2)


class IntegrationTestMaterialRequestPPEUnlink(IntegrationTestCase):
	def setUp(self):
		self.farm, self.business_unit = get_test_farm_and_business_unit()
		if not self.farm or not self.business_unit:
			self.skipTest("No Farm/Business Unit record on this site to build a valid test Material Request.")
		employees = get_test_employees(count=1)
		if not employees:
			self.skipTest("Need at least 1 Active Employee record on this site.")
		self.employee = employees[0]

	def test_cancel_clears_the_replacement_lock(self):
		assignment = frappe.get_doc(
			{
				"doctype": "Employee PPE Assignment",
				"employee": self.employee,
				"item_code": make_ppe_item(),
				"quantity": 1,
				"company": "_Test Company",
				"issue_date": "2026-01-01",
				"lifespan_months": 6,
				"status": "Inactive",
			}
		).insert(ignore_permissions=True)

		mr = frappe.get_doc(
			{
				"doctype": "Material Request",
				"material_request_type": "Material Issue",
				"transaction_date": frappe.utils.today(),
				"company": "_Test Company",
				"custom_farm": self.farm,
				"custom_business_unit": self.business_unit,
				"custom_ppe_issuance": 1,
				"items": [
					{
						"item_code": "_Test Item",
						"qty": 1,
						"uom": "_Test UOM",
						"stock_uom": "_Test UOM",
						"conversion_factor": 1,
						"schedule_date": frappe.utils.today(),
						"warehouse": "_Test Warehouse - _TC",
					}
				],
			}
		)
		mr.insert(ignore_permissions=True)
		frappe.db.set_value(
			"Employee PPE Assignment",
			assignment.name,
			{"replacement_requested": 1, "replacement_material_request": mr.name},
		)

		mr.submit()
		mr.cancel()

		assignment.reload()
		self.assertEqual(assignment.replacement_requested, 0)
		self.assertFalse(assignment.replacement_material_request)

	def test_non_ppe_material_request_cancel_is_a_noop(self):
		mr = frappe.get_doc(
			{
				"doctype": "Material Request",
				"material_request_type": "Material Issue",
				"transaction_date": frappe.utils.today(),
				"company": "_Test Company",
				"custom_farm": self.farm,
				"custom_business_unit": self.business_unit,
				"items": [
					{
						"item_code": "_Test Item",
						"qty": 1,
						"uom": "_Test UOM",
						"stock_uom": "_Test UOM",
						"conversion_factor": 1,
						"schedule_date": frappe.utils.today(),
						"warehouse": "_Test Warehouse - _TC",
					}
				],
			}
		)
		mr.insert(ignore_permissions=True)
		mr.submit()
		mr.cancel()  # must not raise
