# Material Request Employee/Farm Field Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-home Material Request's `custom_farm`/`custom_business_unit` fields and the Employee Details table to `upande_stores`, and retire `custom_request_type` and everything depending on it, with zero data loss on the live `david.local` site.

**Architecture:** Frappe's Customize-Form-export convention (`custom/<doctype>.json`, `sync_on_migrate: 1`) drives ongoing field definitions; `Custom Field`/`Property Setter` records get `module: "Upande Stores"` so app uninstall auto-removes them (native Frappe behavior via `_delete_linked_documents`, no custom hook needed). The `Employee Request` child doctype is re-homed by moving its folder + editing its `module` value — DocType lifecycle is fully automatic based on module ownership. A one-time patch in `upande_kaitet` deletes the DB rows for fields being fully retired (the JSON-file sync mechanism upserts by fieldname but never deletes rows removed from the file).

**Tech Stack:** Frappe framework (Python + JSON doctype/customization files), MariaDB, bench CLI.

## Global Constraints

- Site to migrate and verify against: `david.local` (bench: `/home/david/frappe/kaitet-bench`).
- `upande_stores` is a git repo (branch `upande-kaitet`) — commit changes there. `upande_kaitet` has **no** `.git` — edit files on disk, do not attempt to commit.
- Every new/moved field or doctype must carry `module: "Upande Stores"` (Custom Field/Property Setter) or `"module": "Upande Stores"` (DocType) — this is what makes app uninstall auto-clean everything.
- Preserve existing data: never rename/retype `custom_farm`, `custom_business_unit`, `custom_employee_data`, or any `Employee Request` field that's being kept — same fieldname on an existing DB column/table preserves data even when the owning Custom Field/DocType record is deleted and recreated.
- Do not touch: header-level `custom_asset` (depends on `custom_business_unit`, staying in `upande_kaitet`, NOT the same as the Material Request Item child's `custom_asset` being removed), `custom_source_farm`, `custom_purpose`, or any Stock Entry customization other than the shared `Employee Request` doctype's `location` field removal (explicitly approved).
- JSON files in this codebase are formatted exactly like `frappe.as_json`: `json.dumps(data, indent=1, sort_keys=True, ensure_ascii=True, separators=(",", ": "))`. Match this style for every file written or rewritten.

---

### Task 1: Clean up `upande_kaitet`'s Material Request / Material Request Item custom field exports

**Files:**
- Modify: `apps/upande_kaitet/upande_kaitet/upande_kaitet/custom/material_request.json`
- Modify: `apps/upande_kaitet/upande_kaitet/upande_kaitet/custom/material_request_item.json`
- Test: none (JSON validity + content checks below; live DB effects happen in Task 5)

**Interfaces:**
- Produces: `material_request.json` with 10 custom_fields (`custom_approver_name`, `custom_asset`, `custom_phone_number`, `custom_purpose`, `custom_rejected_reason`, `custom_repack_stock_entry`, `custom_repair_reference`, `custom_source_farm`, `custom_total`, `workflow_state`) and 19 property_setters (all except the 4 removed below), with `field_order` no longer containing `custom_request_type`, `custom_vehicle_registration`, `custom_farm_selector`.
- Produces: `material_request_item.json` with 5 custom_fields (`custom_disease`, `custom_pest`, `custom_purpose`, `custom_task`, `farm`) — `custom_asset` removed.

- [ ] **Step 1: Write and run the transform script for `material_request.json`**

```bash
cd /home/david/frappe/kaitet-bench
python3 <<'EOF'
import json

path = "apps/upande_kaitet/upande_kaitet/upande_kaitet/custom/material_request.json"
with open(path) as f:
    data = json.load(f)

REMOVE_FIELDS = {
    "custom_biometric_id", "custom_business_unit", "custom_employee",
    "custom_employee_data", "custom_employee_details", "custom_employee_name",
    "custom_farm", "custom_farm_selector", "custom_milk_customer",
    "custom_reason", "custom_request_type", "custom_tractor_daily_task",
    "custom_vehicle_registration",
}
before = len(data["custom_fields"])
data["custom_fields"] = [f for f in data["custom_fields"] if f["fieldname"] not in REMOVE_FIELDS]
assert before - len(data["custom_fields"]) == 13, f"expected to remove 13 fields, removed {before - len(data['custom_fields'])}"

REMOVE_PROPERTY_SETTERS = {
    "Material Request-custom_employee_name-in_list_view",
    "Material Request-custom_employee-in_list_view",
    "Material Request-custom_farm-in_list_view",
    "Material Request-custom_request_type-in_list_view",
}
before_ps = len(data["property_setters"])
data["property_setters"] = [p for p in data["property_setters"] if p["name"] not in REMOVE_PROPERTY_SETTERS]
assert before_ps - len(data["property_setters"]) == 4, f"expected to remove 4 property setters, removed {before_ps - len(data['property_setters'])}"

DROP_FROM_ORDER = {"custom_request_type", "custom_vehicle_registration", "custom_farm_selector"}
found_field_order = False
for p in data["property_setters"]:
    if p["name"] == "Material Request-main-field_order":
        found_field_order = True
        order = json.loads(p["value"])
        p["value"] = json.dumps([f for f in order if f not in DROP_FROM_ORDER])
assert found_field_order, "field_order property setter not found"

with open(path, "w") as f:
    f.write(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=True, separators=(",", ": ")))
    f.write("\n")

print("material_request.json: OK,", len(data["custom_fields"]), "custom_fields,", len(data["property_setters"]), "property_setters")
EOF
```

Expected output: `material_request.json: OK, 10 custom_fields, 19 property_setters`

- [ ] **Step 2: Write and run the transform script for `material_request_item.json`**

```bash
cd /home/david/frappe/kaitet-bench
python3 <<'EOF'
import json

path = "apps/upande_kaitet/upande_kaitet/upande_kaitet/custom/material_request_item.json"
with open(path) as f:
    data = json.load(f)

before = len(data["custom_fields"])
data["custom_fields"] = [f for f in data["custom_fields"] if f["fieldname"] != "custom_asset"]
assert before - len(data["custom_fields"]) == 1, f"expected to remove 1 field, removed {before - len(data['custom_fields'])}"

with open(path, "w") as f:
    f.write(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=True, separators=(",", ": ")))
    f.write("\n")

print("material_request_item.json: OK,", len(data["custom_fields"]), "custom_fields")
EOF
```

Expected output: `material_request_item.json: OK, 5 custom_fields`

- [ ] **Step 3: Verify both files are valid JSON and contain no removed fieldnames**

```bash
cd /home/david/frappe/kaitet-bench
python3 -c "
import json
mr = json.load(open('apps/upande_kaitet/upande_kaitet/upande_kaitet/custom/material_request.json'))
mri = json.load(open('apps/upande_kaitet/upande_kaitet/upande_kaitet/custom/material_request_item.json'))
mr_names = {f['fieldname'] for f in mr['custom_fields']}
mri_names = {f['fieldname'] for f in mri['custom_fields']}
removed = {'custom_biometric_id','custom_business_unit','custom_employee','custom_employee_data','custom_employee_details','custom_employee_name','custom_farm','custom_farm_selector','custom_milk_customer','custom_reason','custom_request_type','custom_tractor_daily_task','custom_vehicle_registration'}
assert not (mr_names & removed), mr_names & removed
assert 'custom_asset' not in mri_names
assert 'custom_asset' in mr_names  # header-level custom_asset must remain
print('OK: no removed fields present, header custom_asset intact')
"
```

Expected output: `OK: no removed fields present, header custom_asset intact`

- [ ] **Step 4: No commit** — `upande_kaitet` has no `.git`. Leave the files edited on disk; they'll be picked up by `bench migrate` in Task 5.

---

### Task 2: Re-home the `Employee Request` doctype to `upande_stores` and drop `location`

**Files:**
- Move: `apps/upande_kaitet/upande_kaitet/upande_kaitet/doctype/employee_request/` → `apps/upande_stores/upande_stores/upande_stores/doctype/employee_request/`
- Modify (after move): `apps/upande_stores/upande_stores/upande_stores/doctype/employee_request/employee_request.json`
- Delete: `apps/upande_kaitet/upande_kaitet/upande_kaitet/custom/employee_request.json`
- Create if missing: `apps/upande_stores/upande_stores/upande_stores/doctype/__init__.py`

**Interfaces:**
- Produces: `Employee Request` DocType JSON with `"module": "Upande Stores"`, `field_order: ["employee", "employee_name", "department", "farm"]`, and matching `fields` list (no `location`).

- [ ] **Step 1: Create the doctype package folder in `upande_stores` if it doesn't exist**

```bash
mkdir -p /home/david/frappe/kaitet-bench/apps/upande_stores/upande_stores/upande_stores/doctype
touch /home/david/frappe/kaitet-bench/apps/upande_stores/upande_stores/upande_stores/doctype/__init__.py
```

- [ ] **Step 2: Move the doctype folder (excluding `__pycache__`)**

```bash
cd /home/david/frappe/kaitet-bench
mkdir -p apps/upande_stores/upande_stores/upande_stores/doctype/employee_request
cp apps/upande_kaitet/upande_kaitet/upande_kaitet/doctype/employee_request/__init__.py \
   apps/upande_kaitet/upande_kaitet/upande_kaitet/doctype/employee_request/employee_request.json \
   apps/upande_kaitet/upande_kaitet/upande_kaitet/doctype/employee_request/employee_request.py \
   apps/upande_stores/upande_stores/upande_stores/doctype/employee_request/
rm -rf apps/upande_kaitet/upande_kaitet/upande_kaitet/doctype/employee_request
```

- [ ] **Step 3: Edit the moved `employee_request.json`** — set module, drop `location`

```bash
cd /home/david/frappe/kaitet-bench
python3 <<'EOF'
import json

path = "apps/upande_stores/upande_stores/upande_stores/doctype/employee_request/employee_request.json"
with open(path) as f:
    data = json.load(f)

data["module"] = "Upande Stores"
data["field_order"] = [f for f in data["field_order"] if f != "location"]
data["fields"] = [f for f in data["fields"] if f["fieldname"] != "location"]

assert data["field_order"] == ["employee", "employee_name", "farm", "department"], data["field_order"]
assert {f["fieldname"] for f in data["fields"]} == {"employee", "employee_name", "farm", "department"}

with open(path, "w") as f:
    f.write(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=True, separators=(",", ": ")))
    f.write("\n")

print("employee_request.json: OK, module =", data["module"], "fields =", data["field_order"])
EOF
```

Expected output: `employee_request.json: OK, module = Upande Stores fields = ['employee', 'employee_name', 'farm', 'department']`

- [ ] **Step 4: Delete the now-obsolete Customize Form export for Employee Request**

```bash
rm /home/david/frappe/kaitet-bench/apps/upande_kaitet/upande_kaitet/upande_kaitet/custom/employee_request.json
```

This file only contained the `location.fetch_from` property setter, which is meaningless once `location` no longer exists. (The live DB row for it is deleted by the Task 4 patch.)

- [ ] **Step 5: Verify the old location is gone and the new location has no stray `__pycache__`**

```bash
test ! -d /home/david/frappe/kaitet-bench/apps/upande_kaitet/upande_kaitet/upande_kaitet/doctype/employee_request && echo "OK: old folder gone"
ls /home/david/frappe/kaitet-bench/apps/upande_stores/upande_stores/upande_stores/doctype/employee_request/
```

Expected output: `OK: old folder gone`, followed by a directory listing showing `__init__.py`, `employee_request.json`, `employee_request.py`.

- [ ] **Step 6: Stage for commit (commit happens in Task 6 alongside everything else in `upande_stores`)** — no action needed yet, just leave as-is.

---

### Task 3: Create Material Request's new custom fields owned by `upande_stores`

**Files:**
- Create: `apps/upande_stores/upande_stores/upande_stores/custom/material_request.json`

**Interfaces:**
- Consumes: `Employee Request` doctype (Task 2) as the `options` target for the `custom_employee_data` Table field.
- Produces: `custom_farm`, `custom_business_unit` (Link fields, both `module: "Upande Stores"`, `reqd: 1`, same `insert_after` chain as before: `custom_purpose` → `custom_farm` → `custom_business_unit`), `custom_employee_details` (Section Break, insert_after `custom_total`), `custom_employee_data` (Table → `Employee Request`, insert_after `custom_employee_details`, same `depends_on` as before), plus the `custom_farm-in_list_view` property setter.

- [ ] **Step 1: Create the `custom/` folder and write the new file**

```bash
mkdir -p /home/david/frappe/kaitet-bench/apps/upande_stores/upande_stores/upande_stores/custom
```

Write `apps/upande_stores/upande_stores/upande_stores/custom/material_request.json`:

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
   "creation": "2026-07-16 00:00:00.000000",
   "default": null,
   "depends_on": null,
   "description": null,
   "docstatus": 0,
   "dt": "Material Request",
   "fetch_from": null,
   "fetch_if_empty": 0,
   "fieldname": "custom_farm",
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
   "insert_after": "custom_purpose",
   "is_system_generated": 0,
   "is_virtual": 0,
   "label": "Farm",
   "length": 0,
   "link_filters": null,
   "mandatory_depends_on": null,
   "modified": "2026-07-16 00:00:00.000000",
   "modified_by": "Administrator",
   "module": "Upande Stores",
   "name": "Material Request-custom_farm",
   "no_copy": 0,
   "non_negative": 0,
   "options": "Farm",
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
   "reqd": 1,
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
   "creation": "2026-07-16 00:00:00.000000",
   "default": null,
   "depends_on": null,
   "description": null,
   "docstatus": 0,
   "dt": "Material Request",
   "fetch_from": null,
   "fetch_if_empty": 0,
   "fieldname": "custom_business_unit",
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
   "insert_after": "custom_farm",
   "is_system_generated": 0,
   "is_virtual": 0,
   "label": "Business Unit",
   "length": 0,
   "link_filters": null,
   "mandatory_depends_on": null,
   "modified": "2026-07-16 00:00:00.000000",
   "modified_by": "Administrator",
   "module": "Upande Stores",
   "name": "Material Request-custom_business_unit",
   "no_copy": 0,
   "non_negative": 0,
   "options": "Business Unit",
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
   "reqd": 1,
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
   "creation": "2026-07-16 00:00:00.000000",
   "default": null,
   "depends_on": "",
   "description": null,
   "docstatus": 0,
   "dt": "Material Request",
   "fetch_from": null,
   "fetch_if_empty": 0,
   "fieldname": "custom_employee_details",
   "fieldtype": "Section Break",
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
   "insert_after": "custom_total",
   "is_system_generated": 0,
   "is_virtual": 0,
   "label": "Employee Details",
   "length": 0,
   "link_filters": null,
   "mandatory_depends_on": "",
   "modified": "2026-07-16 00:00:00.000000",
   "modified_by": "Administrator",
   "module": "Upande Stores",
   "name": "Material Request-custom_employee_details",
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
   "creation": "2026-07-16 00:00:00.000000",
   "default": null,
   "depends_on": "eval:doc.material_request_type == \"Material Issue\"",
   "description": null,
   "docstatus": 0,
   "dt": "Material Request",
   "fetch_from": null,
   "fetch_if_empty": 0,
   "fieldname": "custom_employee_data",
   "fieldtype": "Table",
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
   "insert_after": "custom_employee_details",
   "is_system_generated": 0,
   "is_virtual": 0,
   "label": "Employee Data",
   "length": 0,
   "link_filters": null,
   "mandatory_depends_on": "",
   "modified": "2026-07-16 00:00:00.000000",
   "modified_by": "Administrator",
   "module": "Upande Stores",
   "name": "Material Request-custom_employee_data",
   "no_copy": 0,
   "non_negative": 0,
   "options": "Employee Request",
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
 "doctype": "Material Request",
 "links": [],
 "property_setters": [
  {
   "_assign": null,
   "_comments": null,
   "_liked_by": null,
   "_user_tags": null,
   "creation": "2026-07-16 00:00:00.000000",
   "default_value": null,
   "doc_type": "Material Request",
   "docstatus": 0,
   "doctype_or_field": "DocField",
   "field_name": "custom_farm",
   "idx": 0,
   "is_system_generated": 0,
   "modified": "2026-07-16 00:00:00.000000",
   "modified_by": "Administrator",
   "module": "Upande Stores",
   "name": "Material Request-custom_farm-in_list_view",
   "owner": "Administrator",
   "property": "in_list_view",
   "property_type": "Check",
   "row_name": null,
   "value": "1"
  }
 ],
 "sync_on_migrate": 1
}
```

- [ ] **Step 2: Verify JSON validity and required keys**

```bash
python3 -c "
import json
data = json.load(open('/home/david/frappe/kaitet-bench/apps/upande_stores/upande_stores/upande_stores/custom/material_request.json'))
names = {f['fieldname'] for f in data['custom_fields']}
assert names == {'custom_farm', 'custom_business_unit', 'custom_employee_details', 'custom_employee_data'}, names
assert all(f['module'] == 'Upande Stores' for f in data['custom_fields'])
assert data['sync_on_migrate'] == 1
assert data['property_setters'][0]['module'] == 'Upande Stores'
print('OK')
"
```

Expected output: `OK`

- [ ] **Step 3: No commit yet** — bundled into Task 6.

---

### Task 4: One-time cleanup patch in `upande_kaitet`

**Files:**
- Create: `apps/upande_kaitet/upande_kaitet/patches/__init__.py` (empty)
- Create: `apps/upande_kaitet/upande_kaitet/patches/v1_0/__init__.py`? — **not needed**, erpnext's own versioned patch folders (e.g. `v14_0/`) have no `__init__.py`; Python 3 namespace packages resolve them without one. Do not create this file.
- Create: `apps/upande_kaitet/upande_kaitet/patches/v1_0/remove_legacy_material_request_fields.py`
- Modify: `apps/upande_kaitet/upande_kaitet/patches.txt`

**Interfaces:**
- Consumes: nothing from earlier tasks at import time; at runtime it assumes Task 1–3's file edits are already on disk (so `bench migrate`'s regular doctype/customization sync has already re-homed `custom_farm`/`custom_business_unit`/`Employee Request` before this patch's deletions run).
- Produces: `execute()` function, idempotent (every deletion is guarded by an existence check, safe to run more than once).

- [ ] **Step 1: Create the empty patches package init file**

```bash
mkdir -p /home/david/frappe/kaitet-bench/apps/upande_kaitet/upande_kaitet/patches/v1_0
touch /home/david/frappe/kaitet-bench/apps/upande_kaitet/upande_kaitet/patches/__init__.py
```

- [ ] **Step 2: Write the patch**

Create `apps/upande_kaitet/upande_kaitet/patches/v1_0/remove_legacy_material_request_fields.py`:

```python
# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe


