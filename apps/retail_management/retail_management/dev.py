"""Development helpers. Never run these on a production site."""

import frappe
from frappe.utils.password import update_password

from retail_management.setup import ROLE_CASHIER, ROLE_MANAGER, ROLE_OWNER, ROLE_PARTNER, ensure_roles

DEMO_BUSINESS = "Demo Business"
DEMO_SHOPS = ("Demo Shop 1", "Demo Shop 2")

# Password tiers, one per role. Both demo cashiers share the cashier password.
TIERS = ("owner", "partner", "manager", "cashier")

# email, first name, role, password tier, assigned shop (None = all shops through the role)
DEMO_USERS = (
	("demo.owner@example.com", "Demo Owner", ROLE_OWNER, "owner", None),
	("demo.partner@example.com", "Demo Partner", ROLE_PARTNER, "partner", None),
	("demo.manager1@example.com", "Demo Manager 1", ROLE_MANAGER, "manager", DEMO_SHOPS[0]),
	("demo.cashier1@example.com", "Demo Cashier 1", ROLE_CASHIER, "cashier", DEMO_SHOPS[0]),
	("demo.cashier2@example.com", "Demo Cashier 2", ROLE_CASHIER, "cashier", DEMO_SHOPS[1]),
)


def _tier_passwords(passwords, password) -> dict[str, str]:
	"""One password per tier: from `passwords` ({"owner": ..., ...}), else the
	single `password` for every tier."""
	if passwords:
		result = frappe.parse_json(passwords)
	elif password:
		result = {tier: password for tier in TIERS}
	else:
		frappe.throw("Give passwords for the tiers: " + ", ".join(TIERS))
	missing = [tier for tier in TIERS if not result.get(tier)]
	if missing:
		frappe.throw("Missing demo password for: " + ", ".join(missing))
	short = [tier for tier in TIERS if len(result[tier]) < 8]
	if short:
		frappe.throw("Demo passwords must be at least 8 characters: " + ", ".join(short))
	return result


def seed_demo(passwords: dict | str | None = None, password: str | None = None):
	"""Create synthetic shops and users for trying the interface locally.

	Use infrastructure/docker/seed-demo.sh, which reads the per-tier passwords
	from .env. Directly:

	bench --site <site> execute retail_management.dev.seed_demo \
		--kwargs '{"passwords": {"owner": "...", "partner": "...", "manager": "...", "cashier": "..."}}'

	Safe to run repeatedly; resets the demo users' passwords. Refuses to run
	unless the site allows tests.
	"""
	if not frappe.conf.allow_tests:
		frappe.throw("seed_demo only runs on a site with allow_tests enabled.")
	tier_passwords = _tier_passwords(passwords, password)

	ensure_roles()
	company = frappe.db.get_value("Company", {}, "name")
	if not company:
		frappe.throw("No company yet. Complete the ERPNext setup wizard or run the tests once.")

	if not frappe.db.exists("Retail Business", DEMO_BUSINESS):
		frappe.get_doc({"doctype": "Retail Business", "business_name": DEMO_BUSINESS}).insert()

	for shop in DEMO_SHOPS:
		if not frappe.db.exists("Retail Shop", shop):
			frappe.get_doc(
				{
					"doctype": "Retail Shop",
					"shop_name": shop,
					"retail_business": DEMO_BUSINESS,
					"company": company,
				}
			).insert()

	for email, first_name, role, tier, shop in DEMO_USERS:
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{"doctype": "User", "email": email, "first_name": first_name, "send_welcome_email": 0}
			).insert()
		frappe.get_doc("User", email).add_roles(role)
		update_password(email, tier_passwords[tier])

		if shop and not frappe.db.exists("Retail Shop Access", {"user": email, "retail_shop": shop}):
			frappe.get_doc({"doctype": "Retail Shop Access", "user": email, "retail_shop": shop}).insert()

	_seed_demo_products(company)
	_seed_demo_sales(company)
	_backfill_demo_sales(company)
	_assign_demo_categories()
	_spread_demo_sale_times()

	frappe.db.commit()  # nosemgrep: one-off dev seed run from the command line
	return [user[0] for user in DEMO_USERS]


# barcode, name, price, (stock shop 1, stock shop 2), reorder level per shop
DEMO_PRODUCTS = (
	("2000000000011", "Demo ballpoint pen, blue", 4.0, (120, 8), 20),
	("2000000000028", "Demo A4 paper ream", 45.0, (30, 40), 10),
	("2000000000035", "Demo spiral notebook", 12.5, (4, 60), 15),
)


