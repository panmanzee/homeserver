"""cloudhost compute service: rent a virtual machine.

Customers get a real Ubuntu VM on the Proxmox host (KVM), on a private network that can reach the
internet and nothing else. This service owns the Proxmox API token; the portal talks to this service.

  create -> clone the template, inject SSH keys + a fixed IP with cloud-init, resize disk, boot
  start / stop / reboot / delete
  web terminal (SSH over a WebSocket, so it works from a browser behind any firewall)
  optional public web address:  https://m-<name>.<base domain>  ->  the VM's port
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import asyncssh
import httpx
from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from pve import PVE, PVEError
from sizes import CAPACITY, GATEWAY, IMAGES, IP_POOL, SIZES, TIER_RULES

log = logging.getLogger("compute")
logging.basicConfig(level=logging.INFO)

DB_PATH = os.environ.get("COMPUTE_DB", "/data/compute.db")
SERVICE_KEY = os.environ.get("SERVICE_KEY", "")
BILLING_URL = os.environ.get("BILLING_URL", "http://cloudhost-billing:8090")
BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "pandeploy.dev")
TRAEFIK_DIR = Path(os.environ.get("TRAEFIK_DIR", "/traefik"))
PLATFORM_KEY_PATH = Path(os.environ.get("PLATFORM_KEY", "/data/platform_key"))
POOL = os.environ.get("PVE_POOL", "customers")
VMID_BASE = 20000

NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,28}[a-z0-9]$")
KEY_RE = re.compile(r"^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(256|384|521)) [A-Za-z0-9+/=]{20,800}( [^\r\n]{0,80})?$")
LIVE_STATES = ("creating", "running", "stopped", "stopping", "deleting")     # states that use quota and resources

pve = PVE(os.environ.get("PVE_URL", "https://192.168.0.101:8006"), os.environ.get("PVE_TOKEN_ID", ""),
          os.environ.get("PVE_TOKEN_SECRET", ""), os.environ.get("PVE_NODE", "pve"),
          os.environ.get("PVE_CA") or None)
_alloc_lock = asyncio.Lock()


# --------------------------------------------------------------------------- storage
@contextmanager
def db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS machines(
            id INTEGER PRIMARY KEY AUTOINCREMENT, tenant TEXT NOT NULL, name TEXT UNIQUE NOT NULL,
            vmid INTEGER UNIQUE NOT NULL, ip TEXT UNIQUE NOT NULL, size TEXT NOT NULL, image TEXT NOT NULL,
            state TEXT NOT NULL, error TEXT NOT NULL DEFAULT '', public_port INTEGER, created_at TEXT NOT NULL)""")


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- platform key
async def ensure_platform_key() -> str:
    """The key the web terminal uses. Created once, kept in the data volume, installed in every VM."""
    if not PLATFORM_KEY_PATH.exists():
        key = asyncssh.generate_private_key("ssh-ed25519", comment="pandeploy-console")
        PLATFORM_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        PLATFORM_KEY_PATH.write_bytes(key.export_private_key("openssh"))
        PLATFORM_KEY_PATH.chmod(0o600)
    key = asyncssh.read_private_key(str(PLATFORM_KEY_PATH))
    return key.export_public_key("openssh").decode().strip()


# --------------------------------------------------------------------------- billing
class Billing:
    async def tier(self, tenant: str) -> str:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{BILLING_URL}/quota/{tenant}")
        if r.status_code >= 300:
            raise HTTPException(503, "Billing is unavailable right now. Try again in a moment.")
        return r.json().get("tier", "free")


billing = Billing()


# --------------------------------------------------------------------------- app
app = FastAPI(title="cloudhost compute", docs_url=None, redoc_url=None, openapi_url=None)


def guard(key: str | None):
    if SERVICE_KEY and key != SERVICE_KEY:
        raise HTTPException(401, "Unauthorized")


class CreateIn(BaseModel):
    tenant: str
    name: str
    size: str = "nano"
    image: str = "ubuntu-24.04"
    public_key: str = ""
    generate_key: bool = False


class PublicIn(BaseModel):
    enabled: bool
    port: int = 80


def row_to_dict(r, live: str | None = None) -> dict:
    state = r["state"]
    if state in ("running", "stopped") and live:
        state = "running" if live == "running" else "stopped"
    s = SIZES[r["size"]]
    return {"id": r["id"], "name": r["name"], "state": state, "error": r["error"], "ip": r["ip"],
            "size": r["size"], "specs": s, "image": r["image"], "image_label": IMAGES[r["image"]]["label"],
            "user": IMAGES[r["image"]]["user"], "created_at": r["created_at"],
            "public": ({"url": f"https://m-{r['name']}.{BASE_DOMAIN}", "port": r["public_port"]} if r["public_port"] else None)}


