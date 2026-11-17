"""Copies of backup bundles on Google Drive.

Uses Frappe's Google sign-in (Google Settings holds the OAuth client) with the
narrow drive.file scope: the app sees only the files and folder it created,
never the rest of the owner's Drive.
"""

import frappe
from frappe import _

from retail_management.services import backup
from retail_management.services.backup import BUNDLE_PREFIX, SETTINGS

DOMAIN = "retail_drive"
SCOPE = "https://www.googleapis.com/auth/drive.file"
CALLBACK = "retail_management.services.backup_drive.authorize_access"
PAGE_ROUTE = "/desk/retail-backups"
FOLDER_MIME = "application/vnd.google-apps.folder"
CHUNK = 8 * 1024 * 1024


def _oauth():
	from frappe.integrations import google_oauth

	google_oauth._SCOPES[DOMAIN] = SCOPE
	google_oauth._SERVICES[DOMAIN] = ("drive", "v3")
	google_oauth._DOMAIN_CALLBACK_METHODS[DOMAIN] = CALLBACK
	return google_oauth.GoogleOAuth(DOMAIN)


def redirect_uri() -> str:
	"""The address to register in the Google Cloud OAuth client."""
	from frappe.integrations.google_oauth import CALLBACK_METHOD
	from frappe.utils import get_request_site_address

	return get_request_site_address(True) + CALLBACK_METHOD


def google_ready() -> bool:
	settings = frappe.get_single("Google Settings")
	return bool(settings.enable and settings.client_id and settings.client_secret)


def _token() -> str | None:
	from frappe.utils.password import get_decrypted_password

	return get_decrypted_password(SETTINGS, SETTINGS, "refresh_token", raise_exception=False)


def is_connected() -> bool:
	return bool(_token())


def authorization_url() -> str:
	return _oauth().get_authentication_url(
		{
			"redirect": PAGE_ROUTE,
			"success_query_param": "drive=connected",
			"failure_query_param": "drive=failed",
		}
	)["url"]


def authorize_access(code: str | None = None, **_kwargs):
	"""Google sends the owner back here (through Frappe's callback) after consent."""
	frappe.only_for("System Manager")
	response = _oauth().authorize(code)
	token = response.get("refresh_token")
	if not token:
		frappe.throw(_("Google did not grant offline access. Remove the app's access in your Google account and connect again."))
	settings = backup.get_settings()
	settings.refresh_token = token
	settings.drive_folder_id = None
	settings.drive_account = None
	settings.save(ignore_permissions=True)
	try:
		about = _service().about().get(fields="user(emailAddress)").execute()
		frappe.db.set_single_value(SETTINGS, "drive_account", about["user"]["emailAddress"])
	except Exception:
		frappe.log_error(title="Retail backups: could not read the Google account")


def disconnect():
	from frappe.utils.password import remove_encrypted_password

	remove_encrypted_password(SETTINGS, SETTINGS, "refresh_token")
	frappe.db.set_single_value(
		SETTINGS, {"refresh_token": None, "drive_account": None, "drive_folder_id": None}
	)


def _service():
	token = _token()
	if not token:
		frappe.throw(_("Google Drive is not connected."))
	oauth = _oauth()
	access = oauth.refresh_access_token(token).get("access_token")
	return oauth.get_google_service_object(access, token)


def _folder(service) -> str:
	"""The backups folder on Drive, created the first time."""
	settings = backup.get_settings()
	if settings.drive_folder_id:
		try:
			found = service.files().get(fileId=settings.drive_folder_id, fields="id,trashed").execute()
			if not found.get("trashed"):
				return found["id"]
		except Exception:
			pass
	folder = (
		service.files()
		.create(body={"name": settings.drive_folder or "RetailMaster backups", "mimeType": FOLDER_MIME}, fields="id")
		.execute()
	)
	frappe.db.set_single_value(SETTINGS, "drive_folder_id", folder["id"])
	frappe.db.commit()
	return folder["id"]


def upload(path: str) -> str:
	"""Upload a bundle into the backups folder; returns the Drive file id."""
	import os

	from googleapiclient.http import MediaFileUpload

	service = _service()
	folder = _folder(service)
	media = MediaFileUpload(path, mimetype="application/zip", resumable=True, chunksize=CHUNK)
	request = service.files().create(
		body={"name": os.path.basename(path), "parents": [folder]}, media_body=media, fields="id"
	)
	response = None
	while response is None:
		_status, response = request.next_chunk(num_retries=3)
	return response["id"]


def prune(keep: int):
	"""Keep the newest `keep` backups in the Drive folder."""
	service = _service()
	folder = _folder(service)
	files = (
		service.files()
		.list(
			q=f"'{folder}' in parents and trashed = false and name contains '{BUNDLE_PREFIX}'",
			orderBy="createdTime desc",
			fields="files(id,name)",
			pageSize=1000,
		)
		.execute()
		.get("files", [])
	)
	for old in files[max(1, keep) :]:
		service.files().delete(fileId=old["id"]).execute()
