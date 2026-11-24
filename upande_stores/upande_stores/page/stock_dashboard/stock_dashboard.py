import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, nowdate

# ============================================================
# Security -- applied from the start (see ppe_dashboard.py for the review
# finding this pattern originally fixed: the Page doctype's own `roles`
# list only gates whether the page shows up in Desk, it does NOT restrict
# these whitelisted methods, which are reachable directly via
# /api/method/... by any authenticated user regardless of role).
# ============================================================
ALLOWED_ROLES = {
	"System Manager",
	"Stock Manager",
	"Stock User",
	"Purchase Manager",
	"Purchase User",
	"Accounts Manager",
	"Accounts User",
	"Farm Manager",
}


def _check_dashboard_access():
	if not set(frappe.get_roles()) & ALLOWED_ROLES:
		frappe.throw(_("Not permitted to view the Stock Dashboard."), frappe.PermissionError)


# ============================================================
# Rose item-group exclusion -- NOT a company exclusion (Karen Roses stays
# in the switcher), only an item-group exclusion. "Roses" and "Roses
# Chemical Spray Products" are themselves leaf item groups; "Spray Roses"
# and "Standard Roses" are is_group=1 parents each with several real
# sub-groups (Spray Roses - Bombastics, Standard Roses - Garden, ...).
# Resolved via the Item Group nested set (lft/rgt) at call time rather than
# hardcoding descendant names or lft/rgt numbers, so it stays correct if
# the tree is edited later. Confirmed against real data: 4 roots resolve
# to 16 item groups total.
# ============================================================
ROSE_ITEM_GROUP_ROOTS = ["Roses", "Spray Roses", "Standard Roses", "Roses Chemical Spray Products"]


def _rose_item_groups():
	roots = frappe.get_all("Item Group", filters={"name": ["in", ROSE_ITEM_GROUP_ROOTS]}, fields=["lft", "rgt"])
	if not roots:
		return []
	conditions = " or ".join(["(lft >= %s and rgt <= %s)"] * len(roots))
	params = [v for r in roots for v in (r.lft, r.rgt)]
	return frappe.db.sql_list(f"select name from `tabItem Group` where {conditions}", params)


def _rose_exclusion(item_code_col):
	"""Returns (sql_fragment, params) excluding rows whose `item_code_col`
	belongs to a rose item group. The fragment is "" (and params []) when
	there's nothing to exclude -- MySQL errors on an empty `in ()` list, so
	callers must splice this exact fragment in rather than assuming it
	always contributes a clause. The fragment must be spliced in at the end
	of the query's WHERE/EXISTS (...) and `params` appended as the last
	elements of that query's parameter tuple, since %s placeholders are
	positional."""
	groups = _rose_item_groups()
	if not groups:
		return "", []
	placeholders = ", ".join(["%s"] * len(groups))
	return (
		f" and {item_code_col} not in (select name from `tabItem` where item_group in ({placeholders}))",
		list(groups),
	)


# ============================================================
# Stock Entry type scope. `stock_entry_type` (a custom-extended Select/Link
# field with harvest/livestock-specific values added on top of the core
# ERPNext set) is NOT the same thing as `purpose` (the small, fixed core
# ERPNext field every Stock Entry also carries for GL/stock-ledger
# purposes). Verified against real data that `purpose` is unusable for this
# exclusion: harvest-type entries get mapped onto the *nearest* core
# `purpose` value for posting purposes -- e.g. every "Harvesting" entry
# (1,858,120 rows) carries purpose="Material Receipt", every "Grading"
# entry (1,440,374 rows) carries purpose="Material Transfer" -- so
# filtering on `purpose` would still include millions of harvest/grading
# rows mislabeled as ordinary receipts/transfers. `stock_entry_type` is the
# only column that actually distinguishes them, so every query below filters
# on it.
#
# Scope is a DENYLIST (not an allowlist), per explicit user correction:
# "include everything except harvesting, grading, receiving" -- then
# further corrected to also exclude Packing and Dispatch. One shared
# constant, used identically everywhere `stock_entry_type` is filtered
# (Tab 1's KPI, Tab 3's listing, Tab 6's consumption aggregation).
# ============================================================
EXCLUDED_STOCK_ENTRY_TYPES = ["Harvesting", "Grading", "Receiving", "Packing", "Dispatch"]


@frappe.whitelist()
def get_companies():
	_check_dashboard_access()
	companies = frappe.get_list(
		"Material Request",
		fields=["company"],
		distinct=True,
		filters={"company": ["is", "set"]},
		order_by="company asc",
		pluck="company",
	)
	default_company = frappe.defaults.get_user_default("Company")
	return {"companies": companies, "default_company": default_company}


@frappe.whitelist()
def get_overview(company: str, from_date: str = None, to_date: str = None):
	"""`from_date`/`to_date` default to the last 30 days, same as the
	original hardcoded window, so nothing changes until the user actually
	touches the new date range control. Only the genuinely period-dependent
	KPIs (stock entry count, consumption value) respect the range --
	point-in-time KPIs (total stock value on hand, pending PO/Receipt
	counts, open Material Requests) don't conceptually have a date range,
	so they stay exactly as before regardless of what's selected."""
	_check_dashboard_access()
	frappe.has_permission("Company", "read", company, throw=True)

	to_date = to_date or nowdate()
	period_start = from_date or add_days(to_date, -30)

	rose_clause, rose_params = _rose_exclusion("mri.item_code")
	# Open Material Issue / Material Transfer requests: at least one
	# non-rose item row not yet fully issued (issued_via_stock_entry unset
	# -- upande_stores' own tracking field, same signal the PPE dashboard
	# already uses correctly; per_ordered doesn't apply to these two types,
	# it tracks conversion to Purchase Order/Work Order, which never
	# happens for a Material Issue/Transfer request).
	open_issue_transfer = frappe.db.sql(
		f"""
		select count(distinct mr.name)
		from `tabMaterial Request` mr
		inner join `tabMaterial Request Item` mri on mri.parent = mr.name
		where mr.material_request_type in ('Material Issue', 'Material Transfer')
		  and mr.company = %s and mr.docstatus = 1
		  and (mri.issued_via_stock_entry is null or mri.issued_via_stock_entry = ''){rose_clause}
		""",
		(company, *rose_params),
	)[0][0]

	# Open Purchase / Manufacture requests: per_ordered < 100 (ERPNext's own
	# conversion-to-PO/Work-Order percentage, which DOES apply cleanly to
	# both of these types), scoped to requests that still have at least one
	# non-rose item row.
	open_purchase_manufacture = frappe.db.sql(
		f"""
		select count(distinct mr.name)
		from `tabMaterial Request` mr
		where mr.material_request_type in ('Purchase', 'Manufacture')
		  and mr.company = %s and mr.docstatus = 1 and mr.per_ordered < 100
		  and exists (
		      select 1 from `tabMaterial Request Item` mri
		      where mri.parent = mr.name{rose_clause}
		  )
		""",
		(company, *rose_params),
	)[0][0]

	entry_type_placeholders = ", ".join(["%s"] * len(EXCLUDED_STOCK_ENTRY_TYPES))
	stock_entries_period = frappe.db.sql(
		f"""
		select count(*) from `tabStock Entry`
		where company = %s and docstatus = 1 and posting_date between %s and %s
		  and stock_entry_type not in ({entry_type_placeholders})
		""",
		(company, period_start, to_date, *EXCLUDED_STOCK_ENTRY_TYPES),
	)[0][0]

	bin_clause, bin_params = _rose_exclusion("b.item_code")
	total_stock_value = frappe.db.sql(
		f"""
		select coalesce(sum(b.stock_value), 0)
		from `tabBin` b
		inner join `tabWarehouse` w on w.name = b.warehouse
		where w.company = %s{bin_clause}
		""",
		(company, *bin_params),
	)[0][0]

	poi_clause, poi_params = _rose_exclusion("poi.item_code")
	pending_purchase_orders = frappe.db.sql(
		f"""
		select count(distinct po.name)
		from `tabPurchase Order` po
		where po.company = %s and po.docstatus = 1 and po.per_received < 100
		  and exists (
		      select 1 from `tabPurchase Order Item` poi
		      where poi.parent = po.name{poi_clause}
		  )
		""",
		(company, *poi_params),
	)[0][0]

	pri_clause, pri_params = _rose_exclusion("pri.item_code")
	pending_purchase_receipts = frappe.db.sql(
		f"""
		select count(distinct pr.name)
		from `tabPurchase Receipt` pr
		where pr.company = %s and pr.docstatus = 1 and pr.per_billed < 100
		  and exists (
		      select 1 from `tabPurchase Receipt Item` pri
		      where pri.parent = pr.name{pri_clause}
		  )
		""",
		(company, *pri_params),
	)[0][0]

	consumption_clause, consumption_params = _rose_exclusion("sed.item_code")
	consumption_period = frappe.db.sql(
		f"""
		select coalesce(sum(sed.amount), 0)
		from `tabStock Entry Detail` sed
		inner join `tabStock Entry` se on se.name = sed.parent and se.docstatus = 1
		where se.company = %s and se.posting_date between %s and %s
		  and se.stock_entry_type not in ({entry_type_placeholders}){consumption_clause}
		""",
		(company, period_start, to_date, *EXCLUDED_STOCK_ENTRY_TYPES, *consumption_params),
	)[0][0]

	return {
		"from_date": period_start,
		"to_date": to_date,
		"open_material_requests": cint(open_issue_transfer) + cint(open_purchase_manufacture),
		"stock_entries_period": stock_entries_period,
		"total_stock_value": flt(total_stock_value),
		"pending_purchase_orders": pending_purchase_orders,
		"pending_purchase_receipts": pending_purchase_receipts,
		"consumption_period": flt(consumption_period),
	}


