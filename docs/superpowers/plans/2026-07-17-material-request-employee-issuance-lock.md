# Material Request → Stock Entry Employee Issuance Lock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scope Stock Entry's `bio_employee` field to a linked Material Request's not-yet-issued employees, lock an employee to a Stock Entry on submit, unlock on cancel, and block duplicate employees within one Material Request's Employee Data table.

**Architecture:** One new field (`issued_via_stock_entry`) on the shared `Employee Request` child doctype records which Stock Entry (if any) has claimed each employee row. `upande_stores` owns the write side (`Material Request.validate` duplicate check; `Stock Entry.on_submit`/`on_cancel` lock/unlock). `upande_ta` owns the read side (a Link-field query scoping `bio_employee`'s options). Both resolve "which Material Request" the same way: the first `Stock Entry Detail` row with a non-empty `material_request`.

**Tech Stack:** Frappe framework (Python doc_events + whitelisted query functions), Frappe client-side form scripting (`frappe.ui.form.on`), MariaDB via `frappe.db`/`frappe.get_all`. Site under test: `david.local`.

## Global Constraints

- Design doc: `apps/upande_stores/docs/superpowers/specs/2026-07-17-material-request-employee-issuance-lock-design.md` — every task below implements one of its sections.
- `custom_farm` and `custom_business_unit` are `reqd=1` on both `Material Request` and `Stock Entry` — every test document built in this plan must set both.
- Never clear a lock that doesn't belong to the cancelling Stock Entry (match on `issued_via_stock_entry == doc.name`, not just employee+MR).
- No cross-app Python imports between `upande_stores` and `upande_ta`. `upande_stores` (Task 3) resolves the Material Request server-side, in its own `_resolve_material_request` helper. `upande_ta` (Task 4) resolves it client-side in JavaScript instead (from `frm.doc.items`, which also works for unsaved drafts) and passes it to the server as a plain filter value — so there is no server-side resolution helper to duplicate on that side.
- Run tests against the `david.local` site (`bench --site david.local run-tests --module <dotted.path>`), using its existing seed data (`_Test Company`, `_Test Item`, `_Test Warehouse - _TC`, `Material Issue` Stock Entry Type — all confirmed present) plus a live `Farm`/`Business Unit` record looked up at test time (skip the test if none exist rather than hardcoding a name).

---

### Task 1: Add `issued_via_stock_entry` field to Employee Request

**Files:**
- Modify: `apps/upande_stores/upande_stores/upande_stores/doctype/employee_request/employee_request.json`

**Interfaces:**
- Produces: `Employee Request.issued_via_stock_entry` (Link → Stock Entry, nullable). Later tasks read/write it via `frappe.db.get_value`/`frappe.db.set_value("Employee Request", <row name>, "issued_via_stock_entry", ...)` and via `frappe.get_all("Employee Request", fields=[..., "issued_via_stock_entry"], ...)`.

- [ ] **Step 1: Add the field to the doctype JSON**

Current file (`apps/upande_stores/upande_stores/upande_stores/doctype/employee_request/employee_request.json`) has `field_order: ["employee", "employee_name", "farm", "department"]` and a matching `fields` array. Edit both:

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
  "farm",
  "department",
  "issued_via_stock_entry"
 ],
 "fields": [
  {
   "fieldname": "employee",
   "fieldtype": "Link",
   "in_list_view": 1,
   "label": "Employee",
   "options": "Employee"
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
   "fetch_from": "employee.custom_farm",
   "fieldname": "farm",
   "fieldtype": "Data",
   "label": "Farm",
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
   "fieldname": "issued_via_stock_entry",
   "fieldtype": "Link",
   "in_list_view": 1,
   "label": "Issued Via Stock Entry",
   "options": "Stock Entry",
   "read_only": 1
  }
 ],
 "grid_page_length": 50,
 "index_web_pages_for_search": 1,
 "istable": 1,
 "links": [],
 "modified": "2026-07-17 00:00:00.000000",
 "modified_by": "Administrator",
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

