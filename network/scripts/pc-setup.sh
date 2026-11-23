#!/bin/bash
# tools on the lab box (WSL Ubuntu): docker, terraform, restic, nftables
set -e
export DEBIAN_FRONTEND=noninteractive
A="apt-get -o DPkg::Lock::Timeout=900 -y -q"
need=""
for p in docker.io docker-compose-v2 restic nftables iproute2 bridge-utils jq curl unzip gnupg; do
  dpkg -s "$p" >/dev/null 2>&1 || need="$need $p"
done
if [ -n "$need" ]; then $A update -q >/dev/null; $A install $need >/dev/null; fi
if ! command -v terraform >/dev/null; then
  v=1.9.8
  curl -fsSL -o /tmp/tf.zip https://releases.hashicorp.com/terraform/$v/terraform_${v}_linux_amd64.zip
  unzip -o -q /tmp/tf.zip -d /usr/local/bin
fi
if ! docker info >/dev/null 2>&1; then
  (systemctl start docker 2>/dev/null || service docker start 2>/dev/null || (nohup dockerd >/var/log/dockerd.log 2>&1 &)) || true
  for i in $(seq 30); do docker info >/dev/null 2>&1 && break; sleep 1; done
fi
docker --version; docker compose version; terraform version | head -1; restic version; nft --version
docker info --format 'docker ok: {{.ServerVersion}} cgroup={{.CgroupVersion}}'
