#!/bin/sh
# Create or refresh the demo shops and users on the development site, with
# one password per role tier taken from .env:
#   DEMO_OWNER_PASSWORD    demo.owner@example.com
#   DEMO_PARTNER_PASSWORD  demo.partner@example.com
#   DEMO_MANAGER_PASSWORD  demo.manager1@example.com
#   DEMO_CASHIER_PASSWORD  demo.cashier1@example.com, demo.cashier2@example.com
#
# Run from this directory once the stack is up:  ./seed-demo.sh
set -eu
cd "$(dirname "$0")"
[ -f .env ] || { echo "No .env here; copy .env.example first." >&2; exit 1; }

value() { grep -E "^$1=" .env | head -1 | cut -d= -f2- ; }

site=$(value SITE_NAME)
site=${site:-retail.localhost}
for key in DEMO_OWNER_PASSWORD DEMO_PARTNER_PASSWORD DEMO_MANAGER_PASSWORD DEMO_CASHIER_PASSWORD; do
	[ -n "$(value $key)" ] || { echo "Set $key in .env" >&2; exit 1; }
done

kwargs=$(printf '{"passwords": {"owner": "%s", "partner": "%s", "manager": "%s", "cashier": "%s"}}' \
	"$(value DEMO_OWNER_PASSWORD)" "$(value DEMO_PARTNER_PASSWORD)" \
	"$(value DEMO_MANAGER_PASSWORD)" "$(value DEMO_CASHIER_PASSWORD)")

docker compose -f compose.dev.yaml --env-file .env exec -T backend \
	bench --site "$site" execute retail_management.dev.seed_demo --kwargs "$kwargs" > /dev/null
echo "Demo users ready on $site (passwords: see the DEMO_*_PASSWORD lines in .env)."
