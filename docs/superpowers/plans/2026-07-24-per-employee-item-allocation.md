# Per-employee item allocation on Material Request Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a Material Issue Material Request record, per employee, which item and how much they need, track partial fulfillment, and only lock an employee out of `upande_ta`'s `bio_employee` picker once their specific allocation is fully issued.

**Architecture:** Three new fields on `Employee Request` (`item_code`, `qty`, `qty_issued`) carry the per-employee allocation. `overrides/material_request.py` validates those rows and derives the standard `items` table from them. `overrides/stock_entry.py`'s existing `lock_issued_employee`/`unlock_issued_employee` become qty-aware, matching each Stock Entry item row to its Employee Request allocation and only setting/clearing `issued_via_stock_entry` once the running total crosses the needed quantity.

**Tech Stack:** Frappe/ERPNext doctype JSON, Python `doc_events` hooks, `frappe.tests.IntegrationTestCase`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-24-per-employee-item-allocation-design.md` — every task below implements a section of it.
- Apps touched: `upande_stores` only. Never edit `upande_ta` (owns `bio_employee`'s picker query) or the PPE workflow's own MR-creation code (`api/ppe.py`).
- `mandatory_depends_on` is never enforced server-side (confirmed against `frappe/model/base_document.py`'s `_get_missing_mandatory_fields`) — every "required when X" rule in this plan is enforced by an explicit `validate()` hook, not by JSON alone.
- Test fixtures use `company="Karen Roses"`, warehouse `"Stores - KR"`, and item `"_Test Item"` / `"_Test Item 2"` (both real site fixtures — `stock_uom="_Test UOM"`, non-blank `description`), per the existing convention in `upande_stores/tests/test_helpers.py`.
- Run tests with: `bench --site david.local run-tests --app upande_stores --module upande_stores.overrides.test_material_request` and `...test_stock_entry` (these two modules live outside any `doctype/<name>/` folder, so real `run-tests` works — do not add test files under `doctype/employee_request/`, which hits a pre-existing, unrelated bootstrap crash).
- Blank-`item_code` Employee Request rows (the PPE workflow's shape) must keep behaving byte-for-byte as they do today in every function touched by this plan. Every existing test in `test_material_request.py` and `test_stock_entry.py` must continue to pass unmodified — they are this plan's regression suite for that guarantee.

---

### Task 1: Add `item_code`, `qty`, `qty_issued` fields to Employee Request

**Files:**
- Modify: `upande_stores/upande_stores/doctype/employee_request/employee_request.json`

**Interfaces:**
- Produces: `Employee Request.item_code` (Link → Item, optional), `Employee Request.qty` (Float, optional), `Employee Request.qty_issued` (Float, read-only, default 0) — consumed by Tasks 2-4.

- [ ] **Step 1: Write the new doctype JSON**

Replace the full contents of `upande_stores/upande_stores/doctype/employee_request/employee_request.json` with:

```json
{
 "actions": [],
 "allow_rename": 1,
 "creation": "2025-11-17 15:49:19.819916",
 "doctype": "DocType",
 "editable_grid": 1,
 "engine": "InnoDB",
 "field_order": [
  "employee",
  "employee_name",
  "item_code",
  "qty",
  "employee_farm",
  "department",
  "qty_issued",
  "issued_via_stock_entry"
 ],
 "fields": [
  {
   "fieldname": "employee",
   "fieldtype": "Link",
   "in_list_view": 1,
   "label": "Employee",
   "options": "Employee",
   "reqd": 1
  },
  {
   "fetch_from": "employee.employee_name",
   "fieldname": "employee_name",
   "fieldtype": "Data",
   "in_list_view": 1,
   "label": "Employee Name",
   "read_only": 1
  },
  {
   "fieldname": "item_code",
   "fieldtype": "Link",
   "in_list_view": 1,
   "label": "Item",
   "options": "Item"
  },
  {
   "fieldname": "qty",
   "fieldtype": "Float",
   "in_list_view": 1,
   "label": "Qty",
   "mandatory_depends_on": "eval:doc.item_code"
  },
  {
   "fetch_from": "employee.custom_farm",
   "fieldname": "employee_farm",
   "fieldtype": "Data",
   "label": "Employee's Farm",
   "read_only": 1
  },
  {
   "fetch_from": "employee.department",
   "fieldname": "department",
   "fieldtype": "Data",
   "label": "Department",
   "read_only": 1
  },
  {
   "default": "0",
   "fieldname": "qty_issued",
   "fieldtype": "Float",
   "in_list_view": 1,
   "label": "Qty Issued",
   "read_only": 1
  },
  {
   "fieldname": "issued_via_stock_entry",
   "fieldtype": "Link",
   "in_list_view": 0,
   "label": "Issued Via Stock Entry",
   "options": "Stock Entry",
   "read_only": 1
  }
 ],
 "grid_page_length": 50,
 "index_web_pages_for_search": 1,
 "istable": 1,
 "links": [],
 "modified": "2026-07-24 00:00:00.000000",
 "modified_by": "otieno@upande.com",
 "module": "Upande Stores",
 "name": "Employee Request",
 "owner": "otieno@upande.com",
 "permissions": [],
 "row_format": "Dynamic",
 "sort_field": "modified",
 "sort_order": "DESC",
 "states": []
}
```

- [ ] **Step 2: Migrate**

Run: `bench --site david.local migrate`
Expected: completes with no errors.

- [ ] **Step 3: Verify the columns exist**

Run: `bench --site david.local execute frappe.db.get_table_columns --args '["Employee Request"]'`
Expected: the printed list includes `item_code`, `qty`, and `qty_issued`.

- [ ] **Step 4: Commit**

```bash
git add upande_stores/upande_stores/doctype/employee_request/employee_request.json
git commit -m "feat: add item_code/qty/qty_issued fields to Employee Request"
```

---

### Task 2: Employee Data validation — (employee, item_code) uniqueness + qty required

**Files:**
- Modify: `upande_stores/overrides/material_request.py:21-38` (replace `validate_no_duplicate_employees`)
- Modify: `upande_stores/hooks.py:145` (rename the hook reference)
- Modify: `upande_stores/overrides/test_material_request.py` (extend `IntegrationTestMaterialRequestEmployeeValidation`)

**Interfaces:**
- Consumes: `Employee Request.item_code`/`qty` (Task 1).
- Produces: `upande_stores.overrides.material_request.validate_employee_allocations(doc, method=None) -> None`, replacing `validate_no_duplicate_employees` under the same "Material Request validate" hook slot. Task 3 relies on this having already rejected any row with `item_code` set and no `qty`, so it never needs to re-check that.

- [ ] **Step 1: Write the failing tests**

Append to `upande_stores/overrides/test_material_request.py`'s `IntegrationTestMaterialRequestEmployeeValidation` class (after `test_allows_distinct_employees_in_employee_data`):

```python
	def test_allows_same_employee_with_different_items(self):
		emp = self.employees[0]
		mr = make_material_request(
			employee_rows=[
				{"employee": emp, "item_code": "_Test Item", "qty": 5},
				{"employee": emp, "item_code": "_Test Item 2", "qty": 3},
			]
		)
		self.assertEqual(len(mr.custom_employee_data), 2)

	def test_rejects_duplicate_employee_and_item_pair(self):
		emp = self.employees[0]
		with self.assertRaises(frappe.ValidationError):
			make_material_request(
				employee_rows=[
					{"employee": emp, "item_code": "_Test Item", "qty": 5},
					{"employee": emp, "item_code": "_Test Item", "qty": 3},
				]
			)

	def test_rejects_item_without_qty(self):
		emp = self.employees[0]
		with self.assertRaises(frappe.ValidationError):
			make_material_request(
				employee_rows=[{"employee": emp, "item_code": "_Test Item"}]
			)

	def test_rejects_item_with_zero_qty(self):
		emp = self.employees[0]
		with self.assertRaises(frappe.ValidationError):
			make_material_request(
				employee_rows=[{"employee": emp, "item_code": "_Test Item", "qty": 0}]
			)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bench --site david.local run-tests --app upande_stores --module upande_stores.overrides.test_material_request`
Expected: the 4 new tests FAIL — `test_allows_same_employee_with_different_items` and `test_rejects_item_without_qty`/`test_rejects_item_with_zero_qty` fail because today's `validate_no_duplicate_employees` throws on *any* repeated `employee` regardless of `item_code` (so the "different items" case wrongly raises, and there's no qty check at all so the "missing qty" cases wrongly succeed); `test_rejects_duplicate_employee_and_item_pair` happens to already pass today (same employee, no item distinction) but must keep passing after Step 3.

- [ ] **Step 3: Replace the implementation**

In `upande_stores/overrides/material_request.py`, replace:

```python
def validate_no_duplicate_employees(doc, method=None):
	"""Material Request validate hook: block saving if the same employee
	appears more than once in custom_employee_data. Runs on every save (not
	just once), so a duplicate can't be introduced after the fact -- and it
	protects the Stock Entry lock/unlock logic (Task 3), which would
	otherwise have an ambiguous row to match against.
	"""
	seen = set()
	for row in doc.get("custom_employee_data") or []:
		if not row.employee:
			continue
		if row.employee in seen:
			frappe.throw(
				_("Employee {0} appears more than once in Employee Data.").format(
					frappe.bold(row.employee)
				)
			)
		seen.add(row.employee)
