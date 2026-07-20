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
	},
});
