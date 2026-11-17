"""Run a document-creating action once per request id.

A double click or a network retry sends the same request id again; the
second call then returns the first result instead of creating a second
document. Keys live in Redis for a day, per user and scope.
"""

from collections.abc import Callable

import frappe
from frappe import _

REQUEST_TTL = 24 * 3600


def run_once(scope: str, request_id: str, action: Callable[[], str], load: Callable[[str], dict]) -> dict:
	"""action() creates the document and returns its name; load(name) builds the reply."""
	request_id = (request_id or "").strip()[:64]
	if not request_id:
		return load(action())
	key = frappe.cache.make_key(f"retail_management:{scope}:{frappe.session.user}:{request_id}")
	if not frappe.cache.set(key, "pending", ex=REQUEST_TTL, nx=True):
		existing = frappe.safe_decode(frappe.cache.get(key) or b"")
		if existing and existing != "pending":
			return load(existing)
		frappe.throw(_("This is already being saved."))
	try:
		name = action()
	except Exception:
		frappe.cache.delete(key)
		raise
	frappe.cache.set(key, name, ex=REQUEST_TTL)
	return load(name)
