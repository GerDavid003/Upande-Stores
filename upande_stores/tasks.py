import frappe
from frappe.utils import getdate, nowdate


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
