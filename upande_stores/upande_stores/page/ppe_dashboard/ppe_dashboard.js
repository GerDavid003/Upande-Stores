// Page: ppe-dashboard — PPE Dashboard
//
// Layout:
//   [ pagehead: title + company switcher ]
//   [ tabs: Overview | Assignments | Requests | Procurement ]
//   [ tab body ]  <-- OR -->  [ detail body: employee / request drill-down ]
//
// Uses real Frappe routing for drill-downs (frappe.set_route), consumed on
// every on_page_show (not just first load) -- see handle_route below.
frappe.pages["ppe-dashboard"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "PPE Dashboard",
		single_column: true,
	});
	frappe.pages["ppe-dashboard"].add_styles();
	frappe.pages["ppe-dashboard"].make(page);
};

// Fires on every visit (first load AND every return trip), unlike
// on_page_load which only fires once -- the correct place to react to
// frappe.get_route() for a drill-down link clicked elsewhere (e.g. a report
// row) while this page instance is already alive.
frappe.pages["ppe-dashboard"].on_page_show = function () {
	const P = frappe.pages["ppe-dashboard"];
	if (!P.page) return; // on_page_load hasn't built the page yet
	P._wait_then_route();
};

// Companies load asynchronously on first build; if a route arrives before
// that finishes, wait briefly rather than rendering a dashboard with no
// company selected. Mirrors the retry-loop sales_allocation.js uses while
// its own async location_config loads.
frappe.pages["ppe-dashboard"]._wait_then_route = function (tries) {
	const P = frappe.pages["ppe-dashboard"];
	tries = tries || 0;
	if (P.companies_loaded || tries > 50) {
		P.handle_route();
		return;
	}
	setTimeout(() => P._wait_then_route(tries + 1), 100);
};

