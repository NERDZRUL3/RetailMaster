"""Shop scoping: which user may see which Retail Shop.

Owners, partners and system managers see every shop. Everyone else sees only
the shops they have a Retail Shop Access record for. These checks run on the
server; the frontend is never trusted to hide data.
"""

import frappe
from frappe import _

from retail_management.setup import ROLE_CASHIER, ROLE_MANAGER, ROLE_OWNER, ROLE_PARTNER

FULL_ACCESS_ROLES = frozenset({"System Manager", ROLE_OWNER, ROLE_PARTNER})
SHOP_SCOPED_ROLES = frozenset({ROLE_MANAGER, ROLE_CASHIER})


def is_shop_scoped_without_shop(user: str | None = None) -> bool:
	"""A manager or cashier who has been given no shop at all.

	Frappe treats "no User Permissions" as "no restriction", so such a user
	must be blocked explicitly from shop-linked ERPNext documents.
	"""
	user = user or frappe.session.user
	if has_full_shop_access(user):
		return False
	if not SHOP_SCOPED_ROLES.intersection(frappe.get_roles(user)):
		return False
	return not get_assigned_shops(user)


def no_shop_query_conditions(user: str | None = None, doctype: str | None = None) -> str:
	return "1=0" if is_shop_scoped_without_shop(user) else ""


def no_shop_has_permission(doc, ptype=None, user=None, debug=False) -> bool:
	return not is_shop_scoped_without_shop(user)


def has_full_shop_access(user: str | None = None) -> bool:
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return bool(FULL_ACCESS_ROLES.intersection(frappe.get_roles(user)))


def can_open_desk_app() -> bool:
	"""add_to_apps_screen hook: the Retail tile on the desk home is for people
	who run the business (owners, partners, system managers), not shop staff."""
	return has_full_shop_access()


def get_assigned_shops(user: str | None = None) -> list[str]:
	"""Shops explicitly assigned to the user through Retail Shop Access."""
	user = user or frappe.session.user
	return frappe.get_all("Retail Shop Access", filters={"user": user}, pluck="retail_shop")


def has_shop_access(shop: str, user: str | None = None) -> bool:
	user = user or frappe.session.user
	if has_full_shop_access(user):
		return True
	return shop in get_assigned_shops(user)


def assert_shop_access(shop: str, user: str | None = None) -> None:
	"""Raise PermissionError unless the user may work with this shop.

	Call this at the top of every custom API that takes a shop.
	"""
	if not has_shop_access(shop, user):
		frappe.throw(_("You do not have access to this shop."), frappe.PermissionError)


def shop_query_conditions(user: str | None = None, doctype: str | None = None) -> str:
	"""permission_query_conditions hook for Retail Shop (list views, reports, get_list)."""
	user = user or frappe.session.user
	if has_full_shop_access(user):
		return ""

	shops = get_assigned_shops(user)
	if not shops:
		return "1=0"

	escaped = ", ".join(frappe.db.escape(shop) for shop in shops)
	return f"`tabRetail Shop`.`name` in ({escaped})"


def shop_has_permission(doc, ptype=None, user=None, debug=False) -> bool:
	"""has_permission hook for Retail Shop (single documents).

	Frappe treats any falsy return value as a denial, so this returns True
	explicitly when access is allowed. It can only narrow role permissions,
	never widen them.
	"""
	user = user or frappe.session.user
	if has_full_shop_access(user):
		return True
	return bool(doc.name) and doc.name in get_assigned_shops(user)
