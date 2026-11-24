import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, nowdate

# Status colors mirror Employee PPE Assignment's own "states" (Green/Red/
# Yellow/Blue) plus a neutral grey for "Inactive", which that doctype's
# states list doesn't cover.
STATUS_COLORS = {
	"Active": "#1a8a3a",
	"Expired": "#c4302b",
	"Returned": "#f59e0b",
	"Replaced": "#2563eb",
	"Inactive": "#8a8780",
}

ASSIGNMENT_STATUSES = ["Active", "Inactive", "Expired", "Returned", "Replaced"]

# The Page doctype's own `roles` list only gates whether the page shows up
# in Desk -- it does NOT restrict these whitelisted methods, which are
# reachable directly via /api/method/... by any authenticated user
# regardless of role. Every method below must call _check_dashboard_access()
# first, matching the explicit frappe.throw(..., frappe.PermissionError)
# style already used in upande_stores/api/ppe.py rather than relying on a
# framework helper.
ALLOWED_ROLES = {"System Manager", "HR Manager", "Farm Manager", "Stock Manager", "Stock User"}


def _check_dashboard_access():
	if not set(frappe.get_roles()) & ALLOWED_ROLES:
		frappe.throw(_("Not permitted to view the PPE Dashboard."), frappe.PermissionError)


def _upande_hr_installed() -> bool:
	return "upande_hr" in frappe.get_installed_apps()


@frappe.whitelist()
def get_companies():
	"""Companies to offer in the switcher: every company that has at least
	one Employee PPE Assignment, plus the current user's default company
	(frappe.defaults.get_user_default, which reads the user's default
	Company User Permission / Global Defaults) even if that company has no
	PPE data yet -- the page just renders zeros for it, per spec."""
	_check_dashboard_access()
	companies = frappe.get_list(
		"Employee PPE Assignment",
		fields=["company"],
		distinct=True,
		filters={"company": ["is", "set"]},
		order_by="company asc",
		pluck="company",
	)
	default_company = frappe.defaults.get_user_default("Company")
	return {"companies": companies, "default_company": default_company}


@frappe.whitelist()
def get_overview(company: str):
	_check_dashboard_access()
	frappe.has_permission("Company", "read", company, throw=True)

	today = nowdate()
	expiry_cutoff = add_days(today, 30)

	active_count = frappe.db.count(
		"Employee PPE Assignment", {"status": "Active", "company": company}
	)
	expiring_count = frappe.db.count(
		"Employee PPE Assignment",
		{
			"status": "Active",
			"company": company,
			"expiry_date": ["between", [today, expiry_cutoff]],
		},
	)

	status_rows = frappe.db.sql(
		"""
		select status, count(*) as count
		from `tabEmployee PPE Assignment`
		where company = %s
		group by status
		""",
		(company,),
		as_dict=True,
	)
	status_map = {row.status: row.count for row in status_rows}
	status_breakdown = [
		{"status": s, "count": status_map.get(s, 0), "color": STATUS_COLORS.get(s, "#8a8780")}
		for s in ASSIGNMENT_STATUSES
	]

	# "Pending" issuance requests: a submitted Material Issue PPE request
	# where at least one item row hasn't yet been recorded as issued.
	# per_ordered doesn't apply here -- it tracks conversion to Purchase
	# Order, which never happens for a Material Issue request, so it stays
	# 0 regardless of actual issuance. issued_via_stock_entry (set by
	# overrides/stock_entry.py's lock_issued_employee once a row's
	# qty_issued reaches qty) is the real signal.
	pending_issuance = frappe.db.sql(
		"""
		select count(distinct mr.name)
		from `tabMaterial Request` mr
		where mr.material_request_type = 'Material Issue'
		  and mr.custom_ppe_issuance = 1
		  and mr.company = %s
		  and mr.docstatus = 1
		  and exists (
		      select 1 from `tabMaterial Request Item` mri
		      where mri.parent = mr.name
		        and (mri.issued_via_stock_entry is null or mri.issued_via_stock_entry = '')
		  )
		""",
		(company,),
	)[0][0]

	# Pending PPE purchase requests. NOTE (judgment call): the brief's
	# `custom_purpose = "PPE Issuing"` match doesn't hold against real data
	# -- custom_purpose is a free-text "Purpose" field used across all of
	# upande_stores for every Material Request Item (diesel, droppers,
	# fencing, ...), not a fixed-option field, and the exact string "PPE
	# Issuing"/"PPE Issiing" doesn't appear verbatim. Used Item.custom_is_ppe
	# instead -- the same flag overrides/stock_entry.py's
	# create_ppe_assignments() already treats as the canonical "this is a
	# PPE item" signal -- joined through Material Request Item.item_code.
	pending_purchase = frappe.db.sql(
		"""
		select count(distinct mr.name)
		from `tabMaterial Request` mr
		where mr.material_request_type = 'Purchase'
		  and mr.company = %s
		  and mr.docstatus = 1
		  and mr.per_ordered < 100
		  and exists (
		      select 1 from `tabMaterial Request Item` mri
		      inner join `tabItem` it on it.name = mri.item_code
		      where mri.parent = mr.name and it.custom_is_ppe = 1
		  )
		""",
		(company,),
	)[0][0]

	# Last-90-days PPE spend: Purchase Receipt Item.base_amount for rows
	# whose own item is a PPE item (same Item.custom_is_ppe signal as
	# above), on submitted receipts for this company.
	spend = frappe.db.sql(
		"""
		select coalesce(sum(pri.base_amount), 0)
		from `tabPurchase Receipt Item` pri
		inner join `tabPurchase Receipt` pr on pr.name = pri.parent and pr.docstatus = 1
		inner join `tabItem` it on it.name = pri.item_code
		where pr.company = %s
		  and pr.posting_date >= %s
		  and it.custom_is_ppe = 1
		""",
		(company, add_days(today, -90)),
	)[0][0]

	return {
		"active_assignments": active_count,
		"expiring_30d": expiring_count,
		"pending_issuance": pending_issuance,
		"pending_purchase": pending_purchase,
		"period_spend": flt(spend),
		"status_breakdown": status_breakdown,
	}


