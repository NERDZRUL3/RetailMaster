"""Customer settings (branding and languages), edited from the custom interface.

Only users with write permission on Retail Settings (Retail Owner, System
Manager) may read or change them here. Frappe's own permission check runs on
every save as well.
"""

from io import BytesIO

import frappe
from frappe import _
from PIL import Image, UnidentifiedImageError

from retail_management.services.branding import get_branding

SETTINGS = "Retail Settings"
EDITABLE_FIELDS = ("app_name", "brand_color", "default_language", "enable_en", "enable_fr", "enable_ar")

MAX_LOGO_BYTES = 2 * 1024 * 1024
# SVG is refused on purpose: it can carry scripts.
LOGO_FORMATS = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}


def _require_write():
	frappe.has_permission(SETTINGS, "write", throw=True)


def _settings_payload() -> dict:
	settings = frappe.get_single(SETTINGS)
	return {
		"app_name": settings.app_name or "",
		"logo": settings.logo or None,
		"brand_color": settings.brand_color or "",
		"default_language": settings.default_language or "en",
		"enable_en": int(settings.enable_en or 0),
		"enable_fr": int(settings.enable_fr or 0),
		"enable_ar": int(settings.enable_ar or 0),
		"branding": get_branding(),
	}


@frappe.whitelist()
def get_settings() -> dict:
	_require_write()
	return _settings_payload()


@frappe.whitelist(methods=["POST"])
def save_settings(**values) -> dict:
	_require_write()
	settings = frappe.get_single(SETTINGS)
	for field in EDITABLE_FIELDS:
		if field in values:
			value = values[field]
			if field.startswith("enable_"):
				value = 1 if value in (1, "1", True, "true") else 0
			elif isinstance(value, str):
				value = value.strip() or None
			settings.set(field, value)
	settings.save()
	frappe.clear_document_cache(SETTINGS, SETTINGS)
	return _settings_payload()


def store_logo(content: bytes, filename: str) -> str:
	"""Validate an uploaded logo and attach it publicly to Retail Settings.

	Returns the public file URL. Raises ValidationError for anything that is
	not a small PNG, JPEG or WebP image.
	"""
	_require_write()
	if not content:
		frappe.throw(_("The file is empty."))
	if len(content) > MAX_LOGO_BYTES:
		frappe.throw(_("The logo must be smaller than 2 MB."))

	try:
		with Image.open(BytesIO(content)) as image:
			image.verify()
			image_format = image.format
	except (UnidentifiedImageError, OSError, SyntaxError):
		frappe.throw(_("The logo must be a PNG, JPEG or WebP image."))

	extension = LOGO_FORMATS.get(image_format)
	if not extension:
		frappe.throw(_("The logo must be a PNG, JPEG or WebP image."))

	# Permission on Retail Settings was checked above; the file is public on
	# purpose because the login page shows it before anyone signs in.
	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"logo.{extension}",
			"content": content,
			"is_private": 0,
			"attached_to_doctype": SETTINGS,
			"attached_to_name": SETTINGS,
			"attached_to_field": "logo",
		}
	).insert(ignore_permissions=True)

	settings = frappe.get_single(SETTINGS)
	settings.logo = file_doc.file_url
	settings.save()
	frappe.clear_document_cache(SETTINGS, SETTINGS)
	return file_doc.file_url


@frappe.whitelist(methods=["POST"])
def upload_logo() -> dict:
	_require_write()
	upload = frappe.request.files.get("file") if frappe.request else None
	if not upload:
		frappe.throw(_("No file was sent."))
	store_logo(upload.stream.read(MAX_LOGO_BYTES + 1), upload.filename or "logo")
	return _settings_payload()


@frappe.whitelist(methods=["POST"])
def remove_logo() -> dict:
	_require_write()
	settings = frappe.get_single(SETTINGS)
	settings.logo = None
	settings.save()
	frappe.clear_document_cache(SETTINGS, SETTINGS)
	return _settings_payload()
