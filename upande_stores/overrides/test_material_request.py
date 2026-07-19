import frappe
from frappe.tests import IntegrationTestCase

from upande_stores.tests.test_helpers import (
	get_test_farm_and_business_unit,
	make_material_request,
)


class IntegrationTestMaterialRequestEmployeeValidation(IntegrationTestCase):
	def setUp(self):
		farm, business_unit = get_test_farm_and_business_unit()
		if not farm or not business_unit:
			self.skipTest("No Farm/Business Unit record on this site to build a valid test Material Request.")

	def test_rejects_duplicate_employee_in_employee_data(self):
		with self.assertRaises(frappe.ValidationError):
			make_material_request(
				employee_rows=[
					{"employee": "HR-EMP-00001"},
					{"employee": "HR-EMP-00001"},
				]
			)

	def test_allows_distinct_employees_in_employee_data(self):
		mr = make_material_request(
			employee_rows=[
				{"employee": "HR-EMP-00001"},
				{"employee": "HR-EMP-00002"},
			]
		)
		self.assertEqual(len(mr.custom_employee_data), 2)
