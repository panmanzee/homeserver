#!/bin/bash
# Stand up NetBox (netbox-docker) on the lab PC, import inventory.yaml twice, export.
# Meant to run in WSL Ubuntu with docker + compose. Secrets stay in .lab/secrets.env (not in git).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
cd "$here"
day=$(date +%F)
mkdir -p results .lab
export DOCKER_CONFIG=$(mktemp -d)   # the default config points at a missing docker-credential-desktop.exe

TAG=5.1.2
[ -d .lab/netbox-docker ] || git clone -q -b "$TAG" --depth 1 https://github.com/netbox-community/netbox-docker.git .lab/netbox-docker
cd .lab/netbox-docker

# generated once, reused on later runs so the superuser keeps working
if [ ! -f ../secrets.env ]; then
  {
    echo "SUPERUSER_PASSWORD=$(openssl rand -hex 12)"
    echo "SUPERUSER_API_KEY=$(openssl rand -hex 6)"
    echo "SUPERUSER_API_TOKEN=$(openssl rand -hex 20)"
  } > ../secrets.env
  chmod 600 ../secrets.env
fi
set -a; . ../secrets.env; set +a

# compose fills the three secrets from the environment at "up" time
printf '%s\n' \
  'services:' \
  '  netbox:' \
  '    ports:' \
  '      - "8000:8080"' \
  '    environment:' \
  '      SKIP_SUPERUSER: "false"' \
  '      SUPERUSER_NAME: admin' \
  '      SUPERUSER_EMAIL: admin@example.com' \
  '      SUPERUSER_PASSWORD: "${SUPERUSER_PASSWORD}"' \
  '      SUPERUSER_API_KEY: "${SUPERUSER_API_KEY}"' \
  '      SUPERUSER_API_TOKEN: "${SUPERUSER_API_TOKEN}"' \
  > docker-compose.override.yml

docker compose pull -q
# first start runs all migrations, longer than the default healthcheck window:
# the first "up" may report unhealthy, so wait on the api and run "up" again for the worker
docker compose up -d || echo "up reported unhealthy (migrations still running), waiting on the api"

export NETBOX_URL=http://localhost:8000
# v2 token: Bearer nbt_<key>.<token>
export NETBOX_TOKEN="nbt_${SUPERUSER_API_KEY}.${SUPERUSER_API_TOKEN}"

echo "waiting for netbox api (first start takes a few minutes)"
code=0
for i in $(seq 1 120); do
  code=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $NETBOX_TOKEN" "$NETBOX_URL/api/status/" || true)
  [ "$code" = 200 ] && break
  sleep 10
done
[ "$code" = 200 ] || { echo "netbox not ready, last http code $code"; docker compose logs --tail 40 netbox; exit 1; }
echo "netbox ready after ~$((i*10))s"
for j in $(seq 1 30); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' netbox-docker-netbox-1)" = healthy ] && break
  sleep 10
done
docker compose up -d || docker compose up -d --no-deps netbox-worker

cd "$here"
pip install -q --break-system-packages requests pyyaml 2>&1 | tail -2 || true

echo "== import run 1"
python3 import.py | tee results/import-run1-$day.txt
echo "== import run 2 (must create nothing)"
python3 import.py | tee results/import-run2-$day.txt

echo "== export"
python3 export.py > /dev/null

echo "== docker stats"
docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.CPUPerc}}' | tee results/docker-stats-$day.txt

# a prefixes screenshot needs a logged-in browser session; only possible with a headless browser here
if command -v chromium >/dev/null || command -v chromium-browser >/dev/null; then
  echo "chromium found but login screenshot not scripted, skipping"
else
  echo "no chromium on this box, skipping screenshot"
fi