frappe.pages["ppe-dashboard"].add_styles = function () {
	if (document.getElementById("ppe-dashboard-styles")) return;
	if (!document.getElementById("ppe-dashboard-fonts")) {
		const fontLink = document.createElement("link");
		fontLink.id = "ppe-dashboard-fonts";
		fontLink.rel = "stylesheet";
		fontLink.href =
			"https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600&display=swap";
		document.head.appendChild(fontLink);
	}
	const styleEl = document.createElement("style");
	styleEl.id = "ppe-dashboard-styles";
	// ufd-modern design system, copied from the Dashboard Designs mockups and
	// scoped entirely under .ppe-dash so none of these (deliberately generic)
	// class names -- .card, .list, .tile, .tabs, ... -- ever leak into the
	// rest of Desk.
	styleEl.textContent = `
        .ppe-dash {
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
        .ppe-dash *{box-sizing:border-box}
        .ppe-dash, .ppe-dash input, .ppe-dash select, .ppe-dash button { font-family:var(--sans); }
        .ppe-dash a{color:inherit;text-decoration:none}

        .ppe-dash .pagehead{display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;gap:20px;margin-bottom:24px}
        .ppe-dash .pagehead__eyebrow{font:500 11px var(--sans);text-transform:uppercase;letter-spacing:2.2px;color:var(--ink-mute);margin-bottom:8px;display:inline-flex;align-items:center;gap:10px}
        .ppe-dash .pagehead__eyebrow::before{content:"";width:18px;height:1px;background:var(--ink-3)}
        .ppe-dash .pagehead__title{font:600 36px/1.05 var(--sans);color:var(--ink);letter-spacing:-1.1px;margin:0}
        .ppe-dash .pagehead__sub{margin-top:6px;font-size:14px;color:var(--ink-4)}
        .ppe-dash .pagehead__tools{display:flex;gap:10px;align-items:center}

        .ppe-dash .datepill{display:inline-flex;align-items:center;gap:8px;background:var(--surface-2);border-radius:999px;padding:6px 16px;font:500 12px var(--sans);color:var(--ink);box-shadow:var(--shadow-card)}
        .ppe-dash .datepill label{font:600 9px var(--sans);text-transform:uppercase;letter-spacing:1px;color:var(--ink-faint);margin:0 2px 0 0;white-space:nowrap}
        .ppe-dash .datepill .frappe-control{min-width:170px}
        .ppe-dash .datepill .form-group{margin:0}
        .ppe-dash .datepill .control-label,
        .ppe-dash .datepill .help-box{display:none}
        .ppe-dash .datepill input.form-control{border:0;box-shadow:none;padding:2px 0;font:600 13px var(--sans);color:var(--ink);background:transparent}
        .ppe-dash .datepill input.form-control:focus{box-shadow:none}

        .ppe-dash .tabs{display:inline-flex;gap:4px;margin-bottom:24px;background:rgba(10,10,10,0.04);padding:5px;border-radius:999px;max-width:100%;overflow-x:auto}
        .ppe-dash .tab{background:transparent;border:0;font:500 13px var(--sans);color:var(--ink-4);padding:9px 18px;border-radius:999px;cursor:pointer;white-space:nowrap;transition:all .2s}
        .ppe-dash .tab:hover{color:var(--ink)}
        .ppe-dash .tab.on{background:var(--grad-ink);color:#fafaf6;box-shadow:0 4px 14px rgba(10,10,10,0.20)}

        .ppe-dash .kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;margin-bottom:24px}
        .ppe-dash .kpi{background:var(--surface-2);border-radius:18px;padding:22px 24px;box-shadow:var(--shadow-card);transition:all .25s;position:relative;overflow:hidden}
        .ppe-dash .kpi:hover{transform:translateY(-2px);box-shadow:var(--shadow-hover)}
        .ppe-dash .kpi__label{font:500 11px var(--sans);text-transform:uppercase;letter-spacing:1.6px;color:var(--ink-mute);margin-bottom:12px}
        .ppe-dash .kpi__value{font:600 36px/1 var(--sans);color:var(--ink);letter-spacing:-1.1px;font-feature-settings:"tnum"}
        .ppe-dash .kpi__unit{font:400 13px var(--sans);color:var(--ink-mute);margin-top:6px}
        .ppe-dash .kpi__trend{margin-top:14px;display:inline-flex;align-items:center;gap:6px;font:500 12px var(--sans)}
        .ppe-dash .kpi__trend.up{color:#1a8a3a}
        .ppe-dash .kpi__trend.down{color:#c4302b}
        .ppe-dash .kpi__trend.flat{color:var(--ink-mute)}
        .ppe-dash .kpi__trend small{color:var(--ink-mute);font-weight:400}

        .ppe-dash .card{background:var(--surface-2);border-radius:20px;padding:24px 26px;box-shadow:var(--shadow-card);margin-bottom:16px}
        .ppe-dash .card--padded{padding:28px 30px}
        .ppe-dash .card__head{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:18px;gap:20px;flex-wrap:wrap}
        .ppe-dash .card__head h3{margin:0;font:600 16px var(--sans);color:var(--ink);letter-spacing:-.3px}
        .ppe-dash .card__head .meta{font:500 12px var(--sans);color:var(--ink-mute)}

        .ppe-dash .row-2{display:grid;grid-template-columns:2fr 1fr;gap:16px;margin-bottom:16px}
        .ppe-dash .row-2-eq{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}

        .ppe-dash .list{display:flex;flex-direction:column}
        .ppe-dash .list__row{display:grid;grid-template-columns:1fr auto;gap:14px;padding:12px 8px;border-bottom:1px solid var(--hairline);align-items:center;cursor:pointer;transition:background .2s;border-radius:10px}
        .ppe-dash .list__row:hover{background:rgba(10,10,10,0.02)}
        .ppe-dash .list__row:last-child{border-bottom:0}
        .ppe-dash .list__row.static{cursor:default}
        .ppe-dash .list__name{font:600 14px var(--sans);color:var(--ink)}
        .ppe-dash .list__meta{font-size:12px;color:var(--ink-mute);margin-top:2px}
        .ppe-dash .list__qty{font:600 15px var(--sans);color:var(--ink);font-variant-numeric:tabular-nums;text-align:right}
        .ppe-dash .list__empty{padding:28px 8px;text-align:center;color:var(--ink-mute);font-size:13px}

        .ppe-dash .tilegrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px}
        .ppe-dash .tile{background:var(--surface-2);border-radius:18px;padding:20px 22px;box-shadow:var(--shadow-card);cursor:pointer;transition:all .2s;display:block}
        .ppe-dash .tile:hover{transform:translateY(-2px);box-shadow:var(--shadow-hover)}
        .ppe-dash .tile__head{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;gap:10px}
        .ppe-dash .tile__name{font:600 14px var(--sans);color:var(--ink);letter-spacing:-.1px}
        .ppe-dash .tile__sub{font-size:11.5px;color:var(--ink-mute);margin-top:2px}
        .ppe-dash .tile__chip{display:inline-block;padding:3px 10px;font:600 10.5px var(--sans);background:rgba(34,136,131,0.10);color:var(--signal);border-radius:99px;white-space:nowrap}
        .ppe-dash .tile__chip.neg{background:rgba(196,48,43,0.10);color:#c4302b}
        .ppe-dash .tile__stats{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
        .ppe-dash .tile__stats div small{font:500 10px var(--sans);text-transform:uppercase;letter-spacing:1px;color:var(--ink-mute);display:block;margin-bottom:2px}
        .ppe-dash .tile__stats div b{font:600 15px var(--sans);color:var(--ink);font-variant-numeric:tabular-nums}

        .ppe-dash .hb{display:grid;grid-template-columns:140px 1fr 56px;gap:16px;align-items:center;padding:9px 0;border-bottom:1px solid var(--hairline)}
        .ppe-dash .hb:last-child{border-bottom:0}
        .ppe-dash .hb__name{font:600 12.5px var(--sans);color:var(--ink)}
        .ppe-dash .hb__lane{position:relative;height:16px}
        .ppe-dash .hb__est{position:absolute;left:0;top:0;height:16px;width:100%;background:rgba(10,10,10,0.05);border-radius:999px}
        .ppe-dash .hb__act{position:absolute;left:0;top:2px;height:12px;border-radius:999px;background:var(--grad-ink)}
        .ppe-dash .hb__act.high{background:linear-gradient(90deg,#1a8a3a,#22c55e)}
        .ppe-dash .hb__act.mid{background:linear-gradient(90deg,#9a5a00,#f59e0b)}
        .ppe-dash .hb__act.low{background:linear-gradient(90deg,#7a2218,#c4302b)}
        .ppe-dash .hb__pct{font:600 13px var(--sans);text-align:right;color:var(--ink-3);font-variant-numeric:tabular-nums}

        .ppe-dash .funnel{padding:10px 0 4px;display:flex;flex-direction:column;gap:12px}
        .ppe-dash .funnel__stage{display:grid;grid-template-columns:1fr auto;align-items:center;gap:16px}
        .ppe-dash .funnel__bar{height:52px;display:flex;align-items:center;padding:0 22px;font:600 14px var(--sans);color:#fafaf6;border-radius:12px;letter-spacing:-.1px;min-width:120px;transition:width .3s}
        .ppe-dash .funnel__meta{font:500 11.5px var(--sans);color:var(--ink-mute);min-width:140px;text-align:right}
        .ppe-dash .funnel__meta b{display:block;font:600 20px var(--sans);color:var(--ink);font-variant-numeric:tabular-nums}

        .ppe-dash .backbtn{display:inline-flex;align-items:center;gap:8px;font:500 13px var(--sans);color:var(--ink-4);cursor:pointer;padding:8px 16px;border-radius:999px;background:rgba(10,10,10,0.04);margin-bottom:20px;transition:all .2s;border:0}
        .ppe-dash .backbtn:hover{background:var(--ink);color:#fafaf6}

        .ppe-dash .hero{background:var(--surface-2);border-radius:24px;padding:36px 38px;box-shadow:var(--shadow-card);margin-bottom:16px;background-image:radial-gradient(circle at 95% 5%,rgba(34,136,131,0.08),transparent 35%)}
        .ppe-dash .hero__eyebrow{font:500 11px var(--sans);text-transform:uppercase;letter-spacing:2.2px;color:var(--ink-mute);margin-bottom:12px}
        .ppe-dash .hero__name{font:600 46px/0.98 var(--sans);color:var(--ink);letter-spacing:-1.4px;margin:0 0 10px}
        .ppe-dash .hero__sub{font:400 15px var(--sans);color:var(--ink-4);margin:0 0 24px}
        .ppe-dash .hero__stats{display:grid;grid-template-columns:repeat(4,1fr);gap:24px;padding-top:20px;border-top:1px solid var(--hairline)}
        .ppe-dash .hero__stat small{font:500 11px var(--sans);text-transform:uppercase;letter-spacing:1.4px;color:var(--ink-mute);display:block;margin-bottom:5px}
        .ppe-dash .hero__stat b{font:600 26px var(--sans);color:var(--ink);letter-spacing:-.5px;font-variant-numeric:tabular-nums;display:block}
        .ppe-dash .hero__stat em{font:400 12px var(--sans);font-style:normal;color:var(--ink-mute);margin-left:4px}

        .ppe-dash .legend{display:flex;gap:16px;font-size:12px;color:var(--ink-mute);flex-wrap:wrap}
        .ppe-dash .legend span{display:inline-flex;align-items:center;gap:6px}
        .ppe-dash .legend i{width:10px;height:10px;border-radius:50%;display:inline-block}

        .ppe-dash .pillgroup{display:inline-flex;background:rgba(10,10,10,0.04);border-radius:999px;padding:4px;gap:2px;flex-wrap:wrap}
        .ppe-dash .pillgroup button{border:0;background:transparent;font:500 12px var(--sans);color:var(--ink-4);padding:7px 14px;cursor:pointer;border-radius:999px;transition:all .2s;white-space:nowrap}
        .ppe-dash .pillgroup button.on{background:var(--ink);color:#fafaf6;box-shadow:0 2px 8px rgba(10,10,10,0.15)}

        .ppe-dash .status-chip{display:inline-block;padding:3px 10px;font:600 11px var(--sans);border-radius:99px;white-space:nowrap}

        .ppe-dash .empty-state, .ppe-dash .loading-state{text-align:center;padding:48px 20px;color:var(--ink-mute);font-size:13px}

        .ppe-dash .mini-table{width:100%;border-collapse:collapse;font-size:12.5px}
        .ppe-dash .mini-table th{text-align:left;padding:8px 10px;font:600 10px var(--sans);text-transform:uppercase;letter-spacing:.7px;color:var(--ink-faint);border-bottom:1px solid var(--hairline);white-space:nowrap}
        .ppe-dash .mini-table td{padding:9px 10px;border-bottom:1px solid var(--hairline);color:var(--ink-3);vertical-align:middle}
        .ppe-dash .mini-table tbody tr:last-child td{border-bottom:0}
        .ppe-dash .mini-table tbody tr:hover{background:rgba(10,10,10,0.02)}
        .ppe-dash .link-cell{color:var(--signal);font-weight:600;cursor:pointer}
        .ppe-dash .link-cell:hover{text-decoration:underline}

        @media (max-width:1000px){.ppe-dash .row-2,.ppe-dash .row-2-eq{grid-template-columns:1fr}.ppe-dash .hero__name{font-size:32px}.ppe-dash .hero__stats{grid-template-columns:repeat(2,1fr)}}
    `;
	document.head.appendChild(styleEl);
};

