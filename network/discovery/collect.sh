#!/bin/bash
# read-only inventory of the live homelab -> discovery/raw/
set -u
out="$(dirname "$0")/raw"
mkdir -p "$out"
{
  echo "# host"; hostname; pveversion; uptime
  echo; echo "# cpu/mem"; nproc; free -m
  echo; echo "# interfaces"; ip -br a
  echo; echo "# routes"; ip r
  echo; echo "# bridges"; bridge link 2>/dev/null; bridge vlan 2>/dev/null
  echo; echo "# guests"; pct list; qm list
  echo; echo "# listening"; ss -tlnH | awk '{print $4}' | sort -u
} > "$out/host.txt" 2>&1
nft list ruleset > "$out/host-nft.txt" 2>&1
for id in $(pct list | awk 'NR>1 && $2=="running"{print $1}'); do
  pct config "$id" > "$out/ct$id-config.txt"
  pct exec "$id" -- bash -c 'hostname; ip -br a; ip r; echo; echo "# docker"; docker ps --format "{{.Names}}\t{{.Image}}\t{{.Ports}}" 2>/dev/null; echo; echo "# listening"; ss -tlnH | awk "{print \$4}" | sort -u' > "$out/ct$id.txt" 2>&1
  pct exec "$id" -- nft list ruleset > "$out/ct$id-nft.txt" 2>&1
done
echo "collected $(date -Is)" > "$out/STAMP"
