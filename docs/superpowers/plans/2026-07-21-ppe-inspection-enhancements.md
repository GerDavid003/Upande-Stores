# PPE Inspection Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Require photo evidence before submitting a `PPE Inspection` with any
`Worn Out` item, broaden the assignment-picker filter to `Active`+`Expired`, and
auto-populate the inspected-items table when an employee is selected.

**Architecture:** Two small, independent changes to the existing `PPE Inspection`
doctype (from the 2026-07-20 PPE Workflow plan): a `before_submit` guard in its
Python controller, and a rewrite of its client script's `employee` handler plus
`set_query` filter. No schema changes, no new API endpoint.

**Tech Stack:** Frappe/ERPNext, Python controller, vanilla `frappe.ui.form`
client script, `frappe.tests.IntegrationTestCase` (this app's established test
convention).

Full design rationale: `docs/superpowers/specs/2026-07-21-ppe-inspection-enhancements-design.md`.

## Global Constraints

- Site under test: `david.local`. `upande_stores/upande_stores/doctype/ppe_inspection/test_ppe_inspection.py`
  lives inside a `doctype/<name>/` folder, so — per this plan's own established
  finding (see `docs/superpowers/plans/2026-07-20-ppe-workflow.md`'s Task 14/16
  history) — `bench run-tests` will hit a pre-existing, unrelated erpnext/Price-List
  bootstrap crash at test discovery. Use the `bench execute`-based functional
  verification fallback documented in
  `/home/david/frappe/kaitet-bench/apps/upande_stores/.superpowers/sdd/task-4-report.md`
  (reproduce test method bodies directly, real alphabetical class order, no
  inter-method rollback, no leftover scratch files).
- Indentation: tabs, matching every existing file in this app.
- Reuse `upande_stores/upande_stores/tests/test_helpers.py` builders
  (`get_test_employees`) and the existing helper methods already in
  `test_ppe_inspection.py` (`_assignment`, `_submit_inspection`) — extend that
  file, don't duplicate its fixture logic.
- "The attachment" means Frappe's built-in generic per-document file attachment
  (the `File` doctype, `attached_to_doctype`/`attached_to_name`) — not a new
  Attach-type field anywhere.
- The attachment check applies to every `Worn Out` row regardless of that row's
  `update_assignment` checkbox, and does NOT apply to `Lost` rows.

---

## Task 1: Mandatory attachment on Worn Out

**Files:**
- Modify: `apps/upande_stores/upande_stores/upande_stores/doctype/ppe_inspection/ppe_inspection.py`
- Modify: `apps/upande_stores/upande_stores/upande_stores/doctype/ppe_inspection/test_ppe_inspection.py`

**Interfaces:**
- Consumes: `PPE Inspection.items_inspected` (existing), `PPE Inspection Item.current_status`
  (existing, options `OK\nWorn Out\nLost`).
- Produces: `PPEInspection.before_submit(self)` — no other task depends on this;
  it's a pure validation gate.

- [ ] **Step 1: Read the current file first**

Read `apps/upande_stores/upande_stores/upande_stores/doctype/ppe_inspection/ppe_inspection.py`
and `test_ppe_inspection.py` in full before changing anything — you're appending
to both, not replacing them. The test file already has a
`IntegrationTestPPEInspection` class with a `setUp` (sets `self.employee`,
`self.farm`), a `_assignment(status="Active")` helper, and a
`_submit_inspection(assignment, current_status)` helper — reuse both.

- [ ] **Step 2: Write the failing tests**, appended to the existing
  `IntegrationTestPPEInspection` class in `test_ppe_inspection.py`:

```python
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
				"file_name": "worn_out_evidence.jpg",
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
```

- [ ] **Step 3: Run to confirm the first two fail**

