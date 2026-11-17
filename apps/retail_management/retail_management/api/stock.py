"""Inventory: stock on hand and its value, stock movements, transfers between
shops and stock counts.

Everything is read and written with the signed-in user's own permissions.
Stock only moves through submitted ERPNext documents: a transfer is a Stock
Entry (Material Transfer) between two shops' warehouses, a count is a Stock
Reconciliation that sets the counted quantities. Owners and managers may
transfer and count; managers only in their own shops (both shops for a
transfer). Partners may look; cashiers have no access.
"""

import frappe
from frappe import _
from frappe.utils import cint, escape_html, flt, get_datetime

from retail_management.api.inventory import _require_inventory, _shops
from retail_management.services.idempotency import previous_result, run_once
from retail_management.services.permissions import assert_shop_access
from retail_management.setup import ROLE_MANAGER, ROLE_OWNER

STOCK_ROLES = frozenset({"System Manager", ROLE_OWNER, ROLE_MANAGER})
MAX_LINES = 500

# Stock Ledger voucher -> kind of movement shown to the user
KINDS = ("sale", "return", "receipt", "purchase", "transfer", "count", "other")


def _require_stock(doctype: str):
	if frappe.session.user != "Administrator" and not STOCK_ROLES.intersection(frappe.get_roles()):
		frappe.throw(_("You may not change stock."), frappe.PermissionError)
	frappe.has_permission(doctype, "create", throw=True)


def _shop_row(shop: str) -> frappe._dict:
	assert_shop_access(shop)
	row = frappe.db.get_value("Retail Shop", shop, ["name", "shop_name", "company", "warehouse", "enabled"], as_dict=True)
	if not row or not row.warehouse:
		frappe.throw(_("This shop has no warehouse."))
	if not cint(row.enabled):
		frappe.throw(_("This shop is disabled."))
	return row


def _currency() -> str | None:
	company = frappe.defaults.get_user_default("Company") or frappe.db.get_value("Company", {}, "name")
	return frappe.get_cached_value("Company", company, "default_currency") if company else None


def _iso(date, time=None) -> str:
	if time is None:
		return get_datetime(date).isoformat(timespec="seconds")
	return f"{date}T{str(time).split('.')[0].zfill(8)}"


