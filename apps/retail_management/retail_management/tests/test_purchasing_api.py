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

	def invoice(self, lines, order="", shop=SHOP_A, bill_no=None, request_id="") -> dict:
		return purchasing.receive_invoice(
			{
				"supplier": self.supplier,
				"shop": shop,
				"order": order,
				"bill_no": bill_no or f"F-{frappe.generate_hash(length=8)}",
				"bill_date": add_days(nowdate(), -1),
				"lines": lines,
			},
			request_id=request_id,
		)

	def test_invoice_without_order(self):
		self.as_user(self.manager)
		before = self.qty()
		bill_no = f"INV-{frappe.generate_hash(length=8)}"
		request = frappe.generate_hash(length=12)
		first = self.invoice([{"item_code": ITEM, "qty": 5, "rate": 8}], bill_no=bill_no, request_id=request)
		again = self.invoice([{"item_code": ITEM, "qty": 5, "rate": 8}], bill_no=bill_no, request_id=request)
		self.assertEqual(first["receipt"], again["receipt"])  # same request: received once
		self.assertEqual(self.qty(), before + 5)
		self.assertEqual((first["bill_no"], first["total"], first["shop_name"]), (bill_no, 40, SHOP_A))
		frappe.set_user("Administrator")
		receipt = frappe.get_doc("Purchase Receipt", first["receipt"])
		self.assertEqual((receipt.docstatus, receipt.set_warehouse), (1, self.wh_a))
		bill = frappe.get_doc("Purchase Invoice", first["invoice"])
		self.assertEqual((bill.docstatus, bill.bill_no, str(bill.bill_date)), (1, bill_no, add_days(nowdate(), -1)))
		self.assertEqual(bill.items[0].purchase_receipt, receipt.name)
		self.assertTrue(
			frappe.db.exists(
				"Stock Ledger Entry",
				{"voucher_type": "Purchase Receipt", "voucher_no": receipt.name, "warehouse": self.wh_a, "is_cancelled": 0},
			)
		)
		self.as_user(self.manager)
		with self.assertRaises(frappe.ValidationError):  # same supplier invoice entered twice
			self.invoice([{"item_code": ITEM, "qty": 1, "rate": 8}], bill_no=bill_no)
		self.assertIn(first["receipt"], [r["receipt"] for r in purchasing.get_supplier_invoices()])

	def test_invoice_against_order(self):
		self.as_user(self.owner)
		placed = self.order(qty=10, rate=12.5)
		row = placed["lines"][0]["row"]
		before = self.qty()
		with self.assertRaises(frappe.ValidationError):  # more than ordered
			self.invoice([{"row": row, "qty": 11}], order=placed["name"])
		received = self.invoice(
			[{"row": row, "qty": 6}, {"item_code": ITEM, "qty": 2, "rate": 3.3}], order=placed["name"]
		)
		self.assertEqual(received["orders"], [placed["name"]])
		self.assertEqual(received["total"], 6 * 12.5 + 2 * 3.3)
		self.assertEqual(received["outstanding"], 6 * 12.5 + 2 * 3.3)  # not rounded to 82
		self.assertEqual(self.qty(), before + 8)
		order = purchasing.get_order(placed["name"])
		self.assertEqual((order["status"], order["lines"][0]["remaining"]), ("partly_received", 4))
		with self.assertRaises(frappe.ValidationError):  # order of another shop
			self.invoice([{"row": row, "qty": 1}], order=placed["name"], shop=SHOP_B)

	def test_invoice_scoping(self):
		self.as_user(self.manager)
		with self.assertRaises(frappe.PermissionError):
			self.invoice([{"item_code": ITEM, "qty": 1, "rate": 1}], shop=SHOP_B)
		self.as_user(self.owner)
		other = self.invoice([{"item_code": ITEM, "qty": 1, "rate": 1}], shop=SHOP_B)
		self.as_user(self.manager)
		self.assertNotIn(other["receipt"], [r["receipt"] for r in purchasing.get_supplier_invoices()])
		self.as_user(self.partner)
		self.assertIn(other["receipt"], [r["receipt"] for r in purchasing.get_supplier_invoices()])
		with self.assertRaises(frappe.PermissionError):
			self.invoice([{"item_code": ITEM, "qty": 1, "rate": 1}])
		self.as_user(self.cashier)
		with self.assertRaises(frappe.PermissionError):
			self.invoice([{"item_code": ITEM, "qty": 1, "rate": 1}])
		with self.assertRaises(frappe.PermissionError):
			purchasing.get_supplier_invoices()

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
