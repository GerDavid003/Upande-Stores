import json

import frappe
from frappe import _
from frappe.utils import today


def _matching_ppe_policies(company, department, designation):
	"""Active PPE Policies for this exact company where department/designation
	are either unset on the policy (wildcard) or match exactly."""
	policies = frappe.get_all(
		"PPE Policy",
		filters={"active": 1, "company": company},
		fields=["name", "department", "designation"],
	)
	matched = []
	for policy in policies:
		dept_match = (not policy.department) or (policy.department == (department or ""))
		desig_match = (not policy.designation) or (policy.designation == (designation or ""))
		if dept_match and desig_match:
			matched.append(policy.name)
	return matched


@frappe.whitelist()
def get_ppe_requirements_for_onboarding(employee):
	if not frappe.has_permission("PPE Policy", "read"):
		frappe.throw(
			_("Not permitted to read PPE Policy data."), frappe.PermissionError
		)

	emp = frappe.db.get_value(
		"Employee", employee, ["company", "department", "designation"], as_dict=True
	)
	if not emp:
		frappe.throw(_("Employee {0} not found.").format(employee))
	if not emp.company:
		frappe.throw(_("Employee {0} has no Company set.").format(employee))

	policy_names = _matching_ppe_policies(emp.company, emp.department, emp.designation)

	merged = {}
	for policy_name in policy_names:
		policy = frappe.get_doc("PPE Policy", policy_name)
		for row in policy.items:
			if row.item_code in merged:
				merged[row.item_code]["quantity"] += row.quantity
			else:
				merged[row.item_code] = {
					"item_code": row.item_code,
					"item_name": row.item_name or row.item_code,
					"quantity": row.quantity,
				}
	return [row for row in merged.values() if row["quantity"] > 0]


@frappe.whitelist()
def create_ppe_onboarding_material_request(onboarding, employee, items):
	if not frappe.has_permission("Employee Onboarding", "write", doc=onboarding):
		frappe.throw(
			_("Not permitted to write to Employee Onboarding {0}.").format(onboarding),
			frappe.PermissionError,
		)

	onboarding_employee = frappe.db.get_value("Employee Onboarding", onboarding, "employee")
	if not onboarding_employee:
		frappe.throw(_("Employee Onboarding {0} not found.").format(onboarding))
	if onboarding_employee != employee:
		frappe.throw(_("Employee does not match the Employee Onboarding record."))

	existing_mr = frappe.db.get_value(
		"Employee Onboarding", onboarding, "custom_ppe_material_request"
	)
	if existing_mr:
		frappe.throw(
			_("A PPE Material Request ({0}) already exists for this onboarding.").format(existing_mr)
		)

	if isinstance(items, str):
		items = json.loads(items)
	if not items:
		frappe.throw(_("Items list is empty."))

	emp = frappe.db.get_value(
		"Employee", employee, ["company", "custom_farm", "custom_business_unit"], as_dict=True
	)
	if not emp or not emp.company:
		frappe.throw(_("Employee {0} has no Company set.").format(employee))

	mr = frappe.get_doc(
		{
			"doctype": "Material Request",
			"material_request_type": "Material Issue",
			"schedule_date": today(),
			"company": emp.company,
			"custom_farm": emp.custom_farm or "",
			"custom_business_unit": emp.custom_business_unit or "",
			"custom_ppe_issuance": 1,
			"custom_employee_data": [{"employee": employee}],
		}
	)
	for item in items:
		mr.append(
			"items",
			{
				"item_code": item["item_code"],
				"qty": item["quantity"],
				"schedule_date": today(),
				"description": "PPE Issuance",
			},
		)
	mr.insert()

	frappe.db.set_value("Employee Onboarding", onboarding, "custom_ppe_material_request", mr.name)
	return mr.name