# ---------------------------------------------------------------- stock on hand
@frappe.whitelist()
def get_stock(shop: str | None = None, query: str = "", only: str = "all", limit: int = 300) -> dict:
	"""Stock per product and shop with its value at cost.
	only: all | low (at or below reorder level) | out (none left) | in (in stock)."""
	_require_inventory()
	shops = {row.warehouse: row for row in _shops(shop)}
	result = {"currency": _currency(), "totals": {"products": 0, "units": 0, "value": 0, "low": 0, "out": 0}, "rows": []}
	if not shops:
		return result

	item_filters = {"disabled": 0, "is_stock_item": 1, "has_variants": 0}
	query = (query or "").strip()
	or_filters = None
	if query:
		barcode_items = frappe.get_all("Item Barcode", filters={"barcode": query, "parenttype": "Item"}, pluck="parent")
		if barcode_items:
			item_filters["name"] = ("in", barcode_items)
		else:
			like = f"%{query}%"
			or_filters = [["item_code", "like", like], ["item_name", "like", like]]
	items = {
		row.name: row
		for row in frappe.get_list(
			"Item",
			filters=item_filters,
			or_filters=or_filters,
			fields=["name", "item_name", "item_group", "stock_uom"],
			limit=5000,
		)
	}
	if not items:
		return result

	bins = {
		(row.item_code, row.warehouse): row
		for row in frappe.get_list(
			"Bin",
			filters={"warehouse": ("in", list(shops)), "item_code": ("in", list(items))},
			fields=["item_code", "warehouse", "actual_qty", "stock_value", "valuation_rate"],
			limit=0,
		)
	}
	levels = {
		(row.parent, row.warehouse): flt(row.warehouse_reorder_level)
		for row in frappe.get_all(
			"Item Reorder",
			filters={"parenttype": "Item", "parent": ("in", list(items)), "warehouse": ("in", list(shops))},
			fields=["parent", "warehouse", "warehouse_reorder_level"],
		)
	}

	rows = []
	for code, item in items.items():
		for warehouse, shop_row in shops.items():
			stock = bins.get((code, warehouse))
			level = levels.get((code, warehouse), 0)
			if not stock and not level:
				continue  # never stocked here and no reorder rule: not part of this shop's range
			qty = flt(stock.actual_qty) if stock else 0
			row = {
				"item_code": code,
				"item_name": item.item_name,
				"item_group": item.item_group,
				"uom": item.stock_uom,
				"shop": shop_row.name,
				"shop_name": shop_row.shop_name,
				"qty": qty,
				"rate": flt(stock.valuation_rate) if stock else 0,
				"value": flt(stock.stock_value) if stock else 0,
				"reorder_level": level,
				"low": level > 0 and qty <= level,
				"out": qty <= 0,
			}
			rows.append(row)

	totals = result["totals"]
	totals["products"] = len({row["item_code"] for row in rows if row["qty"] > 0})
	totals["units"] = sum(row["qty"] for row in rows if row["qty"] > 0)
	totals["value"] = flt(sum(row["value"] for row in rows), 2)
	totals["low"] = sum(1 for row in rows if row["low"])
	totals["out"] = sum(1 for row in rows if row["out"])

	if only == "low":
		rows = [row for row in rows if row["low"]]
	elif only == "out":
		rows = [row for row in rows if row["out"]]
	elif only == "in":
		rows = [row for row in rows if row["qty"] > 0]
	rows.sort(key=lambda row: (row["item_name"].lower(), row["shop_name"]))
	result["rows"] = rows[: min(max(cint(limit), 1), 2000)]
	return result


# ---------------------------------------------------------------- movements
def _kind(row, purposes: dict) -> str:
	if row.voucher_type in ("Sales Invoice", "POS Invoice", "Delivery Note"):
		return "return" if flt(row.actual_qty) > 0 else "sale"
	if row.voucher_type == "Purchase Receipt":
		return "purchase"
	if row.voucher_type == "Stock Reconciliation":
		return "count"
	if row.voucher_type == "Stock Entry":
		purpose = purposes.get(row.voucher_no)
		if purpose == "Material Receipt":
			return "receipt"
		if purpose == "Material Transfer":
			return "transfer"
	return "other"


