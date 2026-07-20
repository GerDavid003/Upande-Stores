import frappe
from frappe.tests import IntegrationTestCase

from upande_stores.api.ppe import get_ppe_requirements_for_onboarding
from upande_stores.tests.test_helpers import get_test_employees, make_ppe_item


class IntegrationTestGetPPERequirements(IntegrationTestCase):
	"""test_merges_quantities_across_matching_policies needs an Employee with
	BOTH Department and Designation set, because its two "matching" policies
	are constructed as one department-only row + one designation-only row
	(not two rows scoped identically to the same department): PPEPolicy's own
	active-duplicate-policy guard (Task 4) rejects two active policies for the
	same company with an identical (department, designation) pair, so two
	rows both scoped to the employee's department (the brief's original
	construction) always collide and raise ValidationError on the second
	insert -- verified directly against this site's data. get_test_employees()
	returns real site Employees in an unspecified order, and the first several
	Active ones here have Designation unset, so we search a wider batch for
	one that has both fields, rather than assuming employees[0] qualifies."""

	def setUp(self):
		employees = get_test_employees(count=20)
		candidate = None
		for emp in employees:
			vals = frappe.db.get_value(
				"Employee", emp, ["company", "department", "designation"], as_dict=True
			)
			if vals.department and vals.designation:
				candidate = (emp, vals)
				break
		if not candidate:
			self.skipTest("Need an Active Employee with both Department and Designation set.")
		self.employee, vals = candidate
		self.company, self.department, self.designation = vals.company, vals.department, vals.designation
		frappe.db.delete("PPE Policy", {"company": self.company, "department": self.department})
		frappe.db.delete("PPE Policy", {"company": self.company, "designation": self.designation})

	def test_merges_quantities_across_matching_policies(self):
		item_code = make_ppe_item()

		frappe.get_doc(
			{
				"doctype": "PPE Policy",
				"company": self.company,
				"department": self.department,
				"items": [{"item_code": item_code, "quantity": 2}],
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "PPE Policy",
				"company": self.company,
				"designation": self.designation,
				"items": [{"item_code": item_code, "quantity": 1}],
			}
		).insert(ignore_permissions=True)

		result = get_ppe_requirements_for_onboarding(self.employee)
		self.assertEqual(len(result), 1)
		self.assertEqual(result[0]["item_code"], item_code)
		self.assertEqual(result[0]["quantity"], 3)

	def test_ignores_policy_for_a_different_company(self):
		if not frappe.db.exists("Company", "_Test Company 1") or self.company == "_Test Company 1":
			self.skipTest("Need a second Company distinct from the test Employee's own Company.")

		frappe.get_doc(
			{
				"doctype": "PPE Policy",
				"company": "_Test Company 1",
				"department": self.department,
				"items": [{"item_code": make_ppe_item(), "quantity": 5}],
			}
		).insert(ignore_permissions=True)

		result = get_ppe_requirements_for_onboarding(self.employee)
		self.assertEqual(result, [])