@frappe.whitelist()
def get_assignments(company: str, status: str = None, start: int = 0, page_length: int = 50):
	"""Filtering and pagination both happen server-side -- Karen Roses alone
	has ~5,600 Employee PPE Assignments (1179 Active + 203 Inactive + 4214
	Expired + 1 Replaced), so a single capped client-side fetch followed by
	client-side `.filter()` was both incomplete (never showed ~98% of the
	data) and misleading (a status pill's count reflected only whatever
	fraction of the truncated page happened to match, not the real total)."""
	_check_dashboard_access()
	frappe.has_permission("Company", "read", company, throw=True)

	filters = {"company": company}
	if status and status != "All":
		filters["status"] = status

	total = frappe.db.count("Employee PPE Assignment", filters)
	rows = frappe.get_list(
		"Employee PPE Assignment",
		filters=filters,
		fields=[
			"name",
			"employee",
			"employee_name",
			"item_code",
			"item_name",
			"status",
			"issue_date",
			"expiry_date",
			"quantity",
			"cost_center",
		],
		order_by="creation desc",
		limit_start=cint(start),
		limit_page_length=cint(page_length),
	)
	return {"rows": rows, "total": total}


@frappe.whitelist()
def get_employee_detail(employee: str):
	_check_dashboard_access()
	frappe.has_permission("Employee", "read", employee, throw=True)

	emp = frappe.db.get_value(
		"Employee",
		employee,
		["name", "employee_name", "company", "department", "designation", "status"],
		as_dict=True,
	)
	if not emp:
		frappe.throw(_("Employee {0} not found").format(employee))

	if _upande_hr_installed():
		# Employee PPE History is upande_hr's own child table on Employee,
		# kept in sync by Employee PPE Assignment.on_update/_sync_history_row
		# -- read it when the app is installed so this matches whatever the
		# HR side actually shows the employee.
		# frappe.get_list (not frappe.get_all) deliberately everywhere else in
		# this file, per the fix for the IDOR review finding -- EXCEPT here.
		# Verified against real data: Employee PPE History is a child table
		# (istable=1) with an empty `permissions` list of its own, and
		# frappe.get_list's field-level permission filtering -- correct,
		# wanted behavior for a real standalone doctype -- silently collapses
		# the requested `fields` down to just `name` for a childtable with no
		# permission rows, returning every other column as None instead of
		# erroring. That's not "less filtered", it's broken: the whole
		# Employee detail view would render blank. Access to these rows is
		# already gated the same way Frappe's own form loader gates a
		# document's child tables: by the has_permission("Employee", "read",
		# employee, throw=True) check above, not by permission-filtering the
		# child rows themselves.
		history_rows = frappe.get_all(
			"Employee PPE History",
			filters={"parent": employee, "parenttype": "Employee"},
			fields=[
				"ppe_assignment",
				"item_code",
				"quantity",
				"issue_date",
				"expiry_date",
				"status",
				"stock_entry",
			],
			order_by="issue_date desc, creation desc",
		)
		assignment_names = [row.ppe_assignment for row in history_rows if row.ppe_assignment]
		extra_map = {}
		if assignment_names:
			extra_rows = frappe.get_list(
				"Employee PPE Assignment",
				filters={"name": ["in", assignment_names]},
				fields=["name", "item_name", "replacement_assignment"],
			)
			extra_map = {row.name: row for row in extra_rows}
		history = []
		for row in history_rows:
			extra = extra_map.get(row.ppe_assignment)
			history.append(
				{
					"name": row.ppe_assignment,
					"item_code": row.item_code,
					"item_name": (extra.item_name if extra else row.item_code),
					"quantity": row.quantity,
					"issue_date": row.issue_date,
					"expiry_date": row.expiry_date,
					"status": row.status,
					"stock_entry": row.stock_entry,
					"replacement_assignment": (extra.replacement_assignment if extra else None),
				}
			)
	else:
		# Fall back to Employee PPE Assignment directly, same guard pattern
		# used throughout employee_ppe_assignment.py / overrides/stock_entry.py.
		history = frappe.get_list(
			"Employee PPE Assignment",
			filters={"employee": employee},
			fields=[
				"name",
				"item_code",
				"item_name",
				"quantity",
				"issue_date",
				"expiry_date",
				"status",
				"stock_entry",
				"replacement_assignment",
			],
			order_by="issue_date desc, creation desc",
		)

	total_assignments = len(history)
	active_count = sum(1 for row in history if row.get("status") == "Active")
	expired_count = sum(1 for row in history if row.get("status") == "Expired")

	return {
		"employee": emp,
		"history": history,
		"total_assignments": total_assignments,
		"active_count": active_count,
		"expired_count": expired_count,
	}


