"""Team accounts, managed by the owner: create staff accounts, change their
name, email, username, role, shops and password, switch them off.

Only Retail Owners (and System Managers) may use this. It only ever
touches accounts whose roles are retail roles: System Managers and the
Administrator are never listed or changed here, and only the four retail
roles can be given, so nobody gains back-office administrator rights
through this page. Passwords are checked against the site's password
policy and are never returned. Accounts are switched off rather than
deleted, so their sales and history stay intact.
"""

import re

import frappe
from frappe import _
from frappe.utils import cint, get_datetime

from retail_management.setup import ROLE_CASHIER, ROLE_MANAGER, ROLE_OWNER, ROLE_PARTNER

TIERS = {"owner": ROLE_OWNER, "partner": ROLE_PARTNER, "manager": ROLE_MANAGER, "cashier": ROLE_CASHIER}
RETAIL_ROLES = frozenset(TIERS.values())
SHOP_TIERS = frozenset({"manager", "cashier"})
PROTECTED = ("Administrator", "Guest")
USERNAME = re.compile(r"[A-Za-z0-9._-]{3,60}")


def can_manage_users() -> bool:
	roles = set(frappe.get_roles())
	return frappe.session.user == "Administrator" or bool({"System Manager", ROLE_OWNER} & roles)


def _require():
	if not can_manage_users():
		frappe.throw(_("Only the owner may manage accounts."), frappe.PermissionError)


def _tier(roles: set[str]) -> str | None:
	for tier, role in TIERS.items():  # highest first
		if role in roles:
			return tier
	return None


def _managed(user: str) -> bool:
	"""An account this page may change: a retail account, not an administrator."""
	if user in PROTECTED:
		return False
	roles = set(frappe.get_roles(user))
	return bool(roles & RETAIL_ROLES) and "System Manager" not in roles


def _account(user: str) -> dict:
	row = frappe.db.get_value(
		"User",
		user,
		["name", "email", "first_name", "last_name", "full_name", "username", "enabled", "last_login"],
		as_dict=True,
	)
	return {
		"name": row.name,
		"email": row.email,
		"first_name": row.first_name or "",
		"last_name": row.last_name or "",
		"full_name": row.full_name or row.name,
		"username": row.username or "",
		"enabled": cint(row.enabled),
		"tier": _tier(set(frappe.get_roles(user))),
		"shops": frappe.get_all(
			"Retail Shop Access", filters={"user": user}, pluck="retail_shop", order_by="retail_shop"
		),
		"last_login": get_datetime(row.last_login).isoformat(timespec="seconds") if row.last_login else None,
		"me": user == frappe.session.user,
	}


@frappe.whitelist()
def get_users() -> dict:
	"""Every retail account (administrators excluded) and the shops to give."""
	_require()
	users = frappe.db.sql(
		"""select distinct hr.parent from `tabHas Role` hr
		where hr.parenttype = 'User' and hr.role in %(roles)s and hr.parent not in %(protected)s""",
		{"roles": list(RETAIL_ROLES), "protected": list(PROTECTED)},
		pluck=True,
	)
	order = list(TIERS)
	accounts = [_account(user) for user in users if _managed(user)]
	accounts.sort(
		key=lambda a: (not a["enabled"], order.index(a["tier"]) if a["tier"] else 9, a["full_name"].lower())
	)
	return {
		"users": accounts,
		"shops": frappe.get_all(
			"Retail Shop", filters={"enabled": 1}, fields=["name", "shop_name"], order_by="shop_name"
		),
		"username_login": cint(frappe.db.get_single_value("System Settings", "allow_login_using_user_name")),
	}


def _other_enabled_owners(user: str) -> int:
	return cint(
		frappe.db.sql(
			"""select count(distinct u.name) from `tabUser` u
			join `tabHas Role` hr on hr.parent = u.name and hr.parenttype = 'User'
			where hr.role = %(role)s and u.enabled = 1 and u.name != %(user)s
			and u.name not in %(protected)s""",
			{"role": ROLE_OWNER, "user": user, "protected": list(PROTECTED)},
		)[0][0]
	)


