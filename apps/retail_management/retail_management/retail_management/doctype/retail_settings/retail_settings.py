import re

import frappe
from frappe import _
from frappe.model.document import Document

LANGUAGES = ("en", "fr", "ar")
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")

# White text on buttons needs 4.5:1 contrast (WCAG AA for normal text).
MIN_CONTRAST_WITH_WHITE = 4.5


def _relative_luminance(color: str) -> float:
	def channel(value: int) -> float:
		c = value / 255
		return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

	red, green, blue = (int(color[i : i + 2], 16) for i in (1, 3, 5))
	return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue)


def contrast_with_white(color: str) -> float:
	"""WCAG contrast ratio between a #rrggbb colour and white."""
	return 1.05 / (_relative_luminance(color) + 0.05)


def readable_shade(color: str) -> str:
	"""The brand colour itself if white text is readable on it, otherwise the
	lightest darker shade of it that is.

	Brand colours stay exactly as the customer chose them for logos and
	accents; only surfaces that carry white text use this shade.
	"""
	if contrast_with_white(color) >= MIN_CONTRAST_WITH_WHITE:
		return color.lower()

	red, green, blue = (int(color[i : i + 2], 16) for i in (1, 3, 5))
	for step in range(1, 101):
		factor = 1 - step / 100
		shade = "#{:02x}{:02x}{:02x}".format(
			round(red * factor), round(green * factor), round(blue * factor)
		)
		if contrast_with_white(shade) >= MIN_CONTRAST_WITH_WHITE:
			return shade
	return "#000000"


class RetailSettings(Document):
	"""Per-site (per-customer) settings for the custom interface."""

	def validate(self):
		self.validate_brand_color()
		self.validate_languages()

	def enabled_languages(self) -> list[str]:
		return [language for language in LANGUAGES if self.get(f"enable_{language}")]

	def validate_brand_color(self):
		if not self.brand_color:
			return
		if not HEX_COLOR.match(self.brand_color):
			frappe.throw(_("Brand colour must be a hex colour such as #0f766e."))
		self.brand_color = self.brand_color.lower()

	def validate_languages(self):
		enabled = self.enabled_languages()
		if not enabled:
			frappe.throw(_("Enable at least one language."))
		if self.default_language not in enabled:
			frappe.throw(_("The default language must be one of the enabled languages."))
