# Homepage dashboard

[Homepage](https://gethomepage.dev) — one page with every service, a live
status/health badge and resource stats per container, the mini-PC's
CPU/RAM/disk/uptime, a search box, and bookmark links.

- **URL:** `https://pan-homeserver.tail9ee4c5.ts.net:8443/` (Tailscale only)
- **Container:** `homepage`, bound to `127.0.0.1:8004`; stateless — all state is
  the YAML in `config/`.
- **Docker access:** via `dockerproxy` (`tecnativa/docker-socket-proxy`), which
  exposes a **read-only, containers-only** slice of the Docker API over the
  compose network. Homepage never sees the real `/var/run/docker.sock`.

## Config (`config/`)

| File | Holds |
|---|---|
| `settings.yaml` | title, theme, group layout |
| `services.yaml` | the service tiles (grouped Apps / Infrastructure); each maps to a `container:` for its status badge, some add a `siteMonitor:` HTTP check |
| `widgets.yaml` | the top bar — resources, search, clock |
| `docker.yaml` | points Homepage at `dockerproxy:2375` |
| `bookmarks.yaml` | repo + admin links |

Edit a file and Homepage hot-reloads it — no restart. `config/logs/` is
runtime-only (gitignored).

## Access setup (one-time, recorded for a rebuild)

```bash
# operator was already set to `pan` for the vault, so no sudo needed here
tailscale serve --bg --https=8443 127.0.0.1:8004
tailscale serve status     # :443 → vault (8003), :8443 → homepage (8004)
```

## Notes

- One harmless `<dockerStatsService> ... /var/run/docker.sock` line appears in
  the logs at startup — Homepage probes the local socket once before it picks up
  `docker.yaml`. Per-container stats then flow fine over the proxy; it does not
  recur.
- To add a service: a new entry in `services.yaml` with `server: my-docker` +
  `container: <name>`. To add a widget with secrets (API keys) later, use
  `config/` + a `HOMEPAGE_VAR_*` env in `docker-compose.yml`, never inline.