```

with:

```python
def validate_employee_allocations(doc, method=None):
	"""Material Request validate hook: for each row in custom_employee_data,
	(a) the same (employee, item_code) pair may not repeat, and (b) qty is
	required and must be positive whenever item_code is set. Runs on every
	save (not just once), so a violation can't be introduced after the
	fact -- (a) protects the Stock Entry lock/unlock logic
	(lock_issued_employee/unlock_issued_employee), which would otherwise
	have an ambiguous row to match against.

	Blank-item_code rows (the PPE workflow's own shape: one row per
	employee, no per-item allocation) keep the original
	single-employee-per-request constraint -- two blank-item_code rows for
	the same employee still collide, since both match the key
	(employee, "").

	qty's requirement can't be expressed as a plain JSON `reqd` (it's
	conditional on item_code) and `mandatory_depends_on` is never enforced
	server-side (see Global Constraints) -- so it's checked here instead.
	"""
	seen = set()
	for row in doc.get("custom_employee_data") or []:
		if not row.employee:
			continue
		if row.item_code and not (row.qty and row.qty > 0):
			frappe.throw(
				_("Row for Employee {0}: Qty is required and must be greater than 0 when Item is set.").format(
					frappe.bold(row.employee)
				)
			)
		key = (row.employee, row.item_code or "")
		if key in seen:
			if row.item_code:
				frappe.throw(
					_("Employee {0} appears more than once for Item {1} in Employee Data.").format(
						frappe.bold(row.employee), frappe.bold(row.item_code)
					)
				)
			frappe.throw(
				_("Employee {0} appears more than once in Employee Data.").format(
					frappe.bold(row.employee)
				)
			)
		seen.add(key)