@frappe.whitelist()
def get_material_requests(
	company: str,
	request_type: str = None,
	fulfillment: str = None,
	search: str = None,
	start: int = 0,
	page_length: int = 50,
):
	"""Server-side filtered and paginated from the start -- same {rows,
	total} pattern the PPE dashboard's get_assignments had to be retrofitted
	with after a first version capped at 100 rows; this build never makes
	that mistake to begin with."""
	_check_dashboard_access()
	frappe.has_permission("Company", "read", company, throw=True)

	conditions = ["mr.company = %s", "mr.docstatus = 1"]
	params = [company]

	if request_type and request_type != "All":
		conditions.append("mr.material_request_type = %s")
		params.append(request_type)

	rose_clause, rose_params = _rose_exclusion("mri2.item_code")
	conditions.append(
		f"exists (select 1 from `tabMaterial Request Item` mri2 where mri2.parent = mr.name{rose_clause})"
	)
	params.extend(rose_params)

	# "Open" / "Fulfilled" means something different per type (see
	# get_overview's own split): per_ordered for Purchase/Manufacture,
	# issued_via_stock_entry presence for Material Issue/Transfer. Built as
	# a SQL fragment picked from a fixed, validated set of three outcomes
	# (not string-interpolated user input) so pagination's COUNT and the
	# page query stay consistent with each other.
	if fulfillment in ("Open", "Fulfilled"):
		open_expr = """(
			(mr.material_request_type in ('Purchase', 'Manufacture') and mr.per_ordered < 100)
			or (
				mr.material_request_type in ('Material Issue', 'Material Transfer')
				and exists (
					select 1 from `tabMaterial Request Item` mri3
					where mri3.parent = mr.name
					  and (mri3.issued_via_stock_entry is null or mri3.issued_via_stock_entry = '')
				)
			)
		)"""
		conditions.append(open_expr if fulfillment == "Open" else f"not {open_expr}")

	if search:
		like = f"%{search}%"
		conditions.append(
			"""(
				mr.name like %s
				or exists (
					select 1 from `tabMaterial Request Item` mri4
					inner join `tabItem` it4 on it4.name = mri4.item_code
					where mri4.parent = mr.name and (mri4.item_code like %s or it4.item_name like %s)
				)
			)"""
		)
		params.extend([like, like, like])

	where_sql = " and ".join(conditions)

	total = frappe.db.sql(
		f"select count(*) from `tabMaterial Request` mr where {where_sql}", tuple(params)
	)[0][0]

	rows = frappe.db.sql(
		f"""
		select
		    mr.name, mr.material_request_type, mr.transaction_date, mr.status, mr.docstatus,
		    mr.per_ordered, mr.per_received,
		    (select count(*) from `tabMaterial Request Item` x where x.parent = mr.name) as item_count,
		    (select count(*) from `tabMaterial Request Item` x where x.parent = mr.name
		        and (x.issued_via_stock_entry is null or x.issued_via_stock_entry = '')
		    ) as unfulfilled_item_count
		from `tabMaterial Request` mr
		where {where_sql}
		order by mr.creation desc
		limit %s offset %s
		""",
		(*params, cint(page_length), cint(start)),
		as_dict=True,
	)
	for row in rows:
		if row.material_request_type in ("Purchase", "Manufacture"):
			row["is_open"] = flt(row.per_ordered) < 100
		else:
			row["is_open"] = cint(row.unfulfilled_item_count) > 0

	return {"rows": rows, "total": total}


@frappe.whitelist()
def get_stock_entries(
	company: str, stock_entry_type: str = None, search: str = None, start: int = 0, page_length: int = 50
):
	_check_dashboard_access()
	frappe.has_permission("Company", "read", company, throw=True)

	entry_type_placeholders = ", ".join(["%s"] * len(EXCLUDED_STOCK_ENTRY_TYPES))
	conditions = [
		"se.company = %s",
		"se.docstatus = 1",
		f"se.stock_entry_type not in ({entry_type_placeholders})",
	]
	params = [company, *EXCLUDED_STOCK_ENTRY_TYPES]

	if stock_entry_type and stock_entry_type != "All":
		conditions.append("se.stock_entry_type = %s")
		params.append(stock_entry_type)

	rose_clause, rose_params = _rose_exclusion("sed2.item_code")
	conditions.append(f"exists (select 1 from `tabStock Entry Detail` sed2 where sed2.parent = se.name{rose_clause})")
	params.extend(rose_params)

	if search:
		like = f"%{search}%"
		conditions.append(
			"""(
				se.name like %s or se.from_warehouse like %s or se.to_warehouse like %s
				or exists (
					select 1 from `tabStock Entry Detail` sed5
					inner join `tabItem` it5 on it5.name = sed5.item_code
					where sed5.parent = se.name and (sed5.item_code like %s or it5.item_name like %s)
				)
			)"""
		)
		params.extend([like, like, like, like, like])

	where_sql = " and ".join(conditions)

	total = frappe.db.sql(f"select count(*) from `tabStock Entry` se where {where_sql}", tuple(params))[0][0]

	rows = frappe.db.sql(
		f"""
		select
		    se.name, se.stock_entry_type, se.posting_date, se.from_warehouse, se.to_warehouse,
		    se.total_amount,
		    (select sed4.material_request from `tabStock Entry Detail` sed4
		        where sed4.parent = se.name and sed4.material_request is not null and sed4.material_request != ''
		        limit 1) as material_request,
		    (select count(*) from `tabStock Entry Detail` x where x.parent = se.name) as item_count
		from `tabStock Entry` se
		where {where_sql}
		order by se.creation desc
		limit %s offset %s
		""",
		(*params, cint(page_length), cint(start)),
		as_dict=True,
	)
	return {"rows": rows, "total": total}


