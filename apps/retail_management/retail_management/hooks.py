app_name = "retail_management"
app_title = "Retail Management"
app_publisher = "Nerdoz Retail"
app_description = "Retail management for multi-shop businesses on ERPNext"
app_email = "admin@example.com"
app_license = "gpl-3.0"

# ERPNext provides the accounting, stock and POS engine this app builds on.
required_apps = ["erpnext"]

# Tile on the desk's home (/desk): opens the Retail workspace with shops,
# staff shop access and settings. Owners, partners and system managers only.
add_to_apps_screen = [
	{
		"name": app_name,
		"logo": "/assets/retail_management/images/retail-logo.svg",
		"title": "Retail",
		"route": "/desk/retail",
		"has_permission": "retail_management.services.permissions.can_open_desk_app",
		"sequence_id": 2,
	}
]

# Roles must exist before the DocTypes that reference them are synced.
before_install = "retail_management.setup.ensure_roles"
after_install = "retail_management.setup.after_migrate"
after_migrate = ["retail_management.setup.after_migrate"]

# Completes the ERPNext setup wizard on a fresh site before tests run.
before_tests = "retail_management.tests.utils.before_tests"

# The custom interface is a single-page app: every /retail/... path serves www/retail.html.
website_route_rules = [
	{"from_route": "/retail/<path:app_path>", "to_route": "retail"},
]

# Shop scoping. See services/permissions.py.
# Shop-linked ERPNext doctypes: a shop-scoped user with no shop sees none of
# them (otherwise "no User Permissions" would mean "no restriction").
_SHOP_LINKED_DOCTYPES = (
	"Warehouse",
	"Bin",
	"Stock Ledger Entry",
	"Stock Entry",
	"Stock Reconciliation",
	"Material Request",
	"Purchase Order",
	"Purchase Receipt",
	"Purchase Invoice",
	"Delivery Note",
	"Sales Invoice",
	"POS Invoice",
	"POS Profile",
	"POS Opening Entry",
	"POS Closing Entry",
)
_NO_SHOP = "retail_management.services.permissions"

permission_query_conditions = {
	"Retail Shop": f"{_NO_SHOP}.shop_query_conditions",
	**{doctype: f"{_NO_SHOP}.no_shop_query_conditions" for doctype in _SHOP_LINKED_DOCTYPES},
}
has_permission = {
	"Retail Shop": f"{_NO_SHOP}.shop_has_permission",
	**{doctype: f"{_NO_SHOP}.no_shop_has_permission" for doctype in _SHOP_LINKED_DOCTYPES},
}

# ERPNext documents are scoped per shop through User Permissions on Company,
# Warehouse and POS Profile. See services/shop_access.py.
doc_events = {
	"User": {"on_update": "retail_management.services.shop_access.on_user_update"},
	"Purchase Receipt": {
		"before_validate": "retail_management.api.purchasing.clear_default_rejected_warehouse"
	},
}

# Timed whole-site backups (Backups page in the desk). Checked every hour on the
# long queue; runs when the chosen day and hour come round.
scheduler_events = {
	"hourly_long": ["retail_management.services.backup.run_scheduled_backup"],
}
