#!/bin/sh
# Encrypted offsite copy of everything needed to rebuild the shop system on a
# new server: the newest nightly backup (database, public and private files),
# the server's generated passwords (~/secrets) and each site's
# site_config.json, which holds the encryption key without which saved
# passwords and other encrypted fields cannot be restored.
#
# Uploads with rclone to an encrypted ("crypt") remote, one folder per day,
# and deletes days older than OFFSITE_KEEP_DAYS. The crypt passwords live in
# ~/.config/rclone/rclone.conf on this server: keep a copy of them OFF this
# server (password manager or paper), or the offsite copy cannot be opened
# after losing the server. See docs/recovery.md.
#
# Run after the nightly backup (~/bin/nightly-backup.sh calls it).
# Settings (optional) in ~/offsite.env:
#   OFFSITE_REMOTE=offsite-crypt:retailmaster   rclone crypt remote and folder
#   OFFSITE_KEEP_DAYS=30
set -eu
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"

[ -f "$HOME/offsite.env" ] && . "$HOME/offsite.env"
REMOTE="${OFFSITE_REMOTE:-offsite-crypt:retailmaster}"
KEEP_DAYS="${OFFSITE_KEEP_DAYS:-30}"
BENCH="$HOME/frappe-bench"
LOG="$HOME/backups/offsite.log"

log() { echo "$(date '+%F %T') $*" >> "$LOG"; }
fail() {
	log "FAILED: $*"
	echo "offsite-backup: $*" >&2
	exit 1
}

command -v rclone > /dev/null || fail "rclone is not installed"
rclone listremotes | grep -qx "${REMOTE%%:*}:" || fail "rclone remote '${REMOTE%%:*}' is not set up (docs/recovery.md)"

latest=$(find "$HOME/backups" -mindepth 1 -maxdepth 1 -type d -name '20*' | sort | tail -n 1)
[ -n "$latest" ] || fail "no nightly backup folder in ~/backups"
find "$latest" -name '*-database.sql.gz' | grep -q . || fail "no database dump in $latest"

day=$(basename "$latest")
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
umask 077

mkdir -p "$stage/backup" "$stage/server/sites"
cp -a "$latest/." "$stage/backup/"
cp -a "$HOME/secrets" "$stage/server/secrets"
for config in "$BENCH"/sites/*/site_config.json; do
	site=$(basename "$(dirname "$config")")
	mkdir -p "$stage/server/sites/$site"
	cp "$config" "$stage/server/sites/$site/"
done
cp "$BENCH/sites/common_site_config.json" "$stage/server/sites/" 2> /dev/null || true
(
	cd "$BENCH"
	echo "made: $(date -Is) on $(hostname)"
	echo "backup folder: $day"
	bench version 2> /dev/null || true
	[ -f "$HOME/updater/deployed" ] && echo "retail_management commit: $(cat "$HOME/updater/deployed")"
) > "$stage/server/versions.txt" 2>&1

rclone copy "$stage" "$REMOTE/$day" --log-file "$LOG" --log-level NOTICE || fail "upload to $REMOTE/$day failed"
rclone delete "$REMOTE" --min-age "${KEEP_DAYS}d" --log-file "$LOG" --log-level NOTICE || log "pruning old copies failed"
rclone rmdirs "$REMOTE" --leave-root --log-file "$LOG" --log-level NOTICE 2> /dev/null || true

size=$(du -sh "$stage" | cut -f1)
log "ok: $day ($size) -> $REMOTE/$day"
