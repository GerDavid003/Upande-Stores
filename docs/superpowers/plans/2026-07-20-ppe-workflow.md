# PPE Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `upande_kaitet`'s PPE issuance/inspection/replacement workflow as
git-tracked app code in `upande_stores` (kaitet-bench), with `Employee PPE History`
owned by `upande_hr`, replacing the DB-only Server/Client Scripts the old build
relied on.

**Architecture:** New doctypes own their behavior in their own `.py`/`.js`
controllers. Hooks into doctypes `upande_stores` doesn't own (Stock Entry,
Material Request, Employee Onboarding) go through `hooks.py` `doc_events` /
`doctype_js` into `overrides/*.py` and `public/js/*.js`. All server-callable
entry points live in `upande_stores/api/ppe.py` as real `@frappe.whitelist()`
functions (no `frappe.form_dict` parsing, no raw Server Script records).

**Tech Stack:** Frappe/ERPNext (this bench: `hrms`, `erpnext` installed), Python
controllers, vanilla `frappe.ui.form`/`frappe.listview_settings` client scripts,
`frappe.tests.IntegrationTestCase` for tests (this app's established convention —
see `upande_stores/overrides/test_stock_entry.py`).

Full design rationale: `docs/superpowers/specs/2026-07-20-ppe-workflow-design.md`.

## Global Constraints

- Site under test: `david.local` (kaitet-bench). Run tests with:
  `bench --site david.local run-tests --app upande_stores` (and `--app upande_hr`
  for Task 11).
- Indentation: **tabs**, matching every existing file in both apps (verified in
  `upande_stores/overrides/stock_entry.py`, `upande_kaitet`'s doctype controllers).
- Module tags: every new Custom Field/Property Setter must carry
  `"module": "Upande Stores"` (or `"Upande Hr"` for Task 11) — that's what makes
  the existing `before_uninstall` hooks in each app clean them up. Every new
  DocType JSON must set `"module"` the same way — Frappe removes an app's own
  module's doctypes automatically on uninstall, no extra code needed for those.
- Reuse `upande_stores/upande_stores/tests/test_helpers.py` builders
  (`get_test_farm_and_business_unit`, `get_test_employees`, `make_material_request`,
  `make_stock_entry_for_material_request`) in every new test — this is the
  established pattern in this app; don't hand-roll Farm/Employee/Material Request
  test fixtures inline.
- Permission roles on the 3 new standalone doctypes (PPE Policy, Employee PPE
  Assignment, PPE Inspection) are a judgment call, not something the requester
  specified: `System Manager` (full), `HR Manager` (full), `Farm Manager`
  (create/read/write/report/submit where applicable, no delete). Confirm with the
  requester before or after building if these don't match reality — easy to change
  later via Customize Form.
- `ignore_permissions=True` is used only for the framework-triggered writes a
  regular user shouldn't need direct doctype permission for (assignment
  inserts/updates from a Stock Entry submit, history sync). The 4 whitelisted API
  functions in `api/ppe.py` do **not** use `ignore_permissions` — unlike the old
  Server Scripts, they respect the calling user's own Material Request / Employee
  PPE Assignment permissions. Flag to the requester if this breaks the intended
  UX for a role that shouldn't have direct MR-create rights.

---

## Task 1: Pre-flight — clear both name collisions on `david.local`

**Files:** none (site data + DB operations only)

**Interfaces:** N/A (this task only removes things; nothing later depends on any
new name/function from this task).

- [ ] **Step 1: Confirm with the requester immediately before running the next
  step** — this uninstalls an entire app. State exactly what will run and wait for
  an explicit go-ahead in this session, even though the destructive-action choice
  was already made in principle earlier in this conversation.

- [ ] **Step 2: Uninstall `upande_kaitet` from `david.local`**

