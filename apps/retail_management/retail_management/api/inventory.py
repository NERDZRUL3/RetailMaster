"""Product catalogue and stock levels for the custom interface.

Everything goes through ERPNext documents (Item, Item Barcode, Item Price,
Item Reorder, Bin) with the signed-in user's own permissions: role rights
from setup.ERPNEXT_PERMISSIONS, shop scoping from User Permissions. Stock is
never changed here; quantities only move through ERPNext stock transactions.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from retail_management.api.shops import get_my_shops
from retail_management.services.permissions import assert_shop_access
from retail_management.setup import ROLE_MANAGER, ROLE_OWNER, ROLE_PARTNER

INVENTORY_ROLES = frozenset({"System Manager", ROLE_OWNER, ROLE_PARTNER, ROLE_MANAGER})
ITEM_FIELDS = ["item_code", "item_name", "item_group", "stock_uom", "brand", "disabled", "image"]


def _require_inventory():
	if frappe.session.user != "Administrator" and not INVENTORY_ROLES.intersection(frappe.get_roles()):
		frappe.throw(_("You do not have access to products and stock."), frappe.PermissionError)
	frappe.has_permission("Item", "read", throw=True)


def _shops(shop: str | None = None) -> list[dict]:
	"""Shops in scope: the one asked for (if allowed) or all the user's shops."""
	if shop:
		assert_shop_access(shop)
	shops = [row for row in get_my_shops() if row.warehouse]
	if shop:
		shops = [row for row in shops if row.name == shop]
	return shops


def _selling_price_list() -> str | None:
	return frappe.db.get_single_value("Selling Settings", "selling_price_list")


def _default_item_group() -> str | None:
	"""Stock Settings' default group, else ERPNext's standard "Products" group,
	else the first non-group item group."""
	if group := frappe.db.get_single_value("Stock Settings", "item_group"):
		return group
	if frappe.db.exists("Item Group", {"name": "Products", "is_group": 0}):
		return "Products"
	return frappe.db.get_value("Item Group", {"is_group": 0}, "name", order_by="name asc")


def _enrich(items: list[dict], shops: list[dict]) -> list[dict]:
	"""Add barcodes, selling price and per-shop stock to item rows."""
	if not items:
		return []
	codes = [item.item_code for item in items]
	warehouses = {shop.warehouse: shop for shop in shops}

	barcodes: dict[str, list[str]] = {}
	for row in frappe.get_all(
		"Item Barcode", filters={"parent": ("in", codes)}, fields=["parent", "barcode"], order_by="idx"
	):
		barcodes.setdefault(row.parent, []).append(row.barcode)

	prices = {}
	price_list = _selling_price_list()
	if price_list:
		for row in frappe.get_list(
			"Item Price",
			filters={"item_code": ("in", codes), "price_list": price_list},
			fields=["item_code", "price_list_rate", "currency"],
		):
			prices[row.item_code] = row

	quantities = {}
	if warehouses:
		for row in frappe.get_list(
			"Bin",
			filters={"item_code": ("in", codes), "warehouse": ("in", list(warehouses))},
			fields=["item_code", "warehouse", "actual_qty"],
		):
			quantities[(row.item_code, row.warehouse)] = flt(row.actual_qty)

	reorder = {}
	if warehouses:
		for row in frappe.get_all(
			"Item Reorder",
			filters={"parent": ("in", codes), "parenttype": "Item", "warehouse": ("in", list(warehouses))},
			fields=["parent", "warehouse", "warehouse_reorder_level", "warehouse_reorder_qty"],
		):
			reorder[(row.parent, row.warehouse)] = row

	result = []
	for item in items:
		stock = []
		for warehouse, shop in warehouses.items():
			qty = quantities.get((item.item_code, warehouse), 0.0)
			rule = reorder.get((item.item_code, warehouse))
			level = flt(rule.warehouse_reorder_level) if rule else 0.0
			stock.append(
				{
					"shop": shop.name,
					"shop_name": shop.shop_name,
					"qty": qty,
					"reorder_level": level,
					"reorder_qty": flt(rule.warehouse_reorder_qty) if rule else 0.0,
					"low": bool(rule) and level > 0 and qty <= level,
				}
			)
		price = prices.get(item.item_code)
		result.append(
			{
				**item,
				"disabled": cint(item.disabled),
				"barcodes": barcodes.get(item.item_code, []),
				"price": flt(price.price_list_rate) if price else None,
				"currency": price.currency if price else None,
				"stock": stock,
				"total_qty": sum(row["qty"] for row in stock),
				"low": any(row["low"] for row in stock),
			}
		)
	return result


