"""Till sessions: open with a counted float, cash in and out, X report,
close with a blind count, Z report, session history.

A session is ERPNext's own POS Opening Entry (one open session per shop till
and per person) and is closed with a POS Closing Entry, which holds the
counted amounts and the differences. Every sale belongs to the session of
the person selling, so only the person who opened the till sells on it until
it is closed; owners and managers may close someone else's session (a
forgotten till, a shift handover). Cash movements are Retail Cash Movement
records: they change the cash expected in the drawer but post nothing in the
accounts.
"""

import html

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime, getdate, now_datetime, nowdate

from retail_management.api.pos import _profile, _require_sell
from retail_management.setup import ROLE_MANAGER, ROLE_OWNER

MANAGE_ROLES = frozenset({"System Manager", ROLE_OWNER, ROLE_MANAGER})
LOCK_TTL = 60
MAX_REASON = 140


def can_manage() -> bool:
	return frappe.session.user == "Administrator" or bool(MANAGE_ROLES.intersection(frappe.get_roles()))


def _iso(value) -> str | None:
	return get_datetime(value).isoformat(timespec="seconds") if value else None


def _open_entry(pos_profile: str) -> frappe._dict | None:
	return frappe.db.get_value(
		"POS Opening Entry",
		{"pos_profile": pos_profile, "status": "Open", "docstatus": 1},
		["name", "user", "period_start_date"],
		as_dict=True,
	)


def session_info(pos_profile: str) -> dict | None:
	"""The till's open session, if any, as the till screen needs it."""
	entry = _open_entry(pos_profile)
	if not entry:
		return None
	return {
		"name": entry.name,
		"user": entry.user,
		"user_name": frappe.db.get_value("User", entry.user, "full_name") or entry.user,
		"mine": entry.user == frappe.session.user,
		"opened": _iso(entry.period_start_date),
		"outdated": getdate(entry.period_start_date) != getdate(nowdate()),
	}


def require_my_session(pos_profile: str) -> str:
	"""The caller's open, current session on this till, or a clear error."""
	info = session_info(pos_profile)
	if not info:
		frappe.throw(_("Open the till before selling."))
	if not info["mine"]:
		frappe.throw(_("This till is open by {0}. They must close it first.").format(info["user_name"]))
	if info["outdated"]:
		frappe.throw(_("This session started on an earlier day. Close it and open a new one."))
	return info["name"]


def last_closing_cash(pos_profile: str) -> float | None:
	"""Cash counted at the last close: usually what is left in the drawer."""
	cash_modes = _cash_modes()
	rows = frappe.db.sql(
		"""select d.mode_of_payment, d.closing_amount from `tabPOS Closing Entry Detail` d
		join `tabPOS Closing Entry` c on c.name = d.parent
		where c.pos_profile = %s and c.docstatus = 1
		order by c.period_end_date desc, d.idx limit 10""",
		pos_profile,
		as_dict=True,
	)
	return next((flt(row.closing_amount) for row in rows if row.mode_of_payment in cash_modes), None)


def _cash_modes() -> set[str]:
	return set(frappe.get_all("Mode of Payment", filters={"type": "Cash"}, pluck="name"))


def _lock(pos_profile: str) -> str:
	key = frappe.cache.make_key(f"retail_management:till:{pos_profile}")
	if not frappe.cache.set(key, frappe.session.user, ex=LOCK_TTL, nx=True):
		frappe.throw(_("The till is busy. Try again in a moment."))
	return key


