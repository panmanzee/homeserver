# Runbook (day 2)

Commands assume the repo is at `/root/net/homelab-network` on the Proxmox host unless it says "lab PC".
Heavy things (NetBox, terraform with LocalStack, the zones lab) run on the lab PC through `pcjob`,
because the host has 8 GB RAM.

## 1. Check Zabbix

Web UI: `http://100.108.65.118:8088` over Tailscale (or `127.0.0.1:8088` on workhub).
Look at: Monitoring > Problems, and that hosts panhomelab, workhub, cloudhost are all green (agent available).

Server containers on workhub:
```
docker ps --filter name=zbx
docker stats --no-stream zbx-server zbx-db zbx-web
```
Triggers (per `../monitoring/zabbix/README.md`): memory available under 10% for 5 min, swap over 70% for 5 min,
disk over 85%, agent unreachable 3 min. Alerts go to Telegram.
If a host shows unavailable: check Tailscale first (`tailscale status`), then `systemctl status zabbix-agent2` on that host.
Re-run the setup after changes: `python3 monitoring/zabbix/provision.py setup` (needs `ZBX_ENV_FILE`, see the README).

## 2. Backup and restore test

Needs `/root/.config/homelab-backup.env` (repo path, password file). Not stored in the repo.
```
nice -n 19 ionice -c3 backup/backup.sh
backup/restore-test.sh
tail backup/results/restore-tests.md
```
`backup.sh` backs up, applies retention (7 daily, 4 weekly), prunes and runs `restic check`. Exit code 0 = ok.
It uses a lock, so a second run exits with code 3 ("already running"). Exit 2 = env file missing.
Cron: `backup/homelab-backup.cron`, installed as `/etc/cron.d/homelab-backup` (03:30, log in `/var/log/homelab-backup.log`).
`restore-test.sh` restores the latest snapshot to a temp dir, compares the file count and the sha256 of a random sample
(`SAMPLE=20` by default), and appends a row to `backup/results/restore-tests.md`. It fails if the count does not match.
Do one restore test after every change to the backup paths.
The restic repo is on the same disk as the data. The S3 part is only tested on LocalStack.

## 3. Re-run the zones lab

On the lab PC (needs root, nft, iproute2, socat, netcat-openbsd). From the host:
```
pcjob --dir /root/net/homelab-network -- "cd /root/net/homelab-network/zones && sudo bash lab/build.sh && sudo bash lab/test.sh | tee lab/results/test-\$(date +%F).log; sudo bash lab/teardown.sh"
```
Expected last line: `SUMMARY: 433 passed, 0 failed, 433 total`. Re-run after any edit to `zones/nftables/zones.nft`
or the matrix in `zones.md`. Syntax check only (safe on the host): `nft -c -f zones/nftables/zones.nft`.

## 4. NetBox import and export

NetBox needs about 1.6 GiB of RAM (`../netbox/results/docker-stats-2026-11-21.txt`), so it runs on the lab PC only.
```
pcjob --dir /root/net/homelab-network -- "cd /root/net/homelab-network/netbox && bash run.sh"
```
`run.sh` starts NetBox, runs `import.py` twice (second run should say `created=0 updated=0`) and then `export.py`.
Results land in `netbox/results/`. By hand: `NETBOX_URL=http://localhost:8000 NETBOX_TOKEN=... python3 import.py && python3 export.py`.
Edit `netbox/inventory.yaml` to change data. The importer never deletes, so remove stale objects in the NetBox UI.
When a guest address changes, update the yaml first (see `incidents/2026-11-dhcp-lease-swap.md`).
Refresh the facts with new dumps in `discovery/raw` first.

## 5. Terraform plan (AWS)

No real AWS account was used so far. Local check against LocalStack on the lab PC:
```
pcjob --dir /root/net/homelab-network -- "cd /root/net/homelab-network/aws && bash run-checks.sh"
```
It does fmt, init, validate, plan, apply and destroy against LocalStack on port 4567.
Real plan, only with Pan's credentials in the environment:
```
cd aws/terraform
terraform init
terraform plan -var customer_gateway_ip=<current public IP>
```
The home public IP changes (ISP NAT), so `customer_gateway_ip` must be updated before every apply.
Backup bucket terraform is in `backup/terraform/` (`localstack-test.sh` there).
Budget is 5 USD; do not apply without checking it.

## 6. Quick health list

- `qm list; pct list` both guests running
- `ip -br a` host still has vmbr0 192.168.0.101
- `tailscale status` host and guests online
- `nft list tables` expected tables: `smbguard`, `cloudhost_vm`, `cloudhost_vm_nat`, `cloudhost_vm_l2` (plus `zones` after the migration)
- `free -m` swap should not be close to full (the host froze once from memory, see `incidents/`)
