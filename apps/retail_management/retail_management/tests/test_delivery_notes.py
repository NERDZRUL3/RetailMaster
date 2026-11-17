"""Delivery notes from a PDF: reading (text layer and OCR), matching products
and supplier, receiving the reviewed note into the right shop once, invoicing
it later without moving stock again, shop scoping."""

import io
import shutil
import unittest

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, formatdate, getdate, nowdate

from retail_management.api import delivery_notes, purchasing
from retail_management.setup import ROLE_CASHIER, ROLE_MANAGER, ROLE_OWNER, ensure_erpnext_permissions, ensure_roles
from retail_management.tests.test_inventory_api import grant
from retail_management.tests.test_shop_permissions import make_user
from retail_management.tests.test_shop_stock_scoping import BUSINESS, SHOP_A, SHOP_B, get_company, make_shop

GLUE = "_RM-DN-GLUE"
GLUE_BARCODE = "6111000000017"
TAPE = "_RM-DN-TAPE"
SUPPLIER = "_RM Delivery Supplier"


def text_pdf(lines: list[str]) -> bytes:
	"""A one-page PDF with a real text layer (ASCII only), built by hand."""
	escape = lambda s: s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")  # noqa: E731
	content = "BT /F1 11 Tf 40 800 Td 16 TL " + " ".join(f"({escape(line)}) Tj T*" for line in lines) + " ET"
	objects = [
		"<< /Type /Catalog /Pages 2 0 R >>",
		"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
		"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
		"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
		"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
		f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
	]
	out, offsets = b"%PDF-1.4\n", []
	for number, body in enumerate(objects, 1):
		offsets.append(len(out))
		out += f"{number} 0 obj\n{body}\nendobj\n".encode("ascii")
	xref = len(out)
	out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
	out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
	out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
	return out


def scanned_pdf(lines: list[str]) -> bytes:
	"""A PDF that is only a picture of the page (no text layer), like a scan."""
	from PIL import Image, ImageDraw, ImageFont

	image = Image.new("L", (1700, 1100), 255)
	draw = ImageDraw.Draw(image)
	font = ImageFont.load_default(size=40)
	for index, line in enumerate(lines):
		draw.text((80, 80 + index * 70), line, fill=0, font=font)
	buffer = io.BytesIO()
	image.save(buffer, "PDF", resolution=200)
	return buffer.getvalue()


