# ASTRAVEL

Web build of the ASTRAVEL Figma design (trip planner + admin console). Vanilla ES-module SPA, no framework, no build step; all data is mock and lives in the browser's localStorage.

- Live: https://astravel.pandeploy.dev  (the Google button signs in as the demo user "Mimi Kagari", who is also admin)
- Fonts: Protest Strike (headings, matched to the Figma by pixel comparison), DM Sans, Roboto, Inter, all self-hosted.
- Deploy (LXC 102): `docker build -t astravel:1 .` then run on the `coolify` network as `astravel` (port 8080), routed by `/data/coolify/proxy/dynamic/astravel.yaml` (Host `astravel.pandeploy.dev` -> `http://astravel:8080`).
- Security: strict CSP (self only), read-only container, all caps dropped. User text is only inserted as text nodes.
