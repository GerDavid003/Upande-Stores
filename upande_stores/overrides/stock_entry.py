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


def create_ppe_assignments(doc, method=None):
	"""Stock Entry on_submit: for every custom_is_ppe item issued to
	doc.bio_employee, create an Employee PPE Assignment. No-ops for anything
	that isn't a Material Issue against a bio_employee -- mirrors
	lock_issued_employee's own scoping."""
	if doc.stock_entry_type != "Material Issue" or not doc.get("bio_employee"):
		return

	employee = doc.bio_employee
	employee_name = frappe.db.get_value("Employee", employee, "employee_name")

	material_request = _resolve_material_request(doc)
	is_ppe_issuance = bool(
		material_request
		and frappe.db.get_value("Material Request", material_request, "custom_ppe_issuance")
	)

	for row in doc.items:
		if not row.item_code or not row.qty or row.qty <= 0:
			continue

		is_ppe, lifespan = frappe.db.get_value(
			"Item", row.item_code, ["custom_is_ppe", "custom_ppe_lifespan"]
		)
		if not is_ppe:
			continue
		if not lifespan or lifespan <= 0:
			frappe.throw(_("PPE Lifespan (Months) not set for item {0}").format(row.item_code))

		if frappe.db.exists(
			"Employee PPE Assignment",
			{"employee": employee, "item_code": row.item_code, "status": "Active"},
		):
			frappe.throw(
				_("{0} is already actively assigned to {1}").format(row.item_code, employee_name)
			)

		new_assignment = frappe.get_doc(
			{
				"doctype": "Employee PPE Assignment",
				"employee": employee,
				"employee_name": employee_name,
				"item_code": row.item_code,
				"quantity": row.qty,
				"issue_date": doc.posting_date,
				"lifespan_months": lifespan,
				"stock_entry": doc.name,
				"company": doc.company,
				"farm": doc.get("custom_farm"),
				"business_unit": doc.get("custom_business_unit"),
				"status": "Active",
			}
		).insert(ignore_permissions=True)

		if is_ppe_issuance:
			old_assignments = frappe.get_all(
				"Employee PPE Assignment",
				filters={
					"replacement_material_request": material_request,
					"employee": employee,
					"item_code": row.item_code,
					"name": ["!=", new_assignment.name],
				},
				pluck="name",
			)
			for old_name in old_assignments:
				frappe.db.set_value(
					"Employee PPE Assignment", old_name, "replacement_assignment", new_assignment.name
				)
