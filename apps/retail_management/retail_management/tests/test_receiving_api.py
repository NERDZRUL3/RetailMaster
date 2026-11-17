"""Receiving stock: stock goes up in the right shop only, once per delivery,
and only for owners and managers of that shop."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from retail_management.api import receiving
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
	make_item,
	make_shop,
)


class TestReceivingApi(IntegrationTestCase):
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

		cls.owner = make_user("rm_recv_owner@example.com", ROLE_OWNER)
		cls.partner = make_user("rm_recv_partner@example.com", ROLE_PARTNER)
		cls.manager = make_user("rm_recv_manager@example.com", ROLE_MANAGER)
		cls.cashier = make_user("rm_recv_cashier@example.com", ROLE_CASHIER)
		grant(cls.manager, SHOP_A)
		grant(cls.cashier, SHOP_A)
		cls.item = make_item()

	def tearDown(self):
		frappe.set_user("Administrator")

	def as_user(self, user: str):
		frappe.clear_cache(user=user)
		frappe.set_user(user)

	def stock(self, warehouse: str) -> float:
		return flt(frappe.db.get_value("Bin", {"item_code": self.item, "warehouse": warehouse}, "actual_qty"))

	def test_owner_receives_into_shop(self):
		before_a, before_b = self.stock(self.wh_a), self.stock(self.wh_b)
		self.as_user(self.owner)
		receipt = receiving.receive_stock(SHOP_A, [{"item_code": self.item, "qty": 12, "rate": 2.5}], reference="DN-1")
		frappe.set_user("Administrator")
		self.assertEqual(receipt["qty"], 12)
		self.assertEqual(receipt["shop_name"], SHOP_A)
		self.assertEqual(receipt["value"], 30)
		self.assertEqual(self.stock(self.wh_a), before_a + 12)
		self.assertEqual(self.stock(self.wh_b), before_b)
		entry = frappe.get_doc("Stock Entry", receipt["name"])
		self.assertEqual((entry.docstatus, entry.purpose, entry.to_warehouse), (1, "Material Receipt", self.wh_a))

	def test_same_request_is_received_once(self):
		self.as_user(self.owner)
		before = self.stock(self.wh_a)
		request = frappe.generate_hash(length=12)
		first = receiving.receive_stock(SHOP_A, [{"item_code": self.item, "qty": 5}], request_id=request)
		second = receiving.receive_stock(SHOP_A, [{"item_code": self.item, "qty": 5}], request_id=request)
		self.assertEqual(first["name"], second["name"])
		self.assertEqual(self.stock(self.wh_a), before + 5)

	def test_bad_lines_refused(self):
		self.as_user(self.owner)
		with self.assertRaises(frappe.ValidationError):
			receiving.receive_stock(SHOP_A, [])
		with self.assertRaises(frappe.ValidationError):
			receiving.receive_stock(SHOP_A, [{"item_code": self.item, "qty": 0}])
		with self.assertRaises(frappe.DoesNotExistError):
			receiving.receive_stock(SHOP_A, [{"item_code": "_RM-NO-SUCH-ITEM", "qty": 1}])

	def test_manager_receives_only_into_own_shop(self):
		self.as_user(self.manager)
		receipt = receiving.receive_stock(SHOP_A, [{"item_code": self.item, "qty": 1}])
		self.assertEqual(receipt["shop_name"], SHOP_A)
		with self.assertRaises(frappe.PermissionError):
			receiving.receive_stock(SHOP_B, [{"item_code": self.item, "qty": 1}])
		receipts = receiving.get_receipts()
		self.assertTrue(receipts)
		self.assertTrue(all(row["shop_name"] == SHOP_A for row in receipts))

	def test_cashier_and_partner_cannot_receive(self):
		for user in (self.cashier, self.partner):
			self.as_user(user)
			with self.assertRaises(frappe.PermissionError):
				receiving.receive_stock(SHOP_A, [{"item_code": self.item, "qty": 1}])
