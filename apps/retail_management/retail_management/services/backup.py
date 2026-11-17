"""Whole-site backups in one file, restore from that file, and timed copies to
Google Drive.

A backup is one .zip (opens on any computer) holding:

    manifest.json        what is inside, which site and versions made it
    database.sql.gz      the whole database (every document, user, setting)
    public-files.*       public attachments (product pictures, logo)
    private-files.*      private attachments (scanned delivery notes, invoices)

The members are already compressed, so the zip only stores them.

Bundles live in sites/<site>/private/retail-backups, apart from Frappe's own
private/backups folder, which Frappe empties of files older than a day.

Restoring replaces the database with the one in the file and puts the files
back, then migrates. A fresh backup is taken first so a restore can be undone.
The schedule and the Google Drive connection survive a restore.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from contextlib import contextmanager
from datetime import datetime

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, now_datetime

SETTINGS = "Retail Backup Settings"
RUN = "Retail Backup Run"
FOLDER = "retail-backups"
INCOMING = "incoming"
BUNDLE_PREFIX = "retail-backup-"
BUNDLE_NAME = re.compile(r"^retail-backup-[A-Za-z0-9_.-]+\.zip$")
UPLOAD_ID = re.compile(r"^[a-f0-9]{16,40}$")
MANIFEST_FORMAT = 1
MEMBER_KEYS = ("database", "public_files", "private_files")

# Settings that belong to this server, not to the backup: kept across a restore.
_KEPT_SETTINGS = (
	"auto_backup",
	"frequency",
	"weekday",
	"backup_hour",
	"include_files",
	"keep_on_drive",
	"keep_on_server",
	"notify_email",
	"drive_folder",
	"drive_folder_id",
	"drive_account",
	"last_scheduled_on",
	"last_status",
	"last_error",
)


class BackupBusy(frappe.ValidationError):
	pass


def get_settings():
	"""The backup settings, with the field defaults saved the first time
	(a never-saved single has no values at all, not even its defaults)."""
	if not frappe.db.get_value("Singles", {"doctype": SETTINGS, "field": "frequency"}, "value", order_by=None):
		frappe.new_doc(SETTINGS).save(ignore_permissions=True)
	return frappe.get_single(SETTINGS)


# --- Paths -------------------------------------------------------------------


def backup_dir() -> str:
	path = os.path.abspath(frappe.get_site_path("private", FOLDER))
	os.makedirs(path, exist_ok=True)
	return path


def incoming_dir() -> str:
	path = os.path.join(backup_dir(), INCOMING)
	os.makedirs(path, exist_ok=True)
	return path


def bundle_path(name: str, incoming: bool = False) -> str:
	"""Full path of a bundle by its file name; refuses anything else."""
	if not name or not BUNDLE_NAME.match(name):
		frappe.throw(_("Not a backup file name."), frappe.ValidationError)
	folder = incoming_dir() if incoming else backup_dir()
	path = os.path.abspath(os.path.join(folder, name))
	if os.path.dirname(path) != folder:
		frappe.throw(_("Not a backup file name."), frappe.ValidationError)
	return path


def list_bundles() -> list[dict]:
	"""Bundles on the server, newest first."""
	folder = backup_dir()
	bundles = []
	for name in os.listdir(folder):
		path = os.path.join(folder, name)
		if BUNDLE_NAME.match(name) and os.path.isfile(path):
			stat = os.stat(path)
			bundles.append(
				{
					"name": name,
					"size_mb": round(stat.st_size / 1048576, 1),
					"created": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
				}
			)
	return sorted(bundles, key=lambda b: (b["created"], b["name"]), reverse=True)


# --- Locking -----------------------------------------------------------------

_LOCK_KEY = "retail_backup_busy"


@contextmanager
def _busy(what: str):
	"""One backup or restore at a time on the site."""
	key = frappe.cache.make_key(_LOCK_KEY)
	if not frappe.cache.set(key, what, nx=True, ex=4 * 3600):
		raise BackupBusy(_("A backup or restore is already running. Try again when it has finished."))
	try:
		yield
	finally:
		frappe.cache.delete(key)


def busy_with() -> str | None:
	value = frappe.cache.get(frappe.cache.make_key(_LOCK_KEY))
	return value.decode() if isinstance(value, bytes) else value


def close_stale_runs():
	"""Runs still marked Running while no job holds the lock were cut off
	(worker restart, server reboot): say so instead of showing them as busy."""
	if busy_with():
		return
	for name in frappe.get_all(RUN, {"status": "Running"}, pluck="name"):
		frappe.db.set_value(
			RUN,
			name,
			{"status": "Failed", "finished_on": now_datetime(), "note": _("Stopped before it finished.")},
		)


# --- Run log -----------------------------------------------------------------


def _start_run(kind: str) -> str:
	run = frappe.get_doc(
		{"doctype": RUN, "kind": kind, "status": "Running", "started_on": now_datetime()}
	).insert(ignore_permissions=True)
	frappe.db.commit()  # visible to the page while the job runs
	return run.name


def _finish_run(name: str, **values):
	frappe.db.set_value(RUN, name, values)
	frappe.db.commit()


def _error_text(error: Exception) -> str:
	text = frappe.utils.strip_html(str(error)) or error.__class__.__name__
	return text[:1000]


# --- Making a bundle ---------------------------------------------------------


def _bundle_name(kind: str) -> str:
	site = re.sub(r"[^A-Za-z0-9_.-]", "_", frappe.local.site)
	stamp = now_datetime().strftime("%Y%m%d-%H%M%S")
	suffix = {"Scheduled": "-auto", "Before restore": "-before-restore"}.get(kind, "")
	return f"{BUNDLE_PREFIX}{site}-{stamp}{suffix}.zip"


def _app_versions() -> dict:
	versions = {}
	for app in frappe.get_installed_apps():
		try:
			versions[app] = frappe.get_attr(f"{app}.__version__")
		except Exception:
			versions[app] = None
	return versions


def make_bundle(include_files: bool = True, kind: str = "Manual") -> str:
	"""Write a backup bundle to the backups folder and return its full path."""
	from frappe.utils.backups import new_backup

	path = os.path.join(backup_dir(), _bundle_name(kind))
	with tempfile.TemporaryDirectory(dir=backup_dir(), prefix=".work-") as work:
		# The run log stays out of the dump: history belongs to this server (a
		# restore keeps it), and the dump would catch this very run half-done.
		# ignore_conf keeps the dump a full one that restore accepts.
		odb = new_backup(
			ignore_files=not include_files,
			backup_path=work,
			compress=True,
			force=True,
			exclude_doctypes=RUN,
			ignore_conf=True,
		)
		manifest = {
			"format": MANIFEST_FORMAT,
			"site": frappe.local.site,
			"created": now_datetime().isoformat(),
			"kind": kind,
			"apps": _app_versions(),
			"includes_files": bool(include_files),
			"encrypted": bool(frappe.get_system_settings("encrypt_backup")),
			"members": {},
		}
		sources = {"database": ("database.sql.gz", odb.backup_path_db)}
		if include_files:
			for key, source in (
				("public_files", odb.backup_path_files),
				("private_files", odb.backup_path_private_files),
			):
				ext = ".tgz" if source.endswith(".tgz") else ".tar"
				sources[key] = (key.replace("_", "-") + ext, source)

		partial = path + ".part"
		try:
			with zipfile.ZipFile(partial, "w", zipfile.ZIP_STORED, allowZip64=True) as bundle:
				for key, (arcname, source) in sources.items():
					if not source or not os.path.exists(source):
						frappe.throw(_("The backup step for {0} produced no file.").format(key))
					manifest["members"][key] = arcname
					bundle.write(source, arcname)
				bundle.writestr("manifest.json", json.dumps(manifest, indent=1))
			os.replace(partial, path)
		finally:
			if os.path.exists(partial):
				os.remove(partial)
	return path


def read_manifest(path: str) -> dict:
	"""Check a bundle and return its manifest. Throws on anything unexpected."""
	try:
		with zipfile.ZipFile(path) as bundle:
			names = set(bundle.namelist())
			if "manifest.json" not in names:
				frappe.throw(_("This file is not a backup made here: it has no manifest."))
			manifest = json.loads(bundle.read("manifest.json"))
	except (zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError):
		frappe.throw(_("This file is not a backup made here, or it is damaged."))

	members = manifest.get("members") if isinstance(manifest, dict) else None
	if not isinstance(members, dict) or not members.get("database") or set(members) - set(MEMBER_KEYS):
		frappe.throw(_("This backup has no database in it."))
	for arcname in members.values():
		if (
			not isinstance(arcname, str)
			or "/" in arcname
			or "\\" in arcname
			or arcname.startswith(".")
			or arcname not in names
		):
			frappe.throw(_("This backup is damaged: a part of it is missing."))
	return manifest


def prune_local(keep: int):
	"""Keep the newest `keep` bundles on the server."""
	for bundle in list_bundles()[max(1, keep) :]:
		try:
			os.remove(os.path.join(backup_dir(), bundle["name"]))
		except OSError:
			pass


# --- Backup jobs -------------------------------------------------------------


def run_backup(kind: str = "Manual", upload: bool = False, include_files: bool | None = None) -> str:
	"""Make a bundle, log it, optionally copy it to Google Drive. Returns the run name."""
	settings = get_settings()
	if include_files is None:
		include_files = bool(settings.include_files)

	with _busy("backup"):
		run = _start_run(kind)
		try:
			path = make_bundle(include_files=include_files, kind=kind)
			_finish_run(
				run,
				file_name=os.path.basename(path),
				size_mb=round(os.path.getsize(path) / 1048576, 1),
				includes_files=int(include_files),
			)
			if upload:
				from retail_management.services import backup_drive

				file_id = backup_drive.upload(path)
				_finish_run(run, on_drive=1, drive_file_id=file_id)
				backup_drive.prune(cint(settings.keep_on_drive) or 14)
			prune_local(cint(settings.keep_on_server) or 3)
			_finish_run(run, status="Done", finished_on=now_datetime())
		except Exception as error:
			frappe.db.rollback()
			_finish_run(run, status="Failed", finished_on=now_datetime(), note=_error_text(error))
			raise
	return run


def backup_job(kind: str = "Manual", upload: bool = False):
	"""Background job started from the Backups page."""
	try:
		run_backup(kind=kind, upload=upload)
	except BackupBusy:
		pass
	except Exception:
		frappe.log_error(title="Retail backup failed")


# --- Schedule ----------------------------------------------------------------

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def is_due(settings, now=None) -> bool:
	"""Whether a timed backup should run now (checked every hour)."""
	if not cint(settings.auto_backup):
		return False
	now = now or now_datetime()
	if now.hour < cint(settings.backup_hour):
		return False
	last = get_datetime(settings.last_scheduled_on) if settings.last_scheduled_on else None
	if last and last.date() >= now.date():
		return False
	if settings.frequency == "Weekly":
		if last and (now - last).days > 8:
			return True  # the server was off on the day: catch up
		return WEEKDAYS[now.weekday()] == settings.weekday
	return True


def run_scheduled_backup():
	"""Hourly (long queue): run the timed backup when it is due."""
	settings = get_settings()
	if not is_due(settings):
		return
	from retail_management.services import backup_drive

	upload = backup_drive.is_connected()
	status, error = "Done", None
	try:
		run_backup(kind="Scheduled", upload=upload)
		if not upload:
			status = "Done (kept on the server only: Google Drive is not connected)"
	except BackupBusy:
		return
	except Exception as e:
		status, error = "Failed", _error_text(e)
		frappe.log_error(title="Retail timed backup failed")

	frappe.db.set_single_value(
		SETTINGS,
		{"last_scheduled_on": now_datetime(), "last_status": status, "last_error": error},
	)
	frappe.db.commit()
	if error and settings.notify_email:
		frappe.sendmail(
			recipients=[settings.notify_email],
			subject=_("Backup failed on {0}").format(frappe.local.site),
			message=_("The timed backup failed:<br><br>{0}<br><br>See the Backups page in the desk.").format(
				frappe.utils.escape_html(error)
			),
			now=True,
		)


# --- Restore -----------------------------------------------------------------


def _kept_settings() -> dict:
	from frappe.utils.password import get_decrypted_password

	values = frappe.db.get_singles_dict(SETTINGS)
	kept = {key: values.get(key) for key in _KEPT_SETTINGS}
	kept["__token"] = get_decrypted_password(SETTINGS, SETTINGS, "refresh_token", raise_exception=False)
	return kept


def _put_back_settings(kept: dict):
	from frappe.utils.password import remove_encrypted_password, set_encrypted_password

	kept = dict(kept)
	token = kept.pop("__token", None)
	frappe.db.set_single_value(SETTINGS, kept)
	remove_encrypted_password(SETTINGS, SETTINGS, "refresh_token")
	if token:
		set_encrypted_password(SETTINGS, SETTINGS, token, "refresh_token")
		frappe.db.set_single_value(SETTINGS, "refresh_token", "*" * 10)
	else:
		frappe.db.set_single_value(SETTINGS, "refresh_token", None)


def _extract_member(bundle: zipfile.ZipFile, arcname: str, folder: str) -> str:
	target = os.path.join(folder, arcname)
	with bundle.open(arcname) as source, open(target, "wb") as out:
		shutil.copyfileobj(source, out, 1024 * 1024)
	return target


_FILE_ROOTS = (["public", "files"], ["private", "files"])


def _restore_files(archive: str) -> int:
	"""Unpack a Frappe files archive into this site. Members look like
	./<backup's site>/private/files/x.pdf: the site folder is dropped (the
	backup may come from another site name) and only public/files and
	private/files are written. Returns the number of files written."""
	import tarfile

	site_path = os.path.abspath(frappe.get_site_path())
	written = 0
	with tarfile.open(archive, "r:*") as tar:
		for member in tar:
			parts = [p for p in member.name.replace("\\", "/").split("/") if p not in ("", ".")]
			if len(parts) < 3 or parts[1:3] not in _FILE_ROOTS or ".." in parts:
				continue
			if not (member.isfile() or member.isdir()):
				continue
			member.name = "/".join(parts[1:])
			tar.extract(member, site_path, filter="data")
			written += member.isfile()
	return written


def _migrate():
	sites_path = os.path.abspath(os.path.join(frappe.get_site_path(), ".."))
	return subprocess.run(
		[sys.executable, "-m", "frappe.utils.bench_helper", "frappe", "--site", frappe.local.site, "migrate"],
		cwd=sites_path,
		capture_output=True,
		text=True,
		timeout=3600,
	)


@contextmanager
def _plain(member: str, encrypted: bool):
	"""The member, decrypted in place for the duration if the backup was encrypted."""
	if encrypted:
		from frappe.utils.backups import decrypt_backup, get_or_generate_backup_encryption_key

		with decrypt_backup(member, get_or_generate_backup_encryption_key()):
			yield member
	else:
		yield member


def restore_bundle(path: str, user: str | None = None) -> dict:
	"""Replace this site's data with the bundle's. Returns a summary."""
	from frappe.database.mariadb.setup_db import import_db_from_sql
	from frappe.installer import is_partial, validate_database_sql

	manifest = read_manifest(path)
	encrypted = bool(manifest.get("encrypted"))
	started = now_datetime()

	# 1. A fresh backup of what is here now, so the restore can be undone.
	safety = make_bundle(include_files=True, kind="Before restore")
	safety_size = round(os.path.getsize(safety) / 1048576, 1)
	kept = _kept_settings()

	with tempfile.TemporaryDirectory(dir=backup_dir(), prefix=".restore-") as work:
		with zipfile.ZipFile(path) as bundle:
			files = {key: _extract_member(bundle, arc, work) for key, arc in manifest["members"].items()}

		with _plain(files["database"], encrypted) as sql:
			if is_partial(sql):
				frappe.throw(_("This is a partial backup and cannot replace the whole site."))
			validate_database_sql(sql, _raise=True)
			# 2. The database: every table in the dump is dropped and recreated.
			frappe.db.commit()
			import_db_from_sql(source_sql=sql)

		# 3. The files.
		for key in ("public_files", "private_files"):
			if key in files:
				with _plain(files[key], encrypted) as archive:
					_restore_files(archive)

	frappe.db.rollback()
	frappe.clear_cache()

	# 4. Bring the restored schema up to this code.
	result = _migrate()
	migrate_ok = result.returncode == 0
	frappe.db.rollback()
	frappe.clear_cache()

	# 5. This server's schedule and Drive connection, and the log.
	_put_back_settings(kept)
	finished = now_datetime()
	frappe.get_doc(
		{
			"doctype": RUN,
			"kind": "Before restore",
			"status": "Done",
			"started_on": started,
			"finished_on": finished,
			"file_name": os.path.basename(safety),
			"size_mb": safety_size,
			"includes_files": 1,
			"note": _("Taken automatically before restoring {0}.").format(os.path.basename(path)),
		}
	).insert(ignore_permissions=True)
	note = _("Restored from a backup made {0} on {1}.").format(
		str(manifest.get("created", "?"))[:16].replace("T", " "), manifest.get("site")
	)
	if user:
		note += " " + _("Started by {0}.").format(user)
	if not migrate_ok:
		note += " " + _("Migrate failed, run bench migrate: {0}").format((result.stderr or "")[-600:])
	frappe.get_doc(
		{
			"doctype": RUN,
			"kind": "Restore",
			"status": "Done" if migrate_ok else "Failed",
			"started_on": started,
			"finished_on": finished,
			"file_name": os.path.basename(path),
			"size_mb": round(os.path.getsize(path) / 1048576, 1),
			"includes_files": int(bool(manifest.get("includes_files"))),
			"note": note,
		}
	).insert(ignore_permissions=True)
	frappe.db.commit()
	return {"safety_copy": os.path.basename(safety), "migrated": migrate_ok}


def restore_job(path: str, user: str | None = None, remove_after: bool = False):
	"""Background job started from the Backups page."""
	try:
		with _busy("restore"):
			restore_bundle(path, user=user)
	except BackupBusy:
		return
	except Exception as error:
		frappe.db.rollback()
		frappe.log_error(title="Retail restore failed")
		frappe.get_doc(
			{
				"doctype": RUN,
				"kind": "Restore",
				"status": "Failed",
				"started_on": now_datetime(),
				"finished_on": now_datetime(),
				"file_name": os.path.basename(path),
				"note": _error_text(error),
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
	finally:
		if remove_after and os.path.exists(path):
			os.remove(path)