@frappe.whitelist()
def get_movements(
	shop: str | None = None, item_code: str | None = None, kind: str | None = None, start: int = 0, limit: int = 50
) -> dict:
	"""Stock ledger, newest first: every change of quantity with its reason."""
	_require_inventory()
	shops = {row.warehouse: row for row in _shops(shop)}
	if not shops:
		return {"rows": [], "more": False}
	filters = {"warehouse": ("in", list(shops)), "is_cancelled": 0}
	if item_code:
		filters["item_code"] = item_code
	voucher_types = {
		"sale": ["Sales Invoice", "POS Invoice", "Delivery Note"],
		"return": ["Sales Invoice", "POS Invoice", "Delivery Note"],
		"purchase": ["Purchase Receipt"],
		"count": ["Stock Reconciliation"],
		"receipt": ["Stock Entry"],
		"transfer": ["Stock Entry"],
	}.get(kind or "")
	if voucher_types:
		filters["voucher_type"] = ("in", voucher_types)
	if kind == "sale":
		filters["actual_qty"] = ("<", 0)
	elif kind == "return":
		filters["actual_qty"] = (">", 0)

	limit = min(max(cint(limit), 1), 200)
	start = max(cint(start), 0)
	# Fetch a little more when filtering stock entries by purpose afterwards.
	fetch = limit * 4 if kind in ("receipt", "transfer") else limit + 1
	rows = frappe.get_list(
		"Stock Ledger Entry",
		filters=filters,
		fields=[
			"name",
			"posting_date",
			"posting_time",
			"item_code",
			"warehouse",
			"actual_qty",
			"qty_after_transaction",
			"valuation_rate",
			"voucher_type",
			"voucher_no",
			"owner",
		],
		order_by="posting_date desc, posting_time desc, creation desc",
		start=start,
		limit=fetch,
	)
	entries = [row.voucher_no for row in rows if row.voucher_type == "Stock Entry"]
	purposes = dict(
		frappe.get_all("Stock Entry", filters={"name": ("in", entries)}, fields=["name", "purpose"], as_list=True)
	) if entries else {}
	if kind in ("receipt", "transfer"):
		rows = [row for row in rows if _kind(row, purposes) == kind]
	more = len(rows) > limit
	rows = rows[:limit]
	names = dict(
		frappe.get_all(
			"Item", filters={"name": ("in", list({row.item_code for row in rows}) or [""])}, fields=["name", "item_name"], as_list=True
		)
	)
	# A count's ledger entry carries the new balance, not the change: take
	# the change from the count itself (counted minus quantity before).
	count_changes = {}
	counted = [row.voucher_no for row in rows if row.voucher_type == "Stock Reconciliation"]
	if counted:
		for line in frappe.get_all(
			"Stock Reconciliation Item",
			filters={"parent": ("in", counted)},
			fields=["parent", "item_code", "warehouse", "qty", "current_qty"],
		):
			count_changes[(line.parent, line.item_code, line.warehouse)] = flt(line.qty) - flt(line.current_qty)
	users = {}
	out = []
	for row in rows:
		if row.owner not in users:
			users[row.owner] = frappe.db.get_value("User", row.owner, "full_name") or row.owner
		out.append(
			{
				"posted": _iso(row.posting_date, row.posting_time),
				"item_code": row.item_code,
				"item_name": names.get(row.item_code, row.item_code),
				"shop_name": shops[row.warehouse].shop_name,
				"kind": _kind(row, purposes),
				"qty": count_changes.get((row.voucher_no, row.item_code, row.warehouse), flt(row.actual_qty))
				if row.voucher_type == "Stock Reconciliation"
				else flt(row.actual_qty),
				"balance": flt(row.qty_after_transaction),
				"voucher_type": row.voucher_type,
				"voucher_no": row.voucher_no,
				"reversible": row.voucher_type == "Stock Reconciliation"
				or purposes.get(row.voucher_no) in REVERSIBLE_PURPOSES,
				"by": users[row.owner],
			}
		)
	return {"rows": out, "more": more}


# ---------------------------------------------------------------- transfers
def _items(lines, allow_zero: bool = False) -> list[dict]:
	lines = frappe.parse_json(lines) or []
	if not lines:
		frappe.throw(_("Add at least one product."))
	if len(lines) > MAX_LINES:
		frappe.throw(_("At most {0} lines.").format(MAX_LINES))
	merged: dict[str, float] = {}
	for line in lines:
		code = (line.get("item_code") or "").strip()
		qty = flt(line.get("qty"))
		if qty < 0 or (qty == 0 and not allow_zero):
			frappe.throw(_("Quantities must be more than zero."))
		item = frappe.db.get_value("Item", code, ["name", "item_name", "is_stock_item", "disabled", "stock_uom"], as_dict=True)
		if not item:
			frappe.throw(_("Product {0} not found.").format(code), frappe.DoesNotExistError)
		if not item.is_stock_item or item.disabled:
			frappe.throw(_("{0} is inactive or not a stock product.").format(item.item_name))
		merged[item.name] = (merged.get(item.name, 0) + qty) if not allow_zero else qty
	return [{"item_code": code, "qty": qty} for code, qty in merged.items()]