// ============================================================
// Build
// ============================================================
frappe.pages["ppe-dashboard"].make = function (page) {
	const P = frappe.pages["ppe-dashboard"];
	P.page = page;
	P.companies_loaded = false;
	P.state = {
		company: null,
		companies: [],
		active_tab: "overview",
		assignment_status_filter: "All",
		assignment_page: 0,
		cache: {}, // "<tab>:<company>[:<status>:<page>]" -> data
	};
	P._req = 0; // request-id guard against stale frappe.call responses

	const $container = $(`
        <div class="ppe-dash">
          <div class="pagehead">
            <div>
              <div class="pagehead__eyebrow">Upande Stores · PPE</div>
              <h1 class="pagehead__title">PPE Dashboard</h1>
              <p class="pagehead__sub">Issuance, requests, and procurement for personal protective equipment</p>
            </div>
            <div class="pagehead__tools">
              <div class="datepill"><label>Company</label><div class="ppe-dash-company-field"></div></div>
            </div>
          </div>
          <div class="ppe-dash-tabs">
            <div class="tabs">
              <button class="tab on" data-tab="overview">Overview</button>
              <button class="tab" data-tab="assignments">Assignments</button>
              <button class="tab" data-tab="requests">Requests</button>
              <button class="tab" data-tab="procurement">Procurement</button>
            </div>
            <div class="ppe-dash-tab-body"><div class="loading-state">Loading…</div></div>
          </div>
          <div class="ppe-dash-detail-body" style="display:none"></div>
        </div>
    `).appendTo(page.main);

	P.$wrapper = $container;
	P.$tabs_section = $container.find(".ppe-dash-tabs");
	P.$tab_body = $container.find(".ppe-dash-tab-body");
	P.$detail_body = $container.find(".ppe-dash-detail-body");

	P.$wrapper.on("click", ".tabs .tab", function () {
		P.switch_tab($(this).data("tab"));
	});

	P.make_company_field($container.find(".ppe-dash-company-field"));
	P.load_companies();
};

