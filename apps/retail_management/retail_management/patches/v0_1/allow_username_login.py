import frappe


def execute():
	"""Staff may sign in with the username the owner gives them (Team page)
	as well as with their email. Runs once; the setting stays editable in
	System Settings."""
	frappe.db.set_single_value("System Settings", "allow_login_using_user_name", 1)
