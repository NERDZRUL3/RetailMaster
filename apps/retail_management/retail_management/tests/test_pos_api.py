"""Point of sale: a sale takes stock out of the right shop once, prices come
from ERPNext, payment must cover the total, and staff sell only in their shops."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from retail_management.api import pos
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

ITEM = "_RM-POS-PEN"
BARCODE = "2999000000017"
NO_PRICE_ITEM = "_RM-POS-NOPRICE"
PRICE = 7.5


def make_pos_item(code: str, price: float | None, barcode: str | None = None) -> str:
	if not frappe.db.exists("Item", code):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": f"POS test {code}",
				"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
				"stock_uom": "Nos",
				"is_stock_item": 1,
				"barcodes": [{"barcode": barcode}] if barcode else [],
			}
		).insert(ignore_permissions=True)
	price_list = frappe.db.get_single_value("Selling Settings", "selling_price_list") or "Standard Selling"
	if price is not None and not frappe.db.exists("Item Price", {"item_code": code, "price_list": price_list}):
		frappe.get_doc(
			{"doctype": "Item Price", "item_code": code, "price_list": price_list, "price_list_rate": price}
		).insert(ignore_permissions=True)
	return code


def close_open_session(shop: str):
	"""Close whatever session is open on the shop's till (as Administrator)."""
	from retail_management.api import till

	frappe.set_user("Administrator")
	profile = frappe.db.get_value("Retail Shop", shop, "pos_profile")
	info = till.session_info(profile) if profile else None
	if info:
		entry = frappe.get_doc("POS Opening Entry", info["name"])
		till.close_session(shop, {row.mode_of_payment: 0 for row in entry.balance_details})


def ensure_session(user: str, shop: str, cash: float = 0) -> dict:
	"""Open the shop's till as user, closing other open sessions of the till
	and of the user first. Leaves the user signed in."""
	from retail_management.api import till

	frappe.set_user("Administrator")
	pos.ensure_shop_pos_profile(shop)
	profile = frappe.db.get_value("Retail Shop", shop, "pos_profile")
	info = till.session_info(profile)
	if info and (info["user"] != user or info["outdated"]):
		close_open_session(shop)
	other = frappe.db.get_value(
		"POS Opening Entry", {"user": user, "status": "Open", "docstatus": 1, "pos_profile": ("!=", profile)}, "pos_profile"
	)
	if other:
		close_open_session(frappe.db.get_value("Retail Shop", {"pos_profile": other}, "name"))
	frappe.clear_cache(user=user)
	frappe.set_user(user)
	return till.open_session(shop, cash)


