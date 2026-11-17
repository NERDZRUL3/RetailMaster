"""Whole-site backups: one zip with the database and the attached files, safe
handling of uploaded files, and when timed backups run."""

import json
import os
import subprocess
import tempfile
import zipfile
from datetime import datetime

import frappe
from frappe.tests import IntegrationTestCase

from retail_management.api import backup as backup_api
from retail_management.services import backup
from retail_management.setup import ROLE_CASHIER, ensure_roles
from retail_management.tests.test_shop_permissions import make_user


def _settings(**values):
	return frappe._dict(
		{"auto_backup": 1, "frequency": "Daily", "weekday": "Sunday", "backup_hour": 2, "last_scheduled_on": None}
		| values
	)


class TestBackup(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_roles()
		cls.cashier = make_user("rm_backup_cashier@example.com", ROLE_CASHIER)

	def setUp(self):
		frappe.set_user("Administrator")
		self.made = []

	def tearDown(self):
		frappe.set_user("Administrator")
		for path in self.made:
			if os.path.exists(path):
				os.remove(path)

	def test_bundle_holds_database_and_scanned_files(self):
		scan = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "_rm_backup_scan.txt",
				"is_private": 1,
				"content": b"delivery note scan",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		try:
			path = backup.make_bundle(include_files=True)
			self.made.append(path)
			self.assertTrue(backup.BUNDLE_NAME.match(os.path.basename(path)))

			manifest = backup.read_manifest(path)
			self.assertEqual(manifest["site"], frappe.local.site)
			self.assertTrue(manifest["includes_files"])
			self.assertEqual(set(manifest["members"]), {"database", "public_files", "private_files"})

			with tempfile.TemporaryDirectory() as work, zipfile.ZipFile(path) as bundle:
				bundle.extractall(work)
				members = manifest["members"]
				dump = subprocess.run(
					["zgrep", "-c", "CREATE TABLE `tabRetail Shop`", os.path.join(work, members["database"])],
					capture_output=True,
					text=True,
				)
				self.assertGreater(int(dump.stdout.strip() or 0), 0)
				listing = subprocess.run(
					["tar", "tzf", os.path.join(work, members["private_files"])],
					capture_output=True,
					text=True,
					check=True,
				).stdout
				self.assertIn("private/files/_rm_backup_scan", listing)
		finally:
			scan.delete(ignore_permissions=True)
			frappe.db.commit()

	def test_database_only_bundle(self):
		path = backup.make_bundle(include_files=False)
		self.made.append(path)
		manifest = backup.read_manifest(path)
		self.assertFalse(manifest["includes_files"])
		self.assertEqual(set(manifest["members"]), {"database"})

	def test_run_is_logged_and_old_copies_pruned(self):
		run = backup.run_backup(kind="Manual", include_files=False)
		doc = frappe.get_doc(backup.RUN, run)
		kept = os.path.join(backup.backup_dir(), doc.file_name)
		self.made.append(kept)
		self.assertEqual(doc.status, "Done")
		self.assertGreater(doc.size_mb, 0)
		self.assertTrue(os.path.exists(kept))
		self.addCleanup(frappe.delete_doc, backup.RUN, run, force=True)

		old = os.path.join(backup.backup_dir(), "retail-backup-test-19990101-000000.zip")
		with open(old, "wb") as f:
			f.write(b"old")
		os.utime(old, (0, 0))
		self.made.append(old)
		backup.prune_local(1)
		self.assertFalse(os.path.exists(old))
		self.assertTrue(os.path.exists(kept))

	def test_unexpected_files_are_refused(self):
		folder = backup.incoming_dir()

		def write(name, members: dict):
			path = os.path.join(folder, name)
			with zipfile.ZipFile(path, "w") as z:
				for arcname, data in members.items():
					z.writestr(arcname, data)
			self.made.append(path)
			return path

		not_zip = os.path.join(folder, "not-a-zip.zip")
		with open(not_zip, "wb") as f:
			f.write(b"hello")
		self.made.append(not_zip)

		cases = [
			not_zip,
			write("no-manifest.zip", {"database.sql.gz": b"x"}),
			write("no-db.zip", {"manifest.json": json.dumps({"members": {}})}),
			write(
				"escape.zip",
				{
					"manifest.json": json.dumps({"members": {"database": "../database.sql.gz"}}),
					"../database.sql.gz": b"x",
				},
			),
			write(
				"extra.zip",
				{
					"manifest.json": json.dumps({"members": {"database": "d.sql.gz", "code": "evil.py"}}),
					"d.sql.gz": b"x",
					"evil.py": b"x",
				},
			),
			write("missing.zip", {"manifest.json": json.dumps({"members": {"database": "d.sql.gz"}})}),
		]
		for path in cases:
			with self.subTest(path=os.path.basename(path)), self.assertRaises(frappe.ValidationError):
				backup.read_manifest(path)

	def test_file_names_cannot_leave_the_backups_folder(self):
		for name in ("../site_config.json", "retail-backup-../../x.zip", "x.zip", "", "retail-backup-a/b.zip"):
			with self.subTest(name=name), self.assertRaises(frappe.ValidationError):
				backup.bundle_path(name)
		self.assertTrue(backup.bundle_path("retail-backup-ok-1.zip").endswith("retail-backup-ok-1.zip"))

	def test_restore_needs_the_confirm_word(self):
		path = backup.make_bundle(include_files=False)
		self.made.append(path)
		with self.assertRaises(frappe.ValidationError):
			backup_api.start_restore(os.path.basename(path), "yes")

	def test_daily_schedule(self):
		at = datetime(2026, 11, 17, 3, 0)
		self.assertTrue(backup.is_due(_settings(), at))
		self.assertFalse(backup.is_due(_settings(auto_backup=0), at))
		self.assertFalse(backup.is_due(_settings(backup_hour=4), at))
		self.assertFalse(backup.is_due(_settings(last_scheduled_on="2026-11-17 02:00:00"), at))
		self.assertTrue(backup.is_due(_settings(last_scheduled_on="2026-11-16 02:00:00"), at))

	def test_weekly_schedule(self):
		tuesday = datetime(2026, 11, 17, 3, 0)
		weekly = {"frequency": "Weekly", "last_scheduled_on": "2026-11-10 02:00:00"}
		self.assertTrue(backup.is_due(_settings(weekday="Tuesday", **weekly), tuesday))
		self.assertFalse(backup.is_due(_settings(weekday="Sunday", **weekly), tuesday))
		# Missed the day (server off): catches up.
		self.assertTrue(
			backup.is_due(
				_settings(weekday="Sunday", frequency="Weekly", last_scheduled_on="2026-11-01 02:00:00"), tuesday
			)
		)

	def test_only_system_managers(self):
		frappe.set_user(self.cashier)
		for call in (
			backup_api.overview,
			lambda: backup_api.start_backup(),
			lambda: backup_api.download("retail-backup-x.zip"),
			lambda: backup_api.start_restore("retail-backup-x.zip", "RESTORE"),
			lambda: backup_api.connect_drive(),
		):
			with self.assertRaises(frappe.PermissionError):
				call()

	def test_restored_files_land_only_in_the_files_folders(self):
		import io
		import tarfile
		from unittest.mock import patch

		with tempfile.TemporaryDirectory() as work:
			archive = os.path.join(work, "files.tgz")
			with tarfile.open(archive, "w:gz") as tar:

				def add(name, data=b"x", kind=tarfile.REGTYPE, target=""):
					info = tarfile.TarInfo(name)
					info.type, info.linkname, info.size = kind, target, len(data) if kind == tarfile.REGTYPE else 0
					tar.addfile(info, io.BytesIO(data) if kind == tarfile.REGTYPE else None)

				add("./other.site/private/files/scan.pdf", b"scan")
				add("./other.site/public/files/logo.png", b"logo")
				add("./other.site/site_config.json", b"{}")
				add("./other.site/private/files/../../../escape.txt")
				add("./other.site/public/files/link", kind=tarfile.SYMTYPE, target="/etc/passwd")

			site = os.path.join(work, "site")
			os.makedirs(site)
			with patch("frappe.get_site_path", return_value=site):
				written = backup._restore_files(archive)

			self.assertEqual(written, 2)
			with open(os.path.join(site, "private", "files", "scan.pdf"), "rb") as f:
				self.assertEqual(f.read(), b"scan")
			self.assertTrue(os.path.exists(os.path.join(site, "public", "files", "logo.png")))
			self.assertFalse(os.path.exists(os.path.join(site, "site_config.json")))
			self.assertFalse(os.path.lexists(os.path.join(site, "public", "files", "link")))
			self.assertFalse(os.path.exists(os.path.join(work, "escape.txt")))

	def test_settings_never_saved_still_include_files(self):
		frappe.db.delete("Singles", {"doctype": backup.SETTINGS})
		frappe.clear_document_cache(backup.SETTINGS, backup.SETTINGS)
		settings = backup.get_settings()
		self.assertEqual(settings.include_files, 1)
		self.assertEqual(settings.keep_on_server, 3)
		self.assertEqual(settings.frequency, "Daily")

	def test_dump_leaves_out_the_run_log_and_is_not_partial(self):
		from frappe.installer import is_partial

		path = backup.make_bundle(include_files=False)
		self.made.append(path)
		with tempfile.TemporaryDirectory() as work, zipfile.ZipFile(path) as bundle:
			sql = os.path.join(work, "db.sql.gz")
			with open(sql, "wb") as out:
				out.write(bundle.read(backup.read_manifest(path)["members"]["database"]))
			self.assertFalse(is_partial(sql))
			found = subprocess.run(["zgrep", "-c", "tabRetail Backup Run", sql], capture_output=True, text=True)
			self.assertEqual(found.stdout.strip(), "0")

	def test_cut_off_runs_are_marked_failed(self):
		run = frappe.get_doc(
			{"doctype": backup.RUN, "kind": "Manual", "status": "Running", "started_on": frappe.utils.now_datetime()}
		).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, backup.RUN, run.name, force=True)
		backup.close_stale_runs()
		self.assertEqual(frappe.db.get_value(backup.RUN, run.name, "status"), "Failed")
