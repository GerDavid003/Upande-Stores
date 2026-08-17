import frappe
from frappe.tests import IntegrationTestCase

from upande_stores.tests.test_helpers import get_test_employees, make_ppe_item


def _make_ppe_inspection_for(employee, assignment):
	"""Insert (draft) a minimal valid PPE Inspection so its name can be used as
	a real Link target for Employee PPE Assignment.last_inspection. Returns the
	inspection's name; skips gracefully via the caller if no Farm exists."""
	farm = frappe.db.get_value("Farm", {}, "name")
	inspection = frappe.get_doc(
		{
			"doctype": "PPE Inspection",
			"employee": employee,
			"supervisor": employee,
			"farm": farm,
			"inspection_date": "2026-02-01",
			"items_inspected": [
				{
					"employee_ppe_assignment": assignment.name,
					"current_status": "OK",
					"update_assignment": 0,
				}
			],
		}
	)
	inspection.insert(ignore_permissions=True)
	return inspection.name


class IntegrationTestEmployeePPEAssignment(IntegrationTestCase):
	def setUp(self):
		employees = get_test_employees(count=1)
		if not employees:
			self.skipTest("Need at least 1 Active Employee record on this site.")
		self.employee = employees[0]

	def test_computes_expiry_date_from_lifespan(self):
		assignment = frappe.get_doc(
			{
				"doctype": "Employee PPE Assignment",
				"employee": self.employee,
				"item_code": make_ppe_item(),
				"quantity": 1,
				"company": "_Test Company",
				"issue_date": "2026-01-01",
				"lifespan_months": 6,
				"status": "Active",
			}
		).insert(ignore_permissions=True)
		self.assertEqual(str(assignment.expiry_date), "2026-07-01")

	def test_does_not_overwrite_an_explicit_expiry_date(self):
		assignment = frappe.get_doc(
			{
				"doctype": "Employee PPE Assignment",
				"employee": self.employee,
				"item_code": make_ppe_item(),
				"quantity": 1,
				"company": "_Test Company",
				"issue_date": "2026-01-01",
				"lifespan_months": 6,
				"expiry_date": "2026-03-01",
				"status": "Active",
			}
		).insert(ignore_permissions=True)
		self.assertEqual(str(assignment.expiry_date), "2026-03-01")

	def test_syncs_to_employee_ppe_history_when_upande_hr_installed(self):
		if "upande_hr" not in frappe.get_installed_apps():
			self.skipTest("upande_hr not installed on this site.")

		assignment = frappe.get_doc(
			{
				"doctype": "Employee PPE Assignment",
				"employee": self.employee,
				"item_code": make_ppe_item(),
				"quantity": 1,
				"company": "_Test Company",
				"issue_date": "2026-01-01",
				"lifespan_months": 6,
				"status": "Active",
			}
		).insert(ignore_permissions=True)

		history_row = frappe.db.get_value(
			"Employee PPE History",
			{"ppe_assignment": assignment.name, "parent": self.employee},
			["status", "expiry_date"],
			as_dict=True,
		)
		self.assertTrue(history_row)
		self.assertEqual(history_row.status, "Active")

		assignment.status = "Inactive"
		assignment.save(ignore_permissions=True)

		self.assertEqual(
			frappe.db.get_value(
				"Employee PPE History",
				{"ppe_assignment": assignment.name, "parent": self.employee},
				"status",
			),
			"Inactive",
		)

	def test_on_trash_deletes_the_history_row(self):
		# Finding 2: deleting an assignment must remove its Employee PPE History
		# row, not leave an orphan with a dangling ppe_assignment link.
		if "upande_hr" not in frappe.get_installed_apps():
			self.skipTest("upande_hr not installed on this site.")

		assignment = frappe.get_doc(
			{
				"doctype": "Employee PPE Assignment",
				"employee": self.employee,
				"item_code": make_ppe_item(),
				"quantity": 1,
				"company": "_Test Company",
				"issue_date": "2026-01-01",
				"lifespan_months": 6,
				"status": "Active",
			}
		).insert(ignore_permissions=True)
		name = assignment.name
		self.assertTrue(
			frappe.db.exists("Employee PPE History", {"ppe_assignment": name, "parent": self.employee})
		)

		frappe.delete_doc("Employee PPE Assignment", name, ignore_permissions=True)

		self.assertFalse(
			frappe.db.exists("Employee PPE History", {"ppe_assignment": name, "parent": self.employee})
		)

	def test_on_trash_clears_inbound_replacement_assignment_link(self):
		# A prior assignment's replacement_assignment can point at this one (the
		# PPE replacement flow) -- that inbound link must not block a direct
		# delete of this assignment via the Desk UI, not just when triggered
		# indirectly by a Stock Entry cancel (which already handled this).
		item_code = make_ppe_item()
		new_assignment = frappe.get_doc(
			{
				"doctype": "Employee PPE Assignment",
				"employee": self.employee,
				"item_code": item_code,
				"quantity": 1,
				"company": "_Test Company",
				"issue_date": "2026-01-01",
				"lifespan_months": 6,
				"status": "Active",
			}
		).insert(ignore_permissions=True)
		old_assignment = frappe.get_doc(
			{
				"doctype": "Employee PPE Assignment",
				"employee": self.employee,
				"item_code": item_code,
				"quantity": 1,
				"company": "_Test Company",
				"issue_date": "2025-06-01",
				"lifespan_months": 6,
				"status": "Inactive",
				"replacement_assignment": new_assignment.name,
			}
		).insert(ignore_permissions=True)

		frappe.delete_doc(
			"Employee PPE Assignment", new_assignment.name, ignore_permissions=True
		)  # must not raise LinkExistsError

		self.assertFalse(frappe.db.exists("Employee PPE Assignment", new_assignment.name))
		self.assertFalse(
			frappe.db.get_value("Employee PPE Assignment", old_assignment.name, "replacement_assignment")
		)

	def test_on_trash_clears_ppe_inspection_item_link(self):
		# A PPE Inspection Item child row can hold a link to this assignment --
		# cancelling the inspection it belongs to does not clear that link
		# (PPEInspection.on_cancel only reverts the assignment's status). A
		# direct delete of this assignment must not be blocked by it, not just
		# when triggered indirectly by a Stock Entry cancel (which already
		# handled this).
		if not frappe.db.get_value("Farm", {}, "name"):
			self.skipTest("No Farm record available to build a PPE Inspection link target.")

		assignment = frappe.get_doc(
			{
				"doctype": "Employee PPE Assignment",
				"employee": self.employee,
				"item_code": make_ppe_item(),
				"quantity": 1,
				"company": "_Test Company",
				"issue_date": "2026-01-01",
				"lifespan_months": 6,
				"status": "Active",
			}
		).insert(ignore_permissions=True)
		inspection_name = _make_ppe_inspection_for(self.employee, assignment)
		item_row_name = frappe.db.get_value(
			"PPE Inspection Item", {"employee_ppe_assignment": assignment.name}, "name"
		)
		self.assertTrue(item_row_name)

		frappe.delete_doc(
			"Employee PPE Assignment", assignment.name, ignore_permissions=True
		)  # must not raise LinkExistsError

		self.assertFalse(frappe.db.exists("Employee PPE Assignment", assignment.name))
		self.assertFalse(frappe.db.get_value("PPE Inspection Item", item_row_name, "employee_ppe_assignment"))
		self.assertTrue(frappe.db.exists("PPE Inspection", inspection_name))

	def test_syncs_ppe_inspection_link_into_history(self):
		# Finding 4: on_update must push last_inspection into the history row's
		# ppe_inspection link (previously declared but never populated).
		if "upande_hr" not in frappe.get_installed_apps():
			self.skipTest("upande_hr not installed on this site.")
		if not frappe.db.get_value("Farm", {}, "name"):
			self.skipTest("No Farm record available to build a PPE Inspection link target.")

		assignment = frappe.get_doc(
			{
				"doctype": "Employee PPE Assignment",
				"employee": self.employee,
				"item_code": make_ppe_item(),
				"quantity": 1,
				"company": "_Test Company",
				"issue_date": "2026-01-01",
				"lifespan_months": 6,
				"status": "Active",
			}
		).insert(ignore_permissions=True)

		inspection = _make_ppe_inspection_for(self.employee, assignment)

		assignment.last_inspection = inspection
		assignment.save(ignore_permissions=True)

		self.assertEqual(
			frappe.db.get_value(
				"Employee PPE History",
				{"ppe_assignment": assignment.name, "parent": self.employee},
				"ppe_inspection",
			),
			inspection,
		)
