"""The session API decides what the custom interface shows to whom."""

import frappe
from frappe.tests import IntegrationTestCase

from retail_management.api.session import get_context, set_language
from retail_management.setup import ROLE_CASHIER, ROLE_MANAGER, ROLE_OWNER, ensure_roles
from retail_management.tests.test_shop_permissions import (
	BUSINESS,
	SHOP_1,
	SHOP_2,
	get_company,
	grant,
	make_shop,
	make_user,
)


class TestSessionApi(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_roles()
		company = get_company()
		if not frappe.db.exists("Retail Business", BUSINESS):
			frappe.get_doc({"doctype": "Retail Business", "business_name": BUSINESS}).insert(
				ignore_permissions=True
			)
		make_shop(SHOP_1, company)
		make_shop(SHOP_2, company)

		cls.owner = make_user("rm_s_owner@example.com", ROLE_OWNER)
		cls.manager = make_user("rm_s_manager@example.com", ROLE_MANAGER)
		cls.cashier = make_user("rm_s_cashier@example.com", ROLE_CASHIER)
		cls.outsider = make_user("rm_s_outsider@example.com")
		grant(cls.manager, SHOP_1)
		grant(cls.cashier, SHOP_1)

	def tearDown(self):
		frappe.set_user("Administrator")

	def shop_names(self, context) -> set[str]:
		return {shop["name"] for shop in context["shops"]} & {SHOP_1, SHOP_2}

	def test_guest_is_not_authenticated_and_gets_nothing_else(self):
		frappe.set_user("Guest")
		context = get_context()
		self.assertFalse(context["authenticated"])
		self.assertEqual(set(context), {"authenticated", "branding"})

	def test_owner_lands_on_owner_home_with_all_shops(self):
		frappe.set_user(self.owner)
		context = get_context()
		self.assertEqual(context["home"], "owner")
		self.assertEqual(self.shop_names(context), {SHOP_1, SHOP_2})

	def test_cashier_lands_on_cashier_home_with_own_shop_only(self):
		frappe.set_user(self.cashier)
		context = get_context()
		self.assertEqual(context["home"], "cashier")
		self.assertEqual(self.shop_names(context), {SHOP_1})

	def test_manager_lands_on_manager_home_with_own_shop_only(self):
		frappe.set_user(self.manager)
		context = get_context()
		self.assertEqual(context["home"], "manager")
		self.assertEqual(self.shop_names(context), {SHOP_1})

	def test_user_without_retail_role_has_no_home_and_no_shops(self):
		frappe.set_user(self.outsider)
		context = get_context()
		self.assertTrue(context["authenticated"])
		self.assertIsNone(context["home"])
		self.assertEqual(context["shops"], [])

	def test_set_language_stores_supported_language(self):
		frappe.set_user(self.cashier)
		self.assertEqual(set_language("ar"), "ar")
		self.assertEqual(frappe.db.get_value("User", self.cashier, "language"), "ar")
		self.assertEqual(get_context()["language"], "ar")

	def test_set_language_rejects_unsupported_language(self):
		frappe.set_user(self.cashier)
		with self.assertRaises(frappe.ValidationError):
			set_language("de")
