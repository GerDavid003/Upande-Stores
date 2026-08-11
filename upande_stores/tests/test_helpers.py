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


def make_material_request(items=None, material_request_type="Material Issue"):
	"""Create and insert a minimal submitted-ready Material Request.

	`items` is a list of dicts, each becoming one row in the standard Items
	table directly -- e.g. {"employee": <name>} (defaults to
	item_code="_Test Item", qty=1) or {"employee": <name>, "item_code": ...,
	"qty": ...} for a specific allocation, or {"item_code": ..., "qty": ...}
	with no employee at all. Defaults to material_request_type="Material
	Issue" (this app's primary use case, where every row needs an employee);
	pass "Material Transfer" for tests that need employee to stay optional.

	Each row's item_code/qty/uom/stock_uom/conversion_factor/warehouse
	default the same way the old single-hardcoded-row version did --
	callers only need to specify what's different from that default.
	Material Request Item's "Purpose" (description) field is mandatory
	site-wide via a real Property Setter; ERPNext's own item-defaults fetch
	normally back-fills it from the Item master's description, but
	"_Test Item"/"_Test Item 2" are the only items in this codebase's
	fixtures that happen to have one set, so it's defaulted here explicitly
	to cover any other item_code (e.g. a PPE item from make_ppe_item, which
	has none) too.
	"""
	farm, business_unit = get_test_farm_and_business_unit()
	mr = frappe.get_doc(
		{
			"doctype": "Material Request",
			"material_request_type": material_request_type,
			"transaction_date": today(),
			"company": "Karen Roses",
			"custom_farm": farm,
			"custom_business_unit": business_unit,
		}
	)
	for row in items or []:
		item_code = row.get("item_code", "_Test Item")
		defaults = {
			"item_code": item_code,
			"qty": 1,
			"uom": "_Test UOM",
			"stock_uom": "_Test UOM",
			"conversion_factor": 1,
			"schedule_date": today(),
			"warehouse": "Stores - KR",
			"description": item_code,
		}
		defaults.update(row)
		mr.append("items", defaults)
	mr.insert(ignore_permissions=True)
	return mr


def make_stock_entry_for_material_request(material_request, bio_employee=None, item_code=None, qty=1):
	"""Create a not-yet-submitted 'Material Issue' Stock Entry whose single
	item references material_request's first item row -- the same shape the
	real "Create" button on a submitted Material Request produces.

	item_code selects which of material_request's item rows to issue against
	(defaults to the first row, matching every pre-existing caller); qty
	defaults to 1. Both are needed for per-employee-allocation tests, which
	build Material Requests with more than one item row and issue a specific
	quantity against a specific one -- possibly more than once, to exercise
	partial issuance.
	"""
	mr_item = material_request.items[0]
	if item_code:
		mr_item = next(row for row in material_request.items if row.item_code == item_code)
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
					"qty": qty,
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
