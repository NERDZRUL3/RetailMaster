"""Suppliers and purchase orders: order from a supplier for one shop, then
receive the goods (all at once or in several deliveries).

An order is an ERPNext Purchase Order delivered to the shop's warehouse;
receiving posts a submitted Purchase Receipt against it, which brings the
stock in at the order's unit cost. Everything runs with the signed-in
user's own permissions. Owners and managers may order and receive, managers
only for their own shops; partners may look; cashiers have no access.
A supplier's invoice for received goods (with or without an order) posts a
Purchase Receipt and a Purchase Invoice for it. Payments are not handled here.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, nowdate

from retail_management.api.inventory import _shops
from retail_management.services.idempotency import run_once
from retail_management.services.permissions import assert_shop_access
from retail_management.setup import ROLE_MANAGER, ROLE_OWNER, ROLE_PARTNER

VIEW_ROLES = frozenset({"System Manager", ROLE_OWNER, ROLE_PARTNER, ROLE_MANAGER})
BUY_ROLES = frozenset({"System Manager", ROLE_OWNER, ROLE_MANAGER})
MAX_LINES = 300


def _require(roles: frozenset, doctype: str, ptype: str):
	if frappe.session.user != "Administrator" and not roles.intersection(frappe.get_roles()):
		frappe.throw(_("You do not have access to purchasing."), frappe.PermissionError)
	frappe.has_permission(doctype, ptype, throw=True)


def can_buy() -> bool:
	return (frappe.session.user == "Administrator" or bool(BUY_ROLES.intersection(frappe.get_roles()))) and bool(
		frappe.has_permission("Purchase Order", "create")
	)


# ---------------------------------------------------------------- suppliers
def _supplier(name: str) -> dict:
	row = frappe.db.get_value(
		"Supplier",
		name,
		["name", "supplier_name", "mobile_no", "email_id", "supplier_details", "disabled"],
		as_dict=True,
	)
	return {
		"name": row.name,
		"supplier_name": row.supplier_name,
		"phone": row.mobile_no or "",
		"email": row.email_id or "",
		"notes": row.supplier_details or "",
		"disabled": cint(row.disabled),
	}


@frappe.whitelist()
def get_suppliers(query: str = "", limit: int = 100) -> list[dict]:
	_require(VIEW_ROLES, "Supplier", "read")
	or_filters = None
	query = (query or "").strip()
	if query:
		like = f"%{query}%"
		or_filters = [["supplier_name", "like", like], ["mobile_no", "like", like], ["email_id", "like", like]]
	names = frappe.get_list(
		"Supplier",
		or_filters=or_filters,
		pluck="name",
		order_by="supplier_name asc",
		limit=min(max(cint(limit), 1), 500),
	)
	open_orders = {}
	if names:
		for supplier, count in frappe.db.sql(
			"""select supplier, count(*) from `tabPurchase Order`
			where supplier in %(names)s and docstatus = 1 and per_received < 100
			and status not in ('Closed', 'Completed') group by supplier""",
			{"names": names},
		):
			open_orders[supplier] = cint(count)
	return [{**_supplier(name), "open_orders": open_orders.get(name, 0)} for name in names]


def _set_contact(supplier, phone: str, email: str):
	"""Keep the supplier's primary contact (phone, email) in step."""
	if not supplier.supplier_primary_contact:
		if phone or email:
			contact = frappe.get_doc(
				{
					"doctype": "Contact",
					"first_name": supplier.supplier_name,
					"links": [{"link_doctype": "Supplier", "link_name": supplier.name}],
				}
			)
			if phone:
				contact.add_phone(phone, is_primary_mobile_no=1)
			if email:
				contact.add_email(email, is_primary=1)
			contact.insert(ignore_permissions=True)  # the caller may write the supplier
			supplier.db_set("supplier_primary_contact", contact.name)
	else:
		contact = frappe.get_doc("Contact", supplier.supplier_primary_contact)
		contact.set("phone_nos", [row for row in contact.phone_nos if not row.is_primary_mobile_no])
		contact.set("email_ids", [row for row in contact.email_ids if not row.is_primary])
		if phone:
			contact.add_phone(phone, is_primary_mobile_no=1)
		if email:
			contact.add_email(email, is_primary=1)
		contact.save(ignore_permissions=True)
	supplier.db_set({"mobile_no": phone or None, "email_id": email or None})


