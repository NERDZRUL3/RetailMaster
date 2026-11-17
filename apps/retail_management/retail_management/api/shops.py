"""Shops: the ones a user may work with, and (for the owner) setting them up.

A new shop only needs a name: it joins the site's Retail Business (created
from the application name on the first shop), uses the only company or the
one chosen, and gets its own warehouse automatically (Retail Shop.validate).
Its till settings are created the first time it sells.
"""

import frappe
from frappe import _
from frappe.utils import cint

from retail_management.api.users import _require as _require_owner


@frappe.whitelist()
def get_my_shops() -> list[dict]:
	"""Shops the signed-in user may work with.

	Uses frappe.get_list, so role permissions and the shop scoping hook both
	apply. A user without a retail role gets a PermissionError.
	"""
	return frappe.get_list(
		"Retail Shop",
		filters={"enabled": 1},
		fields=["name", "shop_name", "retail_business", "company", "warehouse"],
		order_by="shop_name asc",
	)


def _shop(name: str) -> dict:
	return frappe.db.get_value(
		"Retail Shop", name, ["name", "shop_name", "enabled", "company", "warehouse"], as_dict=True
	)


@frappe.whitelist()
def get_shop_setup() -> dict:
	"""Every shop, on or off, and the companies a new shop can belong to."""
	_require_owner()
	return {
		"shops": [_shop(name) for name in frappe.get_all("Retail Shop", order_by="shop_name asc", pluck="name")],
		"companies": frappe.get_all("Company", order_by="name asc", pluck="name"),
	}


def _business() -> str:
	existing = frappe.db.get_value("Retail Business", {"enabled": 1}, "name") or frappe.db.get_value(
		"Retail Business", {}, "name"
	)
	if existing:
		return existing
	name = (frappe.db.get_single_value("Retail Settings", "app_name") or "").strip() or frappe.db.get_value(
		"Company", {}, "name"
	)
	return frappe.get_doc({"doctype": "Retail Business", "business_name": name}).insert(ignore_permissions=True).name


@frappe.whitelist(methods=["POST"])
def create_shop(shop_name: str, company: str | None = None) -> dict:
	_require_owner()
	name = " ".join((shop_name or "").split())[:140]
	if not name:
		frappe.throw(_("Enter a shop name."))
	if frappe.db.exists("Retail Shop", name):
		frappe.throw(_("A shop called {0} already exists.").format(name))
	companies = frappe.get_all("Company", pluck="name")
	if not companies:
		frappe.throw(_("Set up the company in ERPNext first."))
	if company:
		if company not in companies:
			frappe.throw(_("Company {0} not found.").format(company))
	elif len(companies) == 1:
		company = companies[0]
	else:
		frappe.throw(_("Choose the company this shop belongs to."))
	doc = frappe.get_doc(
		{
			"doctype": "Retail Shop",
			"shop_name": name,
			"retail_business": _business(),
			"company": company,
			"enabled": 1,
		}
	).insert(ignore_permissions=True)
	return _shop(doc.name)


@frappe.whitelist(methods=["POST"])
def set_shop_enabled(shop: str, enabled: int | str) -> dict:
	"""Switch a shop off (hidden from menus and the till) or back on. Its
	sales, stock and staff access stay as they are."""
	_require_owner()
	if not frappe.db.exists("Retail Shop", shop):
		frappe.throw(_("Shop {0} not found.").format(shop))
	doc = frappe.get_doc("Retail Shop", shop)
	doc.enabled = cint(enabled)
	doc.save(ignore_permissions=True)
	return _shop(doc.name)