def execute():
	"""One-time cleanup after re-homing Material Request's farm/business unit/
	employee fields to upande_stores and retiring custom_request_type and its
	dependents. The custom/*.json Customize-Form-export sync upserts fields
	that are still present in the file, but never deletes a Custom Field or
	Property Setter that's been removed from it -- that's this patch's job.
	"""

	frappe.reload_doc("upande_stores", "doctype", "employee_request", force=True)

	removed_custom_fields = [
		("Material Request", "custom_request_type"),
		("Material Request", "custom_tractor_daily_task"),
		("Material Request", "custom_vehicle_registration"),
		("Material Request", "custom_reason"),
		("Material Request", "custom_milk_customer"),
		("Material Request", "custom_employee"),
		("Material Request", "custom_employee_name"),
		("Material Request", "custom_biometric_id"),
		("Material Request", "custom_farm_selector"),
		("Material Request Item", "custom_asset"),
	]
	for dt, fieldname in removed_custom_fields:
		name = frappe.db.get_value("Custom Field", {"dt": dt, "fieldname": fieldname})
		if name:
			frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)

	removed_property_setters = [
		"Material Request-custom_employee_name-in_list_view",
		"Material Request-custom_employee-in_list_view",
		"Material Request-custom_request_type-in_list_view",
		"Employee Request-location-fetch_from",
	]
	for ps_name in removed_property_setters:
		if frappe.db.exists("Property Setter", ps_name):
			frappe.delete_doc("Property Setter", ps_name, ignore_permissions=True, force=True)

	frappe.db.commit()
