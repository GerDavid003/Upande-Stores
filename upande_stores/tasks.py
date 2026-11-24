import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate


def mark_expired_ppe_assignments():
	today = getdate(nowdate())
	expired = frappe.get_all(
		"Employee PPE Assignment",
		filters={"status": "Active", "expiry_date": ["<=", today]},
		pluck="name",
	)
	for name in expired:
		doc = frappe.get_doc("Employee PPE Assignment", name)
		doc.status = "Expired"
		doc.save(ignore_permissions=True)


FREQUENCY_DAYS = {
	"Monthly": 30,
	"Quarterly": 90,
	"Half Yearly": 182,
	"Yearly": 365,
}


def _ppe_settings_frequency_days(settings):
	if settings.frequency == "Custom":
		return settings.custom_frequency_days or 0
	return FREQUENCY_DAYS.get(settings.frequency, 0)


def _ppe_frequency_days_for_company(company):
	"""Days between required inspections for `company`, per its PPE Settings
	row if one exists, else a loosest-cadence fallback (Yearly) so an
	unconfigured company's assignments don't look alarmingly overdue before
	anyone's set anything up."""
	settings = frappe.get_single("PPE Settings")
	for row in settings.company_notifications:
		if row.company == company:
			if row.frequency == "Custom":
				return row.custom_frequency_days or FREQUENCY_DAYS["Yearly"]
			return FREQUENCY_DAYS.get(row.frequency, FREQUENCY_DAYS["Yearly"])
	return FREQUENCY_DAYS["Yearly"]


def compute_next_inspection_due(company, last_inspection_date, issue_date):
	"""The date this assignment is next due for inspection: `last_inspection_date`
	if it's ever been inspected, else `issue_date`, plus this company's
	configured cadence."""
	base_date = last_inspection_date or issue_date
	if not base_date:
		return None
	days = _ppe_frequency_days_for_company(company)
	return add_days(base_date, days)


def refresh_ppe_inspection_overdue_flags():
	today = getdate(nowdate())
	frappe.db.sql(
		"""
		update `tabEmployee PPE Assignment`
		set inspection_overdue = case when next_inspection_due <= %(today)s then 1 else 0 end
		where status in ('Active', 'Expired') and next_inspection_due is not null
		""",
		{"today": today},
	)
	frappe.db.commit()


def send_ppe_inspection_reminders():
	today = getdate(nowdate())
	single_doc = frappe.get_single("PPE Settings")
	rows_to_update = []

	for row in single_doc.company_notifications:
		if not row.enabled:
			continue

		days = _ppe_settings_frequency_days(row)
		if not days:
			continue
		due_date = add_days(row.last_sent_on, days) if row.last_sent_on else today
		if today < getdate(due_date):
			continue

		overdue = _get_overdue_ppe_assignments(row.company, days)
		if overdue:
			_send_ppe_reminder_email(row, overdue)

		rows_to_update.append(row.name)

	if rows_to_update:
		doc = frappe.get_single("PPE Settings")
		for row in doc.company_notifications:
			if row.name in rows_to_update:
				row.last_sent_on = today
		doc.save(ignore_permissions=True)
		frappe.db.commit()


def _get_overdue_ppe_assignments(company, cutoff_days):
	cutoff = add_days(nowdate(), -cutoff_days)
	return frappe.db.sql(
		"""
		select name, employee, employee_name, item_code, item_name,
			last_inspection_date, issue_date
		from `tabEmployee PPE Assignment`
		where company = %(company)s
			and status = 'Active'
			and coalesce(last_inspection_date, issue_date) < %(cutoff)s
		order by coalesce(last_inspection_date, issue_date) asc
		""",
		{"company": company, "cutoff": cutoff},
		as_dict=True,
	)


def _role_profile_roles(role_profile):
	return frappe.get_all(
		"Has Role", filters={"parent": role_profile, "parenttype": "Role Profile"}, pluck="role"
	)


def _ppe_reminder_recipients(company, roles):
	if not roles:
		return []
	user_names = frappe.get_all(
		"Has Role", filters={"role": ["in", roles], "parenttype": "User"}, pluck="parent"
	)
	if not user_names:
		return []
	enabled_users = frappe.get_all(
		"User",
		filters={
			"name": ["in", list(set(user_names))],
			"enabled": 1,
			"user_type": "System User",
		},
		pluck="name",
	)
	recipients = []
	for user in enabled_users:
		if user == "Administrator":
			continue
		restricted_to = frappe.get_all(
			"User Permission",
			filters={"user": user, "allow": "Company"},
			pluck="for_value",
		)
		if not restricted_to or company in restricted_to:
			recipients.append(user)
	return recipients


def _default_ppe_reminder_message(company, overdue):
	rows = ""
	for row in overdue:
		last = row.last_inspection_date or row.issue_date
		rows += (
			f"<tr><td>{frappe.utils.escape_html(row.employee_name or row.employee)}</td>"
			f"<td>{frappe.utils.escape_html(row.item_name or row.item_code)}</td>"
			f"<td>{frappe.utils.format_date(last) if last else ''}</td></tr>"
		)
	return (
		f"<p>{_('The following PPE assignments for {0} are due for inspection:').format(company)}</p>"
		f"<table border='1' cellpadding='6' style='border-collapse:collapse'>"
		f"<tr><th>{_('Employee')}</th><th>{_('Item')}</th><th>{_('Last Inspected')}</th></tr>"
		f"{rows}</table>"
	)


def _send_ppe_reminder_email(settings_row, overdue):
	roles = _role_profile_roles(settings_row.notify_role_profile)
	recipients = _ppe_reminder_recipients(settings_row.company, roles)
	if not recipients:
		return

	context = {"company": settings_row.company, "assignments": overdue, "count": len(overdue)}
	if settings_row.email_template:
		template = frappe.get_doc("Email Template", settings_row.email_template)
		subject = frappe.render_template(template.subject, context)
		message = frappe.render_template(template.response_ or "", context)
	else:
		subject = _("PPE Inspection Reminder — {0}").format(settings_row.company)
		message = _default_ppe_reminder_message(settings_row.company, overdue)

	frappe.sendmail(
		recipients=recipients,
		subject=subject,
		message=message,
		reference_doctype="PPE Settings",
		reference_name="PPE Settings",
	)
