"""Endpoints for the desk's Backups page (/desk/retail-backups).

System Managers only: a backup holds every document, user and password hash,
and a restore replaces the whole site.
"""

import os
import shutil
from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from retail_management.services import backup, backup_drive

RESTORE_WORD = "RESTORE"
CHUNK_SIZE = 4 * 1024 * 1024  # what the page sends; under every proxy limit
CHUNK_LIMIT = 8 * 1024 * 1024
JOB_TIMEOUT = 4 * 3600
SCHEDULE_FIELDS = (
	"auto_backup",
	"frequency",
	"weekday",
	"backup_hour",
	"include_files",
	"keep_on_drive",
	"keep_on_server",
	"notify_email",
	"drive_folder",
	"last_scheduled_on",
	"last_status",
	"last_error",
)


def _only_admin():
	frappe.only_for("System Manager")


def _not_busy():
	if busy := backup.busy_with():
		frappe.throw(_("A {0} is already running. Wait for it to finish.").format(_(busy)), backup.BackupBusy)


def _existing(file: str) -> str:
	path = backup.bundle_path(file)
	if not os.path.isfile(path):
		frappe.throw(_("This backup is no longer on the server."), frappe.DoesNotExistError)
	return path


@frappe.whitelist()
def overview() -> dict:
	_only_admin()
	backup.close_stale_runs()
	settings = backup.get_settings()
	bundles = backup.list_bundles()
	on_server = {b["name"] for b in bundles}
	runs = frappe.get_all(
		backup.RUN,
		fields=[
			"name",
			"kind",
			"status",
			"started_on",
			"finished_on",
			"file_name",
			"size_mb",
			"includes_files",
			"on_drive",
			"note",
		],
		order_by="creation desc",
		limit=20,
	)
	for run in runs:
		run["on_server"] = run.file_name in on_server
	return {
		"site": frappe.local.site,
		"busy": backup.busy_with(),
		"bundles": bundles,
		"runs": runs,
		"schedule": {key: settings.get(key) for key in SCHEDULE_FIELDS},
		"drive": {
			"google_ready": backup_drive.google_ready(),
			"connected": backup_drive.is_connected(),
			"account": settings.drive_account,
			"redirect_uri": backup_drive.redirect_uri(),
		},
		"server_time": now_datetime().strftime("%Y-%m-%d %H:%M"),
		"restore_word": RESTORE_WORD,
		"chunk_size": CHUNK_SIZE,
	}


@frappe.whitelist(methods=["POST"])
def save_schedule(
	auto_backup=0,
	frequency="Daily",
	weekday="Sunday",
	backup_hour=2,
	include_files=1,
	keep_on_drive=14,
	keep_on_server=3,
	notify_email=None,
	drive_folder=None,
) -> dict:
	_only_admin()
	settings = backup.get_settings()
	settings.update(
		{
			"auto_backup": cint(auto_backup),
			"frequency": frequency,
			"weekday": weekday,
			"backup_hour": cint(backup_hour),
			"include_files": cint(include_files),
			"keep_on_drive": cint(keep_on_drive),
			"keep_on_server": cint(keep_on_server),
			"notify_email": (notify_email or "").strip() or None,
			"drive_folder": drive_folder,
		}
	)
	settings.save()
	return overview()


@frappe.whitelist(methods=["POST"])
def start_backup(upload_to_drive=0) -> dict:
	"""Make a backup now, in the background. With upload_to_drive, copy it to Drive too."""
	_only_admin()
	_not_busy()
	upload = bool(cint(upload_to_drive))
	if upload and not backup_drive.is_connected():
		frappe.throw(_("Connect Google Drive first."))
	frappe.enqueue(
		"retail_management.services.backup.backup_job",
		queue="long",
		timeout=JOB_TIMEOUT,
		kind="Manual",
		upload=upload,
	)
	return {"started": True}


@frappe.whitelist(methods=["GET"])
def download(file: str):
	"""Send a bundle from the server (nginx serves the bytes in production)."""
	from frappe.core.doctype.access_log.access_log import make_access_log
	from frappe.utils.response import send_private_file

	_only_admin()
	_existing(file)
	make_access_log(report_name="Backup", file_type="zip", method="download")
	frappe.db.commit()
	response = send_private_file(f"{backup.FOLDER}/{file}")
	response.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(file)}"
	return response


@frappe.whitelist(methods=["POST"])
def delete_bundle(file: str) -> dict:
	_only_admin()
	_not_busy()
	os.remove(_existing(file))
	return overview()


@frappe.whitelist(methods=["POST"])
def upload_chunk(upload_id: str, offset: int, final: int = 0) -> dict:
	"""Receive a backup file in pieces, so no request is large and web server
	and proxy size limits do not matter. The last piece checks the file and
	adds it to the server's backups."""
	_only_admin()
	if not backup.UPLOAD_ID.match(upload_id or ""):
		frappe.throw(_("Bad upload."))
	chunk = frappe.request.files.get("chunk") if frappe.request else None
	if not chunk:
		frappe.throw(_("No data received."))
	data = chunk.stream.read(CHUNK_LIMIT + 1)
	if len(data) > CHUNK_LIMIT:
		frappe.throw(_("Piece too large."))

	part = os.path.join(backup.incoming_dir(), f"{upload_id}.part")
	offset = cint(offset)
	have = os.path.getsize(part) if os.path.exists(part) else 0
	if offset and offset != have:
		frappe.throw(_("The upload got out of step. Start it again."))
	if shutil.disk_usage(backup.incoming_dir()).free < len(data) + 512 * 1024 * 1024:
		frappe.throw(_("The server is almost out of disk space."))
	with open(part, "ab" if offset else "wb") as out:
		out.write(data)

	if not cint(final):
		return {"received": offset + len(data)}

	try:
		manifest = backup.read_manifest(part)
	except Exception:
		os.remove(part)
		raise
	stamp = now_datetime().strftime("%Y%m%d-%H%M%S")
	name = f"{backup.BUNDLE_PREFIX}uploaded-{stamp}-{upload_id[:6]}.zip"
	os.replace(part, backup.bundle_path(name))
	return {"file": name, "manifest": _summary(manifest)}


def _summary(manifest: dict) -> dict:
	return {
		"site": manifest.get("site"),
		"created": manifest.get("created"),
		"includes_files": manifest.get("includes_files"),
		"apps": manifest.get("apps"),
	}


@frappe.whitelist()
def inspect(file: str) -> dict:
	"""What a bundle on the server holds."""
	_only_admin()
	return _summary(backup.read_manifest(_existing(file)))


@frappe.whitelist(methods=["POST"])
def start_restore(file: str, confirm: str) -> dict:
	"""Replace the whole site with a backup on the server, in the background."""
	_only_admin()
	if (confirm or "").strip() != RESTORE_WORD:
		frappe.throw(_("Type {0} to confirm.").format(RESTORE_WORD))
	_not_busy()
	path = _existing(file)
	backup.read_manifest(path)
	frappe.enqueue(
		"retail_management.services.backup.restore_job",
		queue="long",
		timeout=JOB_TIMEOUT,
		path=path,
		user=frappe.session.user,
	)
	return {"started": True}


@frappe.whitelist(methods=["POST"])
def connect_drive() -> dict:
	_only_admin()
	if not backup_drive.google_ready():
		frappe.throw(_("Fill in and enable Google Settings first."))
	return {"url": backup_drive.authorization_url()}


@frappe.whitelist(methods=["POST"])
def disconnect_drive() -> dict:
	_only_admin()
	backup_drive.disconnect()
	return overview()