def _transfer(name: str) -> dict:
	entry = frappe.db.get_value(
		"Stock Entry",
		name,
		["name", "posting_date", "posting_time", "from_warehouse", "to_warehouse", "remarks", "owner"],
		as_dict=True,
	)
	lines = frappe.get_all(
		"Stock Entry Detail",
		filters={"parent": name, "parenttype": "Stock Entry"},
		fields=["item_code", "item_name", "qty", "s_warehouse", "t_warehouse"],
		order_by="idx",
	)
	shop = lambda warehouse: frappe.db.get_value("Retail Shop", {"warehouse": warehouse}, "shop_name") or warehouse  # noqa: E731
	return {
		"name": entry.name,
		"posted": _iso(entry.posting_date, entry.posting_time),
		"from_shop": shop(entry.from_warehouse or (lines[0].s_warehouse if lines else None)),
		"to_shop": shop(entry.to_warehouse or (lines[0].t_warehouse if lines else None)),
		"lines": [{"item_code": l.item_code, "item_name": l.item_name, "qty": flt(l.qty)} for l in lines],
		"qty": sum(flt(l.qty) for l in lines),
		"reference": entry.remarks or "",
		"by": frappe.db.get_value("User", entry.owner, "full_name") or entry.owner,
	}


@frappe.whitelist(methods=["POST"])
def transfer_stock(from_shop: str, to_shop: str, lines: list | str, reference: str = "", request_id: str = "") -> dict:
	"""Move stock from one shop to another in one submitted transfer."""
	_require_stock("Stock Entry")
	if from_shop == to_shop:
		frappe.throw(_("Choose two different shops."))
	source = _shop_row(from_shop)
	target = _shop_row(to_shop)
	if source.company != target.company:
		frappe.throw(_("Both shops must belong to the same company."))
	items = _items(lines)

	def action() -> str:
		entry = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Transfer",
				"purpose": "Material Transfer",
				"company": source.company,
				"from_warehouse": source.warehouse,
				"to_warehouse": target.warehouse,
				"remarks": (reference or "").strip()[:500],
				"items": [
					{**row, "s_warehouse": source.warehouse, "t_warehouse": target.warehouse} for row in items
				],
			}
		)
		entry.insert()
		entry.submit()
		return entry.name

	return run_once("transfer", request_id, action, _transfer)


@frappe.whitelist()
def get_transfers(shop: str | None = None, limit: int = 10) -> list[dict]:
	_require_inventory()
	warehouses = [row.warehouse for row in _shops(shop)]
	if not warehouses:
		return []
	names = frappe.get_list(
		"Stock Entry",
		filters={"docstatus": 1, "purpose": "Material Transfer"},
		or_filters={"from_warehouse": ("in", warehouses), "to_warehouse": ("in", warehouses)},
		pluck="name",
		order_by="posting_date desc, posting_time desc, creation desc",
		limit=min(max(cint(limit), 1), 50),
	)
	return [_transfer(name) for name in names]


# ---------------------------------------------------------------- stock counts
def _count(name: str) -> dict:
	doc = frappe.get_doc("Stock Reconciliation", name)
	shop = frappe.db.get_value("Retail Shop", {"warehouse": doc.items[0].warehouse}, "shop_name") if doc.items else None
	lines = [
		{
			"item_code": row.item_code,
			"item_name": row.item_name,
			"counted": flt(row.qty),
			"before": flt(row.current_qty),
			"difference": flt(row.qty) - flt(row.current_qty),
			"value_difference": flt(row.amount_difference),
		}
		for row in doc.items
	]
	return {
		"name": doc.name,
		"posted": _iso(doc.posting_date, doc.posting_time),
		"shop_name": shop,
		"lines": lines,
		"value_difference": flt(doc.difference_amount),
		"reference": doc.get("remarks") or _first_comment(doc),
		"by": frappe.db.get_value("User", doc.owner, "full_name") or doc.owner,
	}


def _first_comment(doc) -> str:
	return frappe.db.get_value(
		"Comment",
		{"reference_doctype": doc.doctype, "reference_name": doc.name, "comment_type": "Comment"},
		"content",
		order_by="creation asc",
	) or ""