- [ ] **Step 2: Sync the schema**

Run: `cd /home/david/frappe/kaitet-bench && bench --site david.local migrate`
Expected: completes with no errors (this doctype has no fixture/customization sync involved — it's a native doctype field, picked up directly by the schema sync step).

- [ ] **Step 3: Verify the column exists**

Run:
```bash
cd /home/david/frappe/kaitet-bench
bench --site david.local mariadb -e "DESCRIBE \`tabEmployee Request\`;" | grep issued_via_stock_entry
```
Expected output: a row for `issued_via_stock_entry` with type `varchar(140)`.

- [ ] **Step 4: Commit**

```bash
cd /home/david/frappe/kaitet-bench/apps/upande_stores
git add upande_stores/upande_stores/doctype/employee_request/employee_request.json
git commit -m "Add issued_via_stock_entry field to Employee Request"
```

---

### Task 2: Block duplicate employees in a Material Request's Employee Data

**Files:**
- Create: `apps/upande_stores/upande_stores/overrides/__init__.py`
- Create: `apps/upande_stores/upande_stores/overrides/material_request.py`
- Create: `apps/upande_stores/upande_stores/tests/__init__.py`
- Create: `apps/upande_stores/upande_stores/tests/test_helpers.py`
- Test: `apps/upande_stores/upande_stores/overrides/test_material_request.py`
- Modify: `apps/upande_stores/upande_stores/hooks.py`

**Interfaces:**
- Consumes: `_Test Company`, `_Test Item`, `_Test Warehouse - _TC` (standard ERPNext test fixtures, already present on `david.local`); a live `Farm`/`Business Unit` record (looked up, not hardcoded).
- Produces: `upande_stores.tests.test_helpers.get_test_farm_and_business_unit() -> tuple[str | None, str | None]` and `upande_stores.tests.test_helpers.make_material_request(employee_rows: list[dict] | None = None) -> Document`, both reused by Task 3's tests. `upande_stores.overrides.material_request.validate_no_duplicate_employees(doc, method=None) -> None`.

- [ ] **Step 1: Create the overrides package**

```bash
cd /home/david/frappe/kaitet-bench
mkdir -p apps/upande_stores/upande_stores/overrides
touch apps/upande_stores/upande_stores/overrides/__init__.py
mkdir -p apps/upande_stores/upande_stores/tests
touch apps/upande_stores/upande_stores/tests/__init__.py
```

- [ ] **Step 2: Write the shared test helper**

Create `apps/upande_stores/upande_stores/tests/test_helpers.py`:

```python
"""Shared test-document builders for upande_stores's Material Request /
Stock Entry employee-issuance-lock tests. Kept here (not duplicated per
test file) because both test_material_request.py and test_stock_entry.py
need the same minimal, valid documents.
"""

import frappe
from frappe.utils import today


def get_test_farm_and_business_unit():
	"""Return (farm_name, business_unit_name) from existing site data.

	Farm/Business Unit have no bundled test fixtures of their own (Farm's
	farm_type is a mandatory Table MultiSelect, non-trivial to construct from
	scratch) -- we reuse whatever real records already exist on the site
	under test rather than hardcoding a specific name.
	"""
	farm = frappe.get_all("Farm", limit=1, pluck="name")
	business_unit = frappe.get_all("Business Unit", limit=1, pluck="name")
	return (farm[0] if farm else None, business_unit[0] if business_unit else None)


def get_test_employees(count=2):
	"""Return up to `count` live Active Employee names.

	Like Farm/Business Unit, Employee has no bundled test fixture guaranteeing
	a specific record exists, so we look up real records rather than
	hardcoding a name like "HR-EMP-00001" -- callers should skip their test
	if fewer than the needed count come back.
	"""
	return frappe.get_all("Employee", filters={"status": "Active"}, limit=count, pluck="name")


def make_material_request(employee_rows=None, qty=1):
	"""Create and insert a minimal submitted-ready 'Material Issue' Material
	Request. employee_rows is a list of dicts (e.g. {"employee": <name>}
	or {"employee": <name>, "issued_via_stock_entry": "STE-0001"}), appended
	to custom_employee_data as-is. qty defaults to 1; pass a higher value
	when a test needs to issue against the same Material Request more than
	once without tripping ERPNext's own "can't over-issue" guard before the
	code under test gets a chance to run.
	"""
	farm, business_unit = get_test_farm_and_business_unit()
	mr = frappe.get_doc(
		{
			"doctype": "Material Request",
			"material_request_type": "Material Issue",
			"transaction_date": today(),
			"company": "_Test Company",
			"custom_farm": farm,
			"custom_business_unit": business_unit,
			"items": [
				{
					"item_code": "_Test Item",
					"qty": qty,
					"uom": "_Test UOM",
					"stock_uom": "_Test UOM",
					"conversion_factor": 1,
					"schedule_date": today(),
					"warehouse": "_Test Warehouse - _TC",
				}
			],
		}
	)
	for row in employee_rows or []:
		mr.append("custom_employee_data", row)
	mr.insert(ignore_permissions=True)
	return mr
```

- [ ] **Step 3: Write the failing test**

Create `apps/upande_stores/upande_stores/overrides/test_material_request.py`:

```python
import frappe
from frappe.tests import IntegrationTestCase

from upande_stores.tests.test_helpers import (
	get_test_employees,
	get_test_farm_and_business_unit,
	make_material_request,
)


class IntegrationTestMaterialRequestEmployeeValidation(IntegrationTestCase):
	def setUp(self):
		farm, business_unit = get_test_farm_and_business_unit()
		if not farm or not business_unit:
			self.skipTest("No Farm/Business Unit record on this site to build a valid test Material Request.")
		self.employees = get_test_employees(count=2)
		if len(self.employees) < 2:
			self.skipTest("Need at least 2 Active Employee records on this site.")

	def test_rejects_duplicate_employee_in_employee_data(self):
		emp = self.employees[0]
		with self.assertRaises(frappe.ValidationError):
			make_material_request(
				employee_rows=[
					{"employee": emp},
					{"employee": emp},
				]
			)

	def test_allows_distinct_employees_in_employee_data(self):
		emp1, emp2 = self.employees
		mr = make_material_request(
			employee_rows=[
				{"employee": emp1},
				{"employee": emp2},
			]
		)
		self.assertEqual(len(mr.custom_employee_data), 2)
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd /home/david/frappe/kaitet-bench && bench --site david.local run-tests --module upande_stores.overrides.test_material_request`
Expected: `test_rejects_duplicate_employee_in_employee_data` FAILS (no `ValidationError` is raised yet — the hook doesn't exist). `test_allows_distinct_employees_in_employee_data` may pass already (nothing blocks it today) — that's fine, it's here to pin down the non-regression case.

- [ ] **Step 5: Implement the validation**

Create `apps/upande_stores/upande_stores/overrides/material_request.py`:

```python
import frappe
from frappe import _


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

- [ ] **Step 6: Wire the hook**

In `apps/upande_stores/upande_stores/hooks.py`, replace the commented-out template:

```python
# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }
```

with:

```python
# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Material Request": {
		"validate": "upande_stores.overrides.material_request.validate_no_duplicate_employees",
	},
}
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd /home/david/frappe/kaitet-bench && bench --site david.local run-tests --module upande_stores.overrides.test_material_request`
Expected: both tests PASS.

- [ ] **Step 8: Commit**

```bash
cd /home/david/frappe/kaitet-bench/apps/upande_stores
git add upande_stores/overrides/__init__.py upande_stores/overrides/material_request.py \
        upande_stores/overrides/test_material_request.py upande_stores/tests/__init__.py \
        upande_stores/tests/test_helpers.py upande_stores/hooks.py