```

In `upande_stores/hooks.py`, in `doc_events["Material Request"]["validate"]`, replace:

```python
			"upande_stores.overrides.material_request.validate_no_duplicate_employees",
```

with:

```python
			"upande_stores.overrides.material_request.validate_employee_allocations",
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `bench --site david.local run-tests --app upande_stores --module upande_stores.overrides.test_material_request`
Expected: all tests pass, including the 4 new ones and every pre-existing test in the module (regression check).

- [ ] **Step 5: Commit**

```bash
git add upande_stores/overrides/material_request.py upande_stores/hooks.py upande_stores/overrides/test_material_request.py
git commit -m "feat: validate employee allocations by (employee, item_code) pair, require qty when item_code is set"
```

---

### Task 3: Derive the Items table from employee allocations

**Files:**
- Modify: `upande_stores/overrides/material_request.py` (add `sync_employee_allocations_to_items`)
- Modify: `upande_stores/hooks.py:141-150` (add the new function to the `validate` hook list)
- Modify: `upande_stores/overrides/test_material_request.py` (new test class)

**Interfaces:**
- Consumes: `Employee Request.item_code`/`qty` (Task 1), the fact that `validate_employee_allocations` (Task 2) has already rejected any `item_code` row missing a positive `qty` by the time this hook runs.
- Produces: `upande_stores.overrides.material_request.sync_employee_allocations_to_items(doc, method=None) -> None`.

- [ ] **Step 1: Write the failing tests**

Append to `upande_stores/overrides/test_material_request.py`:

