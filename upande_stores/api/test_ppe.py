import json

import frappe
from frappe.tests import IntegrationTestCase

from upande_stores.api.ppe import (
	create_ppe_onboarding_material_request,
	get_ppe_requirements_for_onboarding,
)
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

	def test_denies_low_privilege_user(self):
		"""PPE Policy's own DocPerm restricts read to System Manager, HR
		Manager, and Farm Manager. A caller with none of those roles must be
		rejected before the function touches any PPE Policy data -- it must
		not matter that get_ppe_requirements_for_onboarding uses
		frappe.db.get_value/frappe.get_all/frappe.get_doc internally, none of
		which enforce permissions on their own.

		mathias@abc.com is a pre-existing site user with only
		["Technician", "All", "Guest", "Desk User"] roles (checked directly
		via frappe.get_roles) -- none of the three permitted roles -- so it's
		reused here rather than creating a new test user."""
		low_privilege_user = "mathias@abc.com"
		if not frappe.db.exists("User", low_privilege_user):
			self.skipTest(f"Expected pre-existing low-privilege user {low_privilege_user} not found.")
		roles = set(frappe.get_roles(low_privilege_user))
		privileged_roles = {"System Manager", "HR Manager", "Farm Manager"}
		if roles & privileged_roles:
			self.skipTest(
				f"{low_privilege_user} unexpectedly has a privileged role ({roles & privileged_roles})."
			)

		original_user = frappe.session.user
		self.addCleanup(frappe.set_user, original_user)
		frappe.set_user(low_privilege_user)

		with self.assertRaises(frappe.PermissionError):
			get_ppe_requirements_for_onboarding(self.employee)


def _ensure_job_offer_has_valid_till(applicant_name):
	"""Pre-empt a genuine gap in hrms's own `create_job_offer()`/`get_job_offer()`
	test helpers (used by make_draft_employee_onboarding below): this site has
	a `valid_till` Custom Field on Job Offer (confirmed directly --
	`frappe.get_all("Custom Field", filters={"dt": "Job Offer"})` returns it,
	`reqd=1` -- it's not part of hrms's own `job_offer.json` schema, and not
	tracked by any fixture in this app or `upande_hr`, so it's real,
	pre-existing site configuration, not something to remove unilaterally).
	`create_job_offer()` never sets it, so `get_job_offer()`'s own
	`.submit()` call always raises `MandatoryError: valid_till` on this site.

	Inserting a fully valid, already-submitted Job Offer for this applicant
	*first* means `get_job_offer()`'s own idempotency check
	(`frappe.db.exists("Job Offer", {"job_applicant": applicant_name})`)
	finds it and returns early, never reaching the broken path -- so
	`get_job_offer()` itself stays untouched/reused as-is."""
	if frappe.db.exists("Job Offer", {"job_applicant": applicant_name}):
		return
	job_offer = frappe.get_doc(
		{
			"doctype": "Job Offer",
			"job_applicant": applicant_name,
			"offer_date": frappe.utils.nowdate(),
			"designation": "Researcher",
			"status": "Accepted",
			"company": "_Test Company",
			"valid_till": frappe.utils.add_months(frappe.utils.nowdate(), 1),
		}
	)
	job_offer.insert(ignore_permissions=True)
	job_offer.submit()


def make_draft_employee_onboarding(employee):
	"""A minimal, not-submitted Employee Onboarding with `employee` pre-set.

	Employee Onboarding requires job_applicant/job_offer/date_of_joining/
	boarding_begins_on (verified against this site's DocField list -- it's not
	just `employee` + `boarding_status`). Reuses hrms's own test builders for
	those two link targets rather than re-implementing them; unlike hrms's own
	`create_employee_onboarding()` helper (which also submits the document),
	this one stays a draft, matching how the real Fetch/Create PPE buttons are
	used before onboarding is complete.
	"""
	from hrms.hr.doctype.employee_onboarding.test_employee_onboarding import (
		get_job_applicant,
		get_job_offer,
	)
	from hrms.payroll.doctype.salary_slip.test_salary_slip import make_holiday_list

	applicant = get_job_applicant()
	_ensure_job_offer_has_valid_till(applicant.name)
	job_offer = get_job_offer(applicant.name)
	holiday_list = make_holiday_list("_Test Employee Boarding")

	onboarding = frappe.new_doc("Employee Onboarding")
	onboarding.employee = employee
	onboarding.job_applicant = applicant.name
	onboarding.job_offer = job_offer.name
	onboarding.date_of_joining = onboarding.boarding_begins_on = frappe.utils.getdate()
	onboarding.company = "_Test Company"
	onboarding.holiday_list = holiday_list
	onboarding.designation = "Engineer"
	onboarding.append(
		"activities",
		{
			"activity_name": "Assign ID Card",
			"role": "HR User",
			"required_for_employee_creation": 1,
			"begin_on": 0,
			"duration": 1,
		},
	)
	onboarding.insert(ignore_permissions=True)
	return onboarding