def _clean(data: dict, existing: str | None) -> dict:
	email = (data.get("email") or "").strip().lower()
	if not email:
		frappe.throw(_("Enter an email address."))
	frappe.utils.validate_email_address(email, throw=True)
	clash = frappe.db.get_value("User", {"email": email}, "name") or (
		frappe.db.exists("User", email) and email
	)
	if clash and clash != existing:
		frappe.throw(_("Another account already uses {0}.").format(email))

	first_name = (data.get("first_name") or "").strip()[:100]
	if not first_name:
		frappe.throw(_("Enter a first name."))
	username = (data.get("username") or "").strip()[:60]
	if username:
		if not USERNAME.fullmatch(username):
			frappe.throw(_("A username uses 3 to 60 letters, digits, dots, dashes or underscores."))
		clash = frappe.db.get_value("User", {"username": username}, "name")
		if clash and clash != existing:
			frappe.throw(_("The username {0} is taken.").format(username))

	tier = data.get("tier")
	if tier not in TIERS:
		frappe.throw(_("Choose a role."))
	shops = [shop for shop in (data.get("shops") or []) if shop]
	for shop in shops:
		if not frappe.db.exists("Retail Shop", shop):
			frappe.throw(_("Shop {0} not found.").format(shop))
	if tier in SHOP_TIERS and not shops:
		frappe.throw(_("Give this person at least one shop."))
	return {
		"email": email,
		"first_name": first_name,
		"last_name": (data.get("last_name") or "").strip()[:100],
		"username": username or None,
		"tier": tier,
		"shops": shops if tier in SHOP_TIERS else [],
		"enabled": cint(data.get("enabled", 1)),
		"password": data.get("password") or "",
	}


def _set_roles(user: str, tier: str):
	doc = frappe.get_doc("User", user)
	doc.set("roles", [row for row in doc.roles if row.role not in RETAIL_ROLES])
	doc.append("roles", {"role": TIERS[tier]})
	doc.flags.ignore_permissions = True
	doc.save()


def _set_shops(user: str, shops: list[str]):
	current = {
		row.retail_shop: row.name
		for row in frappe.get_all("Retail Shop Access", filters={"user": user}, fields=["name", "retail_shop"])
	}
	for shop, name in current.items():
		if shop not in shops:
			frappe.delete_doc("Retail Shop Access", name, ignore_permissions=True)
	for shop in shops:
		if shop not in current:
			frappe.get_doc({"doctype": "Retail Shop Access", "user": user, "retail_shop": shop}).insert(
				ignore_permissions=True
			)


def _check_password(password: str, user_data: tuple):
	from frappe.core.doctype.user.user import test_password_strength

	if len(password) < 8:
		frappe.throw(_("A password needs at least 8 characters."))
	if cint(frappe.db.get_single_value("System Settings", "enable_password_policy")):
		result = test_password_strength(password, user_data=user_data) or {}
		minimum = cint(frappe.db.get_single_value("System Settings", "minimum_password_score")) or 2
		if cint(result.get("score")) < minimum:
			frappe.throw(_("This password is too easy to guess. Use a longer one or the generator."))


def _set_password(user: str, password: str):
	"""Store the password and sign the person out everywhere else."""
	from frappe.utils.password import update_password

	update_password(user, password)
	frappe.sessions.clear_sessions(user, keep_current=user == frappe.session.user, force=True)


@frappe.whitelist(methods=["POST"])
def save_user(user: dict | str) -> dict:
	"""Create an account (password required) or change one (password optional)."""
	_require()
	data = frappe.parse_json(user) or {}
	name = (data.get("name") or "").strip()
	if name and (not frappe.db.exists("User", name) or not _managed(name)):
		frappe.throw(_("This account cannot be changed here."), frappe.PermissionError)
	clean = _clean(data, name or None)
	if clean["password"]:
		_check_password(clean["password"], (clean["email"], clean["first_name"], clean["last_name"]))

	if name:
		before = _tier(set(frappe.get_roles(name)))
		if name == frappe.session.user and (not clean["enabled"] or clean["tier"] != before):
			frappe.throw(_("You cannot switch off your own account or change your own role."))
		losing_owner = before == "owner" and (clean["tier"] != "owner" or not clean["enabled"])
		if losing_owner and not _other_enabled_owners(name):
			frappe.throw(_("There must always be at least one active owner."))
	elif not clean["password"]:
		frappe.throw(_("Set a password for the new account."))

	if name:
		if clean["email"] != name:
			from frappe.model.rename_doc import rename_doc

			# Links (shop access, documents they created) follow the new name.
			# Frappe's User.after_rename also renames the person's Notification
			# Settings with a permission check that cannot be skipped, so the
			# rename itself runs as Administrator once all checks above passed.
			acting = frappe.session.user
			try:
				frappe.set_user("Administrator")
				rename_doc("User", name, clean["email"], force=True, show_alert=False)
			finally:
				frappe.set_user(acting)
			name = clean["email"]
		doc = frappe.get_doc("User", name)
	else:
		doc = frappe.new_doc("User")
		doc.send_welcome_email = 0
		doc.user_type = "System User"
	doc.email = clean["email"]
	doc.first_name = clean["first_name"]
	doc.last_name = clean["last_name"]
	doc.username = clean["username"]
	doc.enabled = clean["enabled"]
	doc.flags.ignore_permissions = True
	doc.flags.no_welcome_mail = True
	if doc.is_new():
		doc.insert()
	else:
		doc.save()
	name = doc.name

	_set_roles(name, clean["tier"])
	_set_shops(name, clean["shops"])
	if clean["password"]:
		_set_password(name, clean["password"])
	if not clean["enabled"]:
		frappe.sessions.clear_sessions(name, force=True)
	return _account(name)
