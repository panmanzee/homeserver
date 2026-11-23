# /dev/null on the Proxmox host was replaced by a regular file

Status: guard in place. The thing that deleted it was never found.

## Summary
The host's `/dev/null` was no longer a character device. New containers and `pct exec` failed until it was recreated.
A cron job now checks it every 5 minutes.

## Timeline
Only these dates can be cited. The date of the failure itself was not written down.
- 2026-10-23 13:03:57: `/etc/cron.d/devnull-guard` was created (file modification time). `Homelab/MAP.md` (updated 2026-10-23) lists it.
- 2026-11-18 12:28 onward: the retained journal shows the guard running every 5 minutes (the cron line count grows every 5 minutes, see `evidence/devnull-guard.txt`), and no `devnull-guard: recreated /dev/null` message from `logger` (0 under `journalctl -t root`). So it has not had to fix anything in the journal window kept (since 2026-11-18).

## Impact
Symptoms as recorded in my ops notes: Docker in an LXC failed with `error creating device nodes: mount src=/dev/null ... no such file or directory`, and `pct exec` printed `Can't open /dev/null`. Running containers kept working; new ones did not start. How long it lasted and which service was hit is not recorded.

## Root cause
Something on the host deleted `/dev/null` and it ended up as a regular file (my ops notes say "if it is a regular file, something deleted it"). What did it is unknown. Each running LXC holds a bind mount of the old deleted inode, so they needed a restart even after the host was fixed.
The notes also say it is not a Docker or containerd version problem, so no downgrade.

## Fix
- Recreate: `rm -f /dev/null; mknod -m 666 /dev/null c 1 3`, then `pct reboot <id>` for each running container.
- Prevention: `/etc/cron.d/devnull-guard`:
  `*/5 * * * * root [ -c /dev/null ] || { rm -f /dev/null; mknod -m 666 /dev/null c 1 3; logger "devnull-guard: recreated /dev/null"; }`
- Open: no logging of who deleted it. If the `recreated` message ever shows up in `journalctl -t root`, look at what ran in the 5 minutes before.
- Today: `ls -la /dev/null` shows `crw-rw-rw- 1 root root 1, 3` (checked 2026-11-21).

## Evidence
- `/etc/cron.d/devnull-guard` (content and mtime, copied in `evidence/devnull-guard.txt`)
- `Homelab/MAP.md` in the vault, line 89
- my homelab ops notes file `homelab-proxmox-ops/SKILL.md` (kept outside this repo), the entry "Docker in LXC fails with ... /dev/null"
- `journalctl -t CRON -g 'devnull-guard'` (cron runs) and `journalctl -t root` (no recreate message); counts in `evidence/devnull-guard.txt`. A plain `-g 'devnull-guard: recreated'` also matches the cron command line itself, so it is not a valid check.
