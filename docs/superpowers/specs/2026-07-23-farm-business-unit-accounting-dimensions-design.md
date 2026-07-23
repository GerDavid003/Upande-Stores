# Farm/Business Unit move to Accounting Dimensions

**Date:** 2026-07-23
**Apps touched:** `upande_stores` only

## Problem

`Farm` and `Business Unit` have just been configured as real Frappe Accounting
Dimensions on `david.local` (fieldnames `farm`/`business_unit`, confirmed via
`tabAccounting Dimension`), which auto-added `farm`/`business_unit` fields to a
large set of doctypes including `Stock Entry`, `Stock Entry Detail`, and
`Material Request Item` — but **not** `Material Request` itself.

`upande_stores` already has its own app-owned `custom_farm`/`custom_business_unit`
fields on `Stock Entry` (header-level) and on `Material Request` (header-level,
user-facing pick fields). Going forward:
- `Stock Entry`'s app-owned fields become redundant with the new Accounting
  Dimension fields and should be removed.
- `Material Request`'s app-owned fields stay (that's where the user actually
  picks Farm/Business Unit) — but since Material Request itself has no
  Accounting Dimension field of its own, the value needs to flow down to
  where the dimension fields actually live: `Material Request Item`, and from
  there to `Stock Entry Detail`.

The PPE workflow (built across two earlier plans, same app) reads Stock
Entry's `custom_farm`/`custom_business_unit` directly in one place — that
read breaks silently (returns `None`, no error) once those fields are removed.

## Goal

1. Remove `custom_farm`/`custom_business_unit` from `Stock Entry`.
2. `Material Request.custom_farm`/`.custom_business_unit` (kept, unchanged)
   propagate onto every `Material Request Item` row's own `farm`/`business_unit`
   Accounting Dimension fields.
3. When a Stock Entry is created against a Material Request, each Stock Entry
   Detail row inherits `farm`/`business_unit` (alongside the already-inherited
   `cost_center`) from the Material Request Item it's linked to.
4. `create_ppe_assignments` (the PPE issuance function) reads `farm`/
   `business_unit` from the Stock Entry Detail row it's processing, not from
   the (now-removed) Stock Entry header fields.

## Out of scope

- `Employee.custom_farm`/`.custom_business_unit` (owned by `upande_hr`) — a
  completely separate pair of fields on a different doctype, untouched by
  this change.
- `Material Request.custom_farm`'s own `fetch_from: set_from_warehouse.custom_farm`
  (Warehouse → Material Request) — unrelated data flow, untouched.
- Anything about how the Accounting Dimensions were configured (reference
  doctype list, mandatory/default settings) — that's already done, on the
  site, outside any app's code.
- `Employee PPE Assignment.farm`/`.business_unit` — these stay exactly as they
  are (plain Link fields, not Accounting Dimensions); only where their *value*
  originates changes (Stock Entry Detail row instead of Stock Entry header).

## Design

### 1. Remove from Stock Entry

Delete the `custom_farm`/`custom_business_unit` Custom Field records from the
site, and remove their two entries from
`upande_stores/upande_stores/custom/stock_entry.json`.

### 2. Material Request → Material Request Item

New `validate` hook in `upande_stores/overrides/material_request.py`
(alongside the existing `validate_no_duplicate_employees`/
`validate_employee_data_required_for_material_issue`):

```python
def sync_accounting_dimensions_to_items(doc, method=None):
    """Material Request validate: custom_farm/custom_business_unit are
    header-level, user-facing pick fields, but the Farm/Business Unit
    Accounting Dimensions only exist at the Material Request Item level
    (Material Request itself isn't a reference doctype for them) -- so the
    header value has to be pushed down onto every item row explicitly."""
    for row in doc.items:
        if doc.custom_farm:
            row.farm = doc.custom_farm
        if doc.custom_business_unit:
            row.business_unit = doc.custom_business_unit
```

### 3. Material Request Item → Stock Entry Detail

Extend the existing `inherit_cost_center_from_material_request` in
`upande_stores/overrides/stock_entry.py` (already hooked on Stock Entry
`validate`) into `inherit_accounting_dimensions_from_material_request`,
fetching all three dimension-like fields in one lookup instead of adding a
near-duplicate second function:

```python
def inherit_accounting_dimensions_from_material_request(doc, method=None):
    """Stock Entry validate: a row created from a Material Request Item
    should carry that item's cost center, farm, and business unit -- not
    whatever Stock Entry itself defaulted to. Runs on every save, not just
    insert, so it self-heals if something resets a row's value afterward."""
    for row in doc.items:
        if not row.material_request_item:
            continue
        mr_item = frappe.db.get_value(
            "Material Request Item",
            row.material_request_item,
            ["cost_center", "farm", "business_unit"],
            as_dict=True,
        )
        if not mr_item:
            continue
        if mr_item.cost_center:
            row.cost_center = mr_item.cost_center
        if mr_item.farm:
            row.farm = mr_item.farm
        if mr_item.business_unit:
            row.business_unit = mr_item.business_unit
```

This is a rename + extension of already-shipped, already-reviewed code, not a
purely additive change — flagged explicitly since it touches a prior task's
output. The function's existing call site in `hooks.py`'s
`doc_events["Stock Entry"]["validate"]` gets its string updated to the new
name; behavior for `cost_center` is unchanged.

### 4. Fix the PPE regression

In `create_ppe_assignments` (same file), the two lines currently reading
Stock Entry's header-level custom fields:

```python
"farm": doc.get("custom_farm"),
"business_unit": doc.get("custom_business_unit"),
```

become row-level reads, since the value now lives per Stock Entry Detail row
rather than assumed constant across the whole document:

```python
"farm": row.get("farm"),
"business_unit": row.get("business_unit"),
```

(`create_ppe_assignments` already loops `for row in doc.items:` per PPE item
— this is a like-for-like swap of the source, not a new loop structure.)

### 5. Test fixtures

- `upande_stores/upande_stores/tests/test_helpers.py`'s
  `make_stock_entry_for_material_request` currently sets `custom_farm`/
  `custom_business_unit` on the Stock Entry dict — drop both; the value now
  arrives via the inheritance chain (MR header → MR Item → Stock Entry Detail)
  once `make_material_request` (which already sets `custom_farm`/
  `custom_business_unit` at the MR header level) triggers the new Task 2
  hook on insert.
- Every inline Stock Entry construction in `overrides/test_stock_entry.py`
  that currently sets `custom_farm`/`custom_business_unit` needs the same
  fields dropped (the implementation task will need to check each call site
  individually — some may need `farm`/`business_unit` set directly on the
  item row instead, for tests that build a Stock Entry with no linked
  Material Request Item at all).
