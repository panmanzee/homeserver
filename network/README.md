# homelab-network

My home server (one Proxmox mini PC) runs my own apps and a small hosting service for other people.
Everything sat on one flat home LAN: a hacked customer app could reach the Proxmox UI and every phone
in the house. This repo turns it into something closer to a small-office network, without buying hardware.

## What is in here

| folder | what | status |
|---|---|---|
| `discovery/` | read-only script that dumped the live host, both containers and their nftables rules | run on the live host |
| `docs/zones.md` | VLAN / zone plan and policy matrix (MGMT, SERVERS, DMZ, CUSTVM, HOME, TAILNET, LAB) | design |
| `zones/` | nftables zone firewall + VLAN-aware bridge config, and a network-namespace lab that tests the matrix | tested in lab |
| `monitoring/zabbix/` | Zabbix 7.0 monitoring the real host and both containers, alerts to Telegram | running live |
| `netbox/` | NetBox as source of truth, idempotent import of the real inventory, IP plan export | ran on my PC |
| `backup/` | encrypted restic backup of host config + notes, restore test, S3 bucket in Terraform | cron installed, results from manual run (local repo) |
| `aws/` | AWS VPC + Site-to-Site VPN + BGP in Terraform, plus a container simulation of the tunnel | LocalStack + simulated only |
| `docs/` | topology, IP plan, runbook, console migration runbook, incident reports | written |
| `migration/` | scripts to move the live containers into VLANs, dry-run by default, with rollback | dry-run only (`migration/results/dry-run-2026-11-21.log`) |

## Results

- Zone firewall: 433/433 checks pass: every zone pair on 7 ports (22, 80, 443, 3306, 8006, 8009, 10051, all ports named in the matrix), plus return traffic, gateway
  services, customer VM isolation, VLAN isolation, drop counters and log prefix, in a network namespace
  copy of the layout. `zones/lab/results/test-2026-11-21.log`
- Monitoring: 3 Zabbix hosts (the physical Proxmox host + its 2 LXC containers, workhub and cloudhost) report with the agent available.
  A test trigger sent a real Telegram problem alert and a recovery 30 s later. The 3 Zabbix containers use
  about 294 MiB under memory limits. `monitoring/zabbix/results/`
- NetBox: first import created the inventory, second run `created=0 updated=0 unchanged=114`.
  `netbox/results/`
- Backup: 4291 files / 1.07 GiB backed up in 64 s, restore test 58.7 s, 4291/4291 files back,
  20/20 sha256 samples match. Results are from a manual first run. The cron job (03:30, `/etc/cron.d/homelab-backup`) was installed on 2026-11-21 and has not run on schedule yet (no `/var/log/homelab-backup.log`). `backup/results/`
- AWS: `terraform validate` ok, plan 24 resources. On LocalStack 22/24 applied (budget and VGW route
  propagation are not implemented there, 501). The VPN + BGP part is a simulation with strongSwan + FRR
  containers: BGP up, prefixes exchanged, ping through the tunnel. `aws/results/`
- Incident write-ups: DHCP lease swap (found during discovery) and two earlier incidents reconstructed from
  host logs and notes (a host freeze from memory pressure, `/dev/null` deleted): `docs/incidents/`,
  trimmed log excerpts in `docs/incidents/evidence/`

## What is not done

- The live containers are not moved into the VLANs yet. That needs someone at the console
  (`docs/migration-runbook.md`). The bridge and the move were dry-run only (`migration/results/dry-run-2026-11-21.log`: all six scripts run without `--apply`, host state hash unchanged).
- No AWS account, so nothing ran on real AWS.
- FortiGate / Cisco parts are not here. Everything uses Linux tools (nftables, FRR, strongSwan).

## How to run

```
bash discovery/collect.sh                          # read-only snapshot of the host
bash zones/lab/build.sh && bash zones/lab/test.sh  # zone lab, needs root, run on a test machine
bash backup/backup.sh && bash backup/restore-test.sh   # needs /root/.config/homelab-backup.env
cd netbox && python3 import.py && python3 export.py    # needs NETBOX_URL, NETBOX_TOKEN
bash aws/run-checks.sh                             # terraform against LocalStack
```

Day-to-day steps are in `docs/runbook.md`, layout in `docs/topology.md` and `docs/ip-plan.md`.
