# Proxmox host froze under memory pressure (19 Nov)

Status: recovered by reboot. RAM upgrade not done yet.

## Summary
On 2026-11-19 the minipc (8 GB RAM, Proxmox host) stopped responding while a software install and build ran on it.
It was unresponsive for remote use some time after 20:21 (the last monitoring heartbeat) until a manual reboot at about 21:25. The real outage window is unknown: the journal of the previous boot still has entries until 21:24, so the host was not fully dead the whole time. Nothing alerted, because nothing monitored the host at that time.

## Timeline
- 20:18 (+07): a setup script started installing Go and building three Go command line tools on the host. Source: vault note
  `Designs/2026-11-19-heavy-jobs-on-pc.md` ("Learn" section). I could not confirm the 20:18 time in the journal (no package or build lines found in the previous boot around 20:00-20:30).
- 20:21:16 (+07, 13:21:16 UTC): last heartbeat of the gateway service on the host (the heartbeat stops here; the journal does not): `mem_available_kib` 1871060 (about 1.8 GB), `swap_used_kib` 3038084 (about 2.9 GB) of 8017768 KiB total. Source: the exit log of that service (`gateway-exit-diag.log`), event `gateway.previous_unclean_exit`. Trimmed copy: `evidence/host-freeze-heartbeat.txt`.
- 21:24:01: last journal entry of the previous boot (`journalctl --list-boots`, boot -1). A systemd service was still logging at that point, so the host was still running. `evidence/host-freeze-journal-boots.txt`.
- 21:25:56: first journal entry of the new boot (boot 0, id `bca166b6...`).
- 21:26:47 (14:26:47 UTC): the gateway starts again and records the previous exit as unclean (`gateway-exit-diag.log`).
- 21:38: an alert fired. The vault note says it was the boot-time load spike, not a new problem.

## Impact
Remote access to the host, workhub, cloudhost (public hosting) and Tailscale was gone until the manual reboot at about 21:25. When it started is not known: somewhere after 20:21 (last heartbeat). I have no uptime graph, so I do not claim a duration.

## Root cause
Probable cause: memory pressure. This is inferred, not confirmed in the logs. What I have: the vault note says a heavy job (Go install and builds) was started on a host with 7.8 GB RAM that already runs two LXCs (6 GB + 3 GB configured) and uses swap (1.8 GB in use on 2026-10-22 per `Homelab/2026-10-22-homelab-audit.md`). The last heartbeat shows 1.8 GB available (about 23% of RAM) and about 2.9 GB swap in use, which is high but not exhausted. No OOM kill line was found in the kernel log of the previous boot. So heavy swapping is a likely explanation, but I did not see the moment it stopped.

## Fix
- Heavy jobs run on the Windows PC through `pcjob`, and a guard on the host blocks builds there (vault `Designs/2026-11-19-heavy-jobs-on-pc.md`).
- Zabbix on workhub now watches the host: available memory under 10% for 5 min and swap over 70% for 5 min send a Telegram alert (`monitoring/zabbix/README.md`, results in `monitoring/zabbix/results/`).
- Still open: more RAM (design step 1.1). `discovery/raw/host.txt` of 2026-11-21 still shows 7829 MB total and 1563 MB swap used.

## Evidence
- `gateway-exit-diag.log` in the logs directory of that service on the minipc (lines with `prior_start_time` 1794872110, last_heartbeat_at `2026-11-19T13:21:16.164206+00:00`)
- `journalctl --list-boots`: boot -1 last entry Thu 2026-11-19 21:24:01 +07, boot 0 first entry 21:25:56 +07 (`evidence/host-freeze-journal-boots.txt`)
- `evidence/host-freeze-heartbeat.txt` (only timestamps and memory fields)
- `/root/obsidian-vault/Designs/2026-11-19-heavy-jobs-on-pc.md`
- `/root/obsidian-vault/Homelab/2026-10-22-homelab-audit.md`
- `discovery/raw/host.txt`, `monitoring/zabbix/README.md`
