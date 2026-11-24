// Page: bulk-ppe-inspection — Bulk PPE Inspection
//
// Pure batch front-end: loads Employee PPE Assignment candidates for a
// Farm/Company into a flat table, lets a supervisor mark each OK/Worn
// Out/Lost in one sitting, then submits them as ordinary PPE Inspection
// documents (one per employee) through the exact same doc.insert()/
// doc.submit() code path a manual single-employee entry already uses.
// Deliberately plain Desk styling -- no custom CSS injected.
frappe.pages["bulk-ppe-inspection"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Bulk PPE Inspection",
		single_column: true,
	});

	frappe.pages["bulk-ppe-inspection"].make(page);
};

frappe.pages["bulk-ppe-inspection"].make = function (page) {
	page.candidates = [];

	page.farm_field = page.add_field({
		fieldname: "farm",
		label: __("Farm"),
		fieldtype: "Link",
		options: "Farm",
	});

	page.company_field = page.add_field({
		fieldname: "company",
		label: __("Company"),
		fieldtype: "Link",
		options: "Company",
	});

	page.inspection_date_field = page.add_field({
		fieldname: "inspection_date",
		label: __("Inspection Date"),
		fieldtype: "Date",
		default: frappe.datetime.get_today(),
	});
	page.inspection_date_field.set_value(frappe.datetime.get_today());

	page.supervisor_field = page.add_field({
		fieldname: "supervisor",
		label: __("Supervisor"),
		fieldtype: "Link",
		options: "Employee",
	});

	page.set_primary_action(__("Load Assignments"), function () {
		frappe.pages["bulk-ppe-inspection"].load_assignments(page);
	});

	page.submit_btn = page.add_button(
		__("Submit All"),
		function () {
			frappe.pages["bulk-ppe-inspection"].submit_all(page);
		},
		{ btn_type: "primary" }
	);

	page.$search_wrapper = $(`
		<div style="margin-top: 16px; display: flex; gap: 8px; align-items: center;">
			<input type="text" class="form-control bulk-ppe-search" style="max-width: 300px;"
				placeholder="${__("Search employee...")}">
			<button class="btn btn-default btn-sm bulk-ppe-select-all">${__("Select All")}</button>
			<button class="btn btn-default btn-sm bulk-ppe-clear-all">${__("Clear All")}</button>
		</div>
	`).appendTo(page.body);
	page.$search_wrapper.hide();

	page.$table_wrapper = $('<div class="bulk-ppe-table-wrapper" style="margin-top: 16px;"></div>').appendTo(
		page.body
	);
	page.$summary_wrapper = $('<div class="bulk-ppe-summary-wrapper" style="margin-top: 16px;"></div>').appendTo(
		page.body
	);

	page.$search_wrapper.on("input", ".bulk-ppe-search", function () {
		const term = $(this).val().trim().toLowerCase();
		page.$table_wrapper.find("table.bulk-ppe-table tbody tr").each(function () {
			const $tr = $(this);
			const name = ($tr.attr("data-employee-name") || "").toLowerCase();
			$tr.toggle(!term || name.indexOf(term) !== -1);
		});
	});

	page.$search_wrapper.on("click", ".bulk-ppe-select-all", function () {
		frappe.pages["bulk-ppe-inspection"].set_all_inspected(page, true);
	});
	page.$search_wrapper.on("click", ".bulk-ppe-clear-all", function () {
		frappe.pages["bulk-ppe-inspection"].set_all_inspected(page, false);
	});
};

frappe.pages["bulk-ppe-inspection"].set_all_inspected = function (page, checked) {
	page.$table_wrapper
		.find("table.bulk-ppe-table tbody tr:visible:not(.bulk-ppe-handled)")
		.find(".bulk-ppe-inspected-toggle")
		.prop("checked", checked)
		.trigger("change");
};

frappe.pages["bulk-ppe-inspection"].load_assignments = function (page) {
	const farm = page.farm_field.get_value();
	const company = page.company_field.get_value();

	if (!farm && !company) {
		frappe.throw(__("Select a Farm or Company before loading assignments."));
		return;
	}

	frappe.call({
		method:
			"upande_stores.upande_stores.page.bulk_ppe_inspection.bulk_ppe_inspection.get_bulk_inspection_candidates",
		args: { farm: farm, company: company },
		freeze: true,
		callback: function (r) {
			page.candidates = r.message || [];
			frappe.pages["bulk-ppe-inspection"].render_table(page);
			page.$summary_wrapper.empty();
			page.$search_wrapper.find(".bulk-ppe-search").val("");
			page.$search_wrapper.toggle(!!page.candidates.length);
		},
	});
};

