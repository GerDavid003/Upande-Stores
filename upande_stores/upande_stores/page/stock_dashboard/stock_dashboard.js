// Page: stock-dashboard — Stock Dashboard
//
// Layout:
//   [ pagehead: title + company switcher ]
//   [ tabs: Overview | Material Requests | Stock Entries | Procurement |
//           Stock Levels | Inventory Health | Consumption | Approvals ]
//   [ tab body ]  <-- OR -->  [ detail body: Material Request / Stock Entry /
//                               Purchase Order / Purchase Receipt drill-down ]
//
// Same skeleton as ppe-dashboard.js (frappe.pages[...].on_page_load /
// add_styles / make / load_data, company switcher as a styled Link control,
// server-side pagination). Unlike the first version of this file, there ARE
// now real in-dashboard drill-down views (same frappe.set_route/on_page_show
// pattern as the PPE dashboard's employee/request detail) -- every PO/
// Receipt/Material Request/Stock Entry reference opens one of those via a
// `drill_link`, and each drill-down still carries a `stock_dash_doc_link` to
// the real ERPNext document for when the user wants to act on it.
frappe.pages["stock-dashboard"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Stock Dashboard",
		single_column: true,
	});
	frappe.pages["stock-dashboard"].add_styles();
	frappe.pages["stock-dashboard"].make(page);
};

frappe.pages["stock-dashboard"].on_page_show = function () {
	const P = frappe.pages["stock-dashboard"];
	if (!P.page) return;
	P._wait_then_route();
};

frappe.pages["stock-dashboard"]._wait_then_route = function (tries) {
	const P = frappe.pages["stock-dashboard"];
	tries = tries || 0;
	if (P.companies_loaded || tries > 50) {
		P.handle_route();
		return;
	}
	setTimeout(() => P._wait_then_route(tries + 1), 100);
};

frappe.pages["stock-dashboard"].add_styles = function () {
	if (document.getElementById("stock-dashboard-styles")) return;
	if (!document.getElementById("stock-dashboard-fonts")) {
		const fontLink = document.createElement("link");
		fontLink.id = "stock-dashboard-fonts";
		fontLink.rel = "stylesheet";
		fontLink.href =
			"https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600&display=swap";
		document.head.appendChild(fontLink);
	}
	const styleEl = document.createElement("style");
	styleEl.id = "stock-dashboard-styles";
	// ufd-modern design system, identical token set/technique to
	// ppe_dashboard.js, scoped under its own .stock-dash wrapper so the two
	// dashboards' styles never collide if both are open via different tabs.
	styleEl.textContent = `
        .stock-dash {
            --ink:#0a0a0a; --ink-1:#1a1a18; --ink-2:#2a2a26; --ink-3:#3a3a34;
            --ink-4:#5a5a52; --ink-mute:#8a8780; --ink-faint:#b8b6ae;
            --bg:#f4f3ef; --surface:#fafaf6; --surface-2:#ffffff;
            --hairline:rgba(10,10,10,0.07);
            --shadow-card:0 1px 0 rgba(10,10,10,0.04), 0 8px 32px -16px rgba(10,10,10,0.10);
            --shadow-hover:0 1px 0 rgba(10,10,10,0.06), 0 24px 48px -24px rgba(10,10,10,0.18);
            --signal:#228883;
            --grad-ink:linear-gradient(135deg,#0a0a0a 0%,#3a3a34 100%);
            --sans:'Poppins',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
            --mono:'JetBrains Mono',ui-monospace,monospace;
            font-family:var(--sans);
            background:var(--bg);
            padding:20px 24px 48px;
            color:var(--ink-3);
            font-size:14px;
            line-height:1.55;
        }
        .stock-dash *{box-sizing:border-box}
        .stock-dash, .stock-dash input, .stock-dash select, .stock-dash button { font-family:var(--sans); }
        .stock-dash a{color:inherit;text-decoration:none}

        .stock-dash .pagehead{display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;gap:20px;margin-bottom:24px}
        .stock-dash .pagehead__eyebrow{font:500 11px var(--sans);text-transform:uppercase;letter-spacing:2.2px;color:var(--ink-mute);margin-bottom:8px;display:inline-flex;align-items:center;gap:10px}
        .stock-dash .pagehead__eyebrow::before{content:"";width:18px;height:1px;background:var(--ink-3)}
        .stock-dash .pagehead__title{font:600 36px/1.05 var(--sans);color:var(--ink);letter-spacing:-1.1px;margin:0}
        .stock-dash .pagehead__sub{margin-top:6px;font-size:14px;color:var(--ink-4)}
        .stock-dash .pagehead__tools{display:flex;gap:10px;align-items:center;flex-wrap:wrap}

        .stock-dash .datepill{display:inline-flex;align-items:center;gap:8px;background:var(--surface-2);border-radius:999px;padding:6px 16px;font:500 12px var(--sans);color:var(--ink);box-shadow:var(--shadow-card)}
        .stock-dash .datepill label{font:600 9px var(--sans);text-transform:uppercase;letter-spacing:1px;color:var(--ink-faint);margin:0 2px 0 0;white-space:nowrap}
        .stock-dash .datepill .frappe-control{min-width:150px}
        .stock-dash .datepill .form-group{margin:0}
        .stock-dash .datepill .control-label,
        .stock-dash .datepill .help-box{display:none}
        .stock-dash .datepill input.form-control,
        .stock-dash .datepill select.form-control{border:0;box-shadow:none;padding:2px 0;font:600 13px var(--sans);color:var(--ink);background:transparent}
        .stock-dash .datepill input.form-control:focus{box-shadow:none}

        .stock-dash .tabs{display:inline-flex;gap:4px;margin-bottom:24px;background:rgba(10,10,10,0.04);padding:5px;border-radius:999px;max-width:100%;overflow-x:auto}
        .stock-dash .tab{background:transparent;border:0;font:500 13px var(--sans);color:var(--ink-4);padding:9px 18px;border-radius:999px;cursor:pointer;white-space:nowrap;transition:all .2s}
        .stock-dash .tab:hover{color:var(--ink)}
        .stock-dash .tab.on{background:var(--grad-ink);color:#fafaf6;box-shadow:0 4px 14px rgba(10,10,10,0.20)}

        .stock-dash .kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:24px}
        .stock-dash .kpi{background:var(--surface-2);border-radius:18px;padding:22px 24px;box-shadow:var(--shadow-card);transition:all .25s;position:relative;overflow:hidden}
        .stock-dash .kpi:hover{transform:translateY(-2px);box-shadow:var(--shadow-hover)}
        .stock-dash .kpi__label{font:500 11px var(--sans);text-transform:uppercase;letter-spacing:1.6px;color:var(--ink-mute);margin-bottom:12px}
        .stock-dash .kpi__value{font:600 34px/1 var(--sans);color:var(--ink);letter-spacing:-1.1px;font-feature-settings:"tnum";white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:clamp(20px,2.6vw,34px);cursor:default}
        .stock-dash .dd-select{border:0;background:transparent;font:600 13px var(--sans);color:var(--ink);outline:none;max-width:160px}
        .stock-dash .dd-filter{display:inline-flex;align-items:center;gap:6px;background:var(--surface-2);border-radius:999px;padding:6px 14px;box-shadow:var(--shadow-card)}
        .stock-dash .dd-filter label{font:600 9px var(--sans);text-transform:uppercase;letter-spacing:1px;color:var(--ink-faint);white-space:nowrap}
        .stock-dash .kpi__unit{font:400 13px var(--sans);color:var(--ink-mute);margin-top:6px}

        .stock-dash .card{background:var(--surface-2);border-radius:20px;padding:24px 26px;box-shadow:var(--shadow-card);margin-bottom:16px}
        .stock-dash .card--padded{padding:28px 30px}
        .stock-dash .card__head{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:18px;gap:20px;flex-wrap:wrap}
        .stock-dash .card__head h3{margin:0;font:600 16px var(--sans);color:var(--ink);letter-spacing:-.3px}
        .stock-dash .card__head .meta{font:500 12px var(--sans);color:var(--ink-mute)}

        .stock-dash .row-2{display:grid;grid-template-columns:2fr 1fr;gap:16px;margin-bottom:16px}
        .stock-dash .row-2-eq{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}

        .stock-dash .list{display:flex;flex-direction:column}
        .stock-dash .list__row{display:grid;grid-template-columns:1fr auto;gap:14px;padding:12px 8px;border-bottom:1px solid var(--hairline);align-items:center;transition:background .2s;border-radius:10px}
        .stock-dash .list__row:hover{background:rgba(10,10,10,0.02)}
        .stock-dash .list__row:last-child{border-bottom:0}
        .stock-dash .list__name{font:600 14px var(--sans);color:var(--ink)}
        .stock-dash .list__meta{font-size:12px;color:var(--ink-mute);margin-top:2px}
        .stock-dash .list__qty{font:600 15px var(--sans);color:var(--ink);font-variant-numeric:tabular-nums;text-align:right}
        .stock-dash .list__empty{padding:28px 8px;text-align:center;color:var(--ink-mute);font-size:13px}

        .stock-dash .hb{display:grid;grid-template-columns:160px 1fr 110px;gap:16px;align-items:center;padding:9px 0;border-bottom:1px solid var(--hairline)}
        .stock-dash .hb:last-child{border-bottom:0}
        .stock-dash .hb__name{font:600 12.5px var(--sans);color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
        .stock-dash .hb__lane{position:relative;height:16px}
        .stock-dash .hb__est{position:absolute;left:0;top:0;height:16px;width:100%;background:rgba(10,10,10,0.05);border-radius:999px}
        .stock-dash .hb__act{position:absolute;left:0;top:2px;height:12px;border-radius:999px;background:var(--grad-ink)}
        .stock-dash .hb__pct{font:600 13px var(--sans);text-align:right;color:var(--ink-3);font-variant-numeric:tabular-nums}

        .stock-dash .funnel{padding:10px 0 4px;display:flex;flex-direction:column;gap:12px}
        .stock-dash .funnel__stage{display:grid;grid-template-columns:1fr auto;align-items:center;gap:16px}
        .stock-dash .funnel__bar{height:52px;display:flex;align-items:center;padding:0 22px;font:600 14px var(--sans);color:#fafaf6;border-radius:12px;letter-spacing:-.1px;min-width:120px;transition:width .3s}
        .stock-dash .funnel__meta{font:500 11.5px var(--sans);color:var(--ink-mute);min-width:140px;text-align:right}
        .stock-dash .funnel__meta b{display:block;font:600 20px var(--sans);color:var(--ink);font-variant-numeric:tabular-nums}

        .stock-dash .backbtn{display:inline-flex;align-items:center;gap:8px;font:500 13px var(--sans);color:var(--ink-4);cursor:pointer;padding:8px 16px;border-radius:999px;background:rgba(10,10,10,0.04);transition:all .2s;border:0}
        .stock-dash .backbtn:hover{background:var(--ink);color:#fafaf6}

        .stock-dash .pillgroup{display:inline-flex;background:rgba(10,10,10,0.04);border-radius:999px;padding:4px;gap:2px;flex-wrap:wrap}
        .stock-dash .pillgroup button{border:0;background:transparent;font:500 12px var(--sans);color:var(--ink-4);padding:7px 14px;cursor:pointer;border-radius:999px;transition:all .2s;white-space:nowrap}
        .stock-dash .pillgroup button.on{background:var(--ink);color:#fafaf6;box-shadow:0 2px 8px rgba(10,10,10,0.15)}

        .stock-dash .status-chip{display:inline-block;padding:3px 10px;font:600 11px var(--sans);border-radius:99px;white-space:nowrap}

        .stock-dash .empty-state, .stock-dash .loading-state{text-align:center;padding:48px 20px;color:var(--ink-mute);font-size:13px}

        .stock-dash .mini-table{width:100%;border-collapse:collapse;font-size:12.5px}
        .stock-dash .mini-table th{text-align:left;padding:8px 10px;font:600 10px var(--sans);text-transform:uppercase;letter-spacing:.7px;color:var(--ink-faint);border-bottom:1px solid var(--hairline);white-space:nowrap}
        .stock-dash .mini-table td{padding:9px 10px;border-bottom:1px solid var(--hairline);color:var(--ink-3);vertical-align:middle}
        .stock-dash .mini-table tbody tr:last-child td{border-bottom:0}
        .stock-dash .mini-table tbody tr:hover{background:rgba(10,10,10,0.02)}
        .stock-dash .mini-table tbody tr.low-stock{background:rgba(196,48,43,0.06)}

        .stock-dash .filter-bar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:16px}
        .stock-dash .filter-bar .fb-label{font:600 10px var(--sans);text-transform:uppercase;letter-spacing:1px;color:var(--ink-faint)}

        .stock-dash .link-cell{color:var(--signal);font-weight:600;cursor:pointer}
        .stock-dash .link-cell:hover{text-decoration:underline}

        .stock-dash .search-box{display:inline-flex;align-items:center;gap:6px;background:var(--surface-2);border:1px solid var(--hairline);border-radius:999px;padding:6px 8px 6px 14px;box-shadow:var(--shadow-card)}
        .stock-dash .search-box input{border:0;outline:none;background:transparent;font:500 12.5px var(--sans);color:var(--ink);width:180px}
        .stock-dash .search-box button{border:0;background:var(--ink);color:#fafaf6;border-radius:999px;padding:5px 12px;font:600 11px var(--sans);cursor:pointer}

        .stock-dash .hero{background:var(--surface-2);border-radius:24px;padding:36px 38px;box-shadow:var(--shadow-card);margin-bottom:16px;background-image:radial-gradient(circle at 95% 5%,rgba(34,136,131,0.08),transparent 35%)}
        .stock-dash .hero__eyebrow{font:500 11px var(--sans);text-transform:uppercase;letter-spacing:2.2px;color:var(--ink-mute);margin-bottom:12px}
        .stock-dash .hero__name{font:600 40px/0.98 var(--sans);color:var(--ink);letter-spacing:-1.2px;margin:0 0 10px;word-break:break-word}
        .stock-dash .hero__sub{font:400 15px var(--sans);color:var(--ink-4);margin:0 0 24px}
        .stock-dash .hero__stats{display:grid;grid-template-columns:repeat(4,1fr);gap:24px;padding-top:20px;border-top:1px solid var(--hairline)}
        .stock-dash .hero__stat small{font:500 11px var(--sans);text-transform:uppercase;letter-spacing:1.4px;color:var(--ink-mute);display:block;margin-bottom:5px}
        .stock-dash .hero__stat b{font:600 24px var(--sans);color:var(--ink);letter-spacing:-.5px;font-variant-numeric:tabular-nums;display:block}

        .stock-dash .chart-box{min-height:240px}

        @media (max-width:1000px){.stock-dash .row-2,.stock-dash .row-2-eq{grid-template-columns:1fr}.stock-dash .hero__stats{grid-template-columns:repeat(2,1fr)}}
    `;
	document.head.appendChild(styleEl);
};