@frappe.whitelist(methods=["POST"])
def save_supplier(supplier: dict | str) -> dict:
	"""Create or edit a supplier: name, phone, email, notes."""
	data = frappe.parse_json(supplier) or {}
	name = (data.get("name") or "").strip()
	label = (data.get("supplier_name") or "").strip()[:140]
	if not label:
		frappe.throw(_("Give the supplier a name."))
	phone = (data.get("phone") or "").strip()[:40]
	email = (data.get("email") or "").strip()[:140]
	if email:
		frappe.utils.validate_email_address(email, throw=True)

	if name:
		_require(BUY_ROLES, "Supplier", "write")
		doc = frappe.get_doc("Supplier", name)
		doc.check_permission("write")
		doc.supplier_name = label
	else:
		_require(BUY_ROLES, "Supplier", "create")
		if frappe.db.get_value("Supplier", {"supplier_name": label}, "name"):
			frappe.throw(_("A supplier named {0} already exists.").format(label))
		doc = frappe.new_doc("Supplier")
		doc.supplier_name = label
		doc.supplier_group = frappe.db.get_single_value("Buying Settings", "supplier_group") or frappe.db.get_value(
			"Supplier Group", {"is_group": 0}, "name"
		)
		doc.supplier_type = "Company"
	doc.supplier_details = (data.get("notes") or "").strip()[:1000]
	if "disabled" in data:
		doc.disabled = cint(data.get("disabled"))
	doc.save()
	_set_contact(doc, phone, email)
	return _supplier(doc.name)


# ---------------------------------------------------------------- orders
def _status(row) -> str:
	if row.docstatus == 0:
		return "draft"
	if row.docstatus == 2:
		return "cancelled"
	if row.status in ("Closed", "Completed") and flt(row.per_received) < 100:
		return "closed"
	if flt(row.per_received) >= 100:
		return "received"
	if flt(row.per_received) > 0:
		return "partly_received"
	return "ordered"


def _shop_of(warehouse: str | None) -> frappe._dict:
	return frappe.db.get_value(
		"Retail Shop", {"warehouse": warehouse}, ["name", "shop_name"], as_dict=True
	) or frappe._dict(name=None, shop_name=warehouse)


def _order(name: str) -> dict:
	doc = frappe.get_doc("Purchase Order", name)
	shop = _shop_of(doc.set_warehouse)
	receipts = frappe.db.sql(
		"""select distinct pr.name, pr.posting_date, pr.supplier_delivery_note, pr.owner, pr.creation
		from `tabPurchase Receipt` pr join `tabPurchase Receipt Item` pri on pri.parent = pr.name
		where pri.purchase_order = %s and pr.docstatus = 1 order by pr.posting_date desc, pr.creation desc""",
		name,
		as_dict=True,
	)
	return {
		"name": doc.name,
		"status": _status(doc),
		"supplier": doc.supplier,
		"supplier_name": doc.supplier_name,
		"shop": shop.name,
		"shop_name": shop.shop_name,
		"company": doc.company,
		"currency": doc.currency,
		"date": str(doc.transaction_date),
		"expected": str(doc.schedule_date) if doc.schedule_date else None,
		"notes": doc.remarks or "",
		"total": flt(doc.grand_total),
		"per_received": flt(doc.per_received),
		"lines": [
			{
				"row": row.name,
				"item_code": row.item_code,
				"item_name": row.item_name,
				"uom": row.uom,
				"qty": flt(row.qty),
				"received": flt(row.received_qty),
				"remaining": max(flt(row.qty) - flt(row.received_qty), 0),
				"rate": flt(row.rate),
				"amount": flt(row.amount),
			}
			for row in doc.items
		],
		"receipts": [
			{
				"name": r.name,
				"date": str(r.posting_date),
				"reference": r.supplier_delivery_note or "",
				"by": frappe.db.get_value("User", r.owner, "full_name") or r.owner,
			}
			for r in receipts
		],
		"by": frappe.db.get_value("User", doc.owner, "full_name") or doc.owner,
	}


