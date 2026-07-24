# Per-employee item allocation on Material Request

**Date:** 2026-07-24
**Apps touched:** `upande_stores` only

## Problem

`MAT-MR-2026-00016` requests 3 items (Amisil ×10, MPK ×12, Protap ×16) for 3
employees (Otieno David, Gloria Masika, James Guchu) — one item per employee.
A Stock Entry (`SE-2026-00014`) issued Otieno only 3 of his 10 Amisil (a
partial issuance). The moment it submitted, `lock_issued_employee` (built in
an earlier plan) stamped `issued_via_stock_entry` on Otieno's Employee
Request row — which is also what scopes `bio_employee`'s "not yet issued"
picker (owned by `upande_ta`) — permanently removing him from it, even though
he's still owed 7 more Amisil.

Root cause: nothing on the Material Request records *which* employee needs
*which* item, or how much. `lock_issued_employee` treats "a Stock Entry
touched this employee at all" as "this employee is done," because there's no
data to know what "done" actually means for them. The Items table and the
Employee Data table are two independent lists with no row-level connection.

## Goal

1. Let whoever raises a Material Issue Material Request record, per employee,
   which item and how much they need — directly on the Employee Data table,
   filled in at request time.
2. Track how much of that allocation has actually been issued so far.
3. Only lock an employee's row (in the existing `issued_via_stock_entry`
   sense) once their specific allocation has been fully issued — partial
   issuances keep them selectable for follow-up Stock Entries.
4. Support one employee needing multiple different items (multiple Employee
   Data rows for the same employee, one per item).
5. Derive the standard Material Request Items table (which ERPNext's stock
   engine requires regardless) from the sum of per-employee allocations,
   instead of requiring it to be filled in separately and kept in sync by
   hand.

## Out of scope

- `upande_ta`'s `bio_employee` query/filter logic — untouched. It already
  filters on whether `Employee Request.issued_via_stock_entry` is set; this
  feature only changes *when* `upande_stores` sets that field, not the field
  itself or who reads it.
- The existing PPE workflow's own Material Request creation
  (`create_ppe_onboarding_material_request`, `create_bulk_ppe_material_request`,
  `create_bulk_ppe_purchase_request` in `api/ppe.py`) — these create Employee
  Data rows with no per-item allocation (`item_code` left blank), because PPE
  issuance already tracks per-employee items a different way (`Employee PPE
  Assignment` records). This feature is explicitly designed so blank
  `item_code` rows keep behaving exactly as they do today — see Design
  section 4.
- Retroactively fixing `MAT-MR-2026-00016` itself — that's a one-off manual
  data fix, handled separately from shipping this feature, not part of this
  spec.
- Any UI/client-script convenience for filling in `item_code`/`qty` (e.g. an
  "auto-suggest from Items table" helper) — out of scope; the fields are
  plain, freely-editable Link/Float fields.

## Design

### 1. New fields on `Employee Request`

| Field | Type | Notes |
|---|---|---|
| `item_code` | Link → Item | Optional. Which item this specific employee needs. |
| `qty` | Float | Optional. How much this employee needs of that item. Required once `item_code` is set (see validation below). |
| `qty_issued` | Float, read-only, default 0 | Running total actually issued to this employee against this specific allocation so far. |

`item_code`/`qty` being unset (both blank) is the explicit "no per-item
allocation — old behavior" case (Design section 4). If `item_code` is set,
`qty` must be too (and must be positive).

`mandatory_depends_on` is client-side JS only and is never enforced
server-side (confirmed against `frappe/model/base_document.py`'s
`_get_missing_mandatory_fields` during this app's earlier PPE work — the
same reason `validate_employee_data_required_for_material_issue` exists
today as an explicit `validate()` check rather than a field property). So
"`qty` required once `item_code` is set" is enforced the same way: a check
added to `validate_no_duplicate_employees`'s existing loop over
`doc.custom_employee_data` (Design section 2) that throws if a row has
`item_code` set but `qty` is blank or `<= 0`.

### 2. Duplicate-check and qty-required update

`validate_no_duplicate_employees` (existing, in `overrides/material_request.py`)
changes its uniqueness key from `employee` alone to `(employee, item_code)` —
the same employee may now legitimately appear on multiple rows (one per item
they need), but the exact same `(employee, item_code)` pair may not repeat.
Two blank-`item_code` rows for the same employee are still a duplicate under
the original rule (this is the PPE workflow's own shape — one row per
employee, no item — so the original single-employee-per-request constraint
must still hold when `item_code` is blank).

The same loop over `doc.custom_employee_data` also throws if a row has
`item_code` set but `qty` is blank or `<= 0` — see the server-side
validation note in section 1.