@frappe.whitelist()
def get_procurement(company: str, search: str = None, supplier: str = None):
	"""Same funnel shape as the PPE dashboard's Procurement tab (Purchase
	Request -> Purchase Order -> Purchase Receipt), but the general case:
	every non-rose Purchase-type request for this company, not scoped to
	any item-level custom flag. `search` (PO name or supplier) and
	`supplier` (exact match, used by the Suppliers tab's drill-down into
	"just this supplier's POs") both only narrow the Purchase Orders list
	shown below the funnel -- the funnel's own counts stay the full
	pipeline totals, not re-filtered by either."""
	_check_dashboard_access()
	frappe.has_permission("Company", "read", company, throw=True)

	mri_clause, mri_params = _rose_exclusion("mri.item_code")
	pr_stage = frappe.db.sql(
		f"""
		select count(distinct mr.name) as cnt, coalesce(sum(mri.qty), 0) as qty
		from `tabMaterial Request` mr
		inner join `tabMaterial Request Item` mri on mri.parent = mr.name
		where mr.material_request_type = 'Purchase' and mr.company = %s and mr.docstatus = 1{mri_clause}
		""",
		(company, *mri_params),
		as_dict=True,
	)[0]

	poi_clause, poi_params = _rose_exclusion("poi.item_code")
	po_stage = frappe.db.sql(
		f"""
		select count(distinct po.name) as cnt, coalesce(sum(poi.qty), 0) as qty
		from `tabPurchase Order Item` poi
		inner join `tabPurchase Order` po on po.name = poi.parent and po.docstatus = 1
		inner join `tabMaterial Request` mr on mr.name = poi.material_request
		where mr.material_request_type = 'Purchase' and mr.company = %s{poi_clause}
		""",
		(company, *poi_params),
		as_dict=True,
	)[0]

	pri_clause, pri_params = _rose_exclusion("pri.item_code")
	receipt_stage = frappe.db.sql(
		f"""
		select count(distinct pr.name) as cnt, coalesce(sum(pri.qty), 0) as qty
		from `tabPurchase Receipt Item` pri
		inner join `tabPurchase Receipt` pr on pr.name = pri.parent and pr.docstatus = 1
		inner join `tabMaterial Request` mr on mr.name = pri.material_request
		where mr.material_request_type = 'Purchase' and mr.company = %s{pri_clause}
		""",
		(company, *pri_params),
		as_dict=True,
	)[0]

	po_poi_clause, po_poi_params = _rose_exclusion("poi2.item_code")
	search_clause, search_params = "", []
	if search:
		like = f"%{search}%"
		search_clause = """ and (
			po.name like %s or po.supplier like %s
			or exists (
				select 1 from `tabPurchase Receipt Item` pri3
				inner join `tabPurchase Receipt` pr3 on pr3.name = pri3.parent and pr3.docstatus = 1
				where pri3.purchase_order = po.name and pr3.name like %s
			)
		)"""
		search_params = [like, like, like]
	supplier_clause, supplier_params = "", []
	if supplier:
		supplier_clause = " and po.supplier = %s"
		supplier_params = [supplier]
	po_list = frappe.db.sql(
		f"""
		select distinct po.name, po.supplier, po.transaction_date, po.status, po.grand_total
		from `tabPurchase Order` po
		inner join `tabPurchase Order Item` poi2 on poi2.parent = po.name
		inner join `tabMaterial Request` mr on mr.name = poi2.material_request
		where mr.material_request_type = 'Purchase' and mr.company = %s{po_poi_clause}{search_clause}{supplier_clause}
		order by po.transaction_date desc
		limit 100
		""",
		(company, *po_poi_params, *search_params, *supplier_params),
		as_dict=True,
	)

	receipt_map = {}
	if po_list:
		po_names = [row.name for row in po_list]
		receipts = frappe.db.sql(
			"""
			select pri.purchase_order as po_name, pr.name, pr.posting_date
			from `tabPurchase Receipt Item` pri
			inner join `tabPurchase Receipt` pr on pr.name = pri.parent and pr.docstatus = 1
			where pri.purchase_order in %s
			order by pr.posting_date desc
			""",
			(po_names,),
			as_dict=True,
		)
		for row in receipts:
			receipt_map.setdefault(row.po_name, row)

	for row in po_list:
		receipt = receipt_map.get(row.name)
		row["receipt_name"] = receipt.name if receipt else None
		row["receipt_date"] = receipt.posting_date if receipt else None

	first_qty = flt(pr_stage.qty) or 1
	funnel = [
		{"stage": "Purchase Requests", "count": pr_stage.cnt, "qty": flt(pr_stage.qty), "width_pct": 100},
		{
			"stage": "Purchase Orders",
			"count": po_stage.cnt,
			"qty": flt(po_stage.qty),
			"width_pct": min(100, (flt(po_stage.qty) / first_qty) * 100),
		},
		{
			"stage": "Purchase Receipts",
			"count": receipt_stage.cnt,
			"qty": flt(receipt_stage.qty),
			"width_pct": min(100, (flt(receipt_stage.qty) / first_qty) * 100),
		},
	]
	return {"funnel": funnel, "purchase_orders": po_list}


