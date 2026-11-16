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
