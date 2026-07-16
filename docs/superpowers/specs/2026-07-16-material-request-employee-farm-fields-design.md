# Material Request: Employee Details rebuild + Farm/Business Unit re-homing

Date: 2026-07-16
App: upande_stores (primary), upande_kaitet (cleanup)
Site verified against: david.local

## Context

Material Request currently carries 23 custom fields owned by `upande_kaitet`
(via `upande_kaitet/upande_kaitet/custom/material_request.json`, a "Customize
Form export" synced on every migrate). This includes farm/business
unit/request-type fields, a set of hidden single-employee fields, and an
"Employee Details" section containing a Farm Selector and an Employee Data
table (child doctype `Employee Request`).

Goal: move Farm and Business Unit ownership to `upande_stores`, rebuild the
Employee Details section as a clean employee/employee name/department/farm
table, retire Request Type and everything that depends on it, and make all of
it install/update/uninstall cleanly with the `upande_stores` app lifecycle.

## Verified facts (live DB, not just files)

- `Custom Field` and `Property Setter` both have a `module` Link(Module Def)
  field. Frappe's app-uninstall routine
  (`frappe.installer.remove_app` → `_delete_modules` →
  `_delete_linked_documents`) auto-deletes every doctype record whose `module`
  field matches the app's Module Def name. No custom uninstall hook is needed
  if we tag our fields with `module: "Upande Stores"`.
- The "Customize Form export" sync (`frappe.modules.utils.sync_customizations`)
  **upserts by fieldname** (insert if missing, update in place if it already
  exists) — it never deletes a Custom Field/Property Setter that's been
  removed from the JSON file. Fields being fully retired need an explicit
  one-time patch to delete the existing DB rows; fields merely changing
  owning app do not (updating in place is sufficient and preserves the
  existing DB column and its data, since deleting/updating a Custom Field
  record never drops the underlying DB column).
- There are currently **zero** `Accounting Dimension` records configured on
  this site. The `is_system_generated: 1` `farm` field seen on Material
  Request Item / Sales Order / Stock Entry is a leftover from a since-deleted
  dimension, not a live feature. Per user decision, syncing `custom_farm` into
  an accounting-dimension farm field is out of scope for this build.
- Module Def `Upande Stores` already exists and the app is already installed
  on `david.local`.
- `upande_stores` is a git repo (branch `upande-kaitet`). `upande_kaitet` has
  no `.git` at all — changes there are made on disk but cannot be committed.

## Changes

### A. Deleted entirely (patch in `upande_kaitet`, removed from its custom/*.json)

Material Request:
- `custom_request_type` (Link, "Request Type For Approval")
- `custom_tractor_daily_task`, `custom_vehicle_registration`, `custom_reason`,
  `custom_milk_customer` (all `depends_on` referencing `custom_request_type`)
- `custom_employee`, `custom_employee_name`, `custom_biometric_id` (hidden
  header fields, `material_request_type == "Material Issue"`)
- `custom_farm_selector` (Farm Selector, superseded by the rebuilt table)
- Property Setters tied to any of the above (e.g. `custom_request_type`
  in_list_view)

Material Request Item:
- `custom_asset` (Link → Asset)

Both doctypes' `field_order` property setters get the now-dead fieldnames
pruned.

### B. Re-homed to `upande_stores` (same fieldname, same position — pure ownership change, no patch needed)

- `custom_farm` — Link → Farm, required, insert_after `custom_purpose`, plus
  its `in_list_view=1` property setter
- `custom_business_unit` — Link → Business Unit, required, insert_after
  `custom_farm`

### C. Employee Details section rebuild

- `Employee Request` child doctype: change `module` to `Upande Stores`, move
  its folder from `upande_kaitet` to `upande_stores`. Trim fields to exactly:
  `employee` (Link → Employee), `employee_name` (Data, fetch_from
  `employee.employee_name`, read-only), `department` (Data, fetch_from
  `employee.department`, read-only), `farm` (Data, fetch_from
  `employee.custom_farm`, read-only). Drop `location`.
- `custom_employee_details` Section Break ("Employee Details", insert_after
  `custom_total`) and `custom_employee_data` Table field (same fieldname,
  `depends_on: material_request_type == "Material Issue"`, options
  `Employee Request`) recreated under `upande_stores`, module-owned there.

### D. Scripts

None required — every change above is declarative field/doctype structure
(`fetch_from` handles auto-population without any script). No `api/` or
`overrides/` folders are being scaffolded speculatively. When a future
customization needs server logic on Material Request, it will go through
`override_doctype_class` pointing at a controller file inside
`upande_stores`'s own doctype-override structure (since Material Request's
own `.py` belongs to core ERPNext, not this app); client scripts via
`doctype_js`; whitelisted endpoints under an `api/` folder — matching the
convention already used in `upande_kaitet`.

## Out of scope (explicitly deferred by user)

- Syncing `custom_farm` into any accounting-dimension-generated `farm` field
  (no such dimension is currently active on this site).
- The header-level `custom_asset` field (depends on `custom_business_unit`) —
  only the **Material Request Item child row's** `custom_asset` is being
  removed.
