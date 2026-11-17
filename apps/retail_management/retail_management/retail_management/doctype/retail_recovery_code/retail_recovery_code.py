from frappe.model.document import Document


class RetailRecoveryCode(Document):
	"""One single-use recovery code of an owner, stored only as a hash.
	Created and used by retail_management.api.recovery; never edited."""