@frappe.whitelist(methods=["POST"])
def open_session(shop: str, cash: float | str = 0) -> dict:
	"""Open the shop's till with the counted cash float."""
	shop_row = _require_sell(shop)
	frappe.has_permission("POS Opening Entry", "create", throw=True)
	profile = _profile(shop_row.pos_profile)
	cash = flt(cash)
	if cash < 0:
		frappe.throw(_("The opening cash cannot be negative."))

	key = _lock(profile.name)
	try:
		current = session_info(profile.name)
		if current:
			if current["mine"]:
				return current
			frappe.throw(_("This till is already open by {0}.").format(current["user_name"]))
		elsewhere = frappe.db.get_value(
			"POS Opening Entry", {"user": frappe.session.user, "status": "Open", "docstatus": 1}, "pos_profile"
		)
		if elsewhere:
			other = frappe.db.get_value("Retail Shop", {"pos_profile": elsewhere}, "shop_name") or elsewhere
			frappe.throw(_("You already have the till open in {0}. Close it first.").format(other))

		cash_modes = _cash_modes()
		cash_mode = next((row.mode_of_payment for row in profile.payments if row.mode_of_payment in cash_modes), None)
		entry = frappe.get_doc(
			{
				"doctype": "POS Opening Entry",
				"company": shop_row.company,
				"pos_profile": profile.name,
				"user": frappe.session.user,
				"period_start_date": now_datetime(),
				"posting_date": nowdate(),
				"balance_details": [
					{"mode_of_payment": row.mode_of_payment, "opening_amount": cash if row.mode_of_payment == cash_mode else 0}
					for row in profile.payments
				],
			}
		)
		entry.insert()
		entry.submit()
	finally:
		frappe.cache.delete(key)
	return session_info(profile.name)


def _session_doc(shop_row, allow_other: bool = False):
	info = session_info(shop_row.pos_profile)
	if not info:
		frappe.throw(_("The till is not open."))
	if not info["mine"] and not (allow_other and can_manage()):
		frappe.throw(_("This till is open by {0}.").format(info["user_name"]), frappe.PermissionError)
	return frappe.get_doc("POS Opening Entry", info["name"])


@frappe.whitelist(methods=["POST"])
def add_cash_movement(shop: str, movement_type: str, amount: float | str, reason: str) -> dict:
	"""Cash put into (In) or taken out of (Out) the drawer, with a reason."""
	shop_row = _require_sell(shop)
	entry = _session_doc(shop_row, allow_other=True)
	if movement_type not in ("In", "Out"):
		frappe.throw(_("Choose cash in or cash out."))
	amount = flt(amount, 2)
	if amount <= 0:
		frappe.throw(_("The amount must be more than zero."))
	reason = (reason or "").strip()[:MAX_REASON]
	if not reason:
		frappe.throw(_("Give a reason."))
	if movement_type == "Out":
		cash = next((row for row in _summary(entry)["rows"] if row["cash"]), None)
		if not cash or flt(cash["expected"]) + 0.005 < amount:
			frappe.throw(_("There is not that much cash in the till."))
	frappe.get_doc(
		{
			"doctype": "Retail Cash Movement",
			"pos_opening_entry": entry.name,
			"retail_shop": shop_row.name,
			"movement_type": movement_type,
			"amount": amount,
			"reason": reason,
		}
	).insert(ignore_permissions=True)  # caller checked above; records are API-only
	return _report(entry)


