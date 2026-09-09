# Vaultwarden

Self-hosted, Bitwarden-compatible password manager. Runs as the `vaultwarden`
service in `docker-compose.yml`, bound to `127.0.0.1:8003` only. The **sole** way
in is `tailscale serve`, which fronts it at
`https://pan-homeserver.tail9ee4c5.ts.net/` with a real TLS cert, tailnet-only —
never the LAN, never the public internet, no Tailscale Funnel.

## One-time setup

### 1. Tailscale front (already done — recorded here for a rebuild)

```bash
sudo tailscale set --operator=pan
sudo tailscale serve --bg --https=443 127.0.0.1:8003
tailscale serve status        # expect: https://<host>.ts.net → http://127.0.0.1:8003
```

### 2. Deploy

```bash
cd ~/homeserver/n8n-stack
# .env already has VAULTWARDEN_DOMAIN + VAULTWARDEN_SIGNUPS_ALLOWED=true
docker compose up -d vaultwarden
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8003/alive   # 200
```

### 3. Register the one account, then lock signups

- Open `https://pan-homeserver.tail9ee4c5.ts.net/` from a device on the tailnet
  (phone with the Tailscale app, or the desktop).
- Create the account. **Master password = a long unique passphrase, memorized,
  used nowhere else.** There is no email/SMTP configured, so there is **no
  password reset** — lose the master password and the vault is gone.
- Turn on two-step login in the vault settings.
- Then close signups:

```bash
sed -i 's/^VAULTWARDEN_SIGNUPS_ALLOWED=.*/VAULTWARDEN_SIGNUPS_ALLOWED=false/' .env
docker compose up -d vaultwarden
```

### 4. Clients

Official Bitwarden apps/extensions, **Settings → Server URL →**
`https://pan-homeserver.tail9ee4c5.ts.net`. The device must be on the tailnet
(Tailscale app running) to reach it.

## Operations

| Task | Command |
|---|---|
| Update | bump the image tag in `docker-compose.yml`, `docker compose up -d vaultwarden` |
| Logs | `docker compose logs -f vaultwarden` |
| Health | `curl -s localhost:8003/alive` |

The `/admin` panel is intentionally disabled (no `ADMIN_TOKEN`) — a single user
doesn't need it, and it's one less secret to guard.

## Backups & restore

`scripts/backup.sh` (cron, 03:00 daily) rolls every Postgres database and the
`n8n` + `vaultwarden` data volumes into `~/backups/homelab-<stamp>.tar.gz`
(keeps 14). Vaultwarden's vault is already encrypted with the account master
password, so the archive holds ciphertext for the vault itself.

**Restore the vault volume:**

```bash
cd ~/homeserver/n8n-stack
docker compose stop vaultwarden
tar xzf ~/backups/homelab-<stamp>.tar.gz -C /tmp n8n-stack_vaultwarden_data.tar.gz
docker run --rm -v n8n-stack_vaultwarden_data:/dst -v /tmp:/src alpine \
    sh -c 'rm -rf /dst/* && tar xzf /src/n8n-stack_vaultwarden_data.tar.gz -C /dst'
docker compose up -d vaultwarden
```

**Still TODO (phase 2):** get backup copies off the box — `rclone` to a cloud
remote, or a periodic pull to the desktop over Tailscale. A backup that only
lives on the same disk as the data doesn't survive a disk failure.
