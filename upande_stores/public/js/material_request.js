// Employee per Material Request line, mandatory per Stock Settings > Employee Issuance
(() => {
    frappe.ui.form.on('Material Request', {
        onload(frm) {
            frappe.call('upande_stores.employee_issuance.get_employee_issuance_settings').then((r) => {
                frm._employee_issuance = r.message || {};
                toggle_employee_reqd(frm);
            });
        },

        material_request_type(frm) {
            toggle_employee_reqd(frm);
        }
    });

    function toggle_employee_reqd(frm) {
        const settings = frm._employee_issuance;
        if (!settings) return;

        const purposes = settings.mandatory_purposes || [];
        const reqd = settings.employee_mandatory
            && (!purposes.length || purposes.includes(frm.doc.material_request_type));

        frm.fields_dict.items.grid.update_docfield_property('employee', 'reqd', reqd ? 1 : 0);
        frm.refresh_field('items');
    }
})();