@frappe.whitelist()
def get_stock_levels(
	company: str,
	low_stock_only: int = 0,
	search: str = None,
	warehouse: str = None,
	start: int = 0,
	page_length: int = 50,
):
	"""Bin is a standalone doctype (istable=0), so frappe.get_list works
	normally here -- unlike the child-table doctypes elsewhere in this file
	(Material Request Item, Stock Entry Detail, Purchase Order/Receipt
	Item), which all have an empty `permissions` list of their own and hit
	the same get_list field-collapse bug already documented in
	ppe_dashboard.py; confirmed Bin does NOT have that problem before
	relying on it here.

	"Low stock" = Bin.actual_qty below the configured per-warehouse
	Item Reorder level (`Item Reorder.warehouse_reorder_level`, the real
	ERPNext field for this -- Item itself has no plain scalar
	`reorder_level` field). NOTE (judgment call, confirmed against real
	data): this site has zero rows in `Item Reorder` and every Item's
	`safety_stock` is 0 -- no reorder threshold is configured anywhere, so
	the Low Stock flag is wired correctly but will show nothing until
	someone configures reorder levels. That's the honest, correct behavior
	for this feature on this dataset, not a bug.
	"""
	_check_dashboard_access()
	frappe.has_permission("Company", "read", company, throw=True)

	rose_clause, rose_params = _rose_exclusion("b.item_code")
	conditions = ["w.company = %s"]
	params = [company]

	join_reorder = """
		left join `tabItem Reorder` ir on ir.parent = b.item_code and ir.warehouse = b.warehouse
	"""
	if cint(low_stock_only):
		conditions.append("ir.warehouse_reorder_level > 0 and b.actual_qty < ir.warehouse_reorder_level")

	if search:
		like = f"%{search}%"
		conditions.append("(b.item_code like %s or it.item_name like %s)")
		params.extend([like, like])

	if warehouse:
		conditions.append("b.warehouse = %s")
		params.append(warehouse)

	where_sql = " and ".join(conditions) + rose_clause
	params.extend(rose_params)

	# `it` (Item) is joined unconditionally -- not just when `search` is
	# set -- so the `total` and `rows` queries below reference the exact
	# same FROM clause and stay consistent with each other.
	total = frappe.db.sql(
		f"""
		select count(*)
		from `tabBin` b
		inner join `tabWarehouse` w on w.name = b.warehouse
		inner join `tabItem` it on it.name = b.item_code
		{join_reorder}
		where {where_sql}
		""",
		tuple(params),
	)[0][0]

	rows = frappe.db.sql(
		f"""
		select
		    b.item_code, it.item_name, b.warehouse, b.actual_qty, b.valuation_rate, b.stock_value,
		    ir.warehouse_reorder_level,
		    (ir.warehouse_reorder_level > 0 and b.actual_qty < ir.warehouse_reorder_level) as is_low_stock
		from `tabBin` b
		inner join `tabWarehouse` w on w.name = b.warehouse
		inner join `tabItem` it on it.name = b.item_code
		{join_reorder}
		where {where_sql}
		order by b.stock_value desc
		limit %s offset %s
		""",
		(*params, cint(page_length), cint(start)),
		as_dict=True,
	)

	# Summary respects `warehouse` (a structural scope, like company) but
	# deliberately NOT `search`/`low_stock_only` (transient list filters) --
	# same reasoning as `by_warehouse` below, just also warehouse-aware so
	# selecting a warehouse gives a real "this warehouse's total value"
	# answer, not just the whole company's total again.
	summary_clause, summary_params = _rose_exclusion("b.item_code")
	summary_where = "w.company = %s"
	summary_sql_params = [company]
	if warehouse:
		summary_where += " and b.warehouse = %s"
		summary_sql_params.append(warehouse)
	summary = frappe.db.sql(
		f"""
		select
		    coalesce(sum(b.stock_value), 0) as total_value,
		    count(distinct b.item_code) as item_count,
		    sum(case when ir.warehouse_reorder_level > 0 and b.actual_qty < ir.warehouse_reorder_level then 1 else 0 end) as low_stock_count
		from `tabBin` b
		inner join `tabWarehouse` w on w.name = b.warehouse
		{join_reorder}
		where {summary_where}{summary_clause}
		""",
		(*summary_sql_params, *summary_params),
		as_dict=True,
	)[0]

	# Chart data for the tab: stock value + item count per warehouse, top
	# 10 by value. Scoped only to company + rose-exclusion -- deliberately
	# NOT re-filtered by the current search/low_stock_only list filters, so
	# the chart always reflects the whole company picture rather than
	# jumping around as the list filter changes.
	by_wh_clause, by_wh_params = _rose_exclusion("b.item_code")
	by_warehouse = frappe.db.sql(
		f"""
		select b.warehouse, coalesce(sum(b.stock_value), 0) as value, count(distinct b.item_code) as item_count
		from `tabBin` b
		inner join `tabWarehouse` w on w.name = b.warehouse
		where w.company = %s{by_wh_clause}
		group by b.warehouse
		order by value desc
		limit 10
		""",
		(company, *by_wh_params),
		as_dict=True,
	)
	for row in by_warehouse:
		row["value"] = flt(row.value)

	return {
		"rows": rows,
		"total": total,
		"summary": {
			"total_value": flt(summary.total_value),
			"item_count": summary.item_count,
			"low_stock_count": summary.low_stock_count,
		},
		"by_warehouse": by_warehouse,
	}


GROUP_BY_COLUMNS = {
	"Company": "se.company",
	"Business Unit": "sed.business_unit",
	"Farm": "sed.farm",
	"Cost Center": "sed.cost_center",
	"Expense Account": "sed.expense_account",
}


def _normalize_group_by(group_by):
	"""Accepts a list, a JSON-encoded list (as frappe.call sends an array
	arg), or a comma-separated string (defensive fallback), and returns a
	validated, non-empty list of GROUP_BY_COLUMNS keys. Falls back to
	["Company"] for anything empty/invalid rather than erroring -- "none
	checked" is a real, expected UI state, not a mistake."""
	if not group_by:
		return ["Company"]
	if isinstance(group_by, str):
		try:
			parsed = frappe.parse_json(group_by)
		except Exception:
			parsed = None
		if isinstance(parsed, list):
			group_by = parsed
		else:
			group_by = [g.strip() for g in group_by.split(",") if g.strip()]
	if not isinstance(group_by, list):
		return ["Company"]
	valid = [g for g in group_by if g in GROUP_BY_COLUMNS]
	return valid or ["Company"]


