"""Supplier delivery notes from a PDF (or a photo): read, review, then receive.

read_delivery_note takes the uploaded file and reads its text: straight from
the PDF when it has a text layer, otherwise with Tesseract OCR on each page.
It then guesses the supplier, the note number and date, and the delivered
products (by barcode, code or name) with their quantities, and suggests the
supplier's open order. Nothing is posted: the user reviews the draft and
confirms.

receive_delivery_note posts the confirmed draft as one submitted Purchase
Receipt into the shop (against the order where it matches), with the file
attached. Stock goes up there and then. The supplier's invoice can be entered
later for that receipt (purchasing.invoice_receipt) without moving stock again.
Same roles and shop scoping as purchasing: owners and managers, managers only
for their own shops.
"""

import io
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
from difflib import SequenceMatcher

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from retail_management.api.inventory import _shops
from retail_management.api.purchasing import (
	BUY_ROLES,
	MAX_LINES,
	VIEW_ROLES,
	_receipt_summary,
	_require,
	_shop_of,
	free_line,
	get_item_costs,
	post_receipt,
	receiving_target,
)
from retail_management.services.idempotency import run_once
from retail_management.services.permissions import assert_shop_access

MAX_BYTES = 15 * 1024 * 1024
MAX_PAGES = 6
OCR_DPI = 300
OCR_TIMEOUT = 90  # seconds per page
MIN_TEXT_CHARS = 40  # fewer readable characters than this: the PDF is a scan
MAX_TEXT = 20000

# Lines that are headers, footers or totals, never a delivered product.
_NOISE = re.compile(
	r"\b(total|sous[- ]total|tva|vat|ht|ttc|net a payer|remise|date|tel|t[eé]l[eé]phone|fax|ice|r\.?c\b|"
	r"patente|i\.?f\b|cnss|page|client|adresse|address|livr[eé] par|re[cç]u par|signature|cachet|"
	r"bon de livraison|delivery note|facture|invoice|qt[eé]|quantit[eé]|d[eé]signation|r[eé]f[eé]rence|"
	r"prix|unit|montant|amount|description)\b",
	re.I,
)
_NUMBER = re.compile(r"(?<![\w.,/:-])\d+(?:[.,]\d{1,3})?(?![\w/:%-]|[.,]\d)")
_DATE = re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})\b|\b(\d{4})-(\d{2})-(\d{2})\b")
_REFERENCE = (
	re.compile(
		r"(?:bon\s+de\s+livraison|bordereau(?:\s+de\s+livraison)?|delivery\s+note|\bB\.?\s?L\b)\.?\s*"
		r"(?:n[°ºo]\.?|no\.?|num(?:[ée]ro)?\.?|#)?\s*[:.]?\s*([A-Z0-9][A-Z0-9/\-.]{1,30})",
		re.I,
	),
	re.compile(r"\b(BL[\s\-/]*\d[\w/\-]*)", re.I),
	re.compile(r"\bn[°º]\s*[:.]?\s*([A-Z0-9][A-Z0-9/\-]{1,30})", re.I),
)


# ---------------------------------------------------------------- reading the file
def _is_pdf(content: bytes) -> bool:
	return content[:5] == b"%PDF-"


def _pdf_text(content: bytes) -> str:
	import pdfplumber

	try:
		with pdfplumber.open(io.BytesIO(content)) as pdf:
			if len(pdf.pages) > MAX_PAGES:
				frappe.throw(_("A delivery note can have at most {0} pages.").format(MAX_PAGES))
			return "\n".join(page.extract_text() or "" for page in pdf.pages)
	except frappe.ValidationError:
		raise
	except Exception:
		frappe.throw(_("This PDF cannot be opened. Is it damaged or password protected?"))


def _tesseract() -> str:
	exe = shutil.which("tesseract")
	if not exe:
		frappe.throw(
			_(
				"This file is a scan, and this server cannot read scans yet (Tesseract is not installed). "
				"Ask your administrator, or enter the delivery by hand."
			)
		)
	return exe


