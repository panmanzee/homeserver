#!/usr/bin/env bash
# restore latest snapshot to a temp dir and compare with the live files
set -uo pipefail
ENV_FILE="${HOMELAB_BACKUP_ENV:-/root/.config/homelab-backup.env}"
set -a; . "$ENV_FILE"; set +a
HERE=$(cd "$(dirname "$0")" && pwd)
TMP=$(mktemp -d /var/tmp/restore-test.XXXXXX)
trap 'rm -r "$TMP"' EXIT
SAMPLE=${SAMPLE:-20}

START=$(date +%s.%N)
restic restore latest --target "$TMP" >/dev/null || { echo "restore FAILED"; exit 1; }
END=$(date +%s.%N)
SECS=$(printf '%.1f' "$(echo "$END - $START" | bc)")

SNAP=$(restic snapshots latest --json | grep -o '"short_id":"[^"]*"' | tail -1 | cut -d'"' -f4)
RESTORED=$(find "$TMP" -type f | wc -l)
# file count the snapshot itself reports
INSNAP=$(restic ls latest --json | grep -c '"type":"file"')

# sha256 of a random sample of restored files vs the live copy
# (files edited after the backup are counted as "changed", not as failures)
ok=0; changed=0; n=0
while IFS= read -r f; do
  live="${f#$TMP}"
  n=$((n+1))
  if [ -f "$live" ] && [ "$(sha256sum < "$f")" = "$(sha256sum < "$live")" ]; then
    ok=$((ok+1))
  else
    changed=$((changed+1))
  fi
done < <(find "$TMP" -type f -size +0 | shuf -n "$SAMPLE")

if [ "$RESTORED" -eq "$INSNAP" ]; then CNT=match; else CNT=MISMATCH; fi
RES=PASS
{ [ "$CNT" = match ] && [ "$ok" -gt 0 ]; } || RES=FAIL
LINE="restore-test $(date +%F) snap=$SNAP restore=${SECS}s files_restored=$RESTORED files_in_snapshot=$INSNAP count=$CNT sha_ok=$ok/$n changed=$changed $RES"
echo "$LINE"

R="$HERE/results/restore-tests.md"
if [ ! -f "$R" ]; then
  echo "| date | snapshot | restore secs | files restored | files in snapshot | sha256 ok (sample) | changed since | result |" > "$R"
  echo "|---|---|---|---|---|---|---|---|" >> "$R"
fi
echo "| $(date +%F) | $SNAP | $SECS | $RESTORED | $INSNAP | $ok/$n | $changed | $RES |" >> "$R"
[ "$RES" = PASS ]