frappe.pages["ppe-dashboard"].make_company_field = function ($parent) {
	const P = frappe.pages["ppe-dashboard"];
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
				P.state.assignment_page = 0; // a new company has a different total, page 3 may no longer exist
				P.render_active();
			},
		},
		only_input: true,
		render_input: true,
	});
	P.company_control.refresh();
};

frappe.pages["ppe-dashboard"].load_companies = function () {
	const P = frappe.pages["ppe-dashboard"];
	frappe.call({
		method: "upande_stores.upande_stores.page.ppe_dashboard.ppe_dashboard.get_companies",
		callback: function (r) {
			const data = r.message || {};
			P.state.companies = data.companies || [];
			const default_company =
				data.default_company && (data.default_company || P.state.companies.includes(data.default_company))
					? data.default_company
					: P.state.companies[0];
			P.state.company = default_company || null;
			if (P.state.company) {
				P.company_control.set_value(P.state.company);
			}
			P.companies_loaded = true;
			P.handle_route();
		},
	});
};

// ============================================================
// Routing: dashboard tabs vs. drill-down detail views
// ============================================================
frappe.pages["ppe-dashboard"].handle_route = function () {
	const P = frappe.pages["ppe-dashboard"];
	if (!P.companies_loaded) return; // _wait_then_route will retry
	const route = frappe.get_route(); // ["ppe-dashboard", view?, id?]
	const view = route[1];
	const id = route[2];
	if (view === "employee" && id) {
		P.show_employee_detail(id);
	} else if (view === "request" && id) {
		P.show_request_detail(id);
	} else {
		P.show_dashboard();
	}
};

frappe.pages["ppe-dashboard"].show_dashboard = function () {
	const P = frappe.pages["ppe-dashboard"];
	P.$detail_body.hide().empty();
	P.$tabs_section.show();
	P.render_active();
};

frappe.pages["ppe-dashboard"].switch_tab = function (tab) {
	const P = frappe.pages["ppe-dashboard"];
	P.state.active_tab = tab;
	P.$wrapper.find(".tabs .tab").removeClass("on");
	P.$wrapper.find(`.tabs .tab[data-tab="${tab}"]`).addClass("on");
	P.render_active();
};

frappe.pages["ppe-dashboard"].render_active = function () {
	const P = frappe.pages["ppe-dashboard"];
	if (!P.state.company) {
		P.$tab_body.html('<div class="empty-state">Select a Company to see PPE data.</div>');
		return;
	}
	const tab = P.state.active_tab;
	if (tab === "overview") P.load_overview();
	else if (tab === "assignments") P.load_assignments();
	else if (tab === "requests") P.load_requests();
	else if (tab === "procurement") P.load_procurement();
};

// ============================================================
// Tab 1: Overview
// ============================================================
frappe.pages["ppe-dashboard"].load_overview = function () {
	const P = frappe.pages["ppe-dashboard"];
	const key = "overview:" + P.state.company;
	if (P.state.cache[key]) {
		P.render_overview(P.state.cache[key]);
		return;
	}
	P.$tab_body.html('<div class="loading-state">Loading overview…</div>');
	const req = ++P._req;
	frappe.call({
		method: "upande_stores.upande_stores.page.ppe_dashboard.ppe_dashboard.get_overview",
		args: { company: P.state.company },
		callback: function (r) {
			if (req !== P._req) return; // a newer tab/company switch superseded this
			P.state.cache[key] = r.message || {};
			P.render_overview(P.state.cache[key]);
		},
	});
};