@frappe.whitelist()
def get_orders(shop: str | None = None, status: str | None = None, query: str = "", limit: int = 100) -> list[dict]:
	"""Purchase orders of the user's shops, newest first.
	status: draft | open (placed, waiting for goods) | received | cancelled."""
	_require(VIEW_ROLES, "Purchase Order", "read")
	warehouses = {row.warehouse: row for row in _shops(shop)}
	if not warehouses:
		return []
	filters = {"set_warehouse": ("in", list(warehouses))}
	if status == "draft":
		filters["docstatus"] = 0
	elif status == "cancelled":
		filters["docstatus"] = 2
	elif status == "open":
		filters.update({"docstatus": 1, "per_received": ("<", 100), "status": ("not in", ["Closed", "Completed"])})
	elif status == "received":
		filters.update({"docstatus": 1, "per_received": (">=", 100)})
	query = (query or "").strip()
	or_filters = [["name", "like", f"%{query}%"], ["supplier_name", "like", f"%{query}%"]] if query else None
	rows = frappe.get_list(
		"Purchase Order",
		filters=filters,
		or_filters=or_filters,
		fields=[
			"name",
			"supplier_name",
			"set_warehouse",
			"transaction_date",
			"schedule_date",
			"grand_total",
			"currency",
			"docstatus",
			"status",
			"per_received",
			"total_qty",
		],
		order_by="transaction_date desc, creation desc",
		limit=min(max(cint(limit), 1), 500),
	)
	today = getdate(nowdate())
	out = []
	for row in rows:
		status_key = _status(row)
		out.append(
			{
				"name": row.name,
				"status": status_key,
				"supplier_name": row.supplier_name,
				"shop_name": warehouses[row.set_warehouse].shop_name if row.set_warehouse in warehouses else row.set_warehouse,
				"date": str(row.transaction_date),
				"expected": str(row.schedule_date) if row.schedule_date else None,
				"late": status_key in ("ordered", "partly_received")
				and bool(row.schedule_date)
				and getdate(row.schedule_date) < today,
				"total": flt(row.grand_total),
				"currency": row.currency,
				"qty": flt(row.total_qty),
				"per_received": flt(row.per_received),
			}
		)
	return out


@frappe.whitelist()
def get_order(name: str) -> dict:
	_require(VIEW_ROLES, "Purchase Order", "read")
	frappe.get_doc("Purchase Order", name).check_permission("read")
	return _order(name)


def _order_lines(lines, warehouse: str, schedule_date) -> list[dict]:
	lines = frappe.parse_json(lines) or []
	if not lines:
		frappe.throw(_("Add at least one product."))
	if len(lines) > MAX_LINES:
		frappe.throw(_("An order can have at most {0} lines.").format(MAX_LINES))
	rows = []
	for line in lines:
		code = (line.get("item_code") or "").strip()
		item = frappe.db.get_value(
			"Item", code, ["name", "item_name", "disabled", "is_purchase_item", "has_variants"], as_dict=True
		)
		if not item:
			frappe.throw(_("Product {0} not found.").format(code), frappe.DoesNotExistError)
		if item.disabled or not item.is_purchase_item or item.has_variants:
			frappe.throw(_("{0} cannot be ordered.").format(item.item_name))
		qty = flt(line.get("qty"))
		rate = flt(line.get("rate"))
		if qty <= 0:
			frappe.throw(_("Quantity must be more than zero for {0}.").format(item.item_name))
		if rate < 0:
			frappe.throw(_("Unit cost cannot be negative for {0}.").format(item.item_name))
		rows.append(
			{"item_code": item.name, "qty": qty, "rate": rate, "warehouse": warehouse, "schedule_date": schedule_date}
		)
	return rows


