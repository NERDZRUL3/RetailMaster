# Architecture

What has been chosen and pinned.

## Version matrix

Checked on 2026-11-16 against the upstream repositories.

| Component | Pinned | Source |
|---|---|---|
| ERPNext | v16.55.0 | frappe/erpnext releases; default in frappe_docker `example.env` |
| Frappe Framework | 16.56.0, as shipped in the `frappe/erpnext:v16.55.0` image | `bench version` in the running stack |
| Python | 3.14.10 (image) | Frappe `version-16` `pyproject.toml`: `>=3.14,<3.15` |
| Node.js | 24.22.3 (image) | `node --version` in the running stack |
| MariaDB | 11.8 | frappe_docker `pwd.yml` |
| Redis | 6.2 | frappe_docker `pwd.yml` |
| Container image | `frappe/erpnext:v16.55.0` | Docker Hub, official |

Custom interface (`frontend/package.json`, exact versions, lockfile committed):

| Package | Pinned |
|---|---|
| Vue | 3.5.45 |
| Vue Router | 5.5.1 |
| Vue I18n | 11.4.20 |
| Vite | 8.3.8 |
| TypeScript | 6.0.3 |
| Tailwind CSS | 4.3.5 |

Frappe UI is not used: the shell needs only a handful of components, and
plain Vue + Tailwind avoids a version coupling with Frappe's own UI library.

## Custom interface

- Source in `frontend/`. One single-page app for owners, managers and cashiers.
- `npm run build` writes the JS/CSS to the app's `public/frontend/` and copies
  `index.html` to `www/retail.html`. Frappe then serves the interface at
  `/retail` (all `/retail/...` paths, via `website_route_rules`).
- It talks to Frappe only through `/api/method/...` with the normal Frappe
  session cookie and CSRF token. It never touches the database.
- `retail_management.api.session.get_context` tells it who is signed in, which
  home they get (`owner`, `manager`, `cashier`) and which shops they may see.
  The menu built from that is a convenience; every API checks permissions.
- Languages: English, French, Arabic (right-to-left). The choice is stored on
  the user's profile.

Version 16 was chosen over 15 because it is the current stable major line and
the default of the official Docker project. Version 15 is still receiving
releases, so it remains the fallback if a v16 blocker appears.

## Shape

```text
User -> Cloudflare Tunnel -> Nginx -> Frappe (ERPNext + retail_management) -> MariaDB / Redis / files
```

- `retail_management` is one Frappe app that depends on ERPNext
  (`required_apps = ["erpnext"]`).
- ERPNext stays the source of truth for accounting, stock and POS documents.
  The custom app adds shop scoping, shelves, alerts and the custom UI APIs.
- Frappe and ERPNext core are never modified.

## Rules

- Never use `latest` image tags.
- Database, Redis and the Docker socket are never published. The dev stack
  binds the web port to `127.0.0.1` only.
- Secrets live in `.env` files that are git-ignored.
