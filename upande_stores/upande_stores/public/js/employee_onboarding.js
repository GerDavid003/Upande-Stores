frappe.ui.form.on("Employee Onboarding", {
	refresh(frm) {
		frm.add_custom_button(
			__("Fetch PPE Requirements"),
			() => {
				if (!frm.doc.employee) {
					frappe.msgprint(__("Please select an Employee first."));
					return;
				}
				frappe.call({
					method: "upande_stores.api.ppe.get_ppe_requirements_for_onboarding",
					args: { employee: frm.doc.employee },
					callback: (r) => {
						if (!r.message || !r.message.length) {
							frappe.msgprint(
								__("No active PPE Policies found for this employee's company/department/designation.")
							);
							return;
						}
						frm.clear_table("custom_ppe_requirements");
						r.message.forEach((item) => {
							const row = frm.add_child("custom_ppe_requirements");
							row.item_code = item.item_code;
							row.item_name = item.item_name;
							row.quantity = item.quantity;
							row.issued = 0;
						});
						frm.refresh_field("custom_ppe_requirements");
						frappe.show_alert({
							message: __("{0} PPE item(s) fetched.", [r.message.length]),
							indicator: "green",
						});
					},
				});
			},
			__("PPE")
		);

		if (
			!frm.is_new() &&
			frm.doc.custom_ppe_requirements &&
			frm.doc.custom_ppe_requirements.length > 0 &&
			!frm.doc.custom_ppe_material_request
		) {
			frm.add_custom_button(
				__("Create PPE Issuance Request"),
				() => {
					frappe.confirm(
						__("Create a PPE Material Issue Request for {0}?", [
							frm.doc.employee_name || frm.doc.employee,
						]),
						() => {
							frappe.call({
								method: "upande_stores.api.ppe.create_ppe_onboarding_material_request",
								args: {
									onboarding: frm.doc.name,
									employee: frm.doc.employee,
									items: JSON.stringify(
										frm.doc.custom_ppe_requirements
											.filter((r) => r.item_code && r.quantity > 0)
											.map((r) => ({ item_code: r.item_code, quantity: r.quantity }))
									),
								},
								callback: (r) => {
									if (r.message) {
										frappe.show_alert({
											message: __("Material Request {0} created", [r.message]),
											indicator: "green",
										});
										frm.reload_doc();
									}
								},
							});
						}
					);
				},
				__("PPE")
			);
		}
	},
});
