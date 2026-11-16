#!/bin/bash
# Production updater for a native bench install (see docs/deploy-lxc.md).
#
# Installs the newest commit of the configured branch, but only when:
#   1. every GitHub CI check on that commit passed,
#   2. the interface builds on this server,
# and then:
#   3. backs up the database,
#   4. copies the app, migrates and restarts,
#   5. checks the site answers correctly.
# If 4 or 5 fails, the previous app and the database backup are put back.
#
# Usage:  update.sh            run from cron; respects DEPLOY_HOURS
#         update.sh --now      ignore DEPLOY_HOURS
#         update.sh --status   show deployed and available commits
#
# Settings come from ~/.config/retail-updater.env (see deploy/updater.env.example).

set -Eeuo pipefail
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

CONFIG="${RETAIL_UPDATER_CONFIG:-$HOME/.config/retail-updater.env}"
# shellcheck disable=SC1090
[ -f "$CONFIG" ] && . "$CONFIG"

: "${REPO:?set REPO (owner/name on GitHub) in $CONFIG}"
BRANCH="${BRANCH:-main}"
BENCH="${BENCH:-$HOME/frappe-bench}"
SRC="${SRC:-$HOME/src/repo}"
STATE="${STATE:-$HOME/updater}"
DEPLOY_HOURS="${DEPLOY_HOURS:-}"          # e.g. "22-6"; empty = any time
REQUIRE_CI="${REQUIRE_CI:-1}"
DB_ROOT_PASSWORD_FILE="${DB_ROOT_PASSWORD_FILE:-$HOME/secrets/db_root_password}"
APP=retail_management
APP_DIR="$BENCH/apps/$APP"

mkdir -p "$STATE"
LOG="$STATE/update.log"
log() { printf '%s %s\n' "$(date '+%F %T')" "$*" | tee -a "$LOG" >&2; }

exec 9>"$STATE/lock"
flock -n 9 || exit 0   # another run is in progress

SITE="${SITE:-$(cat "$BENCH/sites/currentsite.txt" 2>/dev/null || true)}"
[ -n "$SITE" ] || { log "no site configured"; exit 1; }

mode="${1:-}"

# --- What is available ------------------------------------------------------
if [ ! -d "$SRC/.git" ]; then
	git clone --quiet "https://github.com/$REPO.git" "$SRC"
fi
git -C "$SRC" fetch --quiet origin "$BRANCH"
target=$(git -C "$SRC" rev-parse "origin/$BRANCH")
deployed=$(cat "$STATE/deployed" 2>/dev/null || echo none)

if [ "$mode" = "--status" ]; then
	echo "site:      $SITE"
	echo "deployed:  $deployed"
	echo "available: $target ($(git -C "$SRC" log -1 --format='%cd %s' --date=short "$target"))"
	echo "last log:"; tail -5 "$LOG" 2>/dev/null || true
	exit 0
fi

[ "$target" = "$deployed" ] && exit 0
if [ "$target" = "$(cat "$STATE/rejected" 2>/dev/null)" ]; then
	exit 0   # already failed once; wait for a newer commit
fi

# --- Deploy window -------------------------------------------------------------
if [ -n "$DEPLOY_HOURS" ] && [ "$mode" != "--now" ]; then
	start=${DEPLOY_HOURS%-*}; end=${DEPLOY_HOURS#*-}; hour=$((10#$(date +%H)))
	if [ "$start" -le "$end" ]; then
		inside=$(( hour >= start && hour < end ))
	else
		inside=$(( hour >= start || hour < end ))
	fi
	[ "$inside" -eq 1 ] || exit 0
fi

short=${target:0:7}

# --- 1. CI must have passed ----------------------------------------------------
if [ "$REQUIRE_CI" = "1" ]; then
	ci=$(curl -fsS -H "Accept: application/vnd.github+json" \
		"https://api.github.com/repos/$REPO/commits/$target/check-runs?per_page=100" | python3 -c '
import json, sys
runs = json.load(sys.stdin).get("check_runs", [])
if not runs:
    print("pending")
elif any(r["status"] != "completed" for r in runs):
    print("pending")
elif all(r["conclusion"] in ("success", "skipped", "neutral") for r in runs):
    print("success")
else:
    print("failure")
') || ci=unknown
	case "$ci" in
		success) ;;
		pending|unknown) exit 0 ;;   # try again on the next run
		*) log "$short: CI failed, not installing"; echo "$target" > "$STATE/rejected"; exit 0 ;;
	esac
