# Retail Manager

Self-hosted retail management for shops, built on ERPNext 16 and Frappe
with a custom app (`retail_management`) and its own web interface.

- Shops, staff and roles (owner, partner, shop manager, cashier), each
  member of staff limited to their own shop's data
- Product catalogue with barcodes, prices and stock per shop
- Per-customer branding: name, logo, colour and languages (English,
  French, Arabic with right-to-left layout)

## Layout

| Path | What it is |
|---|---|
| `apps/retail_management/` | Custom Frappe app (DocTypes, APIs, tests) |
| `frontend/` | Web interface (Vue 3, TypeScript, Tailwind), served at `/retail` |
| `infrastructure/docker/` | Development stack (pinned ERPNext image + this app) |
| `docs/` | Installation, deployment, architecture, permissions |

## Getting started

- Development: [docs/installation.md](docs/installation.md)
- Production on a Debian server or LXC: [docs/deploy-lxc.md](docs/deploy-lxc.md)