frappe.pages["ppe-dashboard"].render_overview = function (data) {
	const P = frappe.pages["ppe-dashboard"];
	const fmt_money = (v) => frappe.format(v || 0, { fieldtype: "Currency" });
	const kpis = [
		{ label: "Active Assignments", value: data.active_assignments || 0, unit: "employees issued PPE" },
		{ label: "Expiring in 30 Days", value: data.expiring_30d || 0, unit: "active assignments" },
		{ label: "Pending Issuance Requests", value: data.pending_issuance || 0, unit: "not fully issued" },
		{ label: "Pending Purchase Requests", value: data.pending_purchase || 0, unit: "not fully ordered" },
		{ label: "PPE Spend · 90 Days", value: fmt_money(data.period_spend), unit: "received value", is_money: true },
	];

	const kpi_html = kpis
		.map(
			(k) => `
        <div class="kpi">
          <div class="kpi__label">${frappe.utils.escape_html(k.label)}</div>
          <div class="kpi__value">${k.is_money ? k.value : frappe.utils.escape_html(String(k.value))}</div>
          <div class="kpi__unit">${frappe.utils.escape_html(k.unit)}</div>
        </div>`
		)
		.join("");

	const max_count = Math.max(1, ...(data.status_breakdown || []).map((s) => s.count));
	const status_html = (data.status_breakdown || [])
		.map(
			(s) => `
        <div class="hb">
          <div class="hb__name">${frappe.utils.escape_html(s.status)}</div>
          <div class="hb__lane">
            <div class="hb__est"></div>
            <div class="hb__act" style="width:${(s.count / max_count) * 100}%;background:${s.color}"></div>
          </div>
          <div class="hb__pct">${s.count}</div>
        </div>`
		)
		.join("");

	P.$tab_body.html(`
        <div class="kpi-grid">${kpi_html}</div>
        <div class="card card--padded">
          <div class="card__head"><h3>Assignment Status Breakdown</h3><div class="meta">${frappe.utils.escape_html(
				P.state.company
			)}</div></div>
          ${status_html || '<div class="empty-state">No Employee PPE Assignments for this company yet.</div>'}
        </div>
    `);
};

// ============================================================
// Tab 2: Assignments
// ============================================================
const PPE_ASSIGNMENTS_PAGE_LENGTH = 50;

frappe.pages["ppe-dashboard"].load_assignments = function () {
	const P = frappe.pages["ppe-dashboard"];
	const status = P.state.assignment_status_filter || "All";
	const page = P.state.assignment_page || 0;
	const start = page * PPE_ASSIGNMENTS_PAGE_LENGTH;
	// Status + page are now genuinely different server responses (filtering
	// and pagination both happen server-side), not client-side slices of one
	// cached array -- so both must be part of the cache key.
	const key = `assignments:${P.state.company}:${status}:${page}`;
	if (P.state.cache[key]) {
		P.render_assignments(P.state.cache[key]);
		return;
	}
	P.$tab_body.html('<div class="loading-state">Loading assignments…</div>');
	const req = ++P._req;
	frappe.call({
		method: "upande_stores.upande_stores.page.ppe_dashboard.ppe_dashboard.get_assignments",
		args: {
			company: P.state.company,
			status: status,
			start: start,
			page_length: PPE_ASSIGNMENTS_PAGE_LENGTH,
		},
		callback: function (r) {
			if (req !== P._req) return;
			P.state.cache[key] = r.message || { rows: [], total: 0 };
			P.render_assignments(P.state.cache[key]);
		},
	});
};

// Builds an <a> to a real Desk document (frappe.utils.get_form_link is the
// same canonical helper Frappe's own core UI uses to build these URLs --
// verified it emits "/desk/<doctype-slug>/<name>", this site's actual
// canonical Desk route prefix). Opens in a new tab so clicking a PO/Receipt
// doesn't lose the dashboard's current tab/scroll/filter state -- that rules
// out get_form_link's own html=true shortcut, which doesn't support target.
function ppe_dash_doc_link(doctype, name, display_text) {
	if (!name) return "—";
	const href = frappe.utils.get_form_link(doctype, name);
	return `<a href="${href}" target="_blank" rel="noopener">${frappe.utils.escape_html(display_text || name)}</a>`;
}

const PPE_STATUS_COLORS = {
	Active: "#1a8a3a",
	Expired: "#c4302b",
	Returned: "#f59e0b",
	Replaced: "#2563eb",
	Inactive: "#8a8780",
};

frappe.pages["ppe-dashboard"].render_assignments = function (data) {
	const P = frappe.pages["ppe-dashboard"];
	const rows = data.rows || [];
	const total = data.total || 0;
	const filter = P.state.assignment_status_filter || "All";
	const page = P.state.assignment_page || 0;
	const start = page * PPE_ASSIGNMENTS_PAGE_LENGTH;
	const has_prev = page > 0;
	const has_next = start + rows.length < total;

	const statuses = ["All", "Active", "Inactive", "Expired", "Returned", "Replaced"];
	const filter_html = statuses
		.map((s) => `<button class="${s === filter ? "on" : ""}" data-status="${s}">${s}</button>`)
		.join("");

	const tiles_html = rows.length
		? rows
				.map((r) => {
					const color = PPE_STATUS_COLORS[r.status] || "#8a8780";
					return `
            <a class="tile" data-employee="${frappe.utils.escape_html(r.employee)}">
              <div class="tile__head">
                <div>
                  <div class="tile__name">${frappe.utils.escape_html(r.employee_name || r.employee)}</div>
                  <div class="tile__sub">${frappe.utils.escape_html(r.item_name || r.item_code)}</div>
                </div>
                <span class="status-chip" style="background:${color}22;color:${color}">${frappe.utils.escape_html(
						r.status
					)}</span>
              </div>
              <div class="tile__stats">
                <div><small>Issue Date</small><b>${r.issue_date ? frappe.datetime.str_to_user(r.issue_date) : "—"}</b></div>
                <div><small>Expiry</small><b>${r.expiry_date ? frappe.datetime.str_to_user(r.expiry_date) : "—"}</b></div>
              </div>
            </a>`;
				})
				.join("")
		: '<div class="empty-state">No assignments match this filter.</div>';

	const range_label = total
		? `${start + 1}–${start + rows.length} of ${total}`
		: "0 of 0";

	P.$tab_body.html(`
        <div class="card card--padded">
          <div class="card__head">
            <h3>Employee PPE Assignments</h3>
            <div class="meta">${range_label}</div>
          </div>
          <div class="pillgroup ppe-assignment-filter">${filter_html}</div>
        </div>
        <div class="tilegrid">${tiles_html}</div>
        <div class="ppe-assignment-pager" style="display:flex;justify-content:center;gap:10px;margin-top:18px">
          <button class="backbtn ppe-assignment-prev" ${has_prev ? "" : "disabled style=\"opacity:.4;cursor:default\""}>← Prev</button>
          <button class="backbtn ppe-assignment-next" ${has_next ? "" : "disabled style=\"opacity:.4;cursor:default\""}>Next →</button>
        </div>
    `);

	P.$tab_body.find(".ppe-assignment-filter button").on("click", function () {
		const new_status = $(this).data("status");
		if (new_status === P.state.assignment_status_filter) return;
		P.state.assignment_status_filter = new_status;
		P.state.assignment_page = 0; // re-fetch from the top of the new filter, don't re-render stale rows
		P.load_assignments();
	});
	P.$tab_body.find(".ppe-assignment-prev").on("click", function () {
		if (!has_prev) return;
		P.state.assignment_page = Math.max(0, page - 1);
		P.load_assignments();
	});
	P.$tab_body.find(".ppe-assignment-next").on("click", function () {
		if (!has_next) return;
		P.state.assignment_page = page + 1;
		P.load_assignments();
	});
	P.$tab_body.find(".tile[data-employee]").on("click", function () {
		frappe.set_route("ppe-dashboard", "employee", $(this).data("employee"));
	});
};

