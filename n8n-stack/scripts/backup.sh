#!/usr/bin/env bash
# Nightly homelab backup: every Postgres database (+ roles) and the app data
# volumes, rolled into one timestamped tar.gz in ~/backups/. Keeps the last
# $KEEP archives locally. No sudo required (pan is in the docker group).
#
#   ./scripts/backup.sh
#   crontab:  0 3 * * *  /home/pan/homeserver/n8n-stack/scripts/backup.sh >> /home/pan/backups/backup.log 2>&1
#
# Off-box copy: if an rclone remote named "$RCLONE_REMOTE" (default "b2") is
# configured in ~/.config/rclone/rclone.conf, each new archive is copied there
# and remote copies older than $REMOTE_KEEP_DAYS are pruned. If rclone isn't
# configured, this step is skipped with a one-line notice — the local backup
# still runs. Set it up once:
#   rclone config create b2 b2 account <KEY_ID> key <APP_KEY>
#   (Backblaze B2: 10 GB free. Make a private bucket, then:)
#   RCLONE_BUCKET=your-bucket-name   # add to the crontab line or a wrapper
#
# Vaultwarden's vault is encrypted at rest with the account master password, so
# the archive holds ciphertext for the vault itself; the SQL dumps are plaintext.

set -euo pipefail

STACK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$HOME/backups}"
KEEP="${KEEP:-14}"
RCLONE_REMOTE="${RCLONE_REMOTE:-b2}"
RCLONE_BUCKET="${RCLONE_BUCKET:-}"
RCLONE_PATH="${RCLONE_PATH:-homelab-backups}"
REMOTE_KEEP_DAYS="${REMOTE_KEEP_DAYS:-30}"
STAMP="$(date +%Y%m%d-%H%M%S)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$BACKUP_DIR"
cd "$STACK_DIR"

# 1. All Postgres databases + roles in one shot.
docker compose exec -T postgres pg_dumpall -U n8n > "$WORK/postgres-all.sql"

# 2. Named volumes — tar their contents via a throwaway alpine container.
for vol in n8n-stack_n8n_data n8n-stack_vaultwarden_data n8n-stack_uptime_kuma_data \
           n8n-stack_actual_data n8n-stack_adguard_conf; do
    if docker volume inspect "$vol" >/dev/null 2>&1; then
        docker run --rm -v "$vol":/src:ro -v "$WORK":/out alpine \
            tar czf "/out/${vol}.tar.gz" -C /src .
    fi
done

# 3. One archive for the run.
ARCHIVE="$BACKUP_DIR/homelab-$STAMP.tar.gz"
tar czf "$ARCHIVE" -C "$WORK" .
echo "$(date -Is)  wrote $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"

# 4. Prune oldest local archives beyond $KEEP.
ls -1t "$BACKUP_DIR"/homelab-*.tar.gz 2>/dev/null | tail -n +"$((KEEP + 1))" | while read -r old; do
    rm -v "$old"
done

# 5. Off-box copy via rclone (skipped cleanly if not configured).
RCLONE="docker run --rm --user $(id -u):$(id -g) -v $HOME/.config/rclone:/config/rclone -v $BACKUP_DIR:/data:ro rclone/rclone"
if [ ! -f "$HOME/.config/rclone/rclone.conf" ]; then
    echo "$(date -Is)  off-box copy skipped — no ~/.config/rclone/rclone.conf (see script header)"
elif ! $RCLONE listremotes 2>/dev/null | grep -qx "${RCLONE_REMOTE}:"; then
    echo "$(date -Is)  off-box copy skipped — rclone remote '${RCLONE_REMOTE}' not found"
elif [ -z "$RCLONE_BUCKET" ]; then
    echo "$(date -Is)  off-box copy skipped — RCLONE_BUCKET not set"
else
    DEST="${RCLONE_REMOTE}:${RCLONE_BUCKET}/${RCLONE_PATH}"
    if $RCLONE copy "/data/homelab-$STAMP.tar.gz" "$DEST/" 2>&1; then
        echo "$(date -Is)  off-box copy -> $DEST/homelab-$STAMP.tar.gz"
        $RCLONE delete --min-age "${REMOTE_KEEP_DAYS}d" "$DEST" 2>&1 || true
    else
        echo "$(date -Is)  off-box copy FAILED (local backup is fine)"
    fi
fi
