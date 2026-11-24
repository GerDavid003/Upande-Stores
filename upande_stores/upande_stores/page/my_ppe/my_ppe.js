// Page: my-ppe — My PPE
//
// Read-only self-service page: shows the logged-in user their own
// Employee PPE Assignment records (scoped server-side to their linked
// Employee via upande_stores.upande_stores.page.my_ppe.my_ppe.get_my_ppe_assignments).
// Deliberately plain Desk styling -- no custom CSS injected.
frappe.pages["my-ppe"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "My PPE",
		single_column: true,
	});

	frappe.pages["my-ppe"].make(page);
};

frappe.pages["my-ppe"].make = function (page) {
	page.$message_wrapper = $('<div style="margin-top: 16px;"></div>').appendTo(page.body);
	page.$summary_wrapper = $('<div style="margin-top: 16px;"></div>').appendTo(page.body);
	page.$table_wrapper = $('<div style="margin-top: 16px;"></div>').appendTo(page.body);

	frappe.pages["my-ppe"].load(page);
};

frappe.pages["my-ppe"].load = function (page) {
	frappe.call({
		method: "upande_stores.upande_stores.page.my_ppe.my_ppe.get_my_ppe_assignments",
		freeze: true,
		callback: function (r) {
			const data = r.message || { employee: null, assignments: [] };
			frappe.pages["my-ppe"].render(page, data);
		},
	});
};

frappe.pages["my-ppe"].render = function (page, data) {
	page.$message_wrapper.empty();
	page.$summary_wrapper.empty();
	page.$table_wrapper.empty();

	if (!data.employee) {
		page.$message_wrapper.html(
			`<div class="text-muted">${__(
				"No Employee record is linked to your account, so there's nothing to show here."
			)}</div>`
		);
		return;
	}

	if (!data.assignments || !data.assignments.length) {
		page.$message_wrapper.html(
			`<div class="text-muted">${__("You have no active PPE items on record.")}</div>`
		);
		return;
	}

	const assignments = data.assignments;
	const overdue_count = assignments.filter((row) => !!row.inspection_overdue).length;

	page.$summary_wrapper.html(
		`<div><b>${assignments.length} ${__("item(s)")}, ${overdue_count} ${__(
			"due for inspection"
		)}</b></div>`
	);

	const $table = $(`
		<table class="table table-bordered my-ppe-table">
			<thead>
				<tr>
					<th>${__("Item")}</th>
					<th>${__("Issue Date")}</th>
					<th>${__("Status")}</th>
					<th>${__("Last Inspected")}</th>
					<th>${__("Next Inspection Due")}</th>
				</tr>
			</thead>
			<tbody></tbody>
		</table>
	`);
	const $tbody = $table.find("tbody");

	assignments.forEach((row) => {
		const is_overdue = !!row.inspection_overdue;
		const $tr = $("<tr></tr>");
		if (is_overdue) {
			$tr.attr("style", "background-color: #fdecea;");
		}

		$tr.append(`<td>${frappe.utils.escape_html(row.item_name || row.item_code || "")}</td>`);
		$tr.append(`<td>${frappe.datetime.str_to_user(row.issue_date) || ""}</td>`);
		$tr.append(`<td>${frappe.utils.escape_html(row.status || "")}</td>`);
		$tr.append(
			`<td>${
				row.last_inspection_date
					? frappe.datetime.str_to_user(row.last_inspection_date)
					: __("Never")
			}</td>`
		);

		const due_text = row.next_inspection_due
			? frappe.datetime.str_to_user(row.next_inspection_due)
			: "";
		const overdue_badge = is_overdue
			? ` <span class="indicator-pill red" style="margin-left: 4px;">${__("Overdue")}</span>`
			: "";
		$tr.append(`<td>${due_text}${overdue_badge}</td>`);

		$tbody.append($tr);
	});

	page.$table_wrapper.append($table);
};
