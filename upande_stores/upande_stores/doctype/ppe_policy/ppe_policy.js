frappe.ui.form.on("PPE Policy", {
	refresh(frm) {
		if (!frm.doc.department && !frm.doc.designation) {
			frm.set_intro(__("Please set at least one of Department or Designation."), "orange");
		}
	},
});