def get_row(mid: int, tenant: str):
    with db() as c:
        r = c.execute("SELECT * FROM machines WHERE id=? AND tenant=?", (mid, tenant)).fetchone()
    if not r:
        raise HTTPException(404, "Machine not found.")
    return r


async def describe(r) -> dict:
    live = None
    if r["state"] in ("running", "stopped"):
        try:
            live = await pve.status(r["vmid"])
        except PVEError:
            live = None
    return row_to_dict(r, live)


def usage() -> tuple[int, int, int]:
    with db() as c:
        rows = c.execute(f"SELECT size FROM machines WHERE state IN ({','.join('?' * len(LIVE_STATES))})", LIVE_STATES).fetchall()
    mem = sum(SIZES[r["size"]]["memory_mb"] for r in rows)
    disk = sum(SIZES[r["size"]]["disk_gb"] for r in rows)
    return len(rows), mem, disk


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/catalog")
def catalog(tenant: str = "", x_service_key: str | None = Header(None)):
    guard(x_service_key)
    n, mem, disk = usage()
    return {"sizes": SIZES, "images": {k: {"label": v["label"]} for k, v in IMAGES.items()}, "tiers": TIER_RULES,
            "capacity": {"machines": n, "memory_mb": mem, "memory_total_mb": CAPACITY["memory_mb"],
                         "disk_gb": disk, "disk_total_gb": CAPACITY["disk_gb"]}}


@app.get("/machines")
async def list_machines(tenant: str, x_service_key: str | None = Header(None)):
    guard(x_service_key)
    with db() as c:
        rows = c.execute("SELECT * FROM machines WHERE tenant=? ORDER BY id DESC", (tenant,)).fetchall()
    return {"machines": await asyncio.gather(*[describe(r) for r in rows])}


@app.get("/machines/{mid}")
async def one_machine(mid: int, tenant: str, x_service_key: str | None = Header(None)):
    guard(x_service_key)
    return await describe(get_row(mid, tenant))


def free_ip(c) -> str | None:
    used = {r["ip"] for r in c.execute("SELECT ip FROM machines").fetchall()}
    prefix, rng = IP_POOL
    return next((prefix + str(i) for i in rng if prefix + str(i) not in used), None)


@app.post("/machines")
async def create_machine(body: CreateIn, x_service_key: str | None = Header(None)):
    guard(x_service_key)
    name = body.name.strip().lower()
    if not NAME_RE.match(name):
        raise HTTPException(422, "Use 3-30 lowercase letters, numbers or hyphens, starting with a letter.")
    if body.size not in SIZES:
        raise HTTPException(422, "Unknown size.")
    if body.image not in IMAGES:
        raise HTTPException(422, "Unknown image.")
    pub = body.public_key.strip()
    if pub and not KEY_RE.match(pub):
        raise HTTPException(422, "That does not look like an SSH public key. It should start with ssh-ed25519 or ssh-rsa.")
    if not pub and not body.generate_key:
        raise HTTPException(422, "Add your SSH public key, or let us generate a key pair for you.")

    tier = await billing.tier(body.tenant)
    rule = TIER_RULES.get(tier, TIER_RULES["free"])
    if rule["max_machines"] == 0:
        raise HTTPException(402, f"Virtual machines are not part of the {tier.title()} plan. Upgrade to rent one.")
    if body.size not in rule["sizes"]:
        raise HTTPException(402, f"The {tier.title()} plan includes {', '.join(rule['sizes'])} machines. Upgrade for a bigger one.")

    private_pem = None
    if not pub:                                    # generate a key pair; the private half is shown once and never stored
        key = asyncssh.generate_private_key("ssh-ed25519", comment=f"pandeploy-{name}")
        private_pem = key.export_private_key("openssh").decode()
        pub = key.export_public_key("openssh").decode().strip()

    async with _alloc_lock:
        with db() as c:
            mine = c.execute(f"SELECT COUNT(*) FROM machines WHERE tenant=? AND state IN ({','.join('?' * len(LIVE_STATES))})",
                             (body.tenant, *LIVE_STATES)).fetchone()[0]
            if mine >= rule["max_machines"]:
                raise HTTPException(402, f"Your {tier.title()} plan includes {rule['max_machines']} machine"
                                         f"{'s' if rule['max_machines'] != 1 else ''}. Upgrade to rent more.")
            if c.execute("SELECT 1 FROM machines WHERE name=?", (name,)).fetchone():
                raise HTTPException(409, "That name is taken.")
            n, mem, disk = usage()
            s = SIZES[body.size]
            if mem + s["memory_mb"] > CAPACITY["memory_mb"] or disk + s["disk_gb"] > CAPACITY["disk_gb"]:
                raise HTTPException(503, "The server is at capacity for virtual machines right now. Try again later.")
            ip = free_ip(c)
            if not ip:
                raise HTTPException(503, "No addresses are free right now.")
            cur = c.execute("INSERT INTO machines(tenant,name,vmid,ip,size,image,state,created_at) VALUES(?,?,?,?,?,?,?,?)",
                            (body.tenant, name, 0, ip, body.size, body.image, "creating", now_iso()))
            mid = cur.lastrowid
            c.execute("UPDATE machines SET vmid=? WHERE id=?", (VMID_BASE + mid, mid))
    platform_pub = await ensure_platform_key()
    asyncio.create_task(provision(mid, f"{pub}\n{platform_pub}"))
    out = await describe(get_row(mid, body.tenant))
    if private_pem:
        out["private_key"] = private_pem
    return out


