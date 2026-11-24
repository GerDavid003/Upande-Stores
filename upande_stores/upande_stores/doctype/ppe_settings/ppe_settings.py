import frappe
from frappe import _
from frappe.model.document import Document


class PPESettings(Document):
	def validate(self):
		self._validate_company_notifications()

	def _validate_company_notifications(self):
		seen_companies = set()
		for row in self.company_notifications:
			if row.frequency == "Custom" and not row.custom_frequency_days:
				frappe.throw(
					_("Row {0}: set Custom Frequency (Days) when Frequency is Custom.").format(row.idx)
				)
			if not row.notify_role_profile:
				frappe.throw(_("Row {0}: select a Notify Role Profile.").format(row.idx))
			if row.company in seen_companies:
				frappe.throw(
					_("Row {0}: {1} already has a notification setting in this table.").format(
						row.idx, row.company
					)
				)
			seen_companies.add(row.company)
