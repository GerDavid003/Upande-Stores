# PPE Workflow

**Date:** 2026-07-20
**Apps touched:** `upande_stores` (Item/Material Request/Employee Onboarding customizations, PPE Policy, Employee PPE Assignment, PPE Inspection, all automation), `upande_hr` (Employee PPE History only)

## Problem

`upande_kaitet` (frappe-bench) has a working PPE issuance/inspection/replacement
workflow, but almost none of its logic lives in the app's git-tracked code: the
doctype controllers (`ppe_inspection.py`, `employee_ppe_assignment.py`, etc.) are
empty stubs, and the real automation is a set of Server Script / Client Script
DocType records living only in that site's database. It doesn't ship with the app,
isn't portable, and won't survive a fresh install.

We're rebuilding the same workflow as proper app code in `upande_stores`
(kaitet-bench), with `Employee PPE History` specifically owned by `upande_hr`
instead, and picking up several corrections along the way (see Corrections below).

## Pre-flight: two name collisions on the target site (`david.local`)

1. `upande_kaitet` is installed on `david.local` and already owns 8 doctypes named
   `PPE Policy`, `PPE Policy Item`, `PPE Onboarding Item`, `Employee PPE Assignment`,
   `Employee PPE History`, `PPE Inspection`, `PPE Inspection Item`, `PPE Material`
   (all 0 rows) plus 27 Custom Fields under its module. Confirmed with the requester:
   uninstall `upande_kaitet` from `david.local` entirely before creating the
   rebuilt doctypes — frees the names, no data lost.
2. Independently of that: the site already has 4 **orphaned** Custom Fields with
   `module = NULL` (not owned by `upande_kaitet`, so step 1 won't remove them):
   `Item-custom_is_ppe`, `Item-custom_ppe_lifespan`, `Employee-custom_ppe_history`,
   `Employee-custom_ppe_issuance`. These must be deleted before the rebuild creates
   fields with the same names under the correct module tags.

## Out of scope

- `PPE Material` doctype — dropped. Its fields were mistyped (Link options
  pointing at "Stock Entry" for what should be an Item/UOM/Qty), and nothing in
  the real workflow references it as a child table anywhere.
- `PPE Inspection Notifications` (the +1-month / -1-month email nudges) — not
  requested; can be a follow-up if wanted.
- Changing how `bio_employee` / the Stock Entry employee-issuance lock
  (`upande_stores/overrides/stock_entry.py`) works in general — untouched, we only
  add a second `on_submit` hook function alongside it.

## Data model

### Item (custom fields, module `Upande Stores`)

| Field | Type | Notes |
|---|---|---|
| `custom_is_ppe` | Check | insert_after `image` |
| `custom_ppe_lifespan` | Int, label "PPE Lifespan (Months)" | `depends_on`/`mandatory_depends_on` = `eval:doc.custom_is_ppe==1` |

### PPE Policy (new doctype, `upande_stores`)

| Field | Type | Notes |
|---|---|---|
| `company` | Link → Company | **mandatory** — scopes policies per company, not a wildcard-match dimension |
| `department` | Link → Department | optional |
| `designation` | Link → Designation | optional |
| `active` | Check, default 1 | |
| `description` | Small Text | |
| `items` | Table → PPE Policy Item | mandatory |

`validate()`: at least one of department/designation required; if `active`, no
other `active=1` policy may exist for the same `company` + `department` +
`designation` combination (company is now part of the uniqueness key, per
"Company can be mandatory for record separation").

### PPE Policy Item (child, `upande_stores`)

`item_code` (Link → Item, reqd), `item_name` (fetched, read-only), `quantity` (Int,
default 1, reqd). `validate()`: throws if `item_code` isn't `custom_is_ppe`.

### Employee Onboarding (custom fields, module `Upande Stores`)

| Field | Type | Notes |
|---|---|---|
| `custom_ppe_requirements_section` | Section Break | insert_after `holiday_list` |
| `custom_ppe_requirements` | Table → PPE Onboarding Item | |
| `custom_ppe_material_request` | Link → Material Request | read-only, system-set |

### PPE Onboarding Item (child, `upande_stores`)

`item_code`, `item_name` (fetched), `quantity` (default 1), `issued` (Check,
default 0) — unchanged from `upande_kaitet`.

### Material Request (custom field, module `Upande Stores`)

| Field | Type | Notes |
|---|---|---|
| `custom_ppe_issuance` | Check, label "PPE Issuance" | read-only (system-set only); auto-checked **only** when our automation creates a `Material Issue` request (onboarding issuance or replacement issuance) — **never** for the Purchase-type replacement request, per requester's decision |

`upande_stores` already dropped the old `custom_purpose`/`custom_request_type`
fields and relabelled `Material Request Item.description` to "Purpose" (mandatory)
— confirmed, no change needed there. Our automation sets `description` on the
item rows it creates: `"PPE Issuance"` for issuance-type rows, `"PPE Purchase"` for
purchase-type rows (replacing the old inconsistent `"PPE Replacement"` /
`"PPE Purchase"` strings — same purpose value for every issuance path, new-hire or
replacement, since it's the same kind of transaction).

### Employee PPE Assignment (new doctype, `upande_stores`)

Same shape as `upande_kaitet`'s version (`employee`, `item_code`, `quantity`,
`company`/`farm`/`business_unit` fetched from `stock_entry`, `issue_date`,
`lifespan_months` fetched from `item_code.custom_ppe_lifespan`, `expiry_date`,
`stock_entry`, `status` [Active/Inactive/Expired/Returned], `last_inspection_date`,
`last_inspection_status`, `last_inspection`, `replacement_requested`,
`replacement_material_request`, `replacement_purchase_request`,
`replacement_assignment`), with one change:

- `last_inspection_status` options trimmed to `OK / Worn Out / Lost` — "Needs
  Repair" removed (it was never reachable from the Inspection Item picklist
  anyway, per requester's decision to drop it).

### PPE Inspection / PPE Inspection Item (new doctypes, `upande_stores`)

Same shape as `upande_kaitet` (submittable Inspection with `employee`,
`supervisor`, `farm`, `company` fetched, `inspection_date`, `items_inspected`
table; Inspection Item with `employee_ppe_assignment`, fetched `item_code`/
`issue_date`, `current_status` [OK/Worn Out/Lost — already only 3 options, no
change needed], `other_reason`, `comments`, `update_assignment` hidden Check
default 1, `inspection_result_date`).

### Employee PPE History (new doctype, **`upande_hr`**)

Same shape as `upande_kaitet`'s version: `ppe_assignment` (Link → **Employee PPE
Assignment**, which lives in `upande_stores`), `item_code`, `quantity`,
`issue_date`, `expiry_date`, `status`, `stock_entry`, `ppe_inspection`,
`last_inspection_date`, `last_inspection_status`. Attached to **Employee** via two
custom fields in `upande_hr`'s module: `custom_ppe_issuance` (Section Break,
insert_after `custom_company_assets`) and `custom_ppe_history` (Table).