def set_state(mid: int, state: str, error: str = ""):
    with db() as c:
        c.execute("UPDATE machines SET state=?, error=? WHERE id=?", (state, error, mid))


async def port_open(ip: str, port: int, timeout: float = 150) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            _, w = await asyncio.wait_for(asyncio.open_connection(ip, port), 3)
            w.close()
            return True
        except Exception:
            await asyncio.sleep(3)
    return False


async def provision(mid: int, ssh_keys: str):
    with db() as c:
        r = c.execute("SELECT * FROM machines WHERE id=?", (mid,)).fetchone()
    vmid, s, img = r["vmid"], SIZES[r["size"]], IMAGES[r["image"]]
    t0 = time.time()

    def step(what):
        log.info("machine %s: %s (%.0fs)", r["name"], what, time.time() - t0)

    try:
        await pve.wait(await pve.clone(img["template_vmid"], vmid, f"vm-{r['name']}", POOL))
        step("cloned")
        await pve.configure(vmid, memory=s["memory_mb"], cores=s["vcpu"], balloon=0, onboot=0,
                            ciuser=img["user"], sshkeys=ssh_keys, ipconfig0=f"ip={r['ip']}/24,gw={GATEWAY}",
                            nameserver="1.1.1.1 8.8.8.8", description=f"customer machine {r['name']} (tenant {r['tenant']})")
        await pve.resize(vmid, "scsi0", f"{s['disk_gb']}G")
        step("configured and resized")
        await pve.wait(await pve.action(vmid, "start"))
        step("started")
        if not await port_open(r["ip"], 22):
            raise PVEError("the machine started but did not answer on SSH")
        step("answering on SSH")
        set_state(mid, "running")
        log.info("machine %s ready at %s", r["name"], r["ip"])
    except Exception as exc:
        log.error("provisioning %s failed: %s", r["name"], exc)
        try:
            if await pve.exists(vmid):
                try:
                    await pve.wait(await pve.action(vmid, "stop"), 60)
                except PVEError:
                    pass
                await pve.wait(await pve.delete(vmid))
        except Exception as cleanup:
            log.error("cleanup of %s failed: %s", r["name"], cleanup)
        set_state(mid, "error", "The machine could not be created. Delete it and try again.")


SNAP_RE = re.compile(r"^[a-z][a-z0-9-]{0,30}$")
SNAP_LIMIT = {"free": 0, "hobby": 1, "pro": 2}


class SnapIn(BaseModel):
    name: str


async def snap_rows(vmid: int) -> list[dict]:
    rows = await pve.snapshots(vmid)
    return [{"name": r["name"], "created": r.get("snaptime")} for r in rows if r.get("name") != "current"]


@app.get("/machines/{mid}/snapshots")
async def list_snapshots(mid: int, tenant: str, x_service_key: str | None = Header(None)):
    guard(x_service_key)
    r = get_row(mid, tenant)
    tier = await billing.tier(tenant)
    try:
        snaps = await snap_rows(r["vmid"]) if r["state"] in ("running", "stopped") else []
    except PVEError:
        snaps = []
    return {"snapshots": snaps, "limit": SNAP_LIMIT.get(tier, 0)}


