# Zones, VLANs and policy

## Today (from discovery/raw, 2026-11-21)

Everything sits on one flat LAN, `vmbr0` 192.168.0.0/24, behind the ISP router (192.168.0.1).
Phones and laptops at home share that LAN with the Proxmox host, the app box (workhub) and the
public hosting box (cloudhost, *.pandeploy.dev). A compromised customer app on cloudhost can reach
the Proxmox UI on 192.168.0.101:8006 and every home device. Only customer VMs (`vmbr1`, 10.77.0.0/24)
are already isolated.

## Target

No managed switch. Every server is a guest on one Proxmox host, so segmentation is done in software:
one VLAN-aware internal bridge `vmbr2` (no physical port), one tagged sub-interface per zone on the
host, and the host routes and filters between zones with nftables (router-on-a-stick, inside the box).
The home LAN and the ISP router are not touched. vmbr0 stays the uplink.

| VLAN | Zone | Subnet | Gateway (host) | Members |
|---|---|---|---|---|
| 10 | MGMT | 10.10.10.0/24 | 10.10.10.1 | Proxmox host services, Zabbix, NetBox |
| 20 | SERVERS | 10.10.20.0/24 | 10.10.20.1 | LXC 101 workhub |
| 30 | DMZ | 10.10.30.0/24 | 10.10.30.1 | LXC 102 cloudhost (public hosting) |
| 50 | CUSTVM | 10.77.0.0/24 | 10.77.0.1 | customer VMs (existing vmbr1, unchanged) |
| - | HOME | 192.168.0.0/24 | 192.168.0.1 (ISP) | phones, laptops, the host's uplink |
| - | TAILNET | 100.64.0.0/10 | - | admin devices over Tailscale |
| 99 | LAB | 10.10.99.0/24 | 10.10.99.1 | test guests only |

Internet from VLAN zones goes out through the host with masquerade on vmbr0.

## Policy matrix

Rows = source, columns = destination. Default is drop, and drops are logged with a prefix (rate-limited).

| from \ to | MGMT | SERVERS | DMZ | CUSTVM | HOME | Internet |
|---|---|---|---|---|---|---|
| MGMT | - | allow | allow | allow | allow | allow |
| SERVERS | tcp 10051 (Zabbix) | - | tcp 80,443 | drop | drop | allow |
| DMZ | tcp 10051 (Zabbix) | tcp 8009 (kanjidojo backend) | - | cloudhost 10.10.30.10 only | drop | allow |
| CUSTVM | drop | drop | drop | - | drop | allow |
| HOME | drop | drop | tcp 80,443 | drop | - | (ISP router) |
| TAILNET | tcp 22,8006,80,443 | allow | tcp 22,80,443 | drop | - | - |

The matrix covers forwarded traffic to guests in each zone. The host's own services are not in it: the input chain
in `zones.nft` has policy accept on `vmbr0` and accepts everything from `tailscale0`. So the Proxmox UI
(192.168.0.101:8006) stays open from HOME, and all host ports stay open from the tailnet. That is on purpose, so remote
access cannot break during the migration. Locking down the host's own services is a later step, done at the console.

Rules that hold in every zone: established/related allowed back, ICMP echo allowed to each zone's own
gateway, DNS (53) and NTP (123) to the host gateway allowed.
