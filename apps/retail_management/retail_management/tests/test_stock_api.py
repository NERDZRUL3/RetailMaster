"""Inventory: stock on hand with value, movements, transfers between shops and
stock counts, each limited to the user's shops."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from retail_management.api import stock
from retail_management.setup import (
	ROLE_CASHIER,
	ROLE_MANAGER,
	ROLE_OWNER,
	ROLE_PARTNER,
	ensure_erpnext_permissions,
	ensure_roles,
)
from retail_management.tests.test_inventory_api import grant
from retail_management.tests.test_shop_permissions import make_user
from retail_management.tests.test_shop_stock_scoping import (
	BUSINESS,
	SHOP_A,
	SHOP_B,
	get_company,
	make_shop,
	receive_item,
)

ITEM = "_RM-STOCK-RULER"


class TestStockApi(IntegrationTestCase):
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
		cls.wh_a = frappe.db.get_value("Retail Shop", SHOP_A, "warehouse")
		cls.wh_b = frappe.db.get_value("Retail Shop", SHOP_B, "warehouse")
		cls.owner = make_user("rm_stock_owner@example.com", ROLE_OWNER)
		cls.partner = make_user("rm_stock_partner@example.com", ROLE_PARTNER)
		cls.manager = make_user("rm_stock_manager@example.com", ROLE_MANAGER)
		cls.cashier = make_user("rm_stock_cashier@example.com", ROLE_CASHIER)
		grant(cls.manager, SHOP_A)
		grant(cls.cashier, SHOP_A)
		if not frappe.db.exists("Item", ITEM):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": ITEM,
					"item_name": "Stock test ruler",
					"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
					"stock_uom": "Nos",
					"is_stock_item": 1,
				}
			).insert(ignore_permissions=True)
		receive_item(ITEM, cls.wh_a, cls.company, 40)
		receive_item(ITEM, cls.wh_b, cls.company, 10)

	def tearDown(self):
		frappe.set_user("Administrator")

	def as_user(self, user: str):
		frappe.clear_cache(user=user)
		frappe.set_user(user)

	def qty(self, warehouse: str) -> float:
		return flt(frappe.db.get_value("Bin", {"item_code": ITEM, "warehouse": warehouse}, "actual_qty"))

	def test_stock_list_with_value_and_scope(self):
		self.as_user(self.owner)
		rows = [row for row in stock.get_stock(query=ITEM)["rows"] if row["item_code"] == ITEM]
		self.assertEqual({row["shop"] for row in rows}, {SHOP_A, SHOP_B})
		row_a = next(row for row in rows if row["shop"] == SHOP_A)
		self.assertEqual(row_a["qty"], self.qty(self.wh_a))
		self.assertGreater(row_a["value"], 0)  # received at a cost of 5
		self.as_user(self.manager)
		rows = stock.get_stock(query=ITEM)["rows"]
		self.assertEqual({row["shop"] for row in rows}, {SHOP_A})
		self.as_user(self.cashier)
		with self.assertRaises(frappe.PermissionError):
			stock.get_stock()

	def test_transfer_between_shops(self):
		before_a, before_b = self.qty(self.wh_a), self.qty(self.wh_b)
		self.as_user(self.owner)
		request = frappe.generate_hash(length=10)
		first = stock.transfer_stock(SHOP_A, SHOP_B, [{"item_code": ITEM, "qty": 3}], "T-1", request)
		second = stock.transfer_stock(SHOP_A, SHOP_B, [{"item_code": ITEM, "qty": 3}], "T-1", request)
		self.assertEqual(first["name"], second["name"])
		self.assertEqual((first["from_shop"], first["to_shop"], first["qty"]), (SHOP_A, SHOP_B, 3))
		self.assertEqual(self.qty(self.wh_a), before_a - 3)
		self.assertEqual(self.qty(self.wh_b), before_b + 3)
		moves = stock.get_movements(item_code=ITEM, kind="transfer")["rows"]
		self.assertTrue(any(m["voucher_no"] == first["name"] and m["qty"] == -3 for m in moves))
		self.assertIn(first["name"], [t["name"] for t in stock.get_transfers()])
		with self.assertRaises(frappe.ValidationError):
			stock.transfer_stock(SHOP_A, SHOP_A, [{"item_code": ITEM, "qty": 1}])

	def test_manager_cannot_transfer_to_other_shop(self):
		self.as_user(self.manager)
		with self.assertRaises(frappe.PermissionError):
			stock.transfer_stock(SHOP_A, SHOP_B, [{"item_code": ITEM, "qty": 1}])
		self.as_user(self.partner)
		with self.assertRaises(frappe.PermissionError):
			stock.transfer_stock(SHOP_A, SHOP_B, [{"item_code": ITEM, "qty": 1}])

	def test_stock_count(self):
		self.as_user(self.manager)
		before = self.qty(self.wh_a)
		unchanged = stock.submit_count(SHOP_A, [{"item_code": ITEM, "qty": before}])
		self.assertIsNone(unchanged["name"])
		self.assertEqual(unchanged["unchanged"], 1)
		count = stock.submit_count(SHOP_A, [{"item_code": ITEM, "qty": before - 2}], "Shelf A")
		self.assertEqual(self.qty(self.wh_a), before - 2)
		self.assertEqual(count["lines"][0]["difference"], -2)
		self.assertEqual(count["shop_name"], SHOP_A)
		self.assertIn(count["name"], [c["name"] for c in stock.get_counts()])
		moves = stock.get_movements(item_code=ITEM, kind="count")["rows"]
		self.assertEqual(next(m for m in moves if m["voucher_no"] == count["name"])["qty"], -2)
		with self.assertRaises(frappe.PermissionError):
			stock.submit_count(SHOP_B, [{"item_code": ITEM, "qty": 1}])
