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
| `billing-service/test_billing.py` | 15 tests (sqlite + fake Coolify client) |
| `portal/` | customer portal: sign-up/sign-in, plans, test-mode checkout, deploy and manage apps (FastAPI + vanilla JS, no build step) |
| `portal/test_portal.py` | 17 tests incl. tenant isolation, image/registry allow-list, quota and capacity refusals |
| `portal/devserver.py` | local UI preview with fake Coolify/billing (not shipped in the image) |
| `landing/index.html` | the page served at https://pandeploy.dev |

## Rules the billing service enforces

- Tier limits are **per app** (`tiers.py`). Registering an app is refused with **402** when the tenant
  is at its tier's `max_apps`, and with **503** when the platform as a whole would exceed
  `PLATFORM_CAPACITY` (1.5 CPU / 2048 MB committed across all apps). A tenant whose subscription is
  not `active` is treated as Free.
- Not enforced yet (defined in `tiers.py` but unused): `disk_limit_mb`, `custom_domain`,
  `sleep_after_inactive_min`. Do not advertise them.

## Customer portal (port 8100)

The portal is the only service meant to be public. It owns accounts (scrypt-hashed passwords, HttpOnly session
cookie, login throttling, CSRF origin check) and is the only caller of Coolify and billing. Every app action is
checked against the portal's own `apps` table, so a user cannot touch an app that is not theirs.
Billing is on the private Docker network `cloudhost-internal` and is published to localhost only.
Payments are **test mode**: `MOCK_BILLING=1` on billing enables `/mock/subscribe`; the checkout UI uses a
read-only demo card and collects nothing. Replace with Stripe before charging anyone (see "Not done yet").

Customer containers get `--cap-drop=ALL` plus the few caps a web server needs, and the plan's CPU/RAM limits.
Not possible through Coolify today (verified): `no-new-privileges` fails the deploy, `--pids-limit` is ignored.
Images may only come from Docker Hub, ghcr.io or quay.io.

Run it: `docker run -d --name cloudhost-portal --network cloudhost-internal --add-host host.docker.internal:host-gateway
-p 8100:8100 -v portal-data:/data --env-file <env> --read-only --tmpfs /tmp --cap-drop=ALL
--security-opt no-new-privileges --memory 256m cloudhost-portal`. Env: `COOLIFY_API_TOKEN`, `COOLIFY_BASE_URL`,
`COOLIFY_PROJECT_UUID`, `COOLIFY_SERVER_UUID`, `BILLING_URL`, `BASE_DOMAIN`, `COOKIE_SECURE` (1 behind https),
optional `INVITE_CODE` (empty = open sign-up). Set `INVITE_CODE` before exposing it publicly.

### Public routing (app.pandeploy.dev)

The tunnel's `*.pandeploy.dev` rule matches before a separate `app.pandeploy.dev` rule, so the portal is routed by
Traefik instead: `/data/coolify/proxy/dynamic/portal.yaml` (Host `app.pandeploy.dev` on entrypoint `https`,
`tls: {}`, service `http://cloudhost-portal:8100`). Traefik must share a network with the portal:
`docker network connect coolify cloudhost-portal` — **repeat this whenever the portal container is recreated.**
The invite code lives only in `/root/.portal_invite` (mode 600) and the container env; run with `COOKIE_SECURE=1`.

## Run the tests

```
docker run --rm -v "$PWD/billing-service:/w" -w /w cloudhost-billing:latest \
  sh -c "pip install -q pytest && python -m pytest -q"
# portal: pip install -r portal/requirements.txt pytest && (cd portal && python -m pytest -q)
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

Stripe (account, keys, price IDs, public webhook route at `billing.pandeploy.dev/webhook`; the portal's
`/api/subscribe` then calls Stripe instead of `/mock/subscribe`), public exposure of the portal (tunnel route
`app.pandeploy.dev` -> `http://localhost:8100`), email verification and password reset, disk limits, idle sleep for Free apps, and setting `PUBLIC_BASE_URL` to the real https URL.

## Virtual machines (compute-service/)

Besides containers, customers can rent a whole Ubuntu virtual machine from the portal's **Machines** page:
a real KVM machine on the Proxmox host, with a browser terminal and an optional public https address.
It sits on a private network that reaches the internet and nothing else. See `compute-service/README.md` for how
it works and the isolation table, and `infra/proxmox/` for the host setup.
