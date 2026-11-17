"""Dashboard figures: correct totals per widget, per-shop scoping, and who
may see them."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, get_first_day, getdate, nowdate

from retail_management.api import dashboard
from retail_management.setup import (
	ROLE_CASHIER,
	ROLE_MANAGER,
	ROLE_OWNER,
	ensure_erpnext_permissions,
	ensure_roles,
)
from retail_management.tests.test_inventory_api import grant
from retail_management.tests.test_shop_permissions import make_user
from retail_management.tests.test_shop_stock_scoping import BUSINESS, get_company, make_item, make_shop

SHOP_A = "_RM Dash Shop A"
SHOP_B = "_RM Dash Shop B"
CUSTOMER = "_RM Dash Customer"

# (shop, amount, days ago, is return) of the invoices created below
SALES_A = ((100, 0), (50, 2))
RETURN_A = (20, 0)
SALES_B = ((300, 1),)
OLDER_A = (40, 40)  # in the previous 30-day window


def make_customer() -> str:
	if not frappe.db.exists("Customer", CUSTOMER):
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": CUSTOMER,
				"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
				"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
			}
		).insert(ignore_permissions=True)
	return CUSTOMER


def make_invoice(company, warehouse, item, amount, days_ago=0, is_return=False, return_against=None) -> str:
	qty = -1 if is_return else 1
	doc = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"company": company,
			"customer": CUSTOMER,
			"set_posting_time": 1,
			"posting_date": add_days(nowdate(), -days_ago),
			"posting_time": "11:30:00",
			"due_date": add_days(nowdate(), -days_ago),
			"set_warehouse": warehouse,
			"update_stock": 0,
			"is_return": 1 if is_return else 0,
			"return_against": return_against,
			"items": [{"item_code": item, "qty": qty, "rate": amount, "warehouse": warehouse}],
		}
	)
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc.name


class TestDashboardApi(IntegrationTestCase):
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
		make_customer()

		# Start from a clean slate in these two shops.
		for name in frappe.get_all(
			"Sales Invoice", filters={"set_warehouse": ("in", [cls.wh_a, cls.wh_b]), "docstatus": 1}, pluck="name"
		):
			frappe.get_doc("Sales Invoice", name).cancel()
		for name in frappe.get_all("Sales Invoice", filters={"set_warehouse": ("in", [cls.wh_a, cls.wh_b])}, pluck="name"):
			frappe.delete_doc("Sales Invoice", name, force=True, ignore_permissions=True)

		cls.owner = make_user("rm_dash_owner@example.com", ROLE_OWNER)
		cls.manager = make_user("rm_dash_manager@example.com", ROLE_MANAGER)
		cls.manager_no_shop = make_user("rm_dash_manager_none@example.com", ROLE_MANAGER)
		cls.cashier = make_user("rm_dash_cashier@example.com", ROLE_CASHIER)
		grant(cls.manager, SHOP_A)
		grant(cls.cashier, SHOP_A)

		cls.item = make_item()
		first = None
		for amount, days_ago in SALES_A:
			name = make_invoice(cls.company, cls.wh_a, cls.item, amount, days_ago)
			first = first or name
		make_invoice(cls.company, cls.wh_a, cls.item, RETURN_A[0], RETURN_A[1], is_return=True, return_against=first)
		for amount, days_ago in SALES_B:
			make_invoice(cls.company, cls.wh_b, cls.item, amount, days_ago)
		make_invoice(cls.company, cls.wh_a, cls.item, OLDER_A[0], OLDER_A[1])

	def tearDown(self):
		frappe.set_user("Administrator")

	def as_user(self, user: str):
		frappe.clear_cache(user=user)
		frappe.set_user(user)

	def data(self, user, shop=None):
		self.as_user(user)
		return dashboard.get_dashboard(shop=shop)

	def test_sales_count_and_previous_window(self):
		sales = self.data(self.owner, SHOP_A)["sales"]
		self.assertEqual(sales["value"], 2)  # returns are not sales
		self.assertEqual(sales["previous"], 1)
		self.assertEqual(sales["change"], 100.0)
		self.assertEqual(len(sales["series"]), 30)
		self.assertEqual(sales["series"][-1]["date"], nowdate())
		self.assertEqual(sum(point["value"] for point in sales["series"]), 2)

	def test_revenue_is_net_of_returns(self):
		revenue = self.data(self.owner, SHOP_A)["revenue"]
		month_start = getdate(get_first_day(nowdate()))
		expected = sum(a for a, d in SALES_A if getdate(add_days(nowdate(), -d)) >= month_start)
		expected -= RETURN_A[0]
		self.assertEqual(revenue["value"], expected)
		self.assertEqual(len(revenue["week"]), 7)

	def test_orders_income_per_day(self):
		orders = self.data(self.owner, SHOP_A)["orders"]
		self.assertEqual(len(orders), 15)
		self.assertEqual(orders[-1]["date"], nowdate())
		self.assertEqual(sum(day["income"] for day in orders), 130)  # 100 + 50 - 20

	def test_categories_hours_products_recent(self):
		data = self.data(self.owner, SHOP_A)
		self.assertEqual(data["categories"]["monthly"][0]["percent"], 100)
		self.assertEqual(sum(row["percent"] for row in data["hours"]["monthly"]), 100)
		self.assertEqual(data["hours"]["monthly"][1]["label"], "10–12")  # sales at 11:30
		self.assertEqual(data["hours"]["monthly"][1]["percent"], 100)
		self.assertEqual(data["products"][0]["item_code"], self.item)
		product = data["products"][0]
		self.assertEqual(product["sold"], 1)  # two sales, one return (the older sale is outside 30 days)
		self.assertEqual(product["price"], 75)  # average of the sales only: (100 + 50) / 2
		self.assertTrue(any(row["is_return"] for row in data["recent"]))
		self.assertTrue(all(row["shop_name"] == SHOP_A for row in data["recent"]))

	def test_owner_split_by_shop(self):
		split = {row["shop_name"]: row for row in self.data(self.owner)["customers"]["by_shop"]}
		self.assertEqual(split[SHOP_A]["sales"], 2)
		self.assertEqual(split[SHOP_B]["sales"], 1)

	def test_manager_only_sees_own_shop(self):
		data = self.data(self.manager)
		self.assertEqual([row["name"] for row in data["shops"]], [SHOP_A])
		self.assertEqual(data["sales"]["value"], 2)
		self.assertTrue(all(row["shop_name"] == SHOP_A for row in data["recent"]))

	def test_manager_cannot_ask_for_other_shop(self):
		self.as_user(self.manager)
		with self.assertRaises(frappe.PermissionError):
			dashboard.get_dashboard(shop=SHOP_B)

	def test_manager_without_shop_gets_nothing(self):
		data = self.data(self.manager_no_shop)
		self.assertEqual(data["shops"], [])
		self.assertNotIn("sales", data)

	def test_cashier_refused(self):
		self.as_user(self.cashier)
		with self.assertRaises(frappe.PermissionError):
			dashboard.get_dashboard()
