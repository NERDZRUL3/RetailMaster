import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class RetailBackupSettings(Document):
	def validate(self):
		if not 0 <= cint(self.backup_hour) <= 23:
			frappe.throw(_("The hour must be between 0 and 23."))
		self.keep_on_drive = max(1, cint(self.keep_on_drive) or 14)
		self.keep_on_server = max(1, cint(self.keep_on_server) or 3)
		self.drive_folder = (self.drive_folder or "").strip() or "RetailMaster backups"
		if self.has_value_changed("drive_folder"):
			self.drive_folder_id = None
