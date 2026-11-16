"""Staff of one shop must not see another shop's stock in ERPNext.

Uses real ERPNext stock documents (Material Receipts) in each shop's
warehouse. Shop scoping is enforced by User Permissions that
services/shop_access.py derives from Retail Shop Access.
"""

import frappe
from frappe.tests import IntegrationTestCase

from retail_management.services.shop_access import sync_user_permissions
from retail_management.setup import ROLE_CASHIER, ROLE_OWNER, ensure_roles
from retail_management.tests.test_shop_permissions import BUSINESS, get_company, make_user

SHOP_A = "_RM Stock Shop A"
SHOP_B = "_RM Stock Shop B"
ITEM = "_RM-TEST-PEN"
# ERPNext's own role that can read stock documents. Retail Cashier gets no
# ERPNext permissions yet (that comes with the POS milestone), so the test
# gives it explicitly to prove the shop restriction holds once it does.
STOCK_ROLE = "Stock User"


def make_shop(name: str, company: str) -> str:
	if not frappe.db.exists("Retail Shop", name):
		frappe.get_doc(
			{"doctype": "Retail Shop", "shop_name": name, "retail_business": BUSINESS, "company": company}
		).insert(ignore_permissions=True)
	return name


def make_item() -> str:
	if not frappe.db.exists("Item", ITEM):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": ITEM,
				"item_name": "Test pen",
				"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
				"stock_uom": "Nos",
				"is_stock_item": 1,
			}
		).insert(ignore_permissions=True)
	return ITEM


def receive_item(item_code: str, warehouse: str, company: str, qty: int) -> str:
	entry = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Receipt",
			"company": company,
			# List filtering uses the parent's warehouse field (as the ERPNext
			# form fills it); single-document checks also look at item rows.
			"to_warehouse": warehouse,
			"items": [{"item_code": item_code, "qty": qty, "t_warehouse": warehouse, "basic_rate": 5}],
		}
	)
	entry.insert(ignore_permissions=True)
	entry.submit()
	return entry.name


def receive(warehouse: str, company: str, qty: int) -> str:
	return receive_item(ITEM, warehouse, company, qty)


