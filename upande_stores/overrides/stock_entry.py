import frappe
from frappe import _


def _resolve_material_request(doc):
	"""The Material Request this Stock Entry was created against, if any --
	the first item row with a non-empty material_request. Confirmed with the
	requester that a Stock Entry in this flow is always created against
	exactly one Material Request via its "Create" button."""
	for row in doc.items:
		if row.material_request:
			return row.material_request
	return None


def lock_issued_employee(doc, method=None):
	"""Stock Entry on_submit: stamp the matching Employee Request row (by
	Material Request + employee) with this Stock Entry's name, so it drops
	out of upande_ta's bio_employee query. Blocks the submit if another
	Stock Entry already claimed this employee for this Material Request
	(covers a stale dropdown / race). No-ops if there's no Material Request
	context, no bio_employee set, or bio_employee isn't one of this
	Material Request's tracked employees at all (bio_employee's general
	biometric-verification use, independent of this feature, is untouched).
	"""
	material_request = _resolve_material_request(doc)
	if not material_request or not doc.get("bio_employee"):
		return

	row_name = frappe.db.get_value(
		"Employee Request",
		{
			"parent": material_request,
			"parenttype": "Material Request",
			"employee": doc.bio_employee,
		},
		"name",
	)
	if not row_name:
		return

	existing = frappe.db.get_value(
		"Employee Request", row_name, "issued_via_stock_entry", for_update=True
	)
	if existing and existing != doc.name:
		frappe.throw(
			_(
				"Employee {0} has already been issued items under Material Request {1} via Stock Entry {2}."
			).format(frappe.bold(doc.bio_employee), frappe.bold(material_request), frappe.bold(existing))
		)

	frappe.db.set_value("Employee Request", row_name, "issued_via_stock_entry", doc.name)


def unlock_issued_employee(doc, method=None):
	"""Stock Entry on_cancel: clear the lock, but only the row this exact
	Stock Entry set -- never a lock belonging to a different entry."""
	material_request = _resolve_material_request(doc)
	if not material_request or not doc.get("bio_employee"):
		return

	row_name = frappe.db.get_value(
		"Employee Request",
		{
			"parent": material_request,
			"parenttype": "Material Request",
			"employee": doc.bio_employee,
			"issued_via_stock_entry": doc.name,
		},
		"name",
	)
	if row_name:
		frappe.db.set_value("Employee Request", row_name, "issued_via_stock_entry", None)