frappe.pages["bulk-ppe-inspection"].render_table = function (page) {
	page.$table_wrapper.empty();

	if (!page.candidates.length) {
		page.$table_wrapper.html(
			`<div class="text-muted">${__("No Employee PPE Assignments found for the selected filters.")}</div>`
		);
		return;
	}

	// Group consecutive rows by employee (the server already sorts by
	// employee_name) so the "Inspected" checkbox and employee name can each
	// span the whole group via rowspan, instead of repeating per item row.
	const groups = [];
	page.candidates.forEach((row) => {
		const last = groups[groups.length - 1];
		if (last && last.employee === row.employee) {
			last.rows.push(row);
		} else {
			groups.push({ employee: row.employee, employee_name: row.employee_name, rows: [row] });
		}
	});

	const $table = $(`
		<table class="table table-bordered bulk-ppe-table">
			<thead>
				<tr>
					<th style="width: 90px;">${__("Inspected")}</th>
					<th>${__("Employee")}</th>
					<th>${__("Item")}</th>
					<th>${__("Issue Date")}</th>
					<th>${__("Status")}</th>
					<th>${__("Other Reason")}</th>
					<th>${__("Comments")}</th>
				</tr>
			</thead>
			<tbody></tbody>
		</table>
	`);
	const $tbody = $table.find("tbody");

	groups.forEach((group) => {
		group.rows.forEach((row, i) => {
			const $tr = $("<tr></tr>")
				.attr("data-employee-ppe-assignment", row.employee_ppe_assignment)
				.attr("data-employee", row.employee)
				.attr("data-employee-name", row.employee_name || "")
				.attr("data-inspected", "0");

			if (i === 0) {
				$tr.append(`
					<td rowspan="${group.rows.length}">
						<input type="checkbox" class="bulk-ppe-inspected-toggle" data-employee="${frappe.utils.escape_html(
							group.employee
						)}">
					</td>
				`);
				$tr.append(
					`<td rowspan="${group.rows.length}"><b>${frappe.utils.escape_html(
						group.employee_name || group.employee
					)}</b></td>`
				);
			}

			$tr.append(`<td>${frappe.utils.escape_html(row.item_name || row.item_code || "")}</td>`);
			$tr.append(`<td>${frappe.datetime.str_to_user(row.issue_date) || ""}</td>`);

			const $status_td = $("<td></td>");
			const $status_select = $(`
				<select class="form-control bulk-ppe-status" disabled>
					<option value="OK">${__("OK")}</option>
					<option value="Worn Out">${__("Worn Out")}</option>
					<option value="Lost">${__("Lost")}</option>
				</select>
			`);
			$status_select.val("OK");
			$status_td.append($status_select);
			$tr.append($status_td);

			$tr.append(
				`<td><input type="text" class="form-control bulk-ppe-other-reason" disabled></td>`
			);
			$tr.append(
				`<td><input type="text" class="form-control bulk-ppe-comments" disabled></td>`
			);

			$tbody.append($tr);
		});
	});

	page.$table_wrapper.append($table);

	// One checkbox (on the group's first row) gates every row belonging to
	// that employee -- toggling it marks the whole employee as "inspected"
	// (enabling their status/comment inputs for editing) or not (leaving
	// them disabled so an un-reviewed employee can never be silently
	// submitted as "OK" by default).
	$table.on("change", ".bulk-ppe-inspected-toggle", function () {
		const $checkbox = $(this);
		const employee = $checkbox.attr("data-employee");
		const checked = $checkbox.is(":checked");
		const $rows = $table.find(`tbody tr[data-employee="${employee}"]`);
		$rows.attr("data-inspected", checked ? "1" : "0");
		$rows.toggleClass("bulk-ppe-inspected-row", checked);
		$rows.find("select.bulk-ppe-status, input.bulk-ppe-other-reason, input.bulk-ppe-comments").prop(
			"disabled",
			!checked
		);
	});
};

