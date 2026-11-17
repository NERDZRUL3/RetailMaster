"""Owners set up shops from the retail interface: a name is enough, the
warehouse comes with it, and only owners may do it."""

import frappe
from frappe.tests import IntegrationTestCase

from retail_management.api import shops
from retail_management.setup import ROLE_CASHIER, ROLE_OWNER, ensure_roles
from retail_management.tests.test_shop_permissions import make_user
from retail_management.tests.test_shop_stock_scoping import get_company

NEW_SHOP = "_RM Setup Shop"
RENAMED = "_RM Setup Shop Renamed"


def remove_shop(name: str):
	if frappe.db.exists("Retail Shop", name):
		warehouse = frappe.db.get_value("Retail Shop", name, "warehouse")
		frappe.delete_doc("Retail Shop", name, ignore_permissions=True, force=True)
		if warehouse and frappe.db.exists("Warehouse", warehouse):
			frappe.delete_doc("Warehouse", warehouse, ignore_permissions=True, force=True)


class TestShopSetupApi(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_roles()
		cls.company = get_company()
		cls.owner = make_user("rm_setup_owner@example.com", ROLE_OWNER)
		cls.cashier = make_user("rm_setup_cashier@example.com", ROLE_CASHIER)

	def setUp(self):
		frappe.set_user("Administrator")
		remove_shop(NEW_SHOP)
		remove_shop(RENAMED)

	def tearDown(self):
		frappe.set_user("Administrator")
		remove_shop(NEW_SHOP)

	def test_owner_creates_a_shop_with_its_own_warehouse(self):
		frappe.set_user(self.owner)
		shop = shops.create_shop(f"  {NEW_SHOP} ", self.company)
		self.assertEqual(shop.name, NEW_SHOP)
		self.assertEqual(shop.enabled, 1)
		self.assertTrue(shop.warehouse)
		self.assertEqual(frappe.db.get_value("Warehouse", shop.warehouse, "company"), self.company)
		self.assertTrue(frappe.db.get_value("Retail Shop", NEW_SHOP, "retail_business"))
		self.assertIn(NEW_SHOP, [s.name for s in shops.get_shop_setup()["shops"]])

	def test_duplicate_and_empty_names_are_refused(self):
		frappe.set_user(self.owner)
		shops.create_shop(NEW_SHOP, self.company)
		with self.assertRaises(frappe.ValidationError):
			shops.create_shop(NEW_SHOP, self.company)
		with self.assertRaises(frappe.ValidationError):
			shops.create_shop("   ", self.company)

	def test_unknown_company_is_refused(self):
		frappe.set_user(self.owner)
		with self.assertRaises(frappe.ValidationError):
			shops.create_shop(NEW_SHOP, "_RM No Such Company")

	def test_owner_switches_a_shop_off_and_on(self):
		frappe.set_user(self.owner)
		shops.create_shop(NEW_SHOP, self.company)
		self.assertEqual(shops.set_shop_enabled(NEW_SHOP, 0).enabled, 0)
		self.assertEqual(shops.set_shop_enabled(NEW_SHOP, "1").enabled, 1)

	def test_owner_renames_a_shop_and_staff_access_follows(self):
		frappe.set_user(self.owner)
		shops.create_shop(NEW_SHOP, self.company)
		frappe.set_user("Administrator")
		frappe.get_doc({"doctype": "Retail Shop Access", "user": self.cashier, "retail_shop": NEW_SHOP}).insert(
			ignore_permissions=True
		)
		frappe.set_user(self.owner)
		try:
			renamed = shops.rename_shop(NEW_SHOP, f"  {RENAMED} ")
			self.assertEqual(renamed.name, RENAMED)
			self.assertEqual(renamed.shop_name, RENAMED)
			self.assertFalse(frappe.db.exists("Retail Shop", NEW_SHOP))
			self.assertEqual(
				frappe.get_all("Retail Shop Access", {"user": self.cashier}, pluck="retail_shop"), [RENAMED]
			)
			self.assertEqual(frappe.session.user, self.owner)
		finally:
			frappe.set_user("Administrator")
			frappe.db.delete("Retail Shop Access", {"user": self.cashier})
			remove_shop(RENAMED)

	def test_rename_to_an_existing_shop_is_refused(self):
		frappe.set_user(self.owner)
		shops.create_shop(NEW_SHOP, self.company)
		shops.create_shop(RENAMED, self.company)
		try:
			with self.assertRaises(frappe.ValidationError):
				shops.rename_shop(NEW_SHOP, RENAMED)
		finally:
			frappe.set_user("Administrator")
			remove_shop(RENAMED)

	def test_desk_tile_is_for_owners_not_staff(self):
		from retail_management.services.permissions import can_open_desk_app

		frappe.set_user(self.owner)
		self.assertTrue(can_open_desk_app())
		frappe.set_user(self.cashier)
		self.assertFalse(can_open_desk_app())

	def test_cashier_cannot_set_up_shops(self):
		frappe.set_user(self.cashier)
		with self.assertRaises(frappe.PermissionError):
			shops.get_shop_setup()
		with self.assertRaises(frappe.PermissionError):
			shops.create_shop(NEW_SHOP, self.company)
		with self.assertRaises(frappe.PermissionError):
			shops.set_shop_enabled(NEW_SHOP, 0)
		with self.assertRaises(frappe.PermissionError):
			shops.rename_shop(NEW_SHOP, RENAMED)