def _ocr_images(images) -> str:
	exe = _tesseract()
	texts = []
	with tempfile.TemporaryDirectory() as tmp:
		for index, image in enumerate(images):
			path = os.path.join(tmp, f"page-{index}.png")
			image.convert("L").save(path)
			try:
				result = subprocess.run(
					[exe, path, "stdout", "-l", "fra+eng", "--psm", "6"],
					capture_output=True,
					timeout=OCR_TIMEOUT,
					check=False,
				)
			except subprocess.TimeoutExpired:
				frappe.throw(_("Reading the scan took too long. Try a smaller or clearer file."))
			texts.append(result.stdout.decode("utf-8", "replace"))
	return "\n".join(texts)


def _pdf_images(content: bytes):
	import pypdfium2 as pdfium

	pdf = pdfium.PdfDocument(content)
	try:
		if len(pdf) > MAX_PAGES:
			frappe.throw(_("A delivery note can have at most {0} pages.").format(MAX_PAGES))
		return [pdf[i].render(scale=OCR_DPI / 72).to_pil() for i in range(len(pdf))]
	finally:
		pdf.close()


def extract_text(content: bytes) -> tuple[str, str]:
	"""(text, method): method is "text" (PDF text layer) or "ocr" (Tesseract)."""
	if _is_pdf(content):
		text = _pdf_text(content)
		if len(re.sub(r"\s", "", text)) >= MIN_TEXT_CHARS:
			return text, "text"
		return _ocr_images(_pdf_images(content)), "ocr"
	from PIL import Image, UnidentifiedImageError

	try:
		image = Image.open(io.BytesIO(content))
		image.load()
	except (UnidentifiedImageError, OSError):
		frappe.throw(_("Send a PDF or a photo (JPG, PNG) of the delivery note."))
	return _ocr_images([image]), "ocr"


# ---------------------------------------------------------------- understanding the text
def _norm(text: str) -> str:
	text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
	return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _number(token: str) -> float:
	return flt(token.replace(",", "."))


def find_reference(text: str) -> str:
	for pattern in _REFERENCE:
		for match in pattern.finditer(text):
			value = match.group(1).strip(" .:-/")
			if any(ch.isdigit() for ch in value):
				return value[:140]
	return ""


def find_date(text: str) -> str | None:
	today = getdate(nowdate())
	found = []
	for line in text.splitlines():
		for match in _DATE.finditer(line):
			try:
				if match.group(4):
					year, month, day = int(match.group(4)), int(match.group(5)), int(match.group(6))
				else:
					day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
					year += 2000 if year < 100 else 0
				value = getdate(f"{year:04d}-{month:02d}-{day:02d}")
			except Exception:
				continue
			if value <= today and (today - value).days <= 730:
				found.append((0 if re.search(r"date|le\b|du\b", line, re.I) else 1, value))
	return str(min(found, key=lambda f: f[0])[1]) if found else None


def find_supplier(text: str, suppliers: list[dict]) -> str | None:
	norm_text = f" {_norm(text)} "
	best = None
	for row in suppliers:
		label = _norm(row["supplier_name"])
		if len(label) >= 3 and f" {label} " in norm_text and (not best or len(label) > len(best[1])):
			best = (row["name"], label)
	if best:
		return best[0]
	head = [_norm(line) for line in text.splitlines()[:15] if line.strip()]
	scored = [
		(SequenceMatcher(None, _norm(row["supplier_name"]), line).ratio(), row["name"])
		for row in suppliers
		for line in head
	]
	scored = [s for s in scored if s[0] >= 0.8]
	return max(scored)[1] if scored else None