@frappe.whitelist()
def get_consumption(
	company: str,
	from_date: str = None,
	to_date: str = None,
	group_by=None,
	business_unit: str = None,
	farm: str = None,
	cost_center: str = None,
	expense_account: str = None,
):
	"""Stock Entry Detail joined to Stock Entry, scoped to
	EXCLUDED_STOCK_ENTRY_TYPES (the same shared denylist used everywhere
	else in this file -- per explicit user correction, this is deliberately
	broad: Milking, Egg Collection, Chemical Spray, Discard, etc. all count
	toward consumption value here, only Harvesting/Grading/Receiving/
	Packing/Dispatch are excluded).

	Uses `amount` (not `basic_amount`) as the valued consumption figure:
	`basic_amount` is qty * basic_rate before any additional/landed costs
	are allocated to the row, while `amount` includes those allocations and
	is what Stock Entry's own GL posting logic treats as the row's final
	valued amount (the two are equal whenever a row has no additional
	costs, so this never produces a *smaller* number than basic_amount
	would).

	`group_by` is a LIST of 1+ of Company/Business Unit/Farm/Cost Center/
	Expense Account (multi-select, per explicit user request) -- the
	breakdown is grouped by the combination of every checked dimension,
	using concat_ws(' / ', ...) to build a single composite label per
	combination. With exactly one dimension checked, concat_ws on a single
	argument just returns that value, so single-select behavior (the
	original v1 shape) falls out of the same code path unchanged.

	`business_unit`/`farm`/`cost_center`/`expense_account` are a SEPARATE
	feature from `group_by` -- value filters, not grouping dimensions.
	Narrows the query down to one specific value in that dimension first;
	whatever's left is then grouped by whichever dimension(s) `group_by`
	selected. Both apply together.
	"""
	_check_dashboard_access()
	frappe.has_permission("Company", "read", company, throw=True)

	group_bys = _normalize_group_by(group_by)
	group_cols = [GROUP_BY_COLUMNS[g] for g in group_bys]
	coalesced_cols = [f"coalesce({c}, '(Not Set)')" for c in group_cols]
	dimension_expr = f"concat_ws(' / ', {', '.join(coalesced_cols)})"
	group_by_sql = ", ".join(coalesced_cols)

	from_date = from_date or add_days(nowdate(), -30)
	to_date = to_date or nowdate()

	entry_type_placeholders = ", ".join(["%s"] * len(EXCLUDED_STOCK_ENTRY_TYPES))
	rose_clause, rose_params = _rose_exclusion("sed.item_code")

	value_filter_sql = ""
	value_filter_params = []
	if business_unit:
		value_filter_sql += " and sed.business_unit = %s"
		value_filter_params.append(business_unit)
	if farm:
		value_filter_sql += " and sed.farm = %s"
		value_filter_params.append(farm)
	if cost_center:
		value_filter_sql += " and sed.cost_center = %s"
		value_filter_params.append(cost_center)
	if expense_account:
		value_filter_sql += " and sed.expense_account = %s"
		value_filter_params.append(expense_account)

	base_where = f"""
		se.docstatus = 1 and se.company = %s
		and se.posting_date between %s and %s
		and se.stock_entry_type not in ({entry_type_placeholders}){rose_clause}{value_filter_sql}
	"""
	base_params = [company, from_date, to_date, *EXCLUDED_STOCK_ENTRY_TYPES, *rose_params, *value_filter_params]

	total_value = flt(
		frappe.db.sql(
			f"""
			select coalesce(sum(sed.amount), 0)
			from `tabStock Entry Detail` sed
			inner join `tabStock Entry` se on se.name = sed.parent
			where {base_where}
			""",
			tuple(base_params),
		)[0][0]
	)
	divisor = total_value or 1  # avoid /0 in share_pct below when the period has no consumption at all

	breakdown = frappe.db.sql(
		f"""
		select {dimension_expr} as dimension, coalesce(sum(sed.amount), 0) as value
		from `tabStock Entry Detail` sed
		inner join `tabStock Entry` se on se.name = sed.parent
		where {base_where}
		group by {group_by_sql}
		order by value desc
		limit 25
		""",
		tuple(base_params),
		as_dict=True,
	)
	for row in breakdown:
		row["value"] = flt(row.value)
		row["share_pct"] = min(100, (row.value / divisor) * 100)

	top_items = frappe.db.sql(
		f"""
		select sed.item_code, it.item_name, coalesce(sum(sed.amount), 0) as value, sum(sed.qty) as qty
		from `tabStock Entry Detail` sed
		inner join `tabStock Entry` se on se.name = sed.parent
		inner join `tabItem` it on it.name = sed.item_code
		where {base_where}
		group by sed.item_code, it.item_name
		order by value desc
		limit 10
		""",
		tuple(base_params),
		as_dict=True,
	)
	for row in top_items:
		row["value"] = flt(row.value)
		row["qty"] = flt(row.qty)

	return {
		"from_date": from_date,
		"to_date": to_date,
		"group_by": group_bys,
		"total_value": total_value,
		"breakdown": breakdown,
		"top_items": top_items,
	}


# ============================================================
# Drill-down detail views -- same pattern as the PPE dashboard's employee/
# request detail (frappe.set_route + on_page_show, a .hero header +
# .backbtn), reused here for Material Request / Stock Entry / Purchase
# Order / Purchase Receipt. Each still carries a stock_dash_doc_link to the
# real document for when the user wants to act on it (edit a draft, submit,
# etc.) -- the drill-down itself is read-only.
# ============================================================
@frappe.whitelist()
def get_material_request_detail(material_request: str):
	_check_dashboard_access()
	frappe.has_permission("Material Request", "read", material_request, throw=True)

	mr = frappe.db.get_value(
		"Material Request",
		material_request,
		[
			"name",
			"material_request_type",
			"status",
			"docstatus",
			"company",
			"transaction_date",
			"schedule_date",
			"per_ordered",
			"per_received",
		],
		as_dict=True,
	)
	if not mr:
		frappe.throw(_("Material Request {0} not found").format(material_request))

	# frappe.get_all, not frappe.get_list -- Material Request Item is a
	# child table with the same empty-`permissions` get_list field-collapse
	# bug documented on get_request_detail in ppe_dashboard.py. Access is
	# already gated by the has_permission check on the parent above.
	items = frappe.get_all(
		"Material Request Item",
		filters={"parent": material_request},
		fields=[
			"name",
			"item_code",
			"item_name",
			"qty",
			"employee",
			"employee_name",
			"cost_center",
			"warehouse",
			"issued_via_stock_entry",
			"qty_issued",
		],
		order_by="idx asc",
	)
	for row in items:
		# Per-row fulfillment only has a clean meaning for Material Issue/
		# Transfer rows (issued_via_stock_entry) -- Purchase/Manufacture
		# fulfillment is tracked at the header level (per_ordered) instead,
		# so leave it unset rather than implying a row-level signal that
		# doesn't really exist for those two types.
		if mr.material_request_type in ("Material Issue", "Material Transfer"):
			row["is_fulfilled"] = bool(row.issued_via_stock_entry)
		else:
			row["is_fulfilled"] = None

	return {"request": mr, "items": items}


@frappe.whitelist()
def get_stock_entry_detail(stock_entry: str):
	_check_dashboard_access()
	frappe.has_permission("Stock Entry", "read", stock_entry, throw=True)

	se = frappe.db.get_value(
		"Stock Entry",
		stock_entry,
		["name", "stock_entry_type", "posting_date", "company", "docstatus", "from_warehouse", "to_warehouse", "total_amount"],
		as_dict=True,
	)
	if not se:
		frappe.throw(_("Stock Entry {0} not found").format(stock_entry))

	# frappe.get_all -- same child-table reasoning as above; access already
	# gated by the has_permission check on the parent Stock Entry.
	items = frappe.get_all(
		"Stock Entry Detail",
		filters={"parent": stock_entry},
		fields=[
			"item_code",
			"item_name",
			"qty",
			"basic_rate",
			"amount",
			"cost_center",
			"expense_account",
			"farm",
			"business_unit",
			"s_warehouse",
			"t_warehouse",
			"material_request",
		],
		order_by="idx asc",
	)
	# A Stock Entry's rows can in principle point at different Material
	# Requests; in practice every real one created via the "Create" button
	# carries the same one on every row, so the first non-empty value is a
	# reasonable single "linked request" for the header -- the per-row
	# material_request is still returned too, for completeness.
	material_request = next((row.material_request for row in items if row.material_request), None)

	return {"entry": se, "items": items, "material_request": material_request}


