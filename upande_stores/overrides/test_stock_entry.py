import frappe
from frappe.tests import IntegrationTestCase

from upande_stores.overrides.stock_entry import inherit_accounting_dimensions_from_material_request
from upande_stores.tests.test_helpers import (
	get_test_employees,
	get_test_farm_and_business_unit,
	make_material_request,
	make_ppe_item,
	make_stock_entry_for_material_request,
)


class IntegrationTestStockEntryEmployeeLock(IntegrationTestCase):
	def setUp(self):
		farm, business_unit = get_test_farm_and_business_unit()
		if not farm or not business_unit:
			self.skipTest("No Farm/Business Unit record on this site to build a valid test document.")
		employees = get_test_employees(count=1)
		if not employees:
			self.skipTest("Need at least 1 Active Employee record on this site.")
		self.employee = employees[0]

	def test_submit_locks_the_employee_request_row(self):
		mr = make_material_request(employee_rows=[{"employee": self.employee}])
		se = make_stock_entry_for_material_request(mr, bio_employee=self.employee)
		se.submit()

		row_name = frappe.db.get_value(
			"Employee Request", {"parent": mr.name, "employee": self.employee}, "name"
		)
		self.assertEqual(
			frappe.db.get_value("Employee Request", row_name, "issued_via_stock_entry"),
			se.name,
		)

	def test_cancel_unlocks_the_employee_request_row(self):
		mr = make_material_request(employee_rows=[{"employee": self.employee}])
		se = make_stock_entry_for_material_request(mr, bio_employee=self.employee)
		se.submit()
		se.cancel()

		row_name = frappe.db.get_value(
			"Employee Request", {"parent": mr.name, "employee": self.employee}, "name"
		)
		self.assertFalse(
			frappe.db.get_value("Employee Request", row_name, "issued_via_stock_entry")
		)

	def test_second_submit_for_already_issued_employee_is_blocked(self):
		# qty=2 on the Material Request against two qty=1 Stock Entries (1+1=2,
		# not >2) keeps ERPNext's own "can't over-issue against a Material
		# Request" guard from firing first -- it would otherwise mask whether
		# lock_issued_employee's own check is what's actually blocking this.
		mr = make_material_request(employee_rows=[{"employee": self.employee}], qty=2)
		first = make_stock_entry_for_material_request(mr, bio_employee=self.employee)
		first.submit()

		second = make_stock_entry_for_material_request(mr, bio_employee=self.employee)
		with self.assertRaises(frappe.ValidationError):
			second.submit()

	def test_stock_entry_without_material_request_is_a_noop(self):
		farm, business_unit = get_test_farm_and_business_unit()
		se = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"purpose": "Material Issue",
				"stock_entry_type": "Material Issue",
				"company": "_Test Company",
				"custom_farm": farm,
				"custom_business_unit": business_unit,
				"bio_employee": self.employee,
				"items": [
					{
						"item_code": "_Test Item",
						"qty": 1,
						"uom": "_Test UOM",
						"stock_uom": "_Test UOM",
						"conversion_factor": 1,
						"s_warehouse": "_Test Warehouse - _TC",
					}
				],
			}
		)
		se.insert(ignore_permissions=True)
		se.submit()  # must not raise


