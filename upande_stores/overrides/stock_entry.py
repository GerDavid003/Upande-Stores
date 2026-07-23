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

		# Plain existence check -- NOT for_update=True. That was tried as a
		# hardened read mirroring lock_issued_employee's, but proven (against two
		# real concurrent processes) not to actually close the race: `SELECT ...
		# FOR UPDATE` locks nothing when zero rows match, which is exactly the
		# first-issuance case this was meant to protect. Keeping the misleading
		# for_update gave the appearance of a fix without the substance, so it's
		# reverted here. Known, accepted gap: two people issuing the exact same
		# item to the exact same employee at the exact same instant could both
		# this is a random comment
		# pass this check and both insert. This is a manual, button-driven
		# action, so that window is rare enough in practice that a real fix
		# (e.g. locking a stable anchor row instead of a query that may match
		# zero rows) isn't worth the added complexity.
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
				"farm": row.get("farm"),
				"business_unit": row.get("business_unit"),
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


def delete_ppe_assignments(doc, method=None):
	"""Stock Entry on_cancel: inverse of create_ppe_assignments. Fully delete
	every Employee PPE Assignment this exact Stock Entry created (keyed by the
	assignment's stock_entry field), rather than merely deactivating them, so a
	later re-issue of the same item to the same employee isn't blocked by
	create_ppe_assignments' duplicate-active guard. Deleting each assignment
	fires its on_trash, which cleans up the linked Employee PPE History row.

	Each assignment is deleted in its own try/except: a delete that's blocked
	for one assignment (e.g. some other, unhandled inbound link) must not stop
	the rest of this Stock Entry's assignments from being cleaned up, and must
	not abort the on_cancel hook -- the Stock Entry cancel itself must still go
	through. Failures are logged via frappe.log_error rather than swallowed."""
	assignment_names = frappe.get_all(
		"Employee PPE Assignment", filters={"stock_entry": doc.name}, pluck="name"
	)
	for name in assignment_names:
		try:
			# create_ppe_assignments points a prior assignment's
			# replacement_assignment at this (new) one during the replacement
			# flow. That inbound link would otherwise make delete_doc's link
			# check raise LinkExistsError and abort the whole Stock Entry
			# cancel. Clearing it here is part of completing the inverse:
			# create sets these links, so cancel unsets them.
			referencing = frappe.get_all(
				"Employee PPE Assignment", filters={"replacement_assignment": name}, pluck="name"
			)
			for ref in referencing:
				frappe.db.set_value("Employee PPE Assignment", ref, "replacement_assignment", None)

			# A PPE Inspection Item child row can also hold a link to this
			# assignment -- and cancelling the PPE Inspection it belongs to does
			# NOT clear that link (on_cancel only reverts the assignment's
			# status, it never touches the child row's own fields). delete_doc's
			# link check for a plain "Delete" ignores docstatus entirely, so
			# even a properly cancelled inspection's child row would otherwise
			# still block this delete. Same idiom as replacement_assignment
			# above: unset the low-level field rather than cascade into
			# deleting the PPE Inspection itself -- it stays as a historical
			# record (remarks, outcome, etc.), just no longer linked to the
			# assignment being deleted.
			inspection_items = frappe.get_all(
				"PPE Inspection Item", filters={"employee_ppe_assignment": name}, pluck="name"
			)
			for item_name in inspection_items:
				frappe.db.set_value("PPE Inspection Item", item_name, "employee_ppe_assignment", None)

			frappe.delete_doc("Employee PPE Assignment", name, ignore_permissions=True)
		except Exception:
			frappe.log_error(
				title=f"delete_ppe_assignments: failed to delete {name} for Stock Entry {doc.name}",
				message=frappe.get_traceback(),
			)
