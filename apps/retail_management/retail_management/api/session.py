import frappe
from frappe import _

from retail_management.api.shops import get_my_shops
from retail_management.services.branding import get_branding
from retail_management.services.permissions import has_full_shop_access
from retail_management.setup import ROLE_CASHIER, ROLE_MANAGER


def get_home(user: str) -> str | None:
	"""Which part of the custom interface the user lands on. None means no access."""
	if has_full_shop_access(user):
		return "owner"
	roles = frappe.get_roles(user)
	if ROLE_MANAGER in roles:
		return "manager"
	if ROLE_CASHIER in roles:
		return "cashier"
	return None


@frappe.whitelist(allow_guest=True)
def get_context() -> dict:
	"""Everything the custom interface needs to start: the site's branding,
	who is signed in, where they land and which shops they may work with.

	Guests get the branding and `authenticated: False` so the interface can
	show the login page. The navigation built from this is a convenience
	only; every data API checks permissions again on the server.
	"""
	branding = get_branding()
	user = frappe.session.user
	if user == "Guest":
		return {"authenticated": False, "branding": branding}

	home = get_home(user)
	details = frappe.db.get_value("User", user, ["full_name", "language"], as_dict=True)

	return {
		"authenticated": True,
		"branding": branding,
		"user": user,
		"full_name": details.full_name or user,
		"language": details.language if details.language in branding["languages"] else None,
		"home": home,
		"shops": get_my_shops() if home else [],
		"can_edit_settings": bool(frappe.has_permission("Retail Settings", "write")),
		"can_receive": _can_receive(),
		"can_sell": _can_sell(),
		"csrf_token": frappe.sessions.get_csrf_token(),
	}


@frappe.whitelist(methods=["POST"])
def set_language(language: str) -> str:
	"""Store the signed-in user's interface language."""
	if language not in get_branding()["languages"]:
		frappe.throw(_("Unsupported language."), frappe.ValidationError)

	frappe.db.set_value("User", frappe.session.user, "language", language)
	return language


def _can_sell() -> bool:
	"""Owners, managers and cashiers may use the point of sale."""
	from retail_management.api.pos import can_sell

	return can_sell()


def _can_receive() -> bool:
	"""Owners and managers may receive stock; partners and cashiers may not."""
	from retail_management.api.receiving import RECEIVE_ROLES

	roles = set(frappe.get_roles())
	return bool(RECEIVE_ROLES & roles) and bool(frappe.has_permission("Stock Entry", "create"))
