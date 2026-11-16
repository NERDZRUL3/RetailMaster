import frappe
from frappe.tests import IntegrationTestCase


class TestInstall(IntegrationTestCase):
	def test_app_is_installed(self):
		self.assertIn("retail_management", frappe.get_installed_apps())

	def test_erpnext_is_installed(self):
		self.assertIn("erpnext", frappe.get_installed_apps())

	def test_module_is_registered(self):
		self.assertTrue(frappe.db.exists("Module Def", "Retail Management"))