// ============================================================
// Build
// ============================================================
const STOCK_DASH_TABS = [
	{ key: "overview", label: "Overview" },
	{ key: "material_requests", label: "Material Requests" },
	{ key: "stock_entries", label: "Stock Entries" },
	{ key: "procurement", label: "Procurement" },
	{ key: "stock_levels", label: "Stock Levels" },
	{ key: "inventory_health", label: "Inventory Health" },
	{ key: "consumption", label: "Consumption" },
	{ key: "suppliers", label: "Suppliers" },
	{ key: "approvals", label: "Approvals" },
];
const STOCK_DASH_PAGE_LENGTH = 50;

frappe.pages["stock-dashboard"].make = function (page) {
	const P = frappe.pages["stock-dashboard"];
	P.page = page;
	P.companies_loaded = false;
	P.state = {
		company: null,
		companies: [],
		active_tab: "overview",
		cache: {},
		mr_type_filter: "All",
		mr_fulfillment_filter: "All",
		mr_search: "",
		mr_page: 0,
		se_type_filter: "All",
		se_search: "",
		se_page: 0,
		proc_search: "",
		sl_low_stock_only: false,
		sl_search: "",
		sl_warehouse: "",
		sl_page: 0,
		overview_from: frappe.datetime.add_days(frappe.datetime.get_today(), -30),
		overview_to: frappe.datetime.get_today(),
		consumption_group_by: ["Cost Center"],
		consumption_from: frappe.datetime.add_days(frappe.datetime.get_today(), -30),
		consumption_to: frappe.datetime.get_today(),
		consumption_business_unit: "",
		consumption_farm: "",
		consumption_cost_center: "",
		consumption_expense_account: "",
		suppliers_search: "",
		suppliers_page: 0,
		suppliers_selected: null,
		approvals_search: "",
		// Company-scoped dropdown option lists (Farm/Business Unit/Cost
		// Center/Warehouse/Expense Account), repopulated on every company
		// change -- see load_company_dropdowns.
		dd: { farms: [], business_units: [], cost_centers: [], warehouses: [], expense_accounts: [] },
		dd_loaded: false,
	};
	P._req = 0;

	const tabs_html = STOCK_DASH_TABS.map(
		(t, i) => `<button class="tab${i === 0 ? " on" : ""}" data-tab="${t.key}">${t.label}</button>`
	).join("");

	const $container = $(`
        <div class="stock-dash">
          <div class="pagehead">
            <div>
              <div class="pagehead__eyebrow">Upande Stores · Stock</div>
              <h1 class="pagehead__title">Stock Dashboard</h1>
              <p class="pagehead__sub">Material requests, stock movement, procurement, levels, health, consumption and approvals</p>
            </div>
            <div class="pagehead__tools">
              <div class="datepill"><label>Company</label><div class="stock-dash-company-field"></div></div>
            </div>
          </div>
          <div class="stock-dash-tabs-section">
            <div class="tabs">${tabs_html}</div>
            <div class="stock-dash-tab-body"><div class="loading-state">Loading…</div></div>
          </div>
          <div class="stock-dash-detail-body" style="display:none"></div>
        </div>
    `).appendTo(page.main);

	P.$wrapper = $container;
	P.$tabs_section = $container.find(".stock-dash-tabs-section");
	P.$tab_body = $container.find(".stock-dash-tab-body");
	P.$detail_body = $container.find(".stock-dash-detail-body");

	P.$wrapper.on("click", ".tabs .tab", function () {
		P.switch_tab($(this).data("tab"));
	});

	// Single delegated handler for every internal drill-down link anywhere
	// in the dashboard (list tables AND cross-links inside a detail view
	// itself, e.g. a Stock Entry's linked Material Request) -- avoids
	// rebinding a click handler per row on every re-render.
	P.$wrapper.on("click", "[data-drill-view]", function () {
		const view = $(this).data("drill-view");
		const id = $(this).data("drill-id");
		if (!id) return;
		frappe.set_route("stock-dashboard", view, String(id));
	});

	P.make_company_field($container.find(".stock-dash-company-field"));
	P.load_companies();
};

frappe.pages["stock-dashboard"].make_company_field = function ($parent) {
	const P = frappe.pages["stock-dashboard"];
	P.company_control = frappe.ui.form.make_control({
		parent: $parent,
		df: {
			fieldtype: "Link",
			fieldname: "company",
			options: "Company",
			label: "",
			placeholder: __("Select Company"),
			change() {
				const value = P.company_control.get_value();
				if (!value || value === P.state.company) return;
				P.state.company = value;
				P.state.cache = {};
				P.state.mr_page = 0;
				P.state.se_page = 0;
				P.state.sl_page = 0;
				P.state.suppliers_page = 0;
				P.state.suppliers_selected = null;
				// A filter VALUE from the old company is meaningless once the
				// company changes (a Farm/Cost Center/Warehouse/Expense Account
				// belongs to exactly one company) -- clear all of them, then
				// re-fetch the dropdown option lists for the new company.
				P.state.sl_warehouse = "";
				P.state.consumption_business_unit = "";
				P.state.consumption_farm = "";
				P.state.consumption_cost_center = "";
				P.state.consumption_expense_account = "";
				P.state.dd = { farms: [], business_units: [], cost_centers: [], warehouses: [], expense_accounts: [] };
				P.state.dd_loaded = false;
				P.load_company_dropdowns();
				P.render_active();
			},
		},
		only_input: true,
		render_input: true,
	});
	P.company_control.refresh();
};

frappe.pages["stock-dashboard"].load_companies = function () {
	const P = frappe.pages["stock-dashboard"];
	frappe.call({
		method: "upande_stores.upande_stores.page.stock_dashboard.stock_dashboard.get_companies",
		callback: function (r) {
			const data = r.message || {};
			P.state.companies = data.companies || [];
			const default_company =
				data.default_company && P.state.companies.includes(data.default_company)
					? data.default_company
					: P.state.companies[0];
			P.state.company = default_company || null;
			if (P.state.company) {
				P.company_control.set_value(P.state.company);
			}
			P.companies_loaded = true;
			if (P.state.company) P.load_company_dropdowns();
			P.handle_route();
		},
	});
};

// Farm/Business Unit/Cost Center/Warehouse/Expense Account option lists for
// the Consumption and Stock Levels filter dropdowns -- all 5 scoped to the
// currently selected company, fetched together and only re-rendered once
// every one has returned (avoids re-rendering the active tab up to 5 times
// in quick succession).
frappe.pages["stock-dashboard"].load_company_dropdowns = function () {
	const P = frappe.pages["stock-dashboard"];
	const company = P.state.company;
	if (!company) return;
	const calls = [
		["farms", "get_farms"],
		["business_units", "get_business_units"],
		["cost_centers", "get_cost_centers"],
		["warehouses", "get_warehouses"],
		["expense_accounts", "get_consumption_expense_accounts"],
	];
	let pending = calls.length;
	calls.forEach(([key, method]) => {
		frappe.call({
			method: `upande_stores.upande_stores.page.stock_dashboard.stock_dashboard.${method}`,
			args: { company: company },
			callback: function (r) {
				if (P.state.company !== company) return; // company changed again before this returned
				P.state.dd[key] = r.message || [];
				pending -= 1;
				if (pending === 0) {
					P.state.dd_loaded = true;
					if (P.state.active_tab === "consumption" || P.state.active_tab === "stock_levels") {
						P.render_active();
					}
				}
			},
		});
	});
};

// ============================================================
// Routing: dashboard tabs vs. drill-down detail views
// ============================================================
frappe.pages["stock-dashboard"].handle_route = function () {
	const P = frappe.pages["stock-dashboard"];
	if (!P.companies_loaded) return; // _wait_then_route will retry
	const route = frappe.get_route(); // ["stock-dashboard", view?, id?]
	const view = route[1];
	const id = route[2];
	if (view === "material-request" && id) P.show_material_request_detail(id);
	else if (view === "stock-entry" && id) P.show_stock_entry_detail(id);
	else if (view === "purchase-order" && id) P.show_purchase_order_detail(id);
	else if (view === "purchase-receipt" && id) P.show_purchase_receipt_detail(id);
	else P.show_dashboard();
};

frappe.pages["stock-dashboard"].show_dashboard = function () {
	const P = frappe.pages["stock-dashboard"];
	P.$detail_body.hide().empty();
	P.$tabs_section.show();
	P.render_active();
};

frappe.pages["stock-dashboard"].switch_tab = function (tab) {
	const P = frappe.pages["stock-dashboard"];
	if (tab !== "suppliers") P.state.suppliers_selected = null; // leaving the tab -> next visit starts at the list, not a stale supplier
	P.state.active_tab = tab;
	P.$wrapper.find(".tabs .tab").removeClass("on");
	P.$wrapper.find(`.tabs .tab[data-tab="${tab}"]`).addClass("on");
	P.render_active();
};