class IntegrationTestCreatePPEOnboardingMR(IntegrationTestCase):
	"""create_ppe_onboarding_material_request() copies custom_farm/custom_business_unit
	from the Employee onto the Material Request it creates, and both are
	mandatory Custom Fields on Material Request on this site (confirmed
	directly -- frappe.get_all("Custom Field", filters={"dt": "Material
	Request", "fieldname": ["in", ["custom_farm", "custom_business_unit"]]})
	shows reqd=1 for both). get_test_employees()'s unspecified ordering
	doesn't guarantee the first Active Employee has either field set, so
	(same pattern as IntegrationTestGetPPERequirements.setUp) we search a
	wider batch for one that has both, rather than assuming employees[0]
	qualifies -- otherwise every insert() below would fail with
	MandatoryError regardless of the code under test."""

	def setUp(self):
		employees = get_test_employees(count=20)
		candidate = None
		for emp in employees:
			vals = frappe.db.get_value(
				"Employee", emp, ["custom_farm", "custom_business_unit"], as_dict=True
			)
			if vals.custom_farm and vals.custom_business_unit:
				candidate = emp
				break
		if not candidate:
			self.skipTest(
				"Need an Active Employee with both custom_farm and custom_business_unit set."
			)
		self.employee = candidate
		self.onboarding = make_draft_employee_onboarding(self.employee)

	def test_blocks_a_second_request_for_the_same_onboarding(self):
		item_code = make_ppe_item()
		create_ppe_onboarding_material_request(
			onboarding=self.onboarding.name,
			employee=self.employee,
			items=json.dumps([{"item_code": item_code, "quantity": 1}]),
		)
		with self.assertRaises(frappe.ValidationError):
			create_ppe_onboarding_material_request(
				onboarding=self.onboarding.name,
				employee=self.employee,
				items=json.dumps([{"item_code": item_code, "quantity": 1}]),
			)

	def test_creates_material_issue_with_ppe_issuance_checked(self):
		item_code = make_ppe_item()
		mr_name = create_ppe_onboarding_material_request(
			onboarding=self.onboarding.name,
			employee=self.employee,
			items=json.dumps([{"item_code": item_code, "quantity": 1}]),
		)
		mr = frappe.get_doc("Material Request", mr_name)
		self.assertEqual(mr.material_request_type, "Material Issue")
		self.assertEqual(mr.custom_ppe_issuance, 1)
		self.assertEqual(mr.items[0].description, "PPE Issuance")
		self.onboarding.reload()
		self.assertEqual(self.onboarding.custom_ppe_material_request, mr_name)

	def test_denies_low_privilege_user(self):
		"""Employee Onboarding's own DocPerm restricts write to System Manager,
		HR Manager, and HR User. A caller with none of those roles must be
		rejected before the function writes anything to the Employee
		Onboarding record (or creates a Material Request) -- it must not
		matter that create_ppe_onboarding_material_request uses
		frappe.db.get_value/frappe.db.set_value internally for that record,
		neither of which enforce permissions on their own.

		mathias@abc.com is the same pre-existing site user reused from
		IntegrationTestGetPPERequirements.test_denies_low_privilege_user
		(only ["Technician", "All", "Guest", "Desk User"] roles, checked
		directly via frappe.get_roles) -- none of the three permitted
		Employee Onboarding write roles, so it's reused here too rather than
		creating a new test user."""
		low_privilege_user = "mathias@abc.com"
		if not frappe.db.exists("User", low_privilege_user):
			self.skipTest(f"Expected pre-existing low-privilege user {low_privilege_user} not found.")
		roles = set(frappe.get_roles(low_privilege_user))
		privileged_roles = {"System Manager", "HR Manager", "HR User"}
		if roles & privileged_roles:
			self.skipTest(
				f"{low_privilege_user} unexpectedly has a privileged role ({roles & privileged_roles})."
			)

		item_code = make_ppe_item()
		original_user = frappe.session.user
		self.addCleanup(frappe.set_user, original_user)
		frappe.set_user(low_privilege_user)

		with self.assertRaises(frappe.PermissionError):
			create_ppe_onboarding_material_request(
				onboarding=self.onboarding.name,
				employee=self.employee,
				items=json.dumps([{"item_code": item_code, "quantity": 1}]),
			)
