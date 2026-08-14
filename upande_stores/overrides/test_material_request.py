import frappe
from frappe.tests import IntegrationTestCase

from upande_stores.tests.test_helpers import (
	get_test_employees,
	get_test_farm_and_business_unit,
	make_material_request,
	make_ppe_item,
)


class IntegrationTestMaterialRequestEmployeeAllocations(IntegrationTestCase):
	def setUp(self):
		farm, business_unit = get_test_farm_and_business_unit()
		if not farm or not business_unit:
			self.skipTest("No Farm/Business Unit record on this site to build a valid test Material Request.")
		self.employees = get_test_employees(count=2)
		if len(self.employees) < 2:
			self.skipTest("Need at least 2 Active Employee records on this site.")

	def test_material_issue_requires_employee_on_every_row(self):
		with self.assertRaises(frappe.ValidationError):
			make_material_request(items=[{"item_code": "_Test Item", "qty": 1}])

	def test_material_issue_with_employee_on_every_row_succeeds(self):
		emp = self.employees[0]
		mr = make_material_request(items=[{"employee": emp, "item_code": "_Test Item", "qty": 1}])
		self.assertEqual(mr.items[0].employee, emp)

	def test_material_issue_requires_employee_on_every_row_even_if_one_has_it(self):
		emp = self.employees[0]
		with self.assertRaises(frappe.ValidationError):
			make_material_request(
				items=[
					{"employee": emp, "item_code": "_Test Item", "qty": 1},
					{"item_code": "_Test Item 2", "qty": 1},
				]
			)

	def test_material_transfer_does_not_require_employee(self):
		mr = make_material_request(
			items=[{"item_code": "_Test Item", "qty": 1}],
			material_request_type="Material Transfer",
		)
		self.assertFalse(mr.items[0].employee)  # must not raise

	def test_allows_same_employee_with_different_items(self):
		emp = self.employees[0]
		mr = make_material_request(
			items=[
				{"employee": emp, "item_code": "_Test Item", "qty": 5},
				{"employee": emp, "item_code": "_Test Item 2", "qty": 3},
			]
		)
		self.assertEqual(len(mr.items), 2)

	def test_rejects_duplicate_employee_and_item_pair(self):
		emp = self.employees[0]
		with self.assertRaises(frappe.ValidationError):
			make_material_request(
				items=[
					{"employee": emp, "item_code": "_Test Item", "qty": 5},
					{"employee": emp, "item_code": "_Test Item", "qty": 3},
				]
			)

	def test_allows_duplicate_item_when_employee_is_blank_on_both(self):
		mr = make_material_request(
			items=[
				{"item_code": "_Test Item", "qty": 5},
				{"item_code": "_Test Item", "qty": 3},
			],
			material_request_type="Material Transfer",
		)
		self.assertEqual(len(mr.items), 2)  # must not raise


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
				"company": "Karen Roses",
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
						"warehouse": "Stores - KR",
						"employee": self.employee,
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
				"company": "Karen Roses",
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
						"warehouse": "Stores - KR",
						"employee": self.employee,
					}
				],
			}
		)
		mr.insert(ignore_permissions=True)
		mr.submit()
		mr.cancel()  # must not raise


class IntegrationTestMaterialRequestAccountingDimensionSync(IntegrationTestCase):
	def setUp(self):
		farm, business_unit = get_test_farm_and_business_unit()
		if not farm or not business_unit:
			self.skipTest("No Farm/Business Unit record on this site to build a valid test Material Request.")
		employees = get_test_employees(count=1)
		if not employees:
			self.skipTest("Need at least 1 Active Employee record on this site.")
		self.employee = employees[0]

	def test_header_farm_and_business_unit_sync_to_every_item_row(self):
		mr = make_material_request(items=[{"employee": self.employee}])
		self.assertTrue(mr.custom_farm)
		self.assertTrue(mr.custom_business_unit)
		for row in mr.items:
			self.assertEqual(row.farm, mr.custom_farm)
			self.assertEqual(row.business_unit, mr.custom_business_unit)
