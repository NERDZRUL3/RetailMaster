"""Owners edit branding from the custom interface; nobody else can."""

from io import BytesIO

import frappe
from frappe.tests import IntegrationTestCase
from PIL import Image

from retail_management.api.session import get_context
from retail_management.api.settings import get_settings, remove_logo, save_settings, store_logo
from retail_management.setup import ROLE_CASHIER, ROLE_MANAGER, ROLE_OWNER, ROLE_PARTNER, ensure_roles
from retail_management.tests.test_shop_permissions import make_user


def png_bytes(size=(32, 32)) -> bytes:
	buffer = BytesIO()
	Image.new("RGB", size, (228, 103, 44)).save(buffer, format="PNG")
	return buffer.getvalue()


class TestSettingsApi(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_roles()
		cls.owner = make_user("rm_set_owner@example.com", ROLE_OWNER)
		cls.partner = make_user("rm_set_partner@example.com", ROLE_PARTNER)
		cls.manager = make_user("rm_set_manager@example.com", ROLE_MANAGER)
		cls.cashier = make_user("rm_set_cashier@example.com", ROLE_CASHIER)
		# tearDown rolls back each test's settings changes; keep the users.
		frappe.db.commit()  # nosemgrep: test fixtures must survive per-test rollback

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		frappe.clear_document_cache("Retail Settings", "Retail Settings")

	def test_owner_can_read_and_save(self):
		frappe.set_user(self.owner)
		result = save_settings(
			app_name="  Papeterie Atlas  ",
			brand_color="#E4672C",
			default_language="fr",
			enable_en="0",
			enable_fr="1",
			enable_ar="1",
		)
		self.assertEqual(result["app_name"], "Papeterie Atlas")
		self.assertEqual(result["branding"]["brand_color"], "#e4672c")
		self.assertEqual(result["branding"]["languages"], ["fr", "ar"])
		self.assertEqual(get_settings()["default_language"], "fr")

	def test_owner_sees_settings_entry_point(self):
		frappe.set_user(self.owner)
		self.assertTrue(get_context()["can_edit_settings"])

	def test_others_do_not_see_settings_entry_point(self):
		for user in (self.partner, self.manager, self.cashier):
			frappe.set_user(user)
			self.assertFalse(get_context()["can_edit_settings"], user)

	def test_others_cannot_read_or_save(self):
		for user in (self.partner, self.manager, self.cashier):
			frappe.set_user(user)
			with self.assertRaises(frappe.PermissionError, msg=user):
				get_settings()
			with self.assertRaises(frappe.PermissionError, msg=user):
				save_settings(app_name="Hacked")

	def test_invalid_values_are_rejected(self):
		frappe.set_user(self.owner)
		with self.assertRaises(frappe.ValidationError):
			save_settings(brand_color="orange")
		with self.assertRaises(frappe.ValidationError):
			save_settings(enable_en="0", enable_fr="0", enable_ar="0")

	def test_owner_can_upload_and_remove_png_logo(self):
		frappe.set_user(self.owner)
		url = store_logo(png_bytes(), "my logo.png")
		self.assertTrue(url.startswith("/files/"))
		self.assertEqual(get_settings()["branding"]["logo"], url)
		self.assertIsNone(remove_logo()["branding"]["logo"])

	def test_non_image_logo_is_rejected(self):
		frappe.set_user(self.owner)
		with self.assertRaises(frappe.ValidationError):
			store_logo(b"not an image", "logo.png")

	def test_svg_logo_is_rejected(self):
		frappe.set_user(self.owner)
		svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
		with self.assertRaises(frappe.ValidationError):
			store_logo(svg, "logo.svg")

	def test_oversized_logo_is_rejected(self):
		frappe.set_user(self.owner)
		with self.assertRaises(frappe.ValidationError):
			store_logo(b"\x89PNG" + b"0" * (2 * 1024 * 1024), "logo.png")

	def test_cashier_cannot_upload_logo(self):
		frappe.set_user(self.cashier)
		with self.assertRaises(frappe.PermissionError):
			store_logo(png_bytes(), "logo.png")
