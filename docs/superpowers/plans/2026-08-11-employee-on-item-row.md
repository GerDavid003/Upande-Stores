# Move employee allocation onto Material Request Item Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record `employee` (plus its fulfillment tracking, `qty_issued`/`issued_via_stock_entry`) directly on each Material Request Item row instead of in a separate `Employee Request` child table, and update every function/query that currently reads or writes that table to work against `items` instead.

**Architecture:** Delete the `Employee Request` doctype and the `custom_employee_data` field on Material Request entirely. Add `employee`/`employee_name`/`qty_issued`/`issued_via_stock_entry` as custom fields on `Material Request Item`. Every downstream consumer — Material Request's own validation, Stock Entry's lock/unlock logic, the two PPE Material-Request-creation functions, and `upande_ta`'s `bio_employee` picker query — gets repointed at `items` instead of the old child table. No data migration for existing documents (confirmed with the user).

**Tech Stack:** Frappe/ERPNext doctype JSON, Custom Fields, Property Setters, Python `doc_events` hooks, `frappe.tests.IntegrationTestCase`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-11-employee-on-item-row-design.md` — every task below implements a section of it.
- Apps touched: `upande_stores` (primary) and `upande_ta` (Task 5 only, the `bio_employee` picker query).
- No data migration. Existing Employee Data on any currently-open Material Request is not carried over onto the new Items-table fields.
- `mandatory_depends_on` is never enforced server-side in this Frappe version — every "required when X" rule in this plan is enforced by an explicit `validate()` hook, never by JSON alone.
- **Field-order gotcha, hit three times already on this exact codebase today**: several doctypes here (`Employee`, `Stock Entry`, and — confirmed while investigating this plan — `Material Request`, `Material Request Item`) carry a stale, hand-arranged, doctype-level `field_order` Property Setter (named `<Doctype>-main-field_order`). Frappe's sort algorithm gives a field already listed in that stored list absolute priority over its own `insert_after` — so a brand-new Custom Field's `insert_after` is silently ignored if the field it targets is one of the (many) fields already baked into that list. Every task that adds a new Custom Field on `Material Request` or `Material Request Item` must also insert the new field's name directly into that doctype's `field_order` Property Setter list, immediately after its `insert_after` target — verified live via `frappe.get_meta` afterward, not assumed.
- Test fixtures in `upande_stores` use `company="Karen Roses"`, warehouse `"Stores - KR"`, items `"_Test Item"`/`"_Test Item 2"`. Fixtures in `upande_ta`'s own test file use `company="_Test Company"` alongside a real Farm/Business Unit — this combination has already been verified safe on this site (not a new risk introduced by this plan).
- Run upande_stores tests with: `bench --site david.local run-tests --app upande_stores --module <module>`. Run upande_ta tests with: `bench --site david.local run-tests --app upande_ta --module upande_ta.upande_ta.overrides.test_stock_entry`.
- Every existing test in the files this plan touches must keep passing unless this plan's own text explicitly says a test is being replaced/renamed — these are the regression proof that the redesign didn't silently break something.

---

### Task 1: Schema — Material Request Item gains employee/qty_issued/issued_via_stock_entry; Employee Request is deleted

**Files:**
- Delete: `upande_stores/upande_stores/doctype/employee_request/` (entire folder)
- Modify: `upande_stores/upande_stores/custom/material_request.json` (remove `custom_employee_data` and `custom_employee_details` custom fields; remove the now-orphaned `Material Request-custom_employee_details-insert_after` property setter; fix the `Material Request-main-field_order` property setter)
- Modify: `upande_stores/upande_stores/custom/material_request_item.json` (add 4 new custom fields; add a new `Material Request Item-main-field_order` property setter)
- Modify: `upande_stores/upande_stores/tests/test_helpers.py` (rewrite `make_material_request`)

**Interfaces:**
- Produces: `Material Request Item.employee` (Link → Employee, optional), `.employee_name` (Data, read-only, `fetch_from: employee.employee_name`), `.qty_issued` (Float, read-only, default 0), `.issued_via_stock_entry` (Link → Stock Entry, read-only). Consumed by every later task.
- Produces: `upande_stores.tests.test_helpers.make_material_request(items=None, material_request_type="Material Issue") -> Document`, replacing the old `employee_rows=`/`qty=`/`item_code=` signature. `items` is a list of dicts, each becoming one row in `doc.items` directly — e.g. `{"employee": <name>}` (defaults to `item_code="_Test Item"`, `qty=1`) or `{"employee": <name>, "item_code": ..., "qty": ...}` for a specific allocation, or `{"item_code": ..., "qty": ...}` with no `employee` at all.

- [ ] **Step 1: Delete the Employee Request doctype's source files**

```bash
rm -rf upande_stores/upande_stores/doctype/employee_request
```

- [ ] **Step 2: Remove custom_employee_data / custom_employee_details from the Material Request fixture**

Open `upande_stores/upande_stores/custom/material_request.json`. Remove the two `custom_fields` array entries whose `"fieldname"` is `"custom_employee_data"` and `"custom_employee_details"` (delete each entire `{...}` object, including its trailing comma if it's not the last entry). Remove the one `property_setters` array entry whose `"name"` is `"Material Request-custom_employee_details-insert_after"` (added earlier today, now orphaned — its target field no longer exists).

- [ ] **Step 3: Add the 4 new fields to the Material Request Item fixture**

Open `upande_stores/upande_stores/custom/material_request_item.json`. Add to its `custom_fields` array (it's currently `[]`):

```json
{
 "_assign": null,
 "_comments": null,
 "_liked_by": null,
 "_user_tags": null,
 "creation": "2026-08-11 00:00:00.000000",
 "default": null,
 "depends_on": null,
 "description": null,
 "docstatus": 0,
 "dt": "Material Request Item",
 "fetch_from": null,
 "fetch_if_empty": 0,
 "fieldname": "employee",
 "fieldtype": "Link",
 "hidden": 0,
 "hide_border": 0,
 "hide_days": 0,
 "hide_seconds": 0,
 "idx": 0,
 "ignore_user_permissions": 0,
 "ignore_xss_filter": 0,
 "in_global_search": 0,
 "in_list_view": 1,
 "in_preview": 0,
 "in_standard_filter": 0,
 "insert_after": "item_code",
 "is_system_generated": 0,
 "is_virtual": 0,
 "label": "Employee",
 "length": 0,
 "link_filters": null,
 "mandatory_depends_on": null,
 "mask": 0,
 "modified": "2026-08-11 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Upande Stores",
 "name": "Material Request Item-employee",
 "no_copy": 0,
 "non_negative": 0,
 "options": "Employee",
 "owner": "Administrator",
 "permlevel": 0,
 "placeholder": null,
 "precision": "",
 "print_hide": 0,
 "print_hide_if_no_value": 0,
 "print_width": null,
 "read_only": 0,
 "read_only_depends_on": null,
 "report_hide": 0,
 "reqd": 0,
 "search_index": 0,
 "set_only_once": 0,
 "show_dashboard": 0,
 "sort_options": 0,
 "translatable": 0,
 "unique": 0,
 "width": null
},
{
 "_assign": null,
 "_comments": null,
 "_liked_by": null,
 "_user_tags": null,
 "creation": "2026-08-11 00:00:00.000000",
 "default": null,
 "depends_on": null,
 "description": null,
 "docstatus": 0,
 "dt": "Material Request Item",
 "fetch_from": "employee.employee_name",
 "fetch_if_empty": 0,
 "fieldname": "employee_name",
 "fieldtype": "Data",
 "hidden": 0,
 "hide_border": 0,
 "hide_days": 0,
 "hide_seconds": 0,
 "idx": 0,
 "ignore_user_permissions": 0,
 "ignore_xss_filter": 0,
 "in_global_search": 0,
 "in_list_view": 0,
 "in_preview": 0,
 "in_standard_filter": 0,
 "insert_after": "employee",
 "is_system_generated": 0,
 "is_virtual": 0,
 "label": "Employee Name",
 "length": 0,
 "link_filters": null,
 "mandatory_depends_on": null,
 "mask": 0,
 "modified": "2026-08-11 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Upande Stores",
 "name": "Material Request Item-employee_name",
 "no_copy": 0,
 "non_negative": 0,
 "options": null,
 "owner": "Administrator",
 "permlevel": 0,
 "placeholder": null,
 "precision": "",
 "print_hide": 0,
 "print_hide_if_no_value": 0,
 "print_width": null,
 "read_only": 1,
 "read_only_depends_on": null,
 "report_hide": 0,
 "reqd": 0,
 "search_index": 0,
 "set_only_once": 0,
 "show_dashboard": 0,
 "sort_options": 0,
 "translatable": 0,
 "unique": 0,
 "width": null
},
{
 "_assign": null,
 "_comments": null,
 "_liked_by": null,
 "_user_tags": null,
 "creation": "2026-08-11 00:00:00.000000",
 "default": "0",
 "depends_on": null,
 "description": null,
 "docstatus": 0,
 "dt": "Material Request Item",
 "fetch_from": null,
 "fetch_if_empty": 0,
 "fieldname": "qty_issued",
 "fieldtype": "Float",
 "hidden": 0,
 "hide_border": 0,
 "hide_days": 0,
 "hide_seconds": 0,
 "idx": 0,
 "ignore_user_permissions": 0,
 "ignore_xss_filter": 0,
 "in_global_search": 0,
 "in_list_view": 1,
 "in_preview": 0,
 "in_standard_filter": 0,
 "insert_after": "employee_name",
 "is_system_generated": 0,
 "is_virtual": 0,
 "label": "Qty Issued",
 "length": 0,
 "link_filters": null,
 "mandatory_depends_on": null,
 "mask": 0,
 "modified": "2026-08-11 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Upande Stores",
 "name": "Material Request Item-qty_issued",
 "no_copy": 0,
 "non_negative": 0,
 "options": null,
 "owner": "Administrator",
 "permlevel": 0,
 "placeholder": null,
 "precision": "",
 "print_hide": 0,
 "print_hide_if_no_value": 0,
 "print_width": null,
 "read_only": 1,
 "read_only_depends_on": null,
 "report_hide": 0,
 "reqd": 0,
 "search_index": 0,
 "set_only_once": 0,
 "show_dashboard": 0,
 "sort_options": 0,
 "translatable": 0,
 "unique": 0,
 "width": null
},
{
 "_assign": null,
 "_comments": null,
 "_liked_by": null,
 "_user_tags": null,
 "creation": "2026-08-11 00:00:00.000000",
 "default": null,
 "depends_on": null,
 "description": null,
 "docstatus": 0,
 "dt": "Material Request Item",
 "fetch_from": null,
 "fetch_if_empty": 0,
 "fieldname": "issued_via_stock_entry",
 "fieldtype": "Link",
 "hidden": 0,
 "hide_border": 0,
 "hide_days": 0,
 "hide_seconds": 0,
 "idx": 0,
 "ignore_user_permissions": 0,
 "ignore_xss_filter": 0,
 "in_global_search": 0,
 "in_list_view": 0,
 "in_preview": 0,
 "in_standard_filter": 0,
 "insert_after": "qty_issued",
 "is_system_generated": 0,
 "is_virtual": 0,
 "label": "Issued Via Stock Entry",
 "length": 0,
 "link_filters": null,
 "mandatory_depends_on": null,
 "mask": 0,
 "modified": "2026-08-11 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Upande Stores",
 "name": "Material Request Item-issued_via_stock_entry",
 "no_copy": 0,
 "non_negative": 0,
 "options": "Stock Entry",
 "owner": "Administrator",
 "permlevel": 0,
 "placeholder": null,
 "precision": "",
 "print_hide": 0,
 "print_hide_if_no_value": 0,
 "print_width": null,
 "read_only": 1,
 "read_only_depends_on": null,
 "report_hide": 0,
 "reqd": 0,
 "search_index": 0,
 "set_only_once": 0,
 "show_dashboard": 0,
 "sort_options": 0,
 "translatable": 0,
 "unique": 0,
 "width": null
}
```

- [ ] **Step 4: Migrate**

Run: `bench --site david.local migrate`
Expected: completes with no errors. This creates the 4 new columns on `tabMaterial Request Item`, drops `custom_employee_data`/`custom_employee_details` from `Material Request`, and — per `migrate`'s own "Removing orphan doctypes" step — drops the `Employee Request` DocType record. It will likely **not** drop the underlying `tabEmployee Request` table (this exact gap was hit earlier today on a different doctype) — check and drop it explicitly if it's still there:

```bash
bench --site david.local execute frappe.db.table_exists --args '["Employee Request"]'
```

If that prints `True`, drop it directly:

```bash
bench --site david.local execute frappe.db.sql --args '["DROP TABLE IF EXISTS `tabEmployee Request`"]'
```

- [ ] **Step 5: Fix the two field_order Property Setters**

Both `Material Request` and `Material Request Item` have a stale, hand-arranged `<Doctype>-main-field_order` Property Setter (confirmed live on this site). Fix both via `bench --site david.local console`:

```python
import json

