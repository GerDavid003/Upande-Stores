import frappe
from frappe import _
from frappe.model.document import Document


class PPEPolicy(Document):
	def validate(self):
		if not self.department and not self.designation:
			frappe.throw(_("Please set at least one of Department or Designation."))
		# Frappe does not automatically call a child table row's own validate()
		# when the parent is saved -- it must be invoked explicitly here so
		# PPEPolicyItem.validate() (rejecting non-PPE items) actually runs.
		for item in self.items:
			item.validate()
		if self.active:
			self._check_no_duplicate_active_policy()

	def _check_no_duplicate_active_policy(self):
		# Unset Link fields (department/designation) are stored as SQL NULL,
		# not "" -- a plain frappe.db.exists() filter dict does a strict "="
		# comparison and never matches NULL, so it would silently miss existing
		# rows whenever only one of department/designation is set. Use
		# COALESCE so NULL and "" are treated as equivalent "not set".
		conflict = frappe.db.sql(
			"""
			select name from `tabPPE Policy`
			where active = 1
				and name != %(name)s
				and company = %(company)s
				and coalesce(department, '') = %(department)s
				and coalesce(designation, '') = %(designation)s
			limit 1
			""",
			{
				"name": self.name or "",
				"company": self.company or "",
				"department": self.department or "",
				"designation": self.designation or "",
			},
		)
		if conflict:
			parts = [_("Company {0}").format(self.company)]
			if self.department:
				parts.append(_("Department {0}").format(self.department))
			if self.designation:
				parts.append(_("Designation {0}").format(self.designation))
			frappe.throw(
				_("An active PPE Policy for {0} already exists.").format(" and ".join(parts))
			)
