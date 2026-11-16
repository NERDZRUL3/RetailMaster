"""Branding of the custom interface, read from Retail Settings.

Each customer runs their own Frappe site, so Retail Settings is per customer.
Nothing here may be specific to one business: every value has a neutral
default and can be changed without touching code.
"""

import frappe

from retail_management.retail_management.doctype.retail_settings.retail_settings import (
	LANGUAGES,
	readable_shade,
)

DEFAULT_APP_NAME = "Retail Manager"
DEFAULT_BRAND_COLOR = "#0f766e"


def get_branding() -> dict:
	"""Public branding. Safe to show to signed-out visitors on the login page."""
	settings = frappe.get_cached_doc("Retail Settings")

	# A site whose settings were never saved has no languages ticked: treat
	# that as "all languages". Saved settings always have at least one.
	languages = settings.enabled_languages() or list(LANGUAGES)
	default_language = (
		settings.default_language if settings.default_language in languages else languages[0]
	)

	# Only public files can be shown before sign-in.
	logo = settings.logo if settings.logo and settings.logo.startswith("/files/") else None
	brand_color = settings.brand_color or DEFAULT_BRAND_COLOR

	return {
		"app_name": settings.app_name or DEFAULT_APP_NAME,
		"logo": logo,
		# Exactly as chosen: logo-matching accents, borders, rings.
		"brand_color": brand_color,
		# Same hue, darkened only if needed so white text on it stays readable.
		"brand_color_strong": readable_shade(brand_color),
		"default_language": default_language,
		"languages": languages,
	}
