import frappe
from frappe.tests import IntegrationTestCase

from upande_stores.tests.test_helpers import make_ppe_item


class IntegrationTestPPEPolicy(IntegrationTestCase):
	"""IntegrationTestCase only rolls back the DB at class teardown, not
	between individual test methods -- and unittest runs methods in
	alphabetical order. self.addCleanup() below removes each test's own
	"_Test Company" / "_Test Department - _TC" PPE Policy immediately so it
	can't be mistaken for a pre-existing duplicate by a later-running test
	method in this same class.
	"""

	def test_requires_department_or_designation(self):
		policy = frappe.get_doc(
			{
				"doctype": "PPE Policy",
				"company": "_Test Company",
				"items": [{"item_code": make_ppe_item(), "quantity": 1}],
			}
		)
		with self.assertRaises(frappe.ValidationError):
			policy.insert(ignore_permissions=True)

	def test_blocks_duplicate_active_policy_for_same_company(self):
		item_code = make_ppe_item()
		first = frappe.get_doc(
			{
				"doctype": "PPE Policy",
				"company": "_Test Company",
				"department": "_Test Department - _TC",
				"items": [{"item_code": item_code, "quantity": 1}],
			}
		)
		first.insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "PPE Policy", first.name, ignore_permissions=True)

		duplicate = frappe.get_doc(
			{
				"doctype": "PPE Policy",
				"company": "_Test Company",
				"department": "_Test Department - _TC",
				"items": [{"item_code": item_code, "quantity": 1}],
			}
		)
		with self.assertRaises(frappe.ValidationError):
			duplicate.insert(ignore_permissions=True)

	def test_allows_same_department_for_a_different_company(self):
		if not frappe.db.exists("Company", "_Test Company 1"):
			self.skipTest("_Test Company 1 fixture not present on this site.")

		item_code = make_ppe_item()
		first = frappe.get_doc(
			{
				"doctype": "PPE Policy",
				"company": "_Test Company",
				"department": "_Test Department - _TC",
				"items": [{"item_code": item_code, "quantity": 1}],
			}
		)
		first.insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "PPE Policy", first.name, ignore_permissions=True)

		other_company = frappe.get_doc(
			{
				"doctype": "PPE Policy",
				"company": "_Test Company 1",
				"department": "_Test Department - _TC",
				"items": [{"item_code": item_code, "quantity": 1}],
			}
		)
		other_company.insert(ignore_permissions=True)  # must not raise
		self.addCleanup(frappe.delete_doc, "PPE Policy", other_company.name, ignore_permissions=True)
		self.assertTrue(other_company.name)
