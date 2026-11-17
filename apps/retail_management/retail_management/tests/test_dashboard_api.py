"""Overview dashboard figures: correct totals, per-shop scoping, comparison
with the previous period, and who may see them."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

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

		item = make_item()
		# This week: shop A sells 100 and 50, one return of 20; shop B sells 300.
		sale = make_invoice(cls.company, cls.wh_a, item, 100)
		make_invoice(cls.company, cls.wh_a, item, 50, days_ago=2)
		make_invoice(cls.company, cls.wh_a, item, 20, is_return=True, return_against=sale)
		make_invoice(cls.company, cls.wh_b, item, 300, days_ago=1)
		# Previous week: shop A sold 40.
		make_invoice(cls.company, cls.wh_a, item, 40, days_ago=10)

	def tearDown(self):
		frappe.set_user("Administrator")

	def as_user(self, user: str):
		frappe.clear_cache(user=user)
		frappe.set_user(user)

	def overview(self, user, **kwargs):
		self.as_user(user)
		return dashboard.get_overview(**kwargs)

	def test_owner_sees_both_shops(self):
		data = self.overview(self.owner, shop=None)
		names = {row["name"] for row in data["shops"]}
		self.assertTrue({SHOP_A, SHOP_B} <= names)

	def test_owner_totals_for_one_shop(self):
		data = self.overview(self.owner, shop=SHOP_A)
		kpis = data["kpis"]
		self.assertEqual(kpis["revenue"]["value"], 130)  # 100 + 50 - 20
		self.assertEqual(kpis["sales"]["value"], 2)
		self.assertEqual(kpis["average"]["value"], 75)
		self.assertEqual(kpis["returns"]["value"], 1)
		# Previous 7 days: 40, so revenue grew by 225 %.
		self.assertEqual(kpis["revenue"]["previous"], 40)
		self.assertEqual(kpis["revenue"]["change"], 225.0)

	def test_series_adds_up_and_splits_by_shop(self):
		data = self.overview(self.owner, shop=None)
		self.assertEqual(len(data["series"]), 7)
		self.assertEqual(data["series"][-1]["key"], nowdate())
		shop_b_total = sum(bucket["by_shop"].get(SHOP_B, 0) for bucket in data["series"])
		self.assertEqual(shop_b_total, 300)
		self.assertAlmostEqual(sum(b["total"] for b in data["series"]), data["kpis"]["revenue"]["value"])

	def test_twelve_month_series(self):
		data = self.overview(self.owner, period="12m", shop=SHOP_A)
		self.assertTrue(data["monthly"])
		self.assertEqual(len(data["series"]), 12)

	def test_recent_sales_marks_returns(self):
		data = self.overview(self.owner, shop=SHOP_A)
		self.assertTrue(any(row["is_return"] for row in data["recent"]))
		self.assertTrue(all(row["shop_name"] == SHOP_A for row in data["recent"]))

	def test_manager_only_sees_own_shop(self):
		data = self.overview(self.manager, shop=None)
		self.assertEqual([row["name"] for row in data["shops"]], [SHOP_A])
		self.assertEqual(data["kpis"]["revenue"]["value"], 130)
		self.assertTrue(all(row["shop_name"] == SHOP_A for row in data["recent"]))

	def test_manager_cannot_ask_for_other_shop(self):
		self.as_user(self.manager)
		with self.assertRaises(frappe.PermissionError):
			dashboard.get_overview(shop=SHOP_B)

	def test_manager_without_shop_gets_nothing(self):
		data = self.overview(self.manager_no_shop, shop=None)
		self.assertEqual(data["shops"], [])
		self.assertEqual(data["kpis"], {})

	def test_cashier_refused(self):
		self.as_user(self.cashier)
		with self.assertRaises(frappe.PermissionError):
			dashboard.get_overview()

	def test_unknown_period_refused(self):
		self.as_user(self.owner)
		with self.assertRaises(frappe.ValidationError):
			dashboard.get_overview(period="5y")