@frappe.whitelist()
def get_requests(company: str):
	_check_dashboard_access()
	# Not explicitly called out in the brief's per-method list, but this
	# method takes the same `company` arg and returns the same kind of
	# cross-company-sensitive data (employee names on issuance requests) as
	# get_overview/get_assignments/get_procurement, so the same check
	# applies here for the same reason.
	frappe.has_permission("Company", "read", company, throw=True)

	issuance = frappe.db.sql(
		"""
		select
		    mr.name,
		    mr.transaction_date,
		    mr.status,
		    mr.docstatus,
		    count(mri.name) as item_count,
		    sum(
		        case when mri.issued_via_stock_entry is not null and mri.issued_via_stock_entry != ''
		        then 1 else 0 end
		    ) as issued_item_count,
		    group_concat(distinct nullif(mri.employee_name, '') separator ', ') as employees
		from `tabMaterial Request` mr
		inner join `tabMaterial Request Item` mri on mri.parent = mr.name
		where mr.material_request_type = 'Material Issue'
		  and mr.custom_ppe_issuance = 1
		  and mr.company = %s
		group by mr.name
		order by mr.creation desc
		limit 200
		""",
		(company,),
		as_dict=True,
	)
	for row in issuance:
		row["fully_issued"] = bool(row["item_count"]) and row["item_count"] == row["issued_item_count"]

	purchase = frappe.db.sql(
		"""
		select distinct
		    mr.name, mr.transaction_date, mr.status, mr.docstatus, mr.per_ordered, mr.per_received
		from `tabMaterial Request` mr
		inner join `tabMaterial Request Item` mri on mri.parent = mr.name
		inner join `tabItem` it on it.name = mri.item_code
		where mr.material_request_type = 'Purchase'
		  and mr.company = %s
		  and it.custom_is_ppe = 1
		order by mr.creation desc
		limit 200
		""",
		(company,),
		as_dict=True,
	)
	if purchase:
		names = [row.name for row in purchase]
		counts = frappe.db.sql(
			"""
			select parent, count(*) as item_count
			from `tabMaterial Request Item`
			where parent in %s
			group by parent
			""",
			(names,),
			as_dict=True,
		)
		count_map = {row.parent: row.item_count for row in counts}
		for row in purchase:
			row["item_count"] = count_map.get(row.name, 0)

	return {"issuance": issuance, "purchase": purchase}


