# Homelab / Portfolio Roadmap

Date: 2026-08-30
Owner: pan (studying CCNA; goal = network-focused job portfolio + genuinely useful self-hosted services)

This is a **roadmap**, not a design. Each project below gets its own
brainstorm → spec → implementation cycle.
Update the Status column as things move.

---

## Hardware

| | Current | Note |
|---|---|---|
| Host | Intel i5-4570T (2c/4t, 2.9 GHz), mini PC, Ubuntu Server | 2013 low-power chip; fine for containers |
| RAM | **8 GB** (1×8 GB DDR3L-1600 SODIMM, slot B; slot A empty) | the real bottleneck |
| RAM slots | **2 total, board-capped at 16 GB** | one free slot |
| Disk | 98 GB, ~81 GB free | fine |
| Virtualisation | **VT-x not currently visible** | check BIOS → enable "Intel Virtualization Technology"; needed for GNS3 switch images |
| Always-on today | Postgres 16, n8n, newsfeed-api | ~0.7 GB |

### Recommended hardware move (do first — cheap, free slot)

**Add one 8 GB DDR3L SODIMM** (PC3L-12800 / 1600 MHz, 1.35 V, 204-pin) into the
empty slot → **16 GB total + dual-channel**. ~$20. The board maxes at 16 GB, so
2×8 GB is the ceiling (do not buy a single 16 GB stick). 16 GB covers the whole
roadmap with no juggling; on 8 GB some things must run on-demand only.

---

## Projects (in build order)

### 1. GNS3 Lab Portfolio  ·  Status: brainstorming next

- **Goal:** rebuild the CCNA labs currently done in Packet Tracer (VLANs, OSPF,
  ACLs, inter-VLAN routing, …) in GNS3, and write each up — topology diagram,
  step-by-step config, verification output — in a Git repo / blog. This is the
  centrepiece portfolio artifact.
- **Why:** directly demonstrates the CCNA skill set; lab + clear write-up is
  exactly what employers for NOC / network-tech roles want to see.
- **Rough shape:** GNS3 server headless on the mini PC; GNS3 GUI client on the
  laptop; router images via Dynamips (IOS 15 c7200) — switch images (IOSvL2)
  need VT-x. FRRouting containers as a lightweight alternative for pure L3 labs.
  One Git repo, one folder + README per lab, diagrams (draw.io / mermaid).
- **Depends on:** BIOS VT-x for realistic L2 switching. Nothing else.
- **Resource cost:** on-demand. Idle server ~0.4 GB; a 6–8 node lab 1.5–3 GB
  while running. Don't run big labs at the same time as LibreNMS on 7 GB.
- **Open questions for its spec:** which labs, in what order; Dynamips vs
  container nodes; how much to mirror the real CCNA blueprint; blog platform.

### 2. RAG Textbook Chatbot  ·  Status: queued

- **Goal:** ingest personal study material (multiple networking textbooks +
  course notes, PDFs) into a vector store; ask questions and get answers with
  citations back to the source. Shareable so classmates can use it too.
- **Why:** the corpus is genuinely too large for a context window, a shared bot
  is wanted, and RAG is a skill worth practising and showing. All three
  justifications hold (unlike the "just use Claude Projects" case for a small
  corpus).
- **Rough shape:** **pgvector in the existing Postgres** (no new DB service);
  ingestion pipeline (PDF → chunk → embed); retrieval + Claude answer synthesis;
  a thin chat UI (web) and/or Telegram bot reusing the existing bot token
  pattern. Embeddings via API (cheap, ~200 MB footprint) rather than a local
  model (1–2 GB).
- **Depends on:** existing Postgres (add `vector` extension). Ideally deployed
  through project 4 (PaaS) once that exists.
- **Resource cost:** low if embeddings are API-based — app container ~200–400 MB
  + pgvector rows in Postgres.
- **Open questions for its spec:** API vs local embeddings; chunking strategy;
  citation format; auth for the shared version; web UI vs Telegram vs both;
  how classmates access it (Tailscale, Cloudflare Tunnel, public).

### 3. LibreNMS Network Monitoring  ·  Status: queued

- **Goal:** SNMP monitoring + alerting for the home network and the mini PC's
  own services; graphs, thresholds, down-alerts to Telegram.
- **Why:** **portfolio / skill demonstration** (Domain 4 hands-on) more than
  daily utility — with few SNMP-capable devices at home there is little to
  monitor. Value goes up sharply when pointed at the **GNS3 lab devices**
  (project 1) or once prosumer gear exists.
- **Rough shape:** official LibreNMS docker-compose (librenms + mariadb + redis
  + dispatcher + snmp trap). Add devices: mini PC (snmpd), router/AP if they
  speak SNMP, GNS3 lab routers.
- **Depends on:** best paired with project 1 for something real to watch.
- **Resource cost:** ~0.8–1.2 GB, always-on. Fits on 7 GB but not alongside a
  big GNS3 lab + everything else — a reason for the RAM upgrade.
