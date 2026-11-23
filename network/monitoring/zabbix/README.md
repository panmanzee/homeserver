# Zabbix monitoring for the homelab

Zabbix 7.0 LTS (alpine images) on workhub, watching the three real machines.
Reason: according to my audit notes Uptime Kuma had 0 monitors, and the Proxmox host froze from RAM pressure with no alert.

## What is monitored

| host | what | address |
|---|---|---|
| panhomelab | Proxmox host, Zabbix agent 2 | 100.109.143.18 (tailnet) |
| workhub | LXC 101, agent 2 + Docker template | 100.108.65.118 |
| cloudhost | LXC 102 (Coolify), agent 2 + Docker template | 100.102.34.29 |

Templates: `Linux by Zabbix agent` on all, `Docker by Zabbix agent 2` on workhub and cloudhost.
Custom triggers on every host (group `Homelab`):

- available memory < 10% for 5m (High)
- swap used > 70% for 5m (Average)
- disk `/` used > 85% (Average)
- agent unreachable 3m (High)

Alerts go through the built-in `Telegram` media type to one chat (the Admin user), severity Warning and up.

## Layout

- `docker-compose.yml` server, web, own postgres:16-alpine (limits 384m / 256m / 384m)
- `.env.example` copy to `.env` (gitignored) and set a DB password
- `agents/` agent configs for the 3 hosts, `install-agent.sh`, `workhub-allow-docker.sh`
- `provision.py` API setup, stdlib only
- `results/` evidence

Web UI: `http://100.108.65.118:8088` (tailnet only) or `127.0.0.1:8088` on workhub.
Server port 10051 is bound to the tailnet IP only. No firewall rule changed.

## Deploy

```
# on workhub, in /home/pan/zabbix
cp .env.example .env   # fill ZBX_DB_PASSWORD
docker compose up -d

# agents (as root on each target): hostname + os
bash agents/install-agent.sh panhomelab debian13
bash agents/install-agent.sh workhub ubuntu24.04
bash agents/install-agent.sh cloudhost ubuntu24.04
bash agents/workhub-allow-docker.sh     # workhub only, see notes

# provisioning
export ZBX_ENV_FILE=<file with TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_USERS>
python3 provision.py setup
python3 provision.py alert-test
python3 provision.py proof
```

`setup` changes the default Admin password to a random one stored in `/root/.config/zabbix-admin.pass` (mode 600, not in the repo).

## Notes

- workhub agent also allows `172.16.0.0/12` in `Server=`. The server container reaches the agent
  from the docker bridge, not from the tailnet IP, so it was refused (passive_available=2) before.
- `zabbix` user is in the `docker` group on workhub and cloudhost so the Docker template can read the socket.
- `mediatype.test` is not available over the API in 7.0, so the delivery proof is the real alert below.
- The stock `Zabbix server` host was deleted (no agent in the container, it only produced a problem).
- Screenshot not done: the UI needs a login and I do not put the password into a browser script.
- The first alert-test run failed (`Bad path`): the webhook parameters are `api_token` and
  `api_parse_mode`, not `Token`. Fixed in `provision.py`, second run delivered.

## Results (from `results/`)

Hosts, `results/hosts-2026-11-21.txt`: all three show `passive_available=1 active_available=1`,
`system.uptime` has a value on each.

Alert test, `results/alert-test-2026-11-21.txt` (temporary trigger `last(/panhomelab/system.uptime)>0`, deleted after):

- problem event 147: alert 3 `status=1 (sent)`, retries 0
- recovery event 148: alert 4 `status=1 (sent)`, retries 0

Memory, `results/memory-2026-11-21.txt` (`docker stats --no-stream`, about 20 min after start):

- zbx-db 165.8 MiB of 384
- zbx-server 64.2 MiB of 384
- zbx-web 64.1 MiB of 256
- total about 294 MiB
