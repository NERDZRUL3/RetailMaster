"""Turn Retail Shop Access into ERPNext User Permissions.

ERPNext documents (stock entries, stock balances, invoices, POS documents)
are restricted per shop with Frappe's standard User Permissions on Company,
Warehouse and POS Profile. Frappe then filters every list, report and
document that links to those records.

This module owns the User Permissions on those three doctypes for users with
a shop-scoped retail role (Retail Shop Manager, Retail Cashier). Never edit
them by hand for such users: the next sync replaces them with what their
Retail Shop Access records say. Users without a retail role are not touched.

Known limit: Frappe allows documents whose link field is empty (unless the
site enables "Apply Strict User Permissions"). Documents created by this app
always set the shop's warehouse and POS profile.
"""

import frappe

from retail_management.setup import ROLES

MANAGED_DOCTYPES = ("Company", "Warehouse", "POS Profile")


def _roles(user: str) -> set[str]:
	# Read straight from the database: during a User save the role cache can be stale.
	return set(frappe.get_all("Has Role", filters={"parent": user, "parenttype": "User"}, pluck="role"))


def desired_permissions(user: str) -> set[tuple[str, str]] | None:
	"""(doctype, value) pairs the user should be limited to.

	None means "leave this user alone" (no retail role). An empty set means
	"no restrictions" (owners, partners, system managers see every shop).
	"""
	from retail_management.services.permissions import FULL_ACCESS_ROLES

	if user in ("Administrator", "Guest"):
		return None
	roles = _roles(user)
	if not roles.intersection(ROLES):
		return None
	if roles.intersection(FULL_ACCESS_ROLES):
		return set()

	shops = frappe.get_all("Retail Shop Access", filters={"user": user}, pluck="retail_shop")
	wanted: set[tuple[str, str]] = set()
	for shop in frappe.get_all(
		"Retail Shop", filters={"name": ("in", shops)}, fields=["company", "warehouse", "pos_profile"]
	):
		for doctype, value in zip(MANAGED_DOCTYPES, (shop.company, shop.warehouse, shop.pos_profile)):
			if value:
				wanted.add((doctype, value))
	return wanted


def sync_user_permissions(user: str) -> None:
	wanted = desired_permissions(user)
	if wanted is None:
		return

	existing = frappe.get_all(
		"User Permission",
		filters={"user": user, "allow": ("in", MANAGED_DOCTYPES)},
		fields=["name", "allow", "for_value"],
	)
	have = {(row.allow, row.for_value): row.name for row in existing}

	for pair, name in have.items():
		if pair not in wanted:
			frappe.delete_doc("User Permission", name, ignore_permissions=True, force=True)

	for doctype, value in sorted(wanted - have.keys()):
		# With a single value per doctype, ERPNext also pre-fills it in new forms.
		only_one = sum(1 for d, _ in wanted if d == doctype) == 1
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": user,
				"allow": doctype,
				"for_value": value,
				"apply_to_all_doctypes": 1,
				"is_default": 1 if only_one else 0,
			}
		).insert(ignore_permissions=True)

	frappe.clear_cache(user=user)


def sync_shop_users(shop: str) -> None:
	for user in set(frappe.get_all("Retail Shop Access", filters={"retail_shop": shop}, pluck="user")):
		sync_user_permissions(user)


def on_user_update(doc, method=None):
	"""doc_events hook: a role change can widen or narrow a user's shop scope."""
	sync_user_permissions(doc.name)
