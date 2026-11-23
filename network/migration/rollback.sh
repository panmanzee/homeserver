#!/usr/bin/env bash
# undo migration steps, using the oldest saved config that still has bridge=vmbr0 (the original) in $BACKUP_ROOT
# usage: rollback.sh 101|102|firewall|bridge|all [--apply]
#   101/102   put net0 back from the saved pct config, reboot the container
#   firewall  delete the zones tables and the rules tagged "migration" added to cloudhost_vm
#   bridge    remove the vmbr2 config and reload (refuses while a guest is still on it)
#   all       102, 101, firewall, bridge in that order
. "$(dirname "$0")/lib.sh"
WHAT=${ARGS[0]:-}
[ -n "$WHAT" ] || die "usage: $0 101|102|firewall|bridge|all [--apply]"
mode

back_ct() {
  local id=$1 f old
  f=$(oldest_ct_conf "$id")
  [ -n "$f" ] || { echo "no saved config for CT $id with bridge=vmbr0 under $BACKUP_ROOT, cannot restore"; return 1; }
  echo "using $f"
  old=$(sed -n 's/^net0: //p' "$f")
  [ -n "$old" ] || { echo "no net0 line in $f"; return 1; }
  say "CT $id back to: $old"
  run pct set "$id" -net0 "$old"
  run pct reboot "$id"
  run sleep 15
  run pct exec "$id" -- ip -4 -br a show eth0
  run pct exec "$id" -- ping -c 2 192.168.0.1
}

back_fw() {
  say "remove the rules tagged migration from the old cloudhost_vm table"
  local h
  for h in $(nft -a list chain inet cloudhost_vm forward 2>/dev/null | sed -n 's/.*comment "migration".*# handle \([0-9]*\)$/\1/p'); do
    run nft delete rule inet cloudhost_vm forward handle "$h"
  done
  say "remove zone firewall"
  run nft delete table inet zones
  run nft delete table ip zones_nat
  run nft list tables
}

back_bridge() {
  say "remove vmbr2"
  for id in 101 102; do
    if pct config "$id" 2>/dev/null | grep -q '^net0:.*bridge=vmbr2'; then
      die "CT $id is still on vmbr2, roll it back first"
    fi
  done
  run rm -f "$IFACE_FILE"
  run ifreload -a
  run ip -br a
}

case $WHAT in
  101|102) back_ct "$WHAT";;
  firewall) back_fw;;
  bridge) back_bridge;;
  all) back_ct 102; back_ct 101; back_fw; back_bridge;;
  *) die "unknown target $WHAT";;
esac