frappe.pages["stock-dashboard"].render_active = function () {
	const P = frappe.pages["stock-dashboard"];
	if (!P.companies_loaded) return;
	if (!P.state.company) {
		P.$tab_body.html('<div class="empty-state">Select a Company to see stock data.</div>');
		return;
	}
	const tab = P.state.active_tab;
	if (tab === "overview") P.load_overview();
	else if (tab === "material_requests") P.load_material_requests();
	else if (tab === "stock_entries") P.load_stock_entries();
	else if (tab === "procurement") P.load_procurement();
	else if (tab === "stock_levels") P.load_stock_levels();
	else if (tab === "inventory_health") P.load_inventory_health();
	else if (tab === "consumption") P.load_consumption();
	else if (tab === "suppliers") P.load_suppliers();
	else if (tab === "approvals") P.load_approvals();
};

// Builds an <a> to a real Desk document (frappe.utils.get_form_link is
// Frappe's own canonical helper for this). Opens in a new tab so clicking a
// document doesn't lose the dashboard's current tab/filter/scroll state.
// Used for the explicit "Open in ERPNext ↗" link inside each drill-down
// view, and directly in the Approvals tab (a draft needs editing, not a
// read-only detail page).
function stock_dash_doc_link(doctype, name, display_text) {
	if (!name) return "—";
	const href = frappe.utils.get_form_link(doctype, name);
	return `<a href="${href}" target="_blank" rel="noopener">${frappe.utils.escape_html(display_text || name)}</a>`;
}

// Builds a clickable span that routes to one of this dashboard's OWN
// drill-down views via frappe.set_route (handled by the delegated
// [data-drill-view] click handler registered once in make()). `view` is
// one of "material-request" / "stock-entry" / "purchase-order" /
// "purchase-receipt".
function drill_link(view, name, display_text) {
	if (!name) return "—";
	return `<span class="link-cell" data-drill-view="${view}" data-drill-id="${frappe.utils.escape_html(
		name
	)}">${frappe.utils.escape_html(display_text || name)}</span>`;
}

function fmt_money(v) {
	return frappe.format(v || 0, { fieldtype: "Currency" });
}
function fmt_date(v) {
	return v ? frappe.datetime.str_to_user(v) : "—";
}

// Compact form for a KPI tile ("KES 107.3M" instead of "KES 107,315,209.58")
// -- the real fix for KPI tiles overflowing their fixed-width container at
// large values, not just a font-size patch. Full precision is still always
// available via the tile's own `title` attribute (see kpi_tile below).
function fmt_compact_money(v) {
	v = flt(v) || 0;
	const currency = (frappe.boot && frappe.boot.sysdefaults && frappe.boot.sysdefaults.currency) || "";
	const abs = Math.abs(v);
	let compact;
	if (abs >= 1e9) compact = (v / 1e9).toFixed(1) + "B";
	else if (abs >= 1e6) compact = (v / 1e6).toFixed(1) + "M";
	else if (abs >= 1e3) compact = (v / 1e3).toFixed(1) + "K";
	else compact = v.toFixed(2);
	return (currency ? currency + " " : "") + compact;
}

// Shared KPI tile builder, used by every tab with a .kpi-grid (Overview,
// Stock Levels, Inventory Health, Approvals) -- one place to keep the
// overflow fix (compact money + title tooltip with the exact figure)
// consistent everywhere instead of re-implementing it per tab.
function kpi_tile(label, raw_value, unit, opts) {
	opts = opts || {};
	let display, title_attr;
	if (opts.money) {
		display = fmt_compact_money(raw_value);
		title_attr = ` title="${frappe.utils.escape_html(fmt_money(raw_value))}"`;
	} else {
		display = frappe.utils.escape_html(String(raw_value));
		title_attr = ` title="${display}"`;
	}
	const label_style = opts.label_color ? ` style="color:${opts.label_color}"` : "";
	return `<div class="kpi">
      <div class="kpi__label"${label_style}>${frappe.utils.escape_html(label)}</div>
      <div class="kpi__value"${title_attr}>${display}</div>
      <div class="kpi__unit">${frappe.utils.escape_html(unit)}</div>
    </div>`;
}

// Renders a company-scoped <select> dropdown for the filter bar. `options`
// is a list of {name, label} (label falls back to name). Empty first
// option is always "All".
function dd_select_html(cls, options, selected, all_label) {
	const opts = (options || [])
		.map(
			(o) =>
				`<option value="${frappe.utils.escape_html(o.name)}" ${
					o.name === selected ? "selected" : ""
				}>${frappe.utils.escape_html(o.label || o.name)}</option>`
		)
		.join("");
	return `<select class="dd-select ${cls}"><option value="">${frappe.utils.escape_html(
		all_label || "All"
	)}</option>${opts}</select>`;
}

// A small reusable search box: renders an input + Search button, wires
// Enter-to-search and the button click, and calls `on_search(value)` only
// when the (trimmed) value actually changed. Returns the HTML string;
// caller inserts it, then calls bind_search_box($container, on_search).
function search_box_html(current_value, placeholder) {
	return `<div class="search-box">
        <input type="text" class="search-box-input" placeholder="${frappe.utils.escape_html(
			placeholder || "Search…"
		)}" value="${frappe.utils.escape_html(current_value || "")}">
        <button class="search-box-btn">Search</button>
    </div>`;
}
function bind_search_box($scope, current_value, on_search) {
	const $input = $scope.find(".search-box-input");
	const fire = () => {
		const v = ($input.val() || "").trim();
		if (v === (current_value || "")) return;
		on_search(v);
	};
	$scope.find(".search-box-btn").on("click", fire);
	$input.on("keyup", function (e) {
		if (e.key === "Enter" || e.keyCode === 13) fire();
	});
}

// ============================================================
// Tab 1: Overview
// ============================================================
frappe.pages["stock-dashboard"].load_overview = function () {
	const P = frappe.pages["stock-dashboard"];
	const from_date = P.state.overview_from;
	const to_date = P.state.overview_to;
	const key = `overview:${P.state.company}:${from_date}:${to_date}`;
	if (P.state.cache[key]) return P.render_overview(P.state.cache[key]);
	P.$tab_body.html('<div class="loading-state">Loading overview…</div>');
	const req = ++P._req;
	frappe.call({
		method: "upande_stores.upande_stores.page.stock_dashboard.stock_dashboard.get_overview",
		args: { company: P.state.company, from_date: from_date, to_date: to_date },
		callback: function (r) {
			if (req !== P._req) return;
			P.state.cache[key] = r.message || {};
			P.render_overview(P.state.cache[key]);
		},
	});
};

frappe.pages["stock-dashboard"].render_overview = function (data) {
	const P = frappe.pages["stock-dashboard"];
	const period_label = `${fmt_date(data.from_date)} → ${fmt_date(data.to_date)}`;
	const kpi_html = [
		kpi_tile("Open Material Requests", data.open_material_requests || 0, "not fully fulfilled"),
		kpi_tile("Stock Entries", data.stock_entries_period || 0, `submitted, stock-module, ${period_label}`),
		kpi_tile("Total Stock Value", data.total_stock_value || 0, "on hand, non-rose", { money: true }),
		kpi_tile("Pending Purchase Orders", data.pending_purchase_orders || 0, "not fully received"),
		kpi_tile("Pending Purchase Receipts", data.pending_purchase_receipts || 0, "not fully billed"),
		kpi_tile("Consumption", data.consumption_period || 0, `see Consumption tab, ${period_label}`, { money: true }),
	].join("");

	P.$tab_body.html(`
        <div class="filter-bar">
          <span class="fb-label">Period (Stock Entries + Consumption KPIs only)</span>
          <div class="datepill"><label>From</label><div class="overview-from-field"></div></div>
          <div class="datepill"><label>To</label><div class="overview-to-field"></div></div>
        </div>
        <div class="kpi-grid">${kpi_html}</div>
        <div class="row-2-eq">
          <div class="card card--padded">
            <div class="card__head"><h3>Stock Entry Activity by Type</h3><div class="meta">submitted, denylist-excluded</div></div>
            <div class="chart-box overview-type-chart"><div class="loading-state">Loading chart…</div></div>
          </div>
          <div class="card card--padded">
            <div class="card__head"><h3>Consumption Trend</h3><div class="meta">weekly, last 8 weeks</div></div>
            <div class="chart-box overview-trend-chart"><div class="loading-state">Loading chart…</div></div>
          </div>
        </div>
    `);

	const from_control = frappe.ui.form.make_control({
		parent: P.$tab_body.find(".overview-from-field"),
		df: {
			fieldtype: "Date",
			fieldname: "overview_from",
			label: "",
			change() {
				const v = from_control.get_value() || "";
				if (!v || v === P.state.overview_from) return;
				P.state.overview_from = v;
				P.load_overview();
			},
		},
		only_input: true,
	});
	from_control.refresh();
	from_control.set_input(P.state.overview_from);

	const to_control = frappe.ui.form.make_control({
		parent: P.$tab_body.find(".overview-to-field"),
		df: {
			fieldtype: "Date",
			fieldname: "overview_to",
			label: "",
			change() {
				const v = to_control.get_value() || "";
				if (!v || v === P.state.overview_to) return;
				P.state.overview_to = v;
				P.load_overview();
			},
		},
		only_input: true,
	});
	to_control.refresh();
	to_control.set_input(P.state.overview_to);

	P.load_overview_charts();
};

frappe.pages["stock-dashboard"].load_overview_charts = function () {
	const P = frappe.pages["stock-dashboard"];
	const key = "overview_charts:" + P.state.company;
	if (P.state.cache[key]) return P.render_overview_charts(P.state.cache[key]);
	frappe.call({
		method: "upande_stores.upande_stores.page.stock_dashboard.stock_dashboard.get_overview_charts",
		args: { company: P.state.company },
		callback: function (r) {
			// Guard on still being on this tab for this company (rather than
			// the usual _req counter) since this is a secondary call fired
			// right after the main KPI render, not a competing tab load.
			if (P.state.active_tab !== "overview") return;
			P.state.cache[key] = r.message || { type_breakdown: [], weekly_consumption: [] };
			P.render_overview_charts(P.state.cache[key]);
		},
	});
};

const STOCK_DASH_CHART_COLORS = [
	"#228883",
	"#0a0a0a",
	"#3a3a34",
	"#9a5a00",
	"#1a8a3a",
	"#c4302b",
	"#5a5a52",
	"#8a8780",
	"#f59e0b",
	"#2563eb",
];

frappe.pages["stock-dashboard"].render_overview_charts = function (data) {
	const P = frappe.pages["stock-dashboard"];
	const $typeEl = P.$tab_body.find(".overview-type-chart");
	const $trendEl = P.$tab_body.find(".overview-trend-chart");
	if (!$typeEl.length || !$trendEl.length) return; // tab body replaced since the call went out

	const tb = data.type_breakdown || [];
	if (tb.length) {
		$typeEl.empty();
		new frappe.Chart($typeEl[0], {
			data: { labels: tb.map((r) => r.stock_entry_type), datasets: [{ values: tb.map((r) => r.count) }] },
			type: "pie",
			height: 240,
			colors: STOCK_DASH_CHART_COLORS,
		});
	} else {
		$typeEl.html('<div class="empty-state">No stock-module activity for this company.</div>');
	}

	const wk = data.weekly_consumption || [];
	if (wk.length) {
		$trendEl.empty();
		new frappe.Chart($trendEl[0], {
			data: {
				labels: wk.map((r) => frappe.datetime.str_to_user(r.week_start)),
				datasets: [{ name: "Consumption", values: wk.map((r) => r.value) }],
			},
			type: "line",
			height: 240,
			colors: ["#228883"],
			lineOptions: { regionFill: 1 },
		});
	} else {
		$trendEl.html('<div class="empty-state">No consumption in the last 8 weeks.</div>');
	}
};

