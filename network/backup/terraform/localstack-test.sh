#!/usr/bin/env bash
# terraform apply on LocalStack, then restic backup/restore roundtrip to the bucket
set -euo pipefail
cd "$(dirname "$0")"

# wsl docker config points at a windows credential helper that is not in PATH
# (public image pull needs no login), so use an empty docker config
export DOCKER_CONFIG=$(mktemp -d)
echo '{}' > "$DOCKER_CONFIG/config.json"

STARTED=0
if docker ps --format '{{.Ports}}' | grep -q '4566->'; then
  echo "== LocalStack already running on 4566, reusing it"
else
  echo "== starting LocalStack"
  docker run -d --rm --name ls-backup -p 4566:4566 localstack/localstack:3.8
  STARTED=1
fi
cleanup() { if [ "$STARTED" = 1 ]; then docker stop ls-backup >/dev/null; echo "== stopped ls-backup"; fi; }
trap cleanup EXIT

for i in $(seq 1 60); do
  curl -sf http://localhost:4566/_localstack/health >/dev/null && break
  sleep 2
done

echo "== terraform"
terraform init -input=false
terraform validate
terraform apply -auto-approve -input=false -var use_localstack=true

BUCKET=$(terraform output -raw bucket)
export AWS_ACCESS_KEY_ID=$(terraform output -raw access_key_id)
export AWS_SECRET_ACCESS_KEY=$(terraform output -raw secret_access_key)
export AWS_DEFAULT_REGION=ap-southeast-1
export RESTIC_REPOSITORY="s3:http://localhost:4566/$BUCKET"
W=$(mktemp -d)
echo "test-repo-password" > "$W/pass"
export RESTIC_PASSWORD_FILE="$W/pass"

echo "== sample data"
mkdir -p "$W/src"
for i in 1 2 3 4 5; do head -c 200000 /dev/urandom > "$W/src/file$i.bin"; echo "note $i" > "$W/src/note$i.txt"; done

echo "== restic roundtrip with the IAM user keys"
restic init
restic backup "$W/src" --tag localstack
restic snapshots
restic restore latest --target "$W/out"
if diff -r "$W/src" "$W/out$W/src"; then echo "ROUNDTRIP OK: restored files identical"; else echo "ROUNDTRIP FAILED"; exit 1; fi
restic check

echo "== bucket settings"
terraform state list | grep -E 'versioning|encryption|public_access|lifecycle|iam_user_policy'

echo "== cleanup"
terraform destroy -auto-approve -input=false -var use_localstack=true | tail -3
rm -r "$W"
