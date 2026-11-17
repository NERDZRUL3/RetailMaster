"""Overview dashboard: sales figures per period and shop.

Figures come from submitted ERPNext Sales Invoices, read with the signed-in
user's own permissions; a shop's sales are the invoices whose source
warehouse (set_warehouse) is that shop's warehouse. Return invoices carry
negative totals in ERPNext, so revenue is already net of returns. Nothing
is written here.
"""

import datetime

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, get_first_day, getdate, nowdate

from retail_management.api.inventory import INVENTORY_ROLES, _shops, get_low_stock

PERIODS = {"7d": 7, "30d": 30, "12m": 12}
RECENT_LIMIT = 8


def _require_dashboard():
	if frappe.session.user != "Administrator" and not INVENTORY_ROLES.intersection(frappe.get_roles()):
		frappe.throw(_("You do not have access to the business overview."), frappe.PermissionError)
	frappe.has_permission("Sales Invoice", "read", throw=True)


def _ranges(period: str, today: datetime.date):
	"""Current period, the previous one of the same length, and the bucket
	start dates of the current period (days, or months for 12m)."""
	if period == "12m":
		start = getdate(get_first_day(add_months(today, -11)))
		previous_start = getdate(add_months(start, -12))
		buckets = [getdate(add_months(start, i)) for i in range(12)]
	else:
		days = PERIODS[period]
		start = getdate(add_days(today, -(days - 1)))
		previous_start = getdate(add_days(start, -days))
		buckets = [getdate(add_days(start, i)) for i in range(days)]
	return start, previous_start, buckets


def _bucket_key(date: datetime.date, monthly: bool) -> str:
	return date.strftime("%Y-%m") if monthly else date.isoformat()


def _change(current: float, previous: float) -> float | None:
	"""Percentage change; None when there is nothing to compare with."""
	if not previous:
		return None
	return round((current - previous) / abs(previous) * 100, 1)


def _kpis(rows: list[dict]) -> dict:
	sales = [row for row in rows if not row.is_return]
	revenue = sum(flt(row.base_grand_total) for row in rows)
	sales_revenue = sum(flt(row.base_grand_total) for row in sales)
	return {
		"revenue": revenue,
		"sales": len(sales),
		"average": sales_revenue / len(sales) if sales else 0.0,
		"returns": len(rows) - len(sales),
	}


@frappe.whitelist()
def get_overview(period: str = "7d", shop: str | None = None) -> dict:
	"""KPIs with the change against the previous period, revenue per day (or
	month) split by shop, the latest sales and the low-stock count."""
	_require_dashboard()
	if period not in PERIODS:
		frappe.throw(_("Unknown period."))
	shops = _shops(shop)
	warehouses = {row.warehouse: row for row in shops}

	today = getdate(nowdate())
	start, previous_start, buckets = _ranges(period, today)
	monthly = period == "12m"

	result = {
		"period": period,
		"start": start.isoformat(),
		"end": today.isoformat(),
		"monthly": monthly,
		"currency": frappe.get_cached_value("Company", shops[0].company, "default_currency") if shops else None,
		"shops": [{"name": row.name, "shop_name": row.shop_name} for row in shops],
		"kpis": {},
		"series": [],
		"recent": [],
		"low_stock": 0,
	}
	if not warehouses:
		return result

	rows = frappe.get_list(
		"Sales Invoice",
		filters={
			"docstatus": 1,
			"set_warehouse": ("in", list(warehouses)),
			"posting_date": ("between", [previous_start, today]),
		},
		fields=["posting_date", "base_grand_total", "is_return", "set_warehouse"],
		limit_page_length=0,
	)
	current = [row for row in rows if getdate(row.posting_date) >= start]
	previous = [row for row in rows if getdate(row.posting_date) < start]

	now, before = _kpis(current), _kpis(previous)
	result["kpis"] = {
		key: {"value": now[key], "previous": before[key], "change": _change(now[key], before[key])} for key in now
	}

	series = {
		_bucket_key(day, monthly): {
			"key": _bucket_key(day, monthly),
			"total": 0.0,
			"by_shop": {row.name: 0.0 for row in shops},
		}
		for day in buckets
	}
	for row in current:
		bucket = series.get(_bucket_key(getdate(row.posting_date), monthly))
		if bucket:
			amount = flt(row.base_grand_total)
			bucket["total"] += amount
			bucket["by_shop"][warehouses[row.set_warehouse].name] += amount
	result["series"] = list(series.values())

	recent = frappe.get_list(
		"Sales Invoice",
		filters={"docstatus": 1, "set_warehouse": ("in", list(warehouses))},
		fields=[
			"name",
			"posting_date",
			"posting_time",
			"customer_name",
			"base_grand_total",
			"is_return",
			"status",
			"total_qty",
			"set_warehouse",
		],
		order_by="posting_date desc, posting_time desc, creation desc",
		limit_page_length=RECENT_LIMIT,
	)
	result["recent"] = [
		{
			"name": row.name,
			"date": str(row.posting_date),
			"customer": row.customer_name,
			"shop_name": warehouses[row.set_warehouse].shop_name,
			"items": flt(row.total_qty),
			"total": flt(row.base_grand_total),
			"is_return": bool(row.is_return),
			"status": row.status,
		}
		for row in recent
	]
	result["low_stock"] = len(get_low_stock(shop))
	return result


@frappe.whitelist()
def get_counts() -> dict:
	"""Small numbers for the menu badges."""
	if frappe.session.user != "Administrator" and not INVENTORY_ROLES.intersection(frappe.get_roles()):
		return {"low_stock": 0}
	return {"low_stock": len(get_low_stock())}