class TestDeliveryNotes(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_roles()
		ensure_erpnext_permissions()
		cls.company = get_company()
		if not frappe.db.exists("Retail Business", BUSINESS):
			frappe.get_doc({"doctype": "Retail Business", "business_name": BUSINESS}).insert(ignore_permissions=True)
		make_shop(SHOP_A, cls.company)
		make_shop(SHOP_B, cls.company)
		cls.wh_a = frappe.db.get_value("Retail Shop", SHOP_A, "warehouse")
		cls.owner = make_user("rm_dn_owner@example.com", ROLE_OWNER)
		cls.manager = make_user("rm_dn_manager@example.com", ROLE_MANAGER)
		cls.cashier = make_user("rm_dn_cashier@example.com", ROLE_CASHIER)
		grant(cls.manager, SHOP_A)
		grant(cls.cashier, SHOP_A)
		group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
		for code, name, barcode in ((GLUE, "Delivery glue stick", GLUE_BARCODE), (TAPE, "Delivery packing tape", None)):
			if not frappe.db.exists("Item", code):
				frappe.get_doc(
					{
						"doctype": "Item",
						"item_code": code,
						"item_name": name,
						"item_group": group,
						"stock_uom": "Nos",
						"is_stock_item": 1,
						"barcodes": [{"barcode": barcode}] if barcode else [],
					}
				).insert(ignore_permissions=True)
		frappe.set_user(cls.owner)
		cls.supplier = frappe.db.get_value("Supplier", {"supplier_name": SUPPLIER}, "name") or purchasing.save_supplier(
			{"supplier_name": SUPPLIER}
		)["name"]
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def as_user(self, user: str):
		frappe.clear_cache(user=user)
		frappe.set_user(user)

	def stock(self, item: str) -> float:
		return flt(frappe.db.get_value("Bin", {"item_code": item, "warehouse": self.wh_a}, "actual_qty"))

	def note_lines(self, reference: str) -> list[str]:
		day = formatdate(add_days(nowdate(), -2), "dd/MM/yyyy")
		return [
			SUPPLIER,
			"12 rue du Commerce, Casablanca - Tel 0522 000000",
			f"Bon de livraison No {reference}",
			f"Date : {day}",
			"Ref  Designation  Qte  PU  Montant",
			f"{GLUE_BARCODE}  Glue stick 21g  24  1,50  36,00",
			"Delivery packing tape brown  10",
			"Mystery widget blue  5",
			"Total HT  51,00",
		]

	def test_parse_text(self):
		self.as_user(self.manager)
		reference = f"BL-{frappe.generate_hash(length=6).upper()}"
		draft = delivery_notes.read_content(text_pdf(self.note_lines(reference)), "bl.pdf")
		self.assertEqual(draft["method"], "text")
		self.assertEqual(draft["supplier"], self.supplier)
		self.assertEqual(draft["reference"], reference)
		self.assertEqual(draft["date"], add_days(nowdate(), -2))
		lines = {row["item_code"]: row for row in draft["lines"]}
		self.assertEqual((lines[GLUE]["qty"], lines[GLUE]["rate"]), (24, 1.5))  # barcode, qty x cost = amount
		self.assertEqual((lines[TAPE]["qty"], lines[TAPE]["rate"]), (10, None))  # by name
		self.assertEqual([" ".join(row["raw"].split()) for row in draft["unmatched"]], ["Mystery widget blue 5"])
		self.assertTrue(frappe.db.get_value("File", draft["file"], "is_private"))

	def test_receive_then_invoice(self):
		self.as_user(self.manager)
		reference = f"BL-{frappe.generate_hash(length=6).upper()}"
		draft = delivery_notes.read_content(text_pdf(self.note_lines(reference)), "bl.pdf")
		before = self.stock(GLUE), self.stock(TAPE)
		note = {
			"supplier": draft["supplier"],
			"shop": SHOP_A,
			"reference": draft["reference"],
			"file": draft["file"],
			"lines": [{"item_code": row["item_code"], "qty": row["qty"], "rate": row["rate"]} for row in draft["lines"]],
		}
		request = frappe.generate_hash(length=12)
		received = delivery_notes.receive_delivery_note(note, request_id=request)
		again = delivery_notes.receive_delivery_note(note, request_id=request)
		self.assertEqual(received["receipt"], again["receipt"])  # same request: received once
		self.assertEqual((self.stock(GLUE), self.stock(TAPE)), (before[0] + 24, before[1] + 10))
		self.assertEqual((received["bill_no"], received["invoice"], received["billed"]), (reference, None, False))
		self.assertTrue(received["attachment"])
		with self.assertRaises(frappe.ValidationError):  # the same note twice
			delivery_notes.receive_delivery_note(note)

		bill_no = f"FA-{frappe.generate_hash(length=6)}"
		billed = purchasing.invoice_receipt(received["receipt"], bill_no, nowdate())
		self.assertEqual((billed["bill_no"], billed["billed"]), (bill_no, True))
		self.assertEqual((self.stock(GLUE), self.stock(TAPE)), (before[0] + 24, before[1] + 10))  # no second receipt
		with self.assertRaises(frappe.ValidationError):
			purchasing.invoice_receipt(received["receipt"], f"{bill_no}-2", nowdate())

	def test_against_order_with_extra(self):
		self.as_user(self.owner)
		order = purchasing.save_order(
			{
				"supplier": self.supplier,
				"shop": SHOP_A,
				"expected": add_days(nowdate(), 3),
				"lines": [{"item_code": TAPE, "qty": 8, "rate": 4}],
			},
			submit=1,
		)
		reference = f"BL-{frappe.generate_hash(length=6).upper()}"
		draft = delivery_notes.read_content(text_pdf(self.note_lines(reference)), "bl.pdf")
		self.assertEqual(draft["order"], order["name"])  # the open order for these products
		received = delivery_notes.receive_delivery_note(
			{
				"supplier": self.supplier,
				"shop": SHOP_A,
				"order": draft["order"],
				"reference": reference,
				"lines": [{"item_code": TAPE, "qty": 10}],
			}
		)
		self.assertEqual(purchasing.get_order(order["name"])["status"], "received")
		self.assertEqual(received["orders"], [order["name"]])
		receipt = frappe.get_doc("Purchase Receipt", received["receipt"])
		rows = sorted((flt(row.qty), flt(row.rate), bool(row.purchase_order)) for row in receipt.items)
		self.assertEqual(rows, [(2, 4, False), (8, 4, True)])  # 8 against the order, 2 more at the order's cost

	@unittest.skipUnless(shutil.which("tesseract"), "Tesseract is not installed")
	def test_scanned_pdf(self):
		self.as_user(self.owner)
		reference = f"BL-{frappe.generate_hash(length=4).upper()}7"
		draft = delivery_notes.read_content(scanned_pdf(self.note_lines(reference)), "scan.pdf")
		self.assertEqual(draft["method"], "ocr")
		self.assertEqual(draft["supplier"], self.supplier)
		lines = {row["item_code"]: row["qty"] for row in draft["lines"]}
		self.assertEqual(lines.get(GLUE), 24)
		self.assertEqual(lines.get(TAPE), 10)

	def test_scoping(self):
		self.as_user(self.manager)
		with self.assertRaises(frappe.PermissionError):
			delivery_notes.receive_delivery_note(
				{"supplier": self.supplier, "shop": SHOP_B, "reference": "BL-X", "lines": [{"item_code": GLUE, "qty": 1}]}
			)
		self.as_user(self.cashier)
		with self.assertRaises(frappe.PermissionError):
			delivery_notes.read_content(text_pdf(["x"]), "x.pdf")

	def test_rejects_other_files(self):
		self.as_user(self.owner)
		with self.assertRaises(frappe.ValidationError):
			delivery_notes.read_content(b"not a pdf at all", "x.txt")
		self.assertIsNone(delivery_notes.find_date("Date : 01/01/2001"))  # too old
		self.assertEqual(getdate(delivery_notes.find_date(f"Date {nowdate()}")), getdate(nowdate()))
