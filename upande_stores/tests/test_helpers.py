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


def get_test_employees(count=2):
	"""Return up to `count` live Active Employee names.

	Like Farm/Business Unit, Employee has no bundled test fixture guaranteeing
	a specific record exists, so we look up real records rather than
	hardcoding a name like "HR-EMP-00001" -- callers should skip their test
	if fewer than the needed count come back.
	"""
	return frappe.get_all("Employee", filters={"status": "Active"}, limit=count, pluck="name")


def make_material_request(employee_rows=None, qty=1, item_code="_Test Item"):
	"""Create and insert a minimal submitted-ready 'Material Issue' Material
	Request. employee_rows is a list of dicts (e.g. {"employee": <name>}
	or {"employee": <name>, "issued_via_stock_entry": "STE-0001"}), appended
	to custom_employee_data as-is. qty defaults to 1; pass a higher value
	when a test needs to issue against the same Material Request more than
	once without tripping ERPNext's own "can't over-issue" guard before the
	code under test gets a chance to run. item_code defaults to "_Test Item";
	pass a specific item (e.g. a PPE item from make_ppe_item) when a caller's
	Stock Entry needs to reference this Material Request's item row -- ERPNext
	rejects a Stock Entry row whose item_code doesn't match the Material
	Request Item it points at via material_request_item.
	"""
	farm, business_unit = get_test_farm_and_business_unit()
	mr = frappe.get_doc(
		{
			"doctype": "Material Request",
			"material_request_type": "Material Issue",
			"transaction_date": today(),
			"company": "Karen Roses",
			"custom_farm": farm,
			"custom_business_unit": business_unit,
			"items": [
				{
					"item_code": item_code,
					"qty": qty,
					"uom": "_Test UOM",
					"stock_uom": "_Test UOM",
					"conversion_factor": 1,
					"schedule_date": today(),
					"warehouse": "Stores - KR",
					# Material Request Item's "Purpose" (description) field is
					# mandatory site-wide via a real Property Setter. ERPNext's
					# own item-defaults fetch normally back-fills it from the
					# Item master's description, but "_Test Item" is the only
					# item in this codebase's fixtures that happens to have one
					# set -- any other item_code (e.g. a PPE item from
					# make_ppe_item, which has none) would otherwise trip that
					# mandatory check. Setting it explicitly here covers every
					# item_code, not just the default.
					"description": item_code,
				}
			],
		}
	)
	for row in employee_rows or []:
		mr.append("custom_employee_data", row)
	mr.insert(ignore_permissions=True)
	return mr


def make_stock_entry_for_material_request(material_request, bio_employee=None):
	"""Create a not-yet-submitted 'Material Issue' Stock Entry whose single
	item references material_request's first item row -- the same shape the
	real "Create" button on a submitted Material Request produces."""
	mr_item = material_request.items[0]
	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"purpose": "Material Issue",
			"stock_entry_type": "Material Issue",
			"company": "Karen Roses",
			"bio_employee": bio_employee,
			"items": [
				{
					"item_code": mr_item.item_code,
					"qty": 1,
					"uom": "_Test UOM",
					"stock_uom": "_Test UOM",
					"conversion_factor": 1,
					"s_warehouse": "Stores - KR",
					"material_request": material_request.name,
					"material_request_item": mr_item.name,
				}
			],
		}
	)
	se.insert(ignore_permissions=True)
	return se


def make_ppe_item(lifespan_months=6):
	"""Return the name of a custom_is_ppe Item with the given lifespan, creating
	it if it doesn't exist yet on this site."""
	item_code = f"_Test PPE Item {lifespan_months}mo"
	if not frappe.db.exists("Item", item_code):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": item_code,
				"item_group": "_Test Item Group",
				"stock_uom": "_Test UOM",
				"is_stock_item": 1,
				"custom_is_ppe": 1,
				"custom_ppe_lifespan": lifespan_months,
			}
		).insert(ignore_permissions=True)
	return item_code