@frappe.whitelist()
def search_items(query: str = "", shop: str | None = None, low_only: int = 0, limit: int = 50) -> list[dict]:
	"""Find products by exact barcode, item code or name.

	An exact barcode match comes first, so a scanner (which types the code and
	presses Enter) lands on the right product.
	"""
	_require_inventory()
	shops = _shops(shop)
	query = (query or "").strip()
	limit = min(max(cint(limit) or 50, 1), 200)

	codes: list[str] = []
	if query:
		codes += frappe.get_all("Item Barcode", filters={"barcode": query, "parenttype": "Item"}, pluck="parent")
		like = f"%{query}%"
		codes += frappe.get_list(
			"Item",
			or_filters=[["item_code", "like", like], ["item_name", "like", like]],
			pluck="name",
			limit=limit,
			order_by="item_name asc",
		)
	else:
		codes = frappe.get_list("Item", pluck="name", limit=limit, order_by="modified desc")

	codes = list(dict.fromkeys(codes))[:limit]
	items = frappe.get_list("Item", filters={"name": ("in", codes)}, fields=ITEM_FIELDS) if codes else []
	order = {code: index for index, code in enumerate(codes)}
	items.sort(key=lambda item: order[item.item_code])

	result = _enrich(items, shops)
	if cint(low_only):
		result = [item for item in result if item["low"]]
	return result


@frappe.whitelist()
def get_item(item_code: str, shop: str | None = None) -> dict:
	_require_inventory()
	frappe.has_permission("Item", "read", doc=item_code, throw=True)
	item = frappe.get_list("Item", filters={"name": item_code}, fields=[*ITEM_FIELDS, "description"])
	if not item:
		frappe.throw(_("Product {0} not found.").format(item_code), frappe.DoesNotExistError)
	return _enrich(item, _shops(shop))[0]


@frappe.whitelist()
def get_low_stock(shop: str | None = None) -> list[dict]:
	"""Products at or below their reorder level in the user's shops."""
	_require_inventory()
	shops = _shops(shop)
	warehouses = [row.warehouse for row in shops]
	if not warehouses:
		return []
	codes = list(
		dict.fromkeys(
			frappe.get_all(
				"Item Reorder",
				filters={"parenttype": "Item", "warehouse": ("in", warehouses), "warehouse_reorder_level": (">", 0)},
				pluck="parent",
			)
		)
	)
	if not codes:
		return []
	items = frappe.get_list("Item", filters={"name": ("in", codes), "disabled": 0}, fields=ITEM_FIELDS)
	return [item for item in _enrich(items, shops) if item["low"]]


@frappe.whitelist()
def get_form_options() -> dict:
	_require_inventory()
	price_list = _selling_price_list()
	return {
		"item_groups": frappe.get_list("Item Group", filters={"is_group": 0}, pluck="name", order_by="name"),
		"uoms": frappe.get_list("UOM", filters={"enabled": 1}, pluck="name", order_by="name", limit=500),
		"brands": frappe.get_list("Brand", pluck="name", order_by="name", limit=500),
		"default_uom": frappe.db.get_single_value("Stock Settings", "stock_uom") or "Nos",
		"default_item_group": _default_item_group(),
		"price_list": price_list,
		"currency": frappe.db.get_value("Price List", price_list, "currency") if price_list else None,
		"shops": [{"name": s.name, "shop_name": s.shop_name} for s in _shops()],
		"can_create": bool(frappe.has_permission("Item", "create")),
		"can_write": bool(frappe.has_permission("Item", "write")),
	}