class TestShopStockScoping(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_roles()
		cls.company = get_company()
		if not frappe.db.exists("Retail Business", BUSINESS):
			frappe.get_doc({"doctype": "Retail Business", "business_name": BUSINESS}).insert(
				ignore_permissions=True
			)
		make_shop(SHOP_A, cls.company)
		make_shop(SHOP_B, cls.company)
		cls.warehouse_a = frappe.db.get_value("Retail Shop", SHOP_A, "warehouse")
		cls.warehouse_b = frappe.db.get_value("Retail Shop", SHOP_B, "warehouse")

		make_item()
		cls.entry_a = receive(cls.warehouse_a, cls.company, 10)
		cls.entry_b = receive(cls.warehouse_b, cls.company, 20)

		cls.cashier = make_user("rm_stock_cashier@example.com", ROLE_CASHIER, STOCK_ROLE)
		cls.owner = make_user("rm_stock_owner@example.com", ROLE_OWNER, STOCK_ROLE)
		cls.bare_cashier = make_user("rm_stock_bare@example.com", ROLE_CASHIER)
		cls.grant(cls.cashier, SHOP_A)

	@classmethod
	def grant(cls, user: str, shop: str):
		if not frappe.db.exists("Retail Shop Access", {"user": user, "retail_shop": shop}):
			frappe.get_doc({"doctype": "Retail Shop Access", "user": user, "retail_shop": shop}).insert(
				ignore_permissions=True
			)

	def tearDown(self):
		frappe.set_user("Administrator")

	def as_user(self, user: str):
		frappe.clear_cache(user=user)
		frappe.set_user(user)

	def user_permissions(self, user: str) -> set[tuple[str, str]]:
		rows = frappe.get_all("User Permission", filters={"user": user}, fields=["allow", "for_value"])
		return {(row.allow, row.for_value) for row in rows}

	# --- shop setup ---------------------------------------------------------

	def test_each_shop_gets_its_own_warehouse_in_its_company(self):
		self.assertTrue(self.warehouse_a and self.warehouse_b)
		self.assertNotEqual(self.warehouse_a, self.warehouse_b)
		self.assertEqual(frappe.db.get_value("Warehouse", self.warehouse_a, "company"), self.company)

	def test_shops_cannot_share_a_warehouse(self):
		shop = frappe.get_doc("Retail Shop", SHOP_B)
		shop.warehouse = self.warehouse_a
		with self.assertRaises(frappe.ValidationError):
			shop.save(ignore_permissions=True)

	# --- user permissions ---------------------------------------------------

	def test_cashier_is_limited_to_own_shop(self):
		self.assertEqual(
			self.user_permissions(self.cashier),
			{("Company", self.company), ("Warehouse", self.warehouse_a)},
		)

	def test_owner_has_no_restrictions(self):
		self.assertEqual(self.user_permissions(self.owner), set())

	def test_user_without_retail_role_is_left_alone(self):
		user = make_user("rm_stock_accountant@example.com")
		if not frappe.db.exists("User Permission", {"user": user, "allow": "Company"}):
			frappe.get_doc(
				{"doctype": "User Permission", "user": user, "allow": "Company", "for_value": self.company}
			).insert(ignore_permissions=True)
		sync_user_permissions(user)
		self.assertEqual(self.user_permissions(user), {("Company", self.company)})

	# --- ERPNext stock documents --------------------------------------------

	def test_cashier_sees_only_own_warehouse(self):
		self.as_user(self.cashier)
		names = set(frappe.get_list("Warehouse", pluck="name"))
		self.assertIn(self.warehouse_a, names)
		self.assertNotIn(self.warehouse_b, names)

	def test_cashier_lists_only_own_stock_entries(self):
		self.as_user(self.cashier)
		names = set(
			frappe.get_list("Stock Entry", filters={"name": ("in", [self.entry_a, self.entry_b])}, pluck="name")
		)
		self.assertEqual(names, {self.entry_a})

	def test_cashier_cannot_open_other_shops_stock_entry(self):
		self.as_user(self.cashier)
		self.assertTrue(frappe.has_permission("Stock Entry", "read", doc=self.entry_a))
		self.assertFalse(frappe.has_permission("Stock Entry", "read", doc=self.entry_b))

	def test_cashier_sees_only_own_stock_balance(self):
		self.as_user(self.cashier)
		warehouses = set(frappe.get_list("Bin", filters={"item_code": ITEM}, pluck="warehouse"))
		self.assertEqual(warehouses, {self.warehouse_a})

	def test_cashier_sees_only_own_stock_ledger(self):
		self.as_user(self.cashier)
		warehouses = set(
			frappe.get_list("Stock Ledger Entry", filters={"item_code": ITEM}, pluck="warehouse")
		)
		self.assertEqual(warehouses, {self.warehouse_a})

	def test_owner_sees_both_shops_stock(self):
		self.as_user(self.owner)
		warehouses = set(frappe.get_list("Bin", filters={"item_code": ITEM}, pluck="warehouse"))
		self.assertEqual(warehouses, {self.warehouse_a, self.warehouse_b})

	def test_cashier_without_erpnext_role_cannot_list_stock_at_all(self):
		self.as_user(self.bare_cashier)
		with self.assertRaises(frappe.PermissionError):
			frappe.get_list("Stock Entry")

	# --- changes follow the access records ----------------------------------

	def test_moving_a_cashier_moves_their_stock_view(self):
		user = make_user("rm_stock_mover@example.com", ROLE_CASHIER, STOCK_ROLE)
		for access in frappe.get_all("Retail Shop Access", filters={"user": user}, pluck="name"):
			frappe.delete_doc("Retail Shop Access", access, ignore_permissions=True)
		self.grant(user, SHOP_A)
		self.assertIn(("Warehouse", self.warehouse_a), self.user_permissions(user))

		access = frappe.get_value("Retail Shop Access", {"user": user, "retail_shop": SHOP_A})
		frappe.delete_doc("Retail Shop Access", access, ignore_permissions=True)
		self.grant(user, SHOP_B)
		self.assertEqual(
			self.user_permissions(user), {("Company", self.company), ("Warehouse", self.warehouse_b)}
		)

		self.as_user(user)
		warehouses = set(frappe.get_list("Bin", filters={"item_code": ITEM}, pluck="warehouse"))
		self.assertEqual(warehouses, {self.warehouse_b})

	def test_promoting_to_owner_lifts_the_restriction(self):
		user = make_user("rm_stock_promoted@example.com", ROLE_CASHIER, STOCK_ROLE)
		frappe.get_doc("User", user).remove_roles(ROLE_OWNER)
		self.grant(user, SHOP_A)
		self.assertTrue(self.user_permissions(user))
		frappe.get_doc("User", user).add_roles(ROLE_OWNER)
		self.assertEqual(self.user_permissions(user), set())
