# Backup (step 1.6)

Encrypted restic backup of the minipc host data. workhub is not included, it already has its own Google Drive backup. App config dirs that hold API keys are left out on purpose.

## What is backed up
`/etc/pve`, `/etc/network`, `/etc/nftables.conf`, `/etc/samba`, `/etc/cron.d`, `/etc/systemd/system`, `/root/obsidian-vault`, `/root/mission-control`, `/root/net`.

Excluded: files over 100 MB (5 files in the vault, 1.49 GiB together, mostly videos; `results/sizes-2026-11-21.txt`), `.obsidian/cache`, `.trash`, sqlite `-wal`/`-shm` files, `.terraform`, `__pycache__`.

## Run
```
# env file (chmod 600), default /root/.config/homelab-backup.env
RESTIC_REPOSITORY=/var/backups/restic-homelab
RESTIC_PASSWORD_FILE=/root/.config/restic-homelab.pass
# optional: TELEGRAM_BOT_TOKEN= / TELEGRAM_CHAT_ID= (message only sent if both set)

nice -n 19 ionice -c3 ./backup.sh     # init if needed, backup, forget (7 daily / 4 weekly) + prune, check
./restore-test.sh                      # restore latest to a temp dir, compare, append to results/restore-tests.md
```
`backup.sh` takes a flock, so two runs cannot overlap. Cron example: `homelab-backup.cron` (03:30 daily, installed as `/etc/cron.d/homelab-backup` on 2026-11-21; no scheduled run yet, so the numbers below are from a manual run).

## Off-site (terraform/)
S3 bucket with versioning, AES256 encryption, all public access blocked, STANDARD_IA after 30 days, noncurrent versions expire after 60 days. A restic IAM user is limited to that bucket. `use_localstack=true` points the provider at LocalStack. `terraform/localstack-test.sh` does apply, restic roundtrip and destroy. Not applied to real AWS yet.

## Measured results (first run, 2026-11-21)
- Backup: 4291 files, 1.070 GiB read in 1:04 (67 s with forget + check); 969 MiB added, 737 MiB stored; repo 739 MB on disk (`du -sh` on 2026-11-21, `results/sizes-2026-11-21.txt`).
- Restore test: 58.7 s, 4291 files restored = 4291 in snapshot, sha256 20/20 sample match, PASS.
- LocalStack: 8 resources applied and destroyed; restic to `s3:http://localhost:4566/...` with the IAM user keys, 10 files, restore identical, `restic check` clean.

Logs in `results/`. Note: the provider is pinned below 5.86 because newer versions timed out on the lifecycle resource against LocalStack 3.8 (first run failed that way).
Repo is on the same disk as the data, so it protects against deletion/mistakes, not disk failure; that is what the S3 part is for.
