#!/usr/bin/env bash
# Nightly homelab backup: every Postgres database (+ roles) and the n8n and
# vaultwarden data volumes, rolled into one timestamped tar.gz in ~/backups/.
# Keeps the last $KEEP archives. No sudo required (pan is in the docker group).
#
#   ./scripts/backup.sh
#   crontab:  0 3 * * *  /home/pan/homeserver/n8n-stack/scripts/backup.sh >> /home/pan/backups/backup.log 2>&1
#
# Vaultwarden's vault is already encrypted at rest with the account master
# password, so the archive adds no exposure beyond the SQL dumps — still, move
# copies off the box (phase 2: rclone to a cloud remote or sync to the desktop).

set -euo pipefail

STACK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$HOME/backups}"
KEEP="${KEEP:-14}"
STAMP="$(date +%Y%m%d-%H%M%S)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$BACKUP_DIR"
cd "$STACK_DIR"

# 1. All Postgres databases + roles in one shot.
docker compose exec -T postgres pg_dumpall -U n8n > "$WORK/postgres-all.sql"

# 2. Named volumes — tar their contents via a throwaway alpine container.
for vol in n8n-stack_n8n_data n8n-stack_vaultwarden_data; do
    if docker volume inspect "$vol" >/dev/null 2>&1; then
        docker run --rm -v "$vol":/src:ro -v "$WORK":/out alpine \
            tar czf "/out/${vol}.tar.gz" -C /src .
    fi
done

# 3. One archive for the run.
ARCHIVE="$BACKUP_DIR/homelab-$STAMP.tar.gz"
tar czf "$ARCHIVE" -C "$WORK" .
echo "$(date -Is)  wrote $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"

# 4. Prune oldest beyond $KEEP.
ls -1t "$BACKUP_DIR"/homelab-*.tar.gz 2>/dev/null | tail -n +"$((KEEP + 1))" | while read -r old; do
    rm -v "$old"
done
