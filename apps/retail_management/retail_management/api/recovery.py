"""Getting back into an account without the server.

Two ways, both from the sign-in page:

- Email link: Frappe's own reset_password sends a link, when the site has an
  outgoing email account. `options` tells the page whether that works.
- Recovery codes: owners (and system managers) make a set of ten single-use
  codes while signed in, and keep them on paper. One code, with the account
  name, lets them set a new password without email. Codes are stored only as
  SHA-256 hashes, are shown once, and making a new set cancels the old one.

A wrong account, a wrong code, a used code or an account that may not hold
codes all get the same answer, and attempts are rate limited.
"""

import hashlib
import secrets

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import now_datetime

from retail_management.api.users import _check_password, _set_password
from retail_management.setup import ROLE_OWNER

DOCTYPE = "Retail Recovery Code"
CODE_COUNT = 10
# No 0/O, 1/I/L: easy to read back from paper.
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
GROUPS, GROUP_LEN = 3, 4  # XXXX-XXXX-XXXX, about 59 bits each


def can_hold_codes(user: str) -> bool:
	if user == "Administrator":
		return True
	if user == "Guest" or not frappe.db.get_value("User", user, "enabled"):
		return False
	return bool({ROLE_OWNER, "System Manager"} & set(frappe.get_roles(user)))


def _normalise(code: str) -> str:
	return "".join(ch for ch in (code or "").upper() if ch.isalnum())


def _hash(user: str, code: str) -> str:
	return hashlib.sha256(f"{user}\n{_normalise(code)}".encode()).hexdigest()


def _new_code() -> str:
	return "-".join("".join(secrets.choice(ALPHABET) for _ in range(GROUP_LEN)) for _ in range(GROUPS))


def _require_holder() -> str:
	user = frappe.session.user
	if not can_hold_codes(user):
		frappe.throw(_("Only owners can have recovery codes."), frappe.PermissionError)
	return user


def _remaining(user: str) -> int:
	return frappe.db.count(DOCTYPE, {"user": user, "used_on": ("is", "not set")})


@frappe.whitelist(allow_guest=True)
def options() -> dict:
	"""What the forgot-password page can offer."""
	email = bool(
		frappe.db.exists("Email Account", {"enable_outgoing": 1, "default_outgoing": 1})
		or frappe.conf.get("mail_server")
	)
	return {"email": email}


@frappe.whitelist()
def get_status() -> dict:
	user = _require_holder()
	created = frappe.db.get_value(DOCTYPE, {"user": user}, "creation", order_by="creation desc")
	return {
		"remaining": _remaining(user),
		"total": frappe.db.count(DOCTYPE, {"user": user}),
		"created": str(created) if created else None,
	}


@frappe.whitelist(methods=["POST"])
def generate_codes() -> dict:
	"""A new set of codes for the signed-in owner. The old set stops working.
	The codes are returned this once and never again."""
	user = _require_holder()
	frappe.db.delete(DOCTYPE, {"user": user})
	codes = [_new_code() for _ in range(CODE_COUNT)]
	for code in codes:
		frappe.get_doc({"doctype": DOCTYPE, "user": user, "code_hash": _hash(user, code)}).insert(
			ignore_permissions=True
		)
	return {"codes": codes, "remaining": CODE_COUNT}


def _find_user(account: str) -> str | None:
	account = (account or "").strip()
	if not account:
		return None
	if account.lower() == "administrator":
		return "Administrator"
	return frappe.db.get_value("User", {"name": account}) or frappe.db.get_value("User", {"username": account})


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60 * 60)
def reset_with_code(account: str, code: str, new_password: str) -> dict:
	"""Set a new password with one recovery code. The code is used up."""
	refused = _("This account and recovery code do not match, or the code was already used.")
	user = _find_user(account)
	row = None
	if user and can_hold_codes(user) and _normalise(code):
		row = frappe.db.get_value(
			DOCTYPE, {"user": user, "code_hash": _hash(user, code), "used_on": ("is", "not set")}, "name"
		)
	if not row:
		frappe.throw(refused, frappe.AuthenticationError)

	names = frappe.db.get_value("User", user, ["first_name", "last_name"]) or ("", "")
	_check_password(new_password or "", (user, *names))

	frappe.db.set_value(DOCTYPE, row, "used_on", now_datetime(), update_modified=False)
	_set_password(user, new_password)
	# A forgotten password usually comes with failed attempts: unlock the account.
	frappe.cache.hdel("login_failed_count", user)
	frappe.cache.hdel("locked_account_time", user)
	return {"ok": True, "remaining": _remaining(user)}
