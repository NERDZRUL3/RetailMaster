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
- **Cashiers:** ERPNext needs read access to products, customers, accounts,
  payment methods and the POS profile to post a sale, so cashiers can open
  those records in ERPNext's back office (`/app`), including a product's
  valuation rate. Prices, stock levels (Bin), stock ledger and suppliers stay
  refused. Hiding costs from cashiers needs field-level permissions (not
  done yet).

## ERPNext permissions given to the retail roles

`setup.ensure_erpnext_permissions` (runs on install and every migrate) adds
these as Custom DocPerms, the same records the Role Permissions Manager
creates. It only adds rights, never removes them.

| Doctype | Owner, Partner | Shop Manager | Cashier |
|---|---|---|---|
| Item | read, write, create | read, write, create | read |
| Item Price | read, write, create, delete | read, write, create, delete | none |
| Brand | read, write, create | read | none |
| Item Group, UOM | read | read | none |
| Price List | read | read | read |
| Warehouse, Bin, Stock Ledger Entry | read | read (own shops via User Permissions) | none |
| Sales Invoice | Owner: read, write, create, submit · Partner: read | read, write, create, submit (own shops: the invoice's warehouse and POS profile are scoped by User Permissions) | same as manager |
| Customer, Account, Mode of Payment, POS Profile | Owner: read | read | read |
| POS Opening Entry, POS Closing Entry | Owner: read, write, create, submit | read, write, create, submit (own shops via POS Profile) | same as manager |
| Retail Cash Movement | Owner: read (created only through the API) | none (API) | none (API) |
| Stock Reconciliation (stock counts) | Owner: read, write, create, submit · Partner: read | read, write, create, submit (own shops) | none |
| Supplier | Owner: read, write, create · Partner: read | read, write, create | none |
| Supplier Group, Contact | Owner: read | read | none |
| Purchase Order | Owner: read, write, create, delete, submit, cancel · Partner: read | same as owner (own shops: the order's warehouse) | none |
| Purchase Receipt | Owner: read, write, create, submit · Partner: read | read, write, create, submit (own shops) | none |

Flags of all groups a role gets are merged (`setup._merge`), so one group
granting read never takes away another group's write.

Inventory (`retail_management.api.stock`):

- Stock on hand per shop with its value at cost, low and out-of-stock
  totals; the stock ledger (sales, returns, deliveries, purchase receipts,
  transfers, counts) newest first.
- A transfer is one submitted Stock Entry (Material Transfer) between two
  shops of the same company. Owners transfer between any shops; a manager
  only between shops they manage (User Permissions apply to both
  warehouses). Transfers to or from a shop a manager does not manage are not
  listed for them.
- A count is a submitted Stock Reconciliation in one shop. Only products
  whose counted quantity differs from the stock on record are adjusted;
  if nothing differs, no document is created.

Purchasing (`retail_management.api.purchasing`):

- Suppliers with phone and email (kept in the supplier's primary Contact).
- A purchase order is delivered to one shop's warehouse. Drafts can be
  changed or deleted; a placed order can be cancelled while nothing was
  received, or closed once partly received.
- Receiving posts a submitted Purchase Receipt against the order for the
  quantities delivered (never more than still expected) at the order's
  unit cost; several deliveries per order are fine.
- A `before_validate` hook on Purchase Receipt clears the "rejected
  warehouse" that Frappe fills in from a restricted user's default
  warehouse (ERPNext refuses accepted = rejected warehouse).
- Supplier invoices and payments are not handled yet.
| Stock Entry | Owner: read, write, create, submit · Partner: read | read, write, create, submit (own shops) | none |
| Stock Entry Type | Owner: read | read | none |
| Item Group (product groups and subgroups) | Owner: read, write, create, delete · Partner: read | read, write, create, delete | none |

The point of sale (`retail_management.api.pos`) posts each sale as a
submitted Sales Invoice (POS, stock updated) on the shop's POS profile and
warehouse. Owners, managers and cashiers may sell; managers and cashiers
only in their own shops (checked by the API and again by User Permissions).
Partners are refused. Prices come from the POS profile's price list and
ERPNext pricing rules; a price sent by the browser is ignored. Payment must
cover the total, and only cash may exceed it (the difference is the change).
A `request_id` makes a double click or retry return the first sale.

Each shop gets its POS profile on its first sale
(`services/pos_profile.py`): the shop's warehouse, the default selling price
list, a "Walk-in Customer", Cash (default) and Credit Card when the company
has an account for them, rounding off. The owner may change it in ERPNext.
Till sessions (`retail_management.api.till`) use ERPNext's own POS Opening
Entry and POS Closing Entry:

- A sale needs the seller's own session on that till, opened today. One
  open session per till and per person (ERPNext's rule), so only the person
  who opened the till sells on it until it is closed.
- Opening records the counted cash float; the last close's counted cash is
  suggested.
- Cash in and cash out (with a reason) are Retail Cash Movement records.
  They change the cash expected in the drawer but post nothing in the
  accounts. Taking out more cash than the drawer should hold is refused.
- Closing is a blind count: the cashier enters what they count per payment
  method, then sees expected amounts and differences, may recount, adds an
  optional note (a comment on the closing entry) and closes. The closing
  entry stores opening, expected, counted and difference per method.
- While a session is open, staff who do not manage the shop do not get the
  expected amounts from the API. The X report still shows opening, sales
  and cash movements per method, so a careful cashier could add them up.
- Owners and managers may close another person's session (forgotten till,
  shift handover) and see every session of their shops' tills; cashiers see
  their own.
- A session opened on an earlier day must be closed before selling again.

Product groups are shared by all shops (`retail_management.api.categories`):
groups sit under the root category, subgroups under a group (two levels).
Renaming moves the products along; only empty categories can be deleted.

Receiving stock (`retail_management.api.receiving`) posts a submitted
Material Receipt into the shop's warehouse. Owners and managers may receive;
managers only into their own shops (checked by the API and again by User
Permissions on the warehouse). Partners and cashiers are refused. A
`request_id` sent with each delivery makes a double click or network retry
return the first receipt instead of receiving twice.

The overview dashboard (`retail_management.api.dashboard`) reads submitted
Sales Invoices whose source warehouse is one of the user's shops. Cashiers
are refused.

Side effect: once a doctype has Custom DocPerms, Frappe uses those instead
of the standard ones, so later ERPNext upgrades that change that doctype's
standard permissions do not apply automatically.

## Team accounts

`retail_management.api.users` (the Team page) lets Retail Owners and System
Managers create and change staff accounts: name, email, username, role,
shops, password, active or switched off.

- Only accounts with a retail role and without System Manager are listed or
  changed; the Administrator never is. Only the four retail roles can be
  given, so the page cannot hand out back-office administrator rights.
  Writes run with `ignore_permissions` after these checks, so owners need
  no User permissions in the back office.
- Managers and cashiers need at least one shop (Retail Shop Access, which
  syncs their User Permissions); owners and partners get none (they see
  every shop).
- Passwords: at least 8 characters and the site's password policy
  (strength score) when enabled. They are never returned. Setting a new
  password, or switching an account off, signs that person out everywhere
  else. A strong password generator runs in the browser.
- Changing someone's email renames the User (links follow). Frappe's
  `User.after_rename` renames their Notification Settings with a permission
  check that cannot be skipped, so the rename alone runs as Administrator.
- Lock-out guards: you cannot switch off your own account or change your
  own role, and the last active owner cannot be switched off or demoted.
- Accounts are switched off, never deleted, so sales and history keep
  their author.
- Signing in with a username is enabled once by the patch
  `v0_1.allow_username_login` (System Settings "Allow Login using User
  Name"); the owner can turn it off there.

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
- `tests/test_pos_api.py` (7 tests): a sale takes stock out of the right
  shop once, change on cash, prices from ERPNext, underpayment and unknown
  payment methods refused, staff limited to their shops, partner refused,
  receipt reprint scoped by shop.
- `tests/test_till_api.py` (5 tests): no sale without an open session;
  float, sale, cash in and out, blind X report for the cashier, expected for
  the manager, close with a shortfall, Z report, history and next float;
  one person per till; manager closes a cashier's session; cashier cannot
  close or read others' sessions; counts required.
- `tests/test_stock_api.py` (4 tests): stock value and shop scope, cashier
  refused; transfer between shops once per request, ledger entries;
  manager and partner cannot transfer to another shop; counts adjust only
  what differs.
- `tests/test_purchasing_api.py` (4 tests): supplier contact; order placed
  and received in two deliveries with stock in at the order's cost and
  over-receipt refused; delete draft, cancel, close; manager limited to own
  shop, partner read-only, cashier refused.
- `tests/test_users_api.py` (5 tests): owner creates an account (password
  checked by sign-in), renames the email, changes username, role, shops,
  password, switches it off; weak or missing password, cashier without a
  shop, taken email or username and non-retail roles refused; no self
  lock-out; administrators not listed or changeable; partner and manager
  refused.
- `tests/test_dashboard_api.py` (10 tests): overview figures net of returns,
  comparison with the previous period, daily and monthly series split by
  shop, latest sales, manager limited to own shop, cashier refused.
