"""Purchasing: suppliers, orders for one shop, deliveries received against
them (stock in at the order's cost), cancel and close, shop scoping."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, nowdate

from retail_management.api import purchasing
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
from retail_management.tests.test_shop_stock_scoping import BUSINESS, SHOP_A, SHOP_B, get_company, make_shop

ITEM = "_RM-PO-STAPLER"


class TestPurchasingApi(IntegrationTestCase):
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
		cls.owner = make_user("rm_po_owner@example.com", ROLE_OWNER)
		cls.partner = make_user("rm_po_partner@example.com", ROLE_PARTNER)
		cls.manager = make_user("rm_po_manager@example.com", ROLE_MANAGER)
		cls.cashier = make_user("rm_po_cashier@example.com", ROLE_CASHIER)
		grant(cls.manager, SHOP_A)
		grant(cls.cashier, SHOP_A)
		if not frappe.db.exists("Item", ITEM):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": ITEM,
					"item_name": "PO test stapler",
					"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
					"stock_uom": "Nos",
					"is_stock_item": 1,
				}
			).insert(ignore_permissions=True)
		frappe.clear_cache(user=cls.owner)
		frappe.set_user(cls.owner)
		existing = frappe.db.get_value("Supplier", {"supplier_name": "_RM Test Supplier"}, "name")
		cls.supplier = existing or purchasing.save_supplier(
			{"supplier_name": "_RM Test Supplier", "phone": "+212600000000", "email": "orders@example.com"}
		)["name"]
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def as_user(self, user: str):
		frappe.clear_cache(user=user)
		frappe.set_user(user)

	def qty(self) -> float:
		return flt(frappe.db.get_value("Bin", {"item_code": ITEM, "warehouse": self.wh_a}, "actual_qty"))

	def order(self, qty=10, rate=12.5, submit=1, shop=SHOP_A) -> dict:
		return purchasing.save_order(
			{
				"supplier": self.supplier,
				"shop": shop,
				"expected": add_days(nowdate(), 3),
				"lines": [{"item_code": ITEM, "qty": qty, "rate": rate}],
				"notes": "Test order",
			},
			submit=submit,
		)

	def test_supplier_contact(self):
		self.as_user(self.owner)
		saved = purchasing.save_supplier(
			{
				"name": self.supplier,
				"supplier_name": "_RM Test Supplier",
				"phone": "+212611111111",
				"email": "new@example.com",
			}
		)
		self.assertEqual((saved["phone"], saved["email"]), ("+212611111111", "new@example.com"))
		self.assertTrue(any(s["name"] == self.supplier for s in purchasing.get_suppliers("_RM Test")))
		with self.assertRaises(frappe.ValidationError):
			purchasing.save_supplier({"supplier_name": "_RM Test Supplier"})  # duplicate

	def test_order_and_receive_in_two_deliveries(self):
		self.as_user(self.manager)
		draft = self.order(submit=0)
		self.assertEqual(draft["status"], "draft")
		placed = purchasing.submit_order(draft["name"])
		self.assertEqual(placed["status"], "ordered")
		row = placed["lines"][0]["row"]
		before = self.qty()
		after_first = purchasing.receive_order(placed["name"], [{"row": row, "qty": 4}], "BL-1")
		self.assertEqual(after_first["status"], "partly_received")
		self.assertEqual(self.qty(), before + 4)
		self.assertEqual(after_first["lines"][0]["remaining"], 6)
		with self.assertRaises(frappe.ValidationError):
			purchasing.receive_order(placed["name"], [{"row": row, "qty": 7}])  # more than ordered
		done = purchasing.receive_order(placed["name"], [{"row": row, "qty": 6}], "BL-2")
		self.assertEqual(done["status"], "received")
		self.assertEqual(len(done["receipts"]), 2)
		self.assertEqual(self.qty(), before + 10)
		self.assertEqual(purchasing.get_item_costs([ITEM], self.supplier)[ITEM], 12.5)
		self.assertIn(placed["name"], [o["name"] for o in purchasing.get_orders(status="received")])

	def test_cancel_close_delete(self):
		self.as_user(self.owner)
		draft = self.order(submit=0)
		purchasing.delete_order(draft["name"])
		self.assertFalse(frappe.db.exists("Purchase Order", draft["name"]))
		placed = self.order()
		self.assertEqual(purchasing.cancel_order(placed["name"])["status"], "cancelled")
		partly = self.order()
		purchasing.receive_order(partly["name"], [{"row": partly["lines"][0]["row"], "qty": 1}])
		with self.assertRaises(frappe.ValidationError):
			purchasing.cancel_order(partly["name"])
		self.assertEqual(purchasing.close_order(partly["name"])["status"], "closed")
		with self.assertRaises(frappe.ValidationError):
			purchasing.receive_order(partly["name"], [{"row": partly["lines"][0]["row"], "qty": 1}])

	def test_scoping(self):
		self.as_user(self.manager)
		with self.assertRaises(frappe.PermissionError):
			self.order(shop=SHOP_B)
		self.as_user(self.owner)
		other = self.order(shop=SHOP_B)
		self.as_user(self.manager)
		self.assertNotIn(other["name"], [o["name"] for o in purchasing.get_orders()])
		self.as_user(self.partner)
		self.assertIn(other["name"], [o["name"] for o in purchasing.get_orders()])
		with self.assertRaises(frappe.PermissionError):
			self.order()
		self.as_user(self.cashier)
		with self.assertRaises(frappe.PermissionError):
			purchasing.get_orders()
		with self.assertRaises(frappe.PermissionError):
			purchasing.get_suppliers()
