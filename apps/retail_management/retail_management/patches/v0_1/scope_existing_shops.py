"""Give shops created before automatic warehouses one, then apply shop scoping
to everyone who already has shop access."""

import frappe

from retail_management.services.shop_access import sync_user_permissions


def execute():
	for name in frappe.get_all("Retail Shop", filters={"warehouse": ("is", "not set")}, pluck="name"):
		frappe.get_doc("Retail Shop", name).save(ignore_permissions=True)

	for user in set(frappe.get_all("Retail Shop Access", pluck="user")):
		sync_user_permissions(user)
