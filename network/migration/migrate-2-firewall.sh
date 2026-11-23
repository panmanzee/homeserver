#!/usr/bin/env bash
# step 2: load the zone firewall (runtime only, not persistent) + two interim exceptions for cloudhost
# usage: migrate-2-firewall.sh [--apply]
. "$(dirname "$0")/lib.sh"
mode
TS=$(date +%Y%m%d-%H%M%S)
B=$BACKUP_ROOT/$TS
NFT=$REPO/zones/nftables/zones.nft
C102=$(pct exec 102 -- ip -4 -br a show eth0 2>/dev/null | awk '{print $3}' | cut -d/ -f1)

say "backup current ruleset"
run mkdir -p "$B"
run_to "$B/nft-ruleset-before.txt" nft list ruleset

say "syntax check"
run nft -c -f "$NFT"

say "load zones.nft"
run nft -f "$NFT"

# zones.nft already allows cloudhost (10.10.30.10) -> CUSTVM. The old cloudhost_vm table still only accepts
# iifname vmbr0 from 192.168.0.102 (stale IP, see incidents/), so add runtime rules tagged "migration" there.
say "interim rules: cloudhost -> customer VMs while it moves from vmbr0 to vlan 30"
if [ -n "$C102" ]; then
  run nft insert rule inet zones from_uplink ip saddr "$C102" oifname vmbr1 accept comment '"migration"'
  run nft insert rule inet cloudhost_vm forward iifname vmbr0 oifname vmbr1 ip saddr "$C102" accept comment '"migration"'
else
  echo "[skip] could not read cloudhost IP, add the vmbr0 rules by hand"
fi
run nft insert rule inet cloudhost_vm forward iifname vmbr2.30 oifname vmbr1 ip saddr 10.10.30.10 accept comment '"migration"'

say "check"
run nft list table inet zones
run nft list table inet cloudhost_vm
echo "expect: both tables present, tailscale and ssh still working, customer VMs still reachable from cloudhost"
echo "not persistent: a reboot drops the zones table. Make it persistent only in the last step (docs/migration-runbook.md step 6)."
