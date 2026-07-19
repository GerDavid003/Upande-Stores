import frappe
from frappe.tests import IntegrationTestCase

from upande_stores.tests.test_helpers import (
	get_test_employees,
	get_test_farm_and_business_unit,
	make_material_request,
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
