# Material Request → Stock Entry employee issuance lock

**Date:** 2026-07-17
**Apps touched:** `upande_stores` (data model, lock/unlock, duplicate validation), `upande_ta` (employee selection filtering)

## Problem

Material Request has an "Employee Data" table (`custom_employee_data`, a table of
`Employee Request` rows: `employee`, `employee_name`, `farm`, `department`) listing
employees who need items issued to them. Store staff issue items one employee at a
time by creating a Stock Entry from the submitted Material Request (via its "Create"
button) and selecting the receiving employee in `bio_employee` (Stock Entry's
biometric-verification field, owned by `upande_ta`).

Today nothing connects the two: `bio_employee` is a free Employee link with no
awareness of the Material Request's employee list, and nothing prevents the same
employee being issued against the same Material Request twice.

## Goal

1. When creating a Stock Entry against a Material Request, `bio_employee`'s options
   are scoped to that Material Request's not-yet-issued employees.
2. Submitting the Stock Entry marks that employee as issued for that Material
   Request. Cancelling the Stock Entry reverses it.
3. The same employee can't appear twice in one Material Request's Employee Data
   table (hard-blocked on save).

## Out of scope

- Stock Entry's own (now-deleted) `custom_employee_data`/`custom_biometric_data`
  tables and the `upande_scp` Spray Plan Transfers feature that used them — unrelated
  cleanup, handled separately.
- Changing `bio_employee`'s existing general-purpose biometric-verification behavior
  for Stock Entries with no Material Request context — that continues unchanged.

## Design

### 1. Data model

Add one field to `Employee Request` (child doctype, owned by `upande_stores`,
existing fields: `employee`, `employee_name`, `farm`, `department`):

| Field | Label | Type | Notes |
|---|---|---|---|
| `issued_via_stock_entry` | Issued Via Stock Entry | Link → Stock Entry | `read_only=1`, `in_list_view=1`, inserted after `department`. Empty = not yet issued. |

`in_list_view=1` so store staff can see directly in the Material Request's Employee
Data grid which employees have already been issued, and via which Stock Entry,
without being able to hand-edit it.

### 2. Resolving "which Material Request" for a Stock Entry

Stock Entry Detail rows carry a standard `material_request` link (populated when
items are pulled from a Material Request — confirmed this is always exactly one MR
per Stock Entry in this flow). Both the query function and the submit/cancel hooks
resolve the Material Request the same way: scan `doc.items`, take the first row with
a non-empty `material_request`. If none of the items have one, there is no MR
context — `bio_employee` behaves exactly as it does today (unrestricted Employee
link, no lock/unlock triggered). This keeps the feature purely additive.

This ~3-line resolution snippet is duplicated in both apps rather than shared, to
avoid introducing a cross-app import dependency between `upande_stores` and
`upande_ta`.

### 3. Selection filtering (`upande_ta`)

New whitelisted query function,
`upande_ta.upande_ta.overrides.stock_entry.material_request_employee_query`,
added to the existing `overrides/stock_entry.py` (already home to `bio_employee`-
adjacent biometric logic), wired as `bio_employee`'s `get_query` in the existing
`stock_entry.js` (already loaded via `doctype_js`).

- Resolve the Material Request (§2). If none, fall back to the standard
  unrestricted Employee query — today's behavior.
- If resolved, return Employees that appear as an `Employee Request` row under that
  Material Request (`parent = <MR>`, `parenttype = "Material Request"`) **and**
  whose row has `issued_via_stock_entry` empty.
- `bio_employee_name` and `department` keep fetching via their existing
  `fetch_from` — unchanged.

This is UI-side filtering only: it narrows what's *offered*, but the submit-time
hook (§4) is the actual enforcement.

### 4. Lock / unlock (`upande_stores`)

New `doc_events["Stock Entry"]` hooks in `upande_stores/hooks.py`, implemented in a
new `apps/upande_stores/upande_stores/overrides/stock_entry.py`:

- **`on_submit`**: resolve the MR (§2); if none, or `bio_employee` is empty, no-op.
  Otherwise look up the `Employee Request` row for `(parent=MR, employee=bio_employee)`.
  - If it already has a *different* `issued_via_stock_entry` set, block the submit
    with `frappe.throw` (e.g. "Employee {employee} has already been issued items
    under this Material Request via {other Stock Entry}") — covers the race where
    the dropdown filter was stale.
  - Otherwise stamp `issued_via_stock_entry = <this Stock Entry's name>` via
    `frappe.db.set_value` (direct child-row update, not a full parent Material
    Request reload/save — same lightweight pattern as `update_custom_scanned.py`'s
    `db_set` calls elsewhere in this codebase).
  - If `bio_employee` doesn't match any `Employee Request` row for that MR at all
    (e.g. `bio_employee` used for an unrelated verification purpose), no-op —
    stays backward-compatible with `bio_employee`'s existing general use.
- **`on_cancel`**: resolve the MR the same way; find the `Employee Request` row
  where `issued_via_stock_entry` equals *this* Stock Entry's name specifically (not
  just employee+MR, so cancelling never clears a lock belonging to a different
  entry), and reset it to empty.

### 5. Duplicate-employee validation (`upande_stores`)

New `doc_events["Material Request"]["validate"]` hook, in a new
`apps/upande_stores/upande_stores/overrides/material_request.py`: scan
`custom_employee_data` rows; if any `employee` value appears more than once,
`frappe.throw` naming the duplicated employee(s). Runs on every save (not just
once), so a duplicate can't be introduced after the fact. This also protects §4's
correctness — a duplicate row would make "which row is this?" ambiguous when
stamping `issued_via_stock_entry`.

## Testing approach

Standard `FrappeTestCase` unit tests:

- **`upande_stores`**: submit stamps the matching `Employee Request` row; cancel
  clears it; submitting a second Stock Entry for an already-issued employee+MR is
  blocked; a Stock Entry with no Material Request context is a no-op; saving a
  Material Request with a duplicated employee in `custom_employee_data` is blocked.
- **`upande_ta`**: the query function excludes already-issued employees for a given
  MR and falls back to the unrestricted query when there's no MR context.

## Known limitations (accepted)

None outstanding — the duplicate-employee case that was the one open limitation is
now hard-blocked by §5.
