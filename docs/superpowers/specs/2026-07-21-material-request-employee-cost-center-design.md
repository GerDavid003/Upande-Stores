# Material Request — mandatory employee on Material Issue, cost center inheritance

**Date:** 2026-07-21
**Apps touched:** `upande_stores` only

## Problem

Two gaps on `Material Request`:

1. A `Material Issue` request can be submitted with zero employees in its
   `custom_employee_data` table (Employee Data — a table of `Employee Request`
   rows), or with a row that has no `employee` selected at all — nothing enforces
   that a Material Issue actually names who it's for.
2. When a Stock Entry is created from a submitted Material Request, its item
   rows' `cost_center` doesn't carry over from the Material Request Item's own
   `cost_center` (a standard ERPNext field) — it ends up defaulting to the
   Company's default cost center ("Main") regardless of what was selected at
   the Material Request level.

## Goal

1. Block a `Material Issue` Material Request from being saved with an empty
   Employee Data table, and block any row in that table from being saved
   without an `employee` selected.
2. When a Stock Entry's item row is linked back to a Material Request Item
   (`material_request_item` set) and that Material Request Item has a
   `cost_center`, the Stock Entry row's `cost_center` should match it —
   overriding whatever default value Stock Entry itself computed.

## Out of scope

- No changes to `material_request_type` values other than `Material Issue` —
  Material Transfer/Purchase/Customer Provided requests are unaffected by
  either change.
- No change to Stock Entry rows that aren't linked to a Material Request Item
  (`material_request_item` empty) — their cost center behaves exactly as
  before.
- If the Material Request Item has no `cost_center` set, the Stock Entry's own
  computed default is left alone — this is inheritance, not a requirement that
  every Stock Entry row have a cost center.
- A person can still manually change the Stock Entry's cost center after
  creation, but it will be re-set back to the Material Request Item's value on
  the next save (this is treated as self-healing, not a bug — the Material
  Request's cost center is the source of truth once specified).

## Design

### 1. Mandatory employee on Material Issue

Two small edits, no new fields:

- `Material Request.custom_employee_data` (Custom Field, in
  `upande_stores/upande_stores/custom/material_request.json`): add
  `"mandatory_depends_on": "eval:doc.material_request_type == \"Material Issue\""`
  — it already has the matching `depends_on`, just not the mandatory flag.
  A mandatory Table field in Frappe requires at least one row.
- `Employee Request.employee` (the child doctype's own field, in
  `upande_stores/upande_stores/doctype/employee_request/employee_request.json`):
  set `"reqd": 1`. `Employee Request` exists solely to back this table, so
  making its `employee` field unconditionally required is safe — there's no
  other context this doctype is used in.

Together these close the loophole of adding a blank row just to satisfy "at
least one row."

### 2. Cost center inherited from Material Request

New function in the existing `upande_stores/overrides/stock_entry.py`
(alongside `lock_issued_employee`/`unlock_issued_employee`/`create_ppe_assignments`),
hooked on Stock Entry's `validate` event — a new key in `hooks.py`'s
`doc_events["Stock Entry"]` dict (currently only has `on_submit`/`on_cancel`):

```python
def inherit_cost_center_from_material_request(doc, method=None):
    """Stock Entry validate: a row created from a Material Request Item
    should carry that item's cost center, not whatever Stock Entry itself
    defaulted to (observed: falls back to the Company's default "Main" cost
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

Runs on `validate` (every save), not `before_insert`, so it keeps correcting
the value even if a later edit or client-side default recomputes it — matches
this file's existing validate/on_submit hook pattern.