// ============================================================
// Tab 2: Material Requests
// ============================================================
const MR_TYPES = ["All", "Material Issue", "Material Transfer", "Purchase", "Manufacture"];
const MR_FULFILLMENT = ["All", "Open", "Fulfilled"];

frappe.pages["stock-dashboard"].load_material_requests = function () {
	const P = frappe.pages["stock-dashboard"];
	const type = P.state.mr_type_filter || "All";
	const fulfillment = P.state.mr_fulfillment_filter || "All";
	const search = P.state.mr_search || "";
	const page = P.state.mr_page || 0;
	const start = page * STOCK_DASH_PAGE_LENGTH;
	const key = `mr:${P.state.company}:${type}:${fulfillment}:${search}:${page}`;
	if (P.state.cache[key]) return P.render_material_requests(P.state.cache[key]);
	P.$tab_body.html('<div class="loading-state">Loading material requests…</div>');
	const req = ++P._req;
	frappe.call({
		method: "upande_stores.upande_stores.page.stock_dashboard.stock_dashboard.get_material_requests",
		args: {
			company: P.state.company,
			request_type: type,
			fulfillment: fulfillment,
			search: search,
			start: start,
			page_length: STOCK_DASH_PAGE_LENGTH,
		},
		callback: function (r) {
			if (req !== P._req) return;
			P.state.cache[key] = r.message || { rows: [], total: 0 };
			P.render_material_requests(P.state.cache[key]);
		},
	});
};

frappe.pages["stock-dashboard"].render_material_requests = function (data) {
	const P = frappe.pages["stock-dashboard"];
	const rows = data.rows || [];
	const total = data.total || 0;
	const page = P.state.mr_page || 0;
	const start = page * STOCK_DASH_PAGE_LENGTH;
	const has_prev = page > 0;
	const has_next = start + rows.length < total;

	const type_pills = MR_TYPES.map(
		(t) => `<button class="${t === P.state.mr_type_filter ? "on" : ""}" data-value="${t}">${t}</button>`
	).join("");
	const fulfillment_pills = MR_FULFILLMENT.map(
		(f) => `<button class="${f === P.state.mr_fulfillment_filter ? "on" : ""}" data-value="${f}">${f}</button>`
	).join("");

	const row_html = rows.length
		? rows
				.map(
					(r) => `
        <tr>
          <td>${drill_link("material-request", r.name)}</td>
          <td>${frappe.utils.escape_html(r.material_request_type)}</td>
          <td>${fmt_date(r.transaction_date)}</td>
          <td>${r.item_count}</td>
          <td><span class="status-chip" style="background:${r.is_open ? "#f59e0b22" : "#1a8a3a22"};color:${
						r.is_open ? "#9a5a00" : "#1a8a3a"
					}">${r.is_open ? "Open" : "Fulfilled"}</span></td>
        </tr>`
				)
				.join("")
		: '<tr><td colspan="5" style="text-align:center;color:var(--ink-mute);padding:24px">No matching Material Requests.</td></tr>';

	P.$tab_body.html(`
        <div class="card card--padded">
          <div class="card__head">
            <h3>Material Requests</h3>
            <div class="meta">${total ? `${start + 1}–${start + rows.length} of ${total}` : "0 of 0"}</div>
          </div>
          <div class="filter-bar"><span class="fb-label">Type</span><div class="pillgroup mr-type-filter">${type_pills}</div></div>
          <div class="filter-bar"><span class="fb-label">Status</span><div class="pillgroup mr-fulfillment-filter">${fulfillment_pills}</div></div>
          <div class="filter-bar"><span class="fb-label">Search</span>${search_box_html(
				P.state.mr_search,
				"Name or item…"
			)}</div>
          <table class="mini-table">
            <thead><tr><th>Request</th><th>Type</th><th>Date</th><th>Items</th><th>Status</th></tr></thead>
            <tbody>${row_html}</tbody>
          </table>
        </div>
        <div style="display:flex;justify-content:center;gap:10px;margin-top:18px">
          <button class="backbtn mr-prev" ${has_prev ? "" : 'disabled style="opacity:.4;cursor:default"'}>← Prev</button>
          <button class="backbtn mr-next" ${has_next ? "" : 'disabled style="opacity:.4;cursor:default"'}>Next →</button>
        </div>
    `);

	P.$tab_body.find(".mr-type-filter button").on("click", function () {
		const v = $(this).data("value");
		if (v === P.state.mr_type_filter) return;
		P.state.mr_type_filter = v;
		P.state.mr_page = 0;
		P.load_material_requests();
	});
	P.$tab_body.find(".mr-fulfillment-filter button").on("click", function () {
		const v = $(this).data("value");
		if (v === P.state.mr_fulfillment_filter) return;
		P.state.mr_fulfillment_filter = v;
		P.state.mr_page = 0;
		P.load_material_requests();
	});
	bind_search_box(P.$tab_body, P.state.mr_search, (v) => {
		P.state.mr_search = v;
		P.state.mr_page = 0;
		P.load_material_requests();
	});
	P.$tab_body.find(".mr-prev").on("click", function () {
		if (!has_prev) return;
		P.state.mr_page = Math.max(0, page - 1);
		P.load_material_requests();
	});
	P.$tab_body.find(".mr-next").on("click", function () {
		if (!has_next) return;
		P.state.mr_page = page + 1;
		P.load_material_requests();
	});
};

// ============================================================
// Tab 3: Stock Entries
// ============================================================
const SE_TYPES = [
	"All",
	"Material Issue",
	"Material Receipt",
	"Material Transfer",
	"Material Transfer for Manufacture",
	"Manufacture",
	"Repack",
	"Material Consumption for Manufacture",
	"Send to Subcontractor",
	"Disassemble",
	"Material Return",
];

frappe.pages["stock-dashboard"].load_stock_entries = function () {
	const P = frappe.pages["stock-dashboard"];
	const type = P.state.se_type_filter || "All";
	const search = P.state.se_search || "";
	const page = P.state.se_page || 0;
	const start = page * STOCK_DASH_PAGE_LENGTH;
	const key = `se:${P.state.company}:${type}:${search}:${page}`;
	if (P.state.cache[key]) return P.render_stock_entries(P.state.cache[key]);
	P.$tab_body.html('<div class="loading-state">Loading stock entries…</div>');
	const req = ++P._req;
	frappe.call({
		method: "upande_stores.upande_stores.page.stock_dashboard.stock_dashboard.get_stock_entries",
		args: {
			company: P.state.company,
			stock_entry_type: type,
			search: search,
			start: start,
			page_length: STOCK_DASH_PAGE_LENGTH,
		},
		callback: function (r) {
			if (req !== P._req) return;
			P.state.cache[key] = r.message || { rows: [], total: 0 };
			P.render_stock_entries(P.state.cache[key]);
		},
	});
};

frappe.pages["stock-dashboard"].render_stock_entries = function (data) {
	const P = frappe.pages["stock-dashboard"];
	const rows = data.rows || [];
	const total = data.total || 0;
	const page = P.state.se_page || 0;
	const start = page * STOCK_DASH_PAGE_LENGTH;
	const has_prev = page > 0;
	const has_next = start + rows.length < total;

	const type_pills = SE_TYPES.map(
		(t) =>
			`<button class="${t === P.state.se_type_filter ? "on" : ""}" data-value="${frappe.utils.escape_html(
				t
			)}">${frappe.utils.escape_html(t)}</button>`
	).join("");

	const row_html = rows.length
		? rows
				.map(
					(r) => `
        <tr>
          <td>${drill_link("stock-entry", r.name)}</td>
          <td>${frappe.utils.escape_html(r.stock_entry_type)}</td>
          <td>${fmt_date(r.posting_date)}</td>
          <td>${frappe.utils.escape_html(r.from_warehouse || "—")}</td>
          <td>${frappe.utils.escape_html(r.to_warehouse || "—")}</td>
          <td>${drill_link("material-request", r.material_request)}</td>
          <td>${r.item_count}</td>
          <td>${fmt_money(r.total_amount)}</td>
        </tr>`
				)
				.join("")
		: '<tr><td colspan="8" style="text-align:center;color:var(--ink-mute);padding:24px">No matching Stock Entries.</td></tr>';

	P.$tab_body.html(`
        <div class="card card--padded">
          <div class="card__head">
            <h3>Stock Entries</h3>
            <div class="meta">${total ? `${start + 1}–${start + rows.length} of ${total}` : "0 of 0"} · excludes Harvesting / Grading / Receiving / Packing / Dispatch</div>
          </div>
          <div class="filter-bar"><span class="fb-label">Type</span><div class="pillgroup se-type-filter">${type_pills}</div></div>
          <div class="filter-bar"><span class="fb-label">Search</span>${search_box_html(
				P.state.se_search,
				"Name, item or warehouse…"
			)}</div>
          <table class="mini-table">
            <thead><tr><th>Entry</th><th>Type</th><th>Date</th><th>From</th><th>To</th><th>Material Request</th><th>Items</th><th>Value</th></tr></thead>
            <tbody>${row_html}</tbody>
          </table>
        </div>
        <div style="display:flex;justify-content:center;gap:10px;margin-top:18px">
          <button class="backbtn se-prev" ${has_prev ? "" : 'disabled style="opacity:.4;cursor:default"'}>← Prev</button>
          <button class="backbtn se-next" ${has_next ? "" : 'disabled style="opacity:.4;cursor:default"'}>Next →</button>
        </div>
    `);

	P.$tab_body.find(".se-type-filter button").on("click", function () {
		const v = $(this).data("value");
		if (v === P.state.se_type_filter) return;
		P.state.se_type_filter = v;
		P.state.se_page = 0;
		P.load_stock_entries();
	});
	bind_search_box(P.$tab_body, P.state.se_search, (v) => {
		P.state.se_search = v;
		P.state.se_page = 0;
		P.load_stock_entries();
	});
	P.$tab_body.find(".se-prev").on("click", function () {
		if (!has_prev) return;
		P.state.se_page = Math.max(0, page - 1);
		P.load_stock_entries();
	});
	P.$tab_body.find(".se-next").on("click", function () {
		if (!has_next) return;
		P.state.se_page = page + 1;
		P.load_stock_entries();
	});
};

// ============================================================
// Tab 4: Procurement
// ============================================================
frappe.pages["stock-dashboard"].load_procurement = function () {
	const P = frappe.pages["stock-dashboard"];
	const search = P.state.proc_search || "";
	const key = `procurement:${P.state.company}:${search}`;
	if (P.state.cache[key]) return P.render_procurement(P.state.cache[key]);
	P.$tab_body.html('<div class="loading-state">Loading procurement pipeline…</div>');
	const req = ++P._req;
	frappe.call({
		method: "upande_stores.upande_stores.page.stock_dashboard.stock_dashboard.get_procurement",
		args: { company: P.state.company, search: search },
		callback: function (r) {
			if (req !== P._req) return;
			P.state.cache[key] = r.message || { funnel: [], purchase_orders: [] };
			P.render_procurement(P.state.cache[key]);
		},
	});
};

