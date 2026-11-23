# IP plan

Source of truth is NetBox (`../netbox/inventory.yaml` is loaded into it by `../netbox/import.py`;
the last read-back is `../netbox/results/netbox-ip-plan-2026-11-21.csv`). This page is a readable copy.
If it disagrees with NetBox, NetBox wins.

## Current (collected 2026-11-21, `../discovery/raw`)

| Device | Interface | Address | How |
|---|---|---|---|
| ISP router | - | 192.168.0.1 | gateway in `host.txt` |
| panhomelab (host) | vmbr0 | 192.168.0.101/24 | static |
| panhomelab | vmbr1 | 10.77.0.1/24 | static, customer VM gateway |
| panhomelab | tailscale0 | 100.109.143.18 | Tailscale |
| workhub (LXC 101) | eth0 | 192.168.0.102/24 | DHCP (`ct101.txt`) |
| workhub | tailscale0 | 100.108.65.118 | Tailscale |
| cloudhost (LXC 102) | eth0 | 192.168.0.104/24 | DHCP (`ct102.txt`) |
| cloudhost | tailscale0 | 100.102.34.29 | Tailscale |
| LXC 100, VM 9000 | - | - | stopped, no address in the dumps |

The two LXC addresses are swapped compared with `Homelab/MAP.md` in the vault (it says 101 = .104, 102 = .102).
Both are DHCP, so the lease moved. Details in `incidents/2026-11-dhcp-lease-swap.md`.
Docker bridge networks inside the guests (172.17-172.24.0.0/16 in workhub, 10.0.0.0/24-10.0.3.0/24 in cloudhost)
are listed in NetBox as well. Do not reuse 10.0.x.0/24 for zones.

## Target

From `zones.md`. Gateways are the host's `vmbr2.<vlan>` interfaces (`../zones/network/vmbr2.interfaces`).

| VLAN | Zone | Subnet | Gateway | Fixed hosts |
|---|---|---|---|---|
| 10 | MGMT | 10.10.10.0/24 | 10.10.10.1 | .1 host. Zabbix and NetBox have no address yet |
| 20 | SERVERS | 10.10.20.0/24 | 10.10.20.1 | .10 workhub |
| 30 | DMZ | 10.10.30.0/24 | 10.10.30.1 | .10 cloudhost |
| 50 | CUSTVM | 10.77.0.0/24 | 10.77.0.1 | existing, unchanged (untagged vmbr1) |
| - | HOME | 192.168.0.0/24 | 192.168.0.1 | host uplink .101 |
| - | TAILNET | 100.64.0.0/10 | - | addresses above, not changed |
| 99 | LAB | 10.10.99.0/24 | 10.10.99.1 | test guests only |
| - | AWS VPC | 10.50.0.0/16 | - | private 10.50.11.0/24, public 10.50.1.0/24 (`../aws/`) |

Rules used for the plan
- Zones are /24s inside 10.10.0.0/16, so one BGP prefix (10.10.0.0/16) covers all of them.
- .1 is the gateway, .10 is the first fixed host, .2-.9 spare, .100 and up for later guests.
- Fixed addresses are set in the container config (no DHCP) in the target zones.
- NetBox holds the planned addresses as status `reserved` with tag `planned`.