def _seed_demo_products(company: str):
	"""A few synthetic products with stock in both demo shops (once only)."""
	from retail_management.api.inventory import save_item

	warehouses = [frappe.db.get_value("Retail Shop", shop, "warehouse") for shop in DEMO_SHOPS]
	for barcode, name, price, quantities, level in DEMO_PRODUCTS:
		if frappe.db.exists("Item", barcode):
			continue
		save_item(
			{
				"item_name": name,
				"barcodes": [barcode],
				"price": price,
				"reorder": [{"shop": shop, "level": level, "qty": level * 3} for shop in DEMO_SHOPS],
			}
		)
		for warehouse, qty in zip(warehouses, quantities):
			entry = frappe.get_doc(
				{
					"doctype": "Stock Entry",
					"stock_entry_type": "Material Receipt",
					"company": company,
					"to_warehouse": warehouse,
					"items": [{"item_code": barcode, "qty": qty, "t_warehouse": warehouse, "basic_rate": price / 2}],
				}
			)
			entry.insert()
			entry.submit()


DEMO_SALE_REMARK = "Demo sale (synthetic data from retail_management.dev.seed_demo)"
DEMO_CUSTOMERS = ("Demo Walk-in Customer", "Demo Customer Amal", "Demo Customer Youssef", "Demo Customer Sara")


def _demo_customer(name: str) -> str:
	if not frappe.db.exists("Customer", name):
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": name,
				"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
				"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
			}
		).insert(ignore_permissions=True)
	return name


def _ensure_fiscal_years(first_year: int):
	"""Calendar fiscal years back to first_year, so older demo sales can be
	posted. Copies the shape (start month and day) of the existing year."""
	import datetime

	current = frappe.get_all("Fiscal Year", fields=["year_start_date"], order_by="year_start_date asc", limit=1)
	if not current:
		return
	start = current[0].year_start_date
	for year in range(first_year, start.year):
		begin = datetime.date(year, start.month, start.day)
		if frappe.db.exists("Fiscal Year", {"year_start_date": begin}):
			continue
		frappe.get_doc(
			{
				"doctype": "Fiscal Year",
				"year": str(year) if start.month == 1 else f"{year}-{year + 1}",
				"year_start_date": begin,
				"year_end_date": datetime.date(year + 1, start.month, start.day) - datetime.timedelta(days=1),
			}
		).insert(ignore_permissions=True)


def _seed_demo_sales(company: str):
	"""About 13 months of synthetic sales in both demo shops (once only), so the
	overview dashboard has figures to show. Stock is not touched (update_stock=0)."""
	import random

	from frappe.utils import add_days, nowdate

	if frappe.db.exists("Sales Invoice", {"remarks": DEMO_SALE_REMARK}):
		return
	_ensure_fiscal_years(frappe.utils.getdate(add_days(nowdate(), -400)).year)
	customers = [_demo_customer(name) for name in DEMO_CUSTOMERS]
	products = [(barcode, price) for barcode, _name, price, _qty, _level in DEMO_PRODUCTS]
	warehouses = [frappe.db.get_value("Retail Shop", shop, "warehouse") for shop in DEMO_SHOPS]
	rng = random.Random(20261117)  # same demo data on every site

	def sell(warehouse: str, days_ago: int, scale: float, is_return: bool = False, against: str | None = None):
		# A return must name the same customer as the sale it reverses.
		customer = frappe.db.get_value("Sales Invoice", against, "customer") if against else rng.choice(customers)
		date = add_days(nowdate(), -days_ago)
		items = rng.sample(products, rng.randint(1, len(products)))
		sign = -1 if is_return else 1
		doc = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": company,
				"customer": customer,
				"set_posting_time": 1,
				"posting_date": date,
				"due_date": date,
				"set_warehouse": warehouse,
				"update_stock": 0,
				"is_return": int(is_return),
				"return_against": against,
				"remarks": DEMO_SALE_REMARK,
				"items": [
					{
						"item_code": code,
						"qty": sign * max(1, round(rng.randint(1, 12) * scale)),
						"rate": price,
						"warehouse": warehouse,
					}
					for code, price in items
				],
			}
		)
		doc.insert(ignore_permissions=True)
		doc.submit()
		return doc.name

	for shop_index, warehouse in enumerate(warehouses):
		shop_scale = 1.0 if shop_index == 0 else 0.7
		for days_ago in range(400, -1, -1):
			recent = days_ago < 35
			if not recent and days_ago % 4:
				continue  # older months: one bigger sale every 4 days
			weekday = frappe.utils.getdate(add_days(nowdate(), -days_ago)).weekday()
			busy = 1.4 if weekday in (4, 5) else 1.0  # Friday and Saturday
			count = rng.randint(1, 3) if recent else 1
			scale = shop_scale * busy * (1.0 if recent else 3.0)
			for _ in range(count):
				name = sell(warehouse, days_ago, scale)
				if recent and rng.random() < 0.05:
					sell(warehouse, days_ago, 0.3, is_return=True, against=name)