@app.post("/machines/{mid}/snapshots")
async def create_snapshot(mid: int, body: SnapIn, tenant: str, x_service_key: str | None = Header(None)):
    guard(x_service_key)
    r = get_row(mid, tenant)
    name = body.name.strip().lower()
    if not SNAP_RE.match(name):
        raise HTTPException(422, "Use lowercase letters, numbers and hyphens, starting with a letter.")
    if r["state"] not in ("running", "stopped"):
        raise HTTPException(409, "The machine is not ready.")
    tier = await billing.tier(tenant)
    limit = SNAP_LIMIT.get(tier, 0)
    if limit == 0:
        raise HTTPException(402, f"Snapshots are not part of the {tier.title()} plan. Upgrade to use them.")
    try:
        have = await snap_rows(r["vmid"])
        if any(x["name"] == name for x in have):
            raise HTTPException(409, "You already have a snapshot with that name.")
        if len(have) >= limit:
            raise HTTPException(402, f"Your {tier.title()} plan keeps {limit} snapshot{'s' if limit != 1 else ''}. Delete one first.")
        await pve.wait(await pve.snapshot(r["vmid"], name), 120)
    except PVEError as exc:
        log.warning("snapshot %s failed: %s", r["name"], exc)
        raise HTTPException(502, "The virtualization host could not take the snapshot. Try again.")
    return {"snapshots": await snap_rows(r["vmid"]), "limit": limit}


@app.post("/machines/{mid}/snapshots/{snap}/restore")
async def restore_snapshot(mid: int, snap: str, tenant: str, x_service_key: str | None = Header(None)):
    guard(x_service_key)
    r = get_row(mid, tenant)
    if r["state"] not in ("running", "stopped") or not SNAP_RE.match(snap):
        raise HTTPException(409, "The machine is not ready.")
    try:
        if not any(x["name"] == snap for x in await snap_rows(r["vmid"])):
            raise HTTPException(404, "Snapshot not found.")
        if await pve.status(r["vmid"]) == "running":
            await pve.wait(await pve.action(r["vmid"], "stop"), 90)
        await pve.wait(await pve.rollback(r["vmid"], snap), 180)
        await pve.wait(await pve.action(r["vmid"], "start"), 60)
    except PVEError as exc:
        log.warning("restore %s failed: %s", r["name"], exc)
        raise HTTPException(502, "The restore failed. The machine was not changed if it is still running; try again.")
    return {"ok": True}


@app.delete("/machines/{mid}/snapshots/{snap}")
async def delete_snapshot(mid: int, snap: str, tenant: str, x_service_key: str | None = Header(None)):
    guard(x_service_key)
    r = get_row(mid, tenant)
    if not SNAP_RE.match(snap):
        raise HTTPException(404, "Snapshot not found.")
    try:
        await pve.wait(await pve.delete_snapshot(r["vmid"], snap), 120)
    except PVEError:
        raise HTTPException(502, "Could not delete the snapshot. Try again.")
    return {"snapshots": await snap_rows(r["vmid"])}


@app.post("/machines/{mid}/{action}")
async def machine_action(mid: int, action: str, tenant: str, x_service_key: str | None = Header(None)):
    guard(x_service_key)
    if action not in ("start", "stop", "reboot"):
        raise HTTPException(400, "Unknown action.")
    r = get_row(mid, tenant)
    if r["state"] in ("creating", "deleting", "error"):
        raise HTTPException(409, f"The machine is {r['state']}; wait or delete it.")
    try:
        await pve.action(r["vmid"], {"start": "start", "stop": "shutdown", "reboot": "reboot"}[action])
    except PVEError as exc:
        log.warning("%s failed: %s", action, exc)
        raise HTTPException(502, "The virtualization host rejected that. Try again in a moment.")
    return {"ok": True}


def route_file(name: str) -> Path:
    return TRAEFIK_DIR / f"vm-{name}.yaml"


def write_route(name: str, ip: str, port: int):
    """Traefik dynamic config: https://m-<name>.<domain> -> http://<vm ip>:<port>"""
    TRAEFIK_DIR.mkdir(parents=True, exist_ok=True)
    key = f"vm-{name}"
    route_file(name).write_text(
        f"http:\n  routers:\n    {key}:\n      rule: Host(`m-{name}.{BASE_DOMAIN}`)\n      entryPoints:\n        - https\n"
        f"      service: {key}\n      tls: {{}}\n  services:\n    {key}:\n      loadBalancer:\n        servers:\n"
        f"          - url: http://{ip}:{port}\n")


