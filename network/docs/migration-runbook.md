# Migration runbook: move LXC 101 and 102 into VLAN 20 and 30

Run at the console of the Proxmox host (keyboard and screen, not over SSH or Tailscale: the network changes under you).
Target layout: `zones.md`, `topology.md`, `ip-plan.md`. Scripts: `../migration/`.

Status: written and dry-run only (output of all six scripts without `--apply`: `../migration/results/dry-run-2026-11-21.log`). None of this has been applied to the live host. The firewall rules are tested in the
network namespace lab (433/433), the VLAN bridge and the container move are not tested anywhere.

## How the scripts work
- Run them from the repo on the host: `cd /root/net/homelab-network/migration`.
- Every script prints the commands (`[dry-run]`) and changes nothing. Add `--apply` to really run.
- Order: `pre-check.sh`, `migrate-1-bridge.sh`, `migrate-2-firewall.sh`, `migrate-3-lxc.sh 101`, `migrate-3-lxc.sh 102`.
- Backups go to `/root/migration-backup/<timestamp>/` (`/etc/network`, the nft ruleset, `pct config` of each container).
- `rollback.sh 101|102|firewall|bridge|all [--apply]` undoes steps. Do rollback in reverse order of the steps.
- `bash -n` passes on all scripts. shellcheck is not installed on the host, so it was not run.

## Remote access: what keeps working
- Tailscale runs on the host and inside both containers (`/dev/net` is bound into them, `ct10x-config.txt`). Its traffic goes out
  through the new gateway with masquerade, so the tailnet addresses (100.109.143.18, 100.108.65.118, 100.102.34.29) do not change.
- cloudflared in cloudhost makes an outbound connection, so the public sites keep working as long as DMZ can reach the internet (zones.nft allows it).
- Host access over vmbr0 (192.168.0.101) is not touched.
- Still keep the console open. If both the LAN and Tailscale are gone, the console is the way back.

What does stop working (by design of the matrix)
- LAN devices (HOME) can no longer reach workhub on 192.168.0.x. HOME to SERVERS is drop. Use Tailscale.
- LAN devices have no route to 10.10.30.0/24 either (the ISP router does not know it), so they lose direct access to cloudhost too. Public access goes through Cloudflare, so only local testing is affected. The HOME to DMZ 80/443 rule in the matrix has no effect until the LAN gets a route to the zone.

## Cloudhost to customer VMs
Cloudhost creates and reaches the customer VMs on vmbr1. The matrix allows this for the cloudhost address only
(10.10.30.10 -> CUSTVM), and the zones lab tests it (allowed from 10.10.30.10, denied from another DMZ address).
The old table in `/etc/cloudhost/vm-net.nft` only lets 192.168.0.102 open connections into vmbr1, and that IP is
stale (see `incidents/2026-11-dhcp-lease-swap.md`). Step 2 adds three runtime rules tagged `migration` so cloudhost
keeps access before and after the move. After the move, update vm-net.nft to the new address and drop the tagged rules.
Also check, in step 4, the route `10.77.0.0/24 via 192.168.0.101` inside cloudhost (`ct102.txt`). It points at an address that is not on its new subnet. Find where it is set and remove it, the default gateway takes over.

## Step 0: pre-check and backup
- What: read-only checks, and a fresh backup of host config.
- Command:
  ```
  cd /root/net/homelab-network
  nice -n 19 ionice -c3 backup/backup.sh
  migration/pre-check.sh
  pct snapshot 102 pre-vlan-$(date +%Y%m%d)
  ```
  Container 101 is not in the host backup; it has its own Google Drive backup. Optional: `pct snapshot 101 pre-vlan-$(date +%Y%m%d)` (not run by the scripts).
- Check: `pre-check passed`, both containers `running` with a fixed `hwaddr`, backup `OK`.
  Warnings about the stale nft IP are expected until step 2.
- Rollback: `pct delsnapshot 102 pre-vlan-<date>` if you do not want it. Nothing else changed.

## Step 1: create vmbr2
- What: add the VLAN-aware bridge `vmbr2` with gateways `vmbr2.10/.20/.30/.99` as `/etc/network/interfaces.d/vmbr2` (copy of `zones/network/vmbr2.interfaces`), then `ifreload -a`. vmbr0 is not edited.
- Command: `migration/migrate-1-bridge.sh` (read it), then `migration/migrate-1-bridge.sh --apply`
- Check: `ip -br a` shows `vmbr2.10 10.10.10.1/24`, `.20`, `.30`, `.99` UP and `vmbr0 192.168.0.101/24`. Ping the router `ping -c2 192.168.0.1` and check the web UI on 8006 still loads.
- Rollback: `migration/rollback.sh bridge --apply` (removes the file, `ifreload -a`). If networking is broken: restore `/etc/network/interfaces` and `interfaces.d` from `/root/migration-backup/<ts>/` and run `ifreload -a`.

