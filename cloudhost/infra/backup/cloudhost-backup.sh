#!/bin/bash
# Nightly backup of the cloudhost platform state (portal, billing, compute SQLite DBs, Coolify's Postgres,
# Traefik file routes). Online-consistent copies via SQLite's backup API inside each container.
# Keeps 7 days in /root/backups. Installed by the 2026-10-22 audit; cron: /etc/cron.d/cloudhost-backup
set -euo pipefail
umask 077
ROOT=/root/backups
DEST="$ROOT/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$DEST"

dump_sqlite() {   # container db-path out-file
  docker exec -i "$1" python - "$2" > "$3" <<'EOF'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1]); mem = sqlite3.connect(":memory:")
src.backup(mem)
sys.stdout.buffer.write(mem.serialize())
EOF
  python3 - "$3" <<'EOF'
import sqlite3, sys
assert sqlite3.connect(sys.argv[1]).execute("PRAGMA integrity_check").fetchone()[0] == "ok"
EOF
}

dump_sqlite cloudhost-portal  /data/portal.db  "$DEST/portal.db"
dump_sqlite cloudhost-billing /data/billing.db "$DEST/billing.db"
dump_sqlite cloudhost-compute /data/compute.db "$DEST/compute.db"
cp /var/lib/docker/volumes/compute-data/_data/platform_key "$DEST/compute-platform_key"
docker exec coolify-db pg_dump -U coolify -d coolify | gzip > "$DEST/coolify-db.sql.gz"
tar -C /data/coolify/proxy -czf "$DEST/traefik-dynamic.tgz" dynamic
chmod -R go-rwx "$DEST"

find "$ROOT" -mindepth 1 -maxdepth 1 -type d -name '20*' -mtime +7 -exec rm -rf {} +
echo "$(date -Is) ok $DEST $(du -sh "$DEST" | cut -f1)"