git commit -m "Block duplicate employees in Material Request Employee Data"
```

---

### Task 3: Lock employee on Stock Entry submit, unlock on cancel

**Files:**
- Create: `apps/upande_stores/upande_stores/overrides/stock_entry.py`
- Test: `apps/upande_stores/upande_stores/overrides/test_stock_entry.py`
- Modify: `apps/upande_stores/upande_stores/tests/test_helpers.py`
- Modify: `apps/upande_stores/upande_stores/hooks.py`

**Interfaces:**
- Consumes: `Employee Request.issued_via_stock_entry` (Task 1); `upande_stores.tests.test_helpers.make_material_request` (Task 2).
- Produces: `upande_stores.overrides.stock_entry.lock_issued_employee(doc, method=None) -> None`, `upande_stores.overrides.stock_entry.unlock_issued_employee(doc, method=None) -> None`. Adds `upande_stores.tests.test_helpers.make_stock_entry_for_material_request(material_request, bio_employee=None) -> Document` for reuse by any future test in this app.

- [ ] **Step 1: Extend the shared test helper**

Append to `apps/upande_stores/upande_stores/tests/test_helpers.py`:

```python
def make_stock_entry_for_material_request(material_request, bio_employee=None):
	"""Create a not-yet-submitted 'Material Issue' Stock Entry whose single
	item references material_request's first item row -- the same shape the
	real "Create" button on a submitted Material Request produces."""
	farm, business_unit = get_test_farm_and_business_unit()
	mr_item = material_request.items[0]
	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"purpose": "Material Issue",
			"stock_entry_type": "Material Issue",
			"custom_farm": farm,
			"custom_business_unit": business_unit,
			"bio_employee": bio_employee,
			"items": [
				{
					"item_code": mr_item.item_code,
					"qty": 1,
					"uom": "_Test UOM",
					"stock_uom": "_Test UOM",
					"conversion_factor": 1,
					"s_warehouse": "_Test Warehouse - _TC",
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

Create `apps/upande_stores/upande_stores/overrides/test_stock_entry.py`:

```python
import frappe
from frappe.tests import IntegrationTestCase

from upande_stores.tests.test_helpers import (
	get_test_employees,
	get_test_farm_and_business_unit,
	make_material_request,
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /home/david/frappe/kaitet-bench && bench --site david.local run-tests --module upande_stores.overrides.test_stock_entry`
Expected: `test_submit_locks_the_employee_request_row` and `test_cancel_unlocks_the_employee_request_row` FAIL (`issued_via_stock_entry` never gets set — no hook exists yet). `test_second_submit_for_already_issued_employee_is_blocked` FAILS (no `ValidationError` raised — nothing blocks the second submit). `test_stock_entry_without_material_request_is_a_noop` passes already (nothing to break yet).

- [ ] **Step 4: Implement the lock/unlock hooks**

Create `apps/upande_stores/upande_stores/overrides/stock_entry.py`:

```python
import frappe
from frappe import _


def _resolve_material_request(doc):
	"""The Material Request this Stock Entry was created against, if any --
	the first item row with a non-empty material_request. Confirmed with the
	requester that a Stock Entry in this flow is always created against
	exactly one Material Request via its "Create" button."""
	for row in doc.items:
		if row.material_request:
			return row.material_request
	return None


def lock_issued_employee(doc, method=None):
	"""Stock Entry on_submit: stamp the matching Employee Request row (by
	Material Request + employee) with this Stock Entry's name, so it drops
	out of upande_ta's bio_employee query. Blocks the submit if another
	Stock Entry already claimed this employee for this Material Request
	(covers a stale dropdown / race). No-ops if there's no Material Request
	context, no bio_employee set, or bio_employee isn't one of this
	Material Request's tracked employees at all (bio_employee's general
	biometric-verification use, independent of this feature, is untouched).
	"""
	material_request = _resolve_material_request(doc)
	if not material_request or not doc.get("bio_employee"):
		return

	row_name = frappe.db.get_value(
		"Employee Request",
		{
			"parent": material_request,
			"parenttype": "Material Request",
			"employee": doc.bio_employee,
		},
		"name",
	)
	if not row_name:
		return

	existing = frappe.db.get_value("Employee Request", row_name, "issued_via_stock_entry")
	if existing and existing != doc.name:
		frappe.throw(
			_(
				"Employee {0} has already been issued items under Material Request {1} via Stock Entry {2}."
			).format(frappe.bold(doc.bio_employee), frappe.bold(material_request), frappe.bold(existing))
		)

	frappe.db.set_value("Employee Request", row_name, "issued_via_stock_entry", doc.name)


def unlock_issued_employee(doc, method=None):
	"""Stock Entry on_cancel: clear the lock, but only the row this exact
	Stock Entry set -- never a lock belonging to a different entry."""
	material_request = _resolve_material_request(doc)
	if not material_request or not doc.get("bio_employee"):
		return

	row_name = frappe.db.get_value(
		"Employee Request",
		{
			"parent": material_request,
			"parenttype": "Material Request",
			"employee": doc.bio_employee,
			"issued_via_stock_entry": doc.name,
		},
		"name",
	)
	if row_name:
		frappe.db.set_value("Employee Request", row_name, "issued_via_stock_entry", None)
```

- [ ] **Step 5: Wire the hooks**

In `apps/upande_stores/upande_stores/hooks.py`, extend the `doc_events` dict added in Task 2:

```python
doc_events = {
	"Material Request": {
		"validate": "upande_stores.overrides.material_request.validate_no_duplicate_employees",
	},
	"Stock Entry": {
		"on_submit": "upande_stores.overrides.stock_entry.lock_issued_employee",
		"on_cancel": "upande_stores.overrides.stock_entry.unlock_issued_employee",
	},
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /home/david/frappe/kaitet-bench && bench --site david.local run-tests --module upande_stores.overrides.test_stock_entry`
Expected: all four tests PASS.

- [ ] **Step 7: Run Task 2's tests too (regression check)**

Run: `cd /home/david/frappe/kaitet-bench && bench --site david.local run-tests --module upande_stores.overrides.test_material_request`
Expected: both still PASS (this task didn't touch Material Request validation, but confirms nothing in `hooks.py` broke it).

- [ ] **Step 8: Commit**

```bash
cd /home/david/frappe/kaitet-bench/apps/upande_stores
git add upande_stores/overrides/stock_entry.py upande_stores/overrides/test_stock_entry.py \
        upande_stores/tests/test_helpers.py upande_stores/hooks.py
git commit -m "Lock issued employee on Stock Entry submit, unlock on cancel"
```

---

### Task 4: Scope bio_employee to the Material Request's un-issued employees

**Files:**
- Modify: `apps/upande_ta/upande_ta/upande_ta/overrides/stock_entry.py`
- Modify: `apps/upande_ta/upande_ta/public/js/stock_entry.js`
- Test: `apps/upande_ta/upande_ta/upande_ta/overrides/test_stock_entry.py`

**Interfaces:**
- Consumes: `Employee Request.issued_via_stock_entry` (Task 1). Reads `filters.material_request`, a value the client resolves from `frm.doc.items` and passes explicitly (works for unsaved drafts too, since it never needs the Stock Entry to exist in the DB).
- Produces: `upande_ta.upande_ta.overrides.stock_entry.material_request_employee_query(doctype, txt, searchfield, start, page_length, filters) -> list[tuple[str, str]]` — the standard Frappe Link-field query signature, wired as `bio_employee`'s `get_query`.

**Cross-app compatibility note:** `upande_ta` is installed on other sites/environments that do not have `upande_stores` installed, so the `Employee Request` doctype (and its underlying DB table) will not exist there. `material_request` on a Stock Entry Detail row is a *standard* ERPNext field, unrelated to this feature and populated in plenty of contexts that have nothing to do with employee issuance — so this function can be reached with a real `material_request` value on a site where `Employee Request` doesn't exist at all. It must check `frappe.db.table_exists("Employee Request")` before querying that doctype and fall back to the plain Employee search if it's absent, exactly as if there were no Material Request context. This mirrors the existing defensive pattern already used elsewhere in this same file: `if not frappe.db.table_exists("Stock Entry"): return` in `ensure_biometric_stock_entry_fields`.

- [ ] **Step 1: Write the failing tests**

Create `apps/upande_ta/upande_ta/upande_ta/overrides/test_stock_entry.py`:

```python
import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from upande_ta.upande_ta.overrides.stock_entry import material_request_employee_query


def _make_material_request_with_employees(employee_status_pairs):
	"""employee_status_pairs: list of (employee, issued_via_stock_entry_or_None)."""
	farm = frappe.get_all("Farm", limit=1, pluck="name")
	business_unit = frappe.get_all("Business Unit", limit=1, pluck="name")
	mr = frappe.get_doc(
		{
			"doctype": "Material Request",
			"material_request_type": "Material Issue",
			"transaction_date": today(),
			"company": "_Test Company",
			"custom_farm": farm[0] if farm else None,
			"custom_business_unit": business_unit[0] if business_unit else None,
			"items": [
				{
					"item_code": "_Test Item",
					"qty": 1,
					"uom": "_Test UOM",
					"stock_uom": "_Test UOM",
					"conversion_factor": 1,
					"schedule_date": today(),
					"warehouse": "_Test Warehouse - _TC",
				}
			],
		}
	)
	for employee, issued_via in employee_status_pairs:
		mr.append("custom_employee_data", {"employee": employee, "issued_via_stock_entry": issued_via})
	mr.insert(ignore_permissions=True)
	return mr


class IntegrationTestMaterialRequestEmployeeQuery(IntegrationTestCase):
	def setUp(self):
		if not frappe.get_all("Farm", limit=1) or not frappe.get_all("Business Unit", limit=1):
			self.skipTest("No Farm/Business Unit record on this site to build a valid test Material Request.")
		# Employee has no bundled test fixture guaranteeing a specific record
		# exists, so look up real ones rather than hardcoding a name like
		# "HR-EMP-00001" (mirrors upande_stores' get_test_employees -- not
		# imported from there, since cross-app Python imports aren't allowed).
		self.employees = frappe.get_all("Employee", filters={"status": "Active"}, limit=2, pluck="name")
		if len(self.employees) < 2:
			self.skipTest("Need at least 2 Active Employee records on this site.")

	def test_excludes_already_issued_employees(self):
		emp1, emp2 = self.employees
		mr = _make_material_request_with_employees(
			[(emp1, None), (emp2, "STE-0001")]
		)
		results = material_request_employee_query(
			"Employee", "", "name", 0, 20, {"material_request": mr.name}
		)
		names = [r[0] for r in results]
		self.assertIn(emp1, names)
		self.assertNotIn(emp2, names)

	def test_falls_back_to_unrestricted_search_without_material_request(self):
		results = material_request_employee_query("Employee", "", "name", 0, 20, {"material_request": ""})
		self.assertIsInstance(results, list)
		self.assertGreater(len(results), 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/david/frappe/kaitet-bench && bench --site david.local run-tests --module upande_ta.upande_ta.overrides.test_stock_entry`
Expected: `ImportError` / `AttributeError` — `material_request_employee_query` doesn't exist yet.

- [ ] **Step 3: Implement the query function**

Append to the existing `apps/upande_ta/upande_ta/upande_ta/overrides/stock_entry.py` (the same file already holding `bio_employee`'s biometric-verification logic), after the existing imports at the top add `from frappe.utils import cint` if not already imported, then add at the end of the file:

```python
@frappe.whitelist()
def material_request_employee_query(doctype, txt, searchfield, start, page_length, filters):
	"""Link query for Stock Entry's bio_employee field.

	filters["material_request"] is resolved client-side (see stock_entry.js)
	from the current form's item rows -- not re-derived server-side from a
	saved Stock Entry, so this works for unsaved drafts too. Scoped to that
	Material Request's Employee Data rows that haven't been issued via
	another Stock Entry yet (Employee Request.issued_via_stock_entry empty).
	Falls back to a plain Employee search when there's no Material Request
	context, matching bio_employee's existing unrestricted behavior -- also
	used when the Employee Request doctype doesn't exist at all (this app is
	installed on other sites that don't have upande_stores, where
	material_request can still be set on a Stock Entry Detail row for
	reasons unrelated to this feature).
	"""
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	material_request = filters.get("material_request")
	offset = cint(start) or 0
	limit = cint(page_length) or 20
	txt_lower = (txt or "").lower()

	if not material_request or not frappe.db.table_exists("Employee Request"):
		return list(
			frappe.get_all(
				"Employee",
				filters={"status": "Active"},
				or_filters={"name": ["like", f"%{txt}%"], "employee_name": ["like", f"%{txt}%"]},
				fields=["name", "employee_name"],
				limit_start=offset,
				limit_page_length=limit,
				as_list=True,
			)
		)

	rows = frappe.get_all(
		"Employee Request",
		filters={"parent": material_request, "parenttype": "Material Request"},
		fields=["employee", "employee_name", "issued_via_stock_entry"],
	)
	results = [
		(row.employee, row.employee_name)
		for row in rows
		if not row.issued_via_stock_entry
		and (txt_lower in (row.employee or "").lower() or txt_lower in (row.employee_name or "").lower())
	]
	return results[offset : offset + limit]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/david/frappe/kaitet-bench && bench --site david.local run-tests --module upande_ta.upande_ta.overrides.test_stock_entry`
Expected: both tests PASS.

Note: the `frappe.db.table_exists("Employee Request")` guard (missing-table fallback) is not covered by a dedicated test here -- `david.local` has `upande_stores` installed, so the table exists, and dropping it to simulate another environment would corrupt this site's real data. The guard mirrors an already-proven pattern elsewhere in this same file (`ensure_biometric_stock_entry_fields`'s `frappe.db.table_exists("Stock Entry")` check) rather than introducing new untested logic.

- [ ] **Step 5: Wire the query on the client side**

In `apps/upande_ta/upande_ta/public/js/stock_entry.js`, the form currently has no `setup` handler (only `refresh`, `after_save`, `requires_biometric`, `bio_employee`, ... inside the single `frappe.ui.form.on("Stock Entry", {...})` call). Add a `setup` key as the first entry in that object:

```js
frappe.ui.form.on("Stock Entry", {
	setup(frm) {
		frm.set_query("bio_employee", () => {
			const material_request = (frm.doc.items || []).find((row) => row.material_request)
				?.material_request;
			return {
				query: "upande_ta.upande_ta.overrides.stock_entry.material_request_employee_query",
				filters: { material_request: material_request || "" },
			};
		});
	},

	refresh(frm) {
		// ... existing refresh code unchanged
```

(Leave every other handler in the file exactly as-is — this only adds the new `setup` key.)

- [ ] **Step 6: Manually verify in the browser**

1. `bench --site david.local clear-cache`
2. Open a submitted "Material Issue" Material Request with at least one Employee Data row on `david.local`, click its "Create" → Stock Entry button.
3. Open the `bio_employee` ("Employee (Receiving)") dropdown — confirm it lists only that Material Request's employees, and confirm an employee already issued via a different submitted Stock Entry against the same Material Request does not appear.
4. Submit the Stock Entry, then re-open the Material Request's Employee Data grid — confirm the "Issued Via Stock Entry" column now shows this Stock Entry's name for the chosen employee.
5. Cancel that Stock Entry, re-check the grid — confirm the column is empty again.

- [ ] **Step 7: Commit**

```bash
cd /home/david/frappe/kaitet-bench/apps/upande_ta
git add upande_ta/overrides/stock_entry.py upande_ta/overrides/test_stock_entry.py public/js/stock_entry.js
git commit -m "Scope bio_employee to the linked Material Request's un-issued employees"
```
