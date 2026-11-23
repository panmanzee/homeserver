# DHCP lease swap: workhub and cloudhost changed addresses

Status: found 2026-11-21, not fixed yet (fix is in the migration).

## Summary
LXC 101 (workhub) and LXC 102 (cloudhost) get their address by DHCP from the ISP router.
Their addresses swapped since the homelab map was written, and a host firewall rule still names the old one.

## Timeline
- 2026-10-23: `Homelab/MAP.md` (vault) is last updated. It lists workhub = 192.168.0.104 and cloudhost = 192.168.0.102.
- 2026-11-21 15:41: discovery run (`discovery/raw/STAMP`). `ct101.txt` shows 192.168.0.102, `ct102.txt` shows 192.168.0.104.
- 2026-11-21: noticed when the discovery output did not match the map. The date of the actual lease change is not known, nothing logged it.

## Impact
- The map and any notes built from it pointed at the wrong guest.
- `discovery/raw/host-nft.txt`, table `cloudhost_vm`, chain `forward`: `iifname "vmbr0" oifname "vmbr1" ip saddr 192.168.0.102 accept`.
  192.168.0.102 is now workhub. Cloudhost (192.168.0.104) is not matched by that accept, and the next line drops everything else to vmbr1.
  I did not test whether cloudhost still reaches the customer VMs; this is from reading the rule.
- Anything on the LAN that used the old addresses (bookmarks, firewall rules) would hit the other box.

## Root cause
Both containers use `ip=dhcp` on `vmbr0` (`ct101-config.txt`, `ct102-config.txt`) and there is no reservation on the ISP router.
A DHCP client can get a different lease after a restart or an expired lease. The containers were probably restarted in the audit period: the map notes two Docker containers in workhub with exit code 255 "at the reboot", which suggests an LXC restart. I did not confirm it.

## Fix
- Short term: NetBox (`netbox/inventory.yaml`) and `docs/ip-plan.md` hold the real addresses of 2026-11-21. `migration/pre-check.sh` prints the rule IP and the live cloudhost IP and warns when they differ.
- Real fix: fixed addresses in the container config (10.10.20.10 and 10.10.30.10 in `docs/ip-plan.md`), set by `migration/migrate-3-lxc.sh`.
- Not done: reservation on the ISP router, and updating the old nft rule (the zones firewall in the migration adds its own cloudhost to customer-VM exception).

## Evidence
- `discovery/raw/ct101.txt`, `discovery/raw/ct102.txt`, `discovery/raw/ct101-config.txt`, `discovery/raw/ct102-config.txt`
- `discovery/raw/host-nft.txt`, and the source of that rule on the host: `/etc/cloudhost/vm-net.nft` line 14 (not in this repo)
- `Homelab/MAP.md` in the vault (lines 20-21, `updated: 2026-10-23`)
- `netbox/inventory.yaml` (comment on workhub IPs)
