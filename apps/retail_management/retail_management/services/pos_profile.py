"""Each shop's till settings: an ERPNext POS Profile created for the shop.

The profile holds what a sale needs: the shop's warehouse, the selling price
list, the walk-in customer, the accounts and the payment methods (Cash first,
Card when the company has an account for it). It is created once, then the
owner may change it in ERPNext.
"""

import frappe
from frappe import _

WALK_IN_CUSTOMER = "Walk-in Customer"
# (mode of payment, company field used as its account when none is set yet)
PAYMENT_METHODS = (("Cash", "default_cash_account"), ("Credit Card", "default_bank_account"))


def walk_in_customer() -> str:
	if not frappe.db.exists("Customer", WALK_IN_CUSTOMER):
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": WALK_IN_CUSTOMER,
				"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
				"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
			}
		).insert(ignore_permissions=True)
	return WALK_IN_CUSTOMER


def _payment_account(mode: str, company: str, fallback_field: str) -> str | None:
	if not frappe.db.exists("Mode of Payment", {"name": mode, "enabled": 1}):
		return None
	account = frappe.db.get_value(
		"Mode of Payment Account", {"parent": mode, "company": company}, "default_account"
	)
	if account:
		return account
	fallback = frappe.get_cached_value("Company", company, fallback_field)
	if not fallback:
		return None
	mode_doc = frappe.get_doc("Mode of Payment", mode)
	mode_doc.append("accounts", {"company": company, "default_account": fallback})
	mode_doc.save(ignore_permissions=True)
	return fallback


def ensure_shop_pos_profile(shop: str) -> str:
	"""The shop's POS profile, created on first use. Raises a clear error when
	the company is not set up enough to sell (no cash account)."""
	details = frappe.db.get_value(
		"Retail Shop", shop, ["name", "shop_name", "company", "warehouse", "pos_profile"], as_dict=True
	)
	if details.pos_profile:
		return details.pos_profile
	if not details.warehouse:
		frappe.throw(_("This shop has no warehouse."))

	company = frappe.get_cached_doc("Company", details.company)
	payments = []
	for mode, fallback_field in PAYMENT_METHODS:
		if _payment_account(mode, company.name, fallback_field):
			payments.append({"mode_of_payment": mode, "default": int(not payments)})
	if not payments:
		frappe.throw(_("Set a cash account on company {0} before selling.").format(company.name))

	name = details.shop_name
	if frappe.db.exists("POS Profile", name):
		name = f"{details.shop_name} - {company.abbr}"
	profile = frappe.get_doc(
		{
			"doctype": "POS Profile",
			"__newname": name,
			"company": company.name,
			"warehouse": details.warehouse,
			"customer": walk_in_customer(),
			"selling_price_list": frappe.db.get_single_value("Selling Settings", "selling_price_list")
			or "Standard Selling",
			"currency": company.default_currency,
			"write_off_account": company.write_off_account,
			"write_off_cost_center": company.cost_center,
			"cost_center": company.cost_center,
			"account_for_change_amount": company.default_cash_account,
			"update_stock": 1,
			"disable_rounded_total": 1,
			"payments": payments,
		}
	).insert(ignore_permissions=True)

	shop_doc = frappe.get_doc("Retail Shop", shop)
	shop_doc.pos_profile = profile.name
	shop_doc.save(ignore_permissions=True)  # re-syncs the shop users' permissions
	return profile.name