### 3. Items table becomes derived from per-employee allocations

New function in `overrides/material_request.py`, added to the existing
`validate` hook list (after `sync_accounting_dimensions_to_items`, itself
after the employee-mandatory/duplicate checks):

```python
def sync_employee_allocations_to_items(doc, method=None):
    """Material Request validate: for a Material Issue request where at
    least one Employee Data row states an item_code/qty, the standard Items
    table (required by ERPNext's stock engine regardless) is fully derived
    from the sum of those per-employee allocations, grouped by item_code --
    not filled in separately and kept in sync by hand.

    If no Employee Data row has item_code set (e.g. the PPE workflow's own
    MR-creation code, which tracks per-employee items a different way), this
    is a no-op -- Items stays exactly as the caller built it. This is the
    load-bearing backward-compatibility guarantee for the PPE workflow."""
    allocations = [row for row in doc.custom_employee_data if row.item_code and row.qty]
    if not allocations:
        return

    merged = {}
    for row in allocations:
        merged[row.item_code] = merged.get(row.item_code, 0) + row.qty

    doc.items = []
    for item_code, qty in merged.items():
        doc.append("items", {
            "item_code": item_code,
            "qty": qty,
            "schedule_date": doc.schedule_date or frappe.utils.today(),
        })
```

A Material Request where *some* Employee Data rows have `item_code` set and
others don't: only the rows with `item_code` contribute to the derived Items
table; blank rows are simply skipped (not an error) — this doesn't arise in
either of this app's real flows (a request is either fully per-employee-item
or fully PPE-style, never mixed) but is defined behavior rather than an
unhandled edge case.

### 4. `lock_issued_employee` / `unlock_issued_employee` — qty-aware locking

Both functions live in `overrides/stock_entry.py`, hooked on Stock Entry
`on_submit`/`on_cancel` respectively (existing hooks, unchanged wiring).

**Matching an employee's specific allocation row:** a Stock Entry has one
`bio_employee` but potentially several item rows (`doc.items`). For each
Stock Entry item row, the matching Employee Request row is found by
`(parent=material_request, employee=doc.bio_employee, item_code=row.item_code)`.
If no such row exists (e.g. this item isn't one of this employee's
allocations — shouldn't happen in practice since Items is derived from
allocations, but not assumed), fall back to matching by
`(parent=material_request, employee=doc.bio_employee, item_code="")` — the
blank-`item_code` case, preserving the PPE workflow's exact original
behavior (one row per employee, no item-specificity, locks immediately on
any submission regardless of which item was issued).

**On submit (`lock_issued_employee`), per Stock Entry item row:**
- If the matched Employee Request row has `item_code` set (the new,
  fine-grained case):
  - If `qty_issued` is already `>= qty` (fully satisfied before this Stock
    Entry), throw — this allocation was already completed, same spirit as
    today's "already issued" guard, just qty-aware instead of
    submission-count-aware.
  - Otherwise, increment `qty_issued` by this row's issued quantity. If the
    new `qty_issued >= qty`, set `issued_via_stock_entry` to this Stock
    Entry's name (now genuinely "done"). If not, leave
    `issued_via_stock_entry` blank — the employee stays selectable for a
    follow-up issuance. This does not cap how much a single Stock Entry may
    issue against an allocation — if one Stock Entry issues more than what
    remains (`qty - qty_issued`), `qty_issued` simply ends up above `qty`
    and the row locks as satisfied; validating that a single issuance
    doesn't overshoot the remaining quantity is out of scope for this
    feature.
- If the matched row has `item_code` blank (old case): unchanged from
  today — throw if `issued_via_stock_entry` is already set to a different
  Stock Entry, otherwise set it to this Stock Entry's name.

**On cancel (`unlock_issued_employee`), per Stock Entry item row:**
- If the matched Employee Request row has `item_code` set: decrement
  `qty_issued` by this row's quantity (never below 0). If `qty_issued` is now
  `< qty`, clear `issued_via_stock_entry` (reopen) — regardless of whether
  *this* Stock Entry was the one recorded there, since any contributing
  entry being cancelled can drop the total below the threshold. If
  `qty_issued` is still `>= qty` after decrementing (multiple Stock Entries
  contributed, this wasn't the last one needed), leave `issued_via_stock_entry`
  as-is.
- If the matched row has `item_code` blank: unchanged from today — clear
  `issued_via_stock_entry` only if it currently equals this Stock Entry's
  name.

This is a genuine behavior change to two already-shipped, already-tested
functions from an earlier plan — the blank-`item_code` branch is written to
be byte-for-byte equivalent to their current behavior, so the PPE workflow
and the original employee-issuance-lock feature both continue to work
unmodified in every scenario where no per-item allocation is used.
