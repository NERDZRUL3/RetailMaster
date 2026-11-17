"""Dashboard figures for the custom interface.

Everything comes from submitted ERPNext Sales Invoices. A shop's sales are
the invoices whose source warehouse (set_warehouse) is that shop's
warehouse; queries are limited to the warehouses of the shops the signed-in
user may see (retail_management.api.inventory._shops checks that), so a
manager only ever gets their own shop. Return invoices carry negative totals,
so revenue is net of returns. Nothing is written here.
"""

import datetime
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, flt, get_first_day, get_last_day, getdate, nowdate

from retail_management.api.inventory import INVENTORY_ROLES, _selling_price_list, _shops, get_low_stock
from retail_management.services.permissions import has_full_shop_access

TOP_CATEGORIES = 5
TOP_PRODUCTS = 5
RECENT = 5
ORDER_DAYS = 15
# (label, first hour, last hour + 1)
HOUR_BUCKETS = (("<10", 0, 10), ("10–12", 10, 12), ("12–15", 12, 15), ("15–18", 15, 18), ("18+", 18, 24))


def _require_dashboard():
	if frappe.session.user != "Administrator" and not INVENTORY_ROLES.intersection(frappe.get_roles()):
		frappe.throw(_("You do not have access to the dashboard."), frappe.PermissionError)
	frappe.has_permission("Sales Invoice", "read", throw=True)


def _change(current: float, previous: float) -> float | None:
	"""Percentage change; None when there is nothing to compare with."""
	if not previous:
		return None
	return round((current - previous) / abs(previous) * 100, 1)


def _shares(totals: dict[str, float], top: int) -> list[dict]:
	"""Largest entries as percentages of the whole, the rest as "Other"."""
	positive = {k: v for k, v in totals.items() if v > 0}
	whole = sum(positive.values())
	if not whole:
		return []
	ranked = sorted(positive.items(), key=lambda kv: kv[1], reverse=True)
	rows = [{"name": name, "value": value} for name, value in ranked[:top]]
	rest = sum(value for _, value in ranked[top:])
	if rest:
		rows.append({"name": None, "value": rest})  # "Other"
	for row in rows:
		row["percent"] = round(row["value"] / whole * 100)
	return rows


def _invoice_sql(where: str = "") -> str:
	return f"""
		from `tabSales Invoice` inv
		where inv.docstatus = 1 and inv.set_warehouse in %(warehouses)s {where}
	"""


def _dashboard_shops(shop: str | None = None) -> list[dict]:
	"""Shops in scope. Owners and partners also keep switched-off shops, so a
	closed shop's past sales stay in the totals; staff see their active shops."""
	if not has_full_shop_access():
		return _shops(shop)
	rows = frappe.get_all(
		"Retail Shop",
		filters={"warehouse": ("is", "set"), **({"name": shop} if shop else {})},
		fields=["name", "shop_name", "retail_business", "company", "warehouse", "enabled"],
		order_by="enabled desc, shop_name asc",
	)
	if shop and not rows:
		frappe.throw(_("Shop {0} not found.").format(shop), frappe.DoesNotExistError)
	return rows