def _catalogue() -> tuple[dict, list]:
	"""Code and barcode index, and (item, name words) for name matching."""
	items = frappe.get_all(
		"Item",
		filters={"disabled": 0, "is_stock_item": 1, "is_purchase_item": 1, "has_variants": 0},
		fields=["name", "item_name"],
		limit=20000,
	)
	by_code = {row.name.lower(): row for row in items}
	for barcode, parent in frappe.get_all(
		"Item Barcode", filters={"parenttype": "Item"}, fields=["barcode", "parent"], as_list=True
	):
		item = by_code.get((parent or "").lower())
		if item and barcode:
			by_code[barcode.lower()] = item
	named = []
	for row in items:
		words = [w for w in _norm(row.item_name).split() if len(w) >= 2]
		if words:
			named.append((row, words))
	return by_code, named


def _word_in(word: str, words: set[str]) -> bool:
	if word in words:
		return True
	if len(word) < 4:
		return False
	return any(abs(len(w) - len(word)) <= 2 and SequenceMatcher(None, word, w).ratio() >= 0.85 for w in words)


def _match_name(line_words: set[str], named: list):
	best, best_score = None, 0.0
	for item, words in named:
		exact = sum(1 for w in words if w in line_words)
		if exact * 2 < len(words):  # cheap filter before fuzzy matching
			continue
		hits = sum(1 for w in words if _word_in(w, line_words))
		score = hits / len(words)
		if score >= 0.75 and (hits >= 2 or len(words) == 1) and (
			score > best_score or (score == best_score and best and len(words) > len(best[1]))
		):
			best, best_score = (item, words), score
	return best


def _quantities(numbers: list[float]) -> tuple[float | None, float | None]:
	"""(qty, unit cost) from the numbers on a line: qty × cost = amount when all three are there."""
	for i in range(len(numbers) - 2):
		a, b, total = numbers[i], numbers[i + 1], numbers[i + 2]
		if a > 0 and b > 0 and abs(a * b - total) <= max(0.05, total * 0.01):
			if float(b).is_integer() and not float(a).is_integer():
				a, b = b, a
			return a, b
	for value in numbers:
		if value > 0 and float(value).is_integer():
			return value, None
	return (numbers[0], None) if numbers and numbers[0] > 0 else (None, None)


def parse_lines(text: str, by_code: dict, named: list) -> tuple[list[dict], list[dict]]:
	"""(matched lines merged per product, lines that look like products but matched nothing)."""
	matched: dict[str, dict] = {}
	unmatched = []
	for raw in text.splitlines():
		line = raw.strip()
		if not line:
			continue
		tokens = re.findall(r"[\w\-]+", line)
		item, skip = None, set()
		for token in tokens:
			found = by_code.get(token.lower())
			if found:
				item, skip = found, {token}
				break
		if not item:
			found = _match_name(set(_norm(line).split()), named)
			if found:
				item, skip = found[0], set(found[1])
		numbers = [
			_number(token)
			for token in _NUMBER.findall(line)
			if token not in skip and len(re.sub(r"\D", "", token)) < 8  # long digit runs are codes
		]
		qty, rate = _quantities(numbers)
		if item:
			if not qty:
				continue
			row = matched.setdefault(
				item.name,
				{"item_code": item.name, "item_name": item.item_name, "qty": 0.0, "rate": rate, "raw": []},
			)
			row["qty"] += qty
			row["rate"] = row["rate"] if row["rate"] is not None else rate
			row["raw"].append(line[:200])
		elif qty and len(re.findall(r"[^\W\d_]", line)) >= 3 and not _NOISE.search(line):
			unmatched.append({"raw": line[:200], "qty": qty, "rate": rate})
	lines = [{**row, "raw": " | ".join(row["raw"])} for row in matched.values()]
	return lines[:MAX_LINES], unmatched[:50]