@frappe.whitelist(methods=["POST"])
def save_order(order: dict | str, submit: int = 0, request_id: str = "") -> dict:
	"""Create or edit a draft order; submit=1 also places it (no more edits)."""
	data = frappe.parse_json(order) or {}
	name = (data.get("name") or "").strip()
	_require(BUY_ROLES, "Purchase Order", "write" if name else "create")
	shop = data.get("shop") or ""
	if not shop:
		frappe.throw(_("Choose a shop."))
	assert_shop_access(shop)
	shop_row = frappe.db.get_value("Retail Shop", shop, ["name", "company", "warehouse", "enabled"], as_dict=True)
	if not shop_row or not shop_row.warehouse or not cint(shop_row.enabled):
		frappe.throw(_("Choose an active shop."))
	supplier = data.get("supplier") or ""
	if not supplier or not frappe.db.exists("Supplier", {"name": supplier, "disabled": 0}):
		frappe.throw(_("Choose a supplier."))
	schedule_date = data.get("expected") or add_days(nowdate(), 7)
	if getdate(schedule_date) < getdate(nowdate()):
		frappe.throw(_("The expected delivery date cannot be in the past."))
	lines = _order_lines(data.get("lines"), shop_row.warehouse, schedule_date)

	def action() -> str:
		if name:
			doc = frappe.get_doc("Purchase Order", name)
			doc.check_permission("write")
			if doc.docstatus != 0:
				frappe.throw(_("Only a draft order can be changed."))
			doc.set("items", [])
		else:
			doc = frappe.new_doc("Purchase Order")
			doc.transaction_date = nowdate()
		doc.update(
			{
				"supplier": supplier,
				"company": shop_row.company,
				"schedule_date": schedule_date,
				"set_warehouse": shop_row.warehouse,
				"remarks": (data.get("notes") or "").strip()[:1000],
			}
		)
		for row in lines:
			doc.append("items", row)
		doc.save()
		if cint(submit):
			_require(BUY_ROLES, "Purchase Order", "submit")
			doc.submit()
		return doc.name

	if name:
		return _order(action())
	return run_once("order", request_id, action, _order)


def _doc_for_action(name: str, ptype: str):
	_require(BUY_ROLES, "Purchase Order", ptype)
	doc = frappe.get_doc("Purchase Order", name)
	doc.check_permission(ptype)
	shop = frappe.db.get_value("Retail Shop", {"warehouse": doc.set_warehouse}, "name")
	if shop:
		assert_shop_access(shop)
	return doc


@frappe.whitelist(methods=["POST"])
def submit_order(name: str) -> dict:
	"""Place a draft order with the supplier."""
	doc = _doc_for_action(name, "submit")
	if doc.docstatus != 0:
		frappe.throw(_("This order is already placed."))
	if doc.schedule_date and getdate(doc.schedule_date) < getdate(nowdate()):
		doc.schedule_date = nowdate()
		for row in doc.items:
			row.schedule_date = nowdate()
		doc.save()
	doc.submit()
	return _order(name)


@frappe.whitelist(methods=["POST"])
def delete_order(name: str) -> dict:
	"""Delete a draft order."""
	doc = _doc_for_action(name, "delete")
	if doc.docstatus != 0:
		frappe.throw(_("Only a draft order can be deleted. Cancel or close it instead."))
	frappe.delete_doc("Purchase Order", name)
	return {"deleted": name}


@frappe.whitelist(methods=["POST"])
def cancel_order(name: str) -> dict:
	"""Cancel a placed order that nothing was received against yet."""
	doc = _doc_for_action(name, "cancel")
	if doc.docstatus != 1:
		frappe.throw(_("Only a placed order can be cancelled."))
	if flt(doc.per_received) > 0:
		frappe.throw(_("Goods were already received. Close the order instead."))
	doc.cancel()
	return _order(name)