This makes `upande_hr` depend on `upande_stores` (the Link field needs that
doctype to exist) — declared via `required_apps = ["upande_stores"]` in
`upande_hr/hooks.py`. Conversely, the sync code that *writes* History rows lives in
`upande_stores`'s `Employee PPE Assignment` controller — it must not hard-fail if
`upande_hr` isn't installed, so every History write is guarded by
`"upande_hr" in frappe.get_installed_apps()`. This keeps `upande_stores` usable on
its own; `upande_hr` is an optional enhancement, not a hard dependency in that
direction.

## Business logic (all as app code — no DB Server/Client Scripts)

| Old Server/Client Script | New home |
|---|---|
| `PPE Onboarding Requirements` (API) | `upande_stores/api/ppe.py::get_ppe_requirements_for_onboarding` — now also filters by `company == employee.company` (mandatory exact match) in addition to optional dept/designation |
| `PPE Onboarding Integration` (Client Script) | `upande_stores/public/js/employee_onboarding.js`, loaded via `doctype_js` hook |
| `PPE Onboarding Material Request` (API) | `upande_stores/api/ppe.py::create_ppe_onboarding_material_request` |
| `PPE Issuance Assignment Creation` (Stock Entry, Server Script) | `upande_stores/overrides/stock_entry.py::create_ppe_assignments` — hooked alongside the existing `lock_issued_employee` on `Stock Entry.on_submit`. **Keyed off `doc.bio_employee`** (the `upande_ta`-owned field used by the existing employee-issuance-lock feature), not the old `custom_employee_data` table — that plumbing doesn't exist on Stock Entry in this app. |
| `Sync PPE Assignment` (After Insert, Server Script) | `Employee PPE Assignment.on_insert` (controller method), guarded by the installed-apps check above |
| `Keep Status in Sync` (After Save, Server Script) | `Employee PPE Assignment.on_update` (controller method), same guard |
| `Update Due Date` (Before Save, Server Script) | `Employee PPE Assignment.validate` (controller method) |
| `Update on PPE Assignment` (PPE Inspection, After Submit) | `PPE Inspection.on_submit` (controller method) — **corrected**: `Lost`/`Worn Out` now set the assignment's `status` to `Inactive` (was a no-op bug that always left it `Active`); `OK` sets it back to `Active` |
| `PPE Auto Expire` (Scheduler) | `upande_stores/tasks.py::mark_expired_ppe_assignments`, registered under `scheduler_events.daily` |
| `Create Bulk Requisition` (API `create_bulk_ppe_material_request`) | `upande_stores/api/ppe.py::create_bulk_ppe_material_request` — eligibility now `status in (Inactive, Expired, Returned)` **or** `last_inspection_status in (Worn Out, Lost)`; checks `custom_ppe_issuance = 1` on the created MR |
| `Create Bulk PPE Purchase Request` (API) + `PPE Assignment Raise Purchase Request` (Client Script, single-record button) | Merged into one: `upande_stores/api/ppe.py::create_bulk_ppe_purchase_request`, called both from the list-view bulk action and from a single-record form button (passing a one-item list) — removes the duplicate code path that had its own, looser rules. Does **not** set `custom_ppe_issuance` (Purchase MR). |
| `Bulk Requisition Button` (Client Script, list view) | `upande_stores/public/js/employee_ppe_assignment_list.js`, loaded via `doctype_list_js` |
| `Filter on PPE Inspection Item` (Client Script) | `upande_stores/doctype/ppe_inspection/ppe_inspection.js` (own doctype, auto-loaded) |
| `PPE MR Cancel/Delete Unlink` (Material Request, Server Script) | `upande_stores/overrides/material_request.py::unlink_ppe_replacement`, hooked on `on_cancel`/`on_trash`; now keyed off `doc.custom_ppe_issuance` instead of the removed `custom_request_type` field |