def _open_orders(supplier: str | None, item_codes: set[str]) -> list[dict]:
	"""The supplier's open orders in the user's shops, best match first."""
	warehouses = {row.warehouse: row for row in _shops(None)}
	if not supplier or not warehouses:
		return []
	orders = frappe.get_list(
		"Purchase Order",
		filters={
			"supplier": supplier,
			"docstatus": 1,
			"per_received": ("<", 100),
			"status": ("not in", ["Closed", "Completed", "On Hold"]),
			"set_warehouse": ("in", list(warehouses)),
		},
		fields=["name", "set_warehouse", "transaction_date"],
		order_by="transaction_date asc",
		limit=20,
	)
	out = []
	for order in orders:
		waiting = {
			row.item_code
			for row in frappe.get_all(
				"Purchase Order Item", filters={"parent": order.name}, fields=["item_code", "qty", "received_qty"]
			)
			if flt(row.qty) > flt(row.received_qty)
		}
		shop = warehouses[order.set_warehouse]
		out.append(
			{
				"name": order.name,
				"shop": shop.name,
				"shop_name": shop.shop_name,
				"date": str(order.transaction_date),
				"overlap": len(waiting & item_codes),
			}
		)
	return sorted(out, key=lambda o: -o["overlap"])


def read_content(content: bytes, file_name: str = "delivery-note") -> dict:
	"""The draft for an uploaded file's bytes (also used by tests)."""
	_require(BUY_ROLES, "Purchase Receipt", "create")
	if len(content) > MAX_BYTES:
		frappe.throw(_("The file is too large (at most {0} MB).").format(MAX_BYTES // (1024 * 1024)))
	if not content:
		frappe.throw(_("The file is empty."))
	text, method = extract_text(content)

	suppliers = frappe.get_list("Supplier", filters={"disabled": 0}, fields=["name", "supplier_name"], limit=2000)
	supplier = find_supplier(text, suppliers)
	by_code, named = _catalogue()
	lines, unmatched = parse_lines(text, by_code, named)
	missing = [row["item_code"] for row in lines if row["rate"] is None]
	costs = get_item_costs(missing, supplier) if missing else {}
	shops = {row.warehouse: row.name for row in _shops(None)}
	stock: dict[str, dict] = {}
	if lines and shops:
		for code, warehouse, qty in frappe.get_all(
			"Bin",
			filters={"item_code": ("in", [row["item_code"] for row in lines]), "warehouse": ("in", list(shops))},
			fields=["item_code", "warehouse", "actual_qty"],
			as_list=True,
		):
			stock.setdefault(code, {})[shops[warehouse]] = flt(qty)
	for row in lines:
		row["suggested_rate"] = costs.get(row["item_code"]) or None
		row["stock"] = stock.get(row["item_code"], {})  # current stock per shop the user may see
	orders = _open_orders(supplier, {row["item_code"] for row in lines})
	order = orders[0] if orders and orders[0]["overlap"] else None

	name = re.sub(r"[\\/]", "_", file_name)[:120] or "delivery-note"
	file_doc = frappe.get_doc(
		{"doctype": "File", "file_name": name, "is_private": 1, "content": content, "folder": "Home/Attachments"}
	).insert(ignore_permissions=True)  # buying roles were checked; the file stays private

	return {
		"file": file_doc.name,
		"file_name": name,
		"method": method,
		"text": text[:MAX_TEXT],
		"supplier": supplier,
		"supplier_name": next((s["supplier_name"] for s in suppliers if s["name"] == supplier), None),
		"reference": find_reference(text),
		"date": find_date(text),
		"order": order["name"] if order else None,
		"shop": order["shop"] if order else None,
		"orders": orders,
		"lines": lines,
		"unmatched": unmatched,
	}


# ---------------------------------------------------------------- API
@frappe.whitelist(methods=["POST"])
def read_delivery_note() -> dict:
	"""Upload a delivery note (PDF or photo) and get a draft to review. Posts nothing."""
	upload = frappe.request.files.get("file") if frappe.request else None
	if not upload:
		frappe.throw(_("No file was sent."))
	return read_content(upload.stream.read(MAX_BYTES + 1), upload.filename or "delivery-note")


def _attach(file_name: str | None, receipt: str):
	if not file_name:
		return
	row = frappe.db.get_value("File", file_name, ["name", "owner", "attached_to_name"], as_dict=True)
	# Only the user's own upload that is not attached anywhere yet.
	if not row or row.owner != frappe.session.user or row.attached_to_name:
		return
	frappe.db.set_value(
		"File", row.name, {"attached_to_doctype": "Purchase Receipt", "attached_to_name": receipt, "is_private": 1}
	)


@frappe.whitelist(methods=["POST"])
def receive_delivery_note(note: dict | str, request_id: str = "") -> dict:
	"""Receive a reviewed delivery note into one shop's stock.

	note: {supplier, shop, order?, reference, file?, lines: [{item_code, qty, rate?}]}.
	Quantities go against the order's rows first (at the order's cost); the
	rest, and products not on the order, at the rate given or the last known
	cost. Posts one submitted Purchase Receipt with the file attached.
	"""
	data = frappe.parse_json(note) or {}
	_require(BUY_ROLES, "Purchase Receipt", "create")
	order, shop_row, supplier = receiving_target(data)
	reference = (data.get("reference") or "").strip()[:140]
	if not reference:
		frappe.throw(_("Enter the delivery note number."))

	wanted: dict[str, dict] = {}
	lines = frappe.parse_json(data.get("lines")) or []
	if len(lines) > MAX_LINES:
		frappe.throw(_("A delivery can have at most {0} lines.").format(MAX_LINES))
	for line in lines:
		code = (line.get("item_code") or "").strip()
		qty = flt(line.get("qty"))
		if qty < 0:
			frappe.throw(_("Quantities cannot be negative."))
		if not code or not qty:
			continue
		row = wanted.setdefault(code, {"qty": 0.0, "rate": None})
		row["qty"] += qty
		if line.get("rate") not in (None, ""):
			row["rate"] = flt(line.get("rate"))
	if not wanted:
		frappe.throw(_("Enter what was delivered."))

	order_rows: dict[str, float] = {}
	order_rates: dict[str, float] = {}
	if order:
		for row in order.items:
			left = flt(row.qty) - flt(row.received_qty)
			want = wanted.get(row.item_code)
			if not want or left <= 0 or want["qty"] <= 1e-9:
				continue
			take = min(left, want["qty"])
			order_rows[row.name] = take
			want["qty"] -= take
			order_rates.setdefault(row.item_code, flt(row.rate))
	missing = [code for code, row in wanted.items() if row["qty"] > 1e-9 and row["rate"] is None]
	costs = get_item_costs(missing, supplier) if missing else {}
	free_rows = [
		free_line(
			{
				"item_code": code,
				"qty": row["qty"],
				"rate": row["rate"] if row["rate"] is not None else order_rates.get(code, costs.get(code, 0)),
			},
			shop_row.warehouse,
		)
		for code, row in wanted.items()
		if row["qty"] > 1e-9
	]

	def action() -> str:
		duplicate = frappe.db.get_value(
			"Purchase Receipt",
			{"supplier": supplier, "supplier_delivery_note": reference, "docstatus": 1, "is_return": 0},
			"name",
		)
		if duplicate:
			frappe.throw(
				_("Delivery note {0} of this supplier was already received ({1}).").format(reference, duplicate)
			)
		receipt = post_receipt(supplier, shop_row, order, order_rows, free_rows, reference)
		_attach(data.get("file"), receipt.name)
		return receipt.name

	return run_once("delivery-note", request_id, action, _receipt_summary)


@frappe.whitelist()
def download(receipt: str):
	"""The delivery note file attached to a receipt."""
	_require(VIEW_ROLES, "Purchase Receipt", "read")
	doc = frappe.get_doc("Purchase Receipt", receipt)
	doc.check_permission("read")
	shop = _shop_of(doc.set_warehouse).name
	if shop:
		assert_shop_access(shop)
	name = frappe.db.get_value(
		"File", {"attached_to_doctype": "Purchase Receipt", "attached_to_name": receipt}, "name"
	)
	if not name:
		frappe.throw(_("No file is attached to this delivery."), frappe.DoesNotExistError)
	file_doc = frappe.get_doc("File", name)
	frappe.local.response.filename = file_doc.file_name
	frappe.local.response.filecontent = file_doc.get_content()
	frappe.local.response.type = "download"