def _post_count(shop_row, changed: list[dict], remarks: str) -> str:
	"""Submit a Stock Reconciliation setting these quantities in the shop's
	warehouse, valued at the current cost. Returns its name."""
	rows = []
	for row in changed:
		line = {"item_code": row["item_code"], "warehouse": shop_row.warehouse, "qty": row["qty"]}
		rate = frappe.db.get_value(
			"Bin", {"item_code": row["item_code"], "warehouse": shop_row.warehouse}, "valuation_rate"
		) or frappe.db.get_value("Item", row["item_code"], "valuation_rate")
		if flt(rate):
			line["valuation_rate"] = flt(rate)
		else:
			line["allow_zero_valuation_rate"] = 1
		rows.append(line)
	doc = frappe.get_doc(
		{
			"doctype": "Stock Reconciliation",
			"purpose": "Stock Reconciliation",
			"company": shop_row.company,
			"set_warehouse": shop_row.warehouse,
			"items": rows,
		}
	)
	remarks = (remarks or "").strip()[:500]
	if doc.meta.has_field("remarks"):
		doc.remarks = remarks
	doc.insert()
	doc.submit()
	if remarks and not doc.meta.has_field("remarks"):
		# Stock Reconciliation has no remarks field: keep the note as a
		# comment on the document, where the desk shows it.
		doc.add_comment("Comment", escape_html(remarks))
	return doc.name


@frappe.whitelist(methods=["POST"])
def submit_count(shop: str, lines: list | str, reference: str = "", request_id: str = "") -> dict:
	"""Set the counted quantities of a shop's products. Only products whose
	count differs from the stock on record are adjusted; returns what changed."""
	_require_stock("Stock Reconciliation")
	shop_row = _shop_row(shop)
	counted = _items(lines, allow_zero=True)
	current = {
		row.item_code: flt(row.actual_qty)
		for row in frappe.get_list(
			"Bin",
			filters={"warehouse": shop_row.warehouse, "item_code": ("in", [row["item_code"] for row in counted])},
			fields=["item_code", "actual_qty"],
		)
	}
	changed = [row for row in counted if abs(row["qty"] - current.get(row["item_code"], 0)) > 1e-9]
	if done := previous_result("count", request_id):
		result = _count(done)
		return {**result, "unchanged": len(counted) - len(result["lines"])}
	if not changed:
		return {"name": None, "lines": [], "unchanged": len(counted), "value_difference": 0}

	def action() -> str:
		return _post_count(shop_row, changed, reference)

	result = run_once("count", request_id, action, _count)
	result["unchanged"] = len(counted) - len(changed)
	return result


@frappe.whitelist()
def get_counts(shop: str | None = None, limit: int = 10) -> list[dict]:
	_require_inventory()
	warehouses = [row.warehouse for row in _shops(shop)]
	if not warehouses:
		return []
	names = frappe.get_list(
		"Stock Reconciliation",
		filters={"docstatus": 1, "purpose": "Stock Reconciliation", "set_warehouse": ("in", warehouses)},
		pluck="name",
		order_by="posting_date desc, posting_time desc, creation desc",
		limit=min(max(cint(limit), 1), 50),
	)
	return [_count(name) for name in names]


# ---------------------------------------------------------------- corrections
# Wrong stock is fixed with ordinary ERPNext documents, never by editing the
# ledger: either set the right quantity (a one-line Stock Reconciliation whose
# remarks carry the reason) or cancel the wrong Stock Entry / Stock
# Reconciliation (ERPNext then posts the reversing ledger rows). The reason is
# kept on the document, so the desk shows who corrected what and why.
REVERSIBLE_PURPOSES = frozenset({"Material Receipt", "Material Issue", "Material Transfer"})
REVERSIBLE_TYPES = ("Stock Entry", "Stock Reconciliation")


def _reason(reason: str) -> str:
	reason = (reason or "").strip()
	if len(reason) < 3:
		frappe.throw(_("Say why the stock is being corrected."))
	return reason[:500]