@frappe.whitelist()
def get_purchase_order_detail(purchase_order: str):
	_check_dashboard_access()
	frappe.has_permission("Purchase Order", "read", purchase_order, throw=True)

	po = frappe.db.get_value(
		"Purchase Order",
		purchase_order,
		[
			"name",
			"supplier",
			"status",
			"docstatus",
			"company",
			"transaction_date",
			"schedule_date",
			"grand_total",
			"per_received",
			"per_billed",
		],
		as_dict=True,
	)
	if not po:
		frappe.throw(_("Purchase Order {0} not found").format(purchase_order))

	items = frappe.get_all(
		"Purchase Order Item",
		filters={"parent": purchase_order},
		fields=["item_code", "item_name", "qty", "rate", "amount", "material_request", "received_qty"],
		order_by="idx asc",
	)

	# Every Purchase Receipt made against this PO, not just the latest one
	# (get_procurement's own po_list only keeps the most recent, which is
	# enough for a one-line funnel summary but not for a real drill-down
	# that should show the full receiving history).
	receipts = frappe.db.sql(
		"""
		select distinct pr.name, pr.posting_date, pr.status, pr.grand_total
		from `tabPurchase Receipt Item` pri
		inner join `tabPurchase Receipt` pr on pr.name = pri.parent and pr.docstatus = 1
		where pri.purchase_order = %s
		order by pr.posting_date desc
		""",
		(purchase_order,),
		as_dict=True,
	)

	material_request = next((row.material_request for row in items if row.material_request), None)

	return {"order": po, "items": items, "receipts": receipts, "material_request": material_request}


@frappe.whitelist()
def get_purchase_receipt_detail(purchase_receipt: str):
	_check_dashboard_access()
	frappe.has_permission("Purchase Receipt", "read", purchase_receipt, throw=True)

	pr = frappe.db.get_value(
		"Purchase Receipt",
		purchase_receipt,
		["name", "supplier", "status", "docstatus", "company", "posting_date", "grand_total", "per_billed"],
		as_dict=True,
	)
	if not pr:
		frappe.throw(_("Purchase Receipt {0} not found").format(purchase_receipt))

	items = frappe.get_all(
		"Purchase Receipt Item",
		filters={"parent": purchase_receipt},
		fields=["item_code", "item_name", "qty", "rate", "amount", "warehouse", "purchase_order", "material_request"],
		order_by="idx asc",
	)
	purchase_order = next((row.purchase_order for row in items if row.purchase_order), None)
	material_request = next((row.material_request for row in items if row.material_request), None)

	return {
		"receipt": pr,
		"items": items,
		"purchase_order": purchase_order,
		"material_request": material_request,
	}


# ============================================================
# Overview tab charts
# ============================================================
@frappe.whitelist()
def get_overview_charts(company: str):
	"""Loaded as a second, separate call after the Overview tab's main KPIs
	(see get_overview) -- kept as its own method rather than folded into
	get_overview so the KPI tiles can render before these two chart queries
	(which touch Stock Entry Detail at the same scale already flagged as
	slow in the previous round) finish."""
	_check_dashboard_access()
	frappe.has_permission("Company", "read", company, throw=True)

	entry_type_placeholders = ", ".join(["%s"] * len(EXCLUDED_STOCK_ENTRY_TYPES))
	type_breakdown = frappe.db.sql(
		f"""
		select stock_entry_type, count(*) as count
		from `tabStock Entry`
		where company = %s and docstatus = 1
		  and stock_entry_type not in ({entry_type_placeholders})
		group by stock_entry_type
		order by count desc
		limit 10
		""",
		(company, *EXCLUDED_STOCK_ENTRY_TYPES),
		as_dict=True,
	)

	# Weekly consumption trend, last 8 weeks. yearweek(..., 3) is ISO week
	# numbering (Monday-based, matches how most people mentally group
	# weeks) -- used only to GROUP BY distinct weeks; week_start (the
	# earliest posting_date in that week's bucket) is what's actually shown
	# as the axis label.
	rose_clause, rose_params = _rose_exclusion("sed.item_code")
	period_start = add_days(nowdate(), -7 * 8)
	weekly = frappe.db.sql(
		f"""
		select yearweek(se.posting_date, 3) as yw, min(se.posting_date) as week_start,
		       coalesce(sum(sed.amount), 0) as value
		from `tabStock Entry Detail` sed
		inner join `tabStock Entry` se on se.name = sed.parent and se.docstatus = 1
		where se.company = %s and se.posting_date >= %s
		  and se.stock_entry_type not in ({entry_type_placeholders}){rose_clause}
		group by yearweek(se.posting_date, 3)
		order by yw asc
		""",
		(company, period_start, *EXCLUDED_STOCK_ENTRY_TYPES, *rose_params),
		as_dict=True,
	)
	for row in weekly:
		row["value"] = flt(row.value)

	return {"type_breakdown": type_breakdown, "weekly_consumption": weekly}


# ============================================================
# Tab 7: Inventory Health (new -- see get_inventory_health's own docstring
# for the exact scoring formula and thresholds, which are a judgment call
# and easy to retune).
# ============================================================
@frappe.whitelist()
def get_inventory_health(company: str):
	"""Scores every non-rose item+warehouse balance (Bin row) for this
	company into 4 buckets -- Excellent / Good / Watch / Critical --
	inspired by a pattern on the reference Kaitet Group "Stores &
	Inventory" dashboard (described to me, not available for me to inspect
	directly; built here from data already on hand). Two signals, both
	documented explicitly so the thresholds can be retuned later without
	spelunking through the query:

	  1. days_since_last_movement -- days since the most recent
	     stock-module Stock Entry (the same EXCLUDED_STOCK_ENTRY_TYPES
	     denylist used everywhere else in this file) touched this item in
	     this warehouse, via either side of the move. Uses Stock Entry
	     Detail's own s_warehouse/t_warehouse (not the Stock Entry header's
	     from_warehouse/to_warehouse), since one multi-row Stock Entry can
	     move different items through different warehouses per row. An
	     item+warehouse with no stock-module movement ever recorded gets
	     treated as age 999 (worst case).
	  2. actual_qty -- zero or negative stock is always Critical regardless
	     of recency, since it's an immediate, visible problem on its own.

	Buckets (exact thresholds -- a judgment call, state in review if these
	feel off and they're trivial to retune):
	    Critical:  actual_qty <= 0, OR no movement ever recorded,
	               OR last movement more than 180 days ago.
	    Watch:     last movement 91-180 days ago.
	    Good:      last movement 31-90 days ago.
	    Excellent: actual_qty > 0 and last movement within 30 days.

	Deliberately does NOT also factor in qty-vs-typical-consumption-rate --
	the brief allowed either signal; the age+zero-qty pair alone is already
	a defensible, cheap-to-explain score without a second heavy aggregation
	stacked on top of the one below (itself already the same class of
	query flagged as slow in the previous round -- performance work on
	this tab is explicitly deferred, same as everywhere else, but this
	query is written straightforwardly rather than pessimized further).
	"""
	_check_dashboard_access()
	frappe.has_permission("Company", "read", company, throw=True)

	rose_clause, rose_params = _rose_exclusion("b.item_code")
	entry_type_placeholders = ", ".join(["%s"] * len(EXCLUDED_STOCK_ENTRY_TYPES))

	rows = frappe.db.sql(
		f"""
		select
		    b.item_code, it.item_name, b.warehouse, b.actual_qty, b.stock_value,
		    lm.last_movement
		from `tabBin` b
		inner join `tabWarehouse` w on w.name = b.warehouse
		inner join `tabItem` it on it.name = b.item_code
		left join (
		    select item_code, warehouse, max(posting_date) as last_movement
		    from (
		        select sed.item_code, sed.s_warehouse as warehouse, se.posting_date
		        from `tabStock Entry Detail` sed
		        inner join `tabStock Entry` se on se.name = sed.parent and se.docstatus = 1
		        where se.stock_entry_type not in ({entry_type_placeholders})
		          and sed.s_warehouse is not null and sed.s_warehouse != ''
		        union all
		        select sed.item_code, sed.t_warehouse as warehouse, se.posting_date
		        from `tabStock Entry Detail` sed
		        inner join `tabStock Entry` se on se.name = sed.parent and se.docstatus = 1
		        where se.stock_entry_type not in ({entry_type_placeholders})
		          and sed.t_warehouse is not null and sed.t_warehouse != ''
		    ) moves
		    group by item_code, warehouse
		) lm on lm.item_code = b.item_code and lm.warehouse = b.warehouse
		where w.company = %s{rose_clause}
		""",
		(*EXCLUDED_STOCK_ENTRY_TYPES, *EXCLUDED_STOCK_ENTRY_TYPES, company, *rose_params),
		as_dict=True,
	)

	today = getdate(nowdate())
	bucket_counts = {"Excellent": 0, "Good": 0, "Watch": 0, "Critical": 0}
	scored = []
	for row in rows:
		age = (today - getdate(row.last_movement)).days if row.last_movement else 999
		qty = flt(row.actual_qty)
		if qty <= 0 or age > 180:
			bucket = "Critical"
		elif age > 90:
			bucket = "Watch"
		elif age > 30:
			bucket = "Good"
		else:
			bucket = "Excellent"
		bucket_counts[bucket] += 1
		row["age_days"] = age
		row["bucket"] = bucket
		row["actual_qty"] = qty
		row["stock_value"] = flt(row.stock_value)
		if bucket in ("Critical", "Watch"):
			scored.append(row)

	bucket_rank = {"Critical": 0, "Watch": 1}
	scored.sort(key=lambda r: (bucket_rank[r["bucket"]], -r["age_days"], r["actual_qty"]))

	return {"bucket_counts": bucket_counts, "worst_items": scored[:20], "total_items": len(rows)}