```python
class IntegrationTestMaterialRequestAllocationItemSync(IntegrationTestCase):
	def setUp(self):
		farm, business_unit = get_test_farm_and_business_unit()
		if not farm or not business_unit:
			self.skipTest("No Farm/Business Unit record on this site to build a valid test Material Request.")
		self.employees = get_test_employees(count=2)
		if len(self.employees) < 2:
			self.skipTest("Need at least 2 Active Employee records on this site.")

	def test_items_table_is_derived_from_employee_allocations(self):
		emp1, emp2 = self.employees
		mr = make_material_request(
			employee_rows=[
				{"employee": emp1, "item_code": "_Test Item", "qty": 10},
				{"employee": emp2, "item_code": "_Test Item 2", "qty": 4},
			]
		)
		by_item = {row.item_code: row.qty for row in mr.items}
		self.assertEqual(by_item, {"_Test Item": 10, "_Test Item 2": 4})

	def test_allocations_for_the_same_item_are_summed(self):
		emp1, emp2 = self.employees
		mr = make_material_request(
			employee_rows=[
				{"employee": emp1, "item_code": "_Test Item", "qty": 10},
				{"employee": emp2, "item_code": "_Test Item", "qty": 4},
			]
		)
		self.assertEqual(len(mr.items), 1)
		self.assertEqual(mr.items[0].item_code, "_Test Item")
		self.assertEqual(mr.items[0].qty, 14)

	def test_blank_item_code_rows_leave_items_table_untouched(self):
		# The PPE workflow's own shape: no employee row has item_code set, so
		# this hook must no-op and leave whatever the caller put in `items`.
		emp = self.employees[0]
		mr = make_material_request(employee_rows=[{"employee": emp}], item_code="_Test Item", qty=7)
		self.assertEqual(len(mr.items), 1)
		self.assertEqual(mr.items[0].item_code, "_Test Item")
		self.assertEqual(mr.items[0].qty, 7)

	def test_derived_item_row_carries_forward_an_existing_warehouse(self):
		# Simulates re-saving a Material Request that already had its Items
		# table filled in with a warehouse (e.g. from an earlier save, before
		# qty changed) -- the derived row must not silently drop it.
		emp = self.employees[0]
		mr = make_material_request(employee_rows=[{"employee": emp, "item_code": "_Test Item", "qty": 5}])
		self.assertEqual(mr.items[0].warehouse, "Stores - KR")

		mr.custom_employee_data[0].qty = 8
		mr.save()

		self.assertEqual(len(mr.items), 1)
		self.assertEqual(mr.items[0].qty, 8)
		self.assertEqual(mr.items[0].warehouse, "Stores - KR")
```