```

- [ ] **Step 3: Register the patch**

Edit `apps/upande_kaitet/upande_kaitet/patches.txt` — add the entry under `[post_model_sync]`:

```
[pre_model_sync]
# Patches added in this section will be executed before doctypes are migrated
# Read docs to understand patches: https://frappeframework.com/docs/v14/user/en/database-migrations

[post_model_sync]
# Patches added in this section will be executed after doctypes are migrated
upande_kaitet.patches.v1_0.remove_legacy_material_request_fields
```

- [ ] **Step 4: Verify the patch module imports cleanly and patches.txt references it correctly**

```bash
cd /home/david/frappe/kaitet-bench
python3 -c "
import ast
ast.parse(open('apps/upande_kaitet/upande_kaitet/patches/v1_0/remove_legacy_material_request_fields.py').read())
print('syntax OK')
"
grep -n "remove_legacy_material_request_fields" apps/upande_kaitet/upande_kaitet/patches.txt
```

Expected output: `syntax OK` followed by the matching `patches.txt` line.

---

### Task 5: Run migrate and verify the live site

**Files:** none (verification only)

**Interfaces:**
- Consumes: all files from Tasks 1–4.

- [ ] **Step 1: Capture a baseline snapshot before migrating (data-preservation check)**

```bash
cd /home/david/frappe/kaitet-bench
bench --site david.local console <<'EOF'
import json
baseline = {
    "mr_farm_bu": frappe.get_all("Material Request", filters=[["custom_farm", "is", "set"]], fields=["name", "custom_farm", "custom_business_unit"], limit_page_length=0),
    "employee_rows": frappe.get_all("Employee Request", fields=["name", "parent", "parenttype", "employee", "employee_name"], limit_page_length=0),
}
with open("/tmp/mr_migration_baseline.json", "w") as f:
    json.dump(baseline, f, default=str)