// ============================================================
// Tab 3: Requests
// ============================================================
frappe.pages["ppe-dashboard"].load_requests = function () {
	const P = frappe.pages["ppe-dashboard"];
	const key = "requests:" + P.state.company;
	if (P.state.cache[key]) {
		P.render_requests(P.state.cache[key]);
		return;
	}
	P.$tab_body.html('<div class="loading-state">Loading requests…</div>');
	const req = ++P._req;
	frappe.call({
		method: "upande_stores.upande_stores.page.ppe_dashboard.ppe_dashboard.get_requests",
		args: { company: P.state.company },
		callback: function (r) {
			if (req !== P._req) return;
			P.state.cache[key] = r.message || { issuance: [], purchase: [] };
			P.render_requests(P.state.cache[key]);
		},
	});
};

frappe.pages["ppe-dashboard"].render_requests = function (data) {
	const P = frappe.pages["ppe-dashboard"];
	const issuance_rows = (data.issuance || [])
		.map(
			(r) => `
        <div class="list__row" data-request="${frappe.utils.escape_html(r.name)}">
          <div>
            <div class="list__name">${frappe.utils.escape_html(r.name)}</div>
            <div class="list__meta">${r.transaction_date ? frappe.datetime.str_to_user(r.transaction_date) : "—"} ·
              ${r.item_count} item(s) · ${frappe.utils.escape_html(r.employees || "—")}</div>
          </div>
          <span class="status-chip" style="background:${r.fully_issued ? "#1a8a3a22" : "#f59e0b22"};color:${
				r.fully_issued ? "#1a8a3a" : "#9a5a00"
			}">${r.fully_issued ? "Fully Issued" : "Pending"}</span>
        </div>`
		)
		.join("");

	const purchase_rows = (data.purchase || [])
		.map(
			(r) => `
        <div class="list__row" data-request="${frappe.utils.escape_html(r.name)}">
          <div>
            <div class="list__name">${frappe.utils.escape_html(r.name)}</div>
            <div class="list__meta">${r.transaction_date ? frappe.datetime.str_to_user(r.transaction_date) : "—"} ·
              ${r.item_count} item(s) · ${frappe.utils.escape_html(r.status || "")}</div>
          </div>
          <div class="list__qty">${flt(r.per_ordered || 0).toFixed(0)}% ordered<br><span style="font-weight:400;font-size:11px;color:var(--ink-mute)">${flt(
				r.per_received || 0
			).toFixed(0)}% received</span></div>
        </div>`
		)
		.join("");

	P.$tab_body.html(`
        <div class="row-2-eq">
          <div class="card card--padded">
            <div class="card__head"><h3>Issuance Requests</h3><div class="meta">${(data.issuance || []).length} shown</div></div>
            <div class="list">${issuance_rows || '<div class="list__empty">No PPE issuance requests for this company.</div>'}</div>
          </div>
          <div class="card card--padded">
            <div class="card__head"><h3>Purchase Requests</h3><div class="meta">${(data.purchase || []).length} shown</div></div>
            <div class="list">${purchase_rows || '<div class="list__empty">No PPE purchase requests for this company.</div>'}</div>
          </div>
        </div>
    `);

	P.$tab_body.find(".list__row[data-request]").on("click", function () {
		frappe.set_route("ppe-dashboard", "request", $(this).data("request"));
	});
};

// ============================================================
// Tab 4: Procurement
// ============================================================
frappe.pages["ppe-dashboard"].load_procurement = function () {
	const P = frappe.pages["ppe-dashboard"];
	const key = "procurement:" + P.state.company;
	if (P.state.cache[key]) {
		P.render_procurement(P.state.cache[key]);
		return;
	}
	P.$tab_body.html('<div class="loading-state">Loading procurement pipeline…</div>');
	const req = ++P._req;
	frappe.call({
		method: "upande_stores.upande_stores.page.ppe_dashboard.ppe_dashboard.get_procurement",
		args: { company: P.state.company },
		callback: function (r) {
			if (req !== P._req) return;
			P.state.cache[key] = r.message || { funnel: [], purchase_orders: [] };
			P.render_procurement(P.state.cache[key]);
		},
	});
};

