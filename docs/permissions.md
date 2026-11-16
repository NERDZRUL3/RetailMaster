# Permissions

## Roles

| Role | Created by | Shop scope |
|---|---|---|
| Retail Owner | `retail_management.setup.ensure_roles` | All shops |
| Retail Partner | same | All shops, read-only on the shop model |
| Retail Shop Manager | same | Assigned shops only |
| Retail Cashier | same | Assigned shops only |
| System Manager (Frappe) | Frappe | All shops |

## Shop model

| DocType | Purpose | Owner | Partner | Manager | Cashier |
|---|---|---|---|---|---|
| Retail Business | Groups shops under one owner group | full | read | none | none |
| Retail Shop | One shop: company, warehouse, POS profile | full | read | read, assigned only | read, assigned only |
| Retail Shop Access | Assigns a user to a shop | full | read | none | none |

A legal entity is an ERPNext Company. A Retail Shop points at one Company, so
both "one company, two shops" and "two companies" work without code changes.

## How scoping is enforced

All of it is in `retail_management/services/permissions.py`, on the server:

- `shop_query_conditions`: filters every list query on Retail Shop
  (`permission_query_conditions` hook).
- `shop_has_permission`: checks single documents (`has_permission` hook).
- `assert_shop_access(shop)`: must be called at the top of every custom API
  that takes a shop.

Role permissions decide what a role may do; the hooks only narrow that to the
assigned shops. They never grant anything.

## ERPNext documents (stock, sales, POS)

Each shop has its own ERPNext warehouse, created automatically with the shop
if none is chosen. Two shops can never share a warehouse or POS profile.

`retail_management/services/shop_access.py` turns Retail Shop Access into
Frappe's standard **User Permissions** on Company, Warehouse and POS Profile.
Frappe then filters every list, report, link dropdown and document that
links to those records. It re-syncs when:

- an access record is added, changed or deleted;
- a shop's company, warehouse or POS profile changes;
- a user's roles change (promoting a cashier to owner lifts the restriction).

Rules:

- Only users with Retail Shop Manager or Retail Cashier (and no full-access
  role) are restricted. Users without any retail role are never touched.
- For restricted users, these User Permissions belong to the app: manual
  edits on Company, Warehouse or POS Profile are replaced on the next sync.

Known limits:

- **Empty links:** list views only filter on the document's own warehouse
  field. A document whose top-level warehouse is empty passes the list
  filter, although opening it is still refused when an item row points at
  another shop's warehouse. Documents created by this app must always set
  the shop's warehouse and POS profile. Frappe's "Apply Strict User
  Permissions" setting closes this fully but is not enabled yet.
- **Cashiers:** Retail Cashier has no ERPNext document permissions yet; they
  arrive with the point of sale (M4). ERPNext's built-in "Desk User" role
  lets any signed-in user list product codes (names only, for link fields).
  Opening a product, prices, stock, costs or suppliers is refused (checked
  over HTTP on 2026-11-16).

## ERPNext permissions given to the retail roles

`setup.ensure_erpnext_permissions` (runs on install and every migrate) adds
these as Custom DocPerms, the same records the Role Permissions Manager
creates. It only adds rights, never removes them.

| Doctype | Owner, Partner | Shop Manager |
|---|---|---|
| Item | read, write, create | read, write, create |
| Item Price | read, write, create, delete | read, write, create, delete |
| Brand | read, write, create | read |
| Item Group, UOM, Price List | read | read |
| Warehouse, Bin, Stock Ledger Entry | read | read (own shops via User Permissions) |

Side effect: once a doctype has Custom DocPerms, Frappe uses those instead
of the standard ones, so later ERPNext upgrades that change that doctype's
standard permissions do not apply automatically.

## A manager or cashier with no shop

Frappe treats "no User Permissions" as "no restriction". To stop a manager
or cashier who has no shop from seeing every shop, the
`no_shop_query_conditions` / `no_shop_has_permission` hooks block them from
the shop-linked ERPNext doctypes listed in `hooks.py` (warehouses, stock,
purchasing, sales and POS documents). Tested in `test_inventory_api.py`.

## Tests

- `tests/test_shop_permissions.py` (21 tests): shop records. 6 fail when the
  two hooks are disabled (checked 2026-11-16).
- `tests/test_shop_stock_scoping.py` (14 tests): real Material Receipts in two
  shops; warehouses, stock entries, stock balances (Bin) and the stock
  ledger. 8 fail when the User Permission sync is disabled (checked
  2026-11-16).
- `tests/test_inventory_api.py` (15 tests): product search by barcode and
  name, per-shop stock and low stock, product create and edit, duplicate
  barcodes, other shops' reorder rules kept, cashier refused, manager with no
  shop blocked.