# Material Request: remove the two deleted fields from its field_order list.
ps = frappe.get_doc("Property Setter", "Material Request-main-field_order")
fo = json.loads(ps.value)
fo = [f for f in fo if f not in ("custom_employee_data", "custom_employee_details")]
ps.value = json.dumps(fo)
ps.save(ignore_permissions=True)

# Material Request Item: insert the 4 new fields right after item_code.
ps2 = frappe.get_doc("Property Setter", "Material Request Item-main-field_order")
fo2 = json.loads(ps2.value)
i = fo2.index("item_code")
for j, fieldname in enumerate(["employee", "employee_name", "qty_issued", "issued_via_stock_entry"]):
    fo2.insert(i + 1 + j, fieldname)
ps2.value = json.dumps(fo2)
ps2.save(ignore_permissions=True)

frappe.db.commit()
```

Then write both corrected `value` strings into `custom/material_request.json`'s and `custom/material_request_item.json`'s own `property_setters` arrays as new entries (mirroring the exact shape already used for `Employee-main-field_order`/`Stock Entry-main-field_order` in this codebase's history — `doc_type`, `doctype_or_field: "DocType"`, `field_name: null`, `property: "field_order"`, `property_type: "Data"`, `module: "Upande Stores"`), so the fix reproduces on any other site via migrate. Fetch each corrected value via:

```python
print(frappe.db.get_value("Property Setter", "Material Request-main-field_order", "value"))
print(frappe.db.get_value("Property Setter", "Material Request Item-main-field_order", "value"))
```

and paste each resulting JSON string as the `value` of its new entry.

- [ ] **Step 6: Verify live**

```bash
bench --site david.local clear-cache
bench --site david.local execute frappe.get_meta --args '["Material Request Item"]' 2>/dev/null | tail -1 > /tmp/mri_meta.json
python3 -c "
import json
d = json.loads(open('/tmp/mri_meta.json').read())
names = [f['fieldname'] for f in d['fields']]
i = names.index('item_code')
print(names[i:i+6])
"
```
Expected: `['item_code', 'employee', 'employee_name', 'qty_issued', 'issued_via_stock_entry', 'item_name']` (or whatever real field used to sit right after `item_code`, now pushed one further).

```bash
bench --site david.local execute frappe.db.exists --args '["DocType", "Employee Request"]'
bench --site david.local execute frappe.db.exists --args '["Custom Field", "Material Request-custom_employee_data"]'
```
Both expected: empty (falsy).

- [ ] **Step 7: Re-migrate to confirm the fixture reproduces idempotently**

```bash
bench --site david.local migrate
```
Expected: completes with no errors, and Step 6's checks still pass afterward.

- [ ] **Step 8: Rewrite the test helper**

In `upande_stores/upande_stores/tests/test_helpers.py`, replace `make_material_request`:

```python
def make_material_request(employee_rows=None, qty=1, item_code="_Test Item"):
	"""Create and insert a minimal submitted-ready 'Material Issue' Material
	Request. employee_rows is a list of dicts (e.g. {"employee": <name>}
	or {"employee": <name>, "issued_via_stock_entry": "STE-0001"}), appended
	to custom_employee_data as-is. qty defaults to 1; pass a higher value
	when a test needs to issue against the same Material Request more than
	once without tripping ERPNext's own "can't over-issue" guard before the
	code under test gets a chance to run. item_code defaults to "_Test Item";
	pass a specific item (e.g. a PPE item from make_ppe_item) when a caller's
	Stock Entry needs to reference this Material Request's item row -- ERPNext
	rejects a Stock Entry row whose item_code doesn't match the Material
	Request Item it points at via material_request_item.
	"""
	farm, business_unit = get_test_farm_and_business_unit()
	mr = frappe.get_doc(
		{
			"doctype": "Material Request",
			"material_request_type": "Material Issue",
			"transaction_date": today(),
			"company": "Karen Roses",
			"custom_farm": farm,
			"custom_business_unit": business_unit,
			"items": [
				{
					"item_code": item_code,
					"qty": qty,
					"uom": "_Test UOM",
					"stock_uom": "_Test UOM",
					"conversion_factor": 1,
					"schedule_date": today(),
					"warehouse": "Stores - KR",
					# Material Request Item's "Purpose" (description) field is
					# mandatory site-wide via a real Property Setter. ERPNext's
					# own item-defaults fetch normally back-fills it from the
					# Item master's description, but "_Test Item" is the only
					# item in this codebase's fixtures that happens to have one
					# set -- any other item_code (e.g. a PPE item from
					# make_ppe_item, which has none) would otherwise trip that
					# mandatory check. Setting it explicitly here covers every
					# item_code, not just the default.
					"description": item_code,
				}
			],
		}
	)
	for row in employee_rows or []:
		mr.append("custom_employee_data", row)
	mr.insert(ignore_permissions=True)
	return mr