frappe.pages["ppe-dashboard"].render_procurement = function (data) {
	const P = frappe.pages["ppe-dashboard"];
	const bg_by_stage = [
		"var(--grad-ink)",
		"linear-gradient(135deg,#3a3a34,#6a6a60)",
		"linear-gradient(135deg,var(--signal),#73b3a0)",
	];
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
          <td>${ppe_dash_doc_link("Purchase Order", po.name)}</td>
          <td>${frappe.utils.escape_html(po.supplier || "—")}</td>
          <td>${po.transaction_date ? frappe.datetime.str_to_user(po.transaction_date) : "—"}</td>
          <td>${frappe.utils.escape_html(po.status || "—")}</td>
          <td>${frappe.format(po.grand_total || 0, { fieldtype: "Currency" })}</td>
          <td>${
				po.receipt_name
					? `${ppe_dash_doc_link("Purchase Receipt", po.receipt_name)} · ${frappe.datetime.str_to_user(po.receipt_date)}`
					: '<span style="color:var(--ink-mute)">Not yet received</span>'
			}</td>
        </tr>`
		)
		.join("");

	P.$tab_body.html(`
        <div class="card card--padded">
          <div class="card__head"><h3>PPE Procurement Funnel</h3><div class="meta">Request → Order → Receipt</div></div>
          <div class="funnel">${funnel_html || '<div class="empty-state">No PPE purchase activity for this company.</div>'}</div>
        </div>
        <div class="card card--padded">
          <div class="card__head"><h3>Purchase Orders from PPE Requests</h3><div class="meta">${(data.purchase_orders || []).length} shown</div></div>
          <table class="mini-table">
            <thead><tr><th>PO</th><th>Supplier</th><th>Date</th><th>Status</th><th>Amount</th><th>Receipt</th></tr></thead>
            <tbody>${po_rows || '<tr><td colspan="6" style="text-align:center;color:var(--ink-mute);padding:24px">No Purchase Orders yet.</td></tr>'}</tbody>
          </table>
        </div>
    `);
};

// ============================================================
// Drill-down: Employee detail
// ============================================================
frappe.pages["ppe-dashboard"].show_employee_detail = function (employee) {
	const P = frappe.pages["ppe-dashboard"];
	P.$tabs_section.hide();
	P.$detail_body.show().html('<div class="loading-state">Loading employee…</div>');
	const req = ++P._req;
	frappe.call({
		method: "upande_stores.upande_stores.page.ppe_dashboard.ppe_dashboard.get_employee_detail",
		args: { employee },
		callback: function (r) {
			if (req !== P._req) return;
			P.render_employee_detail(r.message || {});
		},
	});
};

frappe.pages["ppe-dashboard"].render_employee_detail = function (data) {
	const P = frappe.pages["ppe-dashboard"];
	const emp = data.employee || {};
	const history = data.history || [];

	const rows_html = history.length
		? history
				.map(
					(h) => `
        <tr>
          <td>${frappe.utils.escape_html(h.item_name || h.item_code || "—")}</td>
          <td><span class="status-chip" style="background:${(PPE_STATUS_COLORS[h.status] || "#8a8780") + "22"};color:${
						PPE_STATUS_COLORS[h.status] || "#8a8780"
					}">${frappe.utils.escape_html(h.status || "—")}</span></td>
          <td>${h.issue_date ? frappe.datetime.str_to_user(h.issue_date) : "—"}</td>
          <td>${h.expiry_date ? frappe.datetime.str_to_user(h.expiry_date) : "—"}</td>
          <td>${
				h.replacement_assignment
					? `<span class="link-cell" data-assignment="${frappe.utils.escape_html(
							h.replacement_assignment
					  )}">${frappe.utils.escape_html(h.replacement_assignment)}</span>`
					: "—"
			}</td>
        </tr>`
				)
				.join("")
		: '<tr><td colspan="5" style="text-align:center;color:var(--ink-mute);padding:24px">No PPE history.</td></tr>';

	P.$detail_body.html(`
        <button class="backbtn">← Back to Dashboard</button>
        <div class="hero">
          <div class="hero__eyebrow">${frappe.utils.escape_html(emp.company || "")} · Employee</div>
          <h1 class="hero__name">${frappe.utils.escape_html(emp.employee_name || emp.name || "")}</h1>
          <p class="hero__sub">${frappe.utils.escape_html(emp.designation || "")}${
				emp.designation && emp.department ? " · " : ""
			}${frappe.utils.escape_html(emp.department || "")}</p>
          <div class="hero__stats">
            <div class="hero__stat"><small>Total Assignments</small><b>${data.total_assignments || 0}</b></div>
            <div class="hero__stat"><small>Active</small><b>${data.active_count || 0}</b></div>
            <div class="hero__stat"><small>Expired</small><b>${data.expired_count || 0}</b></div>
            <div class="hero__stat"><small>Employee</small><b style="font-size:16px">${frappe.utils.escape_html(
				emp.name || ""
			)}</b></div>
          </div>
        </div>
        <div class="card card--padded">
          <div class="card__head"><h3>PPE History</h3><div class="meta">${history.length} record(s)</div></div>
          <table class="mini-table">
            <thead><tr><th>Item</th><th>Status</th><th>Issue Date</th><th>Expiry</th><th>Replaced By</th></tr></thead>
            <tbody>${rows_html}</tbody>
          </table>
        </div>
    `);

	P.$detail_body.find(".backbtn").on("click", function () {
		frappe.set_route("ppe-dashboard");
	});
	P.$detail_body.find(".link-cell[data-assignment]").on("click", function () {
		// Employee PPE Assignment doesn't have its own drill-down view here --
		// open the real Desk document for the replacement assignment.
		frappe.set_route("Form", "Employee PPE Assignment", $(this).data("assignment"));
	});
};

// ============================================================
// Drill-down: Request detail
// ============================================================
frappe.pages["ppe-dashboard"].show_request_detail = function (material_request) {
	const P = frappe.pages["ppe-dashboard"];
	P.$tabs_section.hide();
	P.$detail_body.show().html('<div class="loading-state">Loading request…</div>');
	const req = ++P._req;
	frappe.call({
		method: "upande_stores.upande_stores.page.ppe_dashboard.ppe_dashboard.get_request_detail",
		args: { material_request },
		callback: function (r) {
			if (req !== P._req) return;
			P.render_request_detail(r.message || {});
		},
	});
};

frappe.pages["ppe-dashboard"].render_request_detail = function (data) {
	const P = frappe.pages["ppe-dashboard"];
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
        </tr>`
				)
				.join("")
		: '<tr><td colspan="5" style="text-align:center;color:var(--ink-mute);padding:24px">No item rows.</td></tr>';

	const po_rows = (data.downstream_po || [])
		.map(
			(po) => `
        <tr>
          <td>${ppe_dash_doc_link("Purchase Order", po.name)}</td>
          <td>${frappe.utils.escape_html(po.supplier || "—")}</td>
          <td>${po.transaction_date ? frappe.datetime.str_to_user(po.transaction_date) : "—"}</td>
          <td>${frappe.utils.escape_html(po.status || "—")}</td>
          <td>${frappe.format(po.grand_total || 0, { fieldtype: "Currency" })}</td>
        </tr>`
		)
		.join("");
	const pr_rows = (data.downstream_pr || [])
		.map(
			(pr) => `
        <tr>
          <td>${ppe_dash_doc_link("Purchase Receipt", pr.name)}</td>
          <td>${pr.posting_date ? frappe.datetime.str_to_user(pr.posting_date) : "—"}</td>
          <td>${frappe.utils.escape_html(pr.status || "—")}</td>
          <td>${frappe.format(pr.grand_total || 0, { fieldtype: "Currency" })}</td>
        </tr>`
		)
		.join("");

	const downstream_html =
		mr.material_request_type === "Purchase"
			? `
        <div class="row-2-eq">
          <div class="card card--padded">
            <div class="card__head"><h3>Purchase Orders</h3><div class="meta">${(data.downstream_po || []).length}</div></div>
            <table class="mini-table">
              <thead><tr><th>PO</th><th>Supplier</th><th>Date</th><th>Status</th><th>Amount</th></tr></thead>
              <tbody>${po_rows || '<tr><td colspan="5" style="text-align:center;color:var(--ink-mute);padding:16px">None yet.</td></tr>'}</tbody>
            </table>
          </div>
          <div class="card card--padded">
            <div class="card__head"><h3>Purchase Receipts</h3><div class="meta">${(data.downstream_pr || []).length}</div></div>
            <table class="mini-table">
              <thead><tr><th>PR</th><th>Date</th><th>Status</th><th>Amount</th></tr></thead>
              <tbody>${pr_rows || '<tr><td colspan="4" style="text-align:center;color:var(--ink-mute);padding:16px">None yet.</td></tr>'}</tbody>
            </table>
          </div>
        </div>`
			: "";

	P.$detail_body.html(`
        <button class="backbtn">← Back to Dashboard</button>
        <div class="hero">
          <div class="hero__eyebrow">${frappe.utils.escape_html(mr.material_request_type || "")} · ${frappe.utils.escape_html(
				mr.company || ""
			)}</div>
          <h1 class="hero__name">${frappe.utils.escape_html(mr.name || "")}</h1>
          <p class="hero__sub">Status: ${frappe.utils.escape_html(mr.status || "—")} · ${
				mr.transaction_date ? frappe.datetime.str_to_user(mr.transaction_date) : "—"
			}</p>
          <div class="hero__stats">
            <div class="hero__stat"><small>Items</small><b>${data.item_count || 0}</b></div>
            <div class="hero__stat"><small>Total Qty</small><b>${flt(data.total_qty || 0)}</b></div>
            <div class="hero__stat"><small>Fulfillment</small><b>${flt(data.fulfillment_pct || 0).toFixed(0)}%</b></div>
            <div class="hero__stat"><small>Docstatus</small><b style="font-size:16px">${
				{ 0: "Draft", 1: "Submitted", 2: "Cancelled" }[mr.docstatus] || mr.docstatus
			}</b></div>
          </div>
        </div>
        <div class="card card--padded">
          <div class="card__head"><h3>Item Rows</h3><div class="meta">${items.length} row(s)</div></div>
          <table class="mini-table">
            <thead><tr><th>Item</th><th>Qty</th><th>Employee</th><th>Cost Center</th><th>Warehouse</th></tr></thead>
            <tbody>${item_rows}</tbody>
          </table>
        </div>
        ${downstream_html}
    `);

	P.$detail_body.find(".backbtn").on("click", function () {
		frappe.set_route("ppe-dashboard");
	});
};
