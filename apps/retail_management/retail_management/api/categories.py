"""Product categories: groups and their subgroups.

They are ERPNext Item Groups. A group sits directly under the root ("All
Item Groups"); a subgroup sits under a group. Two levels keep the interface
simple; products can be in a group or in one of its subgroups. Changes run
with the signed-in user's own permissions on Item Group.
"""

import frappe
from frappe import _
from frappe.utils import cint

from retail_management.api.inventory import _require_inventory


def _root() -> str:
	root = frappe.db.get_value(
		"Item Group", {"is_group": 1, "parent_item_group": ("in", ("", None))}, "name", order_by="lft asc"
	)
	if not root:
		frappe.throw(_("No root product category exists."))
	return root


def _level(name: str, root: str) -> int:
	"""1 for a group, 2 for a subgroup, 0 for the root, 3+ deeper."""
	depth = 0
	while name and name != root and depth < 10:
		name = frappe.db.get_value("Item Group", name, "parent_item_group")
		depth += 1
	return depth


@frappe.whitelist()
def get_categories() -> dict:
	_require_inventory()
	root = _root()
	counts = {
		group: cint(count)
		for group, count in frappe.db.sql("select item_group, count(*) from `tabItem` group by item_group")
	}
	rows = frappe.get_list(
		"Item Group", fields=["name", "parent_item_group", "is_group"], order_by="lft asc", limit_page_length=0
	)
	groups = []
	by_name = {}
	for row in rows:
		if row.parent_item_group == root:
			entry = {"name": row.name, "items": counts.get(row.name, 0), "children": []}
			groups.append(entry)
			by_name[row.name] = entry
	for row in rows:
		parent = by_name.get(row.parent_item_group)
		if parent is not None:
			parent["children"].append({"name": row.name, "items": counts.get(row.name, 0)})
	groups.sort(key=lambda g: g["name"].lower())
	for group in groups:
		group["children"].sort(key=lambda c: c["name"].lower())
	return {
		"root": root,
		"groups": groups,
		"can_create": bool(frappe.has_permission("Item Group", "create")),
		"can_write": bool(frappe.has_permission("Item Group", "write")),
		"can_delete": bool(frappe.has_permission("Item Group", "delete")),
	}


def _clean_label(label: str) -> str:
	label = (label or "").strip()
	if not label:
		frappe.throw(_("Enter a name."))
	if len(label) > 140:
		frappe.throw(_("The name is too long."))
	return label


@frappe.whitelist(methods=["POST"])
def save_category(label: str, name: str | None = None, parent: str | None = None) -> dict:
	"""Create a category (no name) or rename/move one. parent empty = a
	top-level group, otherwise a subgroup of that group."""
	_require_inventory()
	root = _root()
	label = _clean_label(label)
	parent = parent or root
	if parent != root and _level(parent, root) != 1:
		frappe.throw(_("Subgroups can only be added to a group."))

	if not name:
		frappe.has_permission("Item Group", "create", throw=True)
		if frappe.db.exists("Item Group", label):
			frappe.throw(_("A category named {0} already exists.").format(label))
		_make_group_node(parent, root)
		doc = frappe.get_doc(
			{"doctype": "Item Group", "item_group_name": label, "parent_item_group": parent, "is_group": 0}
		).insert()
		return {"name": doc.name}

	frappe.has_permission("Item Group", "write", doc=name, throw=True)
	if name == root:
		frappe.throw(_("The root category cannot be changed."))
	doc = frappe.get_doc("Item Group", name)
	if parent != doc.parent_item_group:
		if parent == name:
			frappe.throw(_("A category cannot be inside itself."))
		if parent != root and frappe.db.exists("Item Group", {"parent_item_group": name}):
			frappe.throw(_("A group with subgroups cannot become a subgroup."))
		_make_group_node(parent, root)
		old_parent = doc.parent_item_group
		doc.parent_item_group = parent
		doc.save()
		_release_group_node(old_parent, root)
	if label != name:
		if frappe.db.exists("Item Group", label):
			frappe.throw(_("A category named {0} already exists.").format(label))
		name = frappe.rename_doc("Item Group", name, label, force=False)
		frappe.db.set_value("Item Group", name, "item_group_name", label)
	return {"name": name}


def _make_group_node(parent: str, root: str):
	"""ERPNext only nests under group nodes: turn a group into one when it
	gets its first subgroup. Its own products stay where they are."""
	if parent != root and not cint(frappe.db.get_value("Item Group", parent, "is_group")):
		doc = frappe.get_doc("Item Group", parent)
		doc.is_group = 1
		doc.save()


@frappe.whitelist(methods=["POST"])
def delete_category(name: str) -> dict:
	"""Delete an empty category (no products, no subgroups)."""
	_require_inventory()
	frappe.has_permission("Item Group", "delete", doc=name, throw=True)
	root = _root()
	if name == root:
		frappe.throw(_("The root category cannot be deleted."))
	if frappe.db.exists("Item", {"item_group": name}):
		frappe.throw(_("Move its products to another category first."))
	if frappe.db.exists("Item Group", {"parent_item_group": name}):
		frappe.throw(_("Delete or move its subgroups first."))
	parent = frappe.db.get_value("Item Group", name, "parent_item_group")
	frappe.delete_doc("Item Group", name)
	_release_group_node(parent, root)
	return {"deleted": name}


def _release_group_node(parent: str | None, root: str):
	"""A group whose last subgroup went away becomes a plain category again."""
	if parent and parent != root and not frappe.db.exists("Item Group", {"parent_item_group": parent}):
		frappe.db.set_value("Item Group", parent, "is_group", 0)
