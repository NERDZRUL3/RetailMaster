"""A user must only ever see the shops they are assigned to.

Covers list queries, single-document checks, the whitelisted API and the
access records themselves. All users and shops here are synthetic.
"""

import frappe
from frappe.tests import IntegrationTestCase

from retail_management.api.shops import get_my_shops
from retail_management.services import permissions
from retail_management.setup import (
	ROLE_CASHIER,
	ROLE_MANAGER,
	ROLE_OWNER,
	ROLE_PARTNER,
	ensure_roles,
)

BUSINESS = "_RM Test Business"
SHOP_1 = "_RM Test Shop 1"
SHOP_2 = "_RM Test Shop 2"


def get_company() -> str:
	company = frappe.db.get_value("Company", {}, "name")
	if company:
		return company
	return (
		frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": "_RM Test Company",
				"abbr": "_RMT",
				"default_currency": "MAD",
				"country": "Morocco",
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def make_user(email: str, *roles: str) -> str:
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
	else:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
	if roles:
		user.add_roles(*roles)
	return email


def make_shop(name: str, company: str) -> str:
	if not frappe.db.exists("Retail Shop", name):
		frappe.get_doc(
			{
				"doctype": "Retail Shop",
				"shop_name": name,
				"retail_business": BUSINESS,
				"company": company,
			}
		).insert(ignore_permissions=True)
	return name


def grant(user: str, shop: str) -> None:
	if not frappe.db.exists("Retail Shop Access", {"user": user, "retail_shop": shop}):
		frappe.get_doc({"doctype": "Retail Shop Access", "user": user, "retail_shop": shop}).insert(
			ignore_permissions=True
		)


class TestShopPermissions(IntegrationTestCase):
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

		cls.owner = make_user("rm_owner@example.com", ROLE_OWNER)
		cls.partner = make_user("rm_partner@example.com", ROLE_PARTNER)
		cls.manager_1 = make_user("rm_manager1@example.com", ROLE_MANAGER)
		cls.cashier_1 = make_user("rm_cashier1@example.com", ROLE_CASHIER)
		cls.cashier_2 = make_user("rm_cashier2@example.com", ROLE_CASHIER)
		cls.cashier_unassigned = make_user("rm_cashier_none@example.com", ROLE_CASHIER)
		cls.outsider = make_user("rm_outsider@example.com")

		grant(cls.manager_1, SHOP_1)
		grant(cls.cashier_1, SHOP_1)
		grant(cls.cashier_2, SHOP_2)

	def tearDown(self):
		frappe.set_user("Administrator")

	def visible_shops(self, user: str) -> set[str]:
		frappe.set_user(user)
		shops = frappe.get_list("Retail Shop", filters={"name": ("in", [SHOP_1, SHOP_2])}, pluck="name")
		return set(shops)

	# --- list queries -----------------------------------------------------

	def test_owner_sees_both_shops(self):
		self.assertEqual(self.visible_shops(self.owner), {SHOP_1, SHOP_2})

	def test_partner_sees_both_shops(self):
		self.assertEqual(self.visible_shops(self.partner), {SHOP_1, SHOP_2})

	def test_cashier_sees_only_own_shop(self):
		self.assertEqual(self.visible_shops(self.cashier_1), {SHOP_1})
		self.assertEqual(self.visible_shops(self.cashier_2), {SHOP_2})

	def test_manager_sees_only_assigned_shop(self):
		self.assertEqual(self.visible_shops(self.manager_1), {SHOP_1})

	def test_unassigned_cashier_sees_no_shop(self):
		self.assertEqual(self.visible_shops(self.cashier_unassigned), set())

	def test_user_without_retail_role_is_refused(self):
		frappe.set_user(self.outsider)
		with self.assertRaises(frappe.PermissionError):
			frappe.get_list("Retail Shop")

	def test_explicit_filter_cannot_reach_other_shop(self):
		frappe.set_user(self.cashier_1)
		self.assertEqual(frappe.get_list("Retail Shop", filters={"name": SHOP_2}), [])

	# --- single documents -------------------------------------------------

	def test_cashier_can_read_own_shop_document(self):
		frappe.set_user(self.cashier_1)
		self.assertTrue(frappe.has_permission("Retail Shop", "read", doc=SHOP_1))

	def test_cashier_cannot_read_other_shop_document(self):
		frappe.set_user(self.cashier_1)
		self.assertFalse(frappe.has_permission("Retail Shop", "read", doc=SHOP_2))
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc("Retail Shop", SHOP_2).check_permission("read")

	def test_cashier_cannot_change_own_shop(self):
		frappe.set_user(self.cashier_1)
		self.assertFalse(frappe.has_permission("Retail Shop", "write", doc=SHOP_1))
		shop = frappe.get_doc("Retail Shop", SHOP_1)
		shop.enabled = 0
		with self.assertRaises(frappe.PermissionError):
			shop.save()

	def test_partner_can_read_but_not_change(self):
		frappe.set_user(self.partner)
		self.assertTrue(frappe.has_permission("Retail Shop", "read", doc=SHOP_2))
		self.assertFalse(frappe.has_permission("Retail Shop", "write", doc=SHOP_2))

	def test_owner_can_change_shop(self):
		frappe.set_user(self.owner)
		self.assertTrue(frappe.has_permission("Retail Shop", "write", doc=SHOP_2))

	# --- whitelisted API --------------------------------------------------

	def test_api_returns_only_own_shop(self):
		frappe.set_user(self.cashier_1)
		names = {row["name"] for row in get_my_shops()}
		self.assertIn(SHOP_1, names)
		self.assertNotIn(SHOP_2, names)

	def test_api_refuses_user_without_retail_role(self):
		frappe.set_user(self.outsider)
		with self.assertRaises(frappe.PermissionError):
			get_my_shops()

	# --- access records ---------------------------------------------------

	def test_cashier_cannot_list_access_records(self):
		frappe.set_user(self.cashier_1)
		with self.assertRaises(frappe.PermissionError):
			frappe.get_list("Retail Shop Access")

	def test_cashier_cannot_grant_themselves_access(self):
		frappe.set_user(self.cashier_1)
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc(
				{"doctype": "Retail Shop Access", "user": self.cashier_1, "retail_shop": SHOP_2}
			).insert()

	def test_manager_cannot_grant_access(self):
		frappe.set_user(self.manager_1)
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc(
				{"doctype": "Retail Shop Access", "user": self.cashier_1, "retail_shop": SHOP_2}
			).insert()

	def test_duplicate_access_is_rejected(self):
		with self.assertRaises(frappe.DuplicateEntryError):
			frappe.get_doc(
				{"doctype": "Retail Shop Access", "user": self.cashier_1, "retail_shop": SHOP_1}
			).insert(ignore_permissions=True)

	def test_cashier_cannot_list_businesses(self):
		frappe.set_user(self.cashier_1)
		with self.assertRaises(frappe.PermissionError):
			frappe.get_list("Retail Business")

	# --- service helpers --------------------------------------------------

	def test_assert_shop_access(self):
		permissions.assert_shop_access(SHOP_1, self.cashier_1)
		permissions.assert_shop_access(SHOP_2, self.owner)
		with self.assertRaises(frappe.PermissionError):
			permissions.assert_shop_access(SHOP_2, self.cashier_1)

	def test_query_condition_for_unassigned_user_matches_nothing(self):
		self.assertEqual(permissions.shop_query_conditions(self.cashier_unassigned), "1=0")
