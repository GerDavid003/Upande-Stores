import frappe
from frappe import _


def validate_employee_required_for_material_issue(doc, method=None):
	"""Material Request validate hook: when material_request_type is
	"Material Issue", every item row must have employee set -- a Material
	Issue request is always issuing specific items to specific people, so a
	row with a blank employee on that request type is a data-entry mistake,
	not a valid case. Other request types (Material Transfer, Purchase,
	...) leave employee fully optional.

	Enforced here rather than via reqd/mandatory_depends_on -- the latter
	is never enforced server-side in this Frappe version
	(frappe.model.base_document.BaseDocument._get_missing_mandatory_fields
	only ever checks the static reqd flag).
	"""
	if doc.material_request_type != "Material Issue":
		return
	for row in doc.items:
		if not row.employee:
			frappe.throw(_("Row {0}: Employee is required for a Material Issue request.").format(row.idx))


def validate_employee_allocations(doc, method=None):
	"""Material Request validate hook: no two item rows may share the same
	(employee, item_code) pair when employee is set on both. Runs on every
	save (not just once), so a duplicate can't be introduced after the fact
	-- protects the Stock Entry lock/unlock logic
	(lock_issued_employee/unlock_issued_employee), which would otherwise
	have an ambiguous row to match against.

	Rows with a blank employee are unconstrained against each other --
	ordinary bulk items (no per-employee attribution) can repeat item_code
	freely.
	"""
	seen = set()
	for row in doc.items:
		if not row.employee:
			continue
		key = (row.employee, row.item_code)
		if key in seen:
			frappe.throw(
				_("Employee {0} appears more than once for Item {1}.").format(
					frappe.bold(row.employee), frappe.bold(row.item_code)
				)
			)
		seen.add(key)


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