Run:
```bash
cd ~/frappe/kaitet-bench
bench --site david.local uninstall-app upande_kaitet --yes
```
Expected: command completes without error (all 8 PPE doctypes it owns are empty,
per the earlier audit, so there's nothing for Frappe to block on).

- [ ] **Step 3: Verify the collision is cleared**

Run:
```bash
mysql --raw -u _9768ed00be7957a2 -pwwTd8QrTVAwABDuN -h 127.0.0.1 _9768ed00be7957a2 \
  -e "select count(*) from \`tabDocType\` where module='Upande Kaitet';"
```
Expected: `0`.

- [ ] **Step 4: Delete the 4 orphaned (module=NULL) Custom Fields that predate
  this work and would otherwise collide with Tasks 2, 9, and 11**

Run:
```bash
cd ~/frappe/kaitet-bench
bench --site david.local console
```
In the console:
```python
import frappe
for name in [
    "Item-custom_is_ppe",
    "Item-custom_ppe_lifespan",
    "Employee-custom_ppe_history",
    "Employee-custom_ppe_issuance",
]:
    if frappe.db.exists("Custom Field", name):
        frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
frappe.db.commit()
exit()
```

- [ ] **Step 5: Verify**

Run:
```bash
mysql --raw -u _9768ed00be7957a2 -pwwTd8QrTVAwABDuN -h 127.0.0.1 _9768ed00be7957a2 \
  -e "select name from \`tabCustom Field\` where name in ('Item-custom_is_ppe','Item-custom_ppe_lifespan','Employee-custom_ppe_history','Employee-custom_ppe_issuance');"
```
Expected: empty result set.

- [ ] **Step 6: Commit** — nothing to commit (no files changed), but note in your
  session log that Task 1 ran and both checks passed before proceeding to Task 2.

---

## Task 2: Item — `custom_is_ppe` / `custom_ppe_lifespan`

**Files:**
- Create: `apps/upande_stores/upande_stores/upande_stores/custom/item.json`

**Interfaces:**
- Produces: `Item.custom_is_ppe` (Check), `Item.custom_ppe_lifespan` (Int) —
  every later task that reads/writes these two fieldnames depends on this task.

- [ ] **Step 1: Write the file**

```json
{
 "custom_fields": [
  {
   "_assign": null,
   "_comments": null,
   "_liked_by": null,
   "_user_tags": null,
   "allow_in_quick_entry": 0,
   "allow_on_submit": 0,
   "bold": 0,
   "collapsible": 0,
   "collapsible_depends_on": null,
   "columns": 0,
   "creation": "2026-07-20 00:00:00.000000",
   "default": "0",
   "depends_on": null,
   "description": null,
   "docstatus": 0,
   "dt": "Item",
   "fetch_from": null,
   "fetch_if_empty": 0,
   "fieldname": "custom_is_ppe",
   "fieldtype": "Check",
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
   "in_standard_filter": 1,
   "insert_after": "image",
   "is_system_generated": 0,
   "is_virtual": 0,
   "label": "Is PPE",
   "length": 0,
   "link_filters": null,
   "mandatory_depends_on": null,
   "modified": "2026-07-20 00:00:00.000000",
   "modified_by": "Administrator",
   "module": "Upande Stores",
   "name": "Item-custom_is_ppe",
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
   "read_only": 0,
   "read_only_depends_on": null,
   "report_hide": 0,
   "reqd": 0,
   "search_index": 0,
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
   "allow_in_quick_entry": 0,
   "allow_on_submit": 0,
   "bold": 0,
   "collapsible": 0,
   "collapsible_depends_on": null,
   "columns": 0,
   "creation": "2026-07-20 00:00:00.000000",
   "default": null,
   "depends_on": "eval:doc.custom_is_ppe == 1",
   "description": null,
   "docstatus": 0,
   "dt": "Item",
   "fetch_from": null,
   "fetch_if_empty": 0,
   "fieldname": "custom_ppe_lifespan",
   "fieldtype": "Int",
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
   "insert_after": "custom_is_ppe",
   "is_system_generated": 0,
   "is_virtual": 0,
   "label": "PPE Lifespan (Months)",
   "length": 0,
   "link_filters": null,
   "mandatory_depends_on": "eval:doc.custom_is_ppe == 1",
   "modified": "2026-07-20 00:00:00.000000",
   "modified_by": "Administrator",
   "module": "Upande Stores",
   "name": "Item-custom_ppe_lifespan",
   "no_copy": 0,
   "non_negative": 1,
   "options": null,
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
   "show_dashboard": 0,
   "sort_options": 0,
   "translatable": 0,
   "unique": 0,
   "width": null
  }
 ],
 "custom_perms": [],
 "doctype": "Item",
 "links": [],
 "property_setters": [],
 "sync_on_migrate": 1
}
```

- [ ] **Step 2: Migrate and verify**

Run:
```bash
cd ~/frappe/kaitet-bench
bench --site david.local migrate
bench --site david.local console
```
```python
import frappe
frappe.get_meta("Item").get_field("custom_is_ppe").fieldtype  # 'Check'
frappe.get_meta("Item").get_field("custom_ppe_lifespan").mandatory_depends_on
exit()
```
Expected: no errors; `mandatory_depends_on` prints `eval:doc.custom_is_ppe == 1`.

- [ ] **Step 3: Commit**

```bash
cd ~/frappe/kaitet-bench/apps/upande_stores
git add upande_stores/upande_stores/custom/item.json
git commit -m "feat: add Is PPE / PPE Lifespan custom fields to Item"
```

---

## Task 3: Test helper — `make_ppe_item`

**Files:**
- Modify: `apps/upande_stores/upande_stores/upande_stores/tests/test_helpers.py`

**Interfaces:**
- Consumes: `Item.custom_is_ppe`, `Item.custom_ppe_lifespan` (Task 2).
- Produces: `make_ppe_item(lifespan_months=6)` — every later test that needs a
  PPE-flagged Item calls this instead of hardcoding `_Test Item`.

- [ ] **Step 1: Add the helper**, appended to the existing file (after
  `make_stock_entry_for_material_request`):

```python
def make_ppe_item(lifespan_months=6):
	"""Return the name of a custom_is_ppe Item with the given lifespan, creating
	it if it doesn't exist yet on this site."""
	item_code = f"_Test PPE Item {lifespan_months}mo"
	if not frappe.db.exists("Item", item_code):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": item_code,
				"item_group": "_Test Item Group",
				"stock_uom": "_Test UOM",
				"is_stock_item": 1,
				"custom_is_ppe": 1,
				"custom_ppe_lifespan": lifespan_months,
			}
		).insert(ignore_permissions=True)
	return item_code
```

- [ ] **Step 2: Verify it runs standalone**

Run:
```bash
cd ~/frappe/kaitet-bench
bench --site david.local console
```
```python
from upande_stores.tests.test_helpers import make_ppe_item
make_ppe_item()
exit()
```
Expected: returns `'_Test PPE Item 6mo'`, no error.

- [ ] **Step 3: Commit**

```bash
cd ~/frappe/kaitet-bench/apps/upande_stores
git add upande_stores/upande_stores/tests/test_helpers.py
git commit -m "test: add make_ppe_item test helper"
```

---

## Task 4: PPE Policy + PPE Policy Item doctypes

**Files:**
- Create: `apps/upande_stores/upande_stores/upande_stores/doctype/ppe_policy/__init__.py` (empty)
- Create: `apps/upande_stores/upande_stores/upande_stores/doctype/ppe_policy/ppe_policy.json`
- Create: `apps/upande_stores/upande_stores/upande_stores/doctype/ppe_policy/ppe_policy.py`
- Create: `apps/upande_stores/upande_stores/upande_stores/doctype/ppe_policy/ppe_policy.js`
- Create: `apps/upande_stores/upande_stores/upande_stores/doctype/ppe_policy/test_ppe_policy.py`
- Create: `apps/upande_stores/upande_stores/upande_stores/doctype/ppe_policy_item/__init__.py` (empty)
- Create: `apps/upande_stores/upande_stores/upande_stores/doctype/ppe_policy_item/ppe_policy_item.json`
- Create: `apps/upande_stores/upande_stores/upande_stores/doctype/ppe_policy_item/ppe_policy_item.py`
- Create: `apps/upande_stores/upande_stores/upande_stores/doctype/ppe_policy_item/test_ppe_policy_item.py`

**Interfaces:**
- Consumes: `Item.custom_is_ppe` (Task 2), `make_ppe_item` (Task 3).
- Produces: `PPE Policy` doctype (fields `company`, `department`, `designation`,
  `active`, `items`), `PPE Policy Item` child doctype (`item_code`, `item_name`,
  `quantity`) — Task 6's `get_ppe_requirements_for_onboarding` reads both.

- [ ] **Step 1: `ppe_policy_item.json`**

```json
{
 "actions": [],
 "creation": "2026-07-20 00:00:00.000000",
 "doctype": "DocType",
 "editable_grid": 1,
 "engine": "InnoDB",
 "field_order": ["item_code", "item_name", "quantity"],
 "fields": [
  {
   "fieldname": "item_code",
   "fieldtype": "Link",
   "in_list_view": 1,
   "label": "Item Code",
   "options": "Item",
   "reqd": 1,
   "search_index": 1
  },
  {
   "fetch_from": "item_code.item_name",
   "fieldname": "item_name",
   "fieldtype": "Data",
   "in_list_view": 1,
   "label": "Item Name",
   "read_only": 1
  },
  {
   "default": "1",
   "fieldname": "quantity",
   "fieldtype": "Int",
   "in_list_view": 1,
   "label": "Quantity",
   "reqd": 1
  }
 ],
 "grid_page_length": 50,
 "istable": 1,
 "links": [],
 "modified": "2026-07-20 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Upande Stores",
 "name": "PPE Policy Item",
 "owner": "Administrator",
 "permissions": [],
 "row_format": "Dynamic",
 "sort_field": "modified",
 "sort_order": "DESC",
 "states": []
}
```

- [ ] **Step 2: `ppe_policy_item.py`**

```python
import frappe
from frappe import _
from frappe.model.document import Document


class PPEPolicyItem(Document):
	def validate(self):
		if self.item_code:
			is_ppe = frappe.db.get_value("Item", self.item_code, "custom_is_ppe")
			if not is_ppe:
				frappe.throw(_("Item {0} is not marked as a PPE item.").format(self.item_code))
```

- [ ] **Step 3: `ppe_policy.json`**

```json
{
 "actions": [],
 "autoname": "PPE-POL-.####",
 "creation": "2026-07-20 00:00:00.000000",
 "doctype": "DocType",
 "engine": "InnoDB",
 "field_order": [
  "company",
  "department",
  "designation",
  "column_break_1",
  "active",
  "description",
  "items_section",
  "items"
 ],
 "fields": [
  {
   "fieldname": "company",
   "fieldtype": "Link",
   "in_list_view": 1,
   "in_standard_filter": 1,
   "label": "Company",
   "options": "Company",
   "reqd": 1,
   "search_index": 1
  },
  {
   "fieldname": "department",
   "fieldtype": "Link",
   "in_list_view": 1,
   "in_standard_filter": 1,
   "label": "Department",
   "options": "Department",
   "search_index": 1
  },
  {
   "fieldname": "designation",
   "fieldtype": "Link",
   "in_list_view": 1,
   "in_standard_filter": 1,
   "label": "Designation",
   "options": "Designation",
   "search_index": 1
  },
  {
   "fieldname": "column_break_1",
   "fieldtype": "Column Break"
  },
  {
   "default": "1",
   "fieldname": "active",
   "fieldtype": "Check",
   "in_list_view": 1,
   "in_standard_filter": 1,
   "label": "Active"
  },
  {
   "fieldname": "description",
   "fieldtype": "Small Text",
   "label": "Description"
  },
  {
   "fieldname": "items_section",
   "fieldtype": "Section Break",
   "label": "Required PPE Items"
  },
  {
   "fieldname": "items",
   "fieldtype": "Table",
   "label": "Items",
   "options": "PPE Policy Item",
   "reqd": 1
  }
 ],
 "index_web_pages_for_search": 1,
 "links": [],
 "modified": "2026-07-20 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Upande Stores",
 "name": "PPE Policy",
 "naming_rule": "Expression",
 "owner": "Administrator",
 "permissions": [
  {
   "create": 1, "delete": 1, "email": 1, "export": 1, "print": 1, "read": 1,
   "report": 1, "role": "System Manager", "share": 1, "write": 1
  },
  {
   "create": 1, "email": 1, "export": 1, "print": 1, "read": 1,
   "report": 1, "role": "HR Manager", "share": 1, "write": 1
  },
  {
   "create": 1, "email": 1, "export": 1, "print": 1, "read": 1,
   "report": 1, "role": "Farm Manager", "share": 1, "write": 1
  }
 ],
 "row_format": "Dynamic",
 "sort_field": "modified",
 "sort_order": "DESC",
 "states": [],
 "track_changes": 1
}
```

- [ ] **Step 4: `ppe_policy.py`**

```python
import frappe
from frappe import _
from frappe.model.document import Document


class PPEPolicy(Document):
	def validate(self):
		if not self.department and not self.designation:
			frappe.throw(_("Please set at least one of Department or Designation."))
		if self.active:
			self._check_no_duplicate_active_policy()

	def _check_no_duplicate_active_policy(self):
		filters = {
			"active": 1,
			"name": ["!=", self.name or ""],
			"company": self.company or "",
			"department": self.department or "",
			"designation": self.designation or "",
		}
		if frappe.db.exists("PPE Policy", filters):
			parts = [_("Company {0}").format(self.company)]
			if self.department:
				parts.append(_("Department {0}").format(self.department))
			if self.designation:
				parts.append(_("Designation {0}").format(self.designation))
			frappe.throw(
				_("An active PPE Policy for {0} already exists.").format(" and ".join(parts))
			)
```

- [ ] **Step 5: `ppe_policy.js`**

```js
frappe.ui.form.on("PPE Policy", {
	refresh(frm) {
		if (!frm.doc.department && !frm.doc.designation) {
			frm.set_intro(__("Please set at least one of Department or Designation."), "orange");
		}
	},
});
```

- [ ] **Step 6: Write the failing tests — `test_ppe_policy_item.py`**

```python
import frappe
from frappe.tests import IntegrationTestCase

from upande_stores.tests.test_helpers import make_ppe_item


class IntegrationTestPPEPolicyItem(IntegrationTestCase):
	def test_rejects_non_ppe_item(self):
		if not frappe.db.exists("Item", "_Test Item"):
			self.skipTest("Standard _Test Item fixture not present on this site.")

		policy = frappe.get_doc(
			{
				"doctype": "PPE Policy",
				"company": "_Test Company",
				"department": "_Test Department - _TC",
				"items": [{"item_code": "_Test Item", "quantity": 1}],
			}
		)
		with self.assertRaises(frappe.ValidationError):
			policy.insert(ignore_permissions=True)

	def test_accepts_ppe_item(self):
		policy = frappe.get_doc(
			{
				"doctype": "PPE Policy",
				"company": "_Test Company",
				"department": "_Test Department - _TC",
				"items": [{"item_code": make_ppe_item(), "quantity": 2}],
			}
		)
		policy.insert(ignore_permissions=True)
		self.assertEqual(policy.items[0].quantity, 2)
```

- [ ] **Step 7: `test_ppe_policy.py`**

```python
import frappe
from frappe.tests import IntegrationTestCase

from upande_stores.tests.test_helpers import make_ppe_item


class IntegrationTestPPEPolicy(IntegrationTestCase):
	def test_requires_department_or_designation(self):
		policy = frappe.get_doc(
			{
				"doctype": "PPE Policy",
				"company": "_Test Company",
				"items": [{"item_code": make_ppe_item(), "quantity": 1}],
			}
		)
		with self.assertRaises(frappe.ValidationError):
			policy.insert(ignore_permissions=True)

	def test_blocks_duplicate_active_policy_for_same_company(self):
		item_code = make_ppe_item()
		frappe.get_doc(
			{
				"doctype": "PPE Policy",
				"company": "_Test Company",
				"department": "_Test Department - _TC",
				"items": [{"item_code": item_code, "quantity": 1}],
			}
		).insert(ignore_permissions=True)

		duplicate = frappe.get_doc(
			{
				"doctype": "PPE Policy",
				"company": "_Test Company",
				"department": "_Test Department - _TC",
				"items": [{"item_code": item_code, "quantity": 1}],
			}
		)
		with self.assertRaises(frappe.ValidationError):
			duplicate.insert(ignore_permissions=True)

	def test_allows_same_department_for_a_different_company(self):
		if not frappe.db.exists("Company", "_Test Company 1"):
			self.skipTest("_Test Company 1 fixture not present on this site.")

		item_code = make_ppe_item()
		frappe.get_doc(
			{
				"doctype": "PPE Policy",
				"company": "_Test Company",
				"department": "_Test Department - _TC",
				"items": [{"item_code": item_code, "quantity": 1}],
			}
		).insert(ignore_permissions=True)

		other_company = frappe.get_doc(
			{
				"doctype": "PPE Policy",
				"company": "_Test Company 1",
				"department": "_Test Department - _TC",
				"items": [{"item_code": item_code, "quantity": 1}],
			}
		)
		other_company.insert(ignore_permissions=True)  # must not raise
		self.assertTrue(other_company.name)
```

- [ ] **Step 8: Migrate, then run the tests**

Run:
```bash
cd ~/frappe/kaitet-bench
bench --site david.local migrate
bench --site david.local run-tests --app upande_stores --module upande_stores.upande_stores.doctype.ppe_policy.test_ppe_policy
bench --site david.local run-tests --app upande_stores --module upande_stores.upande_stores.doctype.ppe_policy_item.test_ppe_policy_item
```
Expected: all tests PASS (or SKIP where the noted fixture is genuinely absent —
not a failure).

- [ ] **Step 9: Commit**

```bash
cd ~/frappe/kaitet-bench/apps/upande_stores
git add upande_stores/upande_stores/doctype/ppe_policy upande_stores/upande_stores/doctype/ppe_policy_item
git commit -m "feat: add PPE Policy and PPE Policy Item doctypes"
```

---

## Task 5: Employee Onboarding customization + PPE Onboarding Item

**Files:**
- Create: `apps/upande_stores/upande_stores/upande_stores/custom/employee_onboarding.json`
- Create: `apps/upande_stores/upande_stores/upande_stores/doctype/ppe_onboarding_item/__init__.py` (empty)
- Create: `apps/upande_stores/upande_stores/upande_stores/doctype/ppe_onboarding_item/ppe_onboarding_item.json`
- Create: `apps/upande_stores/upande_stores/upande_stores/doctype/ppe_onboarding_item/ppe_onboarding_item.py`

**Interfaces:**
- Produces: `Employee Onboarding.custom_ppe_requirements` (Table →
  `PPE Onboarding Item`), `Employee Onboarding.custom_ppe_material_request`
  (Link → Material Request) — Tasks 6, 7, 9, 10 depend on both fieldnames.
- Note: all 3 custom fields below carry `"allow_on_submit": 1`. Employee
  Onboarding is submittable, and in practice HR submits it well before the PPE
  buttons get used — without this, editing these fields on an already-submitted
  onboarding would raise a "not allowed to edit after submit" error.

- [ ] **Step 1: `ppe_onboarding_item.json`**

```json
{
 "actions": [],
 "creation": "2026-07-20 00:00:00.000000",
 "doctype": "DocType",
 "engine": "InnoDB",
 "field_order": ["item_code", "item_name", "quantity", "issued"],
 "fields": [
  {
   "fieldname": "item_code",
   "fieldtype": "Link",
   "in_list_view": 1,
   "label": "Item Code",
   "options": "Item",
   "read_only": 1,
   "reqd": 1
  },
  {
   "fetch_from": "item_code.item_name",
   "fieldname": "item_name",
   "fieldtype": "Data",
   "in_list_view": 1,
   "label": "Item Name",
   "read_only": 1
  },
  {
   "default": "1",
   "fieldname": "quantity",
   "fieldtype": "Int",
   "in_list_view": 1,
   "label": "Quantity",
   "reqd": 1
  },
  {
   "default": "0",
   "fieldname": "issued",
   "fieldtype": "Check",
   "in_list_view": 1,
   "label": "Issued"
  }
 ],
 "index_web_pages_for_search": 0,
 "istable": 1,
 "links": [],
 "modified": "2026-07-20 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Upande Stores",
 "name": "PPE Onboarding Item",
 "owner": "Administrator",
 "permissions": [],
 "row_format": "Dynamic",
 "track_changes": 0
}
```

- [ ] **Step 2: `ppe_onboarding_item.py`**

```python
from frappe.model.document import Document


class PPEOnboardingItem(Document):
	pass
```

- [ ] **Step 3: `custom/employee_onboarding.json`**

```json
{
 "custom_fields": [
  {
   "_assign": null, "_comments": null, "_liked_by": null, "_user_tags": null,
   "allow_in_quick_entry": 0, "allow_on_submit": 1, "bold": 0, "collapsible": 0,
   "collapsible_depends_on": null, "columns": 0,
   "creation": "2026-07-20 00:00:00.000000", "default": null, "depends_on": null,
   "description": null, "docstatus": 0, "dt": "Employee Onboarding",
   "fetch_from": null, "fetch_if_empty": 0,
   "fieldname": "custom_ppe_requirements_section", "fieldtype": "Section Break",
   "hidden": 0, "hide_border": 0, "hide_days": 0, "hide_seconds": 0, "idx": 0,
   "ignore_user_permissions": 0, "ignore_xss_filter": 0, "in_global_search": 0,
   "in_list_view": 0, "in_preview": 0, "in_standard_filter": 0,
   "insert_after": "holiday_list", "is_system_generated": 0, "is_virtual": 0,
   "label": "PPE Requirements", "length": 0, "link_filters": null,
   "mandatory_depends_on": null, "modified": "2026-07-20 00:00:00.000000",
   "modified_by": "Administrator", "module": "Upande Stores",
   "name": "Employee Onboarding-custom_ppe_requirements_section", "no_copy": 0,
   "non_negative": 0, "options": null, "owner": "Administrator", "permlevel": 0,
   "placeholder": null, "precision": "", "print_hide": 0,
   "print_hide_if_no_value": 0, "print_width": null, "read_only": 0,
   "read_only_depends_on": null, "report_hide": 0, "reqd": 0, "search_index": 0,
   "show_dashboard": 0, "sort_options": 0, "translatable": 0, "unique": 0,
   "width": null
  },
  {
   "_assign": null, "_comments": null, "_liked_by": null, "_user_tags": null,
   "allow_in_quick_entry": 0, "allow_on_submit": 1, "bold": 0, "collapsible": 0,
   "collapsible_depends_on": null, "columns": 0,
   "creation": "2026-07-20 00:00:00.000000", "default": null, "depends_on": null,
   "description": null, "docstatus": 0, "dt": "Employee Onboarding",
   "fetch_from": null, "fetch_if_empty": 0, "fieldname": "custom_ppe_requirements",
   "fieldtype": "Table", "hidden": 0, "hide_border": 0, "hide_days": 0,
   "hide_seconds": 0, "idx": 0, "ignore_user_permissions": 0,
   "ignore_xss_filter": 0, "in_global_search": 0, "in_list_view": 0,
   "in_preview": 0, "in_standard_filter": 0,
   "insert_after": "custom_ppe_requirements_section", "is_system_generated": 0,
   "is_virtual": 0, "label": "PPE Requirements", "length": 0,
   "link_filters": null, "mandatory_depends_on": null,
   "modified": "2026-07-20 00:00:00.000000", "modified_by": "Administrator",
   "module": "Upande Stores", "name": "Employee Onboarding-custom_ppe_requirements",
   "no_copy": 0, "non_negative": 0, "options": "PPE Onboarding Item",
   "owner": "Administrator", "permlevel": 0, "placeholder": null, "precision": "",
   "print_hide": 0, "print_hide_if_no_value": 0, "print_width": null,
   "read_only": 0, "read_only_depends_on": null, "report_hide": 0, "reqd": 0,
   "search_index": 0, "show_dashboard": 0, "sort_options": 0, "translatable": 0,
   "unique": 0, "width": null
  },
  {
   "_assign": null, "_comments": null, "_liked_by": null, "_user_tags": null,
   "allow_in_quick_entry": 0, "allow_on_submit": 1, "bold": 0, "collapsible": 0,
   "collapsible_depends_on": null, "columns": 0,
   "creation": "2026-07-20 00:00:00.000000", "default": null, "depends_on": null,
   "description": null, "docstatus": 0, "dt": "Employee Onboarding",
   "fetch_from": null, "fetch_if_empty": 0,
   "fieldname": "custom_ppe_material_request", "fieldtype": "Link", "hidden": 0,
   "hide_border": 0, "hide_days": 0, "hide_seconds": 0, "idx": 0,
   "ignore_user_permissions": 0, "ignore_xss_filter": 0, "in_global_search": 0,
   "in_list_view": 0, "in_preview": 0, "in_standard_filter": 0,
   "insert_after": "custom_ppe_requirements", "is_system_generated": 0,
   "is_virtual": 0, "label": "PPE Material Request", "length": 0,
   "link_filters": null, "mandatory_depends_on": null,
   "modified": "2026-07-20 00:00:00.000000", "modified_by": "Administrator",
   "module": "Upande Stores",
   "name": "Employee Onboarding-custom_ppe_material_request", "no_copy": 0,
   "non_negative": 0, "options": "Material Request", "owner": "Administrator",
   "permlevel": 0, "placeholder": null, "precision": "", "print_hide": 0,
   "print_hide_if_no_value": 0, "print_width": null, "read_only": 1,
   "read_only_depends_on": null, "report_hide": 0, "reqd": 0, "search_index": 0,
   "show_dashboard": 0, "sort_options": 0, "translatable": 0, "unique": 0,
   "width": null
  }
 ],
 "custom_perms": [],
 "doctype": "Employee Onboarding",
 "links": [],
 "property_setters": [],
 "sync_on_migrate": 1
}
```

- [ ] **Step 4: Migrate and verify**

Run:
```bash
cd ~/frappe/kaitet-bench
bench --site david.local migrate
bench --site david.local console
```
```python
import frappe
frappe.get_meta("Employee Onboarding").get_field("custom_ppe_requirements").options  # 'PPE Onboarding Item'
exit()
```

- [ ] **Step 5: Commit**

```bash
cd ~/frappe/kaitet-bench/apps/upande_stores
git add upande_stores/upande_stores/custom/employee_onboarding.json upande_stores/upande_stores/doctype/ppe_onboarding_item
git commit -m "feat: add PPE Requirements table to Employee Onboarding"
```

---

## Task 6: API — `get_ppe_requirements_for_onboarding`

**Files:**
- Create: `apps/upande_stores/upande_stores/upande_stores/api/__init__.py` (empty)
- Create: `apps/upande_stores/upande_stores/upande_stores/api/ppe.py`
- Create: `apps/upande_stores/upande_stores/upande_stores/api/test_ppe.py`

**Interfaces:**
- Consumes: `PPE Policy` (Task 4), `PPE Policy Item` (Task 4), `Employee.company`/
  `.department`/`.designation` (core fields).
- Produces: `upande_stores.api.ppe.get_ppe_requirements_for_onboarding(employee)`
  → `list[dict]` with keys `item_code`, `item_name`, `quantity`. Task 7's client
  script and Task 9's function both rely on this exact return shape.

- [ ] **Step 1: Write the failing test — `api/test_ppe.py`**

```python
import frappe
from frappe.tests import IntegrationTestCase

from upande_stores.api.ppe import get_ppe_requirements_for_onboarding
from upande_stores.tests.test_helpers import get_test_employees, make_ppe_item


class IntegrationTestGetPPERequirements(IntegrationTestCase):
	def setUp(self):
		employees = get_test_employees(count=1)
		if not employees:
			self.skipTest("Need at least 1 Active Employee record on this site.")
		self.employee = employees[0]
		self.company, self.department, self.designation = frappe.db.get_value(
			"Employee", self.employee, ["company", "department", "designation"]
		)
		if not self.department:
			self.skipTest("Test Employee has no Department set.")
		frappe.db.delete("PPE Policy", {"company": self.company, "department": self.department})

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
				"department": self.department,
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
```

- [ ] **Step 2: Run the test to confirm it fails**

Run:
```bash
cd ~/frappe/kaitet-bench
bench --site david.local run-tests --app upande_stores --module upande_stores.api.test_ppe
```
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'upande_stores.api.ppe'`.

- [ ] **Step 3: Write `api/ppe.py`**

```python
import frappe
from frappe import _


def _matching_ppe_policies(company, department, designation):
	"""Active PPE Policies for this exact company where department/designation
	are either unset on the policy (wildcard) or match exactly."""
	policies = frappe.get_all(
		"PPE Policy",
		filters={"active": 1, "company": company},
		fields=["name", "department", "designation"],
	)
	matched = []
	for policy in policies:
		dept_match = (not policy.department) or (policy.department == (department or ""))
		desig_match = (not policy.designation) or (policy.designation == (designation or ""))
		if dept_match and desig_match:
			matched.append(policy.name)
	return matched


@frappe.whitelist()
def get_ppe_requirements_for_onboarding(employee):
	emp = frappe.db.get_value(
		"Employee", employee, ["company", "department", "designation"], as_dict=True
	)
	if not emp:
		frappe.throw(_("Employee {0} not found.").format(employee))
	if not emp.company:
		frappe.throw(_("Employee {0} has no Company set.").format(employee))

	policy_names = _matching_ppe_policies(emp.company, emp.department, emp.designation)

	merged = {}
	for policy_name in policy_names:
		policy = frappe.get_doc("PPE Policy", policy_name)
		for row in policy.items:
			if row.item_code in merged:
				merged[row.item_code]["quantity"] += row.quantity
			else:
				merged[row.item_code] = {
					"item_code": row.item_code,
					"item_name": row.item_name or row.item_code,
					"quantity": row.quantity,
				}
	return [row for row in merged.values() if row["quantity"] > 0]
```

- [ ] **Step 4: Run the test to confirm it passes**

Run:
```bash
bench --site david.local run-tests --app upande_stores --module upande_stores.api.test_ppe
```
Expected: PASS (or SKIP if the noted fixtures are genuinely absent).

- [ ] **Step 5: Commit**

```bash
cd ~/frappe/kaitet-bench/apps/upande_stores
git add upande_stores/upande_stores/api
git commit -m "feat: add get_ppe_requirements_for_onboarding API"
```

---

## Task 7: Employee Onboarding client script — "Fetch PPE Requirements"

**Files:**
- Create: `apps/upande_stores/upande_stores/upande_stores/public/js/employee_onboarding.js`
- Modify: `apps/upande_stores/upande_stores/upande_stores/hooks.py`

**Interfaces:**
- Consumes: `upande_stores.api.ppe.get_ppe_requirements_for_onboarding` (Task 6).
- Produces: nothing new for later tasks; Task 10 extends this same file.

- [ ] **Step 1: Create `public/js/employee_onboarding.js`**

```js
frappe.ui.form.on("Employee Onboarding", {
	refresh(frm) {
		frm.add_custom_button(
			__("Fetch PPE Requirements"),
			() => {
				if (!frm.doc.employee) {
					frappe.msgprint(__("Please select an Employee first."));
					return;
				}
				frappe.call({
					method: "upande_stores.api.ppe.get_ppe_requirements_for_onboarding",
					args: { employee: frm.doc.employee },
					callback: (r) => {
						if (!r.message || !r.message.length) {
							frappe.msgprint(
								__("No active PPE Policies found for this employee's company/department/designation.")
							);
							return;
						}
						frm.clear_table("custom_ppe_requirements");
						r.message.forEach((item) => {
							const row = frm.add_child("custom_ppe_requirements");
							row.item_code = item.item_code;
							row.item_name = item.item_name;
							row.quantity = item.quantity;
							row.issued = 0;
						});
						frm.refresh_field("custom_ppe_requirements");
						frappe.show_alert({
							message: __("{0} PPE item(s) fetched.", [r.message.length]),
							indicator: "green",
						});
					},
				});
			},
			__("PPE")
		);
	},
});
```

- [ ] **Step 2: Register it via `doctype_js` in `hooks.py`**

Find the existing (empty) `doctype_js`/no-op section near the top of
`upande_stores/hooks.py` and add:

```python
doctype_js = {"Employee Onboarding": "public/js/employee_onboarding.js"}
```

- [ ] **Step 3: Build assets and manually verify in the browser**

Run:
```bash
cd ~/frappe/kaitet-bench
bench build --app upande_stores
bench --site david.local clear-cache
```
Open an Employee Onboarding record in the browser, confirm a "PPE" button group
with "Fetch PPE Requirements" appears, and clicking it (with an Employee selected)
populates the `custom_ppe_requirements` grid.

- [ ] **Step 4: Commit**

```bash
cd ~/frappe/kaitet-bench/apps/upande_stores
git add upande_stores/upande_stores/public/js/employee_onboarding.js upande_stores/hooks.py
git commit -m "feat: add Fetch PPE Requirements button to Employee Onboarding"
```

---

## Task 8: Material Request — `custom_ppe_issuance` checkbox

**Files:**
- Modify: `apps/upande_stores/upande_stores/upande_stores/custom/material_request.json`

**Interfaces:**
- Produces: `Material Request.custom_ppe_issuance` (Check) — Tasks 9, 18, 22 set
  or read this fieldname.

- [ ] **Step 1: Open the file and add one entry to `custom_fields`**

Read the current file first (it already holds `custom_farm`, `custom_business_unit`,
`custom_employee_details`, `custom_employee_data`) and append this object to the
`custom_fields` array — do not remove or reorder the existing entries:

```json
  {
   "_assign": null, "_comments": null, "_liked_by": null, "_user_tags": null,
   "allow_in_quick_entry": 0, "allow_on_submit": 0, "bold": 0, "collapsible": 0,
   "collapsible_depends_on": null, "columns": 0,
   "creation": "2026-07-20 00:00:00.000000", "default": "0", "depends_on": null,
   "description": null, "docstatus": 0, "dt": "Material Request",
   "fetch_from": null, "fetch_if_empty": 0, "fieldname": "custom_ppe_issuance",
   "fieldtype": "Check", "hidden": 0, "hide_border": 0, "hide_days": 0,
   "hide_seconds": 0, "idx": 0, "ignore_user_permissions": 0,
   "ignore_xss_filter": 0, "in_global_search": 0, "in_list_view": 1,
   "in_preview": 0, "in_standard_filter": 1, "insert_after": "material_request_type",
   "is_system_generated": 0, "is_virtual": 0, "label": "PPE Issuance", "length": 0,
   "link_filters": null, "mandatory_depends_on": null,
   "modified": "2026-07-20 00:00:00.000000", "modified_by": "Administrator",
   "module": "Upande Stores", "name": "Material Request-custom_ppe_issuance",
   "no_copy": 0, "non_negative": 0, "options": null, "owner": "Administrator",
   "permlevel": 0, "placeholder": null, "precision": "", "print_hide": 0,
   "print_hide_if_no_value": 0, "print_width": null, "read_only": 1,
   "read_only_depends_on": null, "report_hide": 0, "reqd": 0, "search_index": 0,
   "show_dashboard": 0, "sort_options": 0, "translatable": 0, "unique": 0,
   "width": null
  }
```

- [ ] **Step 2: Migrate and verify**

```bash
cd ~/frappe/kaitet-bench
bench --site david.local migrate
bench --site david.local console
```
```python
import frappe
frappe.get_meta("Material Request").get_field("custom_ppe_issuance").read_only  # 1
exit()
```

- [ ] **Step 3: Commit**

```bash
cd ~/frappe/kaitet-bench/apps/upande_stores
git add upande_stores/upande_stores/custom/material_request.json
git commit -m "feat: add PPE Issuance checkbox to Material Request"
```

---

## Task 9: API — `create_ppe_onboarding_material_request`

**Files:**
- Modify: `apps/upande_stores/upande_stores/upande_stores/api/ppe.py`
- Modify: `apps/upande_stores/upande_stores/upande_stores/api/test_ppe.py`

**Interfaces:**
- Consumes: `Employee Onboarding.custom_ppe_requirements`/`.custom_ppe_material_request`
  (Task 5), `Material Request.custom_ppe_issuance` (Task 8).
- Produces: `upande_stores.api.ppe.create_ppe_onboarding_material_request(onboarding, employee, items)`
  → `str` (Material Request name). Task 10's client script depends on this
  exact signature (named args `onboarding`, `employee`, `items` — `items` a JSON
  string of `{item_code, quantity}` dicts).

- [ ] **Step 1: Write the failing test**, appended to `api/test_ppe.py`:

```python
import json

from upande_stores.api.ppe import create_ppe_onboarding_material_request


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
	def setUp(self):
		employees = get_test_employees(count=1)
		if not employees:
			self.skipTest("Need at least 1 Active Employee record on this site.")
		self.employee = employees[0]
		self.onboarding = make_draft_employee_onboarding(self.employee)

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
```

(Add the `import json` and `create_ppe_onboarding_material_request` import at the
top of the file alongside the existing imports.)

- [ ] **Step 2: Run to confirm it fails**

```bash
bench --site david.local run-tests --app upande_stores --module upande_stores.api.test_ppe
```
Expected: FAIL — `ImportError: cannot import name 'create_ppe_onboarding_material_request'`.

- [ ] **Step 3: Add the function to `api/ppe.py`**

```python
import json

from frappe.utils import today
```
(add these two imports to the top of the file, next to the existing `import frappe`
/ `from frappe import _`), then append:

```python
@frappe.whitelist()
def create_ppe_onboarding_material_request(onboarding, employee, items):
	onboarding_employee = frappe.db.get_value("Employee Onboarding", onboarding, "employee")
	if not onboarding_employee:
		frappe.throw(_("Employee Onboarding {0} not found.").format(onboarding))
	if onboarding_employee != employee:
		frappe.throw(_("Employee does not match the Employee Onboarding record."))

	existing_mr = frappe.db.get_value(
		"Employee Onboarding", onboarding, "custom_ppe_material_request"
	)
	if existing_mr:
		frappe.throw(
			_("A PPE Material Request ({0}) already exists for this onboarding.").format(existing_mr)
		)

	if isinstance(items, str):
		items = json.loads(items)
	if not items:
		frappe.throw(_("Items list is empty."))

	emp = frappe.db.get_value(
		"Employee", employee, ["company", "custom_farm", "custom_business_unit"], as_dict=True
	)
	if not emp or not emp.company:
		frappe.throw(_("Employee {0} has no Company set.").format(employee))

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

	frappe.db.set_value("Employee Onboarding", onboarding, "custom_ppe_material_request", mr.name)
	return mr.name
```

- [ ] **Step 4: Run to confirm it passes**

```bash
bench --site david.local run-tests --app upande_stores --module upande_stores.api.test_ppe
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/frappe/kaitet-bench/apps/upande_stores
git add upande_stores/upande_stores/api
git commit -m "feat: add create_ppe_onboarding_material_request API"
```

---

## Task 10: Employee Onboarding client script — "Create PPE Issuance Request"

**Files:**
- Modify: `apps/upande_stores/upande_stores/upande_stores/public/js/employee_onboarding.js`

**Interfaces:**
- Consumes: `upande_stores.api.ppe.create_ppe_onboarding_material_request` (Task 9).

- [ ] **Step 1: Extend the `refresh` handler** from Task 7 — add this block right
  after the existing `frm.add_custom_button(__("Fetch PPE Requirements"), ...)`
  call, still inside `refresh(frm) { ... }`:

```js
		if (
			!frm.is_new() &&
			frm.doc.custom_ppe_requirements &&
			frm.doc.custom_ppe_requirements.length > 0 &&
			!frm.doc.custom_ppe_material_request
		) {
			frm.add_custom_button(
				__("Create PPE Issuance Request"),
				() => {
					frappe.confirm(
						__("Create a PPE Material Issue Request for {0}?", [
							frm.doc.employee_name || frm.doc.employee,
						]),
						() => {
							frappe.call({
								method: "upande_stores.api.ppe.create_ppe_onboarding_material_request",
								args: {
									onboarding: frm.doc.name,
									employee: frm.doc.employee,
									items: JSON.stringify(
										frm.doc.custom_ppe_requirements
											.filter((r) => r.item_code && r.quantity > 0)
											.map((r) => ({ item_code: r.item_code, quantity: r.quantity }))
									),
								},
								callback: (r) => {
									if (r.message) {
										frappe.show_alert({
											message: __("Material Request {0} created", [r.message]),
											indicator: "green",
										});
										frm.reload_doc();
									}
								},
							});
						}
					);
				},
				__("PPE")
			);
		}
```

- [ ] **Step 2: Build and manually verify**

```bash
cd ~/frappe/kaitet-bench
bench build --app upande_stores
bench --site david.local clear-cache
```
On a saved Employee Onboarding with fetched PPE requirements, confirm the
"Create PPE Issuance Request" button appears, and clicking it creates a Material
Request with `PPE Issuance` checked and routes back correctly (`frm.reload_doc()`
shows the link filled in).

- [ ] **Step 3: Commit**

```bash
cd ~/frappe/kaitet-bench/apps/upande_stores
git add upande_stores/upande_stores/public/js/employee_onboarding.js
git commit -m "feat: add Create PPE Issuance Request button to Employee Onboarding"
```

---

## Task 11: `upande_hr` — Employee PPE History

**Files (in the `upande_hr` app):**
- Create: `apps/upande_hr/upande_hr/upande_hr/custom/employee.json`
- Create: `apps/upande_hr/upande_hr/upande_hr/doctype/employee_ppe_history/__init__.py` (empty)
- Create: `apps/upande_hr/upande_hr/upande_hr/doctype/employee_ppe_history/employee_ppe_history.json`
- Create: `apps/upande_hr/upande_hr/upande_hr/doctype/employee_ppe_history/employee_ppe_history.py`
- Modify: `apps/upande_hr/upande_hr/hooks.py`

**Interfaces:**
- Produces: `Employee PPE History` doctype (fields `ppe_assignment`, `item_code`,
  `quantity`, `issue_date`, `expiry_date`, `status`, `stock_entry`, `ppe_inspection`,
  `last_inspection_date`, `last_inspection_status`), `Employee.custom_ppe_history`
  (Table). Task 13 (in `upande_stores`) writes to this doctype by name.
- Note: `ppe_assignment`'s `options` is `Employee PPE Assignment`, a doctype that
  lives in `upande_stores`, not `upande_hr` — this is why `required_apps` is set
  below.

- [ ] **Step 1: Directory doesn't exist yet — create it**

```bash
mkdir -p ~/frappe/kaitet-bench/apps/upande_hr/upande_hr/upande_hr/doctype/employee_ppe_history
```

- [ ] **Step 2: `employee_ppe_history.json`**

```json
{
 "actions": [],
 "allow_rename": 1,
 "creation": "2026-07-20 00:00:00.000000",
 "doctype": "DocType",
 "editable_grid": 1,
 "engine": "InnoDB",
 "field_order": [
  "ppe_assignment",
  "item_code",
  "quantity",
  "issue_date",
  "expiry_date",
  "status",
  "stock_entry",
  "column_break_qqmj",
  "ppe_inspection",
  "last_inspection_date",
  "last_inspection_status"
 ],
 "fields": [
  {
   "fieldname": "ppe_assignment",
   "fieldtype": "Link",
   "in_list_view": 1,
   "label": "PPE Assignment",
   "options": "Employee PPE Assignment"
  },
  {
   "fieldname": "item_code",
   "fieldtype": "Link",
   "in_list_view": 1,
   "label": "Item Code",
   "options": "Item"
  },
  {
   "fieldname": "quantity",
   "fieldtype": "Float",
   "in_list_view": 1,
   "label": "Quantity",
   "precision": "6"
  },
  {
   "fieldname": "issue_date",
   "fieldtype": "Date",
   "in_list_view": 1,
   "label": "Issue Date"
  },
  {
   "fieldname": "expiry_date",
   "fieldtype": "Date",
   "in_list_view": 1,
   "label": "Expiry Date"
  },
  {
   "fieldname": "status",
   "fieldtype": "Select",
   "in_list_view": 1,
   "label": "Status",
   "options": "Active\nInactive\nExpired\nReturned"
  },
  {
   "fieldname": "stock_entry",
   "fieldtype": "Link",
   "label": "Stock Entry",
   "options": "Stock Entry"
  },
  {
   "fieldname": "column_break_qqmj",
   "fieldtype": "Column Break"
  },
  {
   "fieldname": "ppe_inspection",
   "fieldtype": "Link",
   "label": "PPE Inspection",
   "options": "PPE Inspection"
  },
  {
   "fieldname": "last_inspection_date",
   "fieldtype": "Date",
   "label": "Last Inspection Date"
  },
  {
   "fieldname": "last_inspection_status",
   "fieldtype": "Data",
   "label": "Last Inspection Status"
  }
 ],
 "grid_page_length": 50,
 "index_web_pages_for_search": 1,
 "istable": 1,
 "links": [],
 "modified": "2026-07-20 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Upande Hr",
 "name": "Employee PPE History",
 "owner": "Administrator",
 "permissions": [],
 "row_format": "Dynamic",
 "sort_field": "modified",
 "sort_order": "DESC",
 "states": []
}
```

- [ ] **Step 3: `employee_ppe_history.py`**

```python
from frappe.model.document import Document


class EmployeePPEHistory(Document):
	pass
```

- [ ] **Step 4: `custom/employee.json`**

```json
{
 "custom_fields": [
  {
   "_assign": null, "_comments": null, "_liked_by": null, "_user_tags": null,
   "allow_in_quick_entry": 0, "allow_on_submit": 0, "bold": 0, "collapsible": 0,
   "collapsible_depends_on": null, "columns": 0,
   "creation": "2026-07-20 00:00:00.000000", "default": null, "depends_on": null,
   "description": null, "docstatus": 0, "dt": "Employee", "fetch_from": null,
   "fetch_if_empty": 0, "fieldname": "custom_ppe_issuance", "fieldtype": "Section Break",
   "hidden": 0, "hide_border": 0, "hide_days": 0, "hide_seconds": 0, "idx": 0,
   "ignore_user_permissions": 0, "ignore_xss_filter": 0, "in_global_search": 0,
   "in_list_view": 0, "in_preview": 0, "in_standard_filter": 0,
   "insert_after": "custom_company_assets", "is_system_generated": 0,
   "is_virtual": 0, "label": "PPE Issuance", "length": 0, "link_filters": null,
   "mandatory_depends_on": null, "modified": "2026-07-20 00:00:00.000000",
   "modified_by": "Administrator", "module": "Upande Hr",
   "name": "Employee-custom_ppe_issuance", "no_copy": 0, "non_negative": 0,
   "options": null, "owner": "Administrator", "permlevel": 0, "placeholder": null,
   "precision": "", "print_hide": 0, "print_hide_if_no_value": 0,
   "print_width": null, "read_only": 0, "read_only_depends_on": null,
   "report_hide": 0, "reqd": 0, "search_index": 0, "show_dashboard": 0,
   "sort_options": 0, "translatable": 0, "unique": 0, "width": null
  },
  {
   "_assign": null, "_comments": null, "_liked_by": null, "_user_tags": null,
   "allow_in_quick_entry": 0, "allow_on_submit": 0, "bold": 0, "collapsible": 0,
   "collapsible_depends_on": null, "columns": 0,
   "creation": "2026-07-20 00:00:00.000000", "default": null, "depends_on": null,
   "description": null, "docstatus": 0, "dt": "Employee", "fetch_from": null,
   "fetch_if_empty": 0, "fieldname": "custom_ppe_history", "fieldtype": "Table",
   "hidden": 0, "hide_border": 0, "hide_days": 0, "hide_seconds": 0, "idx": 0,
   "ignore_user_permissions": 0, "ignore_xss_filter": 0, "in_global_search": 0,
   "in_list_view": 0, "in_preview": 0, "in_standard_filter": 0,
   "insert_after": "custom_ppe_issuance", "is_system_generated": 0,
   "is_virtual": 0, "label": "PPE History", "length": 0, "link_filters": null,
   "mandatory_depends_on": null, "modified": "2026-07-20 00:00:00.000000",
   "modified_by": "Administrator", "module": "Upande Hr",
   "name": "Employee-custom_ppe_history", "no_copy": 0, "non_negative": 0,
   "options": "Employee PPE History", "owner": "Administrator", "permlevel": 0,
   "placeholder": null, "precision": "", "print_hide": 0,
   "print_hide_if_no_value": 0, "print_width": null, "read_only": 0,
   "read_only_depends_on": null, "report_hide": 0, "reqd": 0, "search_index": 0,
   "show_dashboard": 0, "sort_options": 0, "translatable": 0, "unique": 0,
   "width": null
  }
 ],
 "custom_perms": [],
 "doctype": "Employee",
 "links": [],
 "property_setters": [],
 "sync_on_migrate": 1
}
```

- [ ] **Step 5: Declare the cross-app dependency in `upande_hr/hooks.py`** — find
  the commented-out `# required_apps = []` near the top and replace with:

```python
required_apps = ["upande_stores"]
```

- [ ] **Step 6: Migrate and verify**

```bash
cd ~/frappe/kaitet-bench
bench --site david.local migrate
bench --site david.local console
```
```python
import frappe
frappe.get_meta("Employee").get_field("custom_ppe_history").options  # 'Employee PPE History'
frappe.get_meta("Employee PPE History").get_field("ppe_assignment").options  # 'Employee PPE Assignment'
exit()
```

- [ ] **Step 7: Commit**

```bash
cd ~/frappe/kaitet-bench/apps/upande_hr
git add upande_hr/upande_hr/custom/employee.json upande_hr/upande_hr/doctype/employee_ppe_history upande_hr/hooks.py
git commit -m "feat: add Employee PPE History doctype and Employee PPE History tab"
```

---

## Task 12: Employee PPE Assignment — doctype schema

**Files:**
- Create: `apps/upande_stores/upande_stores/upande_stores/doctype/employee_ppe_assignment/__init__.py` (empty)
- Create: `apps/upande_stores/upande_stores/upande_stores/doctype/employee_ppe_assignment/employee_ppe_assignment.json`

**Interfaces:**
- Produces: `Employee PPE Assignment` doctype (all fields below) — Tasks 13, 14,
  16, 18, 19, 20, 21 all read/write this doctype's fields by exact name.

- [ ] **Step 1: `employee_ppe_assignment.json`**

```json
{
 "actions": [],
 "allow_rename": 1,
 "autoname": "naming_series:",
 "creation": "2026-07-20 00:00:00.000000",
 "doctype": "DocType",
 "engine": "InnoDB",
 "field_order": [
  "naming_series",
  "employee",
  "employee_name",
  "item_code",
  "item_name",
  "quantity",
  "company",
  "farm",
  "business_unit",
  "column_break_xbtf",
  "issue_date",
  "lifespan_months",
  "expiry_date",
  "stock_entry",
  "status",
  "returned_date",
  "last_inspection_date",
  "last_inspection_status",
  "last_inspection",
  "replacement_requested",
  "replacement_section",
  "replacement_material_request",
  "replacement_purchase_request",
  "replacement_assignment"
 ],
 "fields": [
  {"fieldname": "naming_series", "fieldtype": "Select", "hidden": 1, "label": "Naming Series", "options": "PPE-ASSIGN-.YYYY.-"},
  {"fieldname": "employee", "fieldtype": "Link", "in_standard_filter": 1, "label": "Employee", "options": "Employee", "read_only": 1, "reqd": 1, "search_index": 1},
  {"fetch_from": "employee.employee_name", "fieldname": "employee_name", "fieldtype": "Data", "label": "Employee Name"},
  {"fieldname": "item_code", "fieldtype": "Link", "in_list_view": 1, "label": "Item Code", "options": "Item", "read_only": 1, "reqd": 1, "search_index": 1},
  {"fetch_from": "item_code.item_name", "fieldname": "item_name", "fieldtype": "Data", "label": "Item Name"},
  {"fieldname": "quantity", "fieldtype": "Float", "label": "Quantity", "precision": "6", "reqd": 1},
  {"fieldname": "company", "fieldtype": "Link", "in_standard_filter": 1, "label": "Company", "options": "Company", "read_only": 1, "reqd": 1},
  {"fieldname": "farm", "fieldtype": "Link", "label": "Farm", "options": "Farm"},
  {"fieldname": "business_unit", "fieldtype": "Link", "label": "Business Unit", "options": "Business Unit"},
  {"fieldname": "column_break_xbtf", "fieldtype": "Column Break"},
  {"fieldname": "issue_date", "fieldtype": "Date", "label": "Issue Date", "read_only": 1, "reqd": 1},
  {"fieldname": "lifespan_months", "fieldtype": "Int", "label": "Lifespan (Months)", "read_only": 1},
  {"fieldname": "expiry_date", "fieldtype": "Date", "label": "Estimated Expiry", "read_only": 1, "search_index": 1},
  {"fieldname": "stock_entry", "fieldtype": "Link", "label": "Stock Entry", "options": "Stock Entry", "read_only": 1},
  {"fieldname": "status", "fieldtype": "Select", "in_standard_filter": 1, "label": "Status", "options": "Active\nInactive\nExpired\nReturned", "reqd": 1, "search_index": 1},
  {"depends_on": "eval:doc.status == \"Returned\"", "fieldname": "returned_date", "fieldtype": "Date", "label": "Returned Date"},
  {"fieldname": "last_inspection_date", "fieldtype": "Date", "label": "Last Inspection Date", "read_only": 1},
  {"fieldname": "last_inspection_status", "fieldtype": "Select", "label": "Last Inspection Status", "options": "OK\nWorn Out\nLost", "read_only": 1},
  {"fieldname": "last_inspection", "fieldtype": "Link", "label": "Last Inspection", "options": "PPE Inspection", "read_only": 1},
  {"default": "0", "fieldname": "replacement_requested", "fieldtype": "Check", "hidden": 1, "label": "Replacement Requested"},
  {"depends_on": "eval:doc.replacement_requested", "fieldname": "replacement_section", "fieldtype": "Section Break", "label": "Replacement Tracking"},
  {"fieldname": "replacement_material_request", "fieldtype": "Link", "label": "Replacement Material Request", "options": "Material Request", "read_only": 1},
  {"fieldname": "replacement_purchase_request", "fieldtype": "Link", "label": "Purchase Request", "options": "Material Request", "read_only": 1},
  {"fieldname": "replacement_assignment", "fieldtype": "Link", "label": "Replacement Assignment", "options": "Employee PPE Assignment", "read_only": 1}
 ],
 "grid_page_length": 50,
 "index_web_pages_for_search": 1,
 "links": [],
 "modified": "2026-07-20 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Upande Stores",
 "name": "Employee PPE Assignment",
 "naming_rule": "By \"Naming Series\" field",
 "owner": "Administrator",
 "permissions": [
  {"create": 1, "delete": 1, "email": 1, "export": 1, "print": 1, "read": 1, "report": 1, "role": "System Manager", "share": 1, "write": 1},
  {"create": 1, "email": 1, "export": 1, "print": 1, "read": 1, "report": 1, "role": "HR Manager", "share": 1, "write": 1},
  {"create": 1, "email": 1, "export": 1, "print": 1, "read": 1, "report": 1, "role": "Farm Manager", "share": 1, "write": 1}
 ],
 "row_format": "Dynamic",
 "sort_field": "modified",
 "sort_order": "DESC",
 "states": [
  {"color": "Green", "title": "Active"},
  {"color": "Red", "title": "Expired"},
  {"color": "Yellow", "title": "Returned"}
 ],
 "track_changes": 1
}
```

Note the deliberate change from the old build: `farm`/`business_unit`/`company`
carry **no** `fetch_from` here (the old build's `fetch_from` on these fields was
unreliable for the same reason `Employee PPE History`'s was — see Task 13, which
sets them explicitly instead).

- [ ] **Step 2: Migrate and verify**

```bash
cd ~/frappe/kaitet-bench
bench --site david.local migrate
```
Expected: no error (Task 13 adds the controller next — the doctype needs a `.py`
file to migrate cleanly, so do Task 13's Step 1 file creation before running this
migrate if the bench errors on a missing controller module).

- [ ] **Step 3: Commit** (fold into Task 13's commit — this doctype has no
  functioning controller yet, committing schema-only would leave the tree in a
  broken migrate state)

---

## Task 13: Employee PPE Assignment — controller (due date, History sync)

**Files:**
- Create: `apps/upande_stores/upande_stores/upande_stores/doctype/employee_ppe_assignment/employee_ppe_assignment.py`
- Create: `apps/upande_stores/upande_stores/upande_stores/doctype/employee_ppe_assignment/test_employee_ppe_assignment.py`

**Interfaces:**
- Consumes: `Employee PPE Assignment` schema (Task 12), `Employee PPE History`
  (Task 11, optional — guarded by an installed-apps check).
- Produces: `EmployeePPEAssignment.validate()` (computes `expiry_date`),
  `.on_insert()` / `.on_update()` (History sync) — Task 14's `create_ppe_assignments`
  relies on `validate()` computing `expiry_date` so it doesn't have to.

- [ ] **Step 1: Write the failing tests**

```python
import frappe
from frappe.tests import IntegrationTestCase

from upande_stores.tests.test_helpers import get_test_employees, make_ppe_item


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
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd ~/frappe/kaitet-bench
bench --site david.local migrate
bench --site david.local run-tests --app upande_stores --module upande_stores.upande_stores.doctype.employee_ppe_assignment.test_employee_ppe_assignment
```
Expected: FAIL — no controller module / `AttributeError` from the stub-less
DocType (Frappe generates a default pass-through, so this may actually just fail
the expiry-date assertion instead — either way, not yet passing).

- [ ] **Step 3: Write `employee_ppe_assignment.py`**

```python
import frappe
from frappe.model.document import Document
from frappe.utils import add_months


class EmployeePPEAssignment(Document):
	def validate(self):
		if self.issue_date and self.lifespan_months and not self.expiry_date:
			self.expiry_date = add_months(self.issue_date, int(self.lifespan_months))

	def on_insert(self):
		self._sync_history_row()

	def on_update(self):
		if "upande_hr" not in frappe.get_installed_apps():
			return
		frappe.db.set_value(
			"Employee PPE History",
			{"ppe_assignment": self.name, "parent": self.employee},
			{
				"status": self.status,
				"expiry_date": self.expiry_date,
				"last_inspection_date": self.last_inspection_date,
				"last_inspection_status": self.last_inspection_status,
			},
		)

	def _sync_history_row(self):
		if "upande_hr" not in frappe.get_installed_apps():
			return
		if frappe.db.exists("Employee PPE History", {"ppe_assignment": self.name, "parent": self.employee}):
			return
		frappe.get_doc(
			{
				"doctype": "Employee PPE History",
				"parent": self.employee,
				"parenttype": "Employee",
				"parentfield": "custom_ppe_history",
				"ppe_assignment": self.name,
				"item_code": self.item_code,
				"quantity": self.quantity,
				"issue_date": self.issue_date,
				"expiry_date": self.expiry_date,
				"status": self.status,
				"stock_entry": self.stock_entry,
			}
		).insert(ignore_permissions=True)
```

- [ ] **Step 4: Run to confirm it passes**

```bash
bench --site david.local run-tests --app upande_stores --module upande_stores.upande_stores.doctype.employee_ppe_assignment.test_employee_ppe_assignment
```
Expected: PASS.

- [ ] **Step 5: Commit** (this is where Task 12's schema is committed too)

```bash
cd ~/frappe/kaitet-bench/apps/upande_stores
git add upande_stores/upande_stores/doctype/employee_ppe_assignment
git commit -m "feat: add Employee PPE Assignment doctype with History sync"
```

---

## Task 14: Stock Entry override — create Employee PPE Assignments on issue

**Files:**
- Modify: `apps/upande_stores/upande_stores/upande_stores/overrides/stock_entry.py`
- Modify: `apps/upande_stores/upande_stores/upande_stores/overrides/test_stock_entry.py`
- Modify: `apps/upande_stores/upande_stores/upande_stores/hooks.py`

**Interfaces:**
- Consumes: `Item.custom_is_ppe`/`.custom_ppe_lifespan` (Task 2), `Employee PPE
  Assignment` (Tasks 12–13), `Material Request.custom_ppe_issuance` (Task 8),
  the existing `_resolve_material_request(doc)` helper already in this file.
- Produces: `upande_stores.overrides.stock_entry.create_ppe_assignments(doc, method=None)`.

- [ ] **Step 1: Write the failing tests**, appended to `test_stock_entry.py`
  (reuse the existing `IntegrationTestStockEntryEmployeeLock` fixtures/imports —
  add a new test class in the same file):

```python
from upande_stores.tests.test_helpers import make_ppe_item


class IntegrationTestStockEntryPPEAssignmentCreation(IntegrationTestCase):
	def setUp(self):
		farm, business_unit = get_test_farm_and_business_unit()
		if not farm or not business_unit:
			self.skipTest("No Farm/Business Unit record on this site to build a valid test document.")
		employees = get_test_employees(count=1)
		if not employees:
			self.skipTest("Need at least 1 Active Employee record on this site.")
		self.employee = employees[0]

	def _issue_ppe_item(self, item_code):
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
		item_code = make_ppe_item(lifespan_months=6)
		self._issue_ppe_item(item_code)

		with self.assertRaises(frappe.ValidationError):
			self._issue_ppe_item(item_code)

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
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd ~/frappe/kaitet-bench
bench --site david.local run-tests --app upande_stores --module upande_stores.overrides.test_stock_entry
```
Expected: FAIL — no `Employee PPE Assignment` rows get created yet.

- [ ] **Step 3: Add `create_ppe_assignments` to `overrides/stock_entry.py`**,
  appended after the existing `unlock_issued_employee` function (reusing the
  file's existing `_resolve_material_request` helper and `frappe`/`_` imports):

```python
def create_ppe_assignments(doc, method=None):
	"""Stock Entry on_submit: for every custom_is_ppe item issued to
	doc.bio_employee, create an Employee PPE Assignment. No-ops for anything
	that isn't a Material Issue against a bio_employee -- mirrors
	lock_issued_employee's own scoping."""
	if doc.stock_entry_type != "Material Issue" or not doc.get("bio_employee"):
		return

	employee = doc.bio_employee
	employee_name = frappe.db.get_value("Employee", employee, "employee_name")

	material_request = _resolve_material_request(doc)
	is_ppe_issuance = bool(
		material_request
		and frappe.db.get_value("Material Request", material_request, "custom_ppe_issuance")
	)

	for row in doc.items:
		if not row.item_code or not row.qty or row.qty <= 0:
			continue

		is_ppe, lifespan = frappe.db.get_value(
			"Item", row.item_code, ["custom_is_ppe", "custom_ppe_lifespan"]
		)
		if not is_ppe:
			continue
		if not lifespan or lifespan <= 0:
			frappe.throw(_("PPE Lifespan (Months) not set for item {0}").format(row.item_code))

		if frappe.db.exists(
			"Employee PPE Assignment",
			{"employee": employee, "item_code": row.item_code, "status": "Active"},
		):
			frappe.throw(
				_("{0} is already actively assigned to {1}").format(row.item_code, employee_name)
			)

		new_assignment = frappe.get_doc(
			{
				"doctype": "Employee PPE Assignment",
				"employee": employee,
				"employee_name": employee_name,
				"item_code": row.item_code,
				"quantity": row.qty,
				"issue_date": doc.posting_date,
				"lifespan_months": lifespan,
				"stock_entry": doc.name,
				"company": doc.company,
				"farm": doc.get("custom_farm"),
				"business_unit": doc.get("custom_business_unit"),
				"status": "Active",
			}
		).insert(ignore_permissions=True)

		if is_ppe_issuance:
			old_assignments = frappe.get_all(
				"Employee PPE Assignment",
				filters={
					"replacement_material_request": material_request,
					"employee": employee,
					"item_code": row.item_code,
					"name": ["!=", new_assignment.name],
				},
				pluck="name",
			)
			for old_name in old_assignments:
				frappe.db.set_value(
					"Employee PPE Assignment", old_name, "replacement_assignment", new_assignment.name
				)
```

- [ ] **Step 4: Wire it in `hooks.py`** — find the existing `doc_events["Stock
  Entry"]["on_submit"]` entry (currently a single string,
  `"upande_stores.overrides.stock_entry.lock_issued_employee"`) and change it to
  a list:

```python
	"Stock Entry": {
		"on_submit": [
			"upande_stores.overrides.stock_entry.lock_issued_employee",
			"upande_stores.overrides.stock_entry.create_ppe_assignments",
		],
		"on_cancel": "upande_stores.overrides.stock_entry.unlock_issued_employee",
	},
```

- [ ] **Step 5: Run to confirm it passes**

```bash
bench --site david.local run-tests --app upande_stores --module upande_stores.overrides.test_stock_entry
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd ~/frappe/kaitet-bench/apps/upande_stores
git add upande_stores/upande_stores/overrides/stock_entry.py upande_stores/upande_stores/overrides/test_stock_entry.py upande_stores/hooks.py
git commit -m "feat: create Employee PPE Assignment on PPE Stock Entry submit"
```

---

## Task 15: PPE Inspection + PPE Inspection Item doctypes

**Files:**
- Create: `apps/upande_stores/upande_stores/upande_stores/doctype/ppe_inspection/__init__.py` (empty)
- Create: `apps/upande_stores/upande_stores/upande_stores/doctype/ppe_inspection/ppe_inspection.json`
- Create: `apps/upande_stores/upande_stores/upande_stores/doctype/ppe_inspection_item/__init__.py` (empty)
- Create: `apps/upande_stores/upande_stores/upande_stores/doctype/ppe_inspection_item/ppe_inspection_item.json`
- Create: `apps/upande_stores/upande_stores/upande_stores/doctype/ppe_inspection_item/ppe_inspection_item.py`

**Interfaces:**
- Produces: `PPE Inspection` / `PPE Inspection Item` schemas — Task 16's
  controller and Task 17's client script depend on these exact fieldnames.

- [ ] **Step 1: `ppe_inspection_item.json`**

```json
{
 "actions": [],
 "allow_rename": 1,
 "creation": "2026-07-20 00:00:00.000000",
 "doctype": "DocType",
 "editable_grid": 1,
 "engine": "InnoDB",
 "field_order": [
  "employee_ppe_assignment",
  "item_code",
  "item_name",
  "issue_date",
  "current_status",
  "other_reason",
  "comments",
  "update_assignment",
  "inspection_result_date"
 ],
 "fields": [
  {"fieldname": "employee_ppe_assignment", "fieldtype": "Link", "in_list_view": 1, "label": "Employee PPE Assignment", "options": "Employee PPE Assignment", "reqd": 1},
  {"fetch_from": "employee_ppe_assignment.item_code", "fieldname": "item_code", "fieldtype": "Link", "in_list_view": 1, "label": "Item Code", "options": "Item", "read_only": 1, "reqd": 1},
  {"fetch_from": "item_code.item_name", "fieldname": "item_name", "fieldtype": "Data", "in_list_view": 1, "label": "Item Name", "read_only": 1},
  {"fetch_from": "employee_ppe_assignment.issue_date", "fieldname": "issue_date", "fieldtype": "Date", "in_list_view": 1, "label": "Issue Date", "read_only": 1},
  {"fieldname": "current_status", "fieldtype": "Select", "in_list_view": 1, "label": "Current Status", "options": "OK\nWorn Out\nLost", "reqd": 1},
  {"fieldname": "other_reason", "fieldtype": "Data", "label": "Other Reason"},
  {"fieldname": "comments", "fieldtype": "Small Text", "label": "Comments"},
  {"default": "1", "fieldname": "update_assignment", "fieldtype": "Check", "hidden": 1, "label": "Update Assignment"},
  {"default": "Today", "fieldname": "inspection_result_date", "fieldtype": "Date", "label": "Inspection Result Date", "read_only": 1}
 ],
 "grid_page_length": 50,
 "index_web_pages_for_search": 1,
 "istable": 1,
 "links": [],
 "modified": "2026-07-20 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Upande Stores",
 "name": "PPE Inspection Item",
 "owner": "Administrator",
 "permissions": [],
 "row_format": "Dynamic",
 "sort_field": "modified",
 "sort_order": "DESC",
 "states": []
}
```

- [ ] **Step 2: `ppe_inspection_item.py`**

```python
from frappe.model.document import Document


class PPEInspectionItem(Document):
	pass
```

- [ ] **Step 3: `ppe_inspection.json`**

```json
{
 "actions": [],
 "allow_rename": 1,
 "autoname": "naming_series:",
 "creation": "2026-07-20 00:00:00.000000",
 "doctype": "DocType",
 "engine": "InnoDB",
 "field_order": [
  "section_break_1vy2",
  "naming_series",
  "employee",
  "employee_name",
  "supervisor",
  "amended_from",
  "column_break_jabi",
  "farm",
  "company",
  "inspection_date",
  "remarks",
  "ppe_items_inspected_section",
  "items_inspected"
 ],
 "fields": [
  {"fieldname": "section_break_1vy2", "fieldtype": "Section Break"},
  {"fieldname": "naming_series", "fieldtype": "Select", "label": "Naming Series", "options": "PPE-INSPECT-.YYYY.-"},
  {"fieldname": "employee", "fieldtype": "Link", "in_list_view": 1, "in_standard_filter": 1, "label": "Employee", "options": "Employee", "reqd": 1},
  {"fetch_from": "employee.employee_name", "fieldname": "employee_name", "fieldtype": "Data", "label": "Employee Name", "read_only": 1},
  {"fieldname": "supervisor", "fieldtype": "Link", "label": "Supervisor", "options": "Employee", "reqd": 1},
  {"fieldname": "amended_from", "fieldtype": "Link", "label": "Amended From", "no_copy": 1, "options": "PPE Inspection", "print_hide": 1, "read_only": 1, "search_index": 1},
  {"fieldname": "column_break_jabi", "fieldtype": "Column Break"},
  {"fieldname": "farm", "fieldtype": "Link", "in_filter": 1, "label": "Farm", "options": "Farm", "reqd": 1},
  {"fetch_from": "farm.company", "fieldname": "company", "fieldtype": "Link", "label": "Company", "options": "Company"},
  {"default": "Today", "fieldname": "inspection_date", "fieldtype": "Date", "label": "Inspection Date", "reqd": 1},
  {"fieldname": "remarks", "fieldtype": "Small Text", "label": "Remarks"},
  {"fieldname": "ppe_items_inspected_section", "fieldtype": "Section Break", "label": "PPE Items Inspected"},
  {"fieldname": "items_inspected", "fieldtype": "Table", "label": "Items Inspected", "options": "PPE Inspection Item"}
 ],
 "grid_page_length": 50,
 "index_web_pages_for_search": 1,
 "is_submittable": 1,
 "links": [],
 "modified": "2026-07-20 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Upande Stores",
 "name": "PPE Inspection",
 "naming_rule": "By \"Naming Series\" field",
 "owner": "Administrator",
 "permissions": [
  {"amend": 1, "cancel": 1, "create": 1, "delete": 1, "email": 1, "export": 1, "print": 1, "read": 1, "report": 1, "role": "System Manager", "share": 1, "submit": 1, "write": 1},
  {"amend": 1, "cancel": 1, "create": 1, "email": 1, "export": 1, "print": 1, "read": 1, "report": 1, "role": "HR Manager", "share": 1, "submit": 1, "write": 1},
  {"amend": 1, "cancel": 1, "create": 1, "email": 1, "export": 1, "print": 1, "read": 1, "report": 1, "role": "Farm Manager", "share": 1, "submit": 1, "write": 1}
 ],
 "row_format": "Dynamic",
 "sort_field": "modified",
 "sort_order": "DESC",
 "states": [],
 "track_changes": 1
}
```

- [ ] **Step 4: Migrate**

```bash
cd ~/frappe/kaitet-bench
bench --site david.local migrate
```
Expected: no error (a controller module is required next — see Task 16 before
migrating if this errors on a missing `.py` file).

- [ ] **Step 5: Commit** (fold into Task 16's commit for the same reason as
  Task 12/13 — schema alone won't migrate cleanly without a controller module)

---

## Task 16: PPE Inspection controller — update assignment on submit

**Files:**
- Create: `apps/upande_stores/upande_stores/upande_stores/doctype/ppe_inspection/ppe_inspection.py`
- Create: `apps/upande_stores/upande_stores/upande_stores/doctype/ppe_inspection/test_ppe_inspection.py`

**Interfaces:**
- Consumes: `Employee PPE Assignment` (Tasks 12–13), `PPE Inspection`/`PPE
  Inspection Item` (Task 15).
- Produces: `PPEInspection.on_submit()` — sets `Employee PPE Assignment.status`
  to `Inactive` on `Lost`/`Worn Out`, back to `Active` on `OK`.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd ~/frappe/kaitet-bench
bench --site david.local migrate
bench --site david.local run-tests --app upande_stores --module upande_stores.upande_stores.doctype.ppe_inspection.test_ppe_inspection
```

- [ ] **Step 3: Write `ppe_inspection.py`**

```python
import frappe
from frappe.model.document import Document


class PPEInspection(Document):
	def on_submit(self):
		for row in self.items_inspected:
			if not row.update_assignment or not row.employee_ppe_assignment:
				continue

			assignment = frappe.get_doc("Employee PPE Assignment", row.employee_ppe_assignment)
			assignment.last_inspection_date = self.inspection_date
			assignment.last_inspection_status = row.current_status
			assignment.last_inspection = self.name

			if row.current_status in ("Worn Out", "Lost"):
				assignment.status = "Inactive"
			elif row.current_status == "OK":
				assignment.status = "Active"

			assignment.save(ignore_permissions=True)
```

- [ ] **Step 4: Run to confirm it passes**

```bash
bench --site david.local run-tests --app upande_stores --module upande_stores.upande_stores.doctype.ppe_inspection.test_ppe_inspection
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/frappe/kaitet-bench/apps/upande_stores
git add upande_stores/upande_stores/doctype/ppe_inspection upande_stores/upande_stores/doctype/ppe_inspection_item
git commit -m "feat: add PPE Inspection doctype, deactivate assignment on Lost/Worn Out"
```

---

## Task 17: PPE Inspection client script — scope/clear the assignment picker

**Files:**
- Create: `apps/upande_stores/upande_stores/upande_stores/doctype/ppe_inspection/ppe_inspection.js`

**Interfaces:** none — own-doctype form script, auto-loaded, nothing downstream
depends on it programmatically.

- [ ] **Step 1: Write it**

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
					status: "Active",
				},
			};
		});
	},

	employee(frm) {
		if (frm.doc.items_inspected && frm.doc.items_inspected.length) {
			frm.clear_table("items_inspected");
			frm.refresh_field("items_inspected");
			frappe.msgprint(__("Inspection items cleared because Employee was changed."));
		}
	},
});
```

(The added `status: "Active"` filter — not present in the old build — is a small
improvement: there's no reason to let an inspector pick an already Inactive/
Expired/Returned assignment.)

- [ ] **Step 2: Build and manually verify**

```bash
cd ~/frappe/kaitet-bench
bench build --app upande_stores
bench --site david.local clear-cache
```
Open a new PPE Inspection, select an Employee, add a row in Items Inspected, open
the Employee PPE Assignment link — confirm only that employee's `Active`
assignments appear. Change Employee — confirm the table clears with the message.

- [ ] **Step 3: Commit**

```bash
cd ~/frappe/kaitet-bench/apps/upande_stores
git add upande_stores/upande_stores/doctype/ppe_inspection/ppe_inspection.js
git commit -m "feat: scope PPE Inspection's assignment picker to the selected employee"
```

---

## Task 18: API — `create_bulk_ppe_material_request`

**Files:**
- Modify: `apps/upande_stores/upande_stores/upande_stores/api/ppe.py`
- Modify: `apps/upande_stores/upande_stores/upande_stores/api/test_ppe.py`

**Interfaces:**
- Consumes: `Employee PPE Assignment` (Tasks 12–13, 16).
- Produces: `upande_stores.api.ppe.create_bulk_ppe_material_request(assignments)`
  → `str` (Material Request name), plus shared helpers
  `_assignment_eligible_for_replacement(assignment)`, `_load_assignments(assignments)`,
  `_check_same_scope(assignments)` that Task 19 reuses.

- [ ] **Step 1: Write the failing test**, appended to `api/test_ppe.py`:

```python
from upande_stores.api.ppe import create_bulk_ppe_material_request


class IntegrationTestCreateBulkPPEMaterialRequest(IntegrationTestCase):
	def setUp(self):
		employees = get_test_employees(count=1)
		if not employees:
			self.skipTest("Need at least 1 Active Employee record on this site.")
		self.employee = employees[0]

	def _inactive_assignment(self):
		return frappe.get_doc(
			{
				"doctype": "Employee PPE Assignment",
				"employee": self.employee,
				"item_code": make_ppe_item(),
				"quantity": 1,
				"company": "_Test Company",
				"issue_date": "2026-01-01",
				"lifespan_months": 6,
				"status": "Inactive",
				"last_inspection_status": "Lost",
			}
		).insert(ignore_permissions=True)

	def test_creates_material_issue_and_marks_assignments_requested(self):
		assignment = self._inactive_assignment()
		mr_name = create_bulk_ppe_material_request(json.dumps([assignment.name]))

		mr = frappe.get_doc("Material Request", mr_name)
		self.assertEqual(mr.material_request_type, "Material Issue")
		self.assertEqual(mr.custom_ppe_issuance, 1)
		self.assertEqual(mr.items[0].description, "PPE Issuance")

		assignment.reload()
		self.assertEqual(assignment.replacement_requested, 1)
		self.assertEqual(assignment.replacement_material_request, mr_name)

	def test_rejects_an_active_assignment_with_no_bad_inspection(self):
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

		with self.assertRaises(frappe.ValidationError):
			create_bulk_ppe_material_request(json.dumps([assignment.name]))

	def test_rejects_already_requested_assignment(self):
		assignment = self._inactive_assignment()
		create_bulk_ppe_material_request(json.dumps([assignment.name]))

		with self.assertRaises(frappe.ValidationError):
			create_bulk_ppe_material_request(json.dumps([assignment.name]))
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd ~/frappe/kaitet-bench
bench --site david.local run-tests --app upande_stores --module upande_stores.api.test_ppe
```

- [ ] **Step 3: Add to `api/ppe.py`**

```python
def _assignment_eligible_for_replacement(assignment):
	return assignment.status in ("Inactive", "Expired", "Returned") or assignment.last_inspection_status in (
		"Worn Out",
		"Lost",
	)


def _load_assignments(assignments):
	if isinstance(assignments, str):
		assignments = json.loads(assignments)
	if not assignments:
		frappe.throw(_("No assignments selected."))
	return [frappe.get_doc("Employee PPE Assignment", name) for name in assignments]


def _check_same_scope(assignments):
	first = assignments[0]
	for assignment in assignments[1:]:
		if assignment.company != first.company:
			frappe.throw(
				_("All assignments must have the same Company. {0} has a different Company.").format(
					assignment.name
				)
			)
		if assignment.farm != first.farm:
			frappe.throw(
				_("All assignments must have the same Farm. {0} has a different Farm.").format(assignment.name)
			)
		if assignment.business_unit != first.business_unit:
			frappe.throw(
				_(
					"All assignments must have the same Business Unit. {0} has a different Business Unit."
				).format(assignment.name)
			)
	return first


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

- [ ] **Step 4: Run to confirm it passes**

```bash
bench --site david.local run-tests --app upande_stores --module upande_stores.api.test_ppe
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/frappe/kaitet-bench/apps/upande_stores
git add upande_stores/upande_stores/api
git commit -m "feat: add create_bulk_ppe_material_request API"
```

---

## Task 19: API — `create_bulk_ppe_purchase_request`

**Files:**
- Modify: `apps/upande_stores/upande_stores/upande_stores/api/ppe.py`
- Modify: `apps/upande_stores/upande_stores/upande_stores/api/test_ppe.py`

**Interfaces:**
- Consumes: `_load_assignments`, `_check_same_scope` (Task 18).
- Produces: `upande_stores.api.ppe.create_bulk_ppe_purchase_request(assignments)`
  → `str` (Material Request name). Tasks 20 and 21 both call this — Task 21 with
  a single-element list.

- [ ] **Step 1: Write the failing test**, appended to `api/test_ppe.py`:

```python
from frappe.utils import add_months

from upande_stores.api.ppe import create_bulk_ppe_purchase_request


class IntegrationTestCreateBulkPPEPurchaseRequest(IntegrationTestCase):
	def setUp(self):
		employees = get_test_employees(count=1)
		if not employees:
			self.skipTest("Need at least 1 Active Employee record on this site.")
		self.employee = employees[0]

	def _assignment_with_replacement_mr(self):
		assignment = frappe.get_doc(
			{
				"doctype": "Employee PPE Assignment",
				"employee": self.employee,
				"item_code": make_ppe_item(),
				"quantity": 1,
				"company": "_Test Company",
				"issue_date": "2026-01-01",
				"lifespan_months": 6,
				"status": "Inactive",
				"last_inspection_status": "Lost",
			}
		).insert(ignore_permissions=True)
		mr_name = create_bulk_ppe_material_request(json.dumps([assignment.name]))
		assignment.reload()
		return assignment, mr_name

	def test_creates_purchase_request(self):
		assignment, _ = self._assignment_with_replacement_mr()
		mr_name = create_bulk_ppe_purchase_request(json.dumps([assignment.name]))

		mr = frappe.get_doc("Material Request", mr_name)
		self.assertEqual(mr.material_request_type, "Purchase")
		self.assertFalse(mr.custom_ppe_issuance)
		self.assertEqual(mr.items[0].description, "PPE Purchase")

		assignment.reload()
		self.assertEqual(assignment.replacement_purchase_request, mr_name)

	def test_rejects_assignment_with_no_replacement_material_request(self):
		assignment = frappe.get_doc(
			{
				"doctype": "Employee PPE Assignment",
				"employee": self.employee,
				"item_code": make_ppe_item(),
				"quantity": 1,
				"company": "_Test Company",
				"issue_date": "2026-01-01",
				"lifespan_months": 6,
				"status": "Inactive",
			}
		).insert(ignore_permissions=True)

		with self.assertRaises(frappe.ValidationError):
			create_bulk_ppe_purchase_request(json.dumps([assignment.name]))

	def test_rejects_assignment_already_purchased(self):
		assignment, _ = self._assignment_with_replacement_mr()
		create_bulk_ppe_purchase_request(json.dumps([assignment.name]))

		with self.assertRaises(frappe.ValidationError):
			create_bulk_ppe_purchase_request(json.dumps([assignment.name]))
```

(add `from upande_stores.api.ppe import create_bulk_ppe_material_request` to this
test module's imports if not already present from Task 18)

- [ ] **Step 2: Run to confirm it fails**

```bash
cd ~/frappe/kaitet-bench
bench --site david.local run-tests --app upande_stores --module upande_stores.api.test_ppe
```

- [ ] **Step 3: Add to `api/ppe.py`**

```python
@frappe.whitelist()
def create_bulk_ppe_purchase_request(assignments):
	docs = _load_assignments(assignments)
	first = _check_same_scope(docs)

	merged_items = {}
	for assignment in docs:
		if not assignment.replacement_material_request:
			frappe.throw(
				_("{0} does not have a replacement material request. Please create one first.").format(
					assignment.name
				)
			)
		if assignment.replacement_purchase_request:
			frappe.throw(
				_("{0} already has a purchase request: {1}").format(
					assignment.name, assignment.replacement_purchase_request
				)
			)
		merged_items[assignment.item_code] = merged_items.get(assignment.item_code, 0) + (
			assignment.quantity or 1
		)

	mr = frappe.get_doc(
		{
			"doctype": "Material Request",
			"material_request_type": "Purchase",
			"schedule_date": add_months(today(), 1),
			"company": first.company,
			"custom_farm": first.farm,
			"custom_business_unit": first.business_unit,
		}
	)
	for item_code, qty in merged_items.items():
		mr.append(
			"items",
			{
				"item_code": item_code,
				"qty": qty,
				"schedule_date": add_months(today(), 1),
				"description": "PPE Purchase",
			},
		)
	mr.insert()

	for assignment in docs:
		frappe.db.set_value(
			"Employee PPE Assignment", assignment.name, "replacement_purchase_request", mr.name
		)
	return mr.name
```

Add `from frappe.utils import add_months, today` to the top of `api/ppe.py` if
`add_months` isn't already imported there.

- [ ] **Step 4: Run to confirm it passes**

```bash
bench --site david.local run-tests --app upande_stores --module upande_stores.api.test_ppe
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/frappe/kaitet-bench/apps/upande_stores
git add upande_stores/upande_stores/api
git commit -m "feat: add create_bulk_ppe_purchase_request API"
```

---

## Task 20: Employee PPE Assignment list view — bulk actions

**Files:**
- Create: `apps/upande_stores/upande_stores/upande_stores/public/js/employee_ppe_assignment_list.js`
- Modify: `apps/upande_stores/upande_stores/upande_stores/hooks.py`

**Interfaces:**
- Consumes: `create_bulk_ppe_material_request`, `create_bulk_ppe_purchase_request`
  (Tasks 18–19).

- [ ] **Step 1: Write the file**

```js
frappe.listview_settings["Employee PPE Assignment"] = {
	onload(listview) {
		listview.page.add_action_item(__("Create Replacement Material Request"), () => {
			const selected = listview.get_checked_items();
			if (!selected.length) {
				frappe.msgprint(__("Please select at least one record."));
				return;
			}
			frappe.call({
				method: "upande_stores.api.ppe.create_bulk_ppe_material_request",
				args: { assignments: JSON.stringify(selected.map((d) => d.name)) },
				callback: (r) => {
					if (r.message) frappe.set_route("Form", "Material Request", r.message);
				},
			});
		});

		listview.page.add_action_item(__("Create Bulk Purchase Request"), () => {
			const selected = listview.get_checked_items();
			if (!selected.length) {
				frappe.msgprint(__("Please select at least one record."));
				return;
			}
			frappe.call({
				method: "upande_stores.api.ppe.create_bulk_ppe_purchase_request",
				args: { assignments: JSON.stringify(selected.map((d) => d.name)) },
				callback: (r) => {
					if (r.message) frappe.set_route("Form", "Material Request", r.message);
				},
			});
		});
	},
};
```

- [ ] **Step 2: Register via `doctype_list_js` in `hooks.py`**

```python
doctype_list_js = {"Employee PPE Assignment": "public/js/employee_ppe_assignment_list.js"}
```

- [ ] **Step 3: Build and manually verify**

```bash
cd ~/frappe/kaitet-bench
bench build --app upande_stores
bench --site david.local clear-cache
```
On the Employee PPE Assignment list, select one or more Inactive/Expired/Returned
rows, confirm both bulk actions appear under the "..." menu and each routes to a
newly created Material Request of the right type.

- [ ] **Step 4: Commit**

```bash
cd ~/frappe/kaitet-bench/apps/upande_stores
git add upande_stores/upande_stores/public/js/employee_ppe_assignment_list.js upande_stores/hooks.py
git commit -m "feat: add bulk replacement/purchase actions to Employee PPE Assignment list"
```

---

## Task 21: Employee PPE Assignment form — single "Raise Purchase Request" button

**Files:**
- Create: `apps/upande_stores/upande_stores/upande_stores/doctype/employee_ppe_assignment/employee_ppe_assignment.js`

**Interfaces:**
- Consumes: `create_bulk_ppe_purchase_request` (Task 19) — called with a
  single-element array, replacing the old build's separate, looser single-record
  code path.

- [ ] **Step 1: Write it**

```js
frappe.ui.form.on("Employee PPE Assignment", {
	refresh(frm) {
		if (
			frm.doc.replacement_requested &&
			frm.doc.replacement_material_request &&
			!frm.doc.replacement_purchase_request
		) {
			frm.add_custom_button(
				__("Raise Purchase Request"),
				() => {
					frappe.confirm(
						__("Create a Purchase Material Request for {0}?", [frm.doc.item_name || frm.doc.item_code]),
						() => {
							frappe.call({
								method: "upande_stores.api.ppe.create_bulk_ppe_purchase_request",
								args: { assignments: JSON.stringify([frm.doc.name]) },
								callback: (r) => {
									if (r.message) {
										frappe.show_alert({
											message: __("Purchase Request {0} created", [r.message]),
											indicator: "green",
										});
										frm.reload_doc();
									}
								},
							});
						}
					);
				},
				__("Create")
			);
		}
	},
});
```

- [ ] **Step 2: Build and manually verify**

```bash
cd ~/frappe/kaitet-bench
bench build --app upande_stores
bench --site david.local clear-cache
```
Open an assignment with `replacement_requested=1` and a
`replacement_material_request` set but no purchase request yet — confirm the
button appears and creates a Purchase Material Request.

- [ ] **Step 3: Commit**

```bash
cd ~/frappe/kaitet-bench/apps/upande_stores
git add upande_stores/upande_stores/doctype/employee_ppe_assignment/employee_ppe_assignment.js
git commit -m "feat: add single-record Raise Purchase Request button"
```

---

## Task 22: Material Request override — unlink on cancel/delete

**Files:**
- Modify: `apps/upande_stores/upande_stores/upande_stores/overrides/material_request.py`
- Modify: `apps/upande_stores/upande_stores/upande_stores/overrides/test_material_request.py`
- Modify: `apps/upande_stores/upande_stores/upande_stores/hooks.py`

**Interfaces:**
- Consumes: `Material Request.custom_ppe_issuance` (Task 8), `Employee PPE
  Assignment.replacement_material_request`/`.replacement_requested` (Task 12).
- Produces: `upande_stores.overrides.material_request.unlink_ppe_replacement(doc, method=None)`.

- [ ] **Step 1: Write the failing test**, appended to `test_material_request.py`
  (new class in the same file, reusing its existing imports):

```python
from upande_stores.tests.test_helpers import make_ppe_item


class IntegrationTestMaterialRequestPPEUnlink(IntegrationTestCase):
	def setUp(self):
		employees = get_test_employees(count=1)
		if not employees:
			self.skipTest("Need at least 1 Active Employee record on this site.")
		self.employee = employees[0]

	def test_cancel_clears_the_replacement_lock(self):
		assignment = frappe.get_doc(
			{
				"doctype": "Employee PPE Assignment",
				"employee": self.employee,
				"item_code": make_ppe_item(),
				"quantity": 1,
				"company": "_Test Company",
				"issue_date": "2026-01-01",
				"lifespan_months": 6,
				"status": "Inactive",
			}
		).insert(ignore_permissions=True)

		mr = frappe.get_doc(
			{
				"doctype": "Material Request",
				"material_request_type": "Material Issue",
				"transaction_date": frappe.utils.today(),
				"company": "_Test Company",
				"custom_ppe_issuance": 1,
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
		mr.insert(ignore_permissions=True)
		frappe.db.set_value(
			"Employee PPE Assignment",
			assignment.name,
			{"replacement_requested": 1, "replacement_material_request": mr.name},
		)

		mr.submit()
		mr.cancel()

		assignment.reload()
		self.assertEqual(assignment.replacement_requested, 0)
		self.assertFalse(assignment.replacement_material_request)

	def test_non_ppe_material_request_cancel_is_a_noop(self):
		mr = frappe.get_doc(
			{
				"doctype": "Material Request",
				"material_request_type": "Material Issue",
				"transaction_date": frappe.utils.today(),
				"company": "_Test Company",
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
		mr.insert(ignore_permissions=True)
		mr.submit()
		mr.cancel()  # must not raise
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd ~/frappe/kaitet-bench
bench --site david.local run-tests --app upande_stores --module upande_stores.overrides.test_material_request
```

- [ ] **Step 3: Add to `overrides/material_request.py`**, appended after the
  existing `validate_no_duplicate_employees` function:

```python
def unlink_ppe_replacement(doc, method=None):
	"""Material Request on_cancel/on_trash: if this MR was a PPE Issuance
	request, clear the replacement lock on any Employee PPE Assignment
	pointing at it."""
	if not doc.get("custom_ppe_issuance"):
		return
	for name in frappe.get_all(
		"Employee PPE Assignment", filters={"replacement_material_request": doc.name}, pluck="name"
	):
		frappe.db.set_value(
			"Employee PPE Assignment",
			name,
			{"replacement_requested": 0, "replacement_material_request": None},
		)
```

- [ ] **Step 4: Wire it in `hooks.py`** — find the existing
  `doc_events["Material Request"]` block (currently just `"validate": "...
  validate_no_duplicate_employees"`) and add:

```python
	"Material Request": {
		"validate": "upande_stores.overrides.material_request.validate_no_duplicate_employees",
		"on_cancel": "upande_stores.overrides.material_request.unlink_ppe_replacement",
		"on_trash": "upande_stores.overrides.material_request.unlink_ppe_replacement",
	},
```

- [ ] **Step 5: Run to confirm it passes**

```bash
bench --site david.local run-tests --app upande_stores --module upande_stores.overrides.test_material_request
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd ~/frappe/kaitet-bench/apps/upande_stores
git add upande_stores/upande_stores/overrides/material_request.py upande_stores/upande_stores/overrides/test_material_request.py upande_stores/hooks.py
git commit -m "feat: unlink PPE replacement lock when its Material Request is cancelled/deleted"
```

---

## Task 23: Scheduled task — auto-expire PPE assignments

**Files:**
- Create: `apps/upande_stores/upande_stores/upande_stores/tasks.py`
- Create: `apps/upande_stores/upande_stores/upande_stores/test_tasks.py`
- Modify: `apps/upande_stores/upande_stores/upande_stores/hooks.py`

**Interfaces:**
- Consumes: `Employee PPE Assignment.status`/`.expiry_date` (Task 12).
- Produces: `upande_stores.tasks.mark_expired_ppe_assignments()`.

- [ ] **Step 1: Write the failing test**

```python
import frappe
from frappe.tests import IntegrationTestCase

from upande_stores.tasks import mark_expired_ppe_assignments
from upande_stores.tests.test_helpers import get_test_employees, make_ppe_item


class IntegrationTestMarkExpiredPPEAssignments(IntegrationTestCase):
	def setUp(self):
		employees = get_test_employees(count=1)
		if not employees:
			self.skipTest("Need at least 1 Active Employee record on this site.")
		self.employee = employees[0]

	def test_marks_past_expiry_active_assignment_as_expired(self):
		assignment = frappe.get_doc(
			{
				"doctype": "Employee PPE Assignment",
				"employee": self.employee,
				"item_code": make_ppe_item(),
				"quantity": 1,
				"company": "_Test Company",
				"issue_date": "2020-01-01",
				"expiry_date": "2020-07-01",
				"lifespan_months": 6,
				"status": "Active",
			}
		).insert(ignore_permissions=True)

		mark_expired_ppe_assignments()

		self.assertEqual(frappe.db.get_value("Employee PPE Assignment", assignment.name, "status"), "Expired")

	def test_leaves_future_expiry_assignment_active(self):
		assignment = frappe.get_doc(
			{
				"doctype": "Employee PPE Assignment",
				"employee": self.employee,
				"item_code": make_ppe_item(),
				"quantity": 1,
				"company": "_Test Company",
				"issue_date": frappe.utils.today(),
				"lifespan_months": 60,
				"status": "Active",
			}
		).insert(ignore_permissions=True)

		mark_expired_ppe_assignments()

		self.assertEqual(frappe.db.get_value("Employee PPE Assignment", assignment.name, "status"), "Active")
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd ~/frappe/kaitet-bench
bench --site david.local run-tests --app upande_stores --module upande_stores.test_tasks
```
Expected: FAIL — `ModuleNotFoundError: No module named 'upande_stores.tasks'`.

- [ ] **Step 3: Write `tasks.py`**

```python
import frappe
from frappe.utils import getdate, nowdate


def mark_expired_ppe_assignments():
	today = getdate(nowdate())
	expired = frappe.get_all(
		"Employee PPE Assignment",
		filters={"status": "Active", "expiry_date": ["<=", today]},
		pluck="name",
	)
	for name in expired:
		frappe.db.set_value("Employee PPE Assignment", name, "status", "Expired")
```

- [ ] **Step 4: Register it in `hooks.py`** — find the commented-out
  `scheduler_events` block and uncomment/replace with:

```python
scheduler_events = {
	"daily": [
		"upande_stores.tasks.mark_expired_ppe_assignments",
	],
}
```

- [ ] **Step 5: Run to confirm it passes**

```bash
bench --site david.local run-tests --app upande_stores --module upande_stores.test_tasks
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd ~/frappe/kaitet-bench/apps/upande_stores
git add upande_stores/upande_stores/tasks.py upande_stores/upande_stores/test_tasks.py upande_stores/hooks.py
git commit -m "feat: auto-expire PPE assignments past their expiry date"
```

---

## Post-plan manual smoke test

After all 23 tasks: create a PPE Policy for a real Company+Department, run
"Fetch PPE Requirements" + "Create PPE Issuance Request" on an Employee
Onboarding for an employee in that department, create+submit a Stock Entry
against the resulting Material Request with `bio_employee` set, confirm an
Employee PPE Assignment and an Employee PPE History row both appear, submit a
PPE Inspection marking it "Lost", confirm the assignment goes `Inactive`, then
run both list-view bulk actions end to end to a Purchase Request.
