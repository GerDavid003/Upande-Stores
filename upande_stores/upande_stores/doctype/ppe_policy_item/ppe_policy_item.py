import frappe
from frappe import _
from frappe.model.document import Document


class PPEPolicyItem(Document):
	def validate(self):
		if self.item_code:
			is_ppe = frappe.db.get_value("Item", self.item_code, "custom_is_ppe")
			if not is_ppe:
				frappe.throw(_("Item {0} is not marked as a PPE item.").format(self.item_code))
