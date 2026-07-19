"""Shared test-document builders for upande_stores's Material Request /
Stock Entry employee-issuance-lock tests. Kept here (not duplicated per
test file) because both test_material_request.py and test_stock_entry.py
need the same minimal, valid documents.
"""

import frappe
from frappe.utils import today


def get_test_farm_and_business_unit():
	"""Return (farm_name, business_unit_name) from existing site data.

	Farm/Business Unit have no bundled test fixtures of their own (Farm's
	farm_type is a mandatory Table MultiSelect, non-trivial to construct from
	scratch) -- we reuse whatever real records already exist on the site
	under test rather than hardcoding a specific name.
	"""
	farm = frappe.get_all("Farm", limit=1, pluck="name")
	business_unit = frappe.get_all("Business Unit", limit=1, pluck="name")
	return (farm[0] if farm else None, business_unit[0] if business_unit else None)


def make_material_request(employee_rows=None):
	"""Create and insert a minimal submitted-ready 'Material Issue' Material
	Request. employee_rows is a list of dicts (e.g. {"employee": "HR-EMP-00001"}
	or {"employee": "HR-EMP-00001", "issued_via_stock_entry": "STE-0001"}),
	appended to custom_employee_data as-is.
	"""
	farm, business_unit = get_test_farm_and_business_unit()
	mr = frappe.get_doc(
		{
			"doctype": "Material Request",
			"material_request_type": "Material Issue",
			"transaction_date": today(),
			"company": "_Test Company",
			"custom_farm": farm,
			"custom_business_unit": business_unit,
			"items": [
				{
					"item_code": "_Test Item",
					"qty": 1,
					"uom": "_Test UOM",
					"stock_uom": "_Test UOM",
					"conversion_factor": 1,
					"schedule_date": today(),
					"warehouse": "_Test Warehouse - _TC",
				}
			],
		}
	)
	for row in employee_rows or []:
		mr.append("custom_employee_data", row)
	mr.insert(ignore_permissions=True)
	return mr
