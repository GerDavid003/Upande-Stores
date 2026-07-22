# Material Request Employee/Cost-Center Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Require at least one properly-populated employee row on a Material
Issue Material Request, and have Stock Entry inherit its cost center from the
linked Material Request Item instead of defaulting to the Company's default.

**Architecture:** Two small, independent changes. Task 1 is two schema-level
edits (a Custom Field property, a child doctype field property) with no new
code. Task 2 adds one function to the existing
`upande_stores/overrides/stock_entry.py`, hooked on Stock Entry's `validate`.

**Tech Stack:** Frappe/ERPNext, Python controller/override, Custom Field JSON,
`frappe.tests.IntegrationTestCase` (this app's established test convention).

Full design rationale: `docs/superpowers/specs/2026-07-21-material-request-employee-cost-center-design.md`.

## Global Constraints

- Both tasks' test files (`upande_stores/overrides/test_material_request.py`,
  `upande_stores/overrides/test_stock_entry.py`) live in `overrides/`, NOT
  inside a `doctype/<name>/` folder — per this app's own established finding
  (see `docs/superpowers/plans/2026-07-20-ppe-workflow.md`'s Task 14 history),
  the real `bench run-tests` works cleanly for files in this location; there is
  no need for the `bench execute` fallback here.
- Indentation: tabs, matching every existing file in this app.
- Reuse `upande_stores/upande_stores/tests/test_helpers.py` builders
  (`get_test_farm_and_business_unit`, `get_test_employees`,
  `make_material_request`, `make_stock_entry_for_material_request`) and the
  existing `IntegrationTestCase` conventions already in both test files.
- Scope: only `material_request_type == "Material Issue"` is affected by
  Task 1. Task 2 only touches Stock Entry item rows with `material_request_item`
  set, and only overrides `cost_center` when the source Material Request Item
  actually has one — it must never blank out an existing value.

---

## Task 1: Mandatory employee on Material Issue

**Files:**
- Modify: `apps/upande_stores/upande_stores/upande_stores/custom/material_request.json`
- Modify: `apps/upande_stores/upande_stores/upande_stores/doctype/employee_request/employee_request.json`
- Modify: `apps/upande_stores/upande_stores/overrides/test_material_request.py`

**Interfaces:**
- Consumes: `Material Request.custom_employee_data` (existing Table field,
  options `Employee Request`), `Employee Request.employee` (existing Link
  field).
- Produces: nothing new for later tasks — this is a pure validation
  tightening, independent of Task 2.

- [ ] **Step 1: Read the current files first**

Read `apps/upande_stores/upande_stores/upande_stores/custom/material_request.json`,
`apps/upande_stores/upande_stores/upande_stores/doctype/employee_request/employee_request.json`,
and `apps/upande_stores/upande_stores/overrides/test_material_request.py` in
full before changing anything — you're editing existing content, not
replacing whole files.

- [ ] **Step 2: Write the failing tests**, appended to
  `test_material_request.py` as a new class (the existing
  `IntegrationTestMaterialRequestEmployeeValidation` class covers a different
  concern — duplicate employees — leave it untouched):

```python
class IntegrationTestMaterialRequestEmployeeMandatory(IntegrationTestCase):
	def setUp(self):
		farm, business_unit = get_test_farm_and_business_unit()
		if not farm or not business_unit:
			self.skipTest("No Farm/Business Unit record on this site to build a valid test Material Request.")
		employees = get_test_employees(count=1)
		if not employees:
			self.skipTest("Need at least 1 Active Employee record on this site.")
		self.employee = employees[0]

	def test_material_issue_requires_at_least_one_employee_row(self):
		with self.assertRaises(frappe.ValidationError):
			make_material_request(employee_rows=[])

	def test_material_issue_employee_row_requires_employee_field(self):
		with self.assertRaises(frappe.ValidationError):
			make_material_request(employee_rows=[{}])

	def test_material_issue_with_a_populated_employee_row_succeeds(self):
		mr = make_material_request(employee_rows=[{"employee": self.employee}])
		self.assertEqual(len(mr.custom_employee_data), 1)

	def test_material_transfer_does_not_require_employees(self):
		farm, business_unit = get_test_farm_and_business_unit()
		mr = frappe.get_doc(
			{
				"doctype": "Material Request",
				"material_request_type": "Material Transfer",
				"transaction_date": frappe.utils.today(),
				"company": "_Test Company",
				"custom_farm": farm,
				"custom_business_unit": business_unit,
				"items": [
					{
						"item_code": "_Test Item",
						"qty": 1,
						"uom": "_Test UOM",
						"stock_uom": "_Test UOM",
						"conversion_factor": 1,
						"schedule_date": frappe.utils.today(),
						"warehouse": "_Test Warehouse - _TC",
					}
				],
			}
		)
		mr.insert(ignore_permissions=True)  # must not raise
```

- [ ] **Step 3: Run to confirm the first two fail**

```bash
cd ~/frappe/kaitet-bench
bench --site david.local run-tests --app upande_stores --module upande_stores.overrides.test_material_request
```
Expected: `test_material_issue_requires_at_least_one_employee_row` and
`test_material_issue_employee_row_requires_employee_field` FAIL (no error is
currently raised, since neither the Custom Field nor the child field is
mandatory yet). The other two tests currently pass trivially — that's fine,
not a meaningful RED, just confirm they don't error for an unrelated reason.

- [ ] **Step 4: Make `custom_employee_data` conditionally mandatory**

Open `custom/material_request.json` and find the `custom_employee_data` entry
in the `custom_fields` array (it currently has
`"depends_on": "eval:doc.material_request_type == \"Material Issue\""` and
`"mandatory_depends_on": null`). Change `mandatory_depends_on` to the same
expression:

```json
"mandatory_depends_on": "eval:doc.material_request_type == \"Material Issue\"",
```

Do not touch any other field in the file.

- [ ] **Step 5: Make `employee` required on `Employee Request`**

Open `employee_request.json` and find the `employee` field in the `fields`
array. Change `"reqd": 0` (or add `"reqd": 1` if the key is absent) to:

```json
"reqd": 1,
```

Do not touch any other field.

- [ ] **Step 6: Migrate and run all 4 new tests plus the existing class**

```bash
cd ~/frappe/kaitet-bench
bench --site david.local migrate
bench --site david.local run-tests --app upande_stores --module upande_stores.overrides.test_material_request
```
Expected: all tests in the file pass — the 4 new ones plus the pre-existing
`IntegrationTestMaterialRequestEmployeeValidation` class (2 tests), no
regressions.

- [ ] **Step 7: Commit**

```bash
cd ~/frappe/kaitet-bench/apps/upande_stores
git add upande_stores/upande_stores/custom/material_request.json upande_stores/upande_stores/doctype/employee_request/employee_request.json upande_stores/overrides/test_material_request.py
git commit -m "feat: require at least one employee on Material Issue requests"
```

---

## Task 2: Stock Entry inherits cost center from Material Request Item

**Files:**
- Modify: `apps/upande_stores/upande_stores/overrides/stock_entry.py`
- Modify: `apps/upande_stores/upande_stores/overrides/test_stock_entry.py`
- Modify: `apps/upande_stores/upande_stores/hooks.py`

**Interfaces:**
- Consumes: `Material Request Item.cost_center` (standard ERPNext field,
  already exists — no schema change), `Stock Entry Detail.material_request_item`/`.cost_center`
  (standard ERPNext fields).
- Produces: `upande_stores.overrides.stock_entry.inherit_cost_center_from_material_request(doc, method=None)` —
  no other task depends on this.

- [ ] **Step 1: Read the current files first**

Read `apps/upande_stores/upande_stores/overrides/stock_entry.py` and
`test_stock_entry.py` in full — you're appending to both. Note the existing
`_resolve_material_request(doc)` helper is NOT what you need here (it finds
the whole Material Request a Stock Entry was created against; this task
works per-item, off each row's own `material_request_item` link).

- [ ] **Step 2: Write the failing tests**, appended to the existing
  `IntegrationTestStockEntryEmployeeLock` class's file (as a new class,
  reusing the same imports already at the top of `test_stock_entry.py`:
  `get_test_employees`, `get_test_farm_and_business_unit`,
  `make_material_request`, `make_stock_entry_for_material_request`):

```python
from upande_stores.overrides.stock_entry import inherit_cost_center_from_material_request


class IntegrationTestStockEntryCostCenterInheritance(IntegrationTestCase):
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

	def test_noop_when_material_request_item_has_no_cost_center(self):
		mr = make_material_request(employee_rows=[{"employee": self.employee}])
		se = make_stock_entry_for_material_request(mr, bio_employee=self.employee)
		se.items[0].cost_center = "Should Not Be Overwritten"

		inherit_cost_center_from_material_request(se)

		self.assertEqual(se.items[0].cost_center, "Should Not Be Overwritten")

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

		inherit_cost_center_from_material_request(se)  # must not raise

		self.assertEqual(se.items[0].cost_center, "Should Not Be Overwritten")
```

- [ ] **Step 3: Run to confirm it fails**

```bash
cd ~/frappe/kaitet-bench
bench --site david.local run-tests --app upande_stores --module upande_stores.overrides.test_stock_entry
```
Expected: FAIL — `ImportError: cannot import name 'inherit_cost_center_from_material_request'`.

- [ ] **Step 4: Add the function to `stock_entry.py`**, appended after the
  existing `create_ppe_assignments` function:

```python
def inherit_cost_center_from_material_request(doc, method=None):
	"""Stock Entry validate: a row created from a Material Request Item
	should carry that item's cost center, not whatever Stock Entry itself
	defaulted to (observed: falls back to the Company's default cost
	center). Runs on every save, not just insert, so it self-heals if
	something resets the row's cost_center afterward."""
	for row in doc.items:
		if not row.material_request_item:
			continue
		mr_cost_center = frappe.db.get_value(
			"Material Request Item", row.material_request_item, "cost_center"
		)
		if mr_cost_center:
			row.cost_center = mr_cost_center
```

- [ ] **Step 5: Wire it in `hooks.py`**

Find `doc_events["Stock Entry"]` (currently has `on_submit` as a list and
`on_cancel` as a single string — do not disturb either) and add a new
`validate` key:

```python
	"Stock Entry": {
		"validate": "upande_stores.overrides.stock_entry.inherit_cost_center_from_material_request",
		"on_submit": [
			"upande_stores.overrides.stock_entry.lock_issued_employee",
			"upande_stores.overrides.stock_entry.create_ppe_assignments",
		],
		"on_cancel": "upande_stores.overrides.stock_entry.unlock_issued_employee",
	},
```

- [ ] **Step 6: Run to confirm it passes**

```bash
bench --site david.local run-tests --app upande_stores --module upande_stores.overrides.test_stock_entry
```
Expected: all tests in the file pass — the 3 new ones plus every pre-existing
test (`IntegrationTestStockEntryEmployeeLock`,
`IntegrationTestStockEntryPPEAssignmentCreation`), no regressions.

- [ ] **Step 7: Commit**

```bash
cd ~/frappe/kaitet-bench/apps/upande_stores
git add upande_stores/overrides/stock_entry.py upande_stores/overrides/test_stock_entry.py upande_stores/hooks.py
git commit -m "feat: inherit Stock Entry cost center from linked Material Request Item"
```

---

## Post-plan manual smoke test

Create a Material Issue Material Request with no employees — confirm it's
blocked on save. Add an employee row, set a Cost Center on one of its items,
submit, and create a Stock Entry from it — confirm that item's cost center on
the Stock Entry matches what was set on the Material Request, not the
Company's default.