Since `bench run-tests` hits the pre-existing bootstrap crash for this
`doctype/`-folder test file (see Global Constraints), use the `bench execute`
fallback: write a temporary throwaway script (not committed) that imports
`IntegrationTestPPEInspection`, instantiates it, and calls
`test_blocks_submit_when_worn_out_without_attachment` and
`test_allows_submit_when_worn_out_with_attachment` directly, run via
`bench --site david.local execute <module>.<function>`. Expected: the first
test's `assertRaises` fails (no exception is currently raised — `before_submit`
doesn't exist yet, so nothing blocks the submit); the second test currently
passes trivially (nothing blocks it either, so it's not a meaningful RED, just
confirm it doesn't error for an unrelated reason). Delete the throwaway script
after use.

- [ ] **Step 4: Add `before_submit` to `ppe_inspection.py`**

Add `from frappe import _` to the imports (check it isn't already there), then
add this method to the `PPEInspection` class, alongside the existing
`on_submit`/`on_cancel`:

```python
	def before_submit(self):
		has_worn_out = any(row.current_status == "Worn Out" for row in self.items_inspected)
		if not has_worn_out:
			return

		attached = frappe.get_all(
			"File",
			filters={"attached_to_doctype": "PPE Inspection", "attached_to_name": self.name},
			limit=1,
		)
		if not attached:
			frappe.throw(
				_("Attach photo evidence before submitting — at least one item is marked Worn Out.")
			)
```

- [ ] **Step 5: Run to confirm all three pass**

Same `bench execute` fallback as Step 3, re-run all three new tests plus the
existing 4 tests already in this class (`test_lost_item_deactivates_assignment`,
`test_worn_out_item_deactivates_assignment`,
`test_ok_item_reactivates_a_previously_inactive_assignment`,
`test_skips_rows_with_update_assignment_unchecked`) to confirm no regressions.
Expected: all 7 pass.

- [ ] **Step 6: Commit**

```bash
cd ~/frappe/kaitet-bench/apps/upande_stores
git add upande_stores/upande_stores/doctype/ppe_inspection/ppe_inspection.py upande_stores/upande_stores/doctype/ppe_inspection/test_ppe_inspection.py
git commit -m "feat: require photo attachment before submitting a Worn Out PPE Inspection"
```

---

## Task 2: Broaden assignment filter + auto-fetch on employee selection

**Files:**
- Modify: `apps/upande_stores/upande_stores/upande_stores/doctype/ppe_inspection/ppe_inspection.js`

**Interfaces:**
- Consumes: `Employee PPE Assignment.status` (existing, options
  `Active\nInactive\nExpired\nReturned`), `Employee PPE Assignment.employee`/`.item_code`/`.item_name`
  (existing).
- Produces: nothing new for later tasks — this is a leaf, own-doctype client
  script change (auto-loaded, no `hooks.py` change needed, same mechanism
  already confirmed correct for this file in the 2026-07-20 plan's Task 17).

- [ ] **Step 1: Read the current file first**

Read `apps/upande_stores/upande_stores/upande_stores/doctype/ppe_inspection/ppe_inspection.js` —
you're replacing its `set_query` filter value and its entire `employee(frm)`
handler body; the `setup(frm)` function wrapper itself and the overall
`frappe.ui.form.on("PPE Inspection", {...})` structure stay.

- [ ] **Step 2: Replace the file's content**

```js
frappe.ui.form.on("PPE Inspection", {
	setup(frm) {
		frm.set_query("employee_ppe_assignment", "items_inspected", (doc) => {
			if (!doc.employee) {
				frappe.msgprint(__("Please select Employee first."));
				return;
			}
			return {
				filters: {
					employee: doc.employee,
					status: ["in", ["Active", "Expired"]],
				},
			};
		});
	},

	employee(frm) {
		frm.clear_table("items_inspected");
		frm.refresh_field("items_inspected");

		if (!frm.doc.employee) {
			return;
		}

		frappe.db
			.get_list("Employee PPE Assignment", {
				filters: { employee: frm.doc.employee, status: ["in", ["Active", "Expired"]] },
				fields: ["name", "item_code", "item_name"],
				limit_page_length: 0,
			})
			.then((rows) => {
				rows.forEach((r) => {
					const row = frm.add_child("items_inspected");
					row.employee_ppe_assignment = r.name;
					row.item_code = r.item_code;
					row.item_name = r.item_name;
				});
				frm.refresh_field("items_inspected");
				if (rows.length) {
					frappe.show_alert({
						message: __("{0} assignment(s) fetched.", [rows.length]),
						indicator: "green",
					});
				}
			});
	},
});
```

Note: this deliberately drops the old "Inspection items cleared because Employee
was changed." `msgprint` — the table now immediately refills with the new
employee's assignments, so a standalone "cleared" message no longer fits the
UX; the new `"{0} assignment(s) fetched."` alert covers the equivalent feedback.

- [ ] **Step 3: Build and manually verify**

```bash
cd ~/frappe/kaitet-bench
bench build --app upande_stores
bench --site david.local clear-cache
```

You likely don't have browser access — confirm the build succeeds with no
errors and the JS is syntactically valid (`node --check <file>` if available),
and note in your report that interactive browser verification wasn't possible.
This file auto-loads via the doctype's own folder (not a `hooks.py` path), the
same mechanism already confirmed correct for this exact file in the
2026-07-20 plan's Task 17 review — no `FormMeta`-style hook-resolution check is
needed here.

- [ ] **Step 4: Commit**

```bash
cd ~/frappe/kaitet-bench/apps/upande_stores
git add upande_stores/upande_stores/doctype/ppe_inspection/ppe_inspection.js
git commit -m "feat: broaden PPE Inspection assignment filter to Active+Expired and auto-fetch on employee selection"
```

---

## Post-plan manual smoke test

Open a PPE Inspection, select an Employee with at least one Active or Expired
assignment, confirm the table auto-fills. Mark one row `Worn Out`, try to
submit without attaching a file — confirm it's blocked with the expected
message. Attach a file, submit — confirm it succeeds. Confirm a row with `OK`
or `Lost` and no attachment still submits fine.