## Step 2: load the zone firewall
- What: load `zones/nftables/zones.nft` (tables `inet zones`, `ip zones_nat`) in the running kernel only, plus the three cloudhost exception rules. The old tables `smbguard` and `cloudhost_*` stay.
- Command: `migration/migrate-2-firewall.sh`, then with `--apply`
- Check: `nft list tables` lists `zones` and `zones_nat` next to the old tables. Host still reachable (SSH over LAN or Tailscale, port 8006). From cloudhost the customer VMs still answer. `dmesg | grep zn-drop` shows what is being dropped. Containers are still on vmbr0 here, so nothing should change for them yet.
- Rollback: `migration/rollback.sh firewall --apply` (deletes the zones tables and the rules tagged `migration`). A reboot also drops it, it is not persistent.

## Step 3: move LXC 101 (workhub) to VLAN 20
- What: `pct set 101 -net0 name=eth0,bridge=vmbr2,tag=20,hwaddr=<same MAC>,ip=10.10.20.10/24,gw=10.10.20.1,type=veth`, then `pct reboot 101`. Same MAC, so nothing else sees a new device. The config is saved first.
- Command: `migration/migrate-3-lxc.sh 101`, then with `--apply`
- Check (the script prints them): address `10.10.20.10`, ping gateway `10.10.20.1`, ping `1.1.1.1`, name lookup, `tailscale status` online, `docker ps` same containers as before. From another tailnet device open the Zabbix UI `http://100.108.65.118:8088`: the three hosts are green. Expect a short agent-unreachable blip while it reboots.
- Rollback: `migration/rollback.sh 101 --apply` (net0 back to `vmbr0 ... ip=dhcp`, reboot). It may come back with a different DHCP address; update NetBox if so.

## Step 4: move LXC 102 (cloudhost) to VLAN 30
- What: same as step 3 with tag 30 and `10.10.30.10/24`, gateway `10.10.30.1`. This is the public hosting box, so do it when a short outage is acceptable.
- Command: `migration/migrate-3-lxc.sh 102`, then with `--apply`
- Check: address `10.10.30.10`, gateway and internet ping, `tailscale status`, `docker ps` shows `coolify-proxy` up, cloudflared connected, one `*.pandeploy.dev` site loads from a phone on mobile data (that goes through Cloudflare). Customer VMs on 10.77.0.0/24 still reachable from cloudhost (known gap above). Look at the old `10.77.0.0/24 via 192.168.0.101` route in cloudhost and remove it if it is still there.
- Rollback: `migration/rollback.sh 102 --apply`. The `pre-vlan-*` snapshot from step 0 is the fallback if the container itself is damaged: `pct rollback 102 pre-vlan-<date>` (this also reverts its data).

## Step 5: verify the whole thing
- What: walk the matrix quickly on the real host.
- Check: from workhub reach `10.10.30.10:80` (allowed), from cloudhost try `10.10.20.10` on a port other than 8009 (should time out), cloudhost internet works, `nft list chain inet zones forward` counters move, `dmesg | grep zn-drop` shows only expected drops. Run Zabbix and check all three hosts. Run `backup/backup.sh` again.
- Rollback: `migration/rollback.sh all --apply` goes back in the right order (102, 101, firewall, bridge).

## Step 6: make it survive a reboot (manual)
Not scripted on purpose; do it only after step 5 has been fine for a few days.
- `vmbr2` is already persistent (file in `interfaces.d`) and the containers' `net0` is stored in `/etc/pve/lxc/`.
- The firewall is not. `nftables.service` is disabled on this host and `/etc/nftables.conf` starts with `flush ruleset`, so do not enable it. The customer-VM rules are loaded by `cloudhost-vm-net.service` from `/etc/cloudhost/vm-net.nft`. Add a second oneshot unit that runs after it and loads `zones.nft` (with the exception rules moved into `zones.nft` and the lab re-run), and change line 14 of `/etc/cloudhost/vm-net.nft` to the new cloudhost source address and interface.
- Check by rebooting at the console, then step 5 again.
- Rollback: disable that unit, then `rollback.sh all`.

## Later, optional: the host's own services
The matrix and `zones.nft` only filter traffic forwarded to guests. The host's own ports (for example 8006 on 192.168.0.101)
stay open from HOME and from the tailnet on purpose. Closing them is a separate step, done at the console after step 6.

## After
- Update `netbox/inventory.yaml`: container addresses become the 10.10.x.10 ones with status active, then re-import (`runbook.md`, section 4).
- Zabbix hosts use tailnet addresses, so they need no change.
- Write down anything that went wrong in `incidents/`.
