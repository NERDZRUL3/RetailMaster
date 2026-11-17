"""Product categories: groups and subgroups can be created, renamed, moved and
deleted (when empty), by owners and managers only."""

import frappe
from frappe.tests import IntegrationTestCase

from retail_management.api import categories
from retail_management.setup import (
	ROLE_CASHIER,
	ROLE_MANAGER,
	ROLE_OWNER,
	ROLE_PARTNER,
	ensure_erpnext_permissions,
	ensure_roles,
)
from retail_management.tests.test_shop_permissions import make_user


def unique(prefix: str) -> str:
	return f"{prefix} {frappe.generate_hash(length=5).upper()}"


class TestCategoriesApi(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_roles()
		ensure_erpnext_permissions()
		cls.owner = make_user("rm_cat_owner@example.com", ROLE_OWNER)
		cls.manager = make_user("rm_cat_manager@example.com", ROLE_MANAGER)
		cls.partner = make_user("rm_cat_partner@example.com", ROLE_PARTNER)
		cls.cashier = make_user("rm_cat_cashier@example.com", ROLE_CASHIER)

	def tearDown(self):
		frappe.set_user("Administrator")

	def as_user(self, user: str):
		frappe.clear_cache(user=user)
		frappe.set_user(user)

	def tree(self) -> dict:
		return {g["name"]: [c["name"] for c in g["children"]] for g in categories.get_categories()["groups"]}

	def test_group_and_subgroup(self):
		self.as_user(self.owner)
		group = categories.save_category(unique("Paper"))["name"]
		sub = categories.save_category(unique("A4"), parent=group)["name"]
		self.assertIn(sub, self.tree()[group])
		self.assertEqual(frappe.db.get_value("Item Group", group, "is_group"), 1)
		with self.assertRaises(frappe.ValidationError):
			categories.save_category(unique("Too deep"), parent=sub)

	def test_rename_keeps_products(self):
		self.as_user(self.manager)
		group = categories.save_category(unique("Pens"))["name"]
		frappe.set_user("Administrator")
		item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": unique("_RM-CAT"),
				"item_name": "Category test pen",
				"item_group": group,
				"stock_uom": "Nos",
			}
		).insert()
		self.as_user(self.manager)
		new_name = unique("Writing")
		renamed = categories.save_category(new_name, name=group)["name"]
		self.assertEqual(renamed, new_name)
		self.assertEqual(frappe.db.get_value("Item", item.name, "item_group"), new_name)
		with self.assertRaises(frappe.ValidationError):
			categories.delete_category(new_name)  # still has a product

	def test_move_and_delete(self):
		self.as_user(self.owner)
		first = categories.save_category(unique("Files"))["name"]
		second = categories.save_category(unique("Folders"))["name"]
		sub = categories.save_category(unique("Binders"), parent=first)["name"]
		categories.save_category(sub, name=sub, parent=second)
		tree = self.tree()
		self.assertIn(sub, tree[second])
		self.assertNotIn(sub, tree[first])
		# first lost its only subgroup: it can hold products directly again
		self.assertEqual(frappe.db.get_value("Item Group", first, "is_group"), 0)
		categories.delete_category(sub)
		self.assertFalse(frappe.db.exists("Item Group", sub))
		self.assertEqual(frappe.db.get_value("Item Group", second, "is_group"), 0)

	def test_partner_and_cashier_cannot_change(self):
		self.as_user(self.partner)
		self.assertTrue(categories.get_categories()["groups"])
		with self.assertRaises(frappe.PermissionError):
			categories.save_category(unique("Nope"))
		self.as_user(self.cashier)
		with self.assertRaises(frappe.PermissionError):
			categories.get_categories()
