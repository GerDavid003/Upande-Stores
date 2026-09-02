import frappe


def execute():
	"""Clean up the ``description`` field's old "Purpose"/mandatory
	Property Setters on Material Request Item. These were replaced by the
	dedicated ``custom_purpose`` Custom Field and removed from
	upande_stores/custom/material_request_item.json, but fixture sync only
	inserts/updates Property Setters -- it never deletes ones removed from
	the file -- so sites that had them installed keep enforcing the old
	label/mandatory override even after the fixture no longer defines it.

	Each deletion independently checks existence first, so this is safe to
	run repeatedly and safe to run on a site where the cleanup was already
	done by hand, or never needed at all.
	"""
	for property_setter in (
		"Material Request Item-description-label",
		"Material Request Item-description-reqd",
	):
		if frappe.db.exists("Property Setter", property_setter):
			frappe.delete_doc("Property Setter", property_setter, ignore_permissions=True, force=True)