class TestPosApi(IntegrationTestCase):
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

		cls.owner = make_user("rm_pos_owner@example.com", ROLE_OWNER)
		cls.partner = make_user("rm_pos_partner@example.com", ROLE_PARTNER)
		cls.manager = make_user("rm_pos_manager@example.com", ROLE_MANAGER)
		cls.cashier = make_user("rm_pos_cashier@example.com", ROLE_CASHIER)
		grant(cls.manager, SHOP_A)
		grant(cls.cashier, SHOP_A)
		make_pos_item(ITEM, PRICE, BARCODE)
		make_pos_item(NO_PRICE_ITEM, None)
		for warehouse in (cls.wh_a, cls.wh_b):
			receive_item(ITEM, warehouse, cls.company, 100)
			receive_item(NO_PRICE_ITEM, warehouse, cls.company, 10)
		# Selling needs the seller's open till session.
		ensure_session(cls.cashier, SHOP_A)
		ensure_session(cls.owner, SHOP_B)
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def as_user(self, user: str):
		frappe.clear_cache(user=user)
		frappe.set_user(user)

	def stock(self, warehouse: str) -> float:
		return flt(frappe.db.get_value("Bin", {"item_code": ITEM, "warehouse": warehouse}, "actual_qty"))

	def cash(self) -> str:
		return next(row["mode"] for row in pos.get_till(SHOP_A)["payments"] if row["cash"])

	def test_cashier_sells_with_change(self):
		before_a, before_b = self.stock(self.wh_a), self.stock(self.wh_b)
		self.as_user(self.cashier)
		till = pos.get_till(SHOP_A)
		self.assertTrue(till["payments"])
		sale = pos.submit_sale(SHOP_A, [{"item_code": ITEM, "qty": 2}], [{"mode": self.cash(), "amount": 20}])
		frappe.set_user("Administrator")
		self.assertEqual(sale["total"], 2 * PRICE)
		self.assertEqual(sale["change"], 20 - 2 * PRICE)
		self.assertEqual(sale["shop_name"], SHOP_A)
		self.assertEqual(self.stock(self.wh_a), before_a - 2)
		self.assertEqual(self.stock(self.wh_b), before_b)
		invoice = frappe.get_doc("Sales Invoice", sale["name"])
		self.assertEqual((invoice.docstatus, invoice.is_pos, invoice.update_stock), (1, 1, 1))
		self.assertEqual(invoice.set_warehouse, self.wh_a)

	def test_price_comes_from_erpnext(self):
		self.as_user(self.cashier)
		sale = pos.submit_sale(
			SHOP_A, [{"item_code": ITEM, "qty": 1, "rate": 0.01}], [{"mode": self.cash(), "amount": PRICE}]
		)
		self.assertEqual(sale["total"], PRICE)

	def test_same_request_is_sold_once(self):
		self.as_user(self.cashier)
		before = self.stock(self.wh_a)
		request = frappe.generate_hash(length=12)
		payment = [{"mode": self.cash(), "amount": PRICE}]
		first = pos.submit_sale(SHOP_A, [{"item_code": ITEM, "qty": 1}], payment, request_id=request)
		second = pos.submit_sale(SHOP_A, [{"item_code": ITEM, "qty": 1}], payment, request_id=request)
		self.assertEqual(first["name"], second["name"])
		self.assertEqual(self.stock(self.wh_a), before - 1)

	def test_bad_sales_refused(self):
		self.as_user(self.cashier)
		cash = self.cash()
		with self.assertRaises(frappe.ValidationError):
			pos.submit_sale(SHOP_A, [{"item_code": ITEM, "qty": 2}], [{"mode": cash, "amount": PRICE}])
		with self.assertRaises(frappe.ValidationError):
			pos.submit_sale(SHOP_A, [], [{"mode": cash, "amount": 10}])
		with self.assertRaises(frappe.ValidationError):
			pos.submit_sale(SHOP_A, [{"item_code": NO_PRICE_ITEM, "qty": 1}], [{"mode": cash, "amount": 10}])
		with self.assertRaises(frappe.ValidationError):
			pos.submit_sale(SHOP_A, [{"item_code": ITEM, "qty": 1}], [{"mode": "_No such method", "amount": 10}])

	def test_find_by_barcode(self):
		self.as_user(self.cashier)
		found = pos.find_products(SHOP_A, BARCODE)
		self.assertEqual(found[0]["item_code"], ITEM)
		self.assertEqual(found[0]["price"], PRICE)
		self.assertEqual(found[0]["stock"], self.stock(self.wh_a))

	def test_staff_sell_only_in_own_shop(self):
		for user in (self.cashier, self.manager):
			self.as_user(user)
			with self.assertRaises(frappe.PermissionError):
				pos.submit_sale(SHOP_B, [{"item_code": ITEM, "qty": 1}], [{"mode": "Cash", "amount": 10}])
			with self.assertRaises(frappe.PermissionError):
				pos.find_products(SHOP_B)
		self.as_user(self.partner)
		with self.assertRaises(frappe.PermissionError):
			pos.get_till(SHOP_A)

	def test_owner_sells_anywhere_and_reprints(self):
		self.as_user(self.owner)
		cash = next(row["mode"] for row in pos.get_till(SHOP_B)["payments"] if row["cash"])
		sale = pos.submit_sale(SHOP_B, [{"item_code": ITEM, "qty": 1}], [{"mode": cash, "amount": PRICE}])
		self.assertEqual(pos.get_sale(sale["name"])["total"], PRICE)
		self.assertIn(sale["name"], [row["name"] for row in pos.get_sales(SHOP_B)])
		# A cashier of shop A cannot read shop B's receipt.
		self.as_user(self.cashier)
		with self.assertRaises(frappe.PermissionError):
			pos.get_sale(sale["name"])