Note: `test_derived_item_row_carries_forward_an_existing_warehouse` needs the very first insert to already produce a row with `warehouse="Stores - KR"` — that only happens if Task 3's own sync function is what sets it (from Step 3's `existing_warehouse_by_item` lookup finding nothing on the first save, i.e. warehouse would be blank on insert). Re-read this after Step 3: `make_material_request` always builds one placeholder item row with `"warehouse": "Stores - KR"` before `custom_employee_data` is even considered; that placeholder row is what `existing_warehouse_by_item` picks up on this *first* validate cycle (its `item_code` is `"_Test Item"` by default, matching the allocation's `item_code`), so the derived row for `_Test Item` does inherit `"Stores - KR"` even on insert. The second assertion (after `mr.save()`) is the real regression check: without carrying it forward, a re-save would silently blank the warehouse out.

- [ ] **Step 2: Run tests to verify they fail**

Run: `bench --site david.local run-tests --app upande_stores --module upande_stores.overrides.test_material_request`
Expected: all 4 new tests in `IntegrationTestMaterialRequestAllocationItemSync` FAIL (the sync function doesn't exist yet, so `items` is never derived — `test_blank_item_code_rows_leave_items_table_untouched` happens to pass already since there's nothing to derive, but treat it as failing/unverified until Step 3 lands).

- [ ] **Step 3: Implement `sync_employee_allocations_to_items`**

In `upande_stores/overrides/material_request.py`, add (after `validate_employee_allocations`, before `sync_accounting_dimensions_to_items`):

```python
def sync_employee_allocations_to_items(doc, method=None):
	"""Material Request validate: when at least one Employee Data row states
	an item_code/qty, the standard Items table (required by ERPNext's stock
	engine regardless of this feature) is fully derived from the sum of
	those per-employee allocations, grouped by item_code -- instead of being
	filled in separately by hand and kept in sync with Employee Data.

	No-ops when no Employee Data row has item_code set (e.g. the PPE
	workflow's own MR-creation code, which tracks per-employee items a
	different way via Employee PPE Assignment) -- Items stays exactly as the
	caller built it. This is the backward-compatibility guarantee for the
	PPE workflow.

	Must run before sync_accounting_dimensions_to_items in hooks.py's
	validate list -- that function pushes custom_farm/custom_business_unit
	onto every row in doc.items, and if this function rebuilt doc.items
	afterward, those values would be lost on the freshly created rows.

	This hook runs after ERPNext's own controller validate() has already
	populated defaults (uom, stock_uom, conversion_factor, description) on
	whatever rows existed when THIS SAVE started -- so any row this function
	creates from scratch has to set those itself; nothing downstream will
	fill them in.
	"""
	allocations = [row for row in doc.get("custom_employee_data") or [] if row.item_code and row.qty]
	if not allocations:
		return

	existing_warehouse_by_item = {
		row.item_code: row.warehouse for row in doc.items if row.item_code and row.warehouse
	}

	merged = {}
	for row in allocations:
		merged[row.item_code] = merged.get(row.item_code, 0) + row.qty

	doc.items = []
	for item_code, qty in merged.items():
		stock_uom, description = frappe.db.get_value("Item", item_code, ["stock_uom", "description"])
		doc.append(
			"items",
			{
				"item_code": item_code,
				"qty": qty,
				"uom": stock_uom,
				"stock_uom": stock_uom,
				"conversion_factor": 1,
				"description": description or item_code,
				"schedule_date": doc.schedule_date or frappe.utils.today(),
				"warehouse": existing_warehouse_by_item.get(item_code),
			},
		)
```

In `upande_stores/hooks.py`, replace the `Material Request` `validate` list:

```python
		"validate": [
			"upande_stores.overrides.material_request.validate_employee_data_required_for_material_issue",
			"upande_stores.overrides.material_request.validate_employee_allocations",
			"upande_stores.overrides.material_request.sync_accounting_dimensions_to_items",
		],
```

with:

```python
		"validate": [
			"upande_stores.overrides.material_request.validate_employee_data_required_for_material_issue",
			"upande_stores.overrides.material_request.validate_employee_allocations",
			"upande_stores.overrides.material_request.sync_employee_allocations_to_items",
			"upande_stores.overrides.material_request.sync_accounting_dimensions_to_items",
		],
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `bench --site david.local run-tests --app upande_stores --module upande_stores.overrides.test_material_request`
Expected: all tests pass, including the 4 new ones and every pre-existing test in the module (regression check — in particular `IntegrationTestMaterialRequestAccountingDimensionSync.test_header_farm_and_business_unit_sync_to_every_item_row` must still pass, proving the new hook's insertion point didn't break farm/business_unit syncing).

- [ ] **Step 5: Commit**

```bash
git add upande_stores/overrides/material_request.py upande_stores/hooks.py upande_stores/overrides/test_material_request.py
git commit -m "feat: derive Material Request items table from employee allocations"
```

---

### Task 4: Qty-aware employee lock/unlock on Stock Entry

**Files:**
- Modify: `upande_stores/overrides/stock_entry.py:16-73` (replace `lock_issued_employee`/`unlock_issued_employee`)
- Modify: `upande_stores/tests/test_helpers.py:86-113` (extend `make_stock_entry_for_material_request`)
- Modify: `upande_stores/overrides/test_stock_entry.py` (new test class)

**Interfaces:**
- Consumes: `Employee Request.item_code`/`qty`/`qty_issued` (Task 1); `upande_stores.tests.test_helpers.make_material_request` (unchanged signature).
- Produces: `upande_stores.tests.test_helpers.make_stock_entry_for_material_request(material_request, bio_employee=None, item_code=None, qty=1) -> Document` (new optional `item_code`/`qty` params; existing 2-arg calls are unaffected).

- [ ] **Step 1: Extend the test helper**

In `upande_stores/tests/test_helpers.py`, replace `make_stock_entry_for_material_request`:

```python
def make_stock_entry_for_material_request(material_request, bio_employee=None):
	"""Create a not-yet-submitted 'Material Issue' Stock Entry whose single
	item references material_request's first item row -- the same shape the
	real "Create" button on a submitted Material Request produces."""
	mr_item = material_request.items[0]
	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"purpose": "Material Issue",
			"stock_entry_type": "Material Issue",
			"company": "Karen Roses",
			"bio_employee": bio_employee,
			"items": [
				{
					"item_code": mr_item.item_code,
					"qty": 1,
					"uom": "_Test UOM",
					"stock_uom": "_Test UOM",
					"conversion_factor": 1,
					"s_warehouse": "Stores - KR",
					"material_request": material_request.name,
					"material_request_item": mr_item.name,
				}
			],
		}
	)
	se.insert(ignore_permissions=True)
	return se
