import frappe
from frappe import _
from frappe.utils import cint


def get_mandatory_purposes():
	value = frappe.db.get_single_value("Stock Settings", "employee_mandatory_purposes") or ""
	return [p.strip() for p in value.split(",") if p.strip()]


def is_employee_mandatory(material_request_type):
	if not cint(frappe.db.get_single_value("Stock Settings", "employee_mandatory_in_material_request")):
		return False

	purposes = get_mandatory_purposes()
	return not purposes or material_request_type in purposes


def is_collection_on_behalf_allowed():
	return bool(cint(frappe.db.get_single_value("Stock Settings", "allow_collection_on_behalf")))


@frappe.whitelist()
def get_employee_issuance_settings():
	return {
		"employee_mandatory": cint(
			frappe.db.get_single_value("Stock Settings", "employee_mandatory_in_material_request")
		),
		"mandatory_purposes": get_mandatory_purposes(),
		"allow_collection_on_behalf": is_collection_on_behalf_allowed(),
	}


# ── doc_events ───────────────────────────────────────────────────────────────


def validate_stock_settings(doc, method=None):
	if not doc.get("employee_mandatory_purposes"):
		return

	valid = (frappe.get_meta("Material Request").get_field("material_request_type").options or "").split("\n")
	purposes = [p.strip() for p in doc.employee_mandatory_purposes.split(",") if p.strip()]
	invalid = [p for p in purposes if p not in valid]
	if invalid:
		frappe.throw(
			_("Invalid purpose(s) in Purposes Requiring Employee: {0}. Valid purposes are: {1}").format(
				", ".join(invalid), ", ".join(v for v in valid if v)
			)
		)

	doc.employee_mandatory_purposes = ", ".join(purposes)


def validate_material_request(doc, method=None):
	if not is_employee_mandatory(doc.material_request_type):
		return

	missing = [str(d.idx) for d in doc.items if not d.get("employee")]
	if missing:
		frappe.throw(
			_("Employee is mandatory for {0} requests. Set it on row(s): {1}").format(
				_(doc.material_request_type), ", ".join(missing)
			),
			title=_("Employee Required"),
		)


def validate_stock_entry(doc, method=None):
	set_employee_from_material_request(doc)

	if not doc.get("requires_biometric") or not doc.get("bio_employee"):
		return

	if is_collection_on_behalf_allowed():
		return

	other_rows = [
		str(d.idx) for d in doc.items if d.get("employee") and d.employee != doc.bio_employee
	]
	if other_rows:
		frappe.throw(
			_(
				"Row(s) {0} were requested for a different employee and cannot be issued to {1}. "
				"Remove them and issue them in a separate Stock Entry."
			).format(", ".join(other_rows), doc.get("bio_employee_name") or doc.bio_employee),
			title=_("Items Belong to Another Employee"),
		)


def set_employee_from_material_request(doc):
	"""The source Material Request line is the authority on whose item it is.

	Covers every path into a Stock Entry (direct, via Pick List, via API), since
	they all keep material_request_item on the line.
	"""
	mr_items = {d.material_request_item for d in doc.items if d.get("material_request_item")}
	if not mr_items:
		return

	employees = {
		d.name: d
		for d in frappe.get_all(
			"Material Request Item",
			filters={"name": ["in", list(mr_items)]},
			fields=["name", "employee", "employee_name"],
		)
	}
	for d in doc.items:
		source = employees.get(d.get("material_request_item"))
		if source:
			d.employee = source.employee
			d.employee_name = source.employee_name
