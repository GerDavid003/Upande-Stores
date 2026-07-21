frappe.ui.form.on("Employee PPE Assignment", {
	refresh(frm) {
		if (
			frm.doc.replacement_requested &&
			frm.doc.replacement_material_request &&
			!frm.doc.replacement_purchase_request
		) {
			frm.add_custom_button(
				__("Raise Purchase Request"),
				() => {
					frappe.confirm(
						__("Create a Purchase Material Request for {0}?", [frm.doc.item_name || frm.doc.item_code]),
						() => {
							frappe.call({
								method: "upande_stores.api.ppe.create_bulk_ppe_purchase_request",
								args: { assignments: JSON.stringify([frm.doc.name]) },
								callback: (r) => {
									if (r.message) {
										frappe.show_alert({
											message: __("Purchase Request {0} created", [r.message]),
											indicator: "green",
										});
										frm.reload_doc();
									}
								},
							});
						}
					);
				},
				__("Create")
			);
		}
	},
});
