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


def _assignment_eligible_for_replacement(assignment):
	return assignment.status in ("Inactive", "Expired", "Returned") or assignment.last_inspection_status in (
		"Worn Out",
		"Lost",
	)


def _load_assignments(assignments):
	if isinstance(assignments, str):
		assignments = json.loads(assignments)
	if not assignments:
		frappe.throw(_("No assignments selected."))

	docs = []
	for name in assignments:
		doc = frappe.get_doc("Employee PPE Assignment", name)
		if not frappe.has_permission("Employee PPE Assignment", "write", doc=doc):
			frappe.throw(
				_("Not permitted to write to Employee PPE Assignment {0}.").format(doc.name),
				frappe.PermissionError,
			)
		docs.append(doc)
	return docs


def _check_same_scope(assignments):
	first = assignments[0]
	for assignment in assignments[1:]:
		if assignment.company != first.company:
			frappe.throw(
				_("All assignments must have the same Company. {0} has a different Company.").format(
					assignment.name
				)
			)
		if assignment.farm != first.farm:
			frappe.throw(
				_("All assignments must have the same Farm. {0} has a different Farm.").format(assignment.name)
			)
		if assignment.business_unit != first.business_unit:
			frappe.throw(
				_(
					"All assignments must have the same Business Unit. {0} has a different Business Unit."
				).format(assignment.name)
			)
	return first


@frappe.whitelist()
def create_bulk_ppe_material_request(assignments):
	docs = _load_assignments(assignments)
	first = _check_same_scope(docs)

	merged_items = {}
	employees = set()
	for assignment in docs:
		if assignment.replacement_requested:
			frappe.throw(_("{0} has already been requested for replacement.").format(assignment.name))
		if not _assignment_eligible_for_replacement(assignment):
			frappe.throw(_("{0} is not eligible for replacement.").format(assignment.name))
		employees.add(assignment.employee)
		merged_items[assignment.item_code] = merged_items.get(assignment.item_code, 0) + (
			assignment.quantity or 1
		)

	mr = frappe.get_doc(
		{
			"doctype": "Material Request",
			"material_request_type": "Material Issue",
			"schedule_date": today(),
			"company": first.company,
			"custom_farm": first.farm,
			"custom_business_unit": first.business_unit,
			"custom_ppe_issuance": 1,
			"custom_employee_data": [{"employee": employee} for employee in employees],
		}
	)
	for item_code, qty in merged_items.items():
		mr.append(
			"items",
			{"item_code": item_code, "qty": qty, "schedule_date": today(), "description": "PPE Issuance"},
		)
	mr.insert()

	for assignment in docs:
		frappe.db.set_value(
			"Employee PPE Assignment",
			assignment.name,
			{"replacement_requested": 1, "replacement_material_request": mr.name},
		)
	return mr.name