@app.put("/machines/{mid}/public")
async def set_public(mid: int, body: PublicIn, tenant: str, x_service_key: str | None = Header(None)):
    guard(x_service_key)
    r = get_row(mid, tenant)
    if r["state"] not in ("running", "stopped"):
        raise HTTPException(409, "The machine is not ready.")
    if body.enabled:
        if not 1 <= body.port <= 65535 or body.port == 22:
            raise HTTPException(422, "Choose a web port between 1 and 65535 (not 22).")
        write_route(r["name"], r["ip"], body.port)
        port = body.port
    else:
        route_file(r["name"]).unlink(missing_ok=True)
        port = None
    with db() as c:
        c.execute("UPDATE machines SET public_port=? WHERE id=?", (port, mid))
    return await describe(get_row(mid, tenant))


@app.delete("/machines/{mid}")
async def delete_machine(mid: int, tenant: str, x_service_key: str | None = Header(None)):
    guard(x_service_key)
    r = get_row(mid, tenant)
    if r["state"] == "deleting":
        raise HTTPException(409, "Already being deleted.")
    set_state(mid, "deleting")
    route_file(r["name"]).unlink(missing_ok=True)
    try:
        if await pve.exists(r["vmid"]):
            if await pve.status(r["vmid"]) == "running":
                await pve.wait(await pve.action(r["vmid"], "stop"), 90)
            await pve.wait(await pve.delete(r["vmid"]))
    except PVEError as exc:
        log.error("delete %s failed: %s", r["name"], exc)
        set_state(mid, r["state"] if r["state"] != "creating" else "error")
        raise HTTPException(502, "The virtualization host could not remove the machine. Try again.")
    with db() as c:
        c.execute("DELETE FROM machines WHERE id=?", (mid,))
    return {"ok": True}


# --------------------------------------------------------------------------- web terminal
@app.websocket("/ws/machines/{mid}/terminal")
async def terminal(ws: WebSocket, mid: int, tenant: str):
    if SERVICE_KEY and ws.headers.get("x-service-key") != SERVICE_KEY:
        await ws.close(code=4401)
        return
    try:
        r = get_row(mid, tenant)
    except HTTPException:
        await ws.close(code=4404)
        return
    await ws.accept()
    if r["state"] != "running":
        await ws.send_text("\r\n[the machine is not running]\r\n")
        await ws.close()
        return
    try:
        conn = await asyncssh.connect(r["ip"], username=IMAGES[r["image"]]["user"], known_hosts=None,
                                      client_keys=[str(PLATFORM_KEY_PATH)], connect_timeout=10)
    except Exception as exc:
        log.warning("terminal connect to %s failed: %s", r["name"], exc)
        await ws.send_text("\r\n[could not connect to the machine]\r\n")
        await ws.close()
        return
    proc = await conn.create_process(term_type="xterm-256color", term_size=(100, 30), encoding=None)

    async def out():
        while True:
            data = await proc.stdout.read(4096)
            if not data:
                break
            await ws.send_bytes(data)

    reader = asyncio.create_task(out())
    try:
        while not reader.done():
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if msg.get("bytes") is not None:
                proc.stdin.write(msg["bytes"])
            elif msg.get("text"):
                t = msg["text"]
                if t.startswith("resize:"):
                    try:
                        cols, rows = (int(x) for x in t[7:].split("x"))
                        proc.change_terminal_size(max(10, min(cols, 400)), max(5, min(rows, 200)))
                    except ValueError:
                        pass
                else:
                    proc.stdin.write(t.encode())
    except WebSocketDisconnect:
        pass
    finally:
        reader.cancel()
        proc.close()
        conn.close()
        try:
            await ws.close()
        except Exception:
            pass


# --------------------------------------------------------------------------- startup
@app.on_event("startup")
async def startup():
    init_db()
    await ensure_platform_key()
    # a restart in the middle of creating a machine leaves it half-built: clean those up
    with db() as c:
        stuck = c.execute("SELECT id, vmid FROM machines WHERE state IN ('creating','deleting')").fetchall()
    for r in stuck:
        try:
            if await pve.exists(r["vmid"]):
                try:
                    await pve.wait(await pve.action(r["vmid"], "stop"), 60)
                except PVEError:
                    pass
                await pve.wait(await pve.delete(r["vmid"]))
        except Exception as exc:
            log.error("startup cleanup of %s failed: %s", r["vmid"], exc)
        set_state(r["id"], "error", "Interrupted by a restart. Delete it and try again.")