@frappe.whitelist(methods=["POST"])
def close_order(name: str) -> dict:
	"""Stop waiting for the rest of a partly received order."""
	doc = _doc_for_action(name, "write")
	if doc.docstatus != 1 or flt(doc.per_received) >= 100 or doc.status in ("Closed", "Completed"):
		frappe.throw(_("Only an open order can be closed."))
	doc.update_status("Closed")
	return _order(name)


@frappe.whitelist(methods=["POST"])
def receive_order(name: str, lines: list | str, reference: str = "", request_id: str = "") -> dict:
	"""Receive a delivery against a placed order: lines give the quantity
	received per order row (row id from get_order). Stock comes into the
	order's shop at the order's unit cost."""
	from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt

	_require(BUY_ROLES, "Purchase Receipt", "create")
	order = _doc_for_action(name, "read")
	if order.docstatus != 1 or order.status in ("Closed", "Completed", "On Hold"):
		frappe.throw(_("This order cannot receive goods."))
	wanted = {}
	for line in frappe.parse_json(lines) or []:
		qty = flt(line.get("qty"))
		if qty < 0:
			frappe.throw(_("Quantities cannot be negative."))
		if qty:
			wanted[line.get("row")] = qty
	if not wanted:
		frappe.throw(_("Enter what was delivered."))
	remaining = {row.name: flt(row.qty) - flt(row.received_qty) for row in order.items}
	for row, qty in wanted.items():
		if row not in remaining:
			frappe.throw(_("This line is not on the order."))
		if qty > remaining[row] + 1e-9:
			frappe.throw(_("More than ordered was entered. Change the order first, or receive only what was ordered."))

	def action() -> str:
		receipt = make_purchase_receipt(name)
		receipt.set("items", [row for row in receipt.items if row.purchase_order_item in wanted])
		receipt.rejected_warehouse = None  # no rejected goods: only what is accepted is entered
		for row in receipt.items:
			row.qty = wanted[row.purchase_order_item]
			row.received_qty = row.qty
			row.rejected_qty = 0
			row.rejected_warehouse = None
			row.stock_qty = row.qty * flt(row.conversion_factor or 1)
		receipt.supplier_delivery_note = (reference or "").strip()[:140]
		receipt.insert()
		receipt.submit()
		return receipt.name

	run_once("po-receipt", request_id, action, lambda receipt: {"receipt": receipt})
	return _order(name)


# ---------------------------------------------------------------- supplier invoices
def _invoice_doc_lines(lines) -> list[dict]:
	lines = frappe.parse_json(lines) or []
	if not lines:
		frappe.throw(_("Add at least one product."))
	if len(lines) > MAX_LINES:
		frappe.throw(_("An invoice can have at most {0} lines.").format(MAX_LINES))
	return lines


def free_line(line: dict, warehouse: str) -> dict:
	"""A product on the invoice that is not on an order."""
	code = (line.get("item_code") or "").strip()
	item = frappe.db.get_value(
		"Item",
		code,
		["name", "item_name", "disabled", "is_purchase_item", "is_stock_item", "has_variants", "stock_uom"],
		as_dict=True,
	)
	if not item:
		frappe.throw(_("Product {0} not found.").format(code), frappe.DoesNotExistError)
	if item.disabled or not item.is_purchase_item or not item.is_stock_item or item.has_variants:
		frappe.throw(_("{0} cannot be bought into stock.").format(item.item_name))
	qty = flt(line.get("qty"))
	rate = flt(line.get("rate"))
	if qty <= 0:
		frappe.throw(_("Quantity must be more than zero for {0}.").format(item.item_name))
	if rate < 0:
		frappe.throw(_("Unit cost cannot be negative for {0}.").format(item.item_name))
	return {
		"item_code": item.name,
		"qty": qty,
		"received_qty": qty,
		"rate": rate,
		"uom": item.stock_uom,
		"stock_uom": item.stock_uom,
		"conversion_factor": 1,
		"warehouse": warehouse,
		# No cost known (a delivery note without prices): receive at zero rather than refuse.
		"allow_zero_valuation_rate": 0 if rate else 1,
	}