```

with:

```python
def make_stock_entry_for_material_request(material_request, bio_employee=None, item_code=None, qty=1):
	"""Create a not-yet-submitted 'Material Issue' Stock Entry whose single
	item references material_request's first item row -- the same shape the
	real "Create" button on a submitted Material Request produces.

	item_code selects which of material_request's item rows to issue against
	(defaults to the first row, matching every pre-existing caller); qty
	defaults to 1. Both are needed for per-employee-allocation tests, which
	build Material Requests with more than one item row and issue a specific
	quantity against a specific one -- possibly more than once, to exercise
	partial issuance.
	"""
	mr_item = material_request.items[0]
	if item_code:
		mr_item = next(row for row in material_request.items if row.item_code == item_code)
	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"purpose": "Material Issue",
			"stock_entry_type": "Material Issue",
			"company": "Karen Roses",
			"bio_employee": bio_employee,
			"items": [
				{
					"item_code": mr_item.item_code,
					"qty": qty,
					"uom": "_Test UOM",
					"stock_uom": "_Test UOM",
					"conversion_factor": 1,
					"s_warehouse": "Stores - KR",
					"material_request": material_request.name,
					"material_request_item": mr_item.name,
				}
			],
		}
	)
	se.insert(ignore_permissions=True)
	return se
