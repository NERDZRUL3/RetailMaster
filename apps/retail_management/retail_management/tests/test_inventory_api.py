"""Product catalogue and stock API: who may see and change what, per shop."""

import frappe
from frappe.tests import IntegrationTestCase

from retail_management.api import inventory
from retail_management.setup import (
	ROLE_CASHIER,
	ROLE_MANAGER,
	ROLE_OWNER,
	ensure_erpnext_permissions,
	ensure_roles,
)
from retail_management.tests.test_shop_permissions import make_user
from retail_management.tests.test_shop_stock_scoping import (
	BUSINESS,
	SHOP_A,
	SHOP_B,
	get_company,
	make_shop,
	receive_item,
)


def unique(prefix: str) -> str:
	return f"{prefix}-{frappe.generate_hash(length=6).upper()}"


def grant(user: str, shop: str):
	if not frappe.db.exists("Retail Shop Access", {"user": user, "retail_shop": shop}):
		frappe.get_doc({"doctype": "Retail Shop Access", "user": user, "retail_shop": shop}).insert(
			ignore_permissions=True
		)


class TestInventoryApi(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_roles()
		ensure_erpnext_permissions()
		cls.company = get_company()
		if not frappe.db.exists("Retail Business", BUSINESS):
			frappe.get_doc({"doctype": "Retail Business", "business_name": BUSINESS}).insert(
				ignore_permissions=True
			)
		make_shop(SHOP_A, cls.company)
		make_shop(SHOP_B, cls.company)
		cls.warehouse_a = frappe.db.get_value("Retail Shop", SHOP_A, "warehouse")
		cls.warehouse_b = frappe.db.get_value("Retail Shop", SHOP_B, "warehouse")

		cls.owner = make_user("rm_inv_owner@example.com", ROLE_OWNER)
		cls.manager = make_user("rm_inv_manager@example.com", ROLE_MANAGER)
		cls.manager_no_shop = make_user("rm_inv_manager_none@example.com", ROLE_MANAGER)
		cls.cashier = make_user("rm_inv_cashier@example.com", ROLE_CASHIER)
		grant(cls.manager, SHOP_A)
		grant(cls.cashier, SHOP_A)

		# A product with a barcode and stock in both shops.
		cls.barcode = unique("611")
		frappe.set_user("Administrator")
		cls.item = inventory.save_item(
			{
				"item_name": "Blue ballpoint pen",
				"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
				"stock_uom": "Nos",
				"barcodes": [cls.barcode],
				"price": 4.5,
				"reorder": [{"shop": SHOP_A, "level": 5, "qty": 20}, {"shop": SHOP_B, "level": 50, "qty": 100}],
			}
		)["item_code"]
		receive_item(cls.item, cls.warehouse_a, cls.company, 3)
		receive_item(cls.item, cls.warehouse_b, cls.company, 30)

	def tearDown(self):
		frappe.set_user("Administrator")

	def as_user(self, user: str):
		frappe.clear_cache(user=user)
		frappe.set_user(user)

	def stock_by_shop(self, item: dict) -> dict[str, float]:
		return {row["shop"]: row["qty"] for row in item["stock"]}

	# --- search ------------------------------------------------------------

	def test_barcode_scan_finds_the_product_first(self):
		self.as_user(self.manager)
		results = inventory.search_items(self.barcode)
		self.assertEqual(results[0]["item_code"], self.item)
		self.assertIn(self.barcode, results[0]["barcodes"])
		self.assertEqual(results[0]["price"], 4.5)

	def test_search_by_name(self):
		self.as_user(self.manager)
		codes = [row["item_code"] for row in inventory.search_items("ballpoint")]
		self.assertIn(self.item, codes)

	def test_manager_sees_only_own_shop_stock(self):
		self.as_user(self.manager)
		item = inventory.get_item(self.item)
		self.assertEqual(self.stock_by_shop(item), {SHOP_A: 3})

	def test_owner_sees_stock_in_every_shop(self):
		self.as_user(self.owner)
		stock = self.stock_by_shop(inventory.get_item(self.item))
		self.assertEqual(stock[SHOP_A], 3)
		self.assertEqual(stock[SHOP_B], 30)

	def test_manager_cannot_ask_for_another_shop(self):
		self.as_user(self.manager)
		with self.assertRaises(frappe.PermissionError):
			inventory.search_items(self.barcode, shop=SHOP_B)

	def test_cashier_has_no_access_to_inventory(self):
		self.as_user(self.cashier)
		with self.assertRaises(frappe.PermissionError):
			inventory.search_items(self.barcode)
		with self.assertRaises(frappe.PermissionError):
			inventory.save_item({"item_name": "Sneaky"})

	# --- low stock ---------------------------------------------------------

	def test_low_stock_is_per_shop(self):
		# Shop A: 3 in stock, reorder at 5 -> low. Shop B: 30, reorder at 50 -> low too.
		self.as_user(self.manager)
		low = {row["item_code"]: row for row in inventory.get_low_stock()}
		self.assertIn(self.item, low)
		self.assertEqual([row["shop"] for row in low[self.item]["stock"]], [SHOP_A])

		self.as_user(self.owner)
		rows = {row["item_code"]: row for row in inventory.get_low_stock(shop=SHOP_B)}
		self.assertTrue(rows[self.item]["stock"][0]["low"])

	# --- create and edit ---------------------------------------------------

	def test_manager_creates_product_with_barcode_price_and_reorder(self):
		self.as_user(self.manager)
		barcode = unique("612")
		item = inventory.save_item(
			{
				"item_name": "A4 paper ream",
				"barcodes": [barcode, f" {barcode} "],
				"price": 39,
				"reorder": [{"shop": SHOP_A, "level": 10}],
			}
		)
		self.assertEqual(item["item_code"], barcode)
		self.assertEqual(item["barcodes"], [barcode])
		self.assertEqual(item["price"], 39)
		self.assertEqual(item["stock"][0]["reorder_level"], 10)
		self.assertEqual(item["stock"][0]["reorder_qty"], 10)

	def test_duplicate_barcode_is_rejected(self):
		self.as_user(self.manager)
		with self.assertRaises(frappe.ValidationError):
			inventory.save_item({"item_name": "Copycat pen", "barcodes": [self.barcode]})

	def test_manager_cannot_set_reorder_for_another_shop(self):
		self.as_user(self.manager)
		with self.assertRaises(frappe.PermissionError):
			inventory.save_item(
				{"item_code": self.item, "item_name": "Blue ballpoint pen", "reorder": [{"shop": SHOP_B, "level": 1}]}
			)

	def test_manager_edit_keeps_other_shops_reorder_rules(self):
		self.as_user(self.manager)
		inventory.save_item(
			{
				"item_code": self.item,
				"item_name": "Blue ballpoint pen",
				"barcodes": [self.barcode],
				"reorder": [{"shop": SHOP_A, "level": 6, "qty": 24}],
			}
		)
		frappe.set_user("Administrator")
		rules = {
			row.warehouse: row.warehouse_reorder_level for row in frappe.get_doc("Item", self.item).reorder_levels
		}
		self.assertEqual(rules[self.warehouse_a], 6)
		self.assertEqual(rules[self.warehouse_b], 50)

	def test_clearing_the_price_removes_it(self):
		self.as_user(self.owner)
		code = inventory.save_item({"item_name": "Eraser", "price": 2})["item_code"]
		self.assertIsNone(inventory.save_item({"item_code": code, "item_name": "Eraser", "price": None})["price"])

	def test_negative_values_are_rejected(self):
		self.as_user(self.owner)
		with self.assertRaises(frappe.ValidationError):
			inventory.save_item({"item_name": "Ruler", "price": -1})
		with self.assertRaises(frappe.ValidationError):
			inventory.save_item({"item_name": "Ruler", "reorder": [{"shop": SHOP_A, "level": -3}]})

	def test_name_is_required(self):
		self.as_user(self.owner)
		with self.assertRaises(frappe.ValidationError):
			inventory.save_item({"item_name": "  "})

	# --- a manager with no shop is blocked from shop-linked documents --------

	def test_manager_without_shop_sees_no_stock_documents(self):
		self.as_user(self.manager_no_shop)
		self.assertEqual(frappe.get_list("Bin", filters={"item_code": self.item}), [])
		self.assertEqual(frappe.get_list("Warehouse"), [])
		bin_name = frappe.db.get_value("Bin", {"item_code": self.item, "warehouse": self.warehouse_a})
		self.assertFalse(frappe.has_permission("Bin", "read", doc=bin_name))
		self.assertEqual(inventory.get_item(self.item)["stock"], [])