## Corrections applied (beyond the requester's 5 explicit decisions)

1. Inspection → assignment status: `Lost`/`Worn Out` now actually change `status`
   to `Inactive` (requester's decision #2); `OK` sets it back to `Active`. Dropped
   the old side-effect of stamping `returned_date` on `Lost` — that field means
   "physically handed back in good condition," which doesn't describe a lost item.
2. `Needs Repair` removed from `Employee PPE Assignment.last_inspection_status`
   (requester's decision #3) so its options match `PPE Inspection Item.current_status`
   exactly (`OK` / `Worn Out` / `Lost`) — no more dead/unreachable option.
3. `Employee PPE History.last_inspection_date` / `.last_inspection_status` are now
   set explicitly by the sync code instead of relying on `fetch_from`, which
   doesn't reliably fire on the direct `insert()`/`db.set_value()` writes this flow
   uses — they were often stale in the old build.
4. One purchase-request code path instead of two (see table above) — same
   eligibility rules whether raised from one record or several.
5. Purpose string on generated Material Request Item rows is uniform:
   `"PPE Issuance"` for every Material Issue row this workflow creates (new-hire
   onboarding or replacement), `"PPE Purchase"` for Purchase rows — replaces the
   old inconsistent `"PPE Replacement"` used even for first-time onboarding issuance.
6. Company added to the "no duplicate active policy" uniqueness check on PPE
   Policy, not just to matching — two companies can each have their own active
   policy for the same department/designation pair.

## Install / uninstall

- New doctypes (`PPE Policy`, `PPE Policy Item`, `PPE Onboarding Item`, `Employee
  PPE Assignment`, `PPE Inspection`, `PPE Inspection Item` in `upande_stores`;
  `Employee PPE History` in `upande_hr`) are removed automatically by Frappe when
  their owning app is uninstalled — no extra code needed, as long as they carry
  the correct `module`.
- Custom Fields on Item / Material Request / Employee Onboarding (`upande_stores`)
  and on Employee (`upande_hr`) must be tagged with the owning app's module so the
  existing `before_uninstall` cleanup hooks in each app pick them up:
  `upande_stores/upande_stores/install.py` (deletes Custom Field + Property Setter
  by module) already does this; `upande_hr/upande_hr/install.py` only deletes
  Custom Field (no Property Setter) — sufficient here since we add no Property
  Setters in `upande_hr`.
