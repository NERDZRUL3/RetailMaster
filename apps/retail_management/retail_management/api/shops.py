import frappe


@frappe.whitelist()
def get_my_shops() -> list[dict]:
	"""Shops the signed-in user may work with.

	Uses frappe.get_list, so role permissions and the shop scoping hook both
	apply. A user without a retail role gets a PermissionError.
	"""
	return frappe.get_list(
		"Retail Shop",
		filters={"enabled": 1},
		fields=["name", "shop_name", "retail_business", "company", "warehouse"],
		order_by="shop_name asc",
	)
