import frappe
from frappe.utils import getdate

TEST_COMPANY = "_RM Test Company"


def before_tests():
	"""Prepare a fresh site for tests (before_tests hook).

	A new ERPNext site has no company, fiscal year or stock defaults until
	the setup wizard has run. This completes the wizard once with synthetic
	Moroccan defaults. It does nothing on a site that is already set up.

	Accounting and tax settings here are placeholders for tests only; the
	real configuration must come from the accountant.
	"""
	if frappe.is_setup_complete():
		return

	from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

	year = getdate().year
	setup_complete(
		{
			"language": "English",
			"country": "Morocco",
			"timezone": "Africa/Casablanca",
			"currency": "MAD",
			"company_name": TEST_COMPANY,
			"company_abbr": "_RMT",
			"chart_of_accounts": "Standard",
			"fy_start_date": f"{year}-01-01",
			"fy_end_date": f"{year}-12-31",
			"enable_telemetry": 0,
		}
	)
	frappe.db.commit()  # nosemgrep: test bootstrap must persist before tests start
	frappe.clear_cache()
