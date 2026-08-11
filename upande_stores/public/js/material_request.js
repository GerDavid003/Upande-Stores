// Keeps every Material Request Item row's Farm/Business Unit in sync with
// the header's custom_farm/custom_business_unit as the user picks them --
// live in the browser, before saving. The equivalent server-side push
// (upande_stores.overrides.material_request.sync_accounting_dimensions_to_items)
// still runs on every save regardless, so this is purely an optimistic,
// same-behavior mirror for immediate visual feedback.

frappe.ui.form.on("Material Request", {
	custom_farm(frm) {
		sync_accounting_dimensions_to_items(frm);
	},
	custom_business_unit(frm) {
		sync_accounting_dimensions_to_items(frm);
	},
});

frappe.ui.form.on("Material Request Item", {
	items_add(frm) {
		sync_accounting_dimensions_to_items(frm);
	},
});

function sync_accounting_dimensions_to_items(frm) {
	(frm.doc.items || []).forEach((row) => {
		if (frm.doc.custom_farm) {
			row.farm = frm.doc.custom_farm;
		}
		if (frm.doc.custom_business_unit) {
			row.business_unit = frm.doc.custom_business_unit;
		}
	});
	frm.refresh_field("items");
}