class IntegrationTestStockEntryPPEAssignmentCreation(IntegrationTestCase):
	def setUp(self):
		farm, business_unit = get_test_farm_and_business_unit()
		if not farm or not business_unit:
			self.skipTest("No Farm/Business Unit record on this site to build a valid test document.")
		employees = get_test_employees(count=1)
		if not employees:
			self.skipTest("Need at least 1 Active Employee record on this site.")
		self.employee = employees[0]

	def _receipt_ppe_item(self, item_code):
		# `make_ppe_item` only creates the Item master, not any warehouse
		# stock -- receipt 1 unit first so the issue in `_issue_ppe_item`
		# below doesn't trip ERPNext's own NegativeStockError before our
		# hook ever runs (this site has "Allow Negative Stock" off, and a
		# brand-new PPE item starts with zero stock in
		# "_Test Warehouse - _TC").
		farm, business_unit = get_test_farm_and_business_unit()
		receipt = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"purpose": "Material Receipt",
				"stock_entry_type": "Material Receipt",
				"company": "_Test Company",
				"custom_farm": farm,
				"custom_business_unit": business_unit,
				"items": [
					{
						"item_code": item_code,
						"qty": 1,
						"uom": "_Test UOM",
						"stock_uom": "_Test UOM",
						"conversion_factor": 1,
						"t_warehouse": "_Test Warehouse - _TC",
					}
				],
			}
		)
		receipt.insert(ignore_permissions=True)
		receipt.submit()

	def _issue_ppe_item(self, item_code):
		self._receipt_ppe_item(item_code)

		mr = make_material_request(employee_rows=[{"employee": self.employee}])
		farm, business_unit = get_test_farm_and_business_unit()
		se = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"purpose": "Material Issue",
				"stock_entry_type": "Material Issue",
				"company": "_Test Company",
				"custom_farm": farm,
				"custom_business_unit": business_unit,
				"bio_employee": self.employee,
				"items": [
					{
						"item_code": item_code,
						"qty": 1,
						"uom": "_Test UOM",
						"stock_uom": "_Test UOM",
						"conversion_factor": 1,
						"s_warehouse": "_Test Warehouse - _TC",
					}
				],
			}
		)
		se.insert(ignore_permissions=True)
		se.submit()
		return se

	def test_creates_assignment_for_ppe_item(self):
		item_code = make_ppe_item(lifespan_months=6)
		se = self._issue_ppe_item(item_code)

		assignment_name = frappe.db.get_value(
			"Employee PPE Assignment", {"stock_entry": se.name, "item_code": item_code}, "name"
		)
		self.assertTrue(assignment_name)
		assignment = frappe.get_doc("Employee PPE Assignment", assignment_name)
		self.assertEqual(assignment.employee, self.employee)
		self.assertEqual(assignment.status, "Active")
		self.assertEqual(str(assignment.issue_date), str(se.posting_date))
		self.assertEqual(str(assignment.expiry_date), str(frappe.utils.add_months(se.posting_date, 6)))

	def test_ignores_non_ppe_item(self):
		se = self._issue_ppe_item("_Test Item")
		self.assertFalse(
			frappe.db.get_value("Employee PPE Assignment", {"stock_entry": se.name})
		)

	def test_blocks_duplicate_active_assignment_for_same_employee_and_item(self):
		# Deliberately a different lifespan/item than
		# test_creates_assignment_for_ppe_item's -- IntegrationTestCase only
		# rolls back at class teardown, not between methods, so reusing the
		# same (employee, item_code) pair across test methods would leave a
		# leftover Active assignment from whichever test method happens to
		# run first, tripping this test's own duplicate-block check for the
		# wrong reason in the other test.
		item_code = make_ppe_item(lifespan_months=3)
		self._issue_ppe_item(item_code)

		with self.assertRaises(frappe.ValidationError):
			self._issue_ppe_item(item_code)

	def test_cancel_deletes_created_ppe_assignments(self):
		# Finding 1: Stock Entry on_cancel must fully delete every assignment it
		# created on submit, so the assignment doesn't linger.
		item_code = make_ppe_item(lifespan_months=9)
		se = self._issue_ppe_item(item_code)
		assignment_name = frappe.db.get_value(
			"Employee PPE Assignment", {"stock_entry": se.name, "item_code": item_code}, "name"
		)
		self.assertTrue(assignment_name)

		se.cancel()

		self.assertFalse(frappe.db.exists("Employee PPE Assignment", assignment_name))

	def test_reissue_after_cancel_is_not_blocked(self):
		# Finding 1: because the cancelled entry's assignment is deleted (not just
		# deactivated), re-issuing the same item to the same employee must not
		# trip create_ppe_assignments' duplicate-active guard.
		item_code = make_ppe_item(lifespan_months=12)
		first = self._issue_ppe_item(item_code)
		first.cancel()

		second = self._issue_ppe_item(item_code)  # must not raise

		self.assertTrue(
			frappe.db.get_value(
				"Employee PPE Assignment", {"stock_entry": second.name, "item_code": item_code}
			)
		)

	def test_cancel_clears_inbound_replacement_links_and_deletes(self):
		# Finding 1 (replacement flow): create_ppe_assignments points a prior
		# assignment's replacement_assignment at the newly issued one. Cancelling
		# the issuing Stock Entry must delete the new assignment AND clear that
		# inbound link, instead of aborting the cancel with a LinkExistsError.
		item_code = make_ppe_item(lifespan_months=15)
		se = self._issue_ppe_item(item_code)
		new_name = frappe.db.get_value(
			"Employee PPE Assignment", {"stock_entry": se.name, "item_code": item_code}, "name"
		)
		self.assertTrue(new_name)

		prior = frappe.get_doc(
			{
				"doctype": "Employee PPE Assignment",
				"employee": self.employee,
				"item_code": item_code,
				"quantity": 1,
				"company": "_Test Company",
				"issue_date": "2025-06-01",
				"lifespan_months": 15,
				"status": "Inactive",
				"replacement_assignment": new_name,
			}
		).insert(ignore_permissions=True)

		se.cancel()  # must not raise LinkExistsError

		self.assertFalse(frappe.db.exists("Employee PPE Assignment", new_name))
		self.assertFalse(
			frappe.db.get_value("Employee PPE Assignment", prior.name, "replacement_assignment")
		)

	def test_cancel_deletes_assignment_with_linked_ppe_inspection_item(self):
		# Fix A: a PPE Inspection Item child row referencing this assignment --
		# even from a PPE Inspection that was itself properly cancelled -- used
		# to block the whole Stock Entry cancel with LinkExistsError.
		# Cancelling a PPE Inspection doesn't touch its child rows' own link
		# fields, and delete_doc's link check for a plain "Delete" ignores
		# docstatus entirely, so the cancelled inspection's row still counted
		# as a blocker. Clearing employee_ppe_assignment on those rows first
		# (mirroring the existing replacement_assignment treatment) lets the
		# assignment -- and therefore the Stock Entry cancel -- go through,
		# while the PPE Inspection document itself must survive, untouched as
		# a historical record.
		farm, _business_unit = get_test_farm_and_business_unit()
		item_code = make_ppe_item(lifespan_months=8)
		se = self._issue_ppe_item(item_code)
		assignment_name = frappe.db.get_value(
			"Employee PPE Assignment", {"stock_entry": se.name, "item_code": item_code}, "name"
		)
		self.assertTrue(assignment_name)

		inspection = frappe.get_doc(
			{
				"doctype": "PPE Inspection",
				"employee": self.employee,
				"supervisor": self.employee,
				"farm": farm,
				"inspection_date": "2026-02-01",
				"items_inspected": [
					{
						"employee_ppe_assignment": assignment_name,
						"current_status": "OK",
						"update_assignment": 0,
					}
				],
			}
		)
		inspection.insert(ignore_permissions=True)
		inspection.submit()
		inspection.cancel()  # inspection itself properly cancelled...

		item_row_name = frappe.db.get_value(
			"PPE Inspection Item", {"employee_ppe_assignment": assignment_name}, "name"
		)
		self.assertTrue(item_row_name)  # ...but its child row link is still there

		se.cancel()  # must not raise LinkExistsError

		self.assertFalse(frappe.db.exists("Employee PPE Assignment", assignment_name))
		self.assertFalse(
			frappe.db.get_value("PPE Inspection Item", item_row_name, "employee_ppe_assignment")
		)
		self.assertTrue(frappe.db.exists("PPE Inspection", inspection.name))

	def test_isolates_per_assignment_delete_failures_on_cancel(self):
		# Fix A: if deleting one assignment on a multi-item Stock Entry fails,
		# the others on the same Stock Entry must still be cleaned up, and the
		# failure must not propagate out of on_cancel (the Stock Entry cancel
		# itself must still succeed). Forces a genuine failure for one
		# assignment via a real, unrelated blocking link that this fix
		# deliberately does not clear: an Employee PPE History row for a
		# *different* employee. on_trash's own history cleanup only removes
		# rows matching {ppe_assignment: name, parent: assignment.employee}, so
		# a mismatched parent slips past it and still trips delete_doc's
		# LinkExistsError check.
		if "upande_hr" not in frappe.get_installed_apps():
			self.skipTest("upande_hr not installed on this site.")
		other_employee = next(
			(e for e in get_test_employees(count=10) if e != self.employee), None
		)
		if not other_employee:
			self.skipTest("Need a second Active Employee record on this site.")

		item_blocked = make_ppe_item(lifespan_months=4)
		item_clean = make_ppe_item(lifespan_months=5)
		self._receipt_ppe_item(item_blocked)
		self._receipt_ppe_item(item_clean)

		farm, business_unit = get_test_farm_and_business_unit()
		se = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"purpose": "Material Issue",
				"stock_entry_type": "Material Issue",
				"company": "_Test Company",
				"custom_farm": farm,
				"custom_business_unit": business_unit,
				"bio_employee": self.employee,
				"items": [
					{
						"item_code": item_blocked,
						"qty": 1,
						"uom": "_Test UOM",
						"stock_uom": "_Test UOM",
						"conversion_factor": 1,
						"s_warehouse": "_Test Warehouse - _TC",
					},
					{
						"item_code": item_clean,
						"qty": 1,
						"uom": "_Test UOM",
						"stock_uom": "_Test UOM",
						"conversion_factor": 1,
						"s_warehouse": "_Test Warehouse - _TC",
					},
				],
			}
		)
		se.insert(ignore_permissions=True)
		se.submit()

		assignment_blocked = frappe.db.get_value(
			"Employee PPE Assignment", {"stock_entry": se.name, "item_code": item_blocked}, "name"
		)
		assignment_clean = frappe.db.get_value(
			"Employee PPE Assignment", {"stock_entry": se.name, "item_code": item_clean}, "name"
		)
		self.assertTrue(assignment_blocked)
		self.assertTrue(assignment_clean)

		blocking_row = frappe.get_doc(
			{
				"doctype": "Employee PPE History",
				"parent": other_employee,
				"parenttype": "Employee",
				"parentfield": "custom_ppe_history",
				"ppe_assignment": assignment_blocked,
				"item_code": item_blocked,
				"quantity": 1,
				"status": "Active",
			}
		).insert(ignore_permissions=True)

		se.cancel()  # must not raise, despite assignment_blocked being undeletable

		self.assertTrue(frappe.db.exists("Employee PPE Assignment", assignment_blocked))
		self.assertFalse(frappe.db.exists("Employee PPE Assignment", assignment_clean))

		frappe.db.delete("Employee PPE History", {"name": blocking_row.name})

	def test_throws_if_item_missing_lifespan(self):
		item_code = "_Test PPE Item No Lifespan"
		if not frappe.db.exists("Item", item_code):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": item_code,
					"item_group": "_Test Item Group",
					"stock_uom": "_Test UOM",
					"is_stock_item": 1,
					"custom_is_ppe": 1,
				}
			).insert(ignore_permissions=True)

		with self.assertRaises(frappe.ValidationError):
			self._issue_ppe_item(item_code)


