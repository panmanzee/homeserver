# Compute service (virtual machines)

Rent a whole Ubuntu virtual machine. The portal's **Machines** page talks to this service; this service
talks to Proxmox. Customers never see Proxmox.

## How it works

```
 browser ──► portal ──► compute service ──► Proxmox API ──► KVM virtual machine (10.77.0.x)
                              │
                              └─ SSH (web terminal) / Traefik route (public web address)
```

- **Create:** clone the Ubuntu template (a thin-LVM linked clone, about 2 seconds), set CPU, RAM, a fixed IP and the
  SSH keys with cloud-init, resize the disk, boot. A machine is ready in about 35 seconds.
- **Plans:** Free: none. Hobby: 1 Nano. Pro: 2, up to Small (`sizes.py`). Total RAM and disk sold are capped to what the host can spare.
- **Web terminal:** the browser opens a WebSocket to the portal, which relays to this service, which opens SSH
  to the machine with a platform key that every machine trusts (like AWS Session Manager).
- **Public web address:** optional. Writes a Traefik route so `https://m-<name>.pandeploy.dev` reaches a port on the machine.
- **State:** a small SQLite file. A restart cleans up machines that were half-built.

## Network and isolation (the part to read before trusting it)

Customer machines live on `vmbr1` (10.77.0.0/24), a bridge with no physical port. See `../infra/proxmox/`.

| From a customer VM to | Result |
|---|---|
| the internet | allowed (NAT) |
| your home or dorm LAN, the router, other servers | blocked |
| the Proxmox host (SSH, web UI) | blocked |
| the tailnet | blocked |
| another customer VM | blocked (bridge-level rule) |

Only the cloudhost server (192.168.0.102) can open connections into the VM network.
Anti-spoofing: each VM's network port may only send traffic from the one IP it was given (nft bridge rule +
`cloudhost-vm-guard.sh`, which keeps the allowed (port, IP) list in step with the running VMs every 2 seconds).
A VM that forges another VM's address is dropped. Tested live.

Snapshots: Hobby keeps 1 and Pro keeps 2 restore points per machine (thin-LVM snapshots; restore stops, rolls back, starts).

## Configuration (environment)

`PVE_URL`, `PVE_TOKEN_ID`, `PVE_TOKEN_SECRET`, `PVE_NODE`, `PVE_CA` (path to Proxmox's root CA), `PVE_POOL`,
`SERVICE_KEY` (shared with the portal), `BILLING_URL`, `BASE_DOMAIN`, `TRAEFIK_DIR`.

The Proxmox API token has a custom role limited to the `customers` pool, the template, one storage and the
`vmbr1` bridge. It cannot touch the other VMs, containers or the host.

## Run it

```
docker run -d --name cloudhost-compute --network cloudhost-internal --user 9999:9999 \
  -v compute-data:/data -v /data/coolify/proxy/dynamic:/traefik -v /root/pve-ca.pem:/pve-ca.pem:ro \
  --env-file /root/.compute.env --read-only --tmpfs /tmp --cap-drop=ALL --security-opt no-new-privileges \
  --memory 192m cloudhost-compute
```

Tests: `pip install -r requirements.txt pytest && pytest` (19 tests, no Proxmox needed).