# ============================================================
# Tab 8: Approvals (new) -- draft (docstatus=0) documents across the 4 main
# stock-module doctypes, so stale forgotten drafts don't get lost. Rows
# link directly to the real ERPNext document (stock_dash_doc_link), not the
# new drill-down views -- a draft needs editing/submitting, not a read-only
# detail page.
# ============================================================
@frappe.whitelist()
def get_approvals(company: str, search: str = None):
	_check_dashboard_access()
	frappe.has_permission("Company", "read", company, throw=True)

	like = f"%{search}%" if search else None

	mri_clause, mri_params = _rose_exclusion("mri.item_code")
	mr_conditions = [
		"mr.company = %s",
		"mr.docstatus = 0",
		f"exists (select 1 from `tabMaterial Request Item` mri where mri.parent = mr.name{mri_clause})",
	]
	mr_params = [company, *mri_params]
	if like:
		mr_conditions.append("mr.name like %s")
		mr_params.append(like)
	mr_where = " and ".join(mr_conditions)
	mr_total = frappe.db.sql(f"select count(*) from `tabMaterial Request` mr where {mr_where}", tuple(mr_params))[0][0]
	material_requests = frappe.db.sql(
		f"""
		select mr.name, mr.material_request_type, mr.company, mr.transaction_date,
		       datediff(curdate(), date(mr.creation)) as age_days, mr.owner
		from `tabMaterial Request` mr
		where {mr_where}
		order by mr.creation asc
		limit 50
		""",
		tuple(mr_params),
		as_dict=True,
	)

	poi_clause, poi_params = _rose_exclusion("poi.item_code")
	po_conditions = [
		"po.company = %s",
		"po.docstatus = 0",
		f"exists (select 1 from `tabPurchase Order Item` poi where poi.parent = po.name{poi_clause})",
	]
	po_params = [company, *poi_params]
	if like:
		po_conditions.append("(po.name like %s or po.supplier like %s)")
		po_params.extend([like, like])
	po_where = " and ".join(po_conditions)
	po_total = frappe.db.sql(f"select count(*) from `tabPurchase Order` po where {po_where}", tuple(po_params))[0][0]
	purchase_orders = frappe.db.sql(
		f"""
		select po.name, po.supplier, po.company, po.transaction_date,
		       datediff(curdate(), date(po.creation)) as age_days, po.owner
		from `tabPurchase Order` po
		where {po_where}
		order by po.creation asc
		limit 50
		""",
		tuple(po_params),
		as_dict=True,
	)

	# Stock Entry needs a different query shape from the other 3 doctypes
	# here: it's a 3.96M-row table with no index on docstatus or company, and
	# -- confirmed by direct EXPLAIN/timing during verification -- combining
	# that full scan with a correlated `exists (... item_code not in
	# (subquery))` rose-exclusion check (the same shape used for the other
	# 3, which are tiny tables and stay fast with it) produces a query that
	# never completes (tested: still running past 4 minutes). Fixed by
	# splitting into two cheap steps instead of one expensive correlated
	# one: first the small set of draft Stock Entries themselves (still a
	# genuine full-table-scan cost, same category as this file's other
	# already-flagged-slow queries, but bounded -- confirmed ~25s, not a
	# hang), then a plain join (not a correlated NOT IN) against that small
	# candidate set to find which ones have a non-rose item row. Same rose
	# exclusion semantics as everywhere else in this file, just restructured
	# to avoid the specific plan MySQL was choosing for it here.
	se_conditions = ["se.company = %s", "se.docstatus = 0"]
	se_params = [company]
	if like:
		se_conditions.append("se.name like %s")
		se_params.append(like)
	se_where = " and ".join(se_conditions)
	se_candidates = frappe.db.sql(
		f"""
		select se.name, se.stock_entry_type, se.company, se.posting_date,
		       datediff(curdate(), date(se.creation)) as age_days, se.owner
		from `tabStock Entry` se
		where {se_where}
		order by se.creation asc
		""",
		tuple(se_params),
		as_dict=True,
	)

	rose_groups = _rose_item_groups()
	if se_candidates and rose_groups:
		candidate_names = [row.name for row in se_candidates]
		placeholders = ", ".join(["%s"] * len(rose_groups))
		non_rose_names = set(
			frappe.db.sql_list(
				f"""
				select distinct sed.parent
				from `tabStock Entry Detail` sed
				inner join `tabItem` it on it.name = sed.item_code
				where sed.parent in %s and it.item_group not in ({placeholders})
				""",
				(candidate_names, *rose_groups),
			)
		)
		se_candidates = [row for row in se_candidates if row.name in non_rose_names]

	se_total = len(se_candidates)
	stock_entries = se_candidates[:50]

	pri_clause, pri_params = _rose_exclusion("pri.item_code")
	pr_conditions = [
		"pr.company = %s",
		"pr.docstatus = 0",
		f"exists (select 1 from `tabPurchase Receipt Item` pri where pri.parent = pr.name{pri_clause})",
	]
	pr_params = [company, *pri_params]
	if like:
		pr_conditions.append("(pr.name like %s or pr.supplier like %s)")
		pr_params.extend([like, like])
	pr_where = " and ".join(pr_conditions)
	pr_total = frappe.db.sql(f"select count(*) from `tabPurchase Receipt` pr where {pr_where}", tuple(pr_params))[0][0]
	purchase_receipts = frappe.db.sql(
		f"""
		select pr.name, pr.supplier, pr.company, pr.posting_date,
		       datediff(curdate(), date(pr.creation)) as age_days, pr.owner
		from `tabPurchase Receipt` pr
		where {pr_where}
		order by pr.creation asc
		limit 50
		""",
		tuple(pr_params),
		as_dict=True,
	)

	return {
		"counts": {
			"total_pending": mr_total + po_total + se_total + pr_total,
			"draft_material_requests": mr_total,
			"draft_purchase_orders": po_total,
			"draft_stock_entries": se_total,
			"draft_purchase_receipts": pr_total,
		},
		"material_requests": material_requests,
		"purchase_orders": purchase_orders,
		"stock_entries": stock_entries,
		"purchase_receipts": purchase_receipts,
	}


