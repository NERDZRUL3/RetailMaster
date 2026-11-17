"""Till sessions: sales need an open session of the seller, cash in and out
change the expected cash, closing records counted amounts and differences."""

import frappe
from frappe.tests import IntegrationTestCase

from retail_management.api import pos, till
from retail_management.setup import (
	ROLE_CASHIER,
	ROLE_MANAGER,
	ROLE_OWNER,
	ensure_erpnext_permissions,
	ensure_roles,
)
from retail_management.tests.test_inventory_api import grant
from retail_management.tests.test_pos_api import (
	ITEM,
	PRICE,
	close_open_session,
	ensure_session,
	make_pos_item,
)
from retail_management.tests.test_shop_permissions import make_user
from retail_management.tests.test_shop_stock_scoping import BUSINESS, get_company, make_shop, receive_item

SHOP = "_RM Till Shop"


class TestTillApi(IntegrationTestCase):
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
		make_shop(SHOP, cls.company)
		cls.warehouse = frappe.db.get_value("Retail Shop", SHOP, "warehouse")
		cls.owner = make_user("rm_till_owner@example.com", ROLE_OWNER)
		cls.manager = make_user("rm_till_manager@example.com", ROLE_MANAGER)
		cls.cashier = make_user("rm_till_cashier@example.com", ROLE_CASHIER)
		grant(cls.manager, SHOP)
		grant(cls.cashier, SHOP)
		make_pos_item(ITEM, PRICE)
		receive_item(ITEM, cls.warehouse, cls.company, 200)

	def setUp(self):
		close_open_session(SHOP)

	def tearDown(self):
		frappe.set_user("Administrator")

	def as_user(self, user: str):
		frappe.clear_cache(user=user)
		frappe.set_user(user)

	def cash_mode(self) -> str:
		return next(row["mode"] for row in pos.get_till(SHOP)["payments"] if row["cash"])

	def modes(self) -> list[str]:
		return [row["mode"] for row in pos.get_till(SHOP)["payments"]]

	def test_sale_needs_open_session(self):
		self.as_user(self.cashier)
		self.assertIsNone(pos.get_till(SHOP)["session"])
		with self.assertRaises(frappe.ValidationError):
			pos.submit_sale(SHOP, [{"item_code": ITEM, "qty": 1}], [{"mode": self.cash_mode(), "amount": PRICE}])

	def test_full_session(self):
		ensure_session(self.cashier, SHOP, cash=100)
		cash = self.cash_mode()
		pos.submit_sale(SHOP, [{"item_code": ITEM, "qty": 2}], [{"mode": cash, "amount": 20}])  # 15, change 5
		till.add_cash_movement(SHOP, "In", 50, "Change float top-up")
		report = till.add_cash_movement(SHOP, "Out", 30, "Paid the cleaner")
		row = next(r for r in report["rows"] if r["cash"])
		# Blind count: the cashier does not see the expected cash.
		self.assertIsNone(row["expected"])
		self.assertEqual(report["sales_count"], 1)
		self.assertEqual(report["total"], 2 * PRICE)
		with self.assertRaises(frappe.ValidationError):
			till.add_cash_movement(SHOP, "Out", 10_000, "Too much")

		self.as_user(self.manager)
		row = next(r for r in till.get_session(SHOP)["rows"] if r["cash"])
		expected = 100 + 2 * PRICE + 50 - 30
		self.assertEqual(row["expected"], expected)

		self.as_user(self.cashier)
		counts = {mode: 0 for mode in self.modes()}
		counts[cash] = expected - 1  # one short
		preview = till.preview_close(SHOP, counts)
		self.assertEqual(next(r for r in preview["rows"] if r["cash"])["difference"], -1)
		z = till.close_session(SHOP, counts, note="One coin missing")
		self.assertTrue(z["closed"])
		zrow = next(r for r in z["rows"] if r["cash"])
		self.assertEqual((zrow["counted"], zrow["expected"], zrow["difference"]), (expected - 1, expected, -1))
		self.assertEqual(len(z["movements"]), 2)
		self.assertIn("coin", z["note"])
		self.assertIsNone(pos.get_till(SHOP)["session"])
		self.assertEqual(frappe.db.get_value("POS Opening Entry", z["name"], "status"), "Closed")
		self.assertEqual(frappe.db.get_value("POS Closing Entry", z["closing_entry"], "docstatus"), 1)
		# Closed: no more sales; the session shows in the history.
		with self.assertRaises(frappe.ValidationError):
			pos.submit_sale(SHOP, [{"item_code": ITEM, "qty": 1}], [{"mode": cash, "amount": PRICE}])
		history = till.list_sessions(SHOP)
		self.assertEqual(history[0]["name"], z["name"])
		self.assertEqual(history[0]["difference"], -1)
		self.assertEqual(till.get_report(z["name"])["closing_entry"], z["closing_entry"])
		# The next opening suggests the cash left in the drawer.
		self.assertEqual(pos.get_till(SHOP)["last_cash"], expected - 1)

	def test_one_person_per_till(self):
		ensure_session(self.cashier, SHOP, cash=20)
		again = till.open_session(SHOP, 20)
		self.assertTrue(again["mine"])
		self.as_user(self.manager)
		with self.assertRaises(frappe.ValidationError):
			till.open_session(SHOP, 0)
		with self.assertRaises(frappe.ValidationError):
			pos.submit_sale(SHOP, [{"item_code": ITEM, "qty": 1}], [{"mode": self.cash_mode(), "amount": PRICE}])
		# A manager may close the cashier's forgotten session.
		counts = {mode: 0 for mode in self.modes()}
		counts[self.cash_mode()] = 20
		z = till.close_session(SHOP, counts)
		self.assertEqual(sum(r["difference"] for r in z["rows"]), 0)

	def test_cashier_cannot_close_others_or_see_others_reports(self):
		ensure_session(self.manager, SHOP, cash=0)
		name = pos.get_till(SHOP)["session"]["name"]
		self.as_user(self.cashier)
		with self.assertRaises(frappe.PermissionError):
			till.close_session(SHOP, {mode: 0 for mode in self.modes()})
		with self.assertRaises(frappe.PermissionError):
			till.get_report(name)

	def test_counts_required(self):
		ensure_session(self.cashier, SHOP, cash=0)
		with self.assertRaises(frappe.ValidationError):
			till.close_session(SHOP, {})
		self.assertIsNotNone(pos.get_till(SHOP)["session"])