def _clean_barcodes(values) -> list[str]:
	barcodes = []
	for value in values or []:
		value = str(value).strip()
		if value and value not in barcodes:
			if len(value) > 140:
				frappe.throw(_("Barcode {0} is too long.").format(value[:20] + "…"))
			barcodes.append(value)
	return barcodes


@frappe.whitelist(methods=["POST"])
def save_item(item: dict | str) -> dict:
	"""Create or update a product: details, barcodes, selling price and
	per-shop reorder levels. Stock quantities are not touched."""
	_require_inventory()
	data = frappe.parse_json(item)

	item_code = (data.get("item_code") or "").strip()
	is_new = not (item_code and frappe.db.exists("Item", item_code))
	barcodes = _clean_barcodes(data.get("barcodes"))
	name = (data.get("item_name") or "").strip()
	if not name:
		frappe.throw(_("Product name is required."))

	if is_new:
		item_code = item_code or (barcodes[0] if barcodes else frappe.generate_hash(length=10).upper())
		doc = frappe.new_doc("Item")
		doc.item_code = item_code
		doc.is_stock_item = 1
		doc.include_item_in_manufacturing = 0
		doc.item_group = _default_item_group()
		doc.stock_uom = frappe.db.get_single_value("Stock Settings", "stock_uom") or "Nos"
	else:
		doc = frappe.get_doc("Item", item_code)

	# A clear message before ERPNext's own check, naming the other product.
	for barcode in barcodes:
		filters = {"barcode": barcode, "parenttype": "Item"}
		if not is_new:
			filters["parent"] = ("!=", item_code)
		other = frappe.db.get_value("Item Barcode", filters, "parent")
		if other:
			frappe.throw(_("Barcode {0} is already used by product {1}.").format(barcode, other))
	if is_new and frappe.db.exists("Item", item_code):
		frappe.throw(_("A product with code {0} already exists.").format(item_code))

	doc.item_name = name
	doc.item_group = data.get("item_group") or doc.item_group
	doc.stock_uom = data.get("stock_uom") or doc.stock_uom
	doc.brand = data.get("brand") or None
	doc.description = data.get("description") or doc.description or name
	doc.disabled = cint(data.get("disabled"))

	existing_types = {row.barcode: row.barcode_type for row in doc.get("barcodes", [])}
	doc.set("barcodes", [{"barcode": b, "barcode_type": existing_types.get(b, "")} for b in barcodes])

	for rule in data.get("reorder") or []:
		shop = rule.get("shop")
		assert_shop_access(shop)
		warehouse = frappe.db.get_value("Retail Shop", shop, "warehouse")
		if not warehouse:
			continue
		level, qty = flt(rule.get("level")), flt(rule.get("qty"))
		if level < 0 or qty < 0:
			frappe.throw(_("Reorder level and quantity cannot be negative."))
		rows = [row for row in doc.get("reorder_levels", []) if row.warehouse == warehouse]
		if level <= 0:
			for row in rows:
				doc.remove(row)
		elif rows:
			rows[0].warehouse_reorder_level = level
			rows[0].warehouse_reorder_qty = qty or level
		else:
			doc.append(
				"reorder_levels",
				{
					"warehouse": warehouse,
					"warehouse_reorder_level": level,
					"warehouse_reorder_qty": qty or level,
					"material_request_type": "Purchase",
				},
			)

	if is_new:
		doc.insert()
	else:
		doc.save()

	if "price" in data:
		_set_selling_price(doc.name, data.get("price"))

	return get_item(doc.name)


def _set_selling_price(item_code: str, price) -> None:
	price_list = _selling_price_list()
	if not price_list:
		frappe.throw(_("No default selling price list is set in Selling Settings."))
	existing = frappe.db.get_value("Item Price", {"item_code": item_code, "price_list": price_list})
	if price in (None, ""):
		if existing:
			frappe.delete_doc("Item Price", existing)
		return
	rate = flt(price)
	if rate < 0:
		frappe.throw(_("Price cannot be negative."))
	if existing:
		doc = frappe.get_doc("Item Price", existing)
		doc.price_list_rate = rate
		doc.save()
	else:
		frappe.get_doc(
			{"doctype": "Item Price", "item_code": item_code, "price_list": price_list, "price_list_rate": rate}
		).insert()
