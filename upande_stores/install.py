from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def after_install():
	setup_custom_fields()


def after_migrate():
	setup_custom_fields()


def setup_custom_fields():
	custom_fields = get_custom_fields()
	for fields in custom_fields.values():
		for df in fields:
			df.setdefault("module", "Upande Stores")

	create_custom_fields(custom_fields, update=True)


def get_custom_fields():
	return {
		"Stock Entry Type": [
			{
				"fieldname": "requires_biometric_verification",
				"fieldtype": "Check",
				"label": "Requires Biometric Verification",
				"insert_after": "is_standard",
			},
			{
				"fieldname": "disabled",
				"fieldtype": "Check",
				"label": "Disabled",
				"insert_after": "requires_biometric_verification",
			},
		],
		"Stock Entry": [
			# Own section, placed just above the Items section (items_section).
			# Only shown when the selected Stock Entry Type requires biometrics.
			{
				"fieldname": "biometric_verification_section",
				"fieldtype": "Section Break",
				"label": "Biometric Verification",
				"insert_after": "last_scanned_warehouse",
				"depends_on": "eval:doc.requires_biometric",
				"collapsible": 0,
				"collapsible_depends_on": "",
			},
			{
				"fieldname": "requires_biometric",
				"fieldtype": "Check",
				"label": "Requires Biometric",
				"insert_after": "biometric_verification_section",
				"fetch_from": "stock_entry_type.requires_biometric_verification",
				"read_only": 1,
			},
			{
				"fieldname": "bio_employee",
				"fieldtype": "Link",
				"label": "Employee (Receiving)",
				"options": "Employee",
				"insert_after": "requires_biometric",
				"depends_on": "requires_biometric",
				"mandatory_depends_on": "requires_biometric",
			},
			{
				"fieldname": "bio_employee_name",
				"fieldtype": "Data",
				"label": "Employee Name",
				"fetch_from": "bio_employee.employee_name",
				"insert_after": "bio_employee",
				"depends_on": "requires_biometric",
				"read_only": 1,
			},
			{
				"fieldname": "biometric_column_break",
				"fieldtype": "Column Break",
				"insert_after": "bio_employee_name",
			},
			{
				"fieldname": "biometric_status",
				"fieldtype": "Select",
				"label": "Biometric Status",
				"options": "Pending\nVerified\nFailed",
				"default": "Pending",
				"insert_after": "biometric_column_break",
				"depends_on": "requires_biometric",
				"read_only": 1,
				"no_copy": 1,
				"in_standard_filter": 1,
			},
			{
				"fieldname": "biometric_verified_at",
				"fieldtype": "Datetime",
				"label": "Biometric Verified At",
				"insert_after": "biometric_status",
				"depends_on": "requires_biometric",
				"read_only": 1,
				"no_copy": 1,
			},
			{
				# Data, not Link: Biometric Logs lives in upande_ta, which may not be installed
				"fieldname": "matched_biometric_log",
				"fieldtype": "Data",
				"label": "Matched Biometric Log",
				"insert_after": "biometric_verified_at",
				"depends_on": "requires_biometric",
				"read_only": 1,
				"no_copy": 1,
			},
		],
		# Same fieldname on both item tables so ERPNext's Material Request -> Stock Entry
		# mapper copies the employee across automatically.
		"Material Request Item": [
			{
				"fieldname": "employee",
				"fieldtype": "Link",
				"label": "Employee",
				"options": "Employee",
				"insert_after": "item_name",
				"in_list_view": 1,
			},
			{
				"fieldname": "employee_name",
				"fieldtype": "Data",
				"label": "Employee Name",
				"fetch_from": "employee.employee_name",
				"insert_after": "employee",
				"read_only": 1,
			},
		],
		"Stock Entry Detail": [
			{
				"fieldname": "employee",
				"fieldtype": "Link",
				"label": "Employee",
				"options": "Employee",
				"insert_after": "item_name",
				"in_list_view": 1,
				# Lines pulled from a Material Request keep the requested employee
				"read_only_depends_on": "eval:doc.material_request_item",
			},
			{
				"fieldname": "employee_name",
				"fieldtype": "Data",
				"label": "Employee Name",
				"fetch_from": "employee.employee_name",
				"insert_after": "employee",
				"read_only": 1,
			},
		],
		"Stock Settings": [
			{
				"fieldname": "employee_issuance_tab",
				"fieldtype": "Tab Break",
				"label": "Employee Issuance",
				"insert_after": "stock_auth_role",
			},
			{
				"fieldname": "employee_material_request_section",
				"fieldtype": "Section Break",
				"label": "Material Request",
				"insert_after": "employee_issuance_tab",
			},
			{
				"fieldname": "employee_mandatory_in_material_request",
				"fieldtype": "Check",
				"label": "Employee Mandatory on Material Request Items",
				"insert_after": "employee_material_request_section",
			},
			{
				"fieldname": "employee_mandatory_purposes",
				"fieldtype": "Small Text",
				"label": "Purposes Requiring Employee",
				"description": "Comma-separated Material Request purposes, e.g. Material Issue, Material Transfer. "
				"Leave blank to make the employee mandatory for every purpose.",
				"insert_after": "employee_mandatory_in_material_request",
				"depends_on": "employee_mandatory_in_material_request",
			},
			{
				"fieldname": "employee_stock_entry_section",
				"fieldtype": "Section Break",
				"label": "Stock Entry",
				"insert_after": "employee_mandatory_purposes",
			},
			{
				"fieldname": "allow_collection_on_behalf",
				"fieldtype": "Check",
				"label": "Allow Collecting Items on Behalf of Another Employee",
				"description": "If unchecked, a Stock Entry that requires biometric verification can only "
				"issue lines requested for the employee who signs for it.",
				"insert_after": "employee_stock_entry_section",
			},
		],
	}
