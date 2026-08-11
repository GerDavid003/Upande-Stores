# Move employee allocation from Employee Data table onto Items table

**Date:** 2026-08-11
**Apps touched:** `upande_stores` (primary), `upande_ta` (bio_employee picker query)

## Problem

Material Request currently tracks per-employee item allocation via a
separate child table, `custom_employee_data` (`Employee Request` doctype),
which is kept in sync with the standard `items` table by a dedicated hook
(`sync_employee_allocations_to_items`). Maintaining two tables — one
user-facing (Employee Data) and one derived (Items) — is more indirection
than the feature needs: an employee's allocation is fundamentally "this item
row is for this person," which is naturally a property of the item row
itself, not a separate table that has to be kept in lockstep with it.

## Goal

Record `employee` directly on each Material Request Item row. Remove the
`Employee Request` doctype and `custom_employee_data` field entirely, along
with the derivation hook that existed only to keep the two tables in sync.
Preserve every existing behavioral guarantee from the current design:

- Partial issuance does not lock an employee out of further issuance for
  their remaining quantity.
- The same employee may appear on multiple rows (once per item they need).
- No duplicate (employee, item_code) pair.
- Issuing an item to an employee who isn't allocated it is blocked.

## Out of scope

- Migrating existing Employee Data on already-open Material Requests (e.g.
  MAT-MR-2026-00017) onto the new Items-table fields. The actual stock
  movements for those requests already happened via Stock Entry / Employee
  PPE Assignment records, independent of Employee Data — only the "who this
  item was originally for" breadcrumb on old documents is lost, and that's
  accepted, not remediated.
- Any change to `create_bulk_ppe_purchase_request` — it's a Purchase-type
  request and has never tracked employees.
- Any change to `sync_accounting_dimensions_to_items` (farm/business_unit
  header→item push) or the client-side live-sync script for the same —
  unrelated to this redesign, both keep working exactly as they do today.

## Design

### 1. Schema

- Delete the `Employee Request` doctype (folder, DB table, everything).
- Delete the `custom_employee_data` field on Material Request.
- Add three new fields to `Material Request Item`:
  - `employee` — Link → Employee, optional.
  - `qty_issued` — Float, read-only, default 0.
  - `issued_via_stock_entry` — Link → Stock Entry, read-only.

  These are the same three fields the old design tracked on `Employee
  Request`, just living on the row they're actually about now.

### 2. Validation (`overrides/material_request.py`)

Two existing functions are replaced (not extended):

- `validate_employee_data_required_for_material_issue` (checked "at least
  one row in custom_employee_data") is replaced by
  `validate_employee_required_for_material_issue`: when
  `material_request_type == "Material Issue"`, **every** item row must have
  `employee` set — not just one. A Material Issue request is always issuing
  specific items to specific people, so a row with a blank employee on that
  request type is treated as a data-entry mistake, not a valid case. Other
  request types (Material Transfer, Purchase, ...) leave `employee` fully
  optional, matching ordinary bulk stock movements attributed to no one.
  Enforced via a real `validate()` hook, not `reqd`/`mandatory_depends_on`
  (never enforced server-side in this Frappe version, confirmed repeatedly
  elsewhere in this codebase).

- `validate_employee_allocations` is repointed at `doc.items` instead of
  `doc.custom_employee_data`: no two item rows may share the same
  `(employee, item_code)` pair when `employee` is set on both. Rows with a
  blank `employee` are unconstrained against each other (ordinary bulk items
  can repeat item_code freely). The old "qty required when item_code is set"
  half of this check is dropped entirely — `qty` is already a mandatory core
  field on every Material Request Item row, so there's nothing left to
  enforce there.

- `sync_employee_allocations_to_items` is deleted outright. There is no
  longer a separate table to derive `items` from — `items` is the data.

### 3. Locking (`overrides/stock_entry.py`)

`lock_issued_employee` / `unlock_issued_employee` change what they match
against: instead of looking up an `Employee Request` row, they look up
`Material Request Item` rows under the resolved Material Request. Because
more than one row can share the same `item_code` (e.g. the same item
allocated to two different employees on two separate rows), the match is
two-step, per Stock Entry item row (`item_code = X`, issued by
`doc.bio_employee`):

1. Look for a Material Request Item row with `item_code == X` **and**
   `employee == doc.bio_employee`. If found, this is the allocation —
   accumulate `qty_issued` on that row, set `issued_via_stock_entry` once
   `qty_issued >= qty`, exactly like today's qty-threshold logic.
2. Otherwise, look for a Material Request Item row with `item_code == X`
   and a **blank** `employee`. If found, this item isn't tracked for
   per-employee locking at all — no-op. (This is the direct replacement for
   the old "blank Employee Request row" case; note that per section 2, a
   Material Issue request can never actually have a blank-employee row —
   every row is required to have one — so in practice this branch only
   matters for non-Material-Issue request types, where `employee` stays
   optional and locking logically doesn't apply anyway.)
3. Otherwise (every row with `item_code == X` has some *other*, specific
   employee set) → throw ("not allocated this item"), the same protection
   added for the wrong-employee-issuance fix.

`unlock_issued_employee` is the exact mirror on cancel, same asymmetry as
before (cancel never throws on no-match, so an already-submitted mismatched
Stock Entry can still be undone).

### 4. PPE issuance (`api/ppe.py`)

- `create_ppe_onboarding_material_request`: each appended item row gets
  `employee: employee` set directly (the same single employee on every row,
  since onboarding always builds one employee's kit). Drop
  `custom_employee_data` from the created document entirely.

- `create_bulk_ppe_material_request`: change the merge key from `item_code`
  alone to the `(employee, item_code)` pair — each assignment's quantity is
  merged only with another assignment for the *same employee and same
  item*, never across employees. (A bare "one row per assignment," with no
  merging at all, would risk violating section 2's new no-duplicate-pair
  check in the edge case of one employee having two separate assignments
  for the same item_code needing replacement at once.) A bulk replacement
  covering 3 employees × 2 items each, no employee needing the same item
  twice, now produces 6 item rows instead of 2 merged rows plus 3
  blank-item employee rows — this is the accepted, confirmed tradeoff for
  this redesign. Drop `custom_employee_data`.

- `create_bulk_ppe_purchase_request`: no changes.

### 5. `upande_ta`'s bio_employee picker

`material_request_employee_query` is rewritten to query `Material Request
Item` rows directly (filtered by parent Material Request, `employee` set,
not yet issued via the `item_codes` filter already added for the
wrong-employee-issuance fix) instead of `Employee Request` rows. This is a
bigger rewrite than the `item_codes`-filter addition — the underlying query
target changes doctype entirely — but the external contract (same filters
dict shape, same fallback-to-unrestricted-search behavior when there's no
Material Request context) stays the same.

### 6. Rollout

No data migration. Existing Employee Data on any currently-open Material
Request is not carried over onto the new Items-table fields — accepted per
the Out of scope section above.
