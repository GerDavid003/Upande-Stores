frappe.ui.form.on("PPE Inspection", {
	setup(frm) {
		frm.set_query("employee_ppe_assignment", "items_inspected", (doc) => {
			if (!doc.employee) {
				frappe.msgprint(__("Please select Employee first."));
				return;
			}
			return {
				filters: {
					employee: doc.employee,
					status: "Active",
				},
			};
		});
	},

	employee(frm) {
		if (frm.doc.items_inspected && frm.doc.items_inspected.length) {
			frm.clear_table("items_inspected");
			frm.refresh_field("items_inspected");
			frappe.msgprint(__("Inspection items cleared because Employee was changed."));
		}
	},
});