@frappe.whitelist()
def get_request_detail(material_request: str):
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
			"per_ordered",
			"per_received",
			"custom_ppe_issuance",
		],
		as_dict=True,
	)
	if not mr:
		frappe.throw(_("Material Request {0} not found").format(material_request))

	# frappe.get_all, not frappe.get_list -- same reason as
	# get_employee_detail's Employee PPE History read above, verified the
	# same way: Material Request Item is a child table with no permission
	# rows of its own, and frappe.get_list silently collapses `fields` down
	# to just `name` for it, returning every other column as None. Access is
	# already gated by the has_permission("Material Request", "read", ...)
	# check above, the same umbrella Frappe's own form loader uses for a
	# document's child tables.
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
			"custom_purpose",
		],
		order_by="idx asc",
	)

	item_count = len(items)
	total_qty = sum(flt(row.qty) for row in items)

	if mr.material_request_type == "Purchase":
		fulfillment_pct = flt(mr.per_ordered)
	else:
		issued_rows = sum(1 for row in items if row.issued_via_stock_entry)
		fulfillment_pct = (issued_rows / item_count * 100) if item_count else 0

	downstream_po = []
	downstream_pr = []
	if mr.material_request_type == "Purchase":
		downstream_po = frappe.db.sql(
			"""
			select distinct po.name, po.supplier, po.transaction_date, po.status, po.grand_total
			from `tabPurchase Order Item` poi
			inner join `tabPurchase Order` po on po.name = poi.parent
			where poi.material_request = %s
			order by po.transaction_date desc
			""",
			(material_request,),
			as_dict=True,
		)
		downstream_pr = frappe.db.sql(
			"""
			select distinct pr.name, pr.posting_date, pr.status, pr.grand_total
			from `tabPurchase Receipt Item` pri
			inner join `tabPurchase Receipt` pr on pr.name = pri.parent
			where pri.material_request = %s
			order by pr.posting_date desc
			""",
			(material_request,),
			as_dict=True,
		)

	return {
		"request": mr,
		"items": items,
		"item_count": item_count,
		"total_qty": total_qty,
		"fulfillment_pct": flt(fulfillment_pct),
		"downstream_po": downstream_po,
		"downstream_pr": downstream_pr,
	}


@frappe.whitelist()
def get_procurement(company: str):
	_check_dashboard_access()
	frappe.has_permission("Company", "read", company, throw=True)

	# Three-stage pipeline, each stage traced back to a PPE purchase
	# request via Item.custom_is_ppe (see get_overview's note on why this
	# is used instead of the free-text custom_purpose field).
	pr_stage = frappe.db.sql(
		"""
		select count(distinct mr.name) as cnt, coalesce(sum(mri.qty), 0) as qty
		from `tabMaterial Request` mr
		inner join `tabMaterial Request Item` mri on mri.parent = mr.name
		inner join `tabItem` it on it.name = mri.item_code
		where mr.material_request_type = 'Purchase' and mr.company = %s and it.custom_is_ppe = 1
		""",
		(company,),
		as_dict=True,
	)[0]

	po_stage = frappe.db.sql(
		"""
		select count(distinct po.name) as cnt, coalesce(sum(poi.qty), 0) as qty
		from `tabPurchase Order Item` poi
		inner join `tabPurchase Order` po on po.name = poi.parent and po.docstatus = 1
		inner join `tabMaterial Request` mr on mr.name = poi.material_request
		where mr.material_request_type = 'Purchase' and mr.company = %s
		  and exists (
		      select 1 from `tabMaterial Request Item` mri2
		      inner join `tabItem` it2 on it2.name = mri2.item_code
		      where mri2.parent = mr.name and it2.custom_is_ppe = 1
		  )
		""",
		(company,),
		as_dict=True,
	)[0]

	receipt_stage = frappe.db.sql(
		"""
		select count(distinct pr.name) as cnt, coalesce(sum(pri.qty), 0) as qty
		from `tabPurchase Receipt Item` pri
		inner join `tabPurchase Receipt` pr on pr.name = pri.parent and pr.docstatus = 1
		inner join `tabMaterial Request` mr on mr.name = pri.material_request
		where mr.material_request_type = 'Purchase' and mr.company = %s
		  and exists (
		      select 1 from `tabMaterial Request Item` mri2
		      inner join `tabItem` it2 on it2.name = mri2.item_code
		      where mri2.parent = mr.name and it2.custom_is_ppe = 1
		  )
		""",
		(company,),
		as_dict=True,
	)[0]

	po_list = frappe.db.sql(
		"""
		select distinct po.name, po.supplier, po.transaction_date, po.status, po.grand_total
		from `tabPurchase Order` po
		inner join `tabPurchase Order Item` poi on poi.parent = po.name
		inner join `tabMaterial Request` mr on mr.name = poi.material_request
		where mr.material_request_type = 'Purchase' and mr.company = %s
		  and exists (
		      select 1 from `tabMaterial Request Item` mri2
		      inner join `tabItem` it2 on it2.name = mri2.item_code
		      where mri2.parent = mr.name and it2.custom_is_ppe = 1
		  )
		order by po.transaction_date desc
		limit 100
		""",
		(company,),
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
			# Keep the first (most recent, thanks to ORDER BY) receipt per PO.
			receipt_map.setdefault(row.po_name, row)

	for row in po_list:
		receipt = receipt_map.get(row.name)
		row["receipt_name"] = receipt.name if receipt else None
		row["receipt_date"] = receipt.posting_date if receipt else None

	first_qty = flt(pr_stage.qty) or 1
	funnel = [
		{
			"stage": "Purchase Requests",
			"count": pr_stage.cnt,
			"qty": flt(pr_stage.qty),
			"width_pct": 100,
		},
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