frappe.pages["bulk-ppe-inspection"].submit_all = function (page) {
	const farm = page.farm_field.get_value();
	const inspection_date = page.inspection_date_field.get_value();
	const supervisor = page.supervisor_field.get_value();

	if (!farm) {
		frappe.throw(__("Farm is required."));
		return;
	}
	if (!inspection_date) {
		frappe.throw(__("Inspection Date is required."));
		return;
	}
	if (!supervisor) {
		frappe.throw(__("Supervisor is required."));
		return;
	}

	const $rows = page.$table_wrapper.find(
		'table.bulk-ppe-table tbody tr[data-inspected="1"]:not(.bulk-ppe-handled)'
	);
	if (!$rows.length) {
		frappe.throw(
			__("Mark at least one employee as Inspected (tick the checkbox next to their name) before submitting.")
		);
		return;
	}

	const rows = [];
	$rows.each(function () {
		const $tr = $(this);
		rows.push({
			employee_ppe_assignment: $tr.attr("data-employee-ppe-assignment"),
			employee: $tr.attr("data-employee"),
			employee_name: $tr.attr("data-employee-name"),
			current_status: $tr.find(".bulk-ppe-status").val(),
			other_reason: $tr.find(".bulk-ppe-other-reason").val() || "",
			comments: $tr.find(".bulk-ppe-comments").val() || "",
		});
	});

	frappe.call({
		method:
			"upande_stores.upande_stores.page.bulk_ppe_inspection.bulk_ppe_inspection.submit_bulk_ppe_inspection",
		args: {
			farm: farm,
			inspection_date: inspection_date,
			supervisor: supervisor,
			rows: JSON.stringify(rows),
		},
		freeze: true,
		callback: function (r) {
			const results = r.message || [];
			frappe.pages["bulk-ppe-inspection"].render_summary(page, results, true);

			// Lock in every employee this call actually tried to process
			// (submitted, left as a draft, or errored) so re-clicking
			// "Submit All" later in the same session -- after inspecting
			// more people from this farm -- only sends newly-checked
			// employees, never re-submits someone already handled.
			results.forEach((result) => {
				const $handled = page.$table_wrapper.find(
					`table.bulk-ppe-table tbody tr[data-employee="${result.employee}"]`
				);
				$handled.addClass("bulk-ppe-handled").css("opacity", 0.5);
				$handled.find(".bulk-ppe-inspected-toggle").prop("disabled", true);
				$handled.find("select.bulk-ppe-status, input.bulk-ppe-other-reason, input.bulk-ppe-comments").prop(
					"disabled",
					true
				);
			});
		},
	});
};

frappe.pages["bulk-ppe-inspection"].render_summary = function (page, results, append) {
	if (!append) {
		page.$summary_wrapper.empty();
	}

	const $list = page.$summary_wrapper.find(".bulk-ppe-summary");
	const $target = append && $list.length ? $list : $('<div class="bulk-ppe-summary"></div>');

	results.forEach((result) => {
		let $line;
		if (result.error) {
			$line = $(
				`<div style="color:#c4302b;">${frappe.utils.escape_html(
					result.employee_name || result.employee
				)}: ${frappe.utils.escape_html(result.error)}</div>`
			);
		} else if (result.submitted) {
			$line = $(
				`<div style="color:#1a8a3a;">${frappe.utils.escape_html(
					result.employee_name || result.employee
				)}: ${__("PPE Inspection")} <a href="/app/ppe-inspection/${encodeURIComponent(
					result.name
				)}">${frappe.utils.escape_html(result.name)}</a> ${__("submitted")}</div>`
			);
		} else {
			$line = $(
				`<div style="color:#f59e0b;">${frappe.utils.escape_html(
					result.employee_name || result.employee
				)}: ${__("PPE Inspection")} <a href="/app/ppe-inspection/${encodeURIComponent(
					result.name
				)}">${frappe.utils.escape_html(
					result.name
				)}</a> ${__("created as draft — attach photo evidence for Worn Out item(s) to submit")}</div>`
			);
		}
		$target.append($line);
	});

	if (!$target.parent().length) {
		page.$summary_wrapper.append($target);
	}
};
