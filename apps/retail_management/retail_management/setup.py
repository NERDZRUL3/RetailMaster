import frappe

ROLE_OWNER = "Retail Owner"
ROLE_PARTNER = "Retail Partner"
ROLE_MANAGER = "Retail Shop Manager"
ROLE_CASHIER = "Retail Cashier"

ROLES = (ROLE_OWNER, ROLE_PARTNER, ROLE_MANAGER, ROLE_CASHIER)

# ERPNext document permissions for the retail roles, as Custom DocPerms
# (the same thing the Role Permissions Manager creates). r=read, w=write,
# c=create, d=delete. Shop scoping on top of these comes from services/shop_access.py.
_CATALOGUE_AND_STOCK = {
	"Item": "rwc",
	"Item Price": "rwcd",
	"Item Group": "r",
	"UOM": "r",
	"Brand": "r",
	"Price List": "r",
	"Warehouse": "r",
	"Bin": "r",
	"Stock Ledger Entry": "r",
}
# Read-only sales figures for the overview dashboard. Managers only see their
# own shops' invoices: the invoice's warehouse is scoped by User Permissions.
_SALES_REPORTING = {"Sales Invoice": "r"}
# Receiving stock posts Material Receipt stock entries into the shop's
# warehouse; User Permissions keep managers to their own shops' warehouses.
_RECEIVING = {"Stock Entry": "rwcs", "Stock Entry Type": "r"}
# Product categories (Item Group tree) are shared by all shops; owners and
# managers maintain them like the rest of the catalogue.
_CATEGORIES = {"Item Group": "rwcd"}
# Point of sale (api/pos.py): a sale is a submitted POS Sales Invoice in the
# shop's warehouse. User Permissions on warehouse and POS profile keep
# managers and cashiers to their own shops. Product lookups go through the
# API, so cashiers get no direct rights on products, prices or stock.
# ERPNext checks read access to the receivable and payment accounts it posts to.
_SELLING = {
	"Sales Invoice": "rwcs",
	"Account": "r",
	"Customer": "r",
	"Item": "r",
	"POS Profile": "r",
	"Mode of Payment": "r",
	"Price List": "r",
	# Till sessions (api/till.py), scoped by User Permissions on POS Profile.
	"POS Opening Entry": "rwcs",
	"POS Closing Entry": "rwcs",
}
ERPNEXT_PERMISSIONS = {
	ROLE_OWNER: {**_CATALOGUE_AND_STOCK, **_RECEIVING, **_CATEGORIES, **_SELLING, "Brand": "rwc"},
	ROLE_PARTNER: {**_CATALOGUE_AND_STOCK, **_SALES_REPORTING, "Stock Entry": "r", "Brand": "rwc"},
	ROLE_MANAGER: {**_CATALOGUE_AND_STOCK, **_RECEIVING, **_CATEGORIES, **_SELLING},
	ROLE_CASHIER: {**_SELLING},
}
_FLAG_TO_PTYPE = {
	"r": ("read", "report"),
	"w": ("write",),
	"c": ("create",),
	"d": ("delete",),
	"s": ("submit",),
}


def ensure_roles():
	"""Create the retail roles if they are missing. Safe to run repeatedly."""
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
				ignore_permissions=True
			)


def ensure_erpnext_permissions():
	"""Grant the retail roles the ERPNext permissions listed above.

	Only adds rights, never removes them, so a customer's own changes in the
	Role Permissions Manager survive. Safe to run repeatedly.
	"""
	from frappe.permissions import add_permission, update_permission_property

	for role, doctypes in ERPNEXT_PERMISSIONS.items():
		for doctype, flags in doctypes.items():
			if not frappe.db.exists(
				"Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0}
			):
				add_permission(doctype, role, 0)
			for flag in flags:
				for ptype in _FLAG_TO_PTYPE[flag]:
					update_permission_property(doctype, role, 0, ptype, 1, validate=False)


def after_migrate():
	ensure_roles()
	ensure_erpnext_permissions()
