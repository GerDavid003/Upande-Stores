import json

import frappe
from frappe import _

# The Page doctype's own `roles` list only gates whether the page shows up in
# Desk -- it does NOT restrict these whitelisted methods, which are reachable
# directly via /api/method/... by any authenticated user regardless of role.
# Every method below must call _check_bulk_inspection_access() first, same
# pattern as apps/upande_stores/upande_stores/upande_stores/page/ppe_dashboard/ppe_dashboard.py.
ALLOWED_ROLES = {"System Manager", "HR Manager", "Farm Manager"}


def _check_bulk_inspection_access():
	if not set(frappe.get_roles()) & ALLOWED_ROLES:
		frappe.throw(_("Not permitted to use Bulk PPE Inspection."), frappe.PermissionError)
	if not frappe.has_permission("PPE Inspection", "create"):
		frappe.throw(_("Not permitted to create PPE Inspection records."), frappe.PermissionError)


@frappe.whitelist()
def get_bulk_inspection_candidates(farm=None, company=None):
	_check_bulk_inspection_access()

	if not farm and not company:
		frappe.throw(_("Select a Farm or Company before loading assignments."))

	# Role membership alone (checked above) doesn't prove this user may see
	# data scoped to this specific Farm/Company -- a Farm Manager restricted
	# via User Permissions to one farm could otherwise pass any other farm's
	# name here and read its employees' PPE data. Check explicitly, same
	# pattern used for company-scoping elsewhere in this app (e.g. the PPE
	# reminder email recipient scoping in tasks.py).
	if farm and not frappe.has_permission("Farm", "read", farm):
		frappe.throw(_("Not permitted to read Farm {0}.").format(farm), frappe.PermissionError)
	if company and not frappe.has_permission("Company", "read", company):
		frappe.throw(_("Not permitted to read Company {0}.").format(company), frappe.PermissionError)

	filters = {"status": ["in", ["Active", "Expired"]]}
	if farm:
		filters["farm"] = farm
	if company:
		filters["company"] = company

	# frappe.get_list (not get_all) so record-level/User Permission scoping on
	# Employee PPE Assignment itself is also enforced, not just the Farm/
	# Company checks above.
	return frappe.get_list(
		"Employee PPE Assignment",
		filters=filters,
		fields=["name as employee_ppe_assignment", "employee", "employee_name", "item_code", "item_name", "issue_date"],
		order_by="employee_name asc, item_name asc",
	)


@frappe.whitelist()
def submit_bulk_ppe_inspection(farm, inspection_date, supervisor, rows):
	_check_bulk_inspection_access()

	if isinstance(rows, str):
		rows = json.loads(rows)

	if not farm:
		frappe.throw(_("Farm is required."))
	if not inspection_date:
		frappe.throw(_("Inspection Date is required."))
	if not supervisor:
		frappe.throw(_("Supervisor is required."))
	if not rows:
		frappe.throw(_("No rows to submit."))

	# Group rows by employee -- one PPE Inspection per employee, exactly like
	# a manual single-employee entry would produce.
	rows_by_employee = {}
	for row in rows:
		rows_by_employee.setdefault(row["employee"], []).append(row)

	company = frappe.db.get_value("Farm", farm, "company")

	results = []
	for employee, employee_rows in rows_by_employee.items():
		try:
			doc = frappe.get_doc(
				{
					"doctype": "PPE Inspection",
					"employee": employee,
					"supervisor": supervisor,
					"farm": farm,
					"company": company,
					"inspection_date": inspection_date,
					"items_inspected": [
						{
							"employee_ppe_assignment": r["employee_ppe_assignment"],
							"current_status": r["current_status"],
							"comments": r.get("comments") or "",
							"other_reason": r.get("other_reason") or "",
						}
						for r in employee_rows
					],
				}
			)
			doc.insert()

			has_worn_out = any(r["current_status"] == "Worn Out" for r in employee_rows)
			if not has_worn_out:
				doc.submit()

			employee_name = employee_rows[0].get("employee_name") or frappe.db.get_value(
				"Employee", employee, "employee_name"
			)
			results.append(
				{
					"employee": employee,
					"employee_name": employee_name,
					"name": doc.name,
					"submitted": not has_worn_out,
				}
			)
		except Exception as e:
			# Do not call frappe.db.rollback() here: this method runs inside a
			# single request-level transaction shared across all employees in
			# the batch, and rolling back would also discard earlier
			# employees' already-successful inserts/submits in this same
			# call. doc.insert()/doc.submit() are left to commit as part of
			# Frappe's normal request lifecycle; one employee's failure is
			# simply caught and recorded so the loop can continue.
			results.append({"employee": employee, "error": str(e), "submitted": False})
			continue

	return results
