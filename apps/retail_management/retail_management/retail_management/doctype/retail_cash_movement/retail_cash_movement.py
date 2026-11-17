import frappe
from frappe import _
from frappe.model.document import Document


class RetailCashMovement(Document):
	"""Cash put into or taken out of a till during a session (float top-up,
	paying a supplier from the drawer, bank drop). Recorded by
	retail_management.api.till and counted in the session's expected cash.
	Records are never edited."""

	def validate(self):
		if not self.is_new():
			frappe.throw(_("A cash movement cannot be changed."))
		if self.amount <= 0:
			frappe.throw(_("The amount must be more than zero."))