def _receipt_summary(name: str) -> dict:
	"""A delivery from a supplier: its Purchase Receipt and, if entered, the
	supplier's invoice (Purchase Invoice) for it."""
	pr = frappe.db.get_value(
		"Purchase Receipt",
		name,
		[
			"name",
			"supplier",
			"supplier_name",
			"set_warehouse",
			"posting_date",
			"supplier_delivery_note",
			"grand_total",
			"total_qty",
			"currency",
			"owner",
			"per_billed",
		],
		as_dict=True,
	)
	attachment = frappe.db.get_value(
		"File", {"attached_to_doctype": "Purchase Receipt", "attached_to_name": name}, "name"
	)
	invoice = frappe.db.sql(
		"""select distinct pi.name, pi.bill_no, pi.bill_date, pi.grand_total, pi.outstanding_amount, pi.creation
		from `tabPurchase Invoice` pi join `tabPurchase Invoice Item` pii on pii.parent = pi.name
		where pii.purchase_receipt = %s and pi.docstatus = 1 order by pi.creation desc limit 1""",
		name,
		as_dict=True,
	)
	invoice = invoice[0] if invoice else None
	orders = frappe.get_all(
		"Purchase Receipt Item", filters={"parent": name, "purchase_order": ("is", "set")}, pluck="purchase_order"
	)
	return {
		"receipt": pr.name,
		"invoice": invoice.name if invoice else None,
		"bill_no": (invoice.bill_no if invoice else pr.supplier_delivery_note) or "",
		"bill_date": str(invoice.bill_date) if invoice and invoice.bill_date else None,
		"outstanding": flt(invoice.outstanding_amount) if invoice else None,
		"supplier": pr.supplier,
		"supplier_name": pr.supplier_name,
		"shop_name": _shop_of(pr.set_warehouse).shop_name,
		"date": str(pr.posting_date),
		"total": flt(invoice.grand_total if invoice else pr.grand_total),
		"qty": flt(pr.total_qty),
		"currency": pr.currency,
		"orders": sorted(set(orders)),
		"billed": flt(pr.per_billed) >= 100,
		"attachment": attachment,
		"by": frappe.db.get_value("User", pr.owner, "full_name") or pr.owner,
	}


def receiving_target(data: dict) -> tuple:
	"""(order or None, shop row, supplier) for a delivery into one shop, checked:
	the shop is the user's and active, the order is open and for that shop."""
	shop = data.get("shop") or ""
	order_name = (data.get("order") or "").strip()
	order = _doc_for_action(order_name, "read") if order_name else None
	if order:
		if order.docstatus != 1 or order.status in ("Closed", "Completed", "On Hold"):
			frappe.throw(_("This order cannot receive goods."))
		shop = shop or _shop_of(order.set_warehouse).name or ""
	if not shop:
		frappe.throw(_("Choose a shop."))
	assert_shop_access(shop)
	shop_row = frappe.db.get_value("Retail Shop", shop, ["name", "company", "warehouse", "enabled"], as_dict=True)
	if not shop_row or not shop_row.warehouse or not cint(shop_row.enabled):
		frappe.throw(_("Choose an active shop."))
	if order and order.set_warehouse != shop_row.warehouse:
		frappe.throw(_("This order is for another shop."))
	supplier = (order.supplier if order else data.get("supplier")) or ""
	if not supplier or not frappe.db.exists("Supplier", {"name": supplier, "disabled": 0}):
		frappe.throw(_("Choose a supplier."))
	return order, shop_row, supplier


