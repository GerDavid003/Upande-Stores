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
					status: ["in", ["Active", "Expired"]],
				},
			};
		});
	},

	employee(frm) {
		frm.clear_table("items_inspected");
		frm.refresh_field("items_inspected");

		if (!frm.doc.employee) {
			return;
		}

		frappe.db
			.get_list("Employee PPE Assignment", {
				filters: { employee: frm.doc.employee, status: ["in", ["Active", "Expired"]] },
				fields: ["name", "item_code", "item_name", "issue_date"],
				limit_page_length: 0,
			})
			.then((rows) => {
				rows.forEach((r) => {
					const row = frm.add_child("items_inspected");
					row.employee_ppe_assignment = r.name;
					row.item_code = r.item_code;
					row.item_name = r.item_name;
					row.issue_date = r.issue_date;
				});
				frm.refresh_field("items_inspected");
				if (rows.length) {
					frappe.show_alert({
						message: __("{0} assignment(s) fetched.", [rows.length]),
						indicator: "green",
					});
				}
			});
	},
});
