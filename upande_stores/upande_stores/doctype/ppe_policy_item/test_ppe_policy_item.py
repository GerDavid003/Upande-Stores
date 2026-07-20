import frappe
from frappe.tests import IntegrationTestCase

from upande_stores.tests.test_helpers import make_ppe_item


class IntegrationTestPPEPolicyItem(IntegrationTestCase):
	def test_rejects_non_ppe_item(self):
		if not frappe.db.exists("Item", "_Test Item"):
			self.skipTest("Standard _Test Item fixture not present on this site.")

		policy = frappe.get_doc(
			{
				"doctype": "PPE Policy",
				"company": "_Test Company",
				"department": "_Test Department - _TC",
				"items": [{"item_code": "_Test Item", "quantity": 1}],
			}
		)
		with self.assertRaises(frappe.ValidationError):
			policy.insert(ignore_permissions=True)

	def test_accepts_ppe_item(self):
		policy = frappe.get_doc(
			{
				"doctype": "PPE Policy",
				"company": "_Test Company",
				"department": "_Test Department - _TC",
				"items": [{"item_code": make_ppe_item(), "quantity": 2}],
			}
		)
		policy.insert(ignore_permissions=True)
		self.assertEqual(policy.items[0].quantity, 2)
