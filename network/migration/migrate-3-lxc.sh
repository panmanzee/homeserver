#!/usr/bin/env bash
# step 3 (101) and 4 (102): move one LXC to its zone VLAN with a fixed address, keep the MAC
# usage: migrate-3-lxc.sh 101|102 [--apply]
. "$(dirname "$0")/lib.sh"
ID=${ARGS[0]:-}
VLAN=$(zone_for "$ID") || die "usage: $0 101|102 [--apply]"
mode
TS=$(date +%Y%m%d-%H%M%S)
B=$BACKUP_ROOT/$TS

NET0=$(pct config "$ID" 2>/dev/null | sed -n 's/^net0: //p')
[ -n "$NET0" ] || die "cannot read net0 of CT $ID (pct config)"
MAC=$(echo "$NET0" | grep -o 'hwaddr=[^,]*' | cut -d= -f2)
[ -n "$MAC" ] || die "no hwaddr in net0: $NET0"
IP=10.10.$VLAN.10
GW=10.10.$VLAN.1
NEW="name=eth0,bridge=vmbr2,tag=$VLAN,hwaddr=$MAC,ip=$IP/24,gw=$GW,type=veth"
echo "old net0: $NET0"
echo "new net0: $NEW"

if [ "$APPLY" = 1 ]; then
  ip link show "vmbr2.$VLAN" >/dev/null 2>&1 || die "vmbr2.$VLAN missing, run migrate-1-bridge.sh first"
  nft list table inet zones >/dev/null 2>&1 || die "table inet zones not loaded, run migrate-2-firewall.sh first"
else
  ip link show "vmbr2.$VLAN" >/dev/null 2>&1 || echo "note: vmbr2.$VLAN does not exist yet (step 1); --apply would refuse"
  nft list table inet zones >/dev/null 2>&1 || echo "note: zones table not loaded yet (step 2); --apply would refuse"
fi

say "backup CT $ID config"
run mkdir -p "$B"
run_to "$B/ct$ID.conf" pct config "$ID"

if [ "$ID" = 102 ]; then
  say "where does the guest set the customer-VM route (before the move)"
  run pct exec 102 -- sh -c 'grep -rn "10.77.0" /etc/netplan /etc/systemd/network /etc/network /etc/rc.local 2>/dev/null; ip route | grep 10.77'
  run pct listsnapshot 102
fi

say "change net0"
run pct set "$ID" -net0 "$NEW"

say "restart the container"
run pct reboot "$ID"
run sleep 15

say "check"
run pct exec "$ID" -- ip -4 -br a show eth0
run pct exec "$ID" -- ip route
run pct exec "$ID" -- ping -c 2 "$GW"
run pct exec "$ID" -- ping -c 2 1.1.1.1
run pct exec "$ID" -- getent hosts example.com
run pct exec "$ID" -- tailscale status
run ping -c 2 "$IP"
if [ "$ID" = 102 ]; then
  echo "expect also: docker ps shows coolify-proxy up, cloudflared connected, one *.pandeploy.dev site answers over https,"
  echo "             route 10.77.0.0/24 via 192.168.0.101 is gone or replaced (unreachable from 10.10.30.0/24), customer VMs still reachable"
else
  echo "expect also: docker ps unchanged, Zabbix UI on 100.108.65.118:8088 loads, the 3 hosts still green"
  echo "note: LAN devices can no longer reach workhub on its old 192.168.0.x address (HOME -> SERVERS is drop). Use the tailnet."
fi
echo "if it fails: ./rollback.sh $ID --apply"