# ============================================================
# Company-scoped dropdown filter population -- Farm/Business Unit/Cost
# Center/Warehouse all carry a direct `company` field (confirmed against
# real schema before writing these); Expense Account deliberately does NOT
# list the full chart of accounts (could be hundreds of mostly-irrelevant
# GL accounts) -- it lists only accounts actually used by this company's
# own stock-module Stock Entry Detail rows (same EXCLUDED_STOCK_ENTRY_TYPES
# denylist + rose exclusion as everywhere else in this file).
# ============================================================
@frappe.whitelist()
def get_farms(company: str):
	_check_dashboard_access()
	frappe.has_permission("Company", "read", company, throw=True)
	return frappe.get_list(
		"Farm", filters={"company": company}, fields=["name", "farm_name"], order_by="farm_name asc"
	)


@frappe.whitelist()
def get_business_units(company: str):
	_check_dashboard_access()
	frappe.has_permission("Company", "read", company, throw=True)
	return frappe.get_list("Business Unit", filters={"company": company}, fields=["name"], order_by="name asc")


@frappe.whitelist()
def get_cost_centers(company: str):
	"""is_group=0 only -- a group/parent Cost Center is a tree node, not a
	valid value any real transaction is ever posted against, same reasoning
	as never offering a non-leaf Item Group as a filterable value."""
	_check_dashboard_access()
	frappe.has_permission("Company", "read", company, throw=True)
	return frappe.get_list(
		"Cost Center",
		filters={"company": company, "is_group": 0},
		fields=["name", "cost_center_name"],
		order_by="cost_center_name asc",
	)


@frappe.whitelist()
def get_warehouses(company: str):
	"""is_group=0 only, same reasoning as get_cost_centers -- a group
	Warehouse can't itself hold a Bin balance, so it's never a meaningful
	filter value for the Stock Levels tab."""
	_check_dashboard_access()
	frappe.has_permission("Company", "read", company, throw=True)
	return frappe.get_list(
		"Warehouse",
		filters={"company": company, "is_group": 0},
		fields=["name", "warehouse_name"],
		order_by="warehouse_name asc",
	)


@frappe.whitelist()
def get_consumption_expense_accounts(company: str):
	_check_dashboard_access()
	frappe.has_permission("Company", "read", company, throw=True)

	entry_type_placeholders = ", ".join(["%s"] * len(EXCLUDED_STOCK_ENTRY_TYPES))
	rose_clause, rose_params = _rose_exclusion("sed.item_code")
	rows = frappe.db.sql(
		f"""
		select distinct sed.expense_account
		from `tabStock Entry Detail` sed
		inner join `tabStock Entry` se on se.name = sed.parent and se.docstatus = 1
		where se.company = %s and se.stock_entry_type not in ({entry_type_placeholders}){rose_clause}
		  and sed.expense_account is not null and sed.expense_account != ''
		order by sed.expense_account asc
		""",
		(company, *EXCLUDED_STOCK_ENTRY_TYPES, *rose_params),
	)
	return [row[0] for row in rows]


# ============================================================
# Tab 9: Suppliers (new)
# ============================================================
@frappe.whitelist()
def get_suppliers(company: str, search: str = None, start: int = 0, page_length: int = 50):
	"""One row per supplier with at least one non-rose Purchase Order for
	this company, scoped the same way get_procurement's own Purchase Order
	list is (PO -> Purchase Order Item -> Material Request, material_request_type
	= 'Purchase' -- "same rose-exclusion as Procurement" means the same
	overall scope, not just the item-group filter in isolation). Average
	lead time (submission -> full receipt) is computed only for the page's
	own suppliers, as a second small query against the already-narrow
	per-supplier PO set -- not a third full scan."""
	_check_dashboard_access()
	frappe.has_permission("Company", "read", company, throw=True)

	poi_clause, poi_params = _rose_exclusion("poi.item_code")
	conditions = [
		"po.company = %s",
		"po.docstatus = 1",
		"mr.material_request_type = 'Purchase'",
		f"exists (select 1 from `tabPurchase Order Item` poi where poi.parent = po.name{poi_clause})",
	]
	params = [company, *poi_params]
	if search:
		conditions.append("po.supplier like %s")
		params.append(f"%{search}%")
	where_sql = " and ".join(conditions)

	# distinct is over supplier, via the PO/MR join -- a PO can have several
	# item rows against the same material_request, so de-dup at the PO
	# level first via a derived table rather than risking a join fan-out
	# inflating po_count/total_value.
	base_pos = f"""
		select distinct po.name, po.supplier, po.grand_total, po.per_received
		from `tabPurchase Order` po
		inner join `tabPurchase Order Item` poi2 on poi2.parent = po.name
		inner join `tabMaterial Request` mr on mr.name = poi2.material_request
		where {where_sql}
	"""

	total = frappe.db.sql(
		f"select count(distinct supplier) from ({base_pos}) x", tuple(params)
	)[0][0]

	rows = frappe.db.sql(
		f"""
		select
		    supplier,
		    count(*) as po_count,
		    coalesce(sum(grand_total), 0) as total_value,
		    sum(case when per_received >= 100 then 1 else 0 end) as fully_received_count,
		    sum(case when per_received < 100 then 1 else 0 end) as pending_count
		from ({base_pos}) x
		group by supplier
		order by total_value desc
		limit %s offset %s
		""",
		(*params, cint(page_length), cint(start)),
		as_dict=True,
	)

	if rows:
		suppliers_on_page = [row.supplier for row in rows]
		placeholders = ", ".join(["%s"] * len(suppliers_on_page))
		lead_rows = frappe.db.sql(
			f"""
			select po.supplier, avg(datediff(last_receipt.max_date, po.transaction_date)) as avg_lead_days
			from `tabPurchase Order` po
			inner join (
			    select pri.purchase_order, max(pr.posting_date) as max_date
			    from `tabPurchase Receipt Item` pri
			    inner join `tabPurchase Receipt` pr on pr.name = pri.parent and pr.docstatus = 1
			    group by pri.purchase_order
			) last_receipt on last_receipt.purchase_order = po.name
			where po.company = %s and po.docstatus = 1 and po.per_received >= 100
			  and po.supplier in ({placeholders})
			group by po.supplier
			""",
			(company, *suppliers_on_page),
			as_dict=True,
		)
		lead_map = {row.supplier: row.avg_lead_days for row in lead_rows}
		for row in rows:
			row["total_value"] = flt(row.total_value)
			avg_lead = lead_map.get(row.supplier)
			row["avg_lead_days"] = flt(avg_lead) if avg_lead is not None else None

	return {"rows": rows, "total": total}
