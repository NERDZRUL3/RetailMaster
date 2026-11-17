"""Team accounts: the owner creates and changes staff accounts; nobody can
lock the business out, touch administrators or hand out admin rights."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils.password import check_password

from retail_management.api import users
from retail_management.setup import ROLE_MANAGER, ROLE_OWNER, ROLE_PARTNER, ensure_erpnext_permissions, ensure_roles
from retail_management.tests.test_shop_permissions import make_user
from retail_management.tests.test_shop_stock_scoping import BUSINESS, SHOP_A, SHOP_B, get_company, make_shop

STRONG = "Plume-Cahier-7319"
NEW_EMAIL = "rm_team_new@example.com"
RENAMED = "rm_team_renamed@example.com"


def remove_user(email: str):
	if frappe.db.exists("User", email):
		for name in frappe.get_all("Retail Shop Access", filters={"user": email}, pluck="name"):
			frappe.delete_doc("Retail Shop Access", name, ignore_permissions=True, force=True)
		frappe.delete_doc("User", email, ignore_permissions=True, force=True)


class TestUsersApi(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_roles()
		ensure_erpnext_permissions()
		company = get_company()
		if not frappe.db.exists("Retail Business", BUSINESS):
			frappe.get_doc({"doctype": "Retail Business", "business_name": BUSINESS}).insert(
				ignore_permissions=True
			)
		make_shop(SHOP_A, company)
		make_shop(SHOP_B, company)
		cls.owner = make_user("rm_team_owner@example.com", ROLE_OWNER)
		cls.partner = make_user("rm_team_partner@example.com", ROLE_PARTNER)
		cls.manager = make_user("rm_team_manager@example.com", ROLE_MANAGER)
		cls.admin = make_user("rm_team_sysmgr@example.com", ROLE_OWNER)
		frappe.get_doc("User", cls.admin).add_roles("System Manager")

	def setUp(self):
		frappe.set_user("Administrator")
		for email in (NEW_EMAIL, RENAMED):
			remove_user(email)

	def tearDown(self):
		frappe.set_user("Administrator")

	def as_user(self, user: str):
		frappe.clear_cache(user=user)
		frappe.set_user(user)

	def create(self, **extra) -> dict:
		data = {
			"email": NEW_EMAIL,
			"first_name": "Nadia",
			"last_name": "Test",
			"tier": "cashier",
			"shops": [SHOP_A],
			"password": STRONG,
		}
		data.update(extra)
		return users.save_user(data)

	def test_owner_creates_and_changes_an_account(self):
		self.as_user(self.owner)
		account = self.create(username="nadia.t")
		self.assertEqual((account["tier"], account["shops"], account["username"]), ("cashier", [SHOP_A], "nadia.t"))
		self.assertEqual(check_password(NEW_EMAIL, STRONG), NEW_EMAIL)
		self.assertIn(NEW_EMAIL, [u["name"] for u in users.get_users()["users"]])

		changed = users.save_user(
			{
				"name": NEW_EMAIL,
				"email": RENAMED,
				"first_name": "Nadia",
				"tier": "manager",
				"shops": [SHOP_A, SHOP_B],
				"username": "nadia.m",
				"password": "Encre-Agrafe-2468",
				"enabled": 1,
			}
		)
		self.assertEqual(changed["name"], RENAMED)
		self.assertEqual(
			(changed["tier"], sorted(changed["shops"]), changed["username"]),
			("manager", sorted([SHOP_A, SHOP_B]), "nadia.m"),
		)
		roles = set(frappe.get_roles(RENAMED))
		self.assertIn(ROLE_MANAGER, roles)
		self.assertNotIn("Retail Cashier", roles)
		self.assertEqual(check_password(RENAMED, "Encre-Agrafe-2468"), RENAMED)

		off = users.save_user({**changed, "password": "", "enabled": 0})
		self.assertEqual(off["enabled"], 0)
		# Owners have every shop: their shop list is emptied.
		promoted = users.save_user({**off, "tier": "owner", "enabled": 1})
		self.assertEqual(promoted["shops"], [])

	def test_bad_input_refused(self):
		self.as_user(self.owner)
		with self.assertRaises(frappe.ValidationError):
			self.create(password="1234")  # weak
		with self.assertRaises(frappe.ValidationError):
			self.create(password="")  # a new account needs one
		with self.assertRaises(frappe.ValidationError):
			self.create(shops=[])  # cashier without a shop
		with self.assertRaises(frappe.ValidationError):
			self.create(email=self.manager)  # email taken
		with self.assertRaises(frappe.ValidationError):
			self.create(tier="System Manager")
		self.create(username="taken.name")
		with self.assertRaises(frappe.ValidationError):
			self.create(email=RENAMED, username="taken.name")

	def test_no_lockout(self):
		self.as_user(self.owner)
		me = next(u for u in users.get_users()["users"] if u["me"])
		with self.assertRaises(frappe.ValidationError):
			users.save_user({**me, "enabled": 0})
		with self.assertRaises(frappe.ValidationError):
			users.save_user({**me, "tier": "partner"})

	def test_administrators_off_limits(self):
		self.as_user(self.owner)
		listed = [u["name"] for u in users.get_users()["users"]]
		self.assertNotIn(self.admin, listed)
		self.assertNotIn("Administrator", listed)
		with self.assertRaises(frappe.PermissionError):
			users.save_user({"name": self.admin, "email": self.admin, "first_name": "X", "tier": "owner"})

	def test_only_owner(self):
		for user in (self.partner, self.manager):
			self.as_user(user)
			with self.assertRaises(frappe.PermissionError):
				users.get_users()
			with self.assertRaises(frappe.PermissionError):
				self.create()