frappe.pages["stock-dashboard"].render_procurement = function (data) {
	const P = frappe.pages["stock-dashboard"];
	const bg_by_stage = ["var(--grad-ink)", "linear-gradient(135deg,#3a3a34,#6a6a60)", "linear-gradient(135deg,var(--signal),#73b3a0)"];
	const funnel_html = (data.funnel || [])
		.map(
			(s, i) => `
        <div class="funnel__stage">
          <div class="funnel__bar" style="width:${Math.max(s.width_pct, 6)}%;background:${bg_by_stage[i] || bg_by_stage[2]}">${frappe.utils.escape_html(
				s.stage
			)}</div>
          <div class="funnel__meta"><b>${s.count}</b>${s.qty} qty</div>
        </div>`
		)
		.join("");

	const po_rows = (data.purchase_orders || [])
		.map(
			(po) => `
        <tr>
          <td>${drill_link("purchase-order", po.name)}</td>
          <td>${frappe.utils.escape_html(po.supplier || "—")}</td>
          <td>${fmt_date(po.transaction_date)}</td>
          <td>${frappe.utils.escape_html(po.status || "—")}</td>
          <td>${fmt_money(po.grand_total)}</td>
          <td>${
				po.receipt_name
					? `${drill_link("purchase-receipt", po.receipt_name)} · ${fmt_date(po.receipt_date)}`
					: '<span style="color:var(--ink-mute)">Not yet received</span>'
			}</td>
        </tr>`
		)
		.join("");

	P.$tab_body.html(`
        <div class="card card--padded">
          <div class="card__head"><h3>Procurement Funnel</h3><div class="meta">Request → Order → Receipt · non-rose Purchase requests</div></div>
          <div class="funnel">${funnel_html || '<div class="empty-state">No purchase activity for this company.</div>'}</div>
        </div>
        <div class="card card--padded">
          <div class="card__head"><h3>Purchase Orders</h3><div class="meta">${(data.purchase_orders || []).length} shown</div></div>
          <div class="filter-bar"><span class="fb-label">Search</span>${search_box_html(
				P.state.proc_search,
				"PO/Receipt name or supplier…"
			)}</div>
          <table class="mini-table">
            <thead><tr><th>PO</th><th>Supplier</th><th>Date</th><th>Status</th><th>Amount</th><th>Receipt</th></tr></thead>
            <tbody>${po_rows || '<tr><td colspan="6" style="text-align:center;color:var(--ink-mute);padding:24px">No Purchase Orders yet.</td></tr>'}</tbody>
          </table>
        </div>
    `);

	bind_search_box(P.$tab_body, P.state.proc_search, (v) => {
		P.state.proc_search = v;
		P.load_procurement();
	});
};

// ============================================================
// Tab 5: Stock Levels
// ============================================================
frappe.pages["stock-dashboard"].load_stock_levels = function () {
	const P = frappe.pages["stock-dashboard"];
	const low_only = P.state.sl_low_stock_only ? 1 : 0;
	const search = P.state.sl_search || "";
	const warehouse = P.state.sl_warehouse || "";
	const page = P.state.sl_page || 0;
	const start = page * STOCK_DASH_PAGE_LENGTH;
	const key = `sl:${P.state.company}:${low_only}:${search}:${warehouse}:${page}`;
	if (P.state.cache[key]) return P.render_stock_levels(P.state.cache[key]);
	P.$tab_body.html('<div class="loading-state">Loading stock levels…</div>');
	const req = ++P._req;
	frappe.call({
		method: "upande_stores.upande_stores.page.stock_dashboard.stock_dashboard.get_stock_levels",
		args: {
			company: P.state.company,
			low_stock_only: low_only,
			search: search,
			warehouse: warehouse,
			start: start,
			page_length: STOCK_DASH_PAGE_LENGTH,
		},
		callback: function (r) {
			if (req !== P._req) return;
			P.state.cache[key] = r.message || { rows: [], total: 0, summary: {}, by_warehouse: [] };
			P.render_stock_levels(P.state.cache[key]);
		},
	});
};

frappe.pages["stock-dashboard"].render_stock_levels = function (data) {
	const P = frappe.pages["stock-dashboard"];
	const rows = data.rows || [];
	const total = data.total || 0;
	const summary = data.summary || {};
	const by_warehouse = data.by_warehouse || [];
	const page = P.state.sl_page || 0;
	const start = page * STOCK_DASH_PAGE_LENGTH;
	const has_prev = page > 0;
	const has_next = start + rows.length < total;

	const row_html = rows.length
		? rows
				.map(
					(r) => `
        <tr class="${r.is_low_stock ? "low-stock" : ""}">
          <td>${frappe.utils.escape_html(r.item_name || r.item_code)}</td>
          <td>${frappe.utils.escape_html(r.warehouse)}</td>
          <td>${flt(r.actual_qty)}</td>
          <td>${fmt_money(r.valuation_rate)}</td>
          <td>${fmt_money(r.stock_value)}</td>
          <td>${
				r.is_low_stock
					? '<span class="status-chip" style="background:#c4302b22;color:#c4302b">Low Stock</span>'
					: r.warehouse_reorder_level
						? '<span class="status-chip" style="background:#1a8a3a22;color:#1a8a3a">OK</span>'
						: '<span style="color:var(--ink-mute)">No threshold set</span>'
			}</td>
        </tr>`
				)
				.join("")
		: '<tr><td colspan="6" style="text-align:center;color:var(--ink-mute);padding:24px">No matching stock balances.</td></tr>';

	const warehouse_options = (P.state.dd.warehouses || []).map((w) => ({ name: w.name, label: w.warehouse_name || w.name }));
	const summary_scope_label = P.state.sl_warehouse
		? frappe.utils.escape_html(P.state.sl_warehouse)
		: "non-rose, this company";

	P.$tab_body.html(`
        <div class="kpi-grid">
          ${kpi_tile("Total Stock Value", summary.total_value || 0, summary_scope_label, { money: true })}
          ${kpi_tile("Distinct Items", summary.item_count || 0, "with a stock balance row")}
          ${kpi_tile("Low Stock Items", summary.low_stock_count || 0, "below reorder level")}
        </div>
        <div class="row-2-eq">
          <div class="card card--padded">
            <div class="card__head"><h3>Value by Warehouse</h3><div class="meta">top 10, whole company</div></div>
            <div class="chart-box sl-warehouse-donut"></div>
          </div>
          <div class="card card--padded">
            <div class="card__head"><h3>Item Count by Warehouse</h3><div class="meta">top 10, whole company</div></div>
            <div class="chart-box sl-warehouse-bar"></div>
          </div>
        </div>
        <div class="card card--padded">
          <div class="card__head">
            <h3>Stock Levels</h3>
            <div class="meta">${total ? `${start + 1}–${start + rows.length} of ${total}` : "0 of 0"}</div>
          </div>
          <div class="filter-bar">
            <div class="pillgroup sl-low-filter">
              <button class="${!P.state.sl_low_stock_only ? "on" : ""}" data-value="0">All</button>
              <button class="${P.state.sl_low_stock_only ? "on" : ""}" data-value="1">Low Stock Only</button>
            </div>
          </div>
          <div class="filter-bar">
            <span class="fb-label">Warehouse</span>
            <div class="dd-filter">${dd_select_html("sl-warehouse-filter", warehouse_options, P.state.sl_warehouse, "All Warehouses")}</div>
          </div>
          <div class="filter-bar"><span class="fb-label">Search</span>${search_box_html(
				P.state.sl_search,
				"Item name or code…"
			)}</div>
          <table class="mini-table">
            <thead><tr><th>Item</th><th>Warehouse</th><th>Qty</th><th>Valuation Rate</th><th>Value</th><th>Status</th></tr></thead>
            <tbody>${row_html}</tbody>
          </table>
        </div>
        <div style="display:flex;justify-content:center;gap:10px;margin-top:18px">
          <button class="backbtn sl-prev" ${has_prev ? "" : 'disabled style="opacity:.4;cursor:default"'}>← Prev</button>
          <button class="backbtn sl-next" ${has_next ? "" : 'disabled style="opacity:.4;cursor:default"'}>Next →</button>
        </div>
    `);

	P.$tab_body.find(".sl-warehouse-filter").on("change", function () {
		const v = $(this).val() || "";
		if (v === P.state.sl_warehouse) return;
		P.state.sl_warehouse = v;
		P.state.sl_page = 0;
		P.load_stock_levels();
	});

	if (by_warehouse.length) {
		new frappe.Chart(P.$tab_body.find(".sl-warehouse-donut")[0], {
			data: {
				labels: by_warehouse.map((r) => r.warehouse),
				datasets: [{ values: by_warehouse.map((r) => r.value) }],
			},
			type: "pie",
			height: 240,
			colors: STOCK_DASH_CHART_COLORS,
		});
		new frappe.Chart(P.$tab_body.find(".sl-warehouse-bar")[0], {
			data: {
				labels: by_warehouse.map((r) => r.warehouse),
				datasets: [{ name: "Items", values: by_warehouse.map((r) => r.item_count) }],
			},
			type: "bar",
			height: 240,
			colors: ["#228883"],
		});
	} else {
		P.$tab_body.find(".sl-warehouse-donut, .sl-warehouse-bar").html('<div class="empty-state">No stock balances.</div>');
	}

	P.$tab_body.find(".sl-low-filter button").on("click", function () {
		const v = $(this).data("value") === 1;
		if (v === P.state.sl_low_stock_only) return;
		P.state.sl_low_stock_only = v;
		P.state.sl_page = 0;
		P.load_stock_levels();
	});
	bind_search_box(P.$tab_body, P.state.sl_search, (v) => {
		P.state.sl_search = v;
		P.state.sl_page = 0;
		P.load_stock_levels();
	});
	P.$tab_body.find(".sl-prev").on("click", function () {
		if (!has_prev) return;
		P.state.sl_page = Math.max(0, page - 1);
		P.load_stock_levels();
	});
	P.$tab_body.find(".sl-next").on("click", function () {
		if (!has_next) return;
		P.state.sl_page = page + 1;
		P.load_stock_levels();
	});
};

// ============================================================
// Tab 6: Inventory Health (new)
// ============================================================
const HEALTH_BUCKET_COLORS = { Excellent: "#1a8a3a", Good: "#228883", Watch: "#f59e0b", Critical: "#c4302b" };
const HEALTH_BUCKET_ORDER = ["Excellent", "Good", "Watch", "Critical"];

frappe.pages["stock-dashboard"].load_inventory_health = function () {
	const P = frappe.pages["stock-dashboard"];
	const key = "health:" + P.state.company;
	if (P.state.cache[key]) return P.render_inventory_health(P.state.cache[key]);
	P.$tab_body.html('<div class="loading-state">Loading inventory health…</div>');
	const req = ++P._req;
	frappe.call({
		method: "upande_stores.upande_stores.page.stock_dashboard.stock_dashboard.get_inventory_health",
		args: { company: P.state.company },
		callback: function (r) {
			if (req !== P._req) return;
			P.state.cache[key] = r.message || { bucket_counts: {}, worst_items: [], total_items: 0 };
			P.render_inventory_health(P.state.cache[key]);
		},
	});
};

frappe.pages["stock-dashboard"].render_inventory_health = function (data) {
	const P = frappe.pages["stock-dashboard"];
	const counts = data.bucket_counts || {};
	const worst = data.worst_items || [];

	const kpi_html = HEALTH_BUCKET_ORDER.map((b) =>
		kpi_tile(b, counts[b] || 0, `of ${data.total_items || 0} item/warehouse balances`, {
			label_color: HEALTH_BUCKET_COLORS[b],
		})
	).join("");

	const worst_html = worst.length
		? worst
				.map(
					(r) => `
        <div class="list__row">
          <div>
            <div class="list__name">${frappe.utils.escape_html(r.item_name || r.item_code)}</div>
            <div class="list__meta">${frappe.utils.escape_html(r.warehouse)} · qty ${flt(r.actual_qty)} ·
              ${r.age_days >= 999 ? "never moved" : r.age_days + "d since last movement"}</div>
          </div>
          <span class="status-chip" style="background:${HEALTH_BUCKET_COLORS[r.bucket]}22;color:${
						HEALTH_BUCKET_COLORS[r.bucket]
					}">${r.bucket}</span>
        </div>`
				)
				.join("")
		: '<div class="list__empty">No Critical or Watch items — everything checked looks healthy.</div>';

	P.$tab_body.html(`
        <div class="kpi-grid">${kpi_html}</div>
        <div class="row-2-eq">
          <div class="card card--padded">
            <div class="card__head"><h3>Health Breakdown</h3><div class="meta">non-rose item/warehouse balances</div></div>
            <div class="chart-box health-donut"></div>
          </div>
          <div class="card card--padded">
            <div class="card__head"><h3>Worst Items</h3><div class="meta">Critical first, then Watch, oldest first</div></div>
            <div class="list">${worst_html}</div>
          </div>
        </div>
    `);

	const has_any = HEALTH_BUCKET_ORDER.some((b) => counts[b]);
	if (has_any) {
		new frappe.Chart(P.$tab_body.find(".health-donut")[0], {
			data: {
				labels: HEALTH_BUCKET_ORDER,
				datasets: [{ values: HEALTH_BUCKET_ORDER.map((b) => counts[b] || 0) }],
			},
			type: "pie",
			height: 260,
			colors: HEALTH_BUCKET_ORDER.map((b) => HEALTH_BUCKET_COLORS[b]),
		});
	} else {
		P.$tab_body.find(".health-donut").html('<div class="empty-state">No stock balances to score.</div>');
	}
};

