// Backups page (/desk/retail-backups): export the whole site to one .zip,
// restore from one, and set up timed copies to Google Drive.
// Server side: retail_management/api/backup.py.

const RB_API = "retail_management.api.backup.";

frappe.pages["retail-backups"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Backups"),
		single_column: true,
	});
	wrapper.retail_backups = new RetailBackups(page);
};

frappe.pages["retail-backups"].on_page_show = function (wrapper) {
	wrapper.retail_backups && wrapper.retail_backups.refresh();
};

class RetailBackups {
	constructor(page) {
		this.page = page;
		this.data = null;
		this.timer = null;
		this.page.set_primary_action(__("Make a backup"), () => this.backup_now(false), "download");
		this.page.add_inner_button(__("Restore from a file"), () => this.$file.trigger("click"));
		this.make();
		this.handle_drive_return();
		this.refresh();
	}

	make() {
		const $body = $(this.page.body).addClass("retail-backups");
		$body.html(`
			<style>
				.retail-backups .rb-card { border: 1px solid var(--border-color); border-radius: var(--border-radius-lg);
					background: var(--card-bg); padding: var(--padding-lg); margin-bottom: var(--margin-lg); }
				.retail-backups .rb-card h4 { margin: 0 0 var(--margin-xs); font-size: var(--text-lg); font-weight: 600; }
				.retail-backups .rb-muted { color: var(--text-muted); font-size: var(--text-sm); }
				.retail-backups .rb-row { display: flex; gap: var(--margin-sm); align-items: center; flex-wrap: wrap; }
				.retail-backups .rb-table { width: 100%; font-size: var(--text-sm); }
				.retail-backups .rb-table td, .retail-backups .rb-table th { padding: 6px 8px; border-top: 1px solid var(--border-color); vertical-align: top; }
				.retail-backups .rb-table th { color: var(--text-muted); font-weight: 500; border-top: 0; }
				.retail-backups .rb-actions { white-space: nowrap; text-align: end; }
				.retail-backups .rb-busy { display: none; }
				.retail-backups .rb-progress { height: 6px; border-radius: 3px; background: var(--control-bg); overflow: hidden; margin-top: var(--margin-sm); display: none; }
				.retail-backups .rb-progress > div { height: 100%; width: 0; background: var(--primary); transition: width .2s; }
				.retail-backups code { word-break: break-all; }
			</style>
			<div class="rb-busy alert alert-warning"></div>

			<div class="rb-card">
				<h4>${__("Export")}</h4>
				<p class="rb-muted">${__(
					"One .zip file with the whole database (every product, sale, purchase, user and setting) and every attached file: scanned delivery notes, supplier invoices, pictures. Keep a copy somewhere other than this server."
				)}</p>
				<div class="rb-row">
					<button class="btn btn-primary btn-sm rb-make">${__("Make a backup")}</button>
					<button class="btn btn-default btn-sm rb-make-drive">${__("Make a backup and copy it to Google Drive")}</button>
				</div>
				<div class="rb-bundles" style="margin-top: var(--margin-md)"></div>
			</div>

			<div class="rb-card">
				<h4>${__("Import")}</h4>
				<p class="rb-muted">${__(
					"Restoring replaces everything on this site with what is in the file. A backup of the current state is made first, so it can be undone."
				)}</p>
				<div class="rb-row">
					<button class="btn btn-default btn-sm rb-pick">${__("Choose a backup file (.zip)")}</button>
					<span class="rb-muted rb-upload-text"></span>
				</div>
				<div class="rb-progress"><div></div></div>
				<input type="file" accept=".zip,application/zip" class="rb-file" hidden>
			</div>

			<div class="rb-card">
				<h4>${__("Timed backups to Google Drive")}</h4>
				<div class="rb-drive" style="margin-bottom: var(--margin-md)"></div>
				<div class="rb-schedule"></div>
				<div class="rb-row" style="margin-top: var(--margin-sm)">
					<button class="btn btn-primary btn-sm rb-save">${__("Save schedule")}</button>
					<span class="rb-muted rb-last"></span>
				</div>
			</div>

			<div class="rb-card">
				<h4>${__("History")}</h4>
				<div class="rb-runs"></div>
			</div>
		`);

		this.$busy = $body.find(".rb-busy");
		this.$bundles = $body.find(".rb-bundles");
		this.$drive = $body.find(".rb-drive");
		this.$runs = $body.find(".rb-runs");
		this.$last = $body.find(".rb-last");
		this.$file = $body.find(".rb-file");
		this.$progress = $body.find(".rb-progress");
		this.$upload_text = $body.find(".rb-upload-text");

		$body.find(".rb-make").on("click", () => this.backup_now(false));
		$body.find(".rb-make-drive").on("click", () => this.backup_now(true));
		$body.find(".rb-pick").on("click", () => this.$file.trigger("click"));
		$body.find(".rb-save").on("click", () => this.save_schedule());
		this.$file.on("change", (e) => {
			const file = e.target.files && e.target.files[0];
			e.target.value = "";
			if (file) this.upload(file);
		});

		this.schedule = new frappe.ui.FieldGroup({
			parent: $body.find(".rb-schedule"),
			fields: [
				{ fieldname: "auto_backup", fieldtype: "Check", label: __("Back up automatically") },
				{
					fieldname: "frequency",
					fieldtype: "Select",
					label: __("How often"),
					options: [
						{ value: "Daily", label: __("Every day") },
						{ value: "Weekly", label: __("Every week") },
					],
					depends_on: "auto_backup",
				},
				{
					fieldname: "weekday",
					fieldtype: "Select",
					label: __("Day"),
					options: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].map(
						(d) => ({ value: d, label: __(d) })
					),
					depends_on: "eval:doc.auto_backup && doc.frequency=='Weekly'",
				},
				{
					fieldname: "backup_hour",
					fieldtype: "Int",
					label: __("At hour (0 to 23, server time)"),
					depends_on: "auto_backup",
				},
				{ fieldtype: "Column Break" },
				{
					fieldname: "include_files",
					fieldtype: "Check",
					label: __("Include attached files (scans, pictures)"),
				},
				{ fieldname: "keep_on_drive", fieldtype: "Int", label: __("Copies kept on Google Drive") },
				{ fieldname: "keep_on_server", fieldtype: "Int", label: __("Copies kept on this server") },
				{ fieldname: "drive_folder", fieldtype: "Data", label: __("Google Drive folder") },
				{
					fieldname: "notify_email",
					fieldtype: "Data",
					options: "Email",
					label: __("Email me if a timed backup fails"),
				},
			],
		});
		this.schedule.make();
	}

	call(method, args, opts = {}) {
		return frappe
			.call({ method: RB_API + method, args, freeze: opts.freeze })
			.then((r) => r.message);
	}

	refresh() {
		return this.call("overview").then((data) => this.render(data));
	}

	render(data) {
		this.data = data;
		const running = !!(data.busy || data.runs.some((r) => r.status === "Running"));
		const was_restoring = this.restoring;
		this.restoring = data.busy === "restore";

		this.$busy
			.toggle(running)
			.text(
				this.restoring
					? __("Restoring a backup. The site may be slow, or sign you out, until it finishes.")
					: __("A backup is being made. This page updates by itself.")
			);
		this.page.btn_primary.prop("disabled", running);
		$(this.page.body).find(".rb-make, .rb-make-drive, .rb-pick").prop("disabled", running);
		$(this.page.body).find(".rb-make-drive").toggle(!!data.drive.connected);

		this.render_bundles(data, running);
		this.render_drive(data);
		this.render_runs(data);

		if (!this.schedule_loaded) {
			this.schedule.set_values(data.schedule);
			this.schedule_loaded = true;
		}
		const s = data.schedule;
		this.$last.text(
			s.last_scheduled_on
				? __("Last timed backup: {0}, {1}. Server time now: {2}.", [
						frappe.datetime.str_to_user(s.last_scheduled_on),
						s.last_status || "",
						data.server_time,
				  ])
				: __("Server time now: {0}.", [data.server_time])
		);

		if (was_restoring && !this.restoring) this.restored();
		clearTimeout(this.timer);
		// Jobs start a moment after the click: keep looking for a while even before they show.
		if (running || Date.now() < (this.expect_until || 0))
			this.timer = setTimeout(() => this.refresh().catch(() => this.restored()), running ? 4000 : 1500);
	}

	restored() {
		frappe.msgprint({
			title: __("Restore finished"),
			message: __("The site was replaced. Reload the page, and sign in again if asked. The History shows how it went."),
			primary_action: { label: __("Reload"), action: () => window.location.reload() },
		});
	}

	render_bundles(data, running) {
		const esc = frappe.utils.escape_html;
		if (!data.bundles.length) {
			this.$bundles.html(`<p class="rb-muted">${__("No backups on this server yet.")}</p>`);
			return;
		}
		const off = running ? "disabled" : "";
		const rows = data.bundles
			.map(
				(b) => `
				<tr data-file="${esc(b.name)}">
					<td><code>${esc(b.name)}</code></td>
					<td>${esc(frappe.datetime.str_to_user(b.created))}</td>
					<td>${b.size_mb} MB</td>
					<td class="rb-actions">
						<a class="btn btn-xs btn-default" href="/api/method/${RB_API}download?file=${encodeURIComponent(b.name)}">${__("Download")}</a>
						<button class="btn btn-xs btn-default rb-restore" ${off}>${__("Restore")}</button>
						<button class="btn btn-xs btn-default rb-delete" ${off} title="${__("Delete from the server")}">${frappe.utils.icon("delete", "xs")}</button>
					</td>
				</tr>`
			)
			.join("");
		this.$bundles.html(`
			<div class="rb-muted" style="margin-bottom: 4px">${__("On this server")}</div>
			<div class="table-responsive"><table class="rb-table">
				<thead><tr><th>${__("File")}</th><th>${__("Made")}</th><th>${__("Size")}</th><th></th></tr></thead>
				<tbody>${rows}</tbody>
			</table></div>`);
		const file_of = (e) => $(e.currentTarget).closest("tr").attr("data-file");
		this.$bundles.find(".rb-restore").on("click", (e) => this.confirm_restore(file_of(e)));
		this.$bundles.find(".rb-delete").on("click", (e) => this.delete_bundle(file_of(e)));
	}

	render_drive(data) {
		const esc = frappe.utils.escape_html;
		const d = data.drive;
		let html;
		if (!d.google_ready) {
			html = `
				<p>${__("Google Drive is not set up yet. Once, with the Google account the backups should go to:")}</p>
				<ol class="rb-muted">
					<li>${__("In Google Cloud Console, create a project, enable the Google Drive API, and create an OAuth client of type Web application.")}</li>
					<li>${__("Add this address as an authorised redirect URI:")} <code>${esc(d.redirect_uri)}</code></li>
					<li>${__("Put the client ID and secret in {0}, tick Enable and save.", [
						`<a href="/desk/google-settings">${__("Google Settings")}</a>`,
					])}</li>
					<li>${__("Come back here and connect.")}</li>
				</ol>`;
		} else if (!d.connected) {
			html = `
				<div class="rb-row">
					<button class="btn btn-primary btn-sm rb-connect">${__("Connect Google Drive")}</button>
					<span class="rb-muted">${__("The app only sees the backups folder it creates, nothing else in your Drive.")}</span>
				</div>
				<p class="rb-muted" style="margin-top: var(--margin-xs)">${__("Redirect URI to register in Google Cloud:")} <code>${esc(d.redirect_uri)}</code></p>`;
		} else {
			html = `
				<div class="rb-row">
					<span class="indicator-pill green">${__("Connected")}</span>
					<span>${esc(d.account || __("Google account"))}</span>
					<button class="btn btn-default btn-xs rb-disconnect">${__("Disconnect")}</button>
				</div>`;
		}
		this.$drive.html(html);
		this.$drive
			.find(".rb-connect")
			.on("click", () => this.call("connect_drive").then((r) => (window.location.href = r.url)));
		this.$drive.find(".rb-disconnect").on("click", () =>
			frappe.confirm(__("Stop copying backups to this Google account? Copies already there stay."), () =>
				this.call("disconnect_drive").then((d) => this.render(d))
			)
		);
	}

	render_runs(data) {
		const esc = frappe.utils.escape_html;
		if (!data.runs.length) {
			this.$runs.html(`<p class="rb-muted">${__("Nothing yet.")}</p>`);
			return;
		}
		const color = { Done: "green", Failed: "red", Running: "orange" };
		const rows = data.runs
			.map((r) => {
				const where = [r.on_server ? __("this server") : null, r.on_drive ? __("Google Drive") : null]
					.filter(Boolean)
					.join(", ");
				const no_files = r.file_name && !r.includes_files ? ` <span class="rb-muted">(${__("no files")})</span>` : "";
				return `
				<tr>
					<td>${esc(frappe.datetime.str_to_user(r.started_on))}</td>
					<td>${esc(__(r.kind))}</td>
					<td><span class="indicator-pill ${color[r.status] || "gray"}">${esc(__(r.status))}</span></td>
					<td>${r.size_mb ? r.size_mb + " MB" : ""}${no_files}</td>
					<td>${esc(where)}</td>
					<td class="rb-muted">${esc(r.note || "")}</td>
				</tr>`;
			})
			.join("");
		this.$runs.html(`
			<div class="table-responsive"><table class="rb-table">
				<thead><tr><th>${__("When")}</th><th>${__("Kind")}</th><th>${__("Status")}</th><th>${__("Size")}</th><th>${__("Kept on")}</th><th>${__("Note")}</th></tr></thead>
				<tbody>${rows}</tbody>
			</table></div>`);
	}

	backup_now(to_drive) {
		this.call("start_backup", { upload_to_drive: to_drive ? 1 : 0 }).then(() => {
			this.expect_until = Date.now() + 20000;
			frappe.show_alert({ message: __("Backup started. It appears below when ready."), indicator: "blue" });
			this.refresh();
		});
	}

	save_schedule() {
		const values = this.schedule.get_values();
		if (!values) return;
		this.call("save_schedule", values, { freeze: true }).then((data) => {
			frappe.show_alert({ message: __("Schedule saved"), indicator: "green" });
			this.render(data);
		});
	}

	delete_bundle(file) {
		frappe.confirm(
			__("Delete {0} from the server? Copies on Google Drive or your computer stay.", [
				`<b>${frappe.utils.escape_html(file)}</b>`,
			]),
			() => this.call("delete_bundle", { file }).then((data) => this.render(data))
		);
	}

	confirm_restore(file) {
		this.call("inspect", { file }).then((info) => {
			const esc = frappe.utils.escape_html;
			const word = this.data.restore_word;
			const made = info.created
				? frappe.datetime.str_to_user(String(info.created).replace("T", " ").slice(0, 19))
				: "?";
			const d = new frappe.ui.Dialog({
				title: __("Replace everything with this backup?"),
				fields: [
					{
						fieldtype: "HTML",
						options: `
							<p>${__("Backup made {0} on {1}, {2}.", [
								`<b>${esc(made)}</b>`,
								`<b>${esc(info.site || "?")}</b>`,
								info.includes_files ? __("with files") : __("database only"),
							])}</p>
							<p>${__("Every product, sale, purchase, user, password and setting on this site will be replaced by the ones in the backup. Anything entered since then will be gone from the site, but a backup of the current state is made first.")}</p>
							<p>${__("Type {0} to confirm.", [`<b>${word}</b>`])}</p>`,
					},
					{ fieldname: "confirm", fieldtype: "Data", label: __("Confirm"), reqd: 1 },
				],
				primary_action_label: __("Restore"),
				primary_action: ({ confirm }) => {
					this.call("start_restore", { file, confirm }).then(() => {
						d.hide();
						this.expect_until = Date.now() + 20000;
						frappe.show_alert({ message: __("Restore started"), indicator: "orange" });
						this.refresh();
					});
				},
			});
			d.get_primary_btn().removeClass("btn-primary").addClass("btn-danger");
			d.show();
		});
	}

	async upload(file) {
		if (!/\.zip$/i.test(file.name)) {
			frappe.msgprint(__("Choose a .zip backup made by this page."));
			return;
		}
		const size = this.data.chunk_size;
		const id = Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
		const $bar = this.$progress.show().find("div").css("width", "0");
		const $pick = $(this.page.body).find(".rb-pick").prop("disabled", true);
		try {
			let result = null;
			for (let offset = 0; ; offset += size) {
				const final = offset + size >= file.size;
				const form = new FormData();
				form.append("upload_id", id);
				form.append("offset", offset);
				form.append("final", final ? 1 : 0);
				form.append("chunk", file.slice(offset, offset + size), "chunk");
				const res = await fetch(`/api/method/${RB_API}upload_chunk`, {
					method: "POST",
					headers: { "X-Frappe-CSRF-Token": frappe.csrf_token, Accept: "application/json" },
					body: form,
				});
				const body = await res.json().catch(() => ({}));
				if (!res.ok) throw new Error(this.error_text(body) || res.statusText);
				result = body.message;
				const done = Math.min(file.size, offset + size);
				$bar.css("width", `${Math.round((done / Math.max(file.size, 1)) * 100)}%`);
				this.$upload_text.text(
					__("Uploading {0}: {1} of {2} MB", [
						file.name,
						(done / 1048576).toFixed(1),
						(file.size / 1048576).toFixed(1),
					])
				);
				if (final) break;
			}
			this.$upload_text.text(__("Uploaded and checked."));
			await this.refresh();
			if (result && result.file) this.confirm_restore(result.file);
		} catch (e) {
			this.$upload_text.text("");
			frappe.msgprint({
				title: __("Upload failed"),
				message: frappe.utils.escape_html(e.message),
				indicator: "red",
			});
		} finally {
			setTimeout(() => this.$progress.hide(), 800);
			$pick.prop("disabled", false);
		}
	}

	error_text(body) {
		try {
			const messages = JSON.parse(body._server_messages || "[]").map((m) => JSON.parse(m).message);
			if (messages.length) return frappe.utils.strip_html(messages.join(" "));
		} catch (e) {
			// fall through to the exception text
		}
		return body.exception || "";
	}

	handle_drive_return() {
		const drive = new URLSearchParams(window.location.search).get("drive");
		if (!drive) return;
		if (drive === "connected") {
			frappe.show_alert({ message: __("Google Drive connected"), indicator: "green" });
		} else {
			frappe.msgprint({
				title: __("Google Drive"),
				message: __("Google Drive was not connected."),
				indicator: "red",
			});
		}
		window.history.replaceState(null, "", window.location.pathname);
	}
}
