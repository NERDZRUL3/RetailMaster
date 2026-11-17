"""Point of sale: find products, ring up a sale, print the receipt.

A sale is one submitted ERPNext Sales Invoice (is_pos, update_stock) on the
shop's POS profile and warehouse, created with the signed-in user's own
permissions. Owners, managers and cashiers may sell; managers and cashiers
only in their own shops (checked here, and again by User Permissions on the
warehouse and POS profile). Prices always come from ERPNext (price list and
pricing rules), never from the browser.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from retail_management.services.permissions import assert_shop_access
from retail_management.services.pos_profile import ensure_shop_pos_profile
from retail_management.setup import ROLE_CASHIER, ROLE_MANAGER, ROLE_OWNER

SELL_ROLES = frozenset({"System Manager", ROLE_OWNER, ROLE_MANAGER, ROLE_CASHIER})
MAX_LINES = 200
REQUEST_TTL = 24 * 3600


def can_sell() -> bool:
	roles = set(frappe.get_roles())
	return bool(SELL_ROLES & roles) and bool(frappe.has_permission("Sales Invoice", "create"))


def _require_sell(shop: str) -> frappe._dict:
	if frappe.session.user != "Administrator" and not SELL_ROLES.intersection(frappe.get_roles()):
		frappe.throw(_("You may not sell."), frappe.PermissionError)
	frappe.has_permission("Sales Invoice", "create", throw=True)
	assert_shop_access(shop)
	shop_row = frappe.db.get_value(
		"Retail Shop", shop, ["name", "shop_name", "company", "warehouse", "enabled"], as_dict=True
	)
	if not cint(shop_row.enabled):
		frappe.throw(_("This shop is disabled."))
	shop_row.pos_profile = ensure_shop_pos_profile(shop)
	return shop_row


def _profile(name: str) -> frappe._dict:
	profile = frappe.db.get_value(
		"POS Profile", name, ["name", "selling_price_list", "currency", "customer", "disabled"], as_dict=True
	)
	if cint(profile.disabled):
		frappe.throw(_("This shop's till is disabled."))
	profile.payments = frappe.get_all(
		"POS Payment Method",
		filters={"parent": name, "parenttype": "POS Profile"},
		fields=["mode_of_payment", "default"],
		order_by="idx",
	)
	types = dict(
		frappe.get_all(
			"Mode of Payment",
			filters={"name": ("in", [row.mode_of_payment for row in profile.payments] or [""])},
			fields=["name", "type"],
			as_list=True,
		)
	)
	for row in profile.payments:
		row.type = types.get(row.mode_of_payment)
	return profile


@frappe.whitelist()
def get_till(shop: str) -> dict:
	"""What the till screen needs for one shop."""
	shop_row = _require_sell(shop)
	profile = _profile(shop_row.pos_profile)
	return {
		"shop": shop_row.name,
		"shop_name": shop_row.shop_name,
		"currency": profile.currency,
		"payments": [
			{"mode": row.mode_of_payment, "cash": row.type == "Cash", "default": cint(row.default)}
			for row in profile.payments
		],
	}


def _products(codes: list[str], shop_row, profile) -> list[dict]:
	if not codes:
		return []
	items = frappe.get_all(
		"Item",
		filters={"name": ("in", codes)},
		fields=["name", "item_name", "item_group", "stock_uom", "image"],
	)
	prices = dict(
		frappe.get_all(
			"Item Price",
			filters={"item_code": ("in", codes), "price_list": profile.selling_price_list},
			fields=["item_code", "price_list_rate"],
			as_list=True,
		)
	)
	stock = dict(
		frappe.get_all(
			"Bin",
			filters={"item_code": ("in", codes), "warehouse": shop_row.warehouse},
			fields=["item_code", "actual_qty"],
			as_list=True,
		)
	)
	barcodes: dict[str, str] = {}
	for row in frappe.get_all(
		"Item Barcode", filters={"parent": ("in", codes)}, fields=["parent", "barcode"], order_by="idx desc"
	):
		barcodes[row.parent] = row.barcode
	order = {code: index for index, code in enumerate(codes)}
	return sorted(
		(
			{
				"item_code": item.name,
				"item_name": item.item_name,
				"item_group": item.item_group,
				"uom": item.stock_uom,
				"image": item.image,
				"barcode": barcodes.get(item.name, ""),
				"price": flt(prices.get(item.name)),
				"stock": flt(stock.get(item.name)),
			}
			for item in items
		),
		key=lambda row: order[row["item_code"]],
	)


@frappe.whitelist()
def find_products(shop: str, query: str = "", limit: int = 24) -> list[dict]:
	"""Products to sell: an exact barcode or code first, then name matches.
	With no query, the products in stock in this shop."""
	shop_row = _require_sell(shop)
	profile = _profile(shop_row.pos_profile)
	query = (query or "").strip()[:100]
	limit = min(max(cint(limit), 1), 60)
	active = {"disabled": 0, "is_sales_item": 1, "has_variants": 0}

	codes: list[str] = []
	if query:
		barcode = frappe.db.get_value("Item Barcode", {"barcode": query}, "parent")
		if barcode:
			codes.append(barcode)
		elif frappe.db.exists("Item", query):
			codes.append(query)
		like = f"%{query}%"
		codes += frappe.get_all(
			"Item",
			filters=active,
			or_filters={"item_name": ("like", like), "item_code": ("like", like)},
			pluck="name",
			order_by="item_name asc",
			limit=limit,
		)
	else:
		in_stock = frappe.get_all(
			"Bin",
			filters={"warehouse": shop_row.warehouse, "actual_qty": (">", 0)},
			pluck="item_code",
			limit=500,
		)
		codes = frappe.get_all(
			"Item",
			filters={**active, "name": ("in", in_stock or [""])},
			pluck="name",
			order_by="item_name asc",
			limit=limit,
		)
	codes = list(dict.fromkeys(codes))[:limit]
	return _products(codes, shop_row, profile)


def _sale(name: str) -> dict:
	doc = frappe.get_doc("Sales Invoice", name)
	shop = frappe.db.get_value("Retail Shop", {"warehouse": doc.set_warehouse}, ["name", "shop_name"], as_dict=True)
	return {
		"name": doc.name,
		"posted": f"{doc.posting_date}T{str(doc.posting_time).split('.')[0].zfill(8)}",
		"shop": shop.name if shop else None,
		"shop_name": shop.shop_name if shop else None,
		"company": doc.company,
		"currency": doc.currency,
		"cashier": frappe.db.get_value("User", doc.owner, "full_name") or doc.owner,
		"customer": doc.customer_name,
		"lines": [
			{
				"item_code": row.item_code,
				"item_name": row.item_name,
				"qty": flt(row.qty),
				"rate": flt(row.rate),
				"amount": flt(row.amount),
			}
			for row in doc.items
		],
		"total": flt(doc.grand_total),
		"taxes": flt(doc.total_taxes_and_charges),
		"discount": flt(doc.discount_amount),
		"payments": [
			{"mode": row.mode_of_payment, "amount": flt(row.amount)} for row in doc.payments if flt(row.amount)
		],
		"paid": flt(doc.paid_amount),
		"change": flt(doc.change_amount),
	}


def _clean_lines(lines) -> list[dict]:
	lines = frappe.parse_json(lines) or []
	if not lines:
		frappe.throw(_("Add at least one product."))
	if len(lines) > MAX_LINES:
		frappe.throw(_("A sale can have at most {0} lines.").format(MAX_LINES))
	merged: dict[str, float] = {}
	for line in lines:
		code = (line.get("item_code") or "").strip()
		qty = flt(line.get("qty"))
		if qty <= 0:
			frappe.throw(_("Quantity must be more than zero."))
		merged[code] = merged.get(code, 0) + qty
	rows = []
	for code, qty in merged.items():
		item = frappe.db.get_value(
			"Item", code, ["name", "item_name", "disabled", "is_sales_item", "has_variants"], as_dict=True
		)
		if not item:
			frappe.throw(_("Product {0} not found.").format(code), frappe.DoesNotExistError)
		if item.disabled or not item.is_sales_item or item.has_variants:
			frappe.throw(_("{0} cannot be sold.").format(item.item_name))
		rows.append({"item_code": item.name, "qty": qty})
	return rows


def _clean_payments(payments, profile) -> list[dict]:
	payments = frappe.parse_json(payments) or []
	allowed = {row.mode_of_payment: row for row in profile.payments}
	amounts: dict[str, float] = {}
	for payment in payments:
		mode = payment.get("mode") or payment.get("mode_of_payment")
		amount = flt(payment.get("amount"))
		if mode not in allowed:
			frappe.throw(_("{0} is not accepted in this shop.").format(mode))
		if amount < 0:
			frappe.throw(_("A payment cannot be negative."))
		amounts[mode] = amounts.get(mode, 0) + amount
	# Every allowed method gets a row (ERPNext expects them), unpaid ones at zero.
	return [
		{"mode_of_payment": row.mode_of_payment, "amount": amounts.get(row.mode_of_payment, 0), "default": row.default}
		for row in profile.payments
	]


@frappe.whitelist(methods=["POST"])
def submit_sale(shop: str, lines: list | str, payments: list | str, request_id: str = "") -> dict:
	"""Ring up a paid sale: stock leaves the shop and the receipt is returned.
	Sending the same request_id twice (double click, network retry) returns
	the first sale instead of selling twice."""
	shop_row = _require_sell(shop)
	profile = _profile(shop_row.pos_profile)

	key = None
	request_id = (request_id or "").strip()[:64]
	if request_id:
		key = frappe.cache.make_key(f"retail_management:sale:{frappe.session.user}:{request_id}")
		if not frappe.cache.set(key, "pending", ex=REQUEST_TTL, nx=True):
			existing = frappe.safe_decode(frappe.cache.get(key) or b"")
			if existing and existing != "pending":
				return _sale(existing)
			frappe.throw(_("This sale is already being saved."))

	try:
		invoice = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": shop_row.company,
				"customer": profile.customer,
				"is_pos": 1,
				"pos_profile": profile.name,
				"update_stock": 1,
				"set_warehouse": shop_row.warehouse,
				"selling_price_list": profile.selling_price_list,
				"items": [{**row, "warehouse": shop_row.warehouse} for row in _clean_lines(lines)],
			}
		)
		invoice.set_missing_values(for_validate=True)
		for row in invoice.items:
			if flt(row.price_list_rate) <= 0 and flt(row.rate) <= 0:
				frappe.throw(_("{0} has no selling price.").format(row.item_name))
		invoice.set("payments", _clean_payments(payments, profile))
		invoice.calculate_taxes_and_totals()

		total = flt(invoice.grand_total)
		paid = sum(flt(row.amount) for row in invoice.payments)
		non_cash = sum(
			flt(row.amount)
			for row in invoice.payments
			if frappe.get_cached_value("Mode of Payment", row.mode_of_payment, "type") != "Cash"
		)
		precision = 1.0 / 10 ** (invoice.precision("grand_total") or 2)
		if paid + precision / 2 < total:
			frappe.throw(_("The payment does not cover the total."))
		if non_cash - precision / 2 > total:
			frappe.throw(_("Only cash can be more than the total (to give change)."))

		invoice.insert()
		invoice.submit()
	except Exception:
		if key:
			frappe.cache.delete(key)
		raise
	if key:
		frappe.cache.set(key, invoice.name, ex=REQUEST_TTL)
	return _sale(invoice.name)


@frappe.whitelist()
def get_sale(name: str) -> dict:
	"""One sale for the receipt (reprint). The user must be allowed to read it."""
	frappe.has_permission("Sales Invoice", "read", doc=name, throw=True)
	return _sale(name)


@frappe.whitelist()
def get_sales(shop: str, limit: int = 10) -> list[dict]:
	"""Today's latest sales in the shop (for reprinting a receipt)."""
	shop_row = _require_sell(shop)
	rows = frappe.get_list(
		"Sales Invoice",
		filters={
			"docstatus": 1,
			"is_pos": 1,
			"set_warehouse": shop_row.warehouse,
			"posting_date": frappe.utils.nowdate(),
		},
		fields=["name", "posting_time", "grand_total", "is_return", "owner"],
		order_by="posting_time desc, creation desc",
		limit=min(max(cint(limit), 1), 50),
	)
	return [
		{
			"name": row.name,
			"time": str(row.posting_time).split(".")[0].zfill(8)[:5],
			"total": flt(row.grand_total),
			"is_return": cint(row.is_return),
		}
		for row in rows
	]