// ============================================================
// Tab 7: Consumption (multi-select group-by)
// ============================================================
const CONSUMPTION_GROUP_BY_OPTIONS = ["Company", "Business Unit", "Farm", "Cost Center", "Expense Account"];

frappe.pages["stock-dashboard"].load_consumption = function () {
	const P = frappe.pages["stock-dashboard"];
	const group_by = (P.state.consumption_group_by || []).slice().sort().join(",");
	const from_date = P.state.consumption_from;
	const to_date = P.state.consumption_to;
	const bu = P.state.consumption_business_unit || "";
	const farm = P.state.consumption_farm || "";
	const cc = P.state.consumption_cost_center || "";
	const ea = P.state.consumption_expense_account || "";
	const key = `consumption:${P.state.company}:${group_by}:${from_date}:${to_date}:${bu}:${farm}:${cc}:${ea}`;
	if (P.state.cache[key]) return P.render_consumption(P.state.cache[key]);
	P.$tab_body.html('<div class="loading-state">Loading consumption…</div>');
	const req = ++P._req;
	frappe.call({
		method: "upande_stores.upande_stores.page.stock_dashboard.stock_dashboard.get_consumption",
		args: {
			company: P.state.company,
			from_date: from_date,
			to_date: to_date,
			group_by: P.state.consumption_group_by,
			business_unit: bu,
			farm: farm,
			cost_center: cc,
			expense_account: ea,
		},
		callback: function (r) {
			if (req !== P._req) return;
			P.state.cache[key] = r.message || { breakdown: [], top_items: [] };
			P.render_consumption(P.state.cache[key]);
		},
	});
};

frappe.pages["stock-dashboard"].render_consumption = function (data) {
	const P = frappe.pages["stock-dashboard"];
	const breakdown = data.breakdown || [];
	const top_items = data.top_items || [];
	const checked = P.state.consumption_group_by || [];

	// Multi-select: each pill toggles independently (doesn't clear
	// siblings), reusing .pillgroup styling -- CSS doesn't enforce
	// single-.on, that was always purely a matter of the click handler
	// clearing siblings, which this one deliberately does not do.
	const group_pills = CONSUMPTION_GROUP_BY_OPTIONS.map(
		(g) => `<button class="${checked.includes(g) ? "on" : ""}" data-value="${g}">${g}</button>`
	).join("");

	const applied_label = (data.group_by || []).join(" + ") || "Company";

	const breakdown_html = breakdown.length
		? breakdown
				.map(
					(b) => `
        <div class="hb">
          <div class="hb__name" title="${frappe.utils.escape_html(b.dimension)}">${frappe.utils.escape_html(b.dimension)}</div>
          <div class="hb__lane"><div class="hb__est"></div><div class="hb__act" style="width:${b.share_pct}%"></div></div>
          <div class="hb__pct">${fmt_money(b.value)}</div>
        </div>`
				)
				.join("")
		: '<div class="empty-state">No consumption in this period.</div>';

	const top_items_html = top_items.length
		? top_items
				.map(
					(it, i) => `
        <div class="list__row">
          <div>
            <div class="list__name">${i + 1}. ${frappe.utils.escape_html(it.item_name || it.item_code)}</div>
            <div class="list__meta">${frappe.utils.escape_html(it.item_code)} · qty ${flt(it.qty)}</div>
          </div>
          <div class="list__qty">${fmt_money(it.value)}</div>
        </div>`
				)
				.join("")
		: '<div class="list__empty">No consumption in this period.</div>';

	P.$tab_body.html(`
        <div class="card card--padded">
          <div class="card__head">
            <h3>Consumption Value</h3>
            <div class="meta">${fmt_date(data.from_date)} → ${fmt_date(data.to_date)} · total ${fmt_money(
				data.total_value
			)} · grouped by ${frappe.utils.escape_html(applied_label)}</div>
          </div>
          <div class="filter-bar"><span class="fb-label">Period</span>
            <div class="datepill"><label>From</label><div class="consumption-from-field"></div></div>
            <div class="datepill"><label>To</label><div class="consumption-to-field"></div></div>
          </div>
          <div class="filter-bar"><span class="fb-label">Group By (select 1+)</span><div class="pillgroup consumption-group-filter">${group_pills}</div></div>
          <div class="filter-bar">
            <span class="fb-label">Filter to a specific value</span>
            <div class="dd-filter"><label>Business Unit</label>${dd_select_html(
				"cons-bu-filter",
				(P.state.dd.business_units || []).map((o) => ({ name: o.name, label: o.name })),
				P.state.consumption_business_unit
			)}</div>
            <div class="dd-filter"><label>Farm</label>${dd_select_html(
				"cons-farm-filter",
				(P.state.dd.farms || []).map((o) => ({ name: o.name, label: o.farm_name || o.name })),
				P.state.consumption_farm
			)}</div>
            <div class="dd-filter"><label>Cost Center</label>${dd_select_html(
				"cons-cc-filter",
				(P.state.dd.cost_centers || []).map((o) => ({ name: o.name, label: o.cost_center_name || o.name })),
				P.state.consumption_cost_center
			)}</div>
            <div class="dd-filter"><label>Expense Account</label>${dd_select_html(
				"cons-ea-filter",
				(P.state.dd.expense_accounts || []).map((a) => ({ name: a, label: a })),
				P.state.consumption_expense_account
			)}</div>
          </div>
          <div class="chart-box consumption-bar-chart" style="margin-bottom:18px"></div>
          ${breakdown_html}
        </div>
        <div class="card card--padded">
          <div class="card__head"><h3>Top Consumed Items</h3><div class="meta">by value, same period</div></div>
          <div class="list">${top_items_html}</div>
        </div>
    `);

	if (breakdown.length) {
		new frappe.Chart(P.$tab_body.find(".consumption-bar-chart")[0], {
			data: {
				labels: breakdown.map((b) => b.dimension),
				datasets: [{ name: "Value", values: breakdown.map((b) => b.value) }],
			},
			type: "bar",
			height: 260,
			colors: ["#228883"],
		});
	} else {
		P.$tab_body.find(".consumption-bar-chart").html('<div class="empty-state">No consumption in this period.</div>');
	}

	// set_input (not .val()/set_value) mirrors sales_allocation.js's own date
	// filter controls: it writes the display value without firing `change`,
	// so restoring the already-selected date on every re-render doesn't
	// trigger a redundant reload of its own.
	const from_control = frappe.ui.form.make_control({
		parent: P.$tab_body.find(".consumption-from-field"),
		df: {
			fieldtype: "Date",
			fieldname: "from_date",
			label: "",
			change() {
				const v = from_control.get_value() || "";
				if (!v || v === P.state.consumption_from) return;
				P.state.consumption_from = v;
				P.load_consumption();
			},
		},
		only_input: true,
	});
	from_control.refresh();
	from_control.set_input(P.state.consumption_from);

	const to_control = frappe.ui.form.make_control({
		parent: P.$tab_body.find(".consumption-to-field"),
		df: {
			fieldtype: "Date",
			fieldname: "to_date",
			label: "",
			change() {
				const v = to_control.get_value() || "";
				if (!v || v === P.state.consumption_to) return;
				P.state.consumption_to = v;
				P.load_consumption();
			},
		},
		only_input: true,
	});
	to_control.refresh();
	to_control.set_input(P.state.consumption_to);

	P.$tab_body.find(".consumption-group-filter button").on("click", function () {
		const v = $(this).data("value");
		const idx = P.state.consumption_group_by.indexOf(v);
		if (idx === -1) P.state.consumption_group_by.push(v);
		else P.state.consumption_group_by.splice(idx, 1);
		// Empty selection is a legitimate state -- the server falls back to
		// Company -- so don't force a minimum here, just reload and let the
		// response's own `group_by` (shown in `applied_label` above) tell
		// the user what was actually used.
		P.load_consumption();
	});

	P.$tab_body.find(".cons-bu-filter").on("change", function () {
		P.state.consumption_business_unit = $(this).val() || "";
		P.load_consumption();
	});
	P.$tab_body.find(".cons-farm-filter").on("change", function () {
		P.state.consumption_farm = $(this).val() || "";
		P.load_consumption();
	});
	P.$tab_body.find(".cons-cc-filter").on("change", function () {
		P.state.consumption_cost_center = $(this).val() || "";
		P.load_consumption();
	});
	P.$tab_body.find(".cons-ea-filter").on("change", function () {
		P.state.consumption_expense_account = $(this).val() || "";
		P.load_consumption();
	});
};

// ============================================================
// Tab 8: Approvals (new)
// ============================================================
frappe.pages["stock-dashboard"].load_approvals = function () {
	const P = frappe.pages["stock-dashboard"];
	const search = P.state.approvals_search || "";
	const key = `approvals:${P.state.company}:${search}`;
	if (P.state.cache[key]) return P.render_approvals(P.state.cache[key]);
	P.$tab_body.html('<div class="loading-state">Loading approvals…</div>');
	const req = ++P._req;
	frappe.call({
		method: "upande_stores.upande_stores.page.stock_dashboard.stock_dashboard.get_approvals",
		args: { company: P.state.company, search: search },
		callback: function (r) {
			if (req !== P._req) return;
			P.state.cache[key] = r.message || {};
			P.render_approvals(P.state.cache[key]);
		},
	});
};

function approvals_table(rows, columns) {
	if (!rows || !rows.length) {
		return `<tr><td colspan="${columns.length}" style="text-align:center;color:var(--ink-mute);padding:20px">None pending.</td></tr>`;
	}
	return rows
		.map((r) => `<tr>${columns.map((c) => `<td>${c.render(r)}</td>`).join("")}</tr>`)
		.join("");
}