class IntegrationTestStockEntryAccountingDimensionInheritance(IntegrationTestCase):
	def setUp(self):
		farm, business_unit = get_test_farm_and_business_unit()
		if not farm or not business_unit:
			self.skipTest("No Farm/Business Unit record on this site to build a valid test document.")
		employees = get_test_employees(count=1)
		if not employees:
			self.skipTest("Need at least 1 Active Employee record on this site.")
		self.employee = employees[0]

	def test_inherits_cost_center_from_material_request_item(self):
		default_cost_center = frappe.db.get_value("Company", "Karen Roses", "cost_center")
		distinct_cost_center = frappe.get_all(
			"Cost Center",
			filters={"company": "Karen Roses", "is_group": 0, "name": ["!=", default_cost_center]},
			limit=1,
			pluck="name",
		)
		if not distinct_cost_center:
			self.skipTest(
				"Need a second, non-default Cost Center on Karen Roses to prove inheritance (not coincidence)."
			)
		distinct_cost_center = distinct_cost_center[0]

		mr = make_material_request(employee_rows=[{"employee": self.employee}])
		frappe.db.set_value("Material Request Item", mr.items[0].name, "cost_center", distinct_cost_center)

		se = make_stock_entry_for_material_request(mr, bio_employee=self.employee)
		se.reload()

		self.assertEqual(se.items[0].cost_center, distinct_cost_center)
		self.assertNotEqual(se.items[0].cost_center, default_cost_center)

	def test_inherits_farm_and_business_unit_from_material_request_item(self):
		farm, business_unit = get_test_farm_and_business_unit()
		mr = make_material_request(employee_rows=[{"employee": self.employee}])
		frappe.db.set_value("Material Request Item", mr.items[0].name, "farm", farm)
		frappe.db.set_value("Material Request Item", mr.items[0].name, "business_unit", business_unit)

		se = make_stock_entry_for_material_request(mr, bio_employee=self.employee)
		se.reload()

		self.assertEqual(se.items[0].farm, farm)
		self.assertEqual(se.items[0].business_unit, business_unit)

	def test_noop_when_material_request_item_has_no_accounting_dimensions(self):
		# Verified against real behaviour: a Material Request Item does NOT
		# come out of insert() with a blank cost_center -- ERPNext's own
		# controller defaults it (observed: to "_Test Cost Center - _TC" on
		# this site), so make_material_request() alone can't produce the
		# "no cost center" case this test needs. Force it blank directly via
		# db.set_value (bypassing that controller default) to genuinely
		# exercise the no-op path, rather than relying on a state that
		# ERPNext itself never actually leaves the row in.
		mr = make_material_request(employee_rows=[{"employee": self.employee}])
		frappe.db.set_value("Material Request Item", mr.items[0].name, "cost_center", None)
		frappe.db.set_value("Material Request Item", mr.items[0].name, "farm", None)
		frappe.db.set_value("Material Request Item", mr.items[0].name, "business_unit", None)

		se = make_stock_entry_for_material_request(mr, bio_employee=self.employee)
		se.items[0].cost_center = "Should Not Be Overwritten"
		se.items[0].farm = "Should Not Be Overwritten"
		se.items[0].business_unit = "Should Not Be Overwritten"

		inherit_accounting_dimensions_from_material_request(se)

		self.assertEqual(se.items[0].cost_center, "Should Not Be Overwritten")
		self.assertEqual(se.items[0].farm, "Should Not Be Overwritten")
		self.assertEqual(se.items[0].business_unit, "Should Not Be Overwritten")

	def test_noop_when_row_has_no_material_request_item(self):
		farm, business_unit = get_test_farm_and_business_unit()
		se = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"purpose": "Material Issue",
				"stock_entry_type": "Material Issue",
				"company": "_Test Company",
				"custom_farm": farm,
				"custom_business_unit": business_unit,
				"bio_employee": self.employee,
				"items": [
					{
						"item_code": "_Test Item",
						"qty": 1,
						"uom": "_Test UOM",
						"stock_uom": "_Test UOM",
						"conversion_factor": 1,
						"s_warehouse": "_Test Warehouse - _TC",
					}
				],
			}
		)
		se.items[0].cost_center = "Should Not Be Overwritten"
		se.items[0].farm = "Should Not Be Overwritten"
		se.items[0].business_unit = "Should Not Be Overwritten"

		inherit_accounting_dimensions_from_material_request(se)  # must not raise

		self.assertEqual(se.items[0].cost_center, "Should Not Be Overwritten")
		self.assertEqual(se.items[0].farm, "Should Not Be Overwritten")
		self.assertEqual(se.items[0].business_unit, "Should Not Be Overwritten")