```

- [ ] **Step 2: Write the failing tests**

Append to `upande_stores/overrides/test_stock_entry.py`:

```python
class IntegrationTestStockEntryPerItemAllocationLock(IntegrationTestCase):
	def setUp(self):
		farm, business_unit = get_test_farm_and_business_unit()
		if not farm or not business_unit:
			self.skipTest("No Farm/Business Unit record on this site to build a valid test document.")
		self.employees = get_test_employees(count=2)
		if len(self.employees) < 2:
			self.skipTest("Need at least 2 Active Employee records on this site.")
		self.employee = self.employees[0]

	def _allocation_row(self, mr):
		return frappe.db.get_value(
			"Employee Request",
			{"parent": mr.name, "employee": self.employee},
			["name", "qty", "qty_issued", "issued_via_stock_entry"],
			as_dict=True,
		)

	def test_partial_issuance_does_not_lock_the_employee(self):
		mr = make_material_request(
			employee_rows=[{"employee": self.employee, "item_code": "_Test Item", "qty": 10}]
		)
		se = make_stock_entry_for_material_request(mr, bio_employee=self.employee, qty=3)
		se.submit()

		row = self._allocation_row(mr)
		self.assertEqual(row.qty_issued, 3)
		self.assertFalse(row.issued_via_stock_entry)

	def test_second_partial_issuance_completes_and_locks(self):
		mr = make_material_request(
			employee_rows=[{"employee": self.employee, "item_code": "_Test Item", "qty": 10}]
		)
		first = make_stock_entry_for_material_request(mr, bio_employee=self.employee, qty=3)
		first.submit()

		second = make_stock_entry_for_material_request(mr, bio_employee=self.employee, qty=7)
		second.submit()

		row = self._allocation_row(mr)
		self.assertEqual(row.qty_issued, 10)
		self.assertEqual(row.issued_via_stock_entry, second.name)

	def test_issuance_after_full_satisfaction_is_blocked(self):
		mr = make_material_request(
			employee_rows=[{"employee": self.employee, "item_code": "_Test Item", "qty": 5}]
		)
		first = make_stock_entry_for_material_request(mr, bio_employee=self.employee, qty=5)
		first.submit()

		second = make_stock_entry_for_material_request(mr, bio_employee=self.employee, qty=1)
		with self.assertRaises(frappe.ValidationError):
			second.submit()

	def test_cancelling_a_partial_issuance_reduces_qty_issued(self):
		mr = make_material_request(
			employee_rows=[{"employee": self.employee, "item_code": "_Test Item", "qty": 10}]
		)
		se = make_stock_entry_for_material_request(mr, bio_employee=self.employee, qty=3)
		se.submit()
		se.cancel()

		row = self._allocation_row(mr)
		self.assertEqual(row.qty_issued, 0)
		self.assertFalse(row.issued_via_stock_entry)

	def test_cancelling_a_contributing_issuance_reopens_a_locked_employee(self):
		mr = make_material_request(
			employee_rows=[{"employee": self.employee, "item_code": "_Test Item", "qty": 10}]
		)
		first = make_stock_entry_for_material_request(mr, bio_employee=self.employee, qty=3)
		first.submit()
		second = make_stock_entry_for_material_request(mr, bio_employee=self.employee, qty=7)
		second.submit()

		row = self._allocation_row(mr)
		self.assertEqual(row.issued_via_stock_entry, second.name)  # fully locked

		second.cancel()

		row = self._allocation_row(mr)
		self.assertEqual(row.qty_issued, 3)
		self.assertFalse(row.issued_via_stock_entry)

	def test_one_employee_with_two_item_allocations_are_tracked_independently(self):
		emp = self.employee
		mr = make_material_request(
			employee_rows=[
				{"employee": emp, "item_code": "_Test Item", "qty": 5},
				{"employee": emp, "item_code": "_Test Item 2", "qty": 2},
			]
		)
		se = make_stock_entry_for_material_request(mr, bio_employee=emp, item_code="_Test Item", qty=5)
		se.submit()

		locked_row = frappe.db.get_value(
			"Employee Request",
			{"parent": mr.name, "employee": emp, "item_code": "_Test Item"},
			["qty_issued", "issued_via_stock_entry"],
			as_dict=True,
		)
		open_row = frappe.db.get_value(
			"Employee Request",
			{"parent": mr.name, "employee": emp, "item_code": "_Test Item 2"},
			["qty_issued", "issued_via_stock_entry"],
			as_dict=True,
		)
		self.assertEqual(locked_row.qty_issued, 5)
		self.assertEqual(locked_row.issued_via_stock_entry, se.name)
		self.assertEqual(open_row.qty_issued, 0)
		self.assertFalse(open_row.issued_via_stock_entry)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `bench --site david.local run-tests --app upande_stores --module upande_stores.overrides.test_stock_entry`
Expected: the 6 new tests in `IntegrationTestStockEntryPerItemAllocationLock` FAIL or error — today's `lock_issued_employee` locks on the very first submission regardless of qty, so e.g. `test_partial_issuance_does_not_lock_the_employee` fails because `issued_via_stock_entry` is already set after issuing only 3 of 10.

- [ ] **Step 4: Replace the implementation**

In `upande_stores/overrides/stock_entry.py`, replace `lock_issued_employee` and `unlock_issued_employee` (keep `_resolve_material_request` as-is):