# Busy hours of a stationery shop: (hour, weight)
DEMO_HOURS = ((9, 3), (10, 6), (11, 7), (12, 4), (13, 2), (14, 3), (15, 5), (16, 6), (17, 6), (18, 4), (19, 2))


def _spread_demo_sale_times():
	"""Give demo sales realistic times of day (derived from the receipt name,
	so running this again changes nothing). Only touches demo sales."""
	import hashlib

	weights = [hour for hour, weight in DEMO_HOURS for _ in range(weight)]
	for name in frappe.get_all("Sales Invoice", filters={"remarks": DEMO_SALE_REMARK}, pluck="name"):
		digest = int(hashlib.sha256(name.encode()).hexdigest(), 16)
		hour = weights[digest % len(weights)]
		minute = (digest // 97) % 60
		frappe.db.set_value(
			"Sales Invoice", name, "posting_time", f"{hour:02d}:{minute:02d}:00", update_modified=False
		)


# Demo product -> demo category (an Item Group under the root group)
DEMO_CATEGORIES = {"2000000000011": "Demo Pens", "2000000000028": "Demo Paper", "2000000000035": "Demo Notebooks"}


def _assign_demo_categories():
	"""Put each demo product in its own category, including on past demo
	sales lines, so the category chart has something to compare."""
	root = frappe.db.get_value("Item Group", {"is_group": 1, "parent_item_group": ["in", ["", None]]}, "name") or "All Item Groups"
	for code, group in DEMO_CATEGORIES.items():
		if not frappe.db.exists("Item Group", group):
			frappe.get_doc(
				{"doctype": "Item Group", "item_group_name": group, "parent_item_group": root, "is_group": 0}
			).insert(ignore_permissions=True)
		if frappe.db.exists("Item", code):
			frappe.db.set_value("Item", code, "item_group", group, update_modified=False)
			frappe.db.sql(
				"""update `tabSales Invoice Item` item join `tabSales Invoice` inv on inv.name = item.parent
				set item.item_group = %s where item.item_code = %s and inv.remarks = %s""",
				(group, code, DEMO_SALE_REMARK),
			)


def _backfill_demo_sales(company: str):
	"""Daily demo sales between 35 and 70 days ago (older seeds only had one
	every 4 days there), so 30-day comparisons look like a real shop."""
	import random

	from frappe.utils import add_days, nowdate

	customers = [_demo_customer(name) for name in DEMO_CUSTOMERS]
	products = [(barcode, price) for barcode, _name, price, _qty, _level in DEMO_PRODUCTS]
	rng = random.Random(70)
	for shop_index, shop in enumerate(DEMO_SHOPS):
		warehouse = frappe.db.get_value("Retail Shop", shop, "warehouse")
		for days_ago in range(69, 34, -1):
			date = add_days(nowdate(), -days_ago)
			if frappe.db.exists("Sales Invoice", {"remarks": DEMO_SALE_REMARK, "set_warehouse": warehouse, "posting_date": date}):
				continue
			for _ in range(rng.randint(1, 3)):
				doc = frappe.get_doc(
					{
						"doctype": "Sales Invoice",
						"company": company,
						"customer": rng.choice(customers),
						"set_posting_time": 1,
						"posting_date": date,
						"due_date": date,
						"set_warehouse": warehouse,
						"update_stock": 0,
						"remarks": DEMO_SALE_REMARK,
						"items": [
							{
								"item_code": code,
								"qty": max(1, round(rng.randint(1, 12) * (1.0 if shop_index == 0 else 0.7))),
								"rate": price,
								"warehouse": warehouse,
							}
							for code, price in rng.sample(products, rng.randint(1, len(products)))
						],
					}
				)
				doc.insert(ignore_permissions=True)
				doc.submit()