print("baseline:", len(baseline["mr_farm_bu"]), "material requests,", len(baseline["employee_rows"]), "employee request rows")
EOF
```

Expected output: a line like `baseline: N material requests, M employee request rows` (exact N/M depend on current data — just note them).

- [ ] **Step 2: Run the migration**

```bash
cd /home/david/frappe/kaitet-bench
bench --site david.local migrate
echo "MIGRATE EXIT: $?"
```

Expected output: ends with `MIGRATE EXIT: 0`. If it fails with `QueueOverloaded` (a known transient issue on this bench when many Property Setter deletes enqueue `delete_dynamic_links` jobs faster than the worker drains them), temporarily raise the cap and retry:

```bash
bench --site david.local set-config max_queued_jobs 5000
bench --site david.local migrate
bench --site david.local set-config max_queued_jobs 500
```

- [ ] **Step 3: Verify removed fields are gone from the DB**

```bash
cd /home/david/frappe/kaitet-bench
bench --site david.local console <<'EOF'
removed = [
    ("Custom Field", "Material Request-custom_request_type"),
    ("Custom Field", "Material Request-custom_tractor_daily_task"),
    ("Custom Field", "Material Request-custom_vehicle_registration"),
    ("Custom Field", "Material Request-custom_reason"),
    ("Custom Field", "Material Request-custom_milk_customer"),
    ("Custom Field", "Material Request-custom_employee"),
    ("Custom Field", "Material Request-custom_employee_name"),
    ("Custom Field", "Material Request-custom_biometric_id"),
    ("Custom Field", "Material Request-custom_farm_selector"),
    ("Custom Field", "Material Request Item-custom_asset"),
    ("Property Setter", "Material Request-custom_employee_name-in_list_view"),
    ("Property Setter", "Material Request-custom_employee-in_list_view"),
    ("Property Setter", "Material Request-custom_request_type-in_list_view"),
    ("Property Setter", "Employee Request-location-fetch_from"),
]
still_there = [r for r in removed if frappe.db.exists(r[0], r[1])]
assert not still_there, f"still present: {still_there}"
print("OK: all 14 legacy records gone")
EOF
```

Expected output: `OK: all 14 legacy records gone`

- [ ] **Step 4: Verify re-homed fields exist with correct ownership**

```bash
cd /home/david/frappe/kaitet-bench
bench --site david.local console <<'EOF'
assert frappe.db.get_value("Custom Field", "Material Request-custom_farm", "module") == "Upande Stores"
assert frappe.db.get_value("Custom Field", "Material Request-custom_business_unit", "module") == "Upande Stores"
assert frappe.db.get_value("Custom Field", "Material Request-custom_employee_details", "module") == "Upande Stores"
assert frappe.db.get_value("Custom Field", "Material Request-custom_employee_data", "module") == "Upande Stores"
assert frappe.db.get_value("DocType", "Employee Request", "module") == "Upande Stores"
fieldnames = set(frappe.get_meta("Employee Request").get_valid_columns())
assert fieldnames == {"employee", "employee_name", "farm", "department"}, fieldnames
print("OK: ownership and Employee Request schema correct")
EOF
```

Expected output: `OK: ownership and Employee Request schema correct`

- [ ] **Step 5: Verify no data loss against the Task 5 Step 1 baseline**

```bash
cd /home/david/frappe/kaitet-bench
bench --site david.local console <<'EOF'
import json
baseline = json.load(open("/tmp/mr_migration_baseline.json"))
after_mr = frappe.get_all("Material Request", filters=[["custom_farm", "is", "set"]], fields=["name", "custom_farm", "custom_business_unit"], limit_page_length=0)
after_emp = frappe.get_all("Employee Request", fields=["name", "parent", "parenttype", "employee", "employee_name"], limit_page_length=0)
assert {r["name"]: (r["custom_farm"], r["custom_business_unit"]) for r in after_mr} == {r["name"]: (r["custom_farm"], r["custom_business_unit"]) for r in baseline["mr_farm_bu"]}
assert {r["name"] for r in after_emp} == {r["name"] for r in baseline["employee_rows"]}
print("OK: no data loss,", len(after_mr), "material requests,", len(after_emp), "employee request rows match baseline")
EOF
```

Expected output: `OK: no data loss, ...`

- [ ] **Step 6: Verify Stock Entry's shared use of Employee Request still works structurally**

```bash
cd /home/david/frappe/kaitet-bench
bench --site david.local console <<'EOF'
meta = frappe.get_meta("Stock Entry")
field = meta.get_field("custom_employee_data")
assert field and field.options == "Employee Request"
se_rows = frappe.get_all("Employee Request", filters={"parenttype": "Stock Entry"}, fields=["name"], limit_page_length=0)
print("OK: Stock Entry still wired to Employee Request,", len(se_rows), "existing rows")
EOF
```

Expected output: `OK: Stock Entry still wired to Employee Request, N existing rows`

---

### Task 6: Commit

**Files:** all files touched in `apps/upande_stores` across Tasks 2–3 (Task 1 and Task 4 live in `upande_kaitet`, which has no git — nothing to commit there).

- [ ] **Step 1: Review what changed in `upande_stores`**

```bash
cd /home/david/frappe/kaitet-bench/apps/upande_stores
git status --short
```

- [ ] **Step 2: Stage and commit**

```bash
cd /home/david/frappe/kaitet-bench/apps/upande_stores
git add upande_stores/doctype/employee_request upande_stores/custom/material_request.json
git commit -m "$(cat <<'EOF'
Add Material Request farm/business unit fields and re-home Employee Request

Moves the Employee Request child doctype (Material Request's and Stock
Entry's employee table) under this app's module so its lifecycle is tied
to upande_stores install/uninstall, and adds custom_farm/custom_business_unit
plus the rebuilt Employee Details section as Upande Stores-owned Custom
Fields for the same reason. Drops the unused location column.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
git status --short
```

Expected output after commit: `git status --short` shows a clean tree (aside from anything unrelated already present before this work started).

---

## Self-Review Notes

- **Spec coverage:** Design doc's sections A (deletions), B (re-homed fields), C (Employee Details rebuild), D (no scripts) each map to Task 1 (A), Task 3 (B), Tasks 2+3 (C), and the absence of any script-writing task (D) confirms nothing was silently added beyond scope.
- **Placeholder scan:** none found — every step has literal file paths, literal code, and literal expected output.
- **Type/name consistency:** `custom_employee_data`'s `options` (`"Employee Request"`) matches the doctype name produced by Task 2; `depends_on` on `custom_employee_data` matches the original verbatim (`eval:doc.material_request_type == "Material Issue"`); field_order removals in Task 1 match exactly the 3 fieldnames confirmed present in the live `field_order` property setter value (verified against the live DB Custom Field dump earlier in this project, not just the file).
