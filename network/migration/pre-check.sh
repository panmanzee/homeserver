#!/usr/bin/env bash
# read-only checks before touching anything. Never changes the system, no --apply.
# run on the Proxmox host
. "$(dirname "$0")/lib.sh"
fail=0
ok()   { echo "ok    $*"; }
bad()  { echo "FAIL  $*"; fail=1; }
warn() { echo "warn  $*"; }

say "host"
[ "$(id -u)" = 0 ] && ok "root" || bad "not root"
command -v pct >/dev/null && ok "pct found" || bad "pct missing (not a Proxmox host?)"
command -v nft >/dev/null && ok "nft found" || bad "nft missing"
command -v ifreload >/dev/null && ok "ifreload found (ifupdown2)" || bad "ifreload missing"
[ "$(sysctl -n net.ipv4.ip_forward 2>/dev/null)" = 1 ] && ok "ip_forward=1" || bad "ip_forward is not 1"
ip link show vmbr2 >/dev/null 2>&1 && warn "vmbr2 already exists" || ok "vmbr2 not there yet"
ip link show vmbr0 >/dev/null 2>&1 && ok "vmbr0 present" || bad "vmbr0 missing"
nft list table inet zones >/dev/null 2>&1 && warn "table inet zones already loaded" || ok "zones table not loaded yet"

say "config files"
[ -r "$REPO/zones/network/vmbr2.interfaces" ] && ok "vmbr2.interfaces" || bad "vmbr2.interfaces not found"
if nft -c -f "$REPO/zones/nftables/zones.nft" 2>/dev/null; then ok "zones.nft syntax (nft -c)"; else bad "zones.nft does not pass nft -c"; fi
grep -q 'source /etc/network/interfaces.d' /etc/network/interfaces && ok "interfaces.d is sourced" || bad "interfaces.d not sourced, step 1 would have no effect"

say "guests"
for id in 101 102; do
  st=$(pct status "$id" 2>/dev/null | awk '{print $2}')
  [ "$st" = running ] && ok "CT $id running" || bad "CT $id state: ${st:-unknown}"
  net0=$(pct config "$id" 2>/dev/null | sed -n 's/^net0: //p')
  echo "      net0: $net0"
  case $net0 in *hwaddr=*) ok "CT $id has a fixed hwaddr";; *) bad "CT $id: no hwaddr in net0";; esac
  case $net0 in *bridge=vmbr0*) ok "CT $id on vmbr0 (not migrated yet)";; *) warn "CT $id not on vmbr0";; esac
  pct exec "$id" -- tailscale status >/dev/null 2>&1 && ok "CT $id tailscale up" || warn "CT $id tailscale status failed"
done
echo "      live addresses now:"
for id in 101 102; do echo "      CT $id: $(pct exec "$id" -- ip -4 -br a show eth0 2>/dev/null | awk '{print $3}')"; done

say "stale nft rule (DHCP drift)"
rule_ip=$(nft list table inet cloudhost_vm 2>/dev/null | grep -o 'ip saddr 192\.168\.0\.[0-9]*' | head -1 | awk '{print $3}')
c102=$(pct exec 102 -- ip -4 -br a show eth0 2>/dev/null | awk '{print $3}' | cut -d/ -f1)
echo "      cloudhost_vm allows saddr: ${rule_ip:-none}, cloudhost has: ${c102:-unknown}"
if [ -n "$rule_ip" ] && [ "$rule_ip" != "$c102" ]; then
  warn "rule IP differs from cloudhost IP, see docs/incidents/2026-11-dhcp-lease-swap.md"
fi

say "safety"
n=$(ls -1d "$BACKUP_ROOT"/*/ 2>/dev/null | wc -l)
echo "      earlier migration backups in $BACKUP_ROOT: $n"
if [ -e /var/log/homelab-backup.log ]; then
  echo "      host backup log last written: $(date -r /var/log/homelab-backup.log '+%F %T')"
else
  warn "no /var/log/homelab-backup.log, run backup/backup.sh first"
fi
echo "      reminder: be at the console (keyboard + screen), not only on SSH/Tailscale"

if [ $fail = 0 ]; then say "pre-check passed"; else say "pre-check FAILED"; exit 1; fi
