# Farm/Business Unit Accounting Dimensions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove `upande_stores`'s app-owned `custom_farm`/`custom_business_unit`
from Stock Entry in favor of the newly-configured Farm/Business Unit
Accounting Dimensions, build the propagation chain (Material Request header →
Material Request Item → Stock Entry Detail) that replaces them, and fix the
resulting regression in PPE issuance.

**Architecture:** Three sequential tasks, each depending on the previous:
(1) Material Request → Material Request Item sync (new, additive), (2)
Material Request Item → Stock Entry Detail inheritance (extends an existing
function), (3) remove the old Stock Entry fields and fix the PPE code that
read them — these last two must land together since removal and its fix are
not independently valid states.

**Tech Stack:** Frappe/ERPNext, Python controller/override,
`frappe.tests.IntegrationTestCase` (this app's established test convention).

Full design rationale: `docs/superpowers/specs/2026-07-23-farm-business-unit-accounting-dimensions-design.md`.

## Global Constraints

- Site: `david.local`. The `Farm`/`Business Unit` Accounting Dimensions
  already exist there with fieldnames `farm`/`business_unit` (confirmed via
  `tabAccounting Dimension`) — do not create or modify Accounting Dimension
  records; they're already configured.
- All three test files (`overrides/test_material_request.py`,
  `overrides/test_stock_entry.py`) live in `overrides/`, NOT inside a
  `doctype/<name>/` folder — per this app's established finding, the real
  `bench run-tests` works cleanly here, no `bench execute` fallback needed.
- Indentation: tabs, matching every existing file in this app.
- Reuse `upande_stores/upande_stores/tests/test_helpers.py` builders
  (`get_test_farm_and_business_unit`, `get_test_employees`,
  `make_material_request`, `make_stock_entry_for_material_request`,
  `make_ppe_item`) and the existing `IntegrationTestCase` conventions.
- `Employee.custom_farm`/`.custom_business_unit` (owned by `upande_hr`) are a
  completely separate pair of fields on a different doctype — do not touch
  them, they're out of scope.
- `Material Request.custom_farm`/`.custom_business_unit` (header-level,
  user-facing) are NOT being removed — only Stock Entry's copies are.

---

## Task 1: Material Request header → Material Request Item sync

**Files:**
- Modify: `apps/upande_stores/upande_stores/overrides/material_request.py`
- Modify: `apps/upande_stores/upande_stores/overrides/test_material_request.py`
- Modify: `apps/upande_stores/upande_stores/hooks.py`

**Interfaces:**
- Consumes: `Material Request.custom_farm`/`.custom_business_unit` (existing,
  unchanged), `Material Request Item.farm`/`.business_unit` (new fields,
  auto-added by the Accounting Dimension configuration — already exist on
  the site, no schema change needed here).
- Produces: `upande_stores.overrides.material_request.sync_accounting_dimensions_to_items(doc, method=None)`.
  Task 3's end-to-end test relies on this having already run by the time a
  Material Request is inserted.

- [ ] **Step 1: Read the current files first**

Read `overrides/material_request.py`, `overrides/test_material_request.py`,
and the `doc_events["Material Request"]` block in `hooks.py` in full before
changing anything. `material_request.py` currently has
`validate_no_duplicate_employees` and `validate_employee_data_required_for_material_issue`
and `unlink_ppe_replacement` — you're appending a new function, not touching
those. `hooks.py`'s `doc_events["Material Request"]["validate"]` is currently
a list of the first two function paths — you're appending a third entry.

- [ ] **Step 2: Write the failing test**, appended to
  `test_material_request.py` as a new class (reuse the file's existing
  imports — `get_test_farm_and_business_unit`, `get_test_employees`,
  `make_material_request` — already imported at the top):

```python
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
		mr = make_material_request(employee_rows=[{"employee": self.employee}])
		self.assertTrue(mr.custom_farm)
		self.assertTrue(mr.custom_business_unit)
		for row in mr.items:
			self.assertEqual(row.farm, mr.custom_farm)
			self.assertEqual(row.business_unit, mr.custom_business_unit)
```

- [ ] **Step 3: Run to confirm it fails**

```bash
cd ~/frappe/kaitet-bench
bench --site david.local run-tests --app upande_stores --module upande_stores.overrides.test_material_request
```
Expected: FAIL — `row.farm`/`row.business_unit` are `None`, nothing sets them
yet.

- [ ] **Step 4: Add the function to `material_request.py`**, appended after
  the existing functions:

```python
def sync_accounting_dimensions_to_items(doc, method=None):
	"""Material Request validate: custom_farm/custom_business_unit are
	header-level, user-facing pick fields, but the Farm/Business Unit
	Accounting Dimensions only exist at the Material Request Item level
	(Material Request itself isn't a reference doctype for them) -- so the
	header value has to be pushed down onto every item row explicitly."""
	for row in doc.items:
		if doc.custom_farm:
			row.farm = doc.custom_farm
		if doc.custom_business_unit:
			row.business_unit = doc.custom_business_unit
```

- [ ] **Step 5: Wire it into `hooks.py`**

Find `doc_events["Material Request"]["validate"]` (currently a 2-item list)
and append the new function path as a third entry, without disturbing the
existing two or the `on_cancel`/`on_trash` entries in the same dict:

```python
	"Material Request": {
		"validate": [
			"upande_stores.overrides.material_request.validate_no_duplicate_employees",
			"upande_stores.overrides.material_request.validate_employee_data_required_for_material_issue",
			"upande_stores.overrides.material_request.sync_accounting_dimensions_to_items",
		],
		"on_cancel": "upande_stores.overrides.material_request.unlink_ppe_replacement",
		"on_trash": "upande_stores.overrides.material_request.unlink_ppe_replacement",
	},
```

(Adjust to match whatever the exact current list/order actually is if it
differs from this — the important part is appending the third entry without
removing or reordering the existing ones.)

- [ ] **Step 6: Run to confirm it passes, no regressions**

```bash
bench --site david.local run-tests --app upande_stores --module upande_stores.overrides.test_material_request
```
Expected: all tests in the file pass — the new one plus every pre-existing
class (`IntegrationTestMaterialRequestEmployeeValidation`,
`IntegrationTestMaterialRequestEmployeeMandatory`,
`IntegrationTestMaterialRequestPPEUnlink`).

- [ ] **Step 7: Commit**

```bash
cd ~/frappe/kaitet-bench/apps/upande_stores
git add upande_stores/overrides/material_request.py upande_stores/overrides/test_material_request.py upande_stores/hooks.py
git commit -m "feat: sync Material Request's farm/business unit onto each item row"
```

---

## Task 2: Material Request Item → Stock Entry Detail inheritance

**Files:**
- Modify: `apps/upande_stores/upande_stores/overrides/stock_entry.py`
- Modify: `apps/upande_stores/upande_stores/overrides/test_stock_entry.py`
- Modify: `apps/upande_stores/upande_stores/hooks.py`

**Interfaces:**
- Consumes: `Material Request Item.cost_center`/`.farm`/`.business_unit`
  (existing standard/Accounting-Dimension fields), `Stock Entry Detail.cost_center`/`.farm`/`.business_unit`
  (same).
- Produces: `upande_stores.overrides.stock_entry.inherit_accounting_dimensions_from_material_request(doc, method=None)` —
  **renames** the existing `inherit_cost_center_from_material_request`
  (added in an earlier plan). Task 3 calls this same function name.

- [ ] **Step 1: Read the current files first**

Read `overrides/stock_entry.py` and `overrides/test_stock_entry.py` in full.
Find the existing `inherit_cost_center_from_material_request` function and
the `IntegrationTestStockEntryCostCenterInheritance` test class (with 3
methods: one proving cost-center inheritance, one proving a no-op when the
Material Request Item has no cost center, one proving a no-op when the row
has no `material_request_item` at all) — you are renaming and extending both,
not leaving the old ones in place alongside new duplicates.

- [ ] **Step 2: Write the failing test**

Replace the `IntegrationTestStockEntryCostCenterInheritance` class entirely
with this renamed, extended version (same `setUp`, existing cost-center test
kept verbatim, two new tests added, the no-op tests extended to also cover
`farm`/`business_unit`):

```python
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
		default_cost_center = frappe.db.get_value("Company", "_Test Company", "cost_center")
		distinct_cost_center = frappe.get_all(
			"Cost Center",
			filters={"company": "_Test Company", "is_group": 0, "name": ["!=", default_cost_center]},
			limit=1,
			pluck="name",
		)
		if not distinct_cost_center:
			self.skipTest(
				"Need a second, non-default Cost Center on _Test Company to prove inheritance (not coincidence)."
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
```

Note `test_noop_when_row_has_no_material_request_item` still sets
`custom_farm`/`custom_business_unit` on the inline Stock Entry dict — those
fields still exist on Stock Entry at this point in the plan (Task 3 removes
them later); leave them as-is here, Task 3 will revisit this exact test.

Also update the import at the top of the file from
`from upande_stores.overrides.stock_entry import inherit_cost_center_from_material_request`
to `inherit_accounting_dimensions_from_material_request`.

- [ ] **Step 3: Run to confirm it fails**

```bash
bench --site david.local run-tests --app upande_stores --module upande_stores.overrides.test_stock_entry
```
Expected: FAIL — `ImportError: cannot import name 'inherit_accounting_dimensions_from_material_request'`.

- [ ] **Step 4: Rename and extend the function in `stock_entry.py`**

Replace the existing `inherit_cost_center_from_material_request` function
with:

```python
def inherit_accounting_dimensions_from_material_request(doc, method=None):
	"""Stock Entry validate: a row created from a Material Request Item
	should carry that item's cost center, farm, and business unit -- not
	whatever Stock Entry itself defaulted to. Runs on every save, not just
	insert, so it self-heals if something resets a row's value afterward."""
	for row in doc.items:
		if not row.material_request_item:
			continue
		mr_item = frappe.db.get_value(
			"Material Request Item",
			row.material_request_item,
			["cost_center", "farm", "business_unit"],
			as_dict=True,
		)
		if not mr_item:
			continue
		if mr_item.cost_center:
			row.cost_center = mr_item.cost_center
		if mr_item.farm:
			row.farm = mr_item.farm
		if mr_item.business_unit:
			row.business_unit = mr_item.business_unit
```

- [ ] **Step 5: Update the `hooks.py` reference**

Find `doc_events["Stock Entry"]["validate"]` (currently
`"upande_stores.overrides.stock_entry.inherit_cost_center_from_material_request"`)
and update it to
`"upande_stores.overrides.stock_entry.inherit_accounting_dimensions_from_material_request"`.
Do not touch `on_submit`/`on_cancel` in the same dict.

- [ ] **Step 6: Run to confirm it passes, no regressions**

```bash
bench --site david.local run-tests --app upande_stores --module upande_stores.overrides.test_stock_entry
```
Expected: all tests in the file pass, including every pre-existing class
(`IntegrationTestStockEntryEmployeeLock`,
`IntegrationTestStockEntryPPEAssignmentCreation`).

- [ ] **Step 7: Commit**

```bash
cd ~/frappe/kaitet-bench/apps/upande_stores
git add upande_stores/overrides/stock_entry.py upande_stores/overrides/test_stock_entry.py upande_stores/hooks.py
git commit -m "feat: extend cost-center inheritance to farm and business unit"
```

---

## Task 3: Remove Stock Entry's own fields, fix the PPE regression

**Files:**
- Modify: `apps/upande_stores/upande_stores/upande_stores/custom/stock_entry.json`
- Modify: `apps/upande_stores/upande_stores/overrides/stock_entry.py`
- Modify: `apps/upande_stores/upande_stores/overrides/test_stock_entry.py`
- Modify: `apps/upande_stores/upande_stores/tests/test_helpers.py`

**Interfaces:**
- Consumes: everything Tasks 1 and 2 produced.
- Produces: nothing further downstream — this is the last task in the plan.

This task removes fields and fixes the code that depended on them in the same
commit — a state with one but not the other would be broken, so do all of
Steps 1-6 before running the final verification.

- [ ] **Step 1: Read the current files first**

Read `custom/stock_entry.json`, `overrides/stock_entry.py` (specifically
`create_ppe_assignments`), `overrides/test_stock_entry.py`, and
`tests/test_helpers.py`'s `make_stock_entry_for_material_request` in full.

- [ ] **Step 2: Fix `create_ppe_assignments`**

In `overrides/stock_entry.py`, find these two lines inside
`create_ppe_assignments` (they read Stock Entry's *header*-level custom
fields, which are about to be removed):

```python
				"farm": doc.get("custom_farm"),
				"business_unit": doc.get("custom_business_unit"),
```

Change them to read the *row*-level Accounting Dimension fields instead
(`create_ppe_assignments` already loops `for row in doc.items:` — this is a
like-for-like swap of the source, not a new loop):

```python
				"farm": row.get("farm"),
				"business_unit": row.get("business_unit"),
```

- [ ] **Step 3: Remove `custom_farm`/`custom_business_unit` from every Stock
  Entry construction in the test files**

In `overrides/test_stock_entry.py`, search the file for `custom_farm` and
`custom_business_unit` — every occurrence is inside a Stock Entry document
dict (this file doesn't build Material Requests inline, only via the
`make_material_request` helper, which is untouched — its `custom_farm`/
`custom_business_unit` are Material Request header fields and stay). Remove
both keys from every Stock Entry dict that has them, including the one in
`test_noop_when_row_has_no_material_request_item` from Task 2.

In `tests/test_helpers.py`, find `make_stock_entry_for_material_request` and
remove its `"custom_farm": farm,` and `"custom_business_unit": business_unit,`
lines from the Stock Entry dict it builds (the function's `farm`/
`business_unit` local variables — sourced from `get_test_farm_and_business_unit()`
— may become unused there; if so, remove the now-pointless call entirely from
this function, but check first whether the function's return value or these
locals are used for anything else in the same function before deleting).

- [ ] **Step 4: Run the existing test suites to confirm the code fix alone
  works (fields still present on Stock Entry at this point)**

```bash
cd ~/frappe/kaitet-bench
bench --site david.local run-tests --app upande_stores --module upande_stores.overrides.test_stock_entry
```
Expected: all tests still pass — removing the now-unused dict keys from test
fixtures doesn't change behavior yet, since the fields still exist on the
doctype (just unset in these particular test documents, which is fine, they
were never mandatory).

- [ ] **Step 5: Remove the Custom Field definitions**

In `custom/stock_entry.json`, remove the two entries for `custom_farm` and
`custom_business_unit` from the `custom_fields` array. Also check the file's
`property_setters` array for any entry with `field_name` equal to either —
remove those too if present.

- [ ] **Step 6: Delete the live Custom Field records and migrate**

```bash
cd ~/frappe/kaitet-bench
bench --site david.local console
```
```python
import frappe
for name in ["Stock Entry-custom_farm", "Stock Entry-custom_business_unit"]:
	if frappe.db.exists("Custom Field", name):
		frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
frappe.db.commit()
exit()
```
```bash
bench --site david.local migrate
bench --site david.local clear-cache
```

- [ ] **Step 7: Write the end-to-end integration test**, appended to
  `overrides/test_stock_entry.py` as a new class (reuse `make_ppe_item`,
  already imported in this file from an earlier plan):

```python
class IntegrationTestStockEntryPPEAssignmentAccountingDimensions(IntegrationTestCase):
	def setUp(self):
		farm, business_unit = get_test_farm_and_business_unit()
		if not farm or not business_unit:
			self.skipTest("No Farm/Business Unit record on this site to build a valid test document.")
		employees = get_test_employees(count=1)
		if not employees:
			self.skipTest("Need at least 1 Active Employee record on this site.")
		self.employee = employees[0]

	def test_ppe_assignment_gets_farm_and_business_unit_via_the_full_inheritance_chain(self):
		item_code = make_ppe_item(lifespan_months=6)
		mr = make_material_request(employee_rows=[{"employee": self.employee}])
		expected_farm = mr.custom_farm
		expected_business_unit = mr.custom_business_unit
		self.assertTrue(expected_farm)
		self.assertTrue(expected_business_unit)

		# Task 1's Material Request validate hook should already have synced
		# these onto the item row on insert.
		mr.reload()
		self.assertEqual(mr.items[0].farm, expected_farm)
		self.assertEqual(mr.items[0].business_unit, expected_business_unit)

		se = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"purpose": "Material Issue",
				"stock_entry_type": "Material Issue",
				"company": "_Test Company",
				"bio_employee": self.employee,
				"items": [
					{
						"item_code": item_code,
						"qty": 1,
						"uom": "_Test UOM",
						"stock_uom": "_Test UOM",
						"conversion_factor": 1,
						"s_warehouse": "_Test Warehouse - _TC",
						"material_request": mr.name,
						"material_request_item": mr.items[0].name,
					}
				],
			}
		)
		se.insert(ignore_permissions=True)
		se.submit()

		# Task 2's Stock Entry validate hook should have pulled farm/business_unit
		# from the Material Request Item onto this row before submit.
		se.reload()
		self.assertEqual(se.items[0].farm, expected_farm)
		self.assertEqual(se.items[0].business_unit, expected_business_unit)

		# Task 3's fix: create_ppe_assignments must read the row-level values,
		# not the now-removed Stock Entry header fields.
		assignment_name = frappe.db.get_value(
			"Employee PPE Assignment", {"stock_entry": se.name, "item_code": item_code}, "name"
		)
		self.assertTrue(assignment_name)
		assignment = frappe.get_doc("Employee PPE Assignment", assignment_name)
		self.assertEqual(assignment.farm, expected_farm)
		self.assertEqual(assignment.business_unit, expected_business_unit)
```

- [ ] **Step 8: Run the full suite to confirm everything passes post-removal**

```bash
bench --site david.local run-tests --app upande_stores --module upande_stores.overrides.test_stock_entry
bench --site david.local run-tests --app upande_stores --module upande_stores.overrides.test_material_request
```
Expected: all tests pass in both files, including the new end-to-end test.

- [ ] **Step 9: Commit**

```bash
cd ~/frappe/kaitet-bench/apps/upande_stores
git add upande_stores/upande_stores/custom/stock_entry.json upande_stores/overrides/stock_entry.py upande_stores/overrides/test_stock_entry.py upande_stores/upande_stores/tests/test_helpers.py
git commit -m "feat: remove Stock Entry's app-owned farm/business unit in favor of Accounting Dimensions"
```

---

## Post-plan manual smoke test

Create a Material Request, pick a Farm and Business Unit at the header level,
submit, and confirm every item row shows the same Farm/Business Unit in its
Accounting Dimensions section. Create a Stock Entry from it and confirm those
values carried over to the Stock Entry's item rows (and that Stock Entry no
longer has its own separate Farm/Business Unit fields at all). Submit it as a
PPE issuance and confirm the resulting Employee PPE Assignment shows the
correct Farm/Business Unit.
