import frappe


def execute():
	"""Clean up leftovers from the retired ``Employee Request`` child-table
	doctype (per-employee allocation moved onto ``Material Request Item``
	directly). Fixture sync only inserts/updates Custom Fields -- it never
	deletes ones removed from the fixture file -- so the two Custom Fields
	that used to expose the ``Employee Request`` child table on Material
	Request are orphaned once the doctype itself is gone:
	`Material Request-custom_employee_data` (fieldtype Table, options
	"Employee Request") would otherwise make the Material Request Desk form
	fail to load entirely (`get_meta("Employee Request")` ->
	`DoesNotExistError`).

	Each step independently checks existence first, so this is safe to run
	repeatedly and safe to run on a site where some/all of this cleanup was
	already done by hand, or never needed at all.
	"""
	for custom_field in (
		"Material Request-custom_employee_data",
		"Material Request-custom_employee_details",
	):
		if frappe.db.exists("Custom Field", custom_field):
			frappe.delete_doc("Custom Field", custom_field, ignore_permissions=True, force=True)

	if frappe.db.table_exists("Employee Request"):
		frappe.db.sql("DROP TABLE IF EXISTS `tabEmployee Request`")