frappe.pages["stock-dashboard"].render_approvals = function (data) {
	const P = frappe.pages["stock-dashboard"];
	const counts = data.counts || {};

	const kpi_html = [
		["Total Pending", counts.total_pending || 0],
		["Draft Material Requests", counts.draft_material_requests || 0],
		["Draft Purchase Orders", counts.draft_purchase_orders || 0],
		["Draft Stock Entries", counts.draft_stock_entries || 0],
		["Draft Purchase Receipts", counts.draft_purchase_receipts || 0],
	]
		.map(([label, value]) => kpi_tile(label, value, "docstatus = Draft"))
		.join("");

	const mr_rows = approvals_table(data.material_requests, [
		{ render: (r) => stock_dash_doc_link("Material Request", r.name) },
		{ render: (r) => frappe.utils.escape_html(r.material_request_type || "—") },
		{ render: (r) => frappe.utils.escape_html(r.company || "—") },
		{ render: (r) => fmt_date(r.transaction_date) },
		{ render: (r) => `${r.age_days}d` },
		{ render: (r) => frappe.utils.escape_html(r.owner || "—") },
	]);
	const po_rows = approvals_table(data.purchase_orders, [
		{ render: (r) => stock_dash_doc_link("Purchase Order", r.name) },
		{ render: (r) => frappe.utils.escape_html(r.supplier || "—") },
		{ render: (r) => frappe.utils.escape_html(r.company || "—") },
		{ render: (r) => fmt_date(r.transaction_date) },
		{ render: (r) => `${r.age_days}d` },
		{ render: (r) => frappe.utils.escape_html(r.owner || "—") },
	]);
	const se_rows = approvals_table(data.stock_entries, [
		{ render: (r) => stock_dash_doc_link("Stock Entry", r.name) },
		{ render: (r) => frappe.utils.escape_html(r.stock_entry_type || "—") },
		{ render: (r) => frappe.utils.escape_html(r.company || "—") },
		{ render: (r) => fmt_date(r.posting_date) },
		{ render: (r) => `${r.age_days}d` },
		{ render: (r) => frappe.utils.escape_html(r.owner || "—") },
	]);
	const pr_rows = approvals_table(data.purchase_receipts, [
		{ render: (r) => stock_dash_doc_link("Purchase Receipt", r.name) },
		{ render: (r) => frappe.utils.escape_html(r.supplier || "—") },
		{ render: (r) => frappe.utils.escape_html(r.company || "—") },
		{ render: (r) => fmt_date(r.posting_date) },
		{ render: (r) => `${r.age_days}d` },
		{ render: (r) => frappe.utils.escape_html(r.owner || "—") },
	]);

	P.$tab_body.html(`
        <div class="kpi-grid">${kpi_html}</div>
        <div class="filter-bar"><span class="fb-label">Search</span>${search_box_html(
			P.state.approvals_search,
			"Name or supplier…"
		)}</div>
        <div class="card card--padded">
          <div class="card__head"><h3>Draft Material Requests</h3><div class="meta">${(data.material_requests || []).length} shown</div></div>
          <table class="mini-table"><thead><tr><th>Request</th><th>Type</th><th>Company</th><th>Date</th><th>Age</th><th>Owner</th></tr></thead><tbody>${mr_rows}</tbody></table>
        </div>
        <div class="card card--padded">
          <div class="card__head"><h3>Draft Purchase Orders</h3><div class="meta">${(data.purchase_orders || []).length} shown</div></div>
          <table class="mini-table"><thead><tr><th>PO</th><th>Supplier</th><th>Company</th><th>Date</th><th>Age</th><th>Owner</th></tr></thead><tbody>${po_rows}</tbody></table>
        </div>
        <div class="card card--padded">
          <div class="card__head"><h3>Draft Stock Entries</h3><div class="meta">${(data.stock_entries || []).length} shown</div></div>
          <table class="mini-table"><thead><tr><th>Entry</th><th>Type</th><th>Company</th><th>Date</th><th>Age</th><th>Owner</th></tr></thead><tbody>${se_rows}</tbody></table>
        </div>
        <div class="card card--padded">
          <div class="card__head"><h3>Draft Purchase Receipts</h3><div class="meta">${(data.purchase_receipts || []).length} shown</div></div>
          <table class="mini-table"><thead><tr><th>Receipt</th><th>Supplier</th><th>Company</th><th>Date</th><th>Age</th><th>Owner</th></tr></thead><tbody>${pr_rows}</tbody></table>
        </div>
    `);

	bind_search_box(P.$tab_body, P.state.approvals_search, (v) => {
		P.state.approvals_search = v;
		P.load_approvals();
	});
};

// ============================================================
// Drill-down: Material Request
// ============================================================
frappe.pages["stock-dashboard"].show_material_request_detail = function (name) {
	const P = frappe.pages["stock-dashboard"];
	P.$tabs_section.hide();
	P.$detail_body.show().html('<div class="loading-state">Loading…</div>');
	const req = ++P._req;
	frappe.call({
		method: "upande_stores.upande_stores.page.stock_dashboard.stock_dashboard.get_material_request_detail",
		args: { material_request: name },
		callback: function (r) {
			if (req !== P._req) return;
			P.render_material_request_detail(r.message || {});
		},
	});
};

frappe.pages["stock-dashboard"].render_material_request_detail = function (data) {
	const P = frappe.pages["stock-dashboard"];
	const mr = data.request || {};
	const items = data.items || [];

	const item_rows = items.length
		? items
				.map(
					(i) => `
        <tr>
          <td>${frappe.utils.escape_html(i.item_name || i.item_code || "—")}</td>
          <td>${flt(i.qty || 0)}</td>
          <td>${frappe.utils.escape_html(i.employee_name || "—")}</td>
          <td>${frappe.utils.escape_html(i.cost_center || "—")}</td>
          <td>${frappe.utils.escape_html(i.warehouse || "—")}</td>
          <td>${
				i.is_fulfilled === null
					? "—"
					: i.is_fulfilled
						? '<span class="status-chip" style="background:#1a8a3a22;color:#1a8a3a">Issued</span>'
						: '<span class="status-chip" style="background:#f59e0b22;color:#9a5a00">Pending</span>'
			}</td>
        </tr>`
				)
				.join("")
		: '<tr><td colspan="6" style="text-align:center;color:var(--ink-mute);padding:24px">No item rows.</td></tr>';

	P.$detail_body.html(`
        <button class="backbtn detail-back">← Back to Dashboard</button>
        <div class="hero">
          <div class="hero__eyebrow">${frappe.utils.escape_html(mr.material_request_type || "")} · ${frappe.utils.escape_html(
				mr.company || ""
			)}</div>
          <h1 class="hero__name">${frappe.utils.escape_html(mr.name || "")}</h1>
          <p class="hero__sub">Status: ${frappe.utils.escape_html(mr.status || "—")} · ${fmt_date(mr.transaction_date)}${
				mr.schedule_date ? " → " + fmt_date(mr.schedule_date) : ""
			}</p>
          <div class="hero__stats">
            <div class="hero__stat"><small>Items</small><b>${items.length}</b></div>
            <div class="hero__stat"><small>Per Ordered</small><b>${flt(mr.per_ordered || 0).toFixed(0)}%</b></div>
            <div class="hero__stat"><small>Per Received</small><b>${flt(mr.per_received || 0).toFixed(0)}%</b></div>
            <div class="hero__stat"><small>ERPNext</small><b style="font-size:15px">${stock_dash_doc_link(
				"Material Request",
				mr.name,
				"Open ↗"
			)}</b></div>
          </div>
        </div>
        <div class="card card--padded">
          <div class="card__head"><h3>Item Rows</h3></div>
          <table class="mini-table">
            <thead><tr><th>Item</th><th>Qty</th><th>Employee</th><th>Cost Center</th><th>Warehouse</th><th>Fulfillment</th></tr></thead>
            <tbody>${item_rows}</tbody>
          </table>
        </div>
    `);

	P.$detail_body.find(".detail-back").on("click", () => frappe.set_route("stock-dashboard"));
};

// ============================================================
// Drill-down: Stock Entry
// ============================================================
frappe.pages["stock-dashboard"].show_stock_entry_detail = function (name) {
	const P = frappe.pages["stock-dashboard"];
	P.$tabs_section.hide();
	P.$detail_body.show().html('<div class="loading-state">Loading…</div>');
	const req = ++P._req;
	frappe.call({
		method: "upande_stores.upande_stores.page.stock_dashboard.stock_dashboard.get_stock_entry_detail",
		args: { stock_entry: name },
		callback: function (r) {
			if (req !== P._req) return;
			P.render_stock_entry_detail(r.message || {});
		},
	});
};

frappe.pages["stock-dashboard"].render_stock_entry_detail = function (data) {
	const P = frappe.pages["stock-dashboard"];
	const se = data.entry || {};
	const items = data.items || [];

	const item_rows = items.length
		? items
				.map(
					(i) => `
        <tr>
          <td>${frappe.utils.escape_html(i.item_name || i.item_code || "—")}</td>
          <td>${flt(i.qty || 0)}</td>
          <td>${fmt_money(i.basic_rate)}</td>
          <td>${fmt_money(i.amount)}</td>
          <td>${frappe.utils.escape_html(i.cost_center || "—")}</td>
          <td>${frappe.utils.escape_html(i.expense_account || "—")}</td>
          <td>${frappe.utils.escape_html(i.farm || "—")}</td>
          <td>${frappe.utils.escape_html(i.business_unit || "—")}</td>
        </tr>`
				)
				.join("")
		: '<tr><td colspan="8" style="text-align:center;color:var(--ink-mute);padding:24px">No item rows.</td></tr>';

	P.$detail_body.html(`
        <button class="backbtn detail-back">← Back to Dashboard</button>
        <div class="hero">
          <div class="hero__eyebrow">${frappe.utils.escape_html(se.stock_entry_type || "")} · ${frappe.utils.escape_html(
				se.company || ""
			)}</div>
          <h1 class="hero__name">${frappe.utils.escape_html(se.name || "")}</h1>
          <p class="hero__sub">${fmt_date(se.posting_date)} · ${frappe.utils.escape_html(
				se.from_warehouse || "—"
			)} → ${frappe.utils.escape_html(se.to_warehouse || "—")}</p>
          <div class="hero__stats">
            <div class="hero__stat"><small>Items</small><b>${items.length}</b></div>
            <div class="hero__stat"><small>Total Value</small><b style="font-size:18px">${fmt_money(se.total_amount)}</b></div>
            <div class="hero__stat"><small>Material Request</small><b style="font-size:15px">${drill_link(
				"material-request",
				data.material_request,
				data.material_request || "—"
			)}</b></div>
            <div class="hero__stat"><small>ERPNext</small><b style="font-size:15px">${stock_dash_doc_link(
				"Stock Entry",
				se.name,
				"Open ↗"
			)}</b></div>
          </div>
        </div>
        <div class="card card--padded">
          <div class="card__head"><h3>Item Rows</h3></div>
          <table class="mini-table">
            <thead><tr><th>Item</th><th>Qty</th><th>Rate</th><th>Amount</th><th>Cost Center</th><th>Expense Account</th><th>Farm</th><th>Business Unit</th></tr></thead>
            <tbody>${item_rows}</tbody>
          </table>
        </div>
    `);

	P.$detail_body.find(".detail-back").on("click", () => frappe.set_route("stock-dashboard"));
};

// ============================================================
// Drill-down: Purchase Order
// ============================================================
frappe.pages["stock-dashboard"].show_purchase_order_detail = function (name) {
	const P = frappe.pages["stock-dashboard"];
	P.$tabs_section.hide();
	P.$detail_body.show().html('<div class="loading-state">Loading…</div>');
	const req = ++P._req;
	frappe.call({
		method: "upande_stores.upande_stores.page.stock_dashboard.stock_dashboard.get_purchase_order_detail",
		args: { purchase_order: name },
		callback: function (r) {
			if (req !== P._req) return;
			P.render_purchase_order_detail(r.message || {});
		},
	});
};