def _summary(entry, counts: dict | None = None) -> dict:
	"""Figures of one session. counts (mode -> counted amount) previews a close."""
	from erpnext.accounts.doctype.pos_closing_entry.pos_closing_entry import (
		get_payments,
		get_session_invoices,
	)

	closing = None
	if entry.pos_closing_entry:
		closing = frappe.db.get_value(
			"POS Closing Entry",
			{"name": entry.pos_closing_entry, "docstatus": 1},
			["name", "period_end_date"],
			as_dict=True,
		)
	if closing:
		# Once closed, the invoices are the ones listed on the closing entry.
		names = frappe.get_all(
			"Sales Invoice Reference",
			filters={"parent": closing.name, "parenttype": "POS Closing Entry"},
			pluck="sales_invoice",
		)
		invoices = frappe.get_all(
			"Sales Invoice",
			filters={"name": ("in", names or [""])},
			fields=[
				"name",
				"grand_total",
				"total_qty",
				"total_taxes_and_charges",
				"change_amount",
				"account_for_change_amount",
				"is_return",
			],
		)
		for invoice in invoices:
			invoice.doctype = "Sales Invoice"
	else:
		invoices = get_session_invoices(entry.period_start_date, now_datetime(), entry.pos_profile, entry.user)
	sales = {row.mode_of_payment: flt(row.amount) for row in get_payments(invoices)}
	cash_modes = _cash_modes()

	movements = frappe.get_all(
		"Retail Cash Movement",
		filters={"pos_opening_entry": entry.name},
		fields=["movement_type", "amount", "reason", "creation", "owner"],
		order_by="creation asc",
	)
	cash_in = sum(flt(m.amount) for m in movements if m.movement_type == "In")
	cash_out = sum(flt(m.amount) for m in movements if m.movement_type == "Out")

	counted = {}
	if closing:
		for row in frappe.get_all(
			"POS Closing Entry Detail",
			filters={"parent": closing.name, "parenttype": "POS Closing Entry"},
			fields=["mode_of_payment", "closing_amount"],
		):
			counted[row.mode_of_payment] = flt(row.closing_amount)
	elif counts is not None:
		counted = {mode: flt(amount, 2) for mode, amount in counts.items()}

	modes = [row.mode_of_payment for row in entry.balance_details]
	modes += [mode for mode in sales if mode not in modes]
	cash_mode = next((mode for mode in modes if mode in cash_modes), None)
	rows = []
	opening ={row.mode_of_payment: flt(row.opening_amount) for row in entry.balance_details}
	for mode in modes:
		is_cash = mode == cash_mode
		expected = flt(
			opening.get(mode, 0) + sales.get(mode, 0) + (cash_in - cash_out if is_cash else 0), 2
		)
		line = {
			"mode": mode,
			"cash": is_cash,
			"opening": opening.get(mode, 0),
			"sales": flt(sales.get(mode, 0), 2),
			"cash_in": cash_in if is_cash else 0,
			"cash_out": cash_out if is_cash else 0,
			"expected": expected,
			"counted": None,
			"difference": None,
		}
		if mode in counted:
			line["counted"] = counted[mode]
			line["difference"] = flt(counted[mode] - expected, 2)
		rows.append(line)

	sold = [inv for inv in invoices if not cint(inv.is_return)]
	returned = [inv for inv in invoices if cint(inv.is_return)]
	shop = frappe.db.get_value("Retail Shop", {"pos_profile": entry.pos_profile}, ["name", "shop_name"], as_dict=True)
	note = None
	if closing:
		content = frappe.db.get_value(
			"Comment",
			{"reference_doctype": "POS Closing Entry", "reference_name": closing.name, "comment_type": "Comment"},
			"content",
		)
		note = html.unescape(frappe.utils.strip_html(content)) if content else None
	return {
		"name": entry.name,
		"closing_entry": closing.name if closing else None,
		"shop": shop.name if shop else None,
		"shop_name": shop.shop_name if shop else entry.pos_profile,
		"user": entry.user,
		"user_name": frappe.db.get_value("User", entry.user, "full_name") or entry.user,
		"opened": _iso(entry.period_start_date),
		"closed": _iso(closing.period_end_date) if closing else None,
		"currency": frappe.get_cached_value("Company", entry.company, "default_currency"),
		"sales_count": len(sold),
		"sales_total": flt(sum(flt(inv.grand_total) for inv in sold), 2),
		"returns_count": len(returned),
		"returns_total": flt(sum(flt(inv.grand_total) for inv in returned), 2),
		"total": flt(sum(flt(inv.grand_total) for inv in invoices), 2),
		"taxes": flt(sum(flt(inv.total_taxes_and_charges) for inv in invoices), 2),
		"items": flt(sum(flt(inv.total_qty) for inv in invoices)),
		"rows": rows,
		"movements": [
			{
				"type": m.movement_type,
				"amount": flt(m.amount),
				"reason": m.reason,
				"time": _iso(m.creation),
				"by": frappe.db.get_value("User", m.owner, "full_name") or m.owner,
			}
			for m in movements
		],
		"note": note,
	}


def _report(entry, counts: dict | None = None) -> dict:
	"""The summary as this user may see it: while a session is open, staff who
	do not manage the shop do not see the expected amounts (blind count)."""
	report = _summary(entry, counts)
	if not report["closed"] and not can_manage():
		for row in report["rows"]:
			if row["counted"] is None:
				row["expected"] = None
	return report


@frappe.whitelist()
def get_session(shop: str) -> dict:
	"""X report: the open session so far."""
	shop_row = _require_sell(shop)
	return _report(_session_doc(shop_row, allow_other=True))