```python
def _find_employee_request_row(material_request, employee, item_code):
	"""Match the Employee Request row a Stock Entry item row fulfils: first
	by (material_request, employee, item_code) -- the fine-grained
	per-item-allocation case -- and if no such row exists, fall back to the
	blank-item_code row for this employee (the PPE workflow's shape: one row
	per employee, no item-specificity). Locks the matched row for update so
	concurrent submits/cancels against the same allocation serialize instead
	of racing on a stale read.
	"""
	fields = ["name", "item_code", "qty", "qty_issued", "issued_via_stock_entry"]
	row = frappe.db.get_value(
		"Employee Request",
		{
			"parent": material_request,
			"parenttype": "Material Request",
			"employee": employee,
			"item_code": item_code,
		},
		fields,
		as_dict=True,
		for_update=True,
	)
	if row:
		return row
	return frappe.db.get_value(
		"Employee Request",
		{
			"parent": material_request,
			"parenttype": "Material Request",
			"employee": employee,
			"item_code": "",
		},
		fields,
		as_dict=True,
		for_update=True,
	)


def lock_issued_employee(doc, method=None):
	"""Stock Entry on_submit: for each of this Stock Entry's item rows, find
	the Employee Request row it fulfils and record the issuance against it.

	Fine-grained rows (item_code set): qty_issued accumulates across
	Stock Entries; the row only locks (drops out of upande_ta's bio_employee
	query, via issued_via_stock_entry) once qty_issued reaches qty, so a
	partial issuance leaves the employee selectable for a follow-up entry.
	Throws if this allocation was already fully satisfied before this Stock
	Entry. Does not cap how much a single Stock Entry may issue against an
	allocation -- overshooting the remaining quantity simply locks the row
	as satisfied; validating that is out of scope.

	Blank-item_code rows (PPE-style, no per-item allocation): unchanged from
	before this feature -- locks immediately on any submission, throws if a
	different Stock Entry already claimed it.

	No-ops if there's no Material Request context, no bio_employee set, or a
	given item row has no matching Employee Request row at all (bio_employee's
	general biometric-verification use, independent of this feature, is
	untouched).
	"""
	material_request = _resolve_material_request(doc)
	if not material_request or not doc.get("bio_employee"):
		return

	for row in doc.items:
		if not row.item_code:
			continue

		employee_request = _find_employee_request_row(material_request, doc.bio_employee, row.item_code)
		if not employee_request:
			continue

		if employee_request.item_code:
			if employee_request.qty_issued >= employee_request.qty:
				frappe.throw(
					_("Employee {0} has already been fully issued {1} under Material Request {2}.").format(
						frappe.bold(doc.bio_employee), frappe.bold(row.item_code), frappe.bold(material_request)
					)
				)
			new_qty_issued = employee_request.qty_issued + (row.qty or 0)
			updates = {"qty_issued": new_qty_issued}
			if new_qty_issued >= employee_request.qty:
				updates["issued_via_stock_entry"] = doc.name
			frappe.db.set_value("Employee Request", employee_request.name, updates)
		else:
			existing = employee_request.issued_via_stock_entry
			if existing and existing != doc.name:
				frappe.throw(
					_(
						"Employee {0} has already been issued items under Material Request {1} via Stock Entry {2}."
					).format(frappe.bold(doc.bio_employee), frappe.bold(material_request), frappe.bold(existing))
				)
			frappe.db.set_value("Employee Request", employee_request.name, "issued_via_stock_entry", doc.name)


def unlock_issued_employee(doc, method=None):
	"""Stock Entry on_cancel: inverse of lock_issued_employee, per item row.

	Fine-grained rows (item_code set): qty_issued decrements by this row's
	quantity (never below 0); issued_via_stock_entry is cleared (reopened)
	whenever qty_issued drops below qty as a result -- regardless of which
	Stock Entry is currently recorded there, since cancelling any
	contributing entry can drop the running total below the threshold.

	Blank-item_code rows: unchanged from before this feature -- clears the
	lock only if it currently equals this Stock Entry's name.
	"""
	material_request = _resolve_material_request(doc)
	if not material_request or not doc.get("bio_employee"):
		return

	for row in doc.items:
		if not row.item_code:
			continue

		employee_request = _find_employee_request_row(material_request, doc.bio_employee, row.item_code)
		if not employee_request:
			continue

		if employee_request.item_code:
			new_qty_issued = max(0, employee_request.qty_issued - (row.qty or 0))
			updates = {"qty_issued": new_qty_issued}
			if new_qty_issued < employee_request.qty:
				updates["issued_via_stock_entry"] = None
			frappe.db.set_value("Employee Request", employee_request.name, updates)
		elif employee_request.issued_via_stock_entry == doc.name:
			frappe.db.set_value("Employee Request", employee_request.name, "issued_via_stock_entry", None)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `bench --site david.local run-tests --app upande_stores --module upande_stores.overrides.test_stock_entry`
Expected: all tests pass, including the 6 new ones and every pre-existing test in the module (regression check — in particular `IntegrationTestStockEntryEmployeeLock`'s 4 tests must keep passing unmodified, proving blank-item_code behavior is unchanged; `IntegrationTestStockEntryPPEAssignmentCreation` and the accounting-dimension classes must also keep passing, since they exercise `lock_issued_employee` indirectly through the same submit path).

- [ ] **Step 6: Commit**

```bash
git add upande_stores/overrides/stock_entry.py upande_stores/tests/test_helpers.py upande_stores/overrides/test_stock_entry.py
git commit -m "feat: make employee-issuance lock qty-aware, supporting partial issuance"
```
