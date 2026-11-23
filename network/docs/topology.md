# Topology

Two views of the same box: what runs today, and what the zone plan in `zones.md` turns it into.
Sources: `../discovery/raw/*.txt` (2026-11-21), `zones.md`, `../aws/`.

## Current

One Proxmox host with one NIC. Home devices, the host and both LXCs share `vmbr0`.
Only customer VMs sit on their own bridge (`vmbr1`).

```mermaid
flowchart TB
  net((Internet))
  cf[Cloudflare edge<br/>*.pandeploy.dev]
  ts[Tailscale tailnet<br/>100.64.0.0/10]
  isp[ISP router<br/>192.168.0.1]
  net --- isp
  net --- cf
  subgraph host["Proxmox host panhomelab (one NIC, nic0)"]
    vmbr0["vmbr0 192.168.0.101/24<br/>flat home LAN"]
    vmbr1["vmbr1 10.77.0.1/24<br/>customer VMs, nftables allow-list + NAT"]
    tsh[tailscale0 100.109.143.18]
  end
  isp --- vmbr0
  home[phones, laptops] --- vmbr0
  ct101["LXC 101 workhub<br/>192.168.0.102 (DHCP)<br/>ts 100.108.65.118"] --- vmbr0
  ct102["LXC 102 cloudhost<br/>192.168.0.104 (DHCP)<br/>ts 100.102.34.29<br/>Traefik + cloudflared"] --- vmbr0
  ct102 -. "route 10.77.0.0/24 via host" .-> vmbr1
  cust[customer VMs] --- vmbr1
  cf == tunnel ==> ct102
  ts --- tsh
  ts --- ct101
  ts --- ct102
```

Notes
- LXC 101 and 102 take their address by DHCP, so it can change (see `incidents/2026-11-dhcp-lease-swap.md`).
- Tailscale runs on the host and inside both LXCs. Traefik (`coolify-proxy`, listed in `../discovery/raw/ct102-docker.txt`) and the Cloudflare tunnel connector (cloudflared) in cloudhost serve *.pandeploy.dev. That the tunnel feeds Traefik comes from my vault map (`Homelab/MAP.md`, lines 72, 80 and 124), not from the discovery dump. Port 127.0.0.1:20241 is listening in both guests (`../discovery/raw/ct101.txt`, `ct102.txt`); calling it the cloudflared metrics port is from `Homelab/MAP.md` line 80.
- vmbr1 traffic is limited by the `cloudhost_vm` nftables tables on the host (`../discovery/raw/host-nft.txt`).

## Target

Same host, same single NIC. `vmbr2` is a VLAN-aware bridge with no physical port, the host is the router
between zones and nftables (`../zones/nftables/zones.nft`) is the firewall. The home LAN and ISP router are not changed.
The AWS side is a VPC reached by site-to-site VPN with BGP (`../aws/`). The tunnel and BGP were only
simulated in containers, nothing ran on real AWS.

```mermaid
flowchart TB
  net((Internet))
  cf[Cloudflare edge]
  ts[Tailscale tailnet]
  isp[ISP router 192.168.0.1]
  net --- isp
  net --- cf
  subgraph host["Proxmox host panhomelab: router + nftables (zones.nft)"]
    vmbr0["vmbr0 uplink<br/>192.168.0.101/24"]
    subgraph vmbr2["vmbr2 VLAN-aware, no physical port"]
      v10["vmbr2.10 MGMT<br/>10.10.10.1/24"]
      v20["vmbr2.20 SERVERS<br/>10.10.20.1/24"]
      v30["vmbr2.30 DMZ<br/>10.10.30.1/24"]
      v99["vmbr2.99 LAB<br/>10.10.99.1/24"]
    end
    vmbr1["vmbr1 CUSTVM<br/>10.77.0.1/24"]
    tsh[tailscale0]
    vpn["strongSwan + FRR<br/>AS 65010<br/>advertises 10.10.0.0/16"]
  end
  isp --- vmbr0
  home[HOME devices] --- vmbr0
  ct101["LXC 101 workhub<br/>10.10.20.10 tag 20"] --- v20
  ct102["LXC 102 cloudhost<br/>10.10.30.10 tag 30"] --- v30
  mon["Zabbix, NetBox<br/>10.10.10.x"] --- v10
  lab[test guests] --- v99
  cust[customer VMs] --- vmbr1
  cf == tunnel ==> ct102
  ts --- tsh
  v10 --- vpn
  v20 --- vpn
  v30 --- vpn
  subgraph aws["AWS VPC 10.50.0.0/16 (VGW AS 64512)"]
    vgw[VPN gateway]
    priv["private 10.50.11.0/24<br/>DR instance (off by default)"]
    pub["public 10.50.1.0/24"]
  end
  vpn == "IPsec x2 + eBGP" ==> vgw
  vgw --- priv
  vgw --- pub
```

Notes
- Zone names, subnets and the allow/deny matrix are in `zones.md`. Addresses are in `ip-plan.md`.
- VLAN 50 (CUSTVM) stays untagged on `vmbr1` for now.
- MGMT has no guests yet. Zabbix and NetBox are drawn there as the plan; today Zabbix runs on workhub.
- BGP advertises 10.10.0.0/16 (all zones), AWS advertises 10.50.0.0/16 (`../aws/homelab-side/frr.conf.tpl`).

## PNG

The diagram sources are `img/current.mmd` and `img/target.mmd`. PNG export was tried with
`@mermaid-js/mermaid-cli` on the lab PC and failed: headless Chrome there is missing `libnspr4.so`.
GitHub renders the Mermaid blocks above directly. To make PNGs later: install the Chrome libs on the PC, then
`npx -y @mermaid-js/mermaid-cli -i docs/img/target.mmd -o docs/img/target.png`.
