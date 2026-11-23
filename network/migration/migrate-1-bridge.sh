#!/usr/bin/env bash
# step 1: create vmbr2 (VLAN-aware, no port) and the vmbr2.10/.20/.30/.99 gateways
# usage: migrate-1-bridge.sh [--apply]
. "$(dirname "$0")/lib.sh"
mode
TS=$(date +%Y%m%d-%H%M%S)
B=$BACKUP_ROOT/$TS
[ -r "$REPO/zones/network/vmbr2.interfaces" ] || die "vmbr2.interfaces not found"
[ -e "$IFACE_FILE" ] && die "$IFACE_FILE exists already, remove it or run rollback.sh first"

say "backup /etc/network"
run mkdir -p "$B"
run cp -a /etc/network/interfaces "$B/interfaces"
run cp -a /etc/network/interfaces.d "$B/interfaces.d"

say "install vmbr2 config"
run cp "$REPO/zones/network/vmbr2.interfaces" "$IFACE_FILE"
run ifreload -a --syntax-check

say "apply"
run ifreload -a

say "check"
run ip -br a show vmbr2
run ip -br a show vmbr0
run bridge vlan show dev vmbr2
echo "expect: vmbr2.10/.20/.30/.99 UP with 10.10.x.1/24, vmbr0 still 192.168.0.101/24"