frappe.pages["stock-dashboard"].render_purchase_order_detail = function (data) {
	const P = frappe.pages["stock-dashboard"];
	const po = data.order || {};
	const items = data.items || [];
	const receipts = data.receipts || [];

	const item_rows = items.length
		? items
				.map(
					(i) => `
        <tr>
          <td>${frappe.utils.escape_html(i.item_name || i.item_code || "—")}</td>
          <td>${flt(i.qty || 0)}</td>
          <td>${flt(i.received_qty || 0)}</td>
          <td>${fmt_money(i.rate)}</td>
          <td>${fmt_money(i.amount)}</td>
        </tr>`
				)
				.join("")
		: '<tr><td colspan="5" style="text-align:center;color:var(--ink-mute);padding:24px">No item rows.</td></tr>';

	const receipt_rows = receipts.length
		? receipts
				.map(
					(r) => `
        <tr>
          <td>${drill_link("purchase-receipt", r.name)}</td>
          <td>${fmt_date(r.posting_date)}</td>
          <td>${frappe.utils.escape_html(r.status || "—")}</td>
          <td>${fmt_money(r.grand_total)}</td>
        </tr>`
				)
				.join("")
		: '<tr><td colspan="4" style="text-align:center;color:var(--ink-mute);padding:16px">No Purchase Receipts yet.</td></tr>';

	P.$detail_body.html(`
        <button class="backbtn detail-back">← Back to Dashboard</button>
        <div class="hero">
          <div class="hero__eyebrow">Purchase Order · ${frappe.utils.escape_html(po.company || "")}</div>
          <h1 class="hero__name">${frappe.utils.escape_html(po.name || "")}</h1>
          <p class="hero__sub">${frappe.utils.escape_html(po.supplier || "")} · Status: ${frappe.utils.escape_html(
				po.status || "—"
			)} · ${fmt_date(po.transaction_date)}</p>
          <div class="hero__stats">
            <div class="hero__stat"><small>Total</small><b style="font-size:18px">${fmt_money(po.grand_total)}</b></div>
            <div class="hero__stat"><small>Per Received</small><b>${flt(po.per_received || 0).toFixed(0)}%</b></div>
            <div class="hero__stat"><small>Material Request</small><b style="font-size:15px">${drill_link(
				"material-request",
				data.material_request,
				data.material_request || "—"
			)}</b></div>
            <div class="hero__stat"><small>ERPNext</small><b style="font-size:15px">${stock_dash_doc_link(
				"Purchase Order",
				po.name,
				"Open ↗"
			)}</b></div>
          </div>
        </div>
        <div class="card card--padded">
          <div class="card__head"><h3>Item Rows</h3></div>
          <table class="mini-table">
            <thead><tr><th>Item</th><th>Qty</th><th>Received</th><th>Rate</th><th>Amount</th></tr></thead>
            <tbody>${item_rows}</tbody>
          </table>
        </div>
        <div class="card card--padded">
          <div class="card__head"><h3>Purchase Receipts</h3><div class="meta">${receipts.length} received</div></div>
          <table class="mini-table">
            <thead><tr><th>Receipt</th><th>Date</th><th>Status</th><th>Amount</th></tr></thead>
            <tbody>${receipt_rows}</tbody>
          </table>
        </div>
    `);

	P.$detail_body.find(".detail-back").on("click", () => frappe.set_route("stock-dashboard"));
};

// ============================================================
// Drill-down: Purchase Receipt
// ============================================================
frappe.pages["stock-dashboard"].show_purchase_receipt_detail = function (name) {
	const P = frappe.pages["stock-dashboard"];
	P.$tabs_section.hide();
	P.$detail_body.show().html('<div class="loading-state">Loading…</div>');
	const req = ++P._req;
	frappe.call({
		method: "upande_stores.upande_stores.page.stock_dashboard.stock_dashboard.get_purchase_receipt_detail",
		args: { purchase_receipt: name },
		callback: function (r) {
			if (req !== P._req) return;
			P.render_purchase_receipt_detail(r.message || {});
		},
	});
};

frappe.pages["stock-dashboard"].render_purchase_receipt_detail = function (data) {
	const P = frappe.pages["stock-dashboard"];
	const pr = data.receipt || {};
	const items = data.items || [];

	const item_rows = items.length
		? items
				.map(
					(i) => `
        <tr>
          <td>${frappe.utils.escape_html(i.item_name || i.item_code || "—")}</td>
          <td>${flt(i.qty || 0)}</td>
          <td>${frappe.utils.escape_html(i.warehouse || "—")}</td>
          <td>${fmt_money(i.rate)}</td>
          <td>${fmt_money(i.amount)}</td>
        </tr>`
				)
				.join("")
		: '<tr><td colspan="5" style="text-align:center;color:var(--ink-mute);padding:24px">No item rows.</td></tr>';

	P.$detail_body.html(`
        <button class="backbtn detail-back">← Back to Dashboard</button>
        <div class="hero">
          <div class="hero__eyebrow">Purchase Receipt · ${frappe.utils.escape_html(pr.company || "")}</div>
          <h1 class="hero__name">${frappe.utils.escape_html(pr.name || "")}</h1>
          <p class="hero__sub">${frappe.utils.escape_html(pr.supplier || "")} · Status: ${frappe.utils.escape_html(
				pr.status || "—"
			)} · ${fmt_date(pr.posting_date)}</p>
          <div class="hero__stats">
            <div class="hero__stat"><small>Total</small><b style="font-size:18px">${fmt_money(pr.grand_total)}</b></div>
            <div class="hero__stat"><small>Per Billed</small><b>${flt(pr.per_billed || 0).toFixed(0)}%</b></div>
            <div class="hero__stat"><small>Purchase Order</small><b style="font-size:15px">${drill_link(
				"purchase-order",
				data.purchase_order,
				data.purchase_order || "—"
			)}</b></div>
            <div class="hero__stat"><small>ERPNext</small><b style="font-size:15px">${stock_dash_doc_link(
				"Purchase Receipt",
				pr.name,
				"Open ↗"
			)}</b></div>
          </div>
        </div>
        <div class="card card--padded">
          <div class="card__head"><h3>Item Rows</h3></div>
          <table class="mini-table">
            <thead><tr><th>Item</th><th>Qty</th><th>Warehouse</th><th>Rate</th><th>Amount</th></tr></thead>
            <tbody>${item_rows}</tbody>
          </table>
        </div>
    `);

	P.$detail_body.find(".detail-back").on("click", () => frappe.set_route("stock-dashboard"));
};

// ============================================================
// Tab 9: Suppliers (new)
// ============================================================
frappe.pages["stock-dashboard"].load_suppliers = function () {
	const P = frappe.pages["stock-dashboard"];
	if (P.state.suppliers_selected) return P.load_supplier_pos();

	const search = P.state.suppliers_search || "";
	const page = P.state.suppliers_page || 0;
	const start = page * STOCK_DASH_PAGE_LENGTH;
	const key = `suppliers:${P.state.company}:${search}:${page}`;
	if (P.state.cache[key]) return P.render_suppliers(P.state.cache[key]);
	P.$tab_body.html('<div class="loading-state">Loading suppliers…</div>');
	const req = ++P._req;
	frappe.call({
		method: "upande_stores.upande_stores.page.stock_dashboard.stock_dashboard.get_suppliers",
		args: { company: P.state.company, search: search, start: start, page_length: STOCK_DASH_PAGE_LENGTH },
		callback: function (r) {
			if (req !== P._req) return;
			P.state.cache[key] = r.message || { rows: [], total: 0 };
			P.render_suppliers(P.state.cache[key]);
		},
	});
};

frappe.pages["stock-dashboard"].render_suppliers = function (data) {
	const P = frappe.pages["stock-dashboard"];
	const rows = data.rows || [];
	const total = data.total || 0;
	const page = P.state.suppliers_page || 0;
	const start = page * STOCK_DASH_PAGE_LENGTH;
	const has_prev = page > 0;
	const has_next = start + rows.length < total;

	const row_html = rows.length
		? rows
				.map(
					(r) => `
        <tr class="suppliers-row" data-supplier="${frappe.utils.escape_html(r.supplier)}" style="cursor:pointer">
          <td>${frappe.utils.escape_html(r.supplier)}</td>
          <td>${r.po_count}</td>
          <td>${fmt_money(r.total_value)}</td>
          <td>${r.fully_received_count}</td>
          <td>${r.pending_count}</td>
          <td>${r.avg_lead_days === null || r.avg_lead_days === undefined ? "—" : Math.round(r.avg_lead_days) + "d"}</td>
        </tr>`
				)
				.join("")
		: '<tr><td colspan="6" style="text-align:center;color:var(--ink-mute);padding:24px">No suppliers with a non-rose Purchase Order for this company.</td></tr>';

	P.$tab_body.html(`
        <div class="card card--padded">
          <div class="card__head">
            <h3>Suppliers</h3>
            <div class="meta">${total ? `${start + 1}–${start + rows.length} of ${total}` : "0 of 0"} · click a row to see their POs</div>
          </div>
          <div class="filter-bar"><span class="fb-label">Search</span>${search_box_html(
				P.state.suppliers_search,
				"Supplier name…"
			)}</div>
          <table class="mini-table">
            <thead><tr><th>Supplier</th><th>POs</th><th>Total Value</th><th>Fully Received</th><th>Pending</th><th>Avg Lead Time</th></tr></thead>
            <tbody>${row_html}</tbody>
          </table>
        </div>
        <div style="display:flex;justify-content:center;gap:10px;margin-top:18px">
          <button class="backbtn suppliers-prev" ${has_prev ? "" : 'disabled style="opacity:.4;cursor:default"'}>← Prev</button>
          <button class="backbtn suppliers-next" ${has_next ? "" : 'disabled style="opacity:.4;cursor:default"'}>Next →</button>
        </div>
    `);

	P.$tab_body.find(".suppliers-row").on("click", function () {
		P.state.suppliers_selected = $(this).data("supplier");
		P.load_suppliers();
	});
	bind_search_box(P.$tab_body, P.state.suppliers_search, (v) => {
		P.state.suppliers_search = v;
		P.state.suppliers_page = 0;
		P.load_suppliers();
	});
	P.$tab_body.find(".suppliers-prev").on("click", function () {
		if (!has_prev) return;
		P.state.suppliers_page = Math.max(0, page - 1);
		P.load_suppliers();
	});
	P.$tab_body.find(".suppliers-next").on("click", function () {
		if (!has_next) return;
		P.state.suppliers_page = page + 1;
		P.load_suppliers();
	});
};

// Drilling into one supplier's POs reuses get_procurement's own `supplier`
// param (exact match) rather than a new method -- its `purchase_orders`
// shape (with receipt_name/receipt_date already resolved) is exactly what's
// needed here too.
frappe.pages["stock-dashboard"].load_supplier_pos = function () {
	const P = frappe.pages["stock-dashboard"];
	const supplier = P.state.suppliers_selected;
	const key = `supplier_pos:${P.state.company}:${supplier}`;
	if (P.state.cache[key]) return P.render_supplier_pos(P.state.cache[key]);
	P.$tab_body.html('<div class="loading-state">Loading purchase orders…</div>');
	const req = ++P._req;
	frappe.call({
		method: "upande_stores.upande_stores.page.stock_dashboard.stock_dashboard.get_procurement",
		args: { company: P.state.company, supplier: supplier },
		callback: function (r) {
			if (req !== P._req) return;
			P.state.cache[key] = r.message || { purchase_orders: [] };
			P.render_supplier_pos(P.state.cache[key]);
		},
	});
};

frappe.pages["stock-dashboard"].render_supplier_pos = function (data) {
	const P = frappe.pages["stock-dashboard"];
	const po_rows = (data.purchase_orders || [])
		.map(
			(po) => `
        <tr>
          <td>${drill_link("purchase-order", po.name)}</td>
          <td>${fmt_date(po.transaction_date)}</td>
          <td>${frappe.utils.escape_html(po.status || "—")}</td>
          <td>${fmt_money(po.grand_total)}</td>
          <td>${
				po.receipt_name
					? `${drill_link("purchase-receipt", po.receipt_name)} · ${fmt_date(po.receipt_date)}`
					: '<span style="color:var(--ink-mute)">Not yet received</span>'
			}</td>
        </tr>`
		)
		.join("");

	P.$tab_body.html(`
        <button class="backbtn suppliers-back">← Back to Suppliers</button>
        <div class="card card--padded">
          <div class="card__head"><h3>${frappe.utils.escape_html(P.state.suppliers_selected)}</h3><div class="meta">${
				(data.purchase_orders || []).length
			} Purchase Orders</div></div>
          <table class="mini-table">
            <thead><tr><th>PO</th><th>Date</th><th>Status</th><th>Amount</th><th>Receipt</th></tr></thead>
            <tbody>${po_rows || '<tr><td colspan="5" style="text-align:center;color:var(--ink-mute);padding:24px">No Purchase Orders.</td></tr>'}</tbody>
          </table>
        </div>
    `);

	P.$tab_body.find(".suppliers-back").on("click", function () {
		P.state.suppliers_selected = null;
		P.load_suppliers();
	});
};