- **Open questions for its spec:** what devices actually expose SNMP; alert
  routing (LibreNMS → Telegram); retention; whether to also demo config backup
  (Oxidized) as part of the same portfolio piece.

### 4. Self-Hosted PaaS (Coolify or Dokploy)  ·  Status: queued

- **Goal:** a personal "mini Vercel/Heroku" — deploy apps by git push, automatic
  TLS, managed databases, a container dashboard. Everything new gets deployed
  through it.
- **Why:** the safe, useful, portfolio-worthy version of the "run my own cloud"
  idea. Résumé line: "I operate my own PaaS." Removes hand-rolled
  docker-compose toil for every later project.
- **Rough shape:** one self-hosted control-plane container (Coolify or Dokploy)
  managing the Docker host; connect a Git remote; migrate newsfeed-api and the
  RAG app onto it as the first deployments.
- **Depends on:** nothing technically; most valuable before projects 2 build
  out. Ordering 2↔4 is flexible — can swap.
- **Resource cost:** control plane ~0.7–1 GB, always-on, plus whatever it hosts.
- **Open questions for its spec:** Coolify vs Dokploy; keep n8n-stack as-is or
  bring it under the PaaS; backup strategy; how deploys are triggered.

### 5. Vaultwarden  ·  Status: queued (quick win, do anytime)

- **Goal:** self-hosted Bitwarden-compatible password manager for personal use.
- **Why:** daily-use utility. Low portfolio weight, high life value.
- **Rough shape:** single `vaultwarden` container + volume + reverse proxy +
  TLS; browser/mobile Bitwarden clients point at it. LAN-only or via Tailscale.
- **Depends on:** nothing. Could be the first thing deployed through project 4.
- **Resource cost:** ~50 MB. Negligible.
- **Open questions for its spec:** exposure (LAN-only vs Tailscale vs public);
  backup/export cadence; admin token handling.  **Security note:** if the
  multi-tenant hosting idea below is ever revived, Vaultwarden must not share a
  host with untrusted workloads.

---

## Deferred / rejected

| Idea | Decision | Reason |
|---|---|---|
| Multi-tenant hosting ("rent my compute to others, like AWS") | **Deferred — needs its own hardware + isolation design** | On the shared mini PC it is a severe security risk (untrusted code beside Vaultwarden + on the home LAN), oversubscribes RAM, and breaks residential-ISP terms. Legit as a portfolio piece only on a separate, network-isolated box with proper VM isolation (Incus/Proxmox), free (not paid), 1–2 friends, fully documented. |
| pfSense as the real home firewall | Deferred | Should not run as a VM on the shared box (reboot kills home internet) and needs VT-x. Do it on dedicated hardware, or as a *lab inside GNS3*. |
| Nextcloud | Rejected for now | Heavy (~1 GB+), high disk use, low portfolio value for a network role. Vaultwarden covers the "I self-host what matters" story more cheaply. |
| Personal Finance Tracker Bot | Rejected (off-goal) | Fun and usable, but not aligned with a network career. Sibling of the earlier task-manager idea. |
| AI CCNA Question Generator | Rejected by owner | — |
| Uptime Kuma | Rejected by owner | — |

---

## Sequencing rationale

1. **GNS3 first** — the core portfolio piece, no dependencies, and it gives
   LibreNMS something real to monitor.
2. **RAG** and **PaaS** next, order swappable. PaaS-first means RAG (and a
   migrated newsfeed-api) deploy cleanly onto it; RAG-first means faster
   payoff on studying. Lean PaaS-first if the RAM upgrade happens.
3. **LibreNMS** after GNS3 exists, so it monitors the lab devices.
4. **Vaultwarden** any time — 30-minute job, ideally the first app deployed
   through the PaaS.

## Always-on resource budget

| Service | RAM (approx) |
|---|---|
| Existing: Postgres + n8n + newsfeed-api | 0.7 GB |
| Vaultwarden | 0.05 GB |
| RAG app (API embeddings) | 0.3 GB |
| PaaS control plane | 0.8 GB |
| LibreNMS stack | 1.0 GB |
| **Subtotal always-on** | **~2.9 GB** |
| GNS3 lab (on-demand, while running) | +1.5–3 GB |

At **8 GB**: always-on set fits, but running a GNS3 lab means stopping LibreNMS
or keeping the lab small. At **16 GB** (one $20 stick in the free slot):
everything runs together comfortably.

## Cross-cutting decisions

- **One Postgres.** RAG uses `pgvector` in the existing instance; no separate
  vector DB.
- **PaaS owns deployment.** Once project 4 lands, new services (and ideally
  newsfeed-api) are deployed and TLS-terminated through it, not hand-written
  compose files.
- **Remote access = Tailscale.** For anything that needs off-LAN access
  (RAG for classmates, Vaultwarden on mobile), prefer Tailscale over public
  port-forwarding. Public exposure only with a deliberate reverse-proxy + auth
  design.
- **Telegram bot pattern is reusable.** RAG bot and LibreNMS alerts reuse the
  one-way `notify.py` approach and BotFather-token pattern from newsfeed-api.