```

with:

```python
def make_material_request(items=None, material_request_type="Material Issue"):
	"""Create and insert a minimal submitted-ready Material Request.

	`items` is a list of dicts, each becoming one row in the standard Items
	table directly -- e.g. {"employee": <name>} (defaults to
	item_code="_Test Item", qty=1) or {"employee": <name>, "item_code": ...,
	"qty": ...} for a specific allocation, or {"item_code": ..., "qty": ...}
	with no employee at all. Defaults to material_request_type="Material
	Issue" (this app's primary use case, where every row needs an employee);
	pass "Material Transfer" for tests that need employee to stay optional.

	Each row's item_code/qty/uom/stock_uom/conversion_factor/warehouse
	default the same way the old single-hardcoded-row version did --
	callers only need to specify what's different from that default.
	Material Request Item's "Purpose" (description) field is mandatory
	site-wide via a real Property Setter; ERPNext's own item-defaults fetch
	normally back-fills it from the Item master's description, but
	"_Test Item"/"_Test Item 2" are the only items in this codebase's
	fixtures that happen to have one set, so it's defaulted here explicitly
	to cover any other item_code (e.g. a PPE item from make_ppe_item, which
	has none) too.
	"""
	farm, business_unit = get_test_farm_and_business_unit()
	mr = frappe.get_doc(
		{
			"doctype": "Material Request",
			"material_request_type": material_request_type,
			"transaction_date": today(),
			"company": "Karen Roses",
			"custom_farm": farm,
			"custom_business_unit": business_unit,
		}
	)
	for row in items or []:
		item_code = row.get("item_code", "_Test Item")
		defaults = {
			"item_code": item_code,
			"qty": 1,
			"uom": "_Test UOM",
			"stock_uom": "_Test UOM",
			"conversion_factor": 1,
			"schedule_date": today(),
			"warehouse": "Stores - KR",
			"description": item_code,
		}
		defaults.update(row)
		mr.append("items", defaults)
	mr.insert(ignore_permissions=True)
	return mr
```

- [ ] **Step 9: Commit**

```bash
git add upande_stores/upande_stores/custom/material_request.json upande_stores/upande_stores/custom/material_request_item.json upande_stores/upande_stores/tests/test_helpers.py
git status --short  # confirm the deleted doctype/employee_request folder shows as deleted
git add upande_stores/upande_stores/doctype/employee_request
git commit -m "feat: move employee allocation fields onto Material Request Item, delete Employee Request"
```

Do not run the test suite yet — `test_material_request.py`/`test_stock_entry.py` still reference the old `employee_rows=`/`custom_employee_data` shape and will only be fixed in Tasks 2-3. This task's own verification is Steps 6-7 (live schema checks), not pytest.

---

### Task 2: Material Request validation — employee lives on items, not a separate table

**Files:**
- Modify: `upande_stores/overrides/material_request.py` (replace `validate_employee_data_required_for_material_issue` and `validate_employee_allocations`; delete `sync_employee_allocations_to_items`)
- Modify: `upande_stores/hooks.py` (update the `Material Request` `validate` list)
- Modify: `upande_stores/overrides/test_material_request.py` (replace the employee-related test classes)

**Interfaces:**
- Consumes: `Material Request Item.employee`/`qty_issued`/`issued_via_stock_entry` (Task 1); `upande_stores.tests.test_helpers.make_material_request(items=None, material_request_type="Material Issue")` (Task 1).
- Produces: `upande_stores.overrides.material_request.validate_employee_required_for_material_issue(doc, method=None) -> None`, `upande_stores.overrides.material_request.validate_employee_allocations(doc, method=None) -> None` (same name as before, new implementation — repointed at `doc.items`).

- [ ] **Step 1: Write the failing tests**

Replace the entire contents of `upande_stores/overrides/test_material_request.py`'s employee-related classes. Read the current file first — it has 5 classes:
`IntegrationTestMaterialRequestEmployeeValidation`, `IntegrationTestMaterialRequestPPEUnlink`, `IntegrationTestMaterialRequestEmployeeMandatory`, `IntegrationTestMaterialRequestAccountingDimensionSync`, `IntegrationTestMaterialRequestAllocationItemSync`.

`IntegrationTestMaterialRequestPPEUnlink` also needs updating — it builds two Material Request dicts inline with `"custom_employee_data": [{"employee": self.employee}]"`, handled separately in Step 2 below.

