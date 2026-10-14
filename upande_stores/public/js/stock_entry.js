// Biometric Verification Process for Stock Entry
// Wrapped in an IIFE so helpers don't leak into the global scope.
(() => {
    const VERIFY_WINDOW_MINUTES = 1;

    frappe.ui.form.on('Stock Entry', {

        refresh(frm) {
            if (!frm.is_new() && frm.doc.requires_biometric) {
                frm.clear_custom_buttons();
                render_verify_button(frm);
                render_status_badge(frm);
            }
        },

        after_save(frm) {
            if (frm.doc.requires_biometric) {
                frm.clear_custom_buttons();
                render_verify_button(frm);
                render_status_badge(frm);
            }
        },

        requires_biometric(frm) {
            frm.clear_custom_buttons();
            if (!frm.is_new() && frm.doc.requires_biometric) {
                render_verify_button(frm);
                render_status_badge(frm);
            }
        },

        bio_employee(frm) {
            if (!frm.doc.bio_employee) return;
            frm.set_value('biometric_status', 'Pending');
            frm.set_value('biometric_verified_at', '');
            frm.set_value('matched_biometric_log', '');
            render_status_badge(frm);
            render_verify_button(frm);
            remove_other_employees_lines(frm);
        },

        // Auto-submit when verification succeeds
        biometric_status(frm) {
            if (
                frm.doc.requires_biometric &&
                frm.doc.biometric_status === 'Verified' &&
                frm.doc.docstatus === 0
            ) {
                setTimeout(() => {
                    frm.save('Save').then(() => {
                        frappe.confirm(
                            __('Biometric verification is complete. Submit this stock entry now?'),
                            () => {
                                frm._bypass_bio_check = true;
                                frappe.call({
                                    method: 'frappe.client.submit',
                                    args: { doc: frm.doc },
                                    callback(r) {
                                        frm._bypass_bio_check = false;
                                        if (r.docs || r.message) {
                                            frappe.model.sync(r.docs || [r.message]);
                                            frm.refresh();
                                        }
                                    },
                                    error() {
                                        frm._bypass_bio_check = false;
                                    }
                                });
                            }
                        );
                    });
                }, 300);
            }
        },

        // Soft-block: escalation warning instead of hard stop
        before_submit(frm) {
            if (!frm.doc.requires_biometric) return;
            if (frm.doc.biometric_status === 'Verified') return;
            if (frm._bypass_bio_check) return;

            // Cancel the default submit + its built-in "Permanently Submit?" dialog
            frappe.validated = false;

            frappe.confirm(
                __(
                    '<b>No biometric verification has been completed.</b><br><br>'
                    + 'Are you sure you want to submit this stock entry without '
                    + 'biometric verification?<br>This stock entry might be escalated.'
                ),
                () => {
                    frm._bypass_bio_check = true;
                    frappe.call({
                        method: 'frappe.client.submit',
                        args: { doc: frm.doc },
                        callback(r) {
                            frm._bypass_bio_check = false;
                            if (r.docs || r.message) {
                                frappe.model.sync(r.docs || [r.message]);
                                frm.refresh();
                            }
                        },
                        error() {
                            frm._bypass_bio_check = false;
                        }
                    });
                }
            );
        }
    });

    // ── Employee lines ───────────────────────────────────────────────────────
    // Unless Stock Settings allows collecting on behalf of others, only lines
    // requested for the signing employee can be issued in this entry.

    function remove_other_employees_lines(frm) {
        if (!frm.doc.requires_biometric || frm.doc.docstatus !== 0) return;

        frappe.call('upande_stores.employee_issuance.get_employee_issuance_settings').then((r) => {
            if ((r.message || {}).allow_collection_on_behalf) return;

            const others = (frm.doc.items || []).filter(
                (d) => d.employee && d.employee !== frm.doc.bio_employee
            );
            if (!others.length) return;

            frappe.confirm(
                __('{0} line(s) were requested for other employees and cannot be issued to {1}. Remove them from this Stock Entry?', [
                    others.length,
                    frm.doc.bio_employee_name || frm.doc.bio_employee
                ]),
                () => {
                    others.forEach((d) => frappe.model.clear_doc(d.doctype, d.name));
                    frm.refresh_field('items');
                    frm.dirty();
                }
            );
        });
    }

    // ── Verification helpers ─────────────────────────────────────────────────

    function render_verify_button(frm) {
        frm.remove_custom_button(__('Sign with Biometrics'));
        if (frm.doc.biometric_status === 'Verified') return;

        frm.add_custom_button(__('Sign with Biometrics'), () => {
            if (!frm.doc.bio_employee) {
                frappe.throw(__('Please select the Employee (Receiving) first.'));
                return;
            }
            run_verification(frm);
        }).addClass('btn-primary');
    }

    function run_verification(frm) {
        frappe.dom.freeze(__('Checking biometric log...'));

        frappe.call({
            method: 'frappe.client.get_list',
            args: {
                doctype: 'Biometric Logs',
                filters: [['employee', '=', frm.doc.bio_employee]],
                fields: ['name', 'employee', 'employee_name', 'time', 'log_type'],
                order_by: 'time desc',
                limit: 1
            },
            callback(r) {
                frappe.dom.unfreeze();
                console.log('Biometric query response:', r);

                if (!r.message || r.message.length === 0) {
                    frm.set_value('biometric_status', 'Failed');
                    render_status_badge(frm);
                    frappe.msgprint({
                        title: __('No Biometric Log Found'),
                        message: __(
                            'No biometric record exists at all for <b>{0}</b>.<br><br>'
                            + 'Please ensure the employee scans on the store device first.',
                            [frm.doc.bio_employee_name || frm.doc.bio_employee]
                        ),
                        indicator: 'red'
                    });
                    return;
                }

                const log = r.message[0];
                const log_time = new Date(log.time.replace(' ', 'T'));
                const now = new Date();
                const diff_seconds = (now - log_time) / 1000;
                const window_seconds = VERIFY_WINDOW_MINUTES * 60;

                console.log('Log found:', log, '| diff_seconds:', diff_seconds);

                if (diff_seconds <= window_seconds) {
                    frm.set_value('biometric_status', 'Verified');
                    frm.set_value('biometric_verified_at', frappe.datetime.now_datetime());
                    frm.set_value('matched_biometric_log', log.name);

                    render_status_badge(frm);
                    frm.remove_custom_button(__('Sign with Biometrics'));

                    frappe.show_alert({
                        message: __('Verified — {0} scanned {1} seconds ago', [
                            log.employee_name || log.employee,
                            Math.round(diff_seconds)
                        ]),
                        indicator: 'green'
                    }, 7);

                } else {
                    frm.set_value('biometric_status', 'Failed');
                    render_status_badge(frm);

                    frappe.msgprint({
                        title: __('Biometric Scan Too Old'),
                        message: __(
                            'The last scan for <b>{0}</b> was <b>{1} minute(s) ago</b> — outside the 1-minute window.<br><br>'
                            + 'Log name: {2}<br>'
                            + 'Scanned at: {3}<br><br>'
                            + 'Ask the employee to scan again on the store device, then click <b>Sign with Biometrics</b>.',
                            [
                                frm.doc.bio_employee_name || frm.doc.bio_employee,
                                Math.round(diff_seconds / 60),
                                log.name,
                                log.time
                            ]
                        ),
                        indicator: 'orange'
                    });
                }
            },
            error(r) {
                frappe.dom.unfreeze();
                console.error('Biometric call error:', r);
                frappe.show_alert({
                    message: __('Server error: ') + JSON.stringify(r),
                    indicator: 'red'
                }, 10);
            }
        });
    }

    // ── Status badge ─────────────────────────────────────────────────────────
    // We hide the raw biometric_status field entirely and replace it with the
    // styled pill badge, so the value never appears twice.

    function render_status_badge(frm) {
        // Hide only the input control — NOT the field row, so the wrapper
        // stays visible and the badge (appended below) remains in place.
        frm.fields_dict['biometric_status']?.$wrapper
            .find('.control-input-wrapper, .control-value, input, select')
            .hide();

        // Remove any existing badge before re-rendering
        frm.fields_dict['biometric_status']?.$wrapper.find('.bio-badge').remove();

        const status = frm.doc.biometric_status || 'Pending';
        const map = {
            'Verified': { bg: '#E1F5EE', color: '#0F6E56', dot: '#1D9E75', label: 'Verified' },
            'Failed':   { bg: '#FCEBEB', color: '#791F1F', dot: '#E24B4A', label: 'Failed'   },
            'Pending':  { bg: '#FAEEDA', color: '#633806', dot: '#BA7517', label: 'Pending'  }
        };
        const s = map[status] || map['Pending'];

        const badge = $(`
            <div class="bio-badge" style="
                display: inline-flex; align-items: center; gap: 5px;
                background: ${s.bg}; color: ${s.color};
                font-size: 12px; font-weight: 500;
                padding: 3px 10px; border-radius: 20px;
                margin-bottom: 8px;">
                <span style="width:7px;height:7px;border-radius:50%;
                             background:${s.dot};display:inline-block;"></span>
                ${s.label}
            </div>
        `);

        frm.fields_dict['biometric_status']?.$wrapper.append(badge);
    }
})();
