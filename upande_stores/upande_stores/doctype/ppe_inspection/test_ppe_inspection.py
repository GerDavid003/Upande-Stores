import frappe
from frappe.tests import IntegrationTestCase

from upande_stores.tests.test_helpers import get_test_employees, make_ppe_item


class IntegrationTestPPEInspection(IntegrationTestCase):
	def setUp(self):
		employees = get_test_employees(count=1)
		if not employees:
			self.skipTest("Need at least 1 Active Employee record on this site.")
		self.employee = employees[0]
		farm = frappe.db.get_value("Farm", {}, "name")
		if not farm:
			self.skipTest("No Farm record available on this site to run this test.")
		self.farm = farm

	def _assignment(self, status="Active"):
		return frappe.get_doc(
			{
				"doctype": "Employee PPE Assignment",
				"employee": self.employee,
				"item_code": make_ppe_item(),
				"quantity": 1,
				"company": "_Test Company",
				"issue_date": "2026-01-01",
				"lifespan_months": 6,
				"status": status,
			}
		).insert(ignore_permissions=True)

	def _submit_inspection(self, assignment, current_status):
		inspection = frappe.get_doc(
			{
				"doctype": "PPE Inspection",
				"employee": self.employee,
				"supervisor": self.employee,
				"farm": self.farm,
				"inspection_date": "2026-02-01",
				"items_inspected": [
					{
						"employee_ppe_assignment": assignment.name,
						"current_status": current_status,
						"update_assignment": 1,
					}
				],
			}
		)
		inspection.insert(ignore_permissions=True)
		if current_status == "Worn Out":
			# before_submit now blocks a Worn Out submission without an attached
			# File (see test_blocks_submit_when_worn_out_without_attachment below).
			# Existing callers of this helper exercising "Worn Out" need a File
			# attached first so their own (unrelated) assertions can still run.
			frappe.get_doc(
				{
					"doctype": "File",
					"file_name": "worn_out_evidence.txt",
					"attached_to_doctype": "PPE Inspection",
					"attached_to_name": inspection.name,
					"content": "fake-image-bytes",
				}
			).insert(ignore_permissions=True)
		inspection.submit()
		return inspection

	def test_lost_item_deactivates_assignment(self):
		assignment = self._assignment()
		inspection = self._submit_inspection(assignment, "Lost")

		assignment.reload()
		self.assertEqual(assignment.status, "Inactive")
		self.assertEqual(assignment.last_inspection_status, "Lost")
		self.assertEqual(assignment.last_inspection, inspection.name)

	def test_worn_out_item_deactivates_assignment(self):
		assignment = self._assignment()
		self._submit_inspection(assignment, "Worn Out")

		assignment.reload()
		self.assertEqual(assignment.status, "Inactive")

	def test_ok_item_reactivates_a_previously_inactive_assignment(self):
		assignment = self._assignment(status="Inactive")
		self._submit_inspection(assignment, "OK")

		assignment.reload()
		self.assertEqual(assignment.status, "Active")

	def test_submit_captures_previous_status_on_the_row(self):
		# Finding 3: on_submit stamps the assignment's pre-inspection status onto
		# the inspection's own child row.
		assignment = self._assignment(status="Active")
		inspection = self._submit_inspection(assignment, "Lost")

		inspection.reload()
		self.assertEqual(inspection.items_inspected[0].previous_status, "Active")

	def test_cancel_reverts_status_to_pre_inspection_value(self):
		# Finding 3: an Active assignment marked Lost goes Inactive on submit;
		# cancelling the inspection must restore it to Active (the pre-inspection
		# value), not a hardcoded default.
		assignment = self._assignment(status="Active")
		inspection = self._submit_inspection(assignment, "Lost")

		assignment.reload()
		self.assertEqual(assignment.status, "Inactive")

		inspection.cancel()

		assignment.reload()
		self.assertEqual(assignment.status, "Active")

	def test_cancel_reverts_to_inactive_when_it_was_inactive(self):
		# Finding 3: the revert is to whatever the status actually was before --
		# an Inactive assignment reactivated by an "OK" inspection must go back
		# to Inactive on cancel, proving the revert isn't hardcoded to "Active".
		assignment = self._assignment(status="Inactive")
		inspection = self._submit_inspection(assignment, "OK")

		assignment.reload()
		self.assertEqual(assignment.status, "Active")

		inspection.cancel()

		assignment.reload()
		self.assertEqual(assignment.status, "Inactive")

	def test_cancel_leaves_last_inspection_fields_stamped(self):
		# Finding 3 scope boundary: only `status` reverts on cancel -- the
		# last_inspection* fields stay as whatever the cancelled inspection
		# stamped.
		assignment = self._assignment(status="Active")
		inspection = self._submit_inspection(assignment, "Lost")
		inspection.cancel()

		assignment.reload()
		self.assertEqual(assignment.status, "Active")
		self.assertEqual(assignment.last_inspection, inspection.name)
		self.assertEqual(assignment.last_inspection_status, "Lost")

	def test_skips_rows_with_update_assignment_unchecked(self):
		assignment = self._assignment()
		inspection = frappe.get_doc(
			{
				"doctype": "PPE Inspection",
				"employee": self.employee,
				"supervisor": self.employee,
				"farm": self.farm,
				"inspection_date": "2026-02-01",
				"items_inspected": [
					{
						"employee_ppe_assignment": assignment.name,
						"current_status": "Lost",
						"update_assignment": 0,
					}
				],
			}
		)
		inspection.insert(ignore_permissions=True)
		inspection.submit()

		assignment.reload()
		self.assertEqual(assignment.status, "Active")

	def test_blocks_submit_when_worn_out_without_attachment(self):
		assignment = self._assignment()
		inspection = frappe.get_doc(
			{
				"doctype": "PPE Inspection",
				"employee": self.employee,
				"supervisor": self.employee,
				"farm": self.farm,
				"inspection_date": "2026-02-01",
				"items_inspected": [
					{
						"employee_ppe_assignment": assignment.name,
						"current_status": "Worn Out",
						"update_assignment": 1,
					}
				],
			}
		)
		inspection.insert(ignore_permissions=True)

		with self.assertRaises(frappe.ValidationError):
			inspection.submit()

	def test_allows_submit_when_worn_out_with_attachment(self):
		assignment = self._assignment()
		inspection = frappe.get_doc(
			{
				"doctype": "PPE Inspection",
				"employee": self.employee,
				"supervisor": self.employee,
				"farm": self.farm,
				"inspection_date": "2026-02-01",
				"items_inspected": [
					{
						"employee_ppe_assignment": assignment.name,
						"current_status": "Worn Out",
						"update_assignment": 1,
					}
				],
			}
		)
		inspection.insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "File",
				# Not `.jpg`: this site has `strip_exif_metadata_from_uploaded_images`
				# enabled, so a `.jpg`/`.png` filename routes File.save_file() through
				# PIL's strip_exif_data(), which requires real image bytes and raises
				# `TypeError: a bytes-like object is required, not 'str'` on this plain
				# placeholder string. before_submit only checks for a File row's
				# existence via attached_to_doctype/attached_to_name, not its content
				# type, so a non-image extension exercises the same code path safely.
				"file_name": "worn_out_evidence.txt",
				"attached_to_doctype": "PPE Inspection",
				"attached_to_name": inspection.name,
				"content": "fake-image-bytes",
			}
		).insert(ignore_permissions=True)

		inspection.submit()  # must not raise

		self.assertEqual(inspection.docstatus, 1)

	def test_ok_item_does_not_require_attachment(self):
		assignment = self._assignment()
		inspection = frappe.get_doc(
			{
				"doctype": "PPE Inspection",
				"employee": self.employee,
				"supervisor": self.employee,
				"farm": self.farm,
				"inspection_date": "2026-02-01",
				"items_inspected": [
					{
						"employee_ppe_assignment": assignment.name,
						"current_status": "OK",
						"update_assignment": 1,
					}
				],
			}
		)
		inspection.insert(ignore_permissions=True)

		inspection.submit()  # must not raise

	def test_ok_item_does_not_reactivate_an_expired_assignment(self):
		# Finding 1: an OK verdict must not flip an Expired assignment back to
		# Active -- the daily auto-expiry job would just silently undo that
		# within a day anyway. last_inspection* fields still get stamped.
		assignment = self._assignment(status="Expired")
		inspection = self._submit_inspection(assignment, "OK")

		assignment.reload()
		self.assertEqual(assignment.status, "Expired")
		self.assertEqual(assignment.last_inspection_status, "OK")
		self.assertEqual(assignment.last_inspection, inspection.name)

	def test_duplicate_assignment_rows_are_blocked_on_validate(self):
		# Finding 3: the same employee_ppe_assignment appearing twice in
		# items_inspected must be rejected at save time, before submit is
		# even possible -- otherwise on_submit would process it twice and
		# corrupt the previous_status capture used by on_cancel.
		assignment = self._assignment()
		inspection = frappe.get_doc(
			{
				"doctype": "PPE Inspection",
				"employee": self.employee,
				"supervisor": self.employee,
				"farm": self.farm,
				"inspection_date": "2026-02-01",
				"items_inspected": [
					{
						"employee_ppe_assignment": assignment.name,
						"current_status": "OK",
						"update_assignment": 1,
					},
					{
						"employee_ppe_assignment": assignment.name,
						"current_status": "OK",
						"update_assignment": 1,
					},
				],
			}
		)

		with self.assertRaises(frappe.ValidationError):
			inspection.insert(ignore_permissions=True)
