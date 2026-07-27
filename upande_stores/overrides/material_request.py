import frappe
from frappe import _


def validate_employee_data_required_for_material_issue(doc, method=None):
	"""Material Request validate hook: a Material Issue request must have at
	least one row in custom_employee_data.

	custom_employee_data's mandatory_depends_on (see custom/material_request.json)
	only drives the Desk form's client-side "reqd" behaviour -- Frappe does not
	re-evaluate mandatory_depends_on server-side when a document is inserted
	via the API (frappe.model.base_document.BaseDocument._get_missing_mandatory_fields
	only looks at the field's static reqd flag), so a Material Issue with zero
	employee rows can still be inserted with doc.insert(ignore_permissions=True)
	unless this hook blocks it explicitly.
	"""
	if doc.material_request_type == "Material Issue" and not doc.get("custom_employee_data"):
		frappe.throw(_("At least one row is required in Employee Data for a Material Issue request."))


def validate_employee_allocations(doc, method=None):
	"""Material Request validate hook: for each row in custom_employee_data,
	(a) the same (employee, item_code) pair may not repeat, and (b) qty is
	required and must be positive whenever item_code is set. Runs on every
	save (not just once), so a violation can't be introduced after the
	fact -- (a) protects the Stock Entry lock/unlock logic
	(lock_issued_employee/unlock_issued_employee), which would otherwise
	have an ambiguous row to match against.

	Blank-item_code rows (the PPE workflow's own shape: one row per
	employee, no per-item allocation) keep the original
	single-employee-per-request constraint -- two blank-item_code rows for
	the same employee still collide, since both match the key
	(employee, "").

	qty's requirement can't be expressed as a plain JSON `reqd` (it's
	conditional on item_code) and `mandatory_depends_on` is never enforced
	server-side (see Global Constraints) -- so it's checked here instead.
	"""
	seen = set()
	for row in doc.get("custom_employee_data") or []:
		if not row.employee:
			continue
		if row.item_code and not (row.qty and row.qty > 0):
			frappe.throw(
				_("Row for Employee {0}: Qty is required and must be greater than 0 when Item is set.").format(
					frappe.bold(row.employee)
				)
			)
		key = (row.employee, row.item_code or "")
		if key in seen:
			if row.item_code:
				frappe.throw(
					_("Employee {0} appears more than once for Item {1} in Employee Data.").format(
						frappe.bold(row.employee), frappe.bold(row.item_code)
					)
				)
			frappe.throw(
				_("Employee {0} appears more than once in Employee Data.").format(
					frappe.bold(row.employee)
				)
			)
		seen.add(key)


def sync_employee_allocations_to_items(doc, method=None):
	"""Material Request validate: when at least one Employee Data row states
	an item_code/qty, the standard Items table (required by ERPNext's stock
	engine regardless of this feature) is fully derived from the sum of
	those per-employee allocations, grouped by item_code -- instead of being
	filled in separately by hand and kept in sync with Employee Data.

	No-ops when no Employee Data row has item_code set (e.g. the PPE
	workflow's own MR-creation code, which tracks per-employee items a
	different way via Employee PPE Assignment) -- Items stays exactly as the
	caller built it. This is the backward-compatibility guarantee for the
	PPE workflow.

	Must run before sync_accounting_dimensions_to_items in hooks.py's
	validate list -- that function pushes custom_farm/custom_business_unit
	onto every row in doc.items, and if this function rebuilt doc.items
	afterward, those values would be lost on the freshly created rows.

	This hook runs after ERPNext's own controller validate() has already
	populated defaults (uom, stock_uom, conversion_factor, description) on
	whatever rows existed when THIS SAVE started -- so any row this function
	creates from scratch has to set those itself; nothing downstream will
	fill them in.
	"""
	allocations = [row for row in doc.get("custom_employee_data") or [] if row.item_code and row.qty]
	if not allocations:
		return

	existing_warehouse_by_item = {
		row.item_code: row.warehouse for row in doc.items if row.item_code and row.warehouse
	}

	merged = {}
	for row in allocations:
		merged[row.item_code] = merged.get(row.item_code, 0) + row.qty

	doc.items = []
	for item_code, qty in merged.items():
		stock_uom, description = frappe.db.get_value("Item", item_code, ["stock_uom", "description"])
		doc.append(
			"items",
			{
				"item_code": item_code,
				"qty": qty,
				"uom": stock_uom,
				"stock_uom": stock_uom,
				"conversion_factor": 1,
				"description": description or item_code,
				"schedule_date": doc.schedule_date or frappe.utils.today(),
				"warehouse": existing_warehouse_by_item.get(item_code),
			},
		)

	# Freshly created rows skipped ERPNext's own defaulting pass (that already
	# ran, on the OLD items, before this hook fired) -- re-run it now so any
	# site-level mandatory Material Request Item field this function doesn't
	# know how to compute itself (e.g. expense_account) gets resolved the same
	# way it would for a manually-entered row. Fills any field that's still
	# blank (leaving qty/description/uom/conversion_factor/warehouse alone,
	# since we already set those above) except its own hardcoded
	# force_item_fields list -- stock_uom is the only one of those we also
	# set, and it's harmless here since both resolve to the same Item master
	# value.
	doc.set_missing_values(for_validate=True)


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
