import frappe
from frappe import _
from frappe.model.document import Document

from retail_management.services.shop_access import sync_user_permissions


class RetailShopAccess(Document):
	def validate(self):
		duplicate = frappe.db.exists(
			"Retail Shop Access",
			{"user": self.user, "retail_shop": self.retail_shop, "name": ("!=", self.name)},
		)
		if duplicate:
			frappe.throw(
				_("{0} already has access to {1}.").format(self.user, self.retail_shop),
				frappe.DuplicateEntryError,
			)

	def on_update(self):
		sync_user_permissions(self.user)
		before = self.get_doc_before_save()
		if before and before.user != self.user:
			sync_user_permissions(before.user)

	def after_delete(self):
		sync_user_permissions(self.user)
