# cloudhost (pandeploy.dev)

A small multi-tenant PaaS on one home server: Coolify deploys apps, Traefik routes them,
a Cloudflare Tunnel exposes them (no open ports at home), and a FastAPI service enforces
subscription quotas against Coolify. Runs in Proxmox LXC 102 ("cloudhost"). Early access:
no public sign-up yet, and Stripe is not configured.

```
browser ─▶ Cloudflare (TLS) ─▶ tunnel "cloudhost" ─▶ Traefik :443 ─▶ app containers
                                         (pandeploy.dev, *.pandeploy.dev)
Coolify admin + API + billing  ─▶ Tailscale only (not routed through the tunnel)
```

## Layout

| Path | What |
|---|---|
| `billing-service/` | FastAPI: tiers, `/apps/register` (quota + per-app CPU/RAM limits pushed to Coolify), `/capacity`, Stripe webhook |
| `billing-service/test_billing.py` | 11 tests (sqlite + fake Coolify client) |
| `landing/index.html` | the page served at https://pandeploy.dev |

## Rules the billing service enforces

- Tier limits are **per app** (`tiers.py`). Registering an app is refused with **402** when the tenant
  is at its tier's `max_apps`, and with **503** when the platform as a whole would exceed
  `PLATFORM_CAPACITY` (1.5 CPU / 2048 MB committed across all apps). A tenant whose subscription is
  not `active` is treated as Free.
- Not enforced yet (defined in `tiers.py` but unused): `disk_limit_mb`, `custom_domain`,
  `sleep_after_inactive_min`. Do not advertise them.

## Run the tests

```
docker run --rm -v "$PWD/billing-service:/w" -w /w cloudhost-billing:latest \
  sh -c "pip install -q pytest && python -m pytest -q"
```

## Operations notes (no secrets here)

- DNS: `pandeploy.dev` and `*.pandeploy.dev` are proxied CNAMEs to the tunnel. Tunnel ingress sends both to
  `https://localhost:443` with `noTLSVerify` (Coolify apps use https FQDNs, so pointing at :80 would loop on
  Traefik's https redirect). Cloudflare Universal SSL covers the apex and one wildcard level only.
- Connector: `cloudflared.service` inside LXC 102 (token-based, remotely managed tunnel).
- Coolify: server wildcard domain is `https://pandeploy.dev`; new apps get `<uuid>.pandeploy.dev` unless a
  domain is set. Never route the Coolify dashboard through the tunnel.
- Billing container: plain `docker run` (not compose): `--restart unless-stopped`,
  `--add-host host.docker.internal:host-gateway`, `-p 127.0.0.1:8090:8090`, volume `billing-data:/data`,
  env `DATABASE_URL`, `COOLIFY_BASE_URL`, `COOLIFY_API_TOKEN`, `PUBLIC_BASE_URL`, `STRIPE_*`.
  Back up `/data/billing.db` before changing the schema or image.
- The landing page is deployed as a Coolify "dockerfile" app (nginx:alpine with `index.html` baked in via
  base64), limited to 0.25 CPU / 128 MB.

## Not done yet

Stripe (account, keys, price IDs, public webhook route at `billing.pandeploy.dev/webhook`), a tenant-facing
sign-up/deploy portal, disk limits, idle sleep for Free apps, and setting `PUBLIC_BASE_URL` to the real https URL.