fi

log "$short: installing (was ${deployed:0:7})"

# --- 2. Build the interface (nothing live is touched yet) -----------------------
git -C "$SRC" checkout --quiet --force --detach "$target"
git -C "$SRC" clean --quiet -fdx -e frontend/node_modules
if ! ( cd "$SRC/frontend" && npm ci --no-audit --no-fund --silent && npm run build --silent ) >> "$LOG" 2>&1; then
	log "$short: interface build failed, not installing"
	echo "$target" > "$STATE/rejected"
	exit 1
fi

# --- 3. Backup -------------------------------------------------------------------
backup_dir="$STATE/pre-update"
rm -rf "$backup_dir" "$STATE/previous-app"
mkdir -p "$backup_dir"
( cd "$BENCH" && bench --site "$SITE" backup --backup-path "$backup_dir" ) >> "$LOG" 2>&1
backup_sql=$(ls "$backup_dir"/*-database.sql.gz)
cp -a "$APP_DIR" "$STATE/previous-app"

health() {
	local i page asset
	for i in $(seq 1 30); do
		if [ "$(curl -fsS -m 5 http://127.0.0.1/api/method/ping 2>/dev/null)" = '{"message":"pong"}' ]; then
			break
		fi
		sleep 2
	done
	[ "$(curl -fsS -m 5 http://127.0.0.1/api/method/ping)" = '{"message":"pong"}' ] || return 1
	page=$(curl -fsS -m 10 http://127.0.0.1/retail) || return 1
	asset=$(printf '%s' "$page" | grep -o '/assets/retail_management/frontend/assets/[^"]*\.js' | head -1)
	[ -n "$asset" ] || return 1
	curl -fsS -m 10 -o /dev/null "http://127.0.0.1$asset" || return 1
	curl -fsS -m 10 "http://127.0.0.1/api/method/retail_management.api.session.get_context" | grep -q '"branding"' || return 1
	! sudo supervisorctl status | grep -v RUNNING | grep -q .
}

install_app() {   # install_app <source dir>
	rsync -a --delete --exclude .git --exclude '*.egg-info' --exclude __pycache__ "$1/" "$APP_DIR/"
	uv pip install --quiet --python "$BENCH/env/bin/python" -e "$APP_DIR"
}

rollback() {
	log "$short: $1; rolling back"
	install_app "$STATE/previous-app" >> "$LOG" 2>&1 || true
	if [ "$migrated" = 1 ]; then
		( cd "$BENCH" && bench --site "$SITE" restore "$backup_sql" \
			--db-root-username root --db-root-password "$(cat "$DB_ROOT_PASSWORD_FILE")" --force ) >> "$LOG" 2>&1 \
			|| log "$short: DATABASE RESTORE FAILED, backup is $backup_sql"
	fi
	( cd "$BENCH" && bench --site "$SITE" set-maintenance-mode off ) >> "$LOG" 2>&1 || true
	sudo supervisorctl restart all >> "$LOG" 2>&1 || true
	if health; then
		log "$short: rollback done, site is back on ${deployed:0:7}"
	else
		log "$short: ROLLBACK HEALTH CHECK FAILED, needs a person"
	fi
	echo "$target" > "$STATE/rejected"
	exit 1
}

# --- 4. Install, migrate, restart ------------------------------------------------
migrated=0
install_app "$SRC/apps/$APP" >> "$LOG" 2>&1 || rollback "copying the app failed"
migrated=1
( cd "$BENCH" && bench --site "$SITE" migrate ) >> "$LOG" 2>&1 || rollback "migrate failed"
sudo supervisorctl restart all >> "$LOG" 2>&1 || rollback "restart failed"

# --- 5. Health check -----------------------------------------------------------------
health || rollback "health check failed"

echo "$target" > "$STATE/deployed"
rm -f "$STATE/rejected"
log "$short: installed and healthy"
