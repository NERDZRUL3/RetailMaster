"""Recovery codes: owners can get back in without email or the server;
codes are single use, hashed, and useless to anyone else."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils.password import check_password

from retail_management.api import recovery
from retail_management.setup import ROLE_CASHIER, ROLE_OWNER, ensure_roles
from retail_management.tests.test_shop_permissions import make_user

NEW_PASSWORD = "Lanterne-Rivage-4827"
OTHER_PASSWORD = "Boussole-Falaise-9153"


class TestRecoveryApi(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_roles()
		cls.owner = make_user("rm_recovery_owner@example.com", ROLE_OWNER)
		cls.cashier = make_user("rm_recovery_cashier@example.com", ROLE_CASHIER)
		frappe.db.set_value("User", cls.owner, "username", "rm_recovery_owner")

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete(recovery.DOCTYPE, {"user": ("in", [self.owner, self.cashier])})

	def tearDown(self):
		frappe.set_user("Administrator")

	def _codes(self, user: str) -> list[str]:
		frappe.set_user(user)
		codes = recovery.generate_codes()["codes"]
		frappe.set_user("Guest")
		return codes

	def test_owner_gets_ten_distinct_codes_stored_only_as_hashes(self):
		codes = self._codes(self.owner)
		self.assertEqual(len(set(codes)), 10)
		stored = frappe.get_all(recovery.DOCTYPE, {"user": self.owner}, pluck="code_hash")
		self.assertEqual(len(stored), 10)
		for code in codes:
			self.assertNotIn(code, stored)
			self.assertNotIn(recovery._normalise(code), stored)

	def test_cashier_cannot_hold_codes(self):
		frappe.set_user(self.cashier)
		with self.assertRaises(frappe.PermissionError):
			recovery.generate_codes()
		with self.assertRaises(frappe.PermissionError):
			recovery.get_status()

	def test_code_sets_new_password_once(self):
		code = self._codes(self.owner)[0]
		# Lower case and without dashes is accepted, as typed from paper.
		result = recovery.reset_with_code(self.owner, code.lower().replace("-", " "), NEW_PASSWORD)
		self.assertEqual(result["remaining"], 9)
		self.assertEqual(check_password(self.owner, NEW_PASSWORD, delete_tracker_cache=False), self.owner)
		with self.assertRaises(frappe.AuthenticationError):
			recovery.reset_with_code(self.owner, code, OTHER_PASSWORD)

	def test_username_works_as_account(self):
		code = self._codes(self.owner)[1]
		recovery.reset_with_code("rm_recovery_owner", code, NEW_PASSWORD)
		self.assertEqual(check_password(self.owner, NEW_PASSWORD, delete_tracker_cache=False), self.owner)

	def test_wrong_code_or_other_account_is_refused_the_same_way(self):
		code = self._codes(self.owner)[0]
		for account, attempt in (
			(self.owner, "AAAA-BBBB-CCCC"),
			(self.cashier, code),
			("nobody@example.com", code),
			(self.owner, ""),
		):
			with self.assertRaises(frappe.AuthenticationError):
				recovery.reset_with_code(account, attempt, NEW_PASSWORD)
		self.assertEqual(frappe.db.count(recovery.DOCTYPE, {"user": self.owner, "used_on": ("is", "set")}), 0)

	def test_weak_password_does_not_use_up_the_code(self):
		code = self._codes(self.owner)[0]
		with self.assertRaises(frappe.ValidationError):
			recovery.reset_with_code(self.owner, code, "short")
		recovery.reset_with_code(self.owner, code, NEW_PASSWORD)

	def test_new_set_cancels_the_old_one(self):
		old = self._codes(self.owner)[0]
		self._codes(self.owner)
		with self.assertRaises(frappe.AuthenticationError):
			recovery.reset_with_code(self.owner, old, NEW_PASSWORD)

	def test_disabled_owner_cannot_use_codes(self):
		code = self._codes(self.owner)[0]
		frappe.set_user("Administrator")
		frappe.db.set_value("User", self.owner, "enabled", 0)
		try:
			frappe.set_user("Guest")
			with self.assertRaises(frappe.AuthenticationError):
				recovery.reset_with_code(self.owner, code, NEW_PASSWORD)
		finally:
			frappe.set_user("Administrator")
			frappe.db.set_value("User", self.owner, "enabled", 1)

	def test_options_is_open_to_guests(self):
		frappe.set_user("Guest")
		self.assertIn("email", recovery.options())
