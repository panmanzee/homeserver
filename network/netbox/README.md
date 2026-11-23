# NetBox: the written-down version of the homelab

Before this, the only record was `MAP.md`, and it was already stale (the DHCP leases of the two
containers had swapped). `inventory.yaml` now holds the inventory as data, built from
`../discovery/raw` (read-only dumps of 2026-11-21), and `import.py` loads it into NetBox.

## What is modeled

- site `home`, manufacturer Lenovo, device type ThinkCentre M93p Tiny (10AA), device `panhomelab` (role hypervisor)
- cluster `pve` (type Proxmox); VMs/containers: `workhub` (LXC 101), `cloudhost` (LXC 102), `old-ct100` (stopped), `ubuntu-2404-template` (VM 9000, stopped)
- host interfaces: nic0, vmbr0, vmbr1, tailscale0 + planned vmbr2 with sub-interfaces vmbr2.10/.20/.30/.99
- VLAN group `home-zones` with VLANs 10 MGMT, 20 SERVERS, 30 DMZ, 99 LAB (from `../docs/zones.md`; VLAN 50 left out, vmbr1 is untagged today)
- prefixes: home LAN, customer VM net, the four planned zone nets, Tailscale 100.64.0.0/10 (container), docker bridge nets
- IPs on interfaces, and services (name, protocol, port) from each guest's listening sockets and `docker ps`

Current LAN IPs are `active` (the two DHCP ones `dhcp`). NetBox has no "planned" status for IPs, prefixes and
VLANs, so planned objects are status `reserved` plus the tag `planned`. Right now workhub is 192.168.0.102
and cloudhost is 192.168.0.104 (MAP.md has them the other way round).

## Run

`run.sh` runs on the lab PC (WSL Ubuntu with docker compose): clones netbox-docker tag 5.1.2 into `.lab/`
(git-ignored, with the generated login and API token), starts it on port 8000, waits for the API,
installs `requests` and `pyyaml`, runs `import.py` twice, then `export.py`.

```
export NETBOX_URL=http://localhost:8000 NETBOX_TOKEN=...   # only for running import.py/export.py by hand
python3 import.py && python3 export.py
```

## Results (`results/`)

- `import-run1-2026-11-21.txt`: `created=111 updated=3 unchanged=0` (the 3 updates are the primary IPs, set after the IPs exist)
- `import-run2-2026-11-21.txt`: `created=0 updated=0 unchanged=114` (idempotent)
- `netbox-export-2026-11-21.txt`, `netbox-ip-plan-2026-11-21.csv`: read back from the API (NetBox 4.7.5): 1 device, 4 VMs, 14 interfaces, 4 VLANs, 18 prefixes, 13 IPs, 41 services
- `docker-stats-2026-11-21.txt`: whole stack about 1.6 GiB (netbox 1.19 GiB, worker 260 MiB, postgres 148 MiB, two redis about 4 MiB each), so it needs to run on the lab PC, not on the 8 GB minipc next to the guests
- `run-2026-11-21.log`: log of the last full run. NetBox was already up from earlier attempts, so the long first-start wait is not in it. The first attempts failed on the compose healthcheck (migrations take longer than its start window), which `run.sh` now handles.

No screenshot: there is no headless chromium on the PC.

## Limits

- ct100 has no config dump (it is stopped), so it only has name and state. VM 9000's vmbr1 attachment comes from MAP.md, not from the dumps.
- Service names for ports 8791, 9119 and the tailscale-served ports are guesses from MAP.md where noted in `inventory.yaml`.
- The importer never deletes anything: removing an item from the yaml leaves it in NetBox.
