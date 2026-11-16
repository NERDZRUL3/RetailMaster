import frappe
from frappe import _
from frappe.model.document import Document

# Changing any of these changes what the shop's users may see in ERPNext.
SCOPE_FIELDS = ("company", "warehouse", "pos_profile")


class RetailShop(Document):
	def validate(self):
		if not self.warehouse:
			self.warehouse = create_shop_warehouse(self.shop_name, self.company)
		self.validate_company_scope("Warehouse", self.warehouse)
		self.validate_company_scope("POS Profile", self.pos_profile)
		self.validate_not_shared("warehouse")
		self.validate_not_shared("pos_profile")

	def on_update(self):
		before = self.get_doc_before_save()
		if before and any(before.get(field) != self.get(field) for field in SCOPE_FIELDS):
			from retail_management.services.shop_access import sync_shop_users

			sync_shop_users(self.name)

	def validate_company_scope(self, doctype: str, name: str | None):
		"""A shop's warehouse and POS profile must belong to the shop's company."""
		if not name:
			return
		company = frappe.db.get_value(doctype, name, "company")
		if company != self.company:
			frappe.throw(
				_("{0} {1} belongs to company {2}, not {3}.").format(
					_(doctype), name, company, self.company
				)
			)

	def validate_not_shared(self, fieldname: str):
		"""Each shop needs its own warehouse and POS profile, otherwise staff of
		one shop would see the other shop's stock and sales."""
		value = self.get(fieldname)
		if not value:
			return
		other = frappe.db.get_value("Retail Shop", {fieldname: value, "name": ("!=", self.name)}, "name")
		if other:
			frappe.throw(
				_("{0} is already used by shop {1}. Each shop needs its own.").format(value, other)
			)


def create_shop_warehouse(shop_name: str, company: str) -> str:
	"""Create (or reuse an unused) stock warehouse for a new shop."""
	abbr = frappe.get_cached_value("Company", company, "abbr")
	existing = f"{shop_name} - {abbr}"
	if frappe.db.exists("Warehouse", {"name": existing, "company": company, "is_group": 0}):
		return existing

	root = frappe.db.get_value(
		"Warehouse", {"company": company, "is_group": 1, "parent_warehouse": ("is", "not set")}, "name"
	)
	warehouse = frappe.get_doc(
		{
			"doctype": "Warehouse",
			"warehouse_name": shop_name,
			"company": company,
			"parent_warehouse": root,
		}
	).insert(ignore_permissions=True)
	return warehouse.name