def post_receipt(supplier: str, shop_row, order, order_rows: dict, free_rows: list, reference: str):
	"""Insert and submit a Purchase Receipt into the shop: order_rows {order row: qty}
	at the order's cost, free_rows (from free_line) for products not on the order."""
	from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt

	if order and order_rows:
		receipt = make_purchase_receipt(order.name)
		receipt.set("items", [row for row in receipt.items if row.purchase_order_item in order_rows])
		for row in receipt.items:
			row.qty = order_rows[row.purchase_order_item]
			row.received_qty = row.qty
			row.rejected_qty = 0
			row.rejected_warehouse = None
			row.stock_qty = row.qty * flt(row.conversion_factor or 1)
	else:
		receipt = frappe.new_doc("Purchase Receipt")
		receipt.update(
			{
				"supplier": supplier,
				"company": shop_row.company,
				"set_warehouse": shop_row.warehouse,
				"currency": frappe.get_cached_value("Company", shop_row.company, "default_currency"),
			}
		)
	receipt.rejected_warehouse = None
	for row in free_rows:
		receipt.append("items", row)
	receipt.supplier_delivery_note = reference
	receipt.insert()
	receipt.submit()
	return receipt


def _bill(receipt_name: str, bill_no: str, bill_date):
	"""Submit the supplier's invoice (Purchase Invoice) for a received delivery."""
	from erpnext.stock.doctype.purchase_receipt.purchase_receipt import make_purchase_invoice

	bill = make_purchase_invoice(receipt_name)
	bill.bill_no = bill_no
	bill.bill_date = bill_date
	bill.disable_rounded_total = 1  # owe exactly what the supplier's invoice says
	bill.insert()
	bill.submit()
	return bill


def _bill_fields(data: dict, supplier: str) -> tuple[str, str]:
	bill_no = (data.get("bill_no") or "").strip()[:140]
	if not bill_no:
		frappe.throw(_("Enter the supplier's invoice number."))
	bill_date = data.get("bill_date") or nowdate()
	if getdate(bill_date) > getdate(nowdate()):
		frappe.throw(_("The invoice date cannot be in the future."))
	return bill_no, bill_date


def _no_duplicate_bill(supplier: str, bill_no: str):
	"""A supplier's invoice number is entered only once."""
	duplicate = frappe.db.get_value("Purchase Invoice", {"supplier": supplier, "bill_no": bill_no, "docstatus": 1}, "name")
	if duplicate:
		frappe.throw(_("Invoice {0} of this supplier was already entered ({1}).").format(bill_no, duplicate))


@frappe.whitelist(methods=["POST"])
def invoice_receipt(receipt: str, bill_no: str, bill_date: str | None = None, request_id: str = "") -> dict:
	"""Enter the supplier's invoice for a delivery already received (for example
	from a delivery note). Stock does not change; only what is owed is recorded."""
	_require(BUY_ROLES, "Purchase Invoice", "create")
	doc = frappe.get_doc("Purchase Receipt", receipt)
	doc.check_permission("read")
	shop = _shop_of(doc.set_warehouse).name
	if shop:
		assert_shop_access(shop)
	if doc.docstatus != 1 or doc.is_return:
		frappe.throw(_("Only a received delivery can be invoiced."))
	if flt(doc.per_billed) >= 100:
		frappe.throw(_("This delivery is already invoiced."))
	bill_no, bill_date = _bill_fields({"bill_no": bill_no, "bill_date": bill_date}, doc.supplier)

	def action() -> str:
		_no_duplicate_bill(doc.supplier, bill_no)
		_bill(doc.name, bill_no, bill_date)
		return doc.name

	return run_once("receipt-invoice", request_id, action, _receipt_summary)


