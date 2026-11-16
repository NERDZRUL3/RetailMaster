# Development setup

Frappe does not run natively on Windows. The development stack needs Docker
(Docker Desktop with WSL 2, or any Linux host such as a Proxmox VM/LXC).

## Start

```bash
cd infrastructure/docker
cp .env.example .env        # then set the two passwords
docker compose -f compose.dev.yaml --env-file .env up -d --build
```

The first start creates the site, installs ERPNext and then
`retail_management`. Follow it with:

```bash
docker compose -f compose.dev.yaml logs -f create-site
```

Then open <http://localhost:8080> and sign in as `Administrator` with
`ADMIN_PASSWORD`.

## Verify the app installed

```bash
docker compose -f compose.dev.yaml exec backend bench --site retail.localhost list-apps
docker compose -f compose.dev.yaml exec backend bench --site retail.localhost set-config allow_tests true
docker compose -f compose.dev.yaml exec backend bench --site retail.localhost run-tests --app retail_management
```

Expected: `list-apps` shows `frappe`, `erpnext` and `retail_management`, and
the three tests in `tests/test_install.py` pass.

## After changing app code

The app folder is mounted into the containers, so no rebuild is needed:

```bash
docker compose -f compose.dev.yaml exec backend bench --site retail.localhost migrate   # DocType changes
docker compose -f compose.dev.yaml restart backend                                      # Python changes
```

Rebuild (`up -d --build`) only after changing the Dockerfile.

## Custom interface

Needs Node.js 24 on the workstation.

```bash
cd frontend
npm ci
npm run dev        # http://localhost:5183/retail/ , proxies /api to the stack on :8080
npm run typecheck
npm run build      # then Frappe serves it at http://localhost:8080/retail
```

## Demo shops and users

Each role tier has its own password in `infrastructure/docker/.env`:

| Account | Password key |
|---|---|
| `demo.owner@example.com` | `DEMO_OWNER_PASSWORD` |
| `demo.partner@example.com` | `DEMO_PARTNER_PASSWORD` |
| `demo.manager1@example.com` (Demo Shop 1) | `DEMO_MANAGER_PASSWORD` |
| `demo.cashier1@example.com` (Demo Shop 1), `demo.cashier2@example.com` (Demo Shop 2) | `DEMO_CASHIER_PASSWORD` |

Then:

```bash
./seed-demo.sh
```

This creates two demo shops, the users above and three demo products. Run
it again after changing a password in `.env`. It needs a company, which
exists once the tests have run once.

## Reset

This deletes the development database and files:

```bash
docker compose -f compose.dev.yaml down -v
```