def _clean_counts(counts, entry) -> dict:
	counts = frappe.parse_json(counts) or {}
	allowed = {row.mode_of_payment for row in entry.balance_details}
	clean = {}
	for mode in allowed:
		value = counts.get(mode)
		if value in (None, ""):
			frappe.throw(_("Count {0}.").format(_(mode)))
		if flt(value) < 0:
			frappe.throw(_("A counted amount cannot be negative."))
		clean[mode] = flt(value, 2)
	return clean


@frappe.whitelist(methods=["POST"])
def preview_close(shop: str, counts: dict | str) -> dict:
	"""What closing with these counted amounts would show (nothing is saved)."""
	shop_row = _require_sell(shop)
	entry = _session_doc(shop_row, allow_other=True)
	return _summary(entry, _clean_counts(counts, entry))


@frappe.whitelist(methods=["POST"])
def close_session(shop: str, counts: dict | str, note: str = "") -> dict:
	"""Close the till: counted amounts per payment method, differences and the
	Z report. Owners and managers may close someone else's session."""
	from erpnext.accounts.doctype.pos_closing_entry.pos_closing_entry import (
		make_closing_entry_from_opening,
	)

	shop_row = _require_sell(shop)
	frappe.has_permission("POS Closing Entry", "create", throw=True)
	entry = _session_doc(shop_row, allow_other=True)
	clean = _clean_counts(counts, entry)

	key = _lock(entry.pos_profile)
	try:
		if frappe.db.get_value("POS Opening Entry", entry.name, "status") != "Open":
			entry.reload()
			return _summary(entry)
		summary = _summary(entry, clean)
		closing = make_closing_entry_from_opening(entry)
		closing.set(
			"payment_reconciliation",
			[
				{
					"mode_of_payment": row["mode"],
					"opening_amount": row["opening"],
					"expected_amount": row["expected"],
					"closing_amount": row["counted"],
					"difference": row["difference"],
				}
				for row in summary["rows"]
			],
		)
		closing.insert()
		closing.submit()
		note = (note or "").strip()[:1000]
		if note:
			closing.add_comment("Comment", frappe.utils.escape_html(note))
	finally:
		frappe.cache.delete(key)
	entry.reload()
	return _summary(entry)


@frappe.whitelist()
def get_report(name: str) -> dict:
	"""Any session's report (Z report once closed), for reprinting."""
	entry = frappe.get_doc("POS Opening Entry", name)
	entry.check_permission("read")
	shop = frappe.db.get_value("Retail Shop", {"pos_profile": entry.pos_profile}, "name")
	if shop:
		_require_sell(shop)
	if entry.user != frappe.session.user and not can_manage():
		frappe.throw(_("You may only see your own sessions."), frappe.PermissionError)
	return _report(entry)


@frappe.whitelist()
def list_sessions(shop: str, limit: int = 20) -> list[dict]:
	"""Latest sessions of the shop's till; staff who do not manage the shop see their own."""
	shop_row = _require_sell(shop)
	filters = {"pos_profile": shop_row.pos_profile, "docstatus": 1}
	if not can_manage():
		filters["user"] = frappe.session.user
	entries = frappe.get_list(
		"POS Opening Entry",
		filters=filters,
		fields=["name", "user", "period_start_date", "status", "pos_closing_entry"],
		order_by="period_start_date desc",
		limit=min(max(cint(limit), 1), 100),
	)
	closings = [row.pos_closing_entry for row in entries if row.pos_closing_entry]
	totals = {}
	if closings:
		for row in frappe.db.sql(
			"""select c.name, c.period_end_date, c.grand_total,
				coalesce(sum(d.difference), 0) as difference
			from `tabPOS Closing Entry` c
			left join `tabPOS Closing Entry Detail` d on d.parent = c.name and d.parenttype = 'POS Closing Entry'
			where c.name in %(names)s and c.docstatus = 1 group by c.name""",
			{"names": closings},
			as_dict=True,
		):
			totals[row.name] = row
	out = []
	for row in entries:
		closing = totals.get(row.pos_closing_entry)
		out.append(
			{
				"name": row.name,
				"user_name": frappe.db.get_value("User", row.user, "full_name") or row.user,
				"opened": _iso(row.period_start_date),
				"closed": _iso(closing.period_end_date) if closing else None,
				"total": flt(closing.grand_total) if closing else None,
				"difference": flt(closing.difference, 2) if closing else None,
				"open": row.status == "Open",
			}
		)
	return out
