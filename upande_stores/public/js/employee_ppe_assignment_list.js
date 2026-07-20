frappe.listview_settings["Employee PPE Assignment"] = {
	onload(listview) {
		listview.page.add_action_item(__("Create Replacement Material Request"), () => {
			const selected = listview.get_checked_items();
			if (!selected.length) {
				frappe.msgprint(__("Please select at least one record."));
				return;
			}
			frappe.call({
				method: "upande_stores.api.ppe.create_bulk_ppe_material_request",
				args: { assignments: JSON.stringify(selected.map((d) => d.name)) },
				callback: (r) => {
					if (r.message) frappe.set_route("Form", "Material Request", r.message);
				},
			});
		});

		listview.page.add_action_item(__("Create Bulk Purchase Request"), () => {
			const selected = listview.get_checked_items();
			if (!selected.length) {
				frappe.msgprint(__("Please select at least one record."));
				return;
			}
			frappe.call({
				method: "upande_stores.api.ppe.create_bulk_ppe_purchase_request",
				args: { assignments: JSON.stringify(selected.map((d) => d.name)) },
				callback: (r) => {
					if (r.message) frappe.set_route("Form", "Material Request", r.message);
				},
			});
		});
	},
};
