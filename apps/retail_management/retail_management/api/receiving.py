"""Receiving stock into a shop (stock intake with the barcode scanner).

A receipt is one submitted ERPNext Stock Entry of type Material Receipt into
the shop's warehouse, created with the signed-in user's own permissions:
owners and managers may receive, managers only into their own shops (shop
check here, warehouse and company through User Permissions). Stock is never
changed any other way.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from retail_management.api.inventory import _require_inventory, _shops
from retail_management.services.permissions import assert_shop_access
from retail_management.setup import ROLE_MANAGER, ROLE_OWNER

RECEIVE_ROLES = frozenset({"System Manager", ROLE_OWNER, ROLE_MANAGER})
MAX_LINES = 500
REQUEST_TTL = 24 * 3600


def _require_receiving():
	if frappe.session.user != "Administrator" and not RECEIVE_ROLES.intersection(frappe.get_roles()):
		frappe.throw(_("You may not receive stock."), frappe.PermissionError)
	frappe.has_permission("Stock Entry", "create", throw=True)


def _receipt(name: str) -> dict:
	entry = frappe.db.get_value(
		"Stock Entry",
		name,
		["name", "posting_date", "posting_time", "to_warehouse", "total_incoming_value", "remarks", "owner"],
		as_dict=True,
	)
	totals = frappe.db.sql(
		"select count(*), coalesce(sum(qty), 0) from `tabStock Entry Detail` where parent = %s", name
	)[0]
	return {
		"name": entry.name,
		"posted": f"{entry.posting_date}T{str(entry.posting_time).split('.')[0].zfill(8)}",
		"shop_name": frappe.db.get_value("Retail Shop", {"warehouse": entry.to_warehouse}, "shop_name"),
		"lines": cint(totals[0]),
		"qty": flt(totals[1]),
		"value": flt(entry.total_incoming_value),
		"reference": entry.remarks or "",
		"by": frappe.db.get_value("User", entry.owner, "full_name") or entry.owner,
	}


def _clean_lines(lines, warehouse: str) -> list[dict]:
	lines = frappe.parse_json(lines) or []
	if not lines:
		frappe.throw(_("Scan or add at least one product."))
	if len(lines) > MAX_LINES:
		frappe.throw(_("A receipt can have at most {0} lines.").format(MAX_LINES))
	rows = []
	for line in lines:
		code = (line.get("item_code") or "").strip()
		item = frappe.db.get_value(
			"Item", code, ["name", "item_name", "is_stock_item", "disabled", "stock_uom", "valuation_rate"], as_dict=True
		)
		if not item:
			frappe.throw(_("Product {0} not found.").format(code), frappe.DoesNotExistError)
		if not item.is_stock_item or item.disabled:
			frappe.throw(_("{0} is inactive or not a stock product.").format(item.item_name))
		qty = flt(line.get("qty"))
		if qty <= 0:
			frappe.throw(_("Quantity must be more than zero for {0}.").format(item.item_name))
		row = {
			"item_code": item.name,
			"qty": qty,
			"t_warehouse": warehouse,
			"uom": item.stock_uom,
			"conversion_factor": 1,
		}
		rate = line.get("rate")
		if rate not in (None, ""):
			if flt(rate) < 0:
				frappe.throw(_("Unit cost cannot be negative for {0}.").format(item.item_name))
			row["basic_rate"] = flt(rate)
			row["set_basic_rate_manually"] = 1
		elif not flt(item.valuation_rate) and not frappe.db.get_value(
			"Bin", {"item_code": item.name, "warehouse": warehouse}, "valuation_rate"
		):
			# No cost known yet: receive at zero rather than refuse the delivery.
			row["allow_zero_valuation_rate"] = 1
		rows.append(row)
	return rows


@frappe.whitelist(methods=["POST"])
def receive_stock(shop: str, lines: list | str, reference: str = "", request_id: str = "") -> dict:
	"""Post a delivery into the shop's stock. Sending the same request_id
	twice (double click, network retry) returns the first receipt instead of
	receiving the goods twice."""
	_require_receiving()
	assert_shop_access(shop)
	details = frappe.db.get_value("Retail Shop", shop, ["company", "warehouse", "enabled"], as_dict=True)
	if not details or not details.warehouse:
		frappe.throw(_("This shop has no warehouse."))
	if not cint(details.enabled):
		frappe.throw(_("This shop is disabled."))

	key = None
	request_id = (request_id or "").strip()[:64]
	if request_id:
		key = frappe.cache.make_key(f"retail_management:receive:{frappe.session.user}:{request_id}")
		if not frappe.cache.set(key, "pending", ex=REQUEST_TTL, nx=True):
			existing = frappe.safe_decode(frappe.cache.get(key) or b"")
			if existing and existing != "pending":
				return _receipt(existing)
			frappe.throw(_("This delivery is already being saved."))

	try:
		entry = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Receipt",
				"purpose": "Material Receipt",
				"company": details.company,
				"to_warehouse": details.warehouse,
				"remarks": (reference or "").strip()[:500],
				"items": _clean_lines(lines, details.warehouse),
			}
		)
		entry.insert()
		entry.submit()
	except Exception:
		if key:
			frappe.cache.delete(key)
		raise
	if key:
		frappe.cache.set(key, entry.name, ex=REQUEST_TTL)
	return _receipt(entry.name)


@frappe.whitelist()
def get_receipts(shop: str | None = None, limit: int = 10) -> list[dict]:
	"""Latest deliveries received into the user's shops."""
	_require_inventory()
	warehouses = [row.warehouse for row in _shops(shop)]
	if not warehouses:
		return []
	names = frappe.get_list(
		"Stock Entry",
		filters={"docstatus": 1, "purpose": "Material Receipt", "to_warehouse": ("in", warehouses)},
		pluck="name",
		order_by="posting_date desc, posting_time desc, creation desc",
		limit=min(max(cint(limit), 1), 50),
	)
	return [_receipt(name) for name in names]