@frappe.whitelist(methods=["POST"])
def correct_stock(shop: str, item_code: str, qty: float, reason: str, request_id: str = "") -> dict:
	"""Set one product's quantity in a shop to what is really there. Posts a
	Stock Reconciliation for the difference, with the reason as its remarks."""
	_require_stock("Stock Reconciliation")
	reason = _reason(reason)
	shop_row = _shop_row(shop)
	line = _items([{"item_code": item_code, "qty": qty}], allow_zero=True)[0]
	if done := previous_result("correct", request_id):
		return _count(done)
	before = flt(frappe.db.get_value("Bin", {"item_code": line["item_code"], "warehouse": shop_row.warehouse}, "actual_qty"))
	if abs(line["qty"] - before) <= 1e-9:
		return {"name": None, "lines": [], "unchanged": 1, "value_difference": 0}
	return run_once(
		"correct", request_id, lambda: _post_count(shop_row, [line], _("Correction: {0}").format(reason)), _count
	)


def _voucher(voucher_type: str, voucher_no: str):
	"""The submitted document behind a movement, if this app may cancel it:
	a stock entry (receipt, issue, transfer) or a stock count, touching only
	the user's own shops."""
	if voucher_type not in REVERSIBLE_TYPES:
		frappe.throw(_("Only stock entries and stock counts can be cancelled here."))
	_require_stock(voucher_type)
	if not frappe.db.exists(voucher_type, voucher_no):
		frappe.throw(_("{0} {1} not found.").format(_(voucher_type), voucher_no), frappe.DoesNotExistError)
	doc = frappe.get_doc(voucher_type, voucher_no)
	if doc.docstatus != 1:
		frappe.throw(_("{0} is not an active stock document.").format(voucher_no))
	if voucher_type == "Stock Entry" and doc.purpose not in REVERSIBLE_PURPOSES:
		frappe.throw(_("This kind of stock entry cannot be cancelled here."))
	warehouses = set()
	for row in doc.items:
		warehouses.update(w for w in (row.get("s_warehouse"), row.get("t_warehouse"), row.get("warehouse")) if w)
	mine = {row.warehouse for row in _shops()}
	if not warehouses or not warehouses <= mine:
		frappe.throw(_("This document moves stock in a shop you do not manage."), frappe.PermissionError)
	frappe.has_permission(voucher_type, "cancel", doc=doc, throw=True)
	return doc


def _voucher_summary(doc) -> dict:
	shop = lambda warehouse: frappe.db.get_value("Retail Shop", {"warehouse": warehouse}, "shop_name") or warehouse  # noqa: E731
	lines = []
	for row in doc.items:
		if doc.doctype == "Stock Reconciliation":
			change = flt(row.qty) - flt(row.current_qty)
			where = shop(row.warehouse)
		else:
			change = flt(row.transfer_qty or row.qty)
			where = " → ".join(shop(w) for w in (row.s_warehouse, row.t_warehouse) if w)
			if row.s_warehouse and not row.t_warehouse:
				change = -change
		lines.append({"item_code": row.item_code, "item_name": row.item_name, "shop_name": where, "qty": change})
	return {
		"voucher_type": doc.doctype,
		"voucher_no": doc.name,
		"posted": _iso(doc.posting_date, doc.posting_time),
		"cancelled": doc.docstatus == 2,
		"lines": lines,
		"by": frappe.db.get_value("User", doc.owner, "full_name") or doc.owner,
	}


@frappe.whitelist()
def get_reversal(voucher_type: str, voucher_no: str) -> dict:
	"""What cancelling this document would undo (every line, not just one product)."""
	return _voucher_summary(_voucher(voucher_type, voucher_no))


@frappe.whitelist(methods=["POST"])
def reverse_movement(voucher_type: str, voucher_no: str, reason: str) -> dict:
	"""Undo a wrong stock entry or count by cancelling its document. ERPNext
	posts the reversing ledger rows; the reason is added as a comment."""
	reason = _reason(reason)
	doc = _voucher(voucher_type, voucher_no)
	doc.add_comment("Comment", _("Cancelled from the retail interface. Reason: {0}").format(escape_html(reason)))
	doc.cancel()
	return _voucher_summary(doc)
