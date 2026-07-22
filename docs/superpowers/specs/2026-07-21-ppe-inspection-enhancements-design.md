# PPE Inspection enhancements — mandatory attachment, wider filter, auto-fetch

**Date:** 2026-07-21
**Apps touched:** `upande_stores` only

## Problem

Three gaps in the `PPE Inspection` doctype (built in the 2026-07-20 PPE Workflow plan):

1. Nothing requires photo evidence when an inspector flags an item `Worn Out` — the
   claim is text-only (`current_status` + free-text `comments`).
2. The `employee_ppe_assignment` link query in `items_inspected` (both the manual
   add-row dropdown and, per this change, the new auto-fetch below) only offers
   `Active` assignments. An `Expired` assignment (e.g. past its lifespan but not
   yet inspected/replaced) can't be picked for inspection at all.
3. Building the inspected-items table is entirely manual: the inspector must
   look up each assignment for the selected employee and add rows one at a time.

## Goal

1. Block submitting a `PPE Inspection` if any row is `Worn Out` and no file has
   been attached to the document.
2. Broaden the assignment filter (manual add-row and auto-fetch) to
   `status in (Active, Expired)`.
3. When an employee is selected, auto-populate `items_inspected` with that
   employee's matching assignments instead of requiring manual add-row.

## Out of scope

- No new Attach-type field anywhere. "The attachment" means Frappe's built-in
  generic per-document attachment mechanism (the "Attach File" control every
  document gets) — checked via the `File` doctype's
  `attached_to_doctype`/`attached_to_name`, not a dedicated schema field.
- No new whitelisted API endpoint. The auto-fetch is a plain permission-respecting
  list query (`frappe.db.get_list`) run client-side; nothing here needs
  server-side business logic beyond what already exists.
- `Lost` items are not required to have an attachment — only `Worn Out`. (Lost
  items have nothing to photograph.)
- The attachment check does not depend on a row's `update_assignment` checkbox —
  it fires for every `Worn Out` row regardless of whether that row's assignment
  will actually be deactivated.

## Design

### 1. Mandatory attachment on Worn Out

`upande_stores/upande_stores/doctype/ppe_inspection/ppe_inspection.py` gains a
`before_submit(self)` method:

```python
def before_submit(self):
    has_worn_out = any(row.current_status == "Worn Out" for row in self.items_inspected)
    if not has_worn_out:
        return
    attached = frappe.get_all(
        "File",
        filters={"attached_to_doctype": "PPE Inspection", "attached_to_name": self.name},
        limit=1,
    )
    if not attached:
        frappe.throw(_("Attach photo evidence before submitting — at least one item is marked Worn Out."))
```

Runs only on submit (not on every save), so a draft can be saved without the
attachment and it can be added before submitting.

### 2. Broaden the assignment filter to Active + Expired

`upande_stores/upande_stores/doctype/ppe_inspection/ppe_inspection.js`'s
`set_query` filter changes from `status: "Active"` to
`status: ["in", ["Active", "Expired"]]`. This is the one filter both the manual
add-row dropdown and the auto-fetch (below) use, so they stay consistent by
construction — no filter duplicated in two places.

### 3. Auto-fetch on employee selection

The existing `employee(frm)` handler (currently: clear table + warn) becomes:
clear table, then fetch and populate:

```js
employee(frm) {
    frm.clear_table("items_inspected");
    frm.refresh_field("items_inspected");
    if (!frm.doc.employee) return;

    frappe.db.get_list("Employee PPE Assignment", {
        filters: { employee: frm.doc.employee, status: ["in", ["Active", "Expired"]] },
        fields: ["name", "item_code", "item_name"],
        limit: 0,
    }).then((rows) => {
        rows.forEach((r) => {
            const row = frm.add_child("items_inspected");
            row.employee_ppe_assignment = r.name;
            row.item_code = r.item_code;
            row.item_name = r.item_name;
        });
        frm.refresh_field("items_inspected");
        if (rows.length) {
            frappe.show_alert({ message: __("{0} assignment(s) fetched.", [rows.length]), indicator: "green" });
        }
    });
},
```

`issue_date` is already `fetch_from: employee_ppe_assignment.issue_date` in the
child doctype's schema, so it populates on its own once `employee_ppe_assignment`
is set — no need to fetch/set it here. `current_status` is left blank for the
inspector to fill in per row (it's `reqd: 1`, so an empty value blocks submit
until they do, same as today).

No permission check needed beyond what already exists: `frappe.db.get_list`
enforces the calling user's own read permission on `Employee PPE Assignment`
(System Manager / HR Manager / Farm Manager, per that doctype's existing DocPerm)
the same way the server would.
