import frappe
from frappe.tests import IntegrationTestCase


class IntegrationTestPPESettings(IntegrationTestCase):
	"""PPE Settings is a Single doctype -- there is only ever one document.
	IntegrationTestCase only rolls back the DB at class teardown, not between
	individual test methods -- and unittest runs methods in alphabetical
	order. Each test below uses self.addCleanup() to reset
	company_notifications back to an empty list (and save) immediately after
	the test runs, so a row left behind by one test can't be mistaken for a
	pre-existing row by a later-running test method in this same class.
	"""

	def _get_role_profile(self):
		role_profiles = frappe.get_all("Role Profile", limit=1, pluck="name")
		if not role_profiles:
			self.skipTest("No Role Profile exists on this site.")
		return role_profiles[0]

	def _reset_company_notifications(self):
		doc = frappe.get_single("PPE Settings")
		doc.company_notifications = []
		doc.save(ignore_permissions=True)

	def test_requires_role_profile_in_company_row(self):
		self.addCleanup(self._reset_company_notifications)

		doc = frappe.get_single("PPE Settings")
		doc.append(
			"company_notifications",
			{
				"company": "_Test Company",
				"frequency": "Monthly",
			},
		)
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_requires_custom_frequency_days_when_custom(self):
		self.addCleanup(self._reset_company_notifications)
		role_profile = self._get_role_profile()

		doc = frappe.get_single("PPE Settings")
		doc.append(
			"company_notifications",
			{
				"company": "_Test Company",
				"frequency": "Custom",
				"notify_role_profile": role_profile,
			},
		)
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_blocks_duplicate_company_rows(self):
		self.addCleanup(self._reset_company_notifications)
		role_profile = self._get_role_profile()

		doc = frappe.get_single("PPE Settings")
		doc.append(
			"company_notifications",
			{
				"company": "_Test Company",
				"frequency": "Monthly",
				"notify_role_profile": role_profile,
			},
		)
		doc.append(
			"company_notifications",
			{
				"company": "_Test Company",
				"frequency": "Monthly",
				"notify_role_profile": role_profile,
			},
		)
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_allows_multiple_distinct_companies(self):
		if not frappe.db.exists("Company", "_Test Company 1"):
			self.skipTest("_Test Company 1 fixture not present on this site.")

		self.addCleanup(self._reset_company_notifications)
		role_profile = self._get_role_profile()

		doc = frappe.get_single("PPE Settings")
		doc.append(
			"company_notifications",
			{
				"company": "_Test Company",
				"frequency": "Monthly",
				"notify_role_profile": role_profile,
			},
		)
		doc.append(
			"company_notifications",
			{
				"company": "_Test Company 1",
				"frequency": "Monthly",
				"notify_role_profile": role_profile,
			},
		)
		doc.save(ignore_permissions=True)  # must not raise
