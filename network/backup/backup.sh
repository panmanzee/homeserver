#!/usr/bin/env bash
# restic backup of the minipc host data (no app secrets, not workhub)
set -uo pipefail

ENV_FILE="${HOMELAB_BACKUP_ENV:-/root/.config/homelab-backup.env}"
[ -r "$ENV_FILE" ] || { echo "no env file $ENV_FILE" >&2; exit 2; }
set -a; . "$ENV_FILE"; set +a
: "${RESTIC_REPOSITORY:?missing}" "${RESTIC_PASSWORD_FILE:?missing}"

# only one run at a time
exec 9>/var/lock/homelab-backup.lock
flock -n 9 || { echo "already running" >&2; exit 3; }

HOST=$(hostname -s)
DATE=$(date +%F)
PATHS=()
for p in /etc/pve /etc/network /etc/nftables.conf /etc/samba /etc/cron.d \
         /etc/systemd/system /root/obsidian-vault /root/mission-control /root/net; do
  if [ -e "$p" ]; then PATHS+=("$p"); else echo "skip (missing): $p"; fi
done

# init repo if it does not exist yet
restic cat config >/dev/null 2>&1 || restic init || exit 1

START=$(date +%s)
rc=0
# --exclude-larger-than keeps the big videos/zips in the vault out
restic backup "${PATHS[@]}" --tag "$HOST" --tag "$DATE" \
  --exclude-larger-than 100M \
  --exclude '/root/obsidian-vault/.obsidian/cache' \
  --exclude '/root/obsidian-vault/.trash' \
  --exclude '/root/obsidian-vault/.Trash-*' \
  --exclude '/root/mission-control/data/*.db-wal' \
  --exclude '/root/mission-control/data/*.db-shm' \
  --exclude '**/.terraform' \
  --exclude '**/__pycache__' || rc=1

restic forget --keep-daily 7 --keep-weekly 4 --prune || rc=1
restic check || rc=1
SECS=$(( $(date +%s) - START ))

if [ $rc -eq 0 ]; then MSG="homelab backup OK on $HOST $DATE (${SECS}s)"
else MSG="homelab backup FAILED on $HOST $DATE"; fi
echo "$MSG"

# telegram only when configured
if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
  curl -s -m 15 "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    -d chat_id="$TELEGRAM_CHAT_ID" --data-urlencode text="$MSG" >/dev/null || true
fi
exit $rc
