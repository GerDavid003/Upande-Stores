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
		frappe.db.set_value("Employee PPE Assignment", name, "status", "Expired")