@frappe.whitelist(methods=["POST"])
def receive_invoice(invoice: dict | str, request_id: str = "") -> dict:
	"""Enter a supplier's invoice for goods received into one shop.

	invoice: {supplier, shop, bill_no, bill_date, order?, lines: [{row?, item_code?, qty, rate?}]}.
	Lines with a row receive against that row of the order (at the order's
	unit cost); other lines are products not on an order, at the cost given.
	Posts a submitted Purchase Receipt (stock comes into the shop) and a
	submitted Purchase Invoice for it (what is owed to the supplier).
	"""
	data = frappe.parse_json(invoice) or {}
	_require(BUY_ROLES, "Purchase Receipt", "create")
	_require(BUY_ROLES, "Purchase Invoice", "create")
	order, shop_row, supplier = receiving_target(data)
	bill_no, bill_date = _bill_fields(data, supplier)

	order_rows, free_rows = {}, []
	remaining = {row.name: flt(row.qty) - flt(row.received_qty) for row in order.items} if order else {}
	for line in _invoice_doc_lines(data.get("lines")):
		row = line.get("row")
		if row:
			if row not in remaining:
				frappe.throw(_("This line is not on the order."))
			qty = flt(line.get("qty"))
			if qty < 0:
				frappe.throw(_("Quantities cannot be negative."))
			if qty > remaining[row] + 1e-9:
				frappe.throw(
					_("More than ordered was entered. Change the order first, or receive only what was ordered.")
				)
			if qty:
				order_rows[row] = qty
		else:
			free_rows.append(free_line(line, shop_row.warehouse))
	if not order_rows and not free_rows:
		frappe.throw(_("Enter what was delivered."))

	def action() -> str:
		_no_duplicate_bill(supplier, bill_no)
		receipt = post_receipt(supplier, shop_row, order, order_rows, free_rows, bill_no)
		_bill(receipt.name, bill_no, bill_date)
		return receipt.name

	return run_once("supplier-invoice", request_id, action, _receipt_summary)


@frappe.whitelist()
def get_supplier_invoices(shop: str | None = None, supplier: str | None = None, limit: int = 30) -> list[dict]:
	"""Latest deliveries received from suppliers into the user's shops, with
	the supplier's invoice when one was entered."""
	_require(VIEW_ROLES, "Purchase Receipt", "read")
	warehouses = [row.warehouse for row in _shops(shop)]
	if not warehouses:
		return []
	filters = {"docstatus": 1, "is_return": 0, "set_warehouse": ("in", warehouses)}
	if supplier:
		filters["supplier"] = supplier
	names = frappe.get_list(
		"Purchase Receipt",
		filters=filters,
		pluck="name",
		order_by="posting_date desc, creation desc",
		limit=min(max(cint(limit), 1), 200),
	)
	return [_receipt_summary(name) for name in names]


def clear_default_rejected_warehouse(doc, method=None):
	"""Purchase Receipt before_validate hook. A user restricted to one shop
	gets that shop's warehouse filled in as default on every warehouse field,
	including "rejected warehouse", which ERPNext then refuses (accepted and
	rejected warehouse the same). Rows with nothing rejected need none."""
	for row in doc.get("items") or []:
		if not flt(row.rejected_qty) and row.rejected_warehouse == row.warehouse:
			row.rejected_warehouse = None
	if doc.get("rejected_warehouse") and not any(flt(row.rejected_qty) for row in doc.get("items") or []):
		doc.rejected_warehouse = None


@frappe.whitelist()
def get_item_costs(item_codes: list | str, supplier: str | None = None) -> dict:
	"""Suggested unit cost per product: the last price paid (to this supplier
	if given), else the product's current cost."""
	_require(VIEW_ROLES, "Purchase Order", "read")
	codes = [code for code in (frappe.parse_json(item_codes) or []) if code][:MAX_LINES]
	out = {}
	for code in codes:
		rate = None
		if supplier:
			found = frappe.db.sql(
				"""select poi.rate from `tabPurchase Order Item` poi
				join `tabPurchase Order` po on po.name = poi.parent
				where po.supplier = %s and poi.item_code = %s and po.docstatus = 1
				order by po.transaction_date desc, po.creation desc limit 1""",
				(supplier, code),
			)
			rate = found[0][0] if found else None
		if rate is None:
			rate = frappe.db.get_value("Item", code, "last_purchase_rate") or frappe.db.get_value(
				"Item", code, "valuation_rate"
			)
		if not flt(rate):
			# Current cost in the shops' stock (stock received without an order).
			found = frappe.db.sql(
				"select avg(valuation_rate) from `tabBin` where item_code = %s and valuation_rate > 0", code
			)
			rate = found[0][0] if found else 0
		out[code] = flt(rate, 2)
	return out