Delete `IntegrationTestMaterialRequestAllocationItemSync` entirely (it tested `sync_employee_allocations_to_items`, which no longer exists — there's nothing left to derive). Rewrite `IntegrationTestMaterialRequestAccountingDimensionSync`'s one test to use the new helper signature.

Replace `IntegrationTestMaterialRequestEmployeeValidation` and `IntegrationTestMaterialRequestEmployeeMandatory` with:

```python
class IntegrationTestMaterialRequestEmployeeAllocations(IntegrationTestCase):
	def setUp(self):
		farm, business_unit = get_test_farm_and_business_unit()
		if not farm or not business_unit:
			self.skipTest("No Farm/Business Unit record on this site to build a valid test Material Request.")
		self.employees = get_test_employees(count=2)
		if len(self.employees) < 2:
			self.skipTest("Need at least 2 Active Employee records on this site.")

	def test_material_issue_requires_employee_on_every_row(self):
		with self.assertRaises(frappe.ValidationError):
			make_material_request(items=[{"item_code": "_Test Item", "qty": 1}])

	def test_material_issue_with_employee_on_every_row_succeeds(self):
		emp = self.employees[0]
		mr = make_material_request(items=[{"employee": emp, "item_code": "_Test Item", "qty": 1}])
		self.assertEqual(mr.items[0].employee, emp)

	def test_material_issue_requires_employee_on_every_row_even_if_one_has_it(self):
		emp = self.employees[0]
		with self.assertRaises(frappe.ValidationError):
			make_material_request(
				items=[
					{"employee": emp, "item_code": "_Test Item", "qty": 1},
					{"item_code": "_Test Item 2", "qty": 1},
				]
			)

	def test_material_transfer_does_not_require_employee(self):
		mr = make_material_request(
			items=[{"item_code": "_Test Item", "qty": 1}],
			material_request_type="Material Transfer",
		)
		self.assertFalse(mr.items[0].employee)  # must not raise

	def test_allows_same_employee_with_different_items(self):
		emp = self.employees[0]
		mr = make_material_request(
			items=[
				{"employee": emp, "item_code": "_Test Item", "qty": 5},
				{"employee": emp, "item_code": "_Test Item 2", "qty": 3},
			]
		)
		self.assertEqual(len(mr.items), 2)

	def test_rejects_duplicate_employee_and_item_pair(self):
		emp = self.employees[0]
		with self.assertRaises(frappe.ValidationError):
			make_material_request(
				items=[
					{"employee": emp, "item_code": "_Test Item", "qty": 5},
					{"employee": emp, "item_code": "_Test Item", "qty": 3},
				]
			)

	def test_allows_duplicate_item_when_employee_is_blank_on_both(self):
		mr = make_material_request(
			items=[
				{"item_code": "_Test Item", "qty": 5},
				{"item_code": "_Test Item", "qty": 3},
			],
			material_request_type="Material Transfer",
		)
		self.assertEqual(len(mr.items), 2)  # must not raise
```

- [ ] **Step 2: Update the two inline dicts in IntegrationTestMaterialRequestPPEUnlink**

In `upande_stores/overrides/test_material_request.py`'s `IntegrationTestMaterialRequestPPEUnlink` class, both `test_cancel_clears_the_replacement_lock` and `test_non_ppe_material_request_cancel_is_a_noop` build a Material Request dict inline with:

```python
				"custom_employee_data": [{"employee": self.employee}],
				"items": [
					{
						"item_code": "_Test Item",
						"qty": 1,
						"uom": "_Test UOM",
						"stock_uom": "_Test UOM",
						"conversion_factor": 1,
						"schedule_date": frappe.utils.today(),
						"warehouse": "Stores - KR",
					}
				],
```

Replace with (drop the `custom_employee_data` key, add `"employee": self.employee` to the one item row):

```python
				"items": [
					{
						"item_code": "_Test Item",
						"qty": 1,
						"uom": "_Test UOM",
						"stock_uom": "_Test UOM",
						"conversion_factor": 1,
						"schedule_date": frappe.utils.today(),
						"warehouse": "Stores - KR",
						"employee": self.employee,
					}
				],
```

in both test methods.

- [ ] **Step 3: Rewrite IntegrationTestMaterialRequestAccountingDimensionSync, delete IntegrationTestMaterialRequestAllocationItemSync**

Replace:

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

with:

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
		mr = make_material_request(items=[{"employee": self.employee}])
		self.assertTrue(mr.custom_farm)
		self.assertTrue(mr.custom_business_unit)
		for row in mr.items:
			self.assertEqual(row.farm, mr.custom_farm)
			self.assertEqual(row.business_unit, mr.custom_business_unit)
```

Delete the entire `IntegrationTestMaterialRequestAllocationItemSync` class (its 4 tests: `test_items_table_is_derived_from_employee_allocations`, `test_allocations_for_the_same_item_are_summed`, `test_blank_item_code_rows_leave_items_table_untouched`, `test_derived_item_row_carries_forward_an_existing_warehouse`) — all test `sync_employee_allocations_to_items`, which this task removes; there is no replacement, since there's no longer a separate table to derive `items` from.

- [ ] **Step 4: Run tests to verify they fail**

Run: `bench --site david.local run-tests --app upande_stores --module upande_stores.overrides.test_material_request`
Expected: multiple failures/errors — `validate_employee_required_for_material_issue` doesn't exist yet, `make_material_request`'s new `items=`/`material_request_type=` signature doesn't match the still-old implementation's `employee_rows=`/`qty=`/`item_code=` signature from before Task 1... **actually Task 1 already rewrote the helper** — so at this point the helper accepts `items=`, but `validate_employee_allocations` still reads `doc.get("custom_employee_data")` (a field that Task 1 already deleted from the doctype) instead of `doc.items`, so every call fails with an `AttributeError`/silently no-ops incorrectly. Confirm the failures are all attributable to this task's not-yet-updated functions, not to Task 1.

- [ ] **Step 5: Replace the implementation**

In `upande_stores/overrides/material_request.py`, replace:

```python
def validate_employee_data_required_for_material_issue(doc, method=None):
	"""Material Request validate hook: a Material Issue request must have at
	least one row in custom_employee_data.

	custom_employee_data's mandatory_depends_on (see custom/material_request.json)
	only drives the Desk form's client-side "reqd" behaviour -- Frappe does not
	re-evaluate mandatory_depends_on server-side when a document is inserted
	via the API (frappe.model.base_document.BaseDocument._get_missing_mandatory_fields
	only looks at the field's static reqd flag), so a Material Issue with zero
	employee rows can still be inserted with doc.insert(ignore_permissions=True)
	unless this hook blocks it explicitly.
	"""
	if doc.material_request_type == "Material Issue" and not doc.get("custom_employee_data"):
		frappe.throw(_("At least one row is required in Employee Data for a Material Issue request."))


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

	# Freshly created rows skipped ERPNext's own defaulting pass (that already
	# ran, on the OLD items, before this hook fired) -- re-run it now so any
	# site-level mandatory Material Request Item field this function doesn't
	# know how to compute itself (e.g. expense_account) gets resolved the same
	# way it would for a manually-entered row. Fills any field that's still
	# blank (leaving qty/description/uom/conversion_factor/warehouse alone,
	# since we already set those above) except its own hardcoded
	# force_item_fields list -- stock_uom is the only one of those we also
	# set, and it's harmless here since both resolve to the same Item master
	# value.
	doc.set_missing_values(for_validate=True)
```

with:

```python
def validate_employee_required_for_material_issue(doc, method=None):
	"""Material Request validate hook: when material_request_type is
	"Material Issue", every item row must have employee set -- a Material
	Issue request is always issuing specific items to specific people, so a
	row with a blank employee on that request type is a data-entry mistake,
	not a valid case. Other request types (Material Transfer, Purchase,
	...) leave employee fully optional.

	Enforced here rather than via reqd/mandatory_depends_on -- the latter
	is never enforced server-side in this Frappe version
	(frappe.model.base_document.BaseDocument._get_missing_mandatory_fields
	only ever checks the static reqd flag).
	"""
	if doc.material_request_type != "Material Issue":
		return
	for row in doc.items:
		if not row.employee:
			frappe.throw(_("Row {0}: Employee is required for a Material Issue request.").format(row.idx))


def validate_employee_allocations(doc, method=None):
	"""Material Request validate hook: no two item rows may share the same
	(employee, item_code) pair when employee is set on both. Runs on every
	save (not just once), so a duplicate can't be introduced after the fact
	-- protects the Stock Entry lock/unlock logic
	(lock_issued_employee/unlock_issued_employee), which would otherwise
	have an ambiguous row to match against.

	Rows with a blank employee are unconstrained against each other --
	ordinary bulk items (no per-employee attribution) can repeat item_code
	freely.
	"""
	seen = set()
	for row in doc.items:
		if not row.employee:
			continue
		key = (row.employee, row.item_code)
		if key in seen:
			frappe.throw(
				_("Employee {0} appears more than once for Item {1}.").format(
					frappe.bold(row.employee), frappe.bold(row.item_code)
				)
			)
		seen.add(key)
```

In `upande_stores/hooks.py`, replace the `Material Request` `validate` list:

```python
		"validate": [
			"upande_stores.overrides.material_request.validate_employee_data_required_for_material_issue",
			"upande_stores.overrides.material_request.validate_employee_allocations",
			"upande_stores.overrides.material_request.sync_employee_allocations_to_items",
			"upande_stores.overrides.material_request.sync_accounting_dimensions_to_items",
		],
```

with:

```python
		"validate": [
			"upande_stores.overrides.material_request.validate_employee_required_for_material_issue",
			"upande_stores.overrides.material_request.validate_employee_allocations",
			"upande_stores.overrides.material_request.sync_accounting_dimensions_to_items",
		],
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `bench --site david.local run-tests --app upande_stores --module upande_stores.overrides.test_material_request`
Expected: all tests pass — the new `IntegrationTestMaterialRequestEmployeeAllocations` class, the updated `IntegrationTestMaterialRequestPPEUnlink`/`IntegrationTestMaterialRequestAccountingDimensionSync`, and nothing left over from the deleted `IntegrationTestMaterialRequestAllocationItemSync`.

- [ ] **Step 7: Commit**

```bash
git add upande_stores/overrides/material_request.py upande_stores/hooks.py upande_stores/overrides/test_material_request.py
git commit -m "feat: validate employee allocations directly on Material Request items, drop the derivation hook"
```

---

### Task 3: Stock Entry lock/unlock — match against Material Request Item, not Employee Request

**Files:**
- Modify: `upande_stores/overrides/stock_entry.py` (replace `_find_employee_request_row`, `lock_issued_employee`, `unlock_issued_employee`)
- Modify: `upande_stores/overrides/test_stock_entry.py` (replace `IntegrationTestStockEntryEmployeeLock` and `IntegrationTestStockEntryPerItemAllocationLock`; update 2 other tests' fixture calls)

**Interfaces:**
- Consumes: `Material Request Item.employee`/`qty_issued`/`issued_via_stock_entry` (Task 1); `make_material_request(items=None, material_request_type="Material Issue")` (Task 1).
- Produces: `upande_stores.overrides.stock_entry._find_allocation_row(material_request, employee, item_code) -> dict | None`, replacing `_find_employee_request_row`.

- [ ] **Step 1: Write the failing tests**

In `upande_stores/overrides/test_stock_entry.py`, replace `IntegrationTestStockEntryEmployeeLock`:

```python
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
		mr = make_material_request(items=[{"employee": self.employee}])
		se = make_stock_entry_for_material_request(mr, bio_employee=self.employee)
		se.submit()

		self.assertEqual(
			frappe.db.get_value("Material Request Item", mr.items[0].name, "issued_via_stock_entry"),
			se.name,
		)

	def test_cancel_unlocks_the_employee_request_row(self):
		mr = make_material_request(items=[{"employee": self.employee}])
		se = make_stock_entry_for_material_request(mr, bio_employee=self.employee)
		se.submit()
		se.cancel()

		self.assertFalse(
			frappe.db.get_value("Material Request Item", mr.items[0].name, "issued_via_stock_entry")
		)

	def test_second_submit_for_already_issued_employee_is_blocked(self):
		# qty=2 on the Material Request against two qty=1 Stock Entries (1+1=2,
		# not >2) keeps ERPNext's own "can't over-issue against a Material
		# Request" guard from firing first -- it would otherwise mask whether
		# lock_issued_employee's own check is what's actually blocking this.
		mr = make_material_request(items=[{"employee": self.employee, "qty": 2}])
		first = make_stock_entry_for_material_request(mr, bio_employee=self.employee)
		first.submit()

		second = make_stock_entry_for_material_request(mr, bio_employee=self.employee)
		with self.assertRaises(frappe.ValidationError):
			second.submit()

	def test_stock_entry_without_material_request_is_a_noop(self):
		se = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"purpose": "Material Issue",
				"stock_entry_type": "Material Issue",
				"company": "_Test Company",
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

Note the only real changes from the pre-existing version: `make_material_request(employee_rows=[{"employee": self.employee}])` → `make_material_request(items=[{"employee": self.employee}])` (and `qty=2` moved from a top-level kwarg into the row dict), and the assertions read `Material Request Item.issued_via_stock_entry` directly (via `mr.items[0].name`) instead of looking up an `Employee Request` row by `{"parent": mr.name, "employee": ...}`.

Replace `IntegrationTestStockEntryPerItemAllocationLock`:

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

	def _allocation_row(self, mr, item_code="_Test Item"):
		return frappe.db.get_value(
			"Material Request Item",
			{"parent": mr.name, "employee": self.employee, "item_code": item_code},
			["name", "qty", "qty_issued", "issued_via_stock_entry"],
			as_dict=True,
		)

	def test_partial_issuance_does_not_lock_the_employee(self):
		mr = make_material_request(items=[{"employee": self.employee, "item_code": "_Test Item", "qty": 10}])
		se = make_stock_entry_for_material_request(mr, bio_employee=self.employee, qty=3)
		se.submit()

		row = self._allocation_row(mr)
		self.assertEqual(row.qty_issued, 3)
		self.assertFalse(row.issued_via_stock_entry)

	def test_second_partial_issuance_completes_and_locks(self):
		mr = make_material_request(items=[{"employee": self.employee, "item_code": "_Test Item", "qty": 10}])
		first = make_stock_entry_for_material_request(mr, bio_employee=self.employee, qty=3)
		first.submit()

		second = make_stock_entry_for_material_request(mr, bio_employee=self.employee, qty=7)
		second.submit()

		row = self._allocation_row(mr)
		self.assertEqual(row.qty_issued, 10)
		self.assertEqual(row.issued_via_stock_entry, second.name)

	def test_issuance_after_full_satisfaction_is_blocked(self):
		mr = make_material_request(items=[{"employee": self.employee, "item_code": "_Test Item", "qty": 5}])
		first = make_stock_entry_for_material_request(mr, bio_employee=self.employee, qty=5)
		first.submit()

		second = make_stock_entry_for_material_request(mr, bio_employee=self.employee, qty=1)
		with self.assertRaises(frappe.ValidationError):
			second.submit()

	def test_cancelling_a_partial_issuance_reduces_qty_issued(self):
		mr = make_material_request(items=[{"employee": self.employee, "item_code": "_Test Item", "qty": 10}])
		se = make_stock_entry_for_material_request(mr, bio_employee=self.employee, qty=3)
		se.submit()
		se.cancel()

		row = self._allocation_row(mr)
		self.assertEqual(row.qty_issued, 0)
		self.assertFalse(row.issued_via_stock_entry)

	def test_cancelling_a_contributing_issuance_reopens_a_locked_employee(self):
		mr = make_material_request(items=[{"employee": self.employee, "item_code": "_Test Item", "qty": 10}])
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
			items=[
				{"employee": emp, "item_code": "_Test Item", "qty": 5},
				{"employee": emp, "item_code": "_Test Item 2", "qty": 2},
			]
		)
		se = make_stock_entry_for_material_request(mr, bio_employee=emp, item_code="_Test Item", qty=5)
		se.submit()

		locked_row = self._allocation_row(mr, item_code="_Test Item")
		open_row = self._allocation_row(mr, item_code="_Test Item 2")
		self.assertEqual(locked_row.qty_issued, 5)
		self.assertEqual(locked_row.issued_via_stock_entry, se.name)
		self.assertEqual(open_row.qty_issued, 0)
		self.assertFalse(open_row.issued_via_stock_entry)

	def test_issuing_to_an_employee_without_a_matching_allocation_is_blocked(self):
		emp1, emp2 = self.employees
		mr = make_material_request(
			items=[
				{"employee": emp1, "item_code": "_Test Item", "qty": 10},
				{"employee": emp2, "item_code": "_Test Item 2", "qty": 5},
			]
		)
		se = make_stock_entry_for_material_request(mr, bio_employee=emp2, item_code="_Test Item", qty=3)
		with self.assertRaises(frappe.ValidationError):
			se.submit()

	def test_issuing_to_an_employee_with_no_allocation_at_all_is_blocked(self):
		emp1, emp2 = self.employees
		mr = make_material_request(items=[{"employee": emp1, "item_code": "_Test Item", "qty": 10}])
		se = make_stock_entry_for_material_request(mr, bio_employee=emp2, item_code="_Test Item", qty=3)
		with self.assertRaises(frappe.ValidationError):
			se.submit()
```

Elsewhere in the same file, `IntegrationTestStockEntryAccountingDimensionInheritance` and `IntegrationTestStockEntryPPEAssignmentAccountingDimensions` both call `make_material_request(employee_rows=[{"employee": self.employee}])` (once each) and `make_material_request(employee_rows=[{"employee": self.employee}], item_code=item_code)` (once). Update these two call sites to the new signature: `make_material_request(items=[{"employee": self.employee}])` and `make_material_request(items=[{"employee": self.employee, "item_code": item_code}])` respectively.

- [ ] **Step 2: Run tests to verify they fail**

Run: `bench --site david.local run-tests --app upande_stores --module upande_stores.overrides.test_stock_entry`
Expected: failures/errors throughout this module — `_find_employee_request_row` still queries the (now-deleted) `Employee Request` doctype, so every test that submits a Stock Entry against an employee-allocated Material Request fails.

- [ ] **Step 3: Replace the implementation**

In `upande_stores/overrides/stock_entry.py`, replace `_find_employee_request_row`, `lock_issued_employee`, and `unlock_issued_employee` (keep `_resolve_material_request` as-is):

```python
def _find_allocation_row(material_request, employee, item_code):
	"""Match the Material Request Item row a Stock Entry item row fulfils:
	first by (material_request, item_code, employee) -- the row allocated
	to exactly this employee -- and if no such row exists, fall back to a
	row with the same item_code and a blank employee (no per-employee
	attribution at all; only reachable for non-Material-Issue request
	types, since Material Issue requires employee on every row). Locks the
	matched row for update so concurrent submits/cancels against the same
	allocation serialize instead of racing on a stale read.
	"""
	fields = ["name", "employee", "qty", "qty_issued", "issued_via_stock_entry"]
	row = frappe.db.get_value(
		"Material Request Item",
		{
			"parent": material_request,
			"parenttype": "Material Request",
			"item_code": item_code,
			"employee": employee,
		},
		fields,
		as_dict=True,
		for_update=True,
	)
	if row:
		return row
	return frappe.db.get_value(
		"Material Request Item",
		{
			"parent": material_request,
			"parenttype": "Material Request",
			"item_code": item_code,
			# An unset Link field lands in the DB as NULL, not "" -- match
			# both so this fallback finds a genuinely-blank-employee row
			# regardless of which representation is stored.
			"employee": ["in", ["", None]],
		},
		fields,
		as_dict=True,
		for_update=True,
	)


def lock_issued_employee(doc, method=None):
	"""Stock Entry on_submit: for each of this Stock Entry's item rows, find
	the Material Request Item row it fulfils and record the issuance
	against it directly on that row.

	Row has employee matching doc.bio_employee: qty_issued accumulates
	across Stock Entries; the row only locks (drops out of upande_ta's
	bio_employee query, via issued_via_stock_entry) once qty_issued reaches
	qty, so a partial issuance leaves the employee selectable for a
	follow-up entry. Throws if this allocation was already fully satisfied
	before this Stock Entry. Does not cap how much a single Stock Entry may
	issue against an allocation -- overshooting the remaining quantity
	simply locks the row as satisfied; validating that is out of scope.

	Row has no employee at all (blank -- only possible for non-Material-
	Issue request types): not tracked, no-op.

	No-ops if there's no Material Request context or no bio_employee set.
	Throws if every Material Request Item row with this item_code has some
	other, specific employee set -- i.e. doc.bio_employee was never
	allocated this item_code under this Material Request -- rather than
	silently skipping the row: issuing an allocated item to the wrong
	person (or to someone with no allocation at all) must be blocked
	outright, not merely left untracked.
	"""
	material_request = _resolve_material_request(doc)
	if not material_request or not doc.get("bio_employee"):
		return

	for row in doc.items:
		if not row.item_code:
			continue

		allocation = _find_allocation_row(material_request, doc.bio_employee, row.item_code)
		if not allocation:
			frappe.throw(
				_("{0} is not allocated Item {1} under Material Request {2}.").format(
					frappe.bold(doc.bio_employee), frappe.bold(row.item_code), frappe.bold(material_request)
				)
			)

		if allocation.employee:
			if allocation.qty_issued >= allocation.qty:
				frappe.throw(
					_("Employee {0} has already been fully issued {1} under Material Request {2}.").format(
						frappe.bold(doc.bio_employee), frappe.bold(row.item_code), frappe.bold(material_request)
					)
				)
			new_qty_issued = allocation.qty_issued + (row.qty or 0)
			updates = {"qty_issued": new_qty_issued}
			if new_qty_issued >= allocation.qty:
				updates["issued_via_stock_entry"] = doc.name
			frappe.db.set_value("Material Request Item", allocation.name, updates)
		else:
			existing = allocation.issued_via_stock_entry
			if existing and existing != doc.name:
				frappe.throw(
					_(
						"Employee {0} has already been issued items under Material Request {1} via Stock Entry {2}."
					).format(frappe.bold(doc.bio_employee), frappe.bold(material_request), frappe.bold(existing))
				)
			frappe.db.set_value("Material Request Item", allocation.name, "issued_via_stock_entry", doc.name)


def unlock_issued_employee(doc, method=None):
	"""Stock Entry on_cancel: inverse of lock_issued_employee, per item row.

	Row has employee set: qty_issued decrements by this row's quantity
	(never below 0); issued_via_stock_entry is cleared (reopened) whenever
	qty_issued drops below qty as a result -- regardless of which Stock
	Entry is currently recorded there, since cancelling any contributing
	entry can drop the running total below the threshold.

	Row has no employee: clears the lock only if it currently equals this
	Stock Entry's name.

	Deliberately still no-ops (does NOT throw) when no Material Request
	Item row matches at all -- do not "fix" this to mirror
	lock_issued_employee's throw. Cancel must remain able to unwind a Stock
	Entry that was wrongly submitted before lock_issued_employee's throw
	existed, where no row matches the issued (employee, item_code) pair. If
	cancel also threw on no-match, such a mis-issued, already-submitted
	Stock Entry could never be cancelled.
	"""
	material_request = _resolve_material_request(doc)
	if not material_request or not doc.get("bio_employee"):
		return

	for row in doc.items:
		if not row.item_code:
			continue

		allocation = _find_allocation_row(material_request, doc.bio_employee, row.item_code)
		if not allocation:
			continue

		if allocation.employee:
			new_qty_issued = max(0, allocation.qty_issued - (row.qty or 0))
			updates = {"qty_issued": new_qty_issued}
			if new_qty_issued < allocation.qty:
				updates["issued_via_stock_entry"] = None
			frappe.db.set_value("Material Request Item", allocation.name, updates)
		elif allocation.issued_via_stock_entry == doc.name:
			frappe.db.set_value("Material Request Item", allocation.name, "issued_via_stock_entry", None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `bench --site david.local run-tests --app upande_stores --module upande_stores.overrides.test_stock_entry`
Expected: all tests pass, including `IntegrationTestStockEntryPPEAssignmentCreation` and the accounting-dimension classes (which exercise `lock_issued_employee` indirectly through the same submit path, via `make_material_request(items=[{"employee": self.employee}])` producing a single employee-having row).

- [ ] **Step 5: Commit**

```bash
git add upande_stores/overrides/stock_entry.py upande_stores/overrides/test_stock_entry.py
git commit -m "feat: match Stock Entry issuance against Material Request Item directly"
```

---

### Task 4: PPE issuance — employee lives on each item row, no more merging across employees

**Files:**
- Modify: `upande_stores/api/ppe.py` (rewrite `create_ppe_onboarding_material_request` and `create_bulk_ppe_material_request`)
- Modify: `upande_stores/api/test_ppe.py` (extend `_inactive_assignment`; add new tests to `IntegrationTestCreatePPEOnboardingMR` and `IntegrationTestCreateBulkPPEMaterialRequest`)

**Interfaces:**
- Consumes: `Material Request Item.employee` (Task 1).
- No interface changes to the two whitelisted functions' own signatures — both still take the same arguments and return the same `mr.name` string. Only what they write onto the created Material Request's item rows changes.

- [ ] **Step 1: Write the failing tests**

In `upande_stores/api/test_ppe.py`, extend `_inactive_assignment` in `IntegrationTestCreateBulkPPEMaterialRequest` to accept optional overrides (existing no-argument calls keep working identically):

```python
	def _inactive_assignment(self, employee=None, item_code=None):
		return frappe.get_doc(
			{
				"doctype": "Employee PPE Assignment",
				"employee": employee or self.employee,
				"item_code": item_code or make_ppe_item(),
				"quantity": 1,
				"company": "_Test Company",
				"farm": self.farm,
				"business_unit": self.business_unit,
				"issue_date": "2026-01-01",
				"lifespan_months": 6,
				"status": "Inactive",
				"last_inspection_status": "Lost",
			}
		).insert(ignore_permissions=True)
```

Add to `IntegrationTestCreatePPEOnboardingMR`:

```python
	def test_sets_employee_on_every_item_row(self):
		item_a = make_ppe_item(lifespan_months=6)
		item_b = make_ppe_item(lifespan_months=7)
		mr_name = create_ppe_onboarding_material_request(
			onboarding=self.onboarding.name,
			employee=self.employee,
			items=json.dumps(
				[{"item_code": item_a, "quantity": 1}, {"item_code": item_b, "quantity": 1}]
			),
		)
		mr = frappe.get_doc("Material Request", mr_name)
		self.assertEqual(len(mr.items), 2)
		for row in mr.items:
			self.assertEqual(row.employee, self.employee)
```

Add to `IntegrationTestCreateBulkPPEMaterialRequest`:

```python
	def test_creates_item_row_with_employee_set(self):
		assignment = self._inactive_assignment()
		mr_name = create_bulk_ppe_material_request(json.dumps([assignment.name]))
		mr = frappe.get_doc("Material Request", mr_name)
		self.assertEqual(mr.items[0].employee, self.employee)

	def test_merges_two_assignments_for_the_same_employee_and_item(self):
		item_code = make_ppe_item(lifespan_months=6)
		first = self._inactive_assignment(item_code=item_code)
		second = self._inactive_assignment(item_code=item_code)

		mr_name = create_bulk_ppe_material_request(json.dumps([first.name, second.name]))
		mr = frappe.get_doc("Material Request", mr_name)

		self.assertEqual(len(mr.items), 1)
		self.assertEqual(mr.items[0].employee, self.employee)
		self.assertEqual(mr.items[0].qty, 2)

	def test_does_not_merge_across_different_employees(self):
		employees = get_test_employees(count=2)
		if len(employees) < 2:
			self.skipTest("Need at least 2 Active Employee records on this site.")
		emp1, emp2 = employees
		item_code = make_ppe_item(lifespan_months=6)
		first = self._inactive_assignment(employee=emp1, item_code=item_code)
		second = self._inactive_assignment(employee=emp2, item_code=item_code)

		mr_name = create_bulk_ppe_material_request(json.dumps([first.name, second.name]))
		mr = frappe.get_doc("Material Request", mr_name)

		self.assertEqual(len(mr.items), 2)
		self.assertEqual({row.employee for row in mr.items}, {emp1, emp2})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bench --site david.local run-tests --app upande_stores --module upande_stores.api.test_ppe`
Expected: the 4 new tests fail (`mr.items[0].employee` is currently always empty — neither function sets it yet). Note: this module has a pre-existing, unrelated `Price List "Standard Buying"` duplicate-key bootstrap error affecting `IntegrationTestCreatePPEOnboardingMR`'s OTHER tests on this bench (documented earlier in this app's history) — confirm the 4 new tests' own failures are specifically about the missing `employee` field, not that pre-existing issue, and don't attempt to fix the pre-existing issue as part of this task.

- [ ] **Step 3: Replace the implementation**

In `upande_stores/api/ppe.py`, replace `create_ppe_onboarding_material_request`'s document construction:

```python
	mr = frappe.get_doc(
		{
			"doctype": "Material Request",
			"material_request_type": "Material Issue",
			"schedule_date": today(),
			"company": emp.company,
			"custom_farm": emp.custom_farm or "",
			"custom_business_unit": emp.custom_business_unit or "",
			"custom_ppe_issuance": 1,
			"custom_employee_data": [{"employee": employee}],
		}
	)
	for item in items:
		mr.append(
			"items",
			{
				"item_code": item["item_code"],
				"qty": item["quantity"],
				"schedule_date": today(),
				"description": "PPE Issuance",
			},
		)
	mr.insert()
```

with:

```python
	mr = frappe.get_doc(
		{
			"doctype": "Material Request",
			"material_request_type": "Material Issue",
			"schedule_date": today(),
			"company": emp.company,
			"custom_farm": emp.custom_farm or "",
			"custom_business_unit": emp.custom_business_unit or "",
			"custom_ppe_issuance": 1,
		}
	)
	for item in items:
		mr.append(
			"items",
			{
				"item_code": item["item_code"],
				"qty": item["quantity"],
				"employee": employee,
				"schedule_date": today(),
				"description": "PPE Issuance",
			},
		)
	mr.insert()
```

Replace `create_bulk_ppe_material_request`:

```python
@frappe.whitelist()
def create_bulk_ppe_material_request(assignments):
	docs = _load_assignments(assignments)
	first = _check_same_scope(docs)

	merged_items = {}
	employees = set()
	for assignment in docs:
		if assignment.replacement_requested:
			frappe.throw(_("{0} has already been requested for replacement.").format(assignment.name))
		if not _assignment_eligible_for_replacement(assignment):
			frappe.throw(_("{0} is not eligible for replacement.").format(assignment.name))
		employees.add(assignment.employee)
		merged_items[assignment.item_code] = merged_items.get(assignment.item_code, 0) + (
			assignment.quantity or 1
		)

	mr = frappe.get_doc(
		{
			"doctype": "Material Request",
			"material_request_type": "Material Issue",
			"schedule_date": today(),
			"company": first.company,
			"custom_farm": first.farm,
			"custom_business_unit": first.business_unit,
			"custom_ppe_issuance": 1,
			"custom_employee_data": [{"employee": employee} for employee in employees],
		}
	)
	for item_code, qty in merged_items.items():
		mr.append(
			"items",
			{"item_code": item_code, "qty": qty, "schedule_date": today(), "description": "PPE Issuance"},
		)
	mr.insert()

	for assignment in docs:
		frappe.db.set_value(
			"Employee PPE Assignment",
			assignment.name,
			{"replacement_requested": 1, "replacement_material_request": mr.name},
		)
	return mr.name
```

with:

```python
@frappe.whitelist()
def create_bulk_ppe_material_request(assignments):
	docs = _load_assignments(assignments)
	first = _check_same_scope(docs)

	# Merge by (employee, item_code), not item_code alone -- employee now
	# lives on the item row directly, so a row can only ever belong to one
	# employee. Two assignments for the same employee and same item still
	# merge into one row with the summed quantity; different employees
	# needing the same item get separate rows.
	merged_items = {}
	for assignment in docs:
		if assignment.replacement_requested:
			frappe.throw(_("{0} has already been requested for replacement.").format(assignment.name))
		if not _assignment_eligible_for_replacement(assignment):
			frappe.throw(_("{0} is not eligible for replacement.").format(assignment.name))
		key = (assignment.employee, assignment.item_code)
		merged_items[key] = merged_items.get(key, 0) + (assignment.quantity or 1)

	mr = frappe.get_doc(
		{
			"doctype": "Material Request",
			"material_request_type": "Material Issue",
			"schedule_date": today(),
			"company": first.company,
			"custom_farm": first.farm,
			"custom_business_unit": first.business_unit,
			"custom_ppe_issuance": 1,
		}
	)
	for (employee, item_code), qty in merged_items.items():
		mr.append(
			"items",
			{
				"item_code": item_code,
				"qty": qty,
				"employee": employee,
				"schedule_date": today(),
				"description": "PPE Issuance",
			},
		)
	mr.insert()

	for assignment in docs:
		frappe.db.set_value(
			"Employee PPE Assignment",
			assignment.name,
			{"replacement_requested": 1, "replacement_material_request": mr.name},
		)
	return mr.name
```

Do not touch `create_bulk_ppe_purchase_request` — it never tracked employees.

- [ ] **Step 4: Run tests to verify they pass**

Run: `bench --site david.local run-tests --app upande_stores --module upande_stores.api.test_ppe`
Expected: the 4 new tests pass. `IntegrationTestCreatePPEOnboardingMR`'s other 2 tests (`test_blocks_a_second_request_for_the_same_onboarding`, `test_creates_material_issue_with_ppe_issuance_checked`) and `IntegrationTestCreateBulkPPEMaterialRequest`'s other test (`test_creates_material_issue_and_marks_assignments_requested`) must still pass unmodified — this app's pre-existing `Price List "Standard Buying"` bootstrap issue may still block `test_denies_low_privilege_user`/`test_blocks_a_second_request_for_the_same_onboarding` on this specific bench (confirmed pre-existing and unrelated, per Step 2) — if so, confirm via the same before/after comparison the codebase's history already established, don't attempt to fix it here.

- [ ] **Step 5: Commit**

```bash
git add upande_stores/api/ppe.py upande_stores/api/test_ppe.py
git commit -m "feat: set employee directly on PPE Material Request item rows, merge bulk replacements by (employee, item_code)"
```

---

### Task 5: upande_ta's bio_employee picker — query Material Request Item, not Employee Request

**Files:**
- Modify: `upande_ta/upande_ta/overrides/stock_entry.py` (rewrite `material_request_employee_query`)
- Modify: `upande_ta/upande_ta/overrides/test_stock_entry.py` (replace `_make_material_request_with_employees`/`_make_material_request_with_employee_rows` with one helper; rewrite `IntegrationTestMaterialRequestEmployeeQuery`)

No changes to `upande_ta/public/js/stock_entry.js` — its `item_codes`-gathering client logic is unaffected; only the server-side query target's underlying doctype changes.

**Interfaces:**
- Consumes: `Material Request Item.employee`/`employee_name`/`issued_via_stock_entry` (Task 1, a different app's schema — `upande_ta` doesn't own these fields, it just reads them).
- No interface changes to `material_request_employee_query`'s own signature or the filters dict shape it accepts from the client — only its internal query target changes.

- [ ] **Step 1: Write the failing tests**

Replace the entire contents of `upande_ta/upande_ta/upande_ta/overrides/test_stock_entry.py`'s two builder helpers and the `IntegrationTestMaterialRequestEmployeeQuery` class:

```python
import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from upande_ta.upande_ta.overrides.stock_entry import material_request_employee_query


def _make_material_request_with_items(item_rows, material_request_type="Material Issue"):
	"""item_rows: list of dicts appended to the standard Items table
	as-is (each needs at minimum item_code/qty; employee/
	issued_via_stock_entry are optional -- e.g. {"item_code": "_Test Item",
	"qty": 1, "employee": <name>, "issued_via_stock_entry": "STE-0001"}).
	Unset keys fall back to sensible defaults (item_code="_Test Item",
	qty=1, "_Test UOM", etc.) so callers only need to specify what's
	different.

	material_request_type defaults to "Material Issue" (this app's primary
	use case, where upande_stores' own validate hook requires employee on
	every row); pass "Material Transfer" for a test that needs a
	blank-employee row to coexist with an employee-having one.
	"""
	farm = frappe.get_all("Farm", limit=1, pluck="name")
	business_unit = frappe.get_all("Business Unit", limit=1, pluck="name")
	mr = frappe.get_doc(
		{
			"doctype": "Material Request",
			"material_request_type": material_request_type,
			"transaction_date": today(),
			"company": "_Test Company",
			"custom_farm": farm[0] if farm else None,
			"custom_business_unit": business_unit[0] if business_unit else None,
			"items": [],
		}
	)
	for row in item_rows:
		defaults = {
			"item_code": "_Test Item",
			"qty": 1,
			"uom": "_Test UOM",
			"stock_uom": "_Test UOM",
			"conversion_factor": 1,
			"schedule_date": today(),
			"warehouse": "_Test Warehouse - _TC",
		}
		defaults.update(row)
		mr.append("items", defaults)
	# ignore_links=True: issued_via_stock_entry ("STE-0001" in tests) is a Link
	# to Stock Entry that intentionally doesn't exist as a real record here --
	# only the query function's own emptiness check on the value matters, not
	# whether it resolves to a real document.
	mr.insert(ignore_permissions=True, ignore_links=True)
	return mr


class IntegrationTestMaterialRequestEmployeeQuery(IntegrationTestCase):
	def setUp(self):
		if not frappe.get_all("Farm", limit=1) or not frappe.get_all("Business Unit", limit=1):
			self.skipTest("No Farm/Business Unit record on this site to build a valid test Material Request.")
		self.employees = frappe.get_all("Employee", filters={"status": "Active"}, limit=2, pluck="name")
		if len(self.employees) < 2:
			self.skipTest("Need at least 2 Active Employee records on this site.")

	def test_excludes_already_issued_employees(self):
		emp1, emp2 = self.employees
		mr = _make_material_request_with_items(
			[
				{"item_code": "_Test Item", "qty": 1, "employee": emp1},
				{"item_code": "_Test Item 2", "qty": 1, "employee": emp2, "issued_via_stock_entry": "STE-0001"},
			]
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

	def test_fallback_does_not_filter_by_status(self):
		non_active = frappe.get_all("Employee", filters={"status": ["!=", "Active"]}, limit=1, pluck="name")
		if not non_active:
			self.skipTest("No non-Active Employee record on this site to verify the status filter is gone.")
		results = material_request_employee_query(
			"Employee", "", "name", 0, 1000, {"material_request": ""}
		)
		names = [r[0] for r in results]
		self.assertIn(non_active[0], names)

	def test_honors_pagination_offset(self):
		employees = frappe.get_all("Employee", filters={"status": "Active"}, limit=3, pluck="name")
		if len(employees) < 3:
			self.skipTest("Need at least 3 Active Employee records on this site.")
		mr = _make_material_request_with_items(
			[{"item_code": "_Test Item", "qty": 1, "employee": e} for e in employees]
		)
		page1 = material_request_employee_query("Employee", "", "name", 0, 2, {"material_request": mr.name})
		page2 = material_request_employee_query("Employee", "", "name", 2, 2, {"material_request": mr.name})
		self.assertEqual(len(page1), 2)
		self.assertGreaterEqual(len(page2), 1)
		self.assertEqual(set(r[0] for r in page1) & set(r[0] for r in page2), set())

	def test_filters_by_item_codes_when_provided(self):
		emp1, emp2 = self.employees
		mr = _make_material_request_with_items(
			[
				{"item_code": "_Test Item", "qty": 10, "employee": emp1},
				{"item_code": "_Test Item 2", "qty": 5, "employee": emp2},
			]
		)
		results = material_request_employee_query(
			"Employee", "", "name", 0, 20, {"material_request": mr.name, "item_codes": ["_Test Item"]}
		)
		names = [r[0] for r in results]
		self.assertIn(emp1, names)
		self.assertNotIn(emp2, names)

	def test_blank_employee_rows_are_never_offered(self):
		emp1 = self.employees[0]
		mr = _make_material_request_with_items(
			[
				{"item_code": "_Test Item", "qty": 10, "employee": emp1},
				{"item_code": "_Test Item 2", "qty": 5},
			],
			material_request_type="Material Transfer",
		)
		results = material_request_employee_query(
			"Employee",
			"",
			"name",
			0,
			20,
			{"material_request": mr.name, "item_codes": ["_Test Item", "_Test Item 2"]},
		)
		names = [r[0] for r in results]
		self.assertEqual(names, [emp1])

	def test_no_item_codes_filter_returns_all_unissued_regardless_of_item_code(self):
		emp1, emp2 = self.employees
		mr = _make_material_request_with_items(
			[
				{"item_code": "_Test Item", "qty": 10, "employee": emp1},
				{"item_code": "_Test Item 2", "qty": 5, "employee": emp2},
			]
		)
		results = material_request_employee_query("Employee", "", "name", 0, 20, {"material_request": mr.name})
		names = [r[0] for r in results]
		self.assertIn(emp1, names)
		self.assertIn(emp2, names)

	def test_same_employee_allocated_two_filtered_items_is_offered_once(self):
		emp = self.employees[0]
		mr = _make_material_request_with_items(
			[
				{"item_code": "_Test Item", "qty": 10, "employee": emp},
				{"item_code": "_Test Item 2", "qty": 5, "employee": emp},
			]
		)
		results = material_request_employee_query(
			"Employee",
			"",
			"name",
			0,
			20,
			{"material_request": mr.name, "item_codes": ["_Test Item", "_Test Item 2"]},
		)
		names = [r[0] for r in results]
		self.assertEqual(names.count(emp), 1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bench --site david.local run-tests --app upande_ta --module upande_ta.upande_ta.overrides.test_stock_entry`
Expected: failures — `material_request_employee_query` still queries the (now-deleted) `Employee Request` doctype.

- [ ] **Step 3: Replace the implementation**

In `upande_ta/upande_ta/upande_ta/overrides/stock_entry.py`, replace `material_request_employee_query`:

```python
@frappe.whitelist()
def material_request_employee_query(doctype, txt, searchfield, start, page_length, filters):
	"""Link query for Stock Entry's bio_employee field.

	filters["material_request"] is resolved client-side (see stock_entry.js)
	from the current form's item rows -- not re-derived server-side from a
	saved Stock Entry, so this works for unsaved drafts too. Scoped to that
	Material Request's own Item rows that have an employee set and haven't
	been issued via another Stock Entry yet (Material Request Item.
	issued_via_stock_entry empty).

	filters["item_codes"] (also resolved client-side, from the item_code of
	every item row sharing that same material_request) further narrows this
	to employees allocated one of those specific items -- e.g. a Material
	Request allocating Amisil to James and MPK to Timothy will only offer
	James when the Stock Entry is issuing Amisil. A blank-employee row
	(only reachable for non-Material-Issue request types, where employee
	stays optional) is never offered here at all -- it carries no employee
	to offer in the first place. If no item_codes are passed at all
	(nothing to filter by) every employee-having row is kept, preserving
	today's behavior exactly. The same employee allocated more than one of
	the filtered items is offered exactly once, not once per matching row.

	Falls back to a plain Employee search when there's no Material Request
	context, matching bio_employee's existing unrestricted behavior -- also
	used when the Material Request Item doctype doesn't exist at all (this
	app is installed on other sites that don't have upande_stores, where
	material_request can still be set on a Stock Entry Detail row for
	reasons unrelated to this feature).
	"""
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	material_request = filters.get("material_request")
	item_codes = set(filter(None, filters.get("item_codes") or []))
	if material_request and not frappe.has_permission("Material Request", "read", material_request):
		# Caller can't read this Material Request -- degrade gracefully to the
		# same unrestricted Employee search used when there's no Material
		# Request context at all, rather than leaking which employees are
		# tied to a Material Request the user isn't allowed to see.
		material_request = None
	offset = cint(start) or 0
	limit = cint(page_length) or 20
	txt_lower = (txt or "").lower()

	if not material_request or not frappe.db.table_exists("Material Request Item"):
		# list(...): frappe.get_all(..., as_list=True) returns a tuple of tuples
		# on this Frappe version -- normalize to the documented list[tuple] return
		# type (also what the standard Link-field query contract expects).
		# No status filter here: before this feature existed, bio_employee had
		# no custom query at all -- Frappe's generic, fully unrestricted link
		# search. This fallback must match that exactly, including Suspended/
		# Inactive/Left employees.
		return list(
			frappe.get_all(
				"Employee",
				or_filters={"name": ["like", f"%{txt}%"], "employee_name": ["like", f"%{txt}%"]},
				fields=["name", "employee_name"],
				limit_start=offset,
				limit=limit,
				as_list=True,
			)
		)

	rows = frappe.get_all(
		"Material Request Item",
		filters={
			"parent": material_request,
			"parenttype": "Material Request",
			"employee": ["is", "set"],
		},
		fields=["employee", "employee_name", "issued_via_stock_entry", "item_code"],
	)
	results = [
		(row.employee, row.employee_name)
		for row in rows
		if not row.issued_via_stock_entry
		and (not item_codes or row.item_code in item_codes)
		and (txt_lower in (row.employee or "").lower() or txt_lower in (row.employee_name or "").lower())
	]
	# The same employee can now have more than one row (once per item they
	# need) -- de-duplicate by employee, preserving first-seen order, so a
	# Stock Entry issuing several allocated items doesn't offer them twice.
	seen = set()
	deduped = []
	for pair in results:
		if pair[0] in seen:
			continue
		seen.add(pair[0])
		deduped.append(pair)
	return deduped[offset : offset + limit]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `bench --site david.local run-tests --app upande_ta --module upande_ta.upande_ta.overrides.test_stock_entry`
Expected: all tests pass, including the new `test_blank_employee_rows_are_never_offered` and `test_same_employee_allocated_two_filtered_items_is_offered_once`.

- [ ] **Step 5: Commit**

```bash
git add upande_ta/upande_ta/overrides/stock_entry.py upande_ta/upande_ta/overrides/test_stock_entry.py
git commit -m "fix: scope the bio_employee picker to Material Request Item rows directly"
```

Note: this task's commit lands in the `upande_ta` repo (branch `kaitet`, remote `upstream`) — a separate git history from `upande_stores`. Do not run `git add -A` in that repo — it has a pre-existing, unrelated uncommitted change to `upande_ta/desktop_icon/t&a.json` that must stay untouched.