@frappe.whitelist()
def get_dashboard(shop: str | None = None) -> dict:
	_require_dashboard()
	shops = _dashboard_shops(shop)
	warehouses = {row.warehouse: row for row in shops}
	today = getdate(nowdate())

	result = {
		"currency": frappe.get_cached_value("Company", shops[0].company, "default_currency") if shops else None,
		"shops": [
			{"name": row.name, "shop_name": row.shop_name, "enabled": cint(row.get("enabled", 1))} for row in shops
		],
		"today": today.isoformat(),
		"low_stock": 0,
	}
	if not warehouses:
		return result
	params = {"warehouses": tuple(warehouses)}

	# --- Per day and shop, far enough back for every comparison ---------------
	month_start = getdate(get_first_day(today))
	last_month_start = getdate(add_months(month_start, -1))
	week_start = getdate(add_days(today, -today.weekday()))
	since = min(getdate(add_days(today, -59)), last_month_start, getdate(add_days(week_start, -7)))
	daily = defaultdict(lambda: {"revenue": 0.0, "sales": 0, "returns": 0})
	by_shop_day = defaultdict(lambda: defaultdict(lambda: {"revenue": 0.0, "sales": 0}))
	for row in frappe.db.sql(
		f"""select inv.posting_date as day, inv.set_warehouse as warehouse,
			sum(inv.base_grand_total) as revenue, sum(inv.is_return = 0) as sales, sum(inv.is_return = 1) as returns
		{_invoice_sql("and inv.posting_date between %(since)s and %(today)s")}
		group by inv.posting_date, inv.set_warehouse""",
		{**params, "since": since, "today": today},
		as_dict=True,
	):
		day = getdate(row.day)
		daily[day]["revenue"] += flt(row.revenue)
		daily[day]["sales"] += cint(row.sales)
		daily[day]["returns"] += cint(row.returns)
		by_shop_day[warehouses[row.warehouse].name][day]["revenue"] += flt(row.revenue)
		by_shop_day[warehouses[row.warehouse].name][day]["sales"] += cint(row.sales)

	def total(field: str, start: datetime.date, end: datetime.date, source=daily) -> float:
		return sum(values[field] for day, values in source.items() if start <= day <= end)

	# Sales: receipts over the last 30 days, against the 30 before.
	start_30 = getdate(add_days(today, -29))
	prev_30 = (getdate(add_days(today, -59)), getdate(add_days(today, -30)))
	sales_now = total("sales", start_30, today)
	sales_before = total("sales", *prev_30)
	result["sales"] = {
		"value": sales_now,
		"previous": sales_before,
		"change": _change(sales_now, sales_before),
		"series": [
			{"date": getdate(add_days(start_30, i)).isoformat(), "value": daily[getdate(add_days(start_30, i))]["sales"]}
			for i in range(30)
		],
	}

	# Revenue: month to date against the same days of last month; this week
	# against last week, day by day.
	same_day_last_month = min(getdate(add_months(today, -1)), getdate(get_last_day(last_month_start)))
	month_now = total("revenue", month_start, today)
	month_before = total("revenue", last_month_start, same_day_last_month)
	result["revenue"] = {
		"value": month_now,
		"change": _change(month_now, month_before),
		"last_month": total("revenue", last_month_start, getdate(get_last_day(last_month_start))),
		"week": [
			{
				"this": daily[getdate(add_days(week_start, i))]["revenue"] if add_days(week_start, i) <= today else 0.0,
				"last": daily[getdate(add_days(week_start, i - 7))]["revenue"],
			}
			for i in range(7)
		],
	}

	# Customers: who bought in the last 30 days; first-time buyers this month.
	first_purchase = {
		row.customer: getdate(row.first)
		for row in frappe.db.sql(
			f"select inv.customer, min(inv.posting_date) as first {_invoice_sql('and inv.is_return = 0')} group by inv.customer",
			params,
			as_dict=True,
		)
	}
	recent_buyers = frappe.db.sql(
		f"""select count(distinct inv.customer)
		{_invoice_sql("and inv.is_return = 0 and inv.posting_date between %(start)s and %(end)s")}""",
		{**params, "start": start_30, "end": today},
	)[0][0]
	earlier_buyers = frappe.db.sql(
		f"""select count(distinct inv.customer)
		{_invoice_sql("and inv.is_return = 0 and inv.posting_date between %(start)s and %(end)s")}""",
		{**params, "start": prev_30[0], "end": prev_30[1]},
	)[0][0]
	new_now = sum(1 for day in first_purchase.values() if month_start <= day <= today)
	new_before = sum(1 for day in first_purchase.values() if last_month_start <= day <= same_day_last_month)
	shop_sales = {name: total("sales", start_30, today, days) for name, days in by_shop_day.items()}
	shop_sales_before = {name: total("sales", *prev_30, days) for name, days in by_shop_day.items()}
	all_sales = sum(shop_sales.values())
	result["customers"] = {
		"current": cint(recent_buyers),
		"current_change": _change(cint(recent_buyers), cint(earlier_buyers)),
		"new": new_now,
		"new_change": _change(new_now, new_before),
		"by_shop": [
			{
				"shop_name": row.shop_name,
				"sales": shop_sales.get(row.name, 0),
				"percent": round(shop_sales.get(row.name, 0) / all_sales * 100) if all_sales else 0,
				"change": _change(shop_sales.get(row.name, 0), shop_sales_before.get(row.name, 0)),
			}
			for row in shops
		],
	}

	# Categories and hours, for three ranges.
	ranges = {"all": None, "weekly": getdate(add_days(today, -6)), "monthly": start_30}
	result["categories"] = {}
	result["hours"] = {}
	for key, start in ranges.items():
		date_filter = "and inv.posting_date >= %(start)s" if start else ""
		groups = frappe.db.sql(
			f"""select item.item_group, sum(item.base_net_amount)
			from `tabSales Invoice Item` item join `tabSales Invoice` inv on inv.name = item.parent
			where inv.docstatus = 1 and inv.set_warehouse in %(warehouses)s {date_filter}
			group by item.item_group""",
			{**params, "start": start},
		)
		result["categories"][key] = _shares({group or "": flt(amount) for group, amount in groups}, TOP_CATEGORIES)

		counts = {label: 0 for label, _, _ in HOUR_BUCKETS}
		for hour, count in frappe.db.sql(
			f"select hour(inv.posting_time), count(*) {_invoice_sql('and inv.is_return = 0 ' + date_filter)} group by 1",
			{**params, "start": start},
		):
			for label, low, high in HOUR_BUCKETS:
				if low <= cint(hour) < high:
					counts[label] += cint(count)
		whole = sum(counts.values())
		result["hours"][key] = [
			{"label": label, "percent": round(count / whole * 100) if whole else 0} for label, count in counts.items()
		]

	# Item lines of the last 30 days: daily profit and best sellers.
	lines = frappe.db.sql(
		"""select inv.posting_date as day, item.item_code, item.item_name, item.stock_qty as qty,
			item.base_net_amount as amount, item.incoming_rate, item.price_list_rate
		from `tabSales Invoice Item` item join `tabSales Invoice` inv on inv.name = item.parent
		where inv.docstatus = 1 and inv.set_warehouse in %(warehouses)s and inv.posting_date >= %(start)s""",
		{**params, "start": start_30},
		as_dict=True,
	)
	codes = list({line.item_code for line in lines})
	stock, cost = defaultdict(float), {}
	if codes:
		bins = frappe.db.sql(
			"""select item_code, sum(actual_qty), sum(stock_value), sum(actual_qty)
			from `tabBin` where item_code in %(codes)s and warehouse in %(warehouses)s group by item_code""",
			{"codes": tuple(codes), **params},
		)
		for code, qty, value, _qty in bins:
			stock[code] = flt(qty)
			cost[code] = flt(value) / flt(qty) if flt(qty) > 0 else 0.0
		for code, rate in frappe.db.sql(
			"select name, valuation_rate from `tabItem` where name in %(codes)s", {"codes": tuple(codes)}
		):
			cost.setdefault(code, flt(rate))
			if not cost[code]:
				cost[code] = flt(rate)

	order_start = getdate(add_days(today, -(ORDER_DAYS - 1)))
	profit = defaultdict(float)
	for line in lines:
		day = getdate(line.day)
		if day >= order_start:
			unit_cost = flt(line.incoming_rate) or cost.get(line.item_code, 0.0)
			profit[day] += flt(line.amount) - flt(line.qty) * unit_cost
	result["orders"] = [
		{
			"date": getdate(add_days(order_start, i)).isoformat(),
			"income": daily[getdate(add_days(order_start, i))]["revenue"],
			"profit": profit[getdate(add_days(order_start, i))],
		}
		for i in range(ORDER_DAYS)
	]

	# Units sold are net of returns; the average price only counts sales.
	sold = defaultdict(lambda: {"name": "", "qty": 0.0, "sale_qty": 0.0, "sale_amount": 0.0, "list": 0.0})
	for line in lines:
		entry = sold[line.item_code]
		entry["name"] = line.item_name
		entry["qty"] += flt(line.qty)
		if flt(line.qty) > 0:
			entry["sale_qty"] += flt(line.qty)
			entry["sale_amount"] += flt(line.amount)
			entry["list"] = flt(line.price_list_rate) or entry["list"]
	price_list = _selling_price_list()
	products = []
	for code, entry in sorted(sold.items(), key=lambda kv: kv[1]["qty"], reverse=True)[:TOP_PRODUCTS]:
		if entry["qty"] <= 0 or entry["sale_qty"] <= 0:
			continue
		average = entry["sale_amount"] / entry["sale_qty"]
		list_price = entry["list"] or flt(
			frappe.db.get_value("Item Price", {"item_code": code, "price_list": price_list}, "price_list_rate")
		)
		products.append(
			{
				"item_code": code,
				"name": entry["name"],
				"stock": stock.get(code, 0.0),
				"list_price": list_price or average,
				"price": average,
				"discount": round((1 - average / list_price) * 100, 1) if list_price else 0.0,
				"sold": entry["qty"],
			}
		)
	result["products"] = products

	result["recent"] = [
		{
			"name": row.name,
			"customer": row.customer_name,
			"amount": flt(row.base_grand_total),
			"is_return": bool(row.is_return),
			"shop_name": warehouses[row.set_warehouse].shop_name,
			"posted": f"{row.posting_date}T{str(row.posting_time).split('.')[0].zfill(8)}",
		}
		for row in frappe.db.sql(
			f"""select inv.name, inv.customer_name, inv.base_grand_total, inv.is_return, inv.set_warehouse,
				inv.posting_date, inv.posting_time
			{_invoice_sql()}
			order by inv.posting_date desc, inv.posting_time desc, inv.creation desc limit {RECENT}""",
			params,
			as_dict=True,
		)
	]
	result["low_stock"] = len(get_low_stock(shop))
	return result


@frappe.whitelist()
def get_counts() -> dict:
	"""Small numbers for the menu badges, and the currency the shops trade in."""
	if frappe.session.user != "Administrator" and not INVENTORY_ROLES.intersection(frappe.get_roles()):
		return {"low_stock": 0, "currency": None}
	shops = _shops()
	currency = frappe.get_cached_value("Company", shops[0].company, "default_currency") if shops else None
	return {"low_stock": len(get_low_stock()), "currency": currency}
