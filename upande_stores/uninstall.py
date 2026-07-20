"""Uninstall-time cleanup for upande_stores-owned doctype customizations.

Installing this app (or running `bench migrate` while it's installed) adds
its Custom Fields/Property Setters via the custom/*.json Customize-Form-
export sync, which is an upsert-only mechanism -- it never removes anything.
So the reverse direction (uninstalling the app removes what it added) has to
be done explicitly here, keyed on the "Upande Stores" module tag every
customization in this app's custom/*.json files carries.
"""

import frappe


def before_uninstall():
	for name in frappe.get_all("Custom Field", filters={"module": "Upande Stores"}, pluck="name"):
		frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)

	for name in frappe.get_all("Property Setter", filters={"module": "Upande Stores"}, pluck="name"):
		frappe.delete_doc("Property Setter", name, ignore_permissions=True, force=True)

	frappe.db.commit()
