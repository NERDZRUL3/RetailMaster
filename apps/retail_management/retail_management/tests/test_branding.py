"""Each customer can rebrand the interface through Retail Settings."""

import frappe
from frappe.tests import IntegrationTestCase

from retail_management.api.session import get_context, set_language
from retail_management.retail_management.doctype.retail_settings.retail_settings import contrast_with_white
from retail_management.services.branding import DEFAULT_APP_NAME, DEFAULT_BRAND_COLOR, get_branding
from retail_management.setup import ROLE_CASHIER, ROLE_OWNER, ensure_roles
from retail_management.tests.test_shop_permissions import make_user


def save_settings(**values):
	settings = frappe.get_single("Retail Settings")
	settings.update(
		{"default_language": "en", "enable_en": 1, "enable_fr": 1, "enable_ar": 1, **values}
	)
	settings.save()
	return settings


class TestBranding(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_roles()
		cls.owner = make_user("rm_b_owner@example.com", ROLE_OWNER)
		cls.cashier = make_user("rm_b_cashier@example.com", ROLE_CASHIER)
		# tearDown rolls back each test's settings changes; keep the users.
		frappe.db.commit()  # nosemgrep: test fixtures must survive per-test rollback

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		frappe.clear_document_cache("Retail Settings", "Retail Settings")

	def test_defaults_are_neutral(self):
		save_settings(app_name=None, logo=None, brand_color=None)
		branding = get_branding()
		self.assertEqual(branding["app_name"], DEFAULT_APP_NAME)
		self.assertEqual(branding["brand_color"], DEFAULT_BRAND_COLOR)
		self.assertEqual(branding["languages"], ["en", "fr", "ar"])
		self.assertIsNone(branding["logo"])

	def test_default_brand_colour_is_readable(self):
		self.assertGreaterEqual(contrast_with_white(DEFAULT_BRAND_COLOR), 4.5)

	def test_owner_can_rebrand(self):
		frappe.set_user(self.owner)
		save_settings(app_name="Papeterie Atlas", brand_color="#1d4ed8")
		branding = get_branding()
		self.assertEqual(branding["app_name"], "Papeterie Atlas")
		self.assertEqual(branding["brand_color"], "#1d4ed8")

	def test_guest_gets_branding_and_nothing_else(self):
		save_settings(app_name="Papeterie Atlas")
		frappe.set_user("Guest")
		context = get_context()
		self.assertEqual(set(context), {"authenticated", "branding"})
		self.assertFalse(context["authenticated"])
		self.assertEqual(context["branding"]["app_name"], "Papeterie Atlas")

	def test_cashier_cannot_change_settings(self):
		frappe.set_user(self.cashier)
		with self.assertRaises(frappe.PermissionError):
			save_settings(app_name="Hacked")

	def test_light_colour_is_kept_and_gets_a_readable_button_shade(self):
		save_settings(brand_color="#E4672C")
		branding = get_branding()
		self.assertEqual(branding["brand_color"], "#e4672c")
		self.assertLess(contrast_with_white(branding["brand_color"]), 4.5)
		self.assertGreaterEqual(contrast_with_white(branding["brand_color_strong"]), 4.5)
		self.assertNotEqual(branding["brand_color_strong"], "#000000")

	def test_dark_colour_is_used_as_is_for_buttons(self):
		save_settings(brand_color="#1d4ed8")
		self.assertEqual(get_branding()["brand_color_strong"], "#1d4ed8")

	def test_very_light_colour_still_gives_readable_buttons(self):
		save_settings(brand_color="#fde047")
		self.assertGreaterEqual(contrast_with_white(get_branding()["brand_color_strong"]), 4.5)

	def test_invalid_colour_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			save_settings(brand_color="blue")

	def test_at_least_one_language_is_required(self):
		with self.assertRaises(frappe.ValidationError):
			save_settings(enable_en=0, enable_fr=0, enable_ar=0)

	def test_default_language_must_be_enabled(self):
		with self.assertRaises(frappe.ValidationError):
			save_settings(default_language="ar", enable_ar=0)

	def test_private_logo_is_not_exposed(self):
		save_settings(logo="/private/files/logo.png")
		self.assertIsNone(get_branding()["logo"])

	def test_disabled_language_is_not_offered_or_accepted(self):
		save_settings(default_language="fr", enable_en=0, enable_ar=0)
		self.assertEqual(get_branding()["languages"], ["fr"])
		self.assertEqual(get_branding()["default_language"], "fr")

		frappe.set_user(self.cashier)
		with self.assertRaises(frappe.ValidationError):
			set_language("ar")
		self.assertEqual(set_language("fr"), "fr")
