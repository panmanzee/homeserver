"""
pandeploy customer portal.

The only public-facing service. It owns accounts and sessions, and is the ONLY
thing allowed to talk to Coolify (create/start/stop/delete apps) and to the
billing service on behalf of a logged-in user. Every app operation is checked
against the portal's own ownership table, so a user can never touch an app that
is not theirs, whatever uuid they send.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import WebSocket, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

log = logging.getLogger("portal")
logging.basicConfig(level=logging.INFO)

DB_PATH = os.environ.get("PORTAL_DB", "/data/portal.db")
BILLING_URL = os.environ.get("BILLING_URL", "http://cloudhost-billing:8090")
COOLIFY_URL = os.environ.get("COOLIFY_BASE_URL", "http://host.docker.internal:8000")
COOLIFY_TOKEN = os.environ.get("COOLIFY_API_TOKEN", "")
PROJECT_UUID = os.environ.get("COOLIFY_PROJECT_UUID", "")
SERVER_UUID = os.environ.get("COOLIFY_SERVER_UUID", "")
ENV_NAME = os.environ.get("COOLIFY_ENV_NAME", "production")
COMPUTE_URL = os.environ.get("COMPUTE_URL", "http://cloudhost-compute:8110")
COMPUTE_KEY = os.environ.get("COMPUTE_KEY", "")
BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "pandeploy.dev")
INVITE_CODE = os.environ.get("INVITE_CODE", "")          # empty = open sign-up
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "1") == "1"
SESSION_DAYS = 14
STATIC_DIR = Path(__file__).parent / "static"

# Hardening for customer containers (set through Coolify's custom run options).
# Everything is dropped, then only what a normal web server needs is added back.
# NOT available through Coolify (verified on the live server): `--security-opt
# no-new-privileges` makes the deploy fail, and `--pids-limit` is silently ignored.
# Do not list either here until Coolify supports them.
RUN_OPTIONS = ("--cap-drop=ALL --cap-add=CHOWN --cap-add=SETUID --cap-add=SETGID "
               "--cap-add=NET_BIND_SERVICE --cap-add=DAC_OVERRIDE")

RESERVED = {"www", "app", "admin", "api", "billing", "coolify", "portal", "mail", "smtp", "ftp", "ns1", "ns2",
            "status", "docs", "blog", "dashboard", "login", "signup", "static", "cdn", "dev", "test", "root",
            "support", "help", "console", "git", "sample", "pandeploy", "cloudhost"}
SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{1,28}[a-z0-9]$")
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")
IMG_NAME_RE = re.compile(r"^(?:(?:ghcr\.io|quay\.io|docker\.io)/)?[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*){0,2}$")
IMG_TAG_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,127}$")

# Approximate public list prices (USD / month, 24x7) used only for the comparison widget.
# Source: AWS Lightsail container + Fargate pricing pages, checked 2026-10-06.
AWS_COMPARE = {
    "free": {"label": "Lightsail Nano (0.25 vCPU, 512 MB)", "usd": 7},
    "hobby": {"label": "Fargate 0.5 vCPU, 1 GB", "usd": 18},
    "pro": {"label": "Fargate 1 vCPU, 1 GB", "usd": 33},
}


# --------------------------------------------------------------------------- db
def _connect():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


@contextmanager
def db():
    c = _connect()
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
            pw_hash TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(
            token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS apps(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id),
            slug TEXT UNIQUE NOT NULL, coolify_uuid TEXT UNIQUE NOT NULL, image TEXT NOT NULL,
            port INTEGER NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS invoices(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id),
            description TEXT NOT NULL, amount_usd REAL NOT NULL, created_at TEXT NOT NULL);
        """)


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------- passwords
def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, salt, dk = stored.split("$")
        calc = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(calc.hex(), dk)
    except Exception:
        return False


_DUMMY_HASH = hash_password("not-a-real-password")  # equalises timing for unknown emails


# -------------------------------------------------------------- login throttling
_fails: dict[str, list[float]] = {}


def _throttle_key(request: Request, email: str) -> str:
    ip = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")
    return f"{ip}|{email.lower()}"


def throttled(key: str) -> bool:
    now = time.time()
    recent = [t for t in _fails.get(key, []) if now - t < 900]
    _fails[key] = recent
    return len(recent) >= 5


# ------------------------------------------------------------------ external APIs
class Billing:
    async def _req(self, method, path, **kw):
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.request(method, f"{BILLING_URL}{path}", **kw)
        if r.status_code >= 300:
            try:
                msg = r.json().get("detail", r.text)
            except Exception:
                msg = r.text
            raise HTTPException(r.status_code, msg)
        return r.json()

    async def tiers(self): return await self._req("GET", "/tiers")
    async def capacity(self): return await self._req("GET", "/capacity")
    async def quota(self, tenant): return await self._req("GET", f"/quota/{tenant}")
    async def register(self, tenant, uuid, name, email):
        return await self._req("POST", "/apps/register", params={"tenant_id": tenant, "coolify_app_uuid": uuid, "app_name": name, "email": email})
    async def unregister(self, uuid): return await self._req("DELETE", f"/apps/{uuid}")
    async def subscribe(self, tenant, tier, email):
        return await self._req("POST", f"/mock/subscribe/{tenant}/{tier}", params={"email": email})


class Coolify:
    def _h(self): return {"Authorization": f"Bearer {COOLIFY_TOKEN}", "Content-Type": "application/json"}

    async def _req(self, method, path, quiet=False, **kw):
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.request(method, f"{COOLIFY_URL}/api/v1{path}", headers=self._h(), **kw)
        if r.status_code >= 300:
            # quiet=True for anything that carries customer secrets: log the status only, never the body
            log.warning("coolify %s %s -> %s %s", method, path, r.status_code, "" if quiet else r.text[:200])
            raise HTTPException(502, "The hosting engine rejected the request. Try again in a moment.")
        return r.json()

    async def create(self, slug, image, tag, port, cpus, mem_mb):
        return await self._req("POST", "/applications/dockerimage", json={
            "project_uuid": PROJECT_UUID, "server_uuid": SERVER_UUID, "environment_name": ENV_NAME,
            "docker_registry_image_name": image, "docker_registry_image_tag": tag,
            "ports_exposes": str(port), "name": slug, "domains": f"https://{slug}.{BASE_DOMAIN}",
            "limits_cpus": cpus, "limits_memory": f"{mem_mb}M",
            "custom_docker_run_options": RUN_OPTIONS, "instant_deploy": False})

    async def get(self, uuid): return await self._req("GET", f"/applications/{uuid}")

    # Environment variables. Coolify keeps a second "preview" copy of every variable; we manage both.
    async def envs(self, uuid):
        return await self._req("GET", f"/applications/{uuid}/envs", quiet=True)

    async def env_delete(self, uuid, key):
        for e in await self.envs(uuid):
            if e.get("key") == key:
                await self._req("DELETE", f"/applications/{uuid}/envs/{e['uuid']}", quiet=True)

    async def env_set(self, uuid, key, value):
        await self.env_delete(uuid, key)          # replace = delete + create
        await self._req("POST", f"/applications/{uuid}/envs", quiet=True, json={
            "key": key, "value": value, "is_preview": False, "is_literal": True, "is_buildtime": False})
    async def deployments(self, uuid):
        d = await self._req("GET", f"/deployments/applications/{uuid}")
        return d.get("deployments", []) if isinstance(d, dict) else d
    async def action(self, uuid, action): return await self._req("POST", f"/applications/{uuid}/{action}")
    async def logs(self, uuid, lines=200): return await self._req("GET", f"/applications/{uuid}/logs", params={"lines": lines})
    async def delete(self, uuid):
        return await self._req("DELETE", f"/applications/{uuid}", params={"delete_configurations": "true", "delete_volumes": "true", "docker_cleanup": "true"})


class Compute:
    """Virtual machines live in the compute service; the portal only asks it on behalf of a signed-in user."""
    def _h(self): return {"x-service-key": COMPUTE_KEY}

    async def _req(self, method, path, **kw):
        try:
            async with httpx.AsyncClient(timeout=60) as c:
                r = await c.request(method, f"{COMPUTE_URL}{path}", headers=self._h(), **kw)
        except httpx.HTTPError:
            raise HTTPException(502, "The machine service is not reachable right now. Try again in a moment.")
        if r.status_code >= 300:
            if r.status_code >= 500 or r.status_code in (401, 403):
                log.warning("compute %s %s -> %s", method, path, r.status_code)
                raise HTTPException(502 if r.status_code != 503 else 503,
                                    "The machine service could not do that right now. Try again in a moment."
                                    if r.status_code != 503 else _detail(r))
            raise HTTPException(r.status_code, _detail(r))
        return r.json()

    async def catalog(self): return await self._req("GET", "/catalog")
    async def list(self, t): return await self._req("GET", "/machines", params={"tenant": t})
    async def get(self, mid, t): return await self._req("GET", f"/machines/{mid}", params={"tenant": t})
    async def create(self, t, **body): return await self._req("POST", "/machines", json={"tenant": t, **body})
    async def action(self, mid, t, a): return await self._req("POST", f"/machines/{mid}/{a}", params={"tenant": t})
    async def delete(self, mid, t): return await self._req("DELETE", f"/machines/{mid}", params={"tenant": t})
    async def public(self, mid, t, enabled, port):
        return await self._req("PUT", f"/machines/{mid}/public", params={"tenant": t}, json={"enabled": enabled, "port": port})

    async def open_terminal(self, mid, t):
        import websockets
        url = COMPUTE_URL.replace("http://", "ws://").replace("https://", "wss://")
        return await websockets.connect(f"{url}/ws/machines/{mid}/terminal?tenant={t}", additional_headers=self._h(), max_size=2**20)


def _detail(r):
    try:
        d = r.json().get("detail")
        return d if isinstance(d, str) else "That was not accepted."
    except Exception:
        return "That was not accepted."


billing = Billing()
coolify = Coolify()
compute = Compute()


# --------------------------------------------------------------------- app state
def derive_state(app_status: str | None, deployments: list) -> str:
    """building | running | failed | stopped"""
    latest = deployments[0] if deployments else {}
    dstatus = (latest.get("status") or "").lower()
    if dstatus in ("queued", "in_progress"):
        return "building"
    st = (app_status or "").lower()
    if st.startswith("running"):
        return "running"
    if st.startswith("restarting") or st.startswith("starting"):
        return "building"
    if dstatus == "failed":
        return "failed"
    return "stopped"


def tail_deploy_log(deployments: list, n=40) -> str:
    if not deployments:
        return ""
    raw = deployments[0].get("logs") or ""
    try:
        entries = json.loads(raw)
        lines = [e.get("output", "") for e in entries if not e.get("hidden") and e.get("output")]
    except Exception:
        lines = raw.splitlines()
    return "\n".join(lines[-n:])


# ------------------------------------------------------------------------- app
init_db()
app = FastAPI(title="pandeploy portal", docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def security(request: Request, call_next):
    # CSRF: mutating API calls must come from our own origin.
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.url.path.startswith("/api/"):
        origin = request.headers.get("origin")
        host = request.headers.get("host", "")
        if origin and origin.split("://", 1)[-1] != host:
            return JSONResponse({"detail": "cross-origin request refused"}, status_code=403)
        if "application/json" not in request.headers.get("content-type", "") and request.method != "DELETE" \
                and int(request.headers.get("content-length") or 0) > 0:
            return JSONResponse({"detail": "JSON body required"}, status_code=415)
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    resp.headers["Content-Security-Policy"] = ("default-src 'self'; style-src 'self' 'unsafe-inline'; "
                                               "img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
    if request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


class SignupIn(BaseModel):
    name: str
    email: str
    password: str
    invite: str = ""


class LoginIn(BaseModel):
    email: str
    password: str


class DeployIn(BaseModel):
    name: str
    image: str
    port: int = 80
    env: dict[str, str] = {}


class EnvIn(BaseModel):
    key: str
    value: str


class SubscribeIn(BaseModel):
    tier: str


def set_session(resp: Response, user_id: int):
    token = secrets.token_urlsafe(32)
    with db() as c:
        c.execute("INSERT INTO sessions VALUES(?,?,?)",
                  (hashlib.sha256(token.encode()).hexdigest(), user_id, time.time() + SESSION_DAYS * 86400))
    resp.set_cookie("pd_session", token, max_age=SESSION_DAYS * 86400, httponly=True,
                    samesite="lax", secure=COOKIE_SECURE, path="/")


def current_user(request: Request, required=True):
    token = request.cookies.get("pd_session")
    if token:
        with db() as c:
            row = c.execute(
                "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?",
                (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
        if row:
            return row
    if required:
        raise HTTPException(401, "Please sign in.")
    return None


def tenant(user) -> str:
    return f"u{user['id']}"


def public_user(u):
    return {"id": u["id"], "name": u["name"], "email": u["email"]}


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


# ------------------------------------------------------------------------- auth
@app.post("/api/signup")
def signup(body: SignupIn, request: Request, response: Response):
    name, email = body.name.strip(), body.email.strip().lower()
    if not 1 <= len(name) <= 60:
        raise HTTPException(422, "Enter your name (up to 60 characters).")
    if not EMAIL_RE.match(email):
        raise HTTPException(422, "Enter a valid email address.")
    if not 10 <= len(body.password) <= 200:
        raise HTTPException(422, "Use a password with at least 10 characters.")
    if INVITE_CODE and not hmac.compare_digest(body.invite.strip(), INVITE_CODE):
        raise HTTPException(403, "That invite code isn't valid.")
    with db() as c:
        if c.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            raise HTTPException(409, "An account with this email already exists. Sign in instead.")
        cur = c.execute("INSERT INTO users(email,name,pw_hash,created_at) VALUES(?,?,?,?)",
                        (email, name, hash_password(body.password), now_iso()))
        uid = cur.lastrowid
    set_session(response, uid)
    return {"user": {"id": uid, "name": name, "email": email}}


@app.post("/api/login")
def login(body: LoginIn, request: Request, response: Response):
    email = body.email.strip().lower()
    key = _throttle_key(request, email)
    if throttled(key):
        raise HTTPException(429, "Too many attempts. Wait 15 minutes and try again.")
    with db() as c:
        u = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    ok = verify_password(body.password, u["pw_hash"] if u else _DUMMY_HASH)
    if not (u and ok):
        _fails.setdefault(key, []).append(time.time())
        raise HTTPException(401, "Email or password is wrong.")
    _fails.pop(key, None)
    set_session(response, u["id"])
    return {"user": public_user(u)}


@app.post("/api/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get("pd_session")
    if token:
        with db() as c:
            c.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))
    response.delete_cookie("pd_session", path="/")
    return {"ok": True}


@app.get("/api/me")
async def me(request: Request):
    u = current_user(request)
    q = await billing.quota(tenant(u))
    with db() as c:
        inv = [dict(r) for r in c.execute(
            "SELECT id,description,amount_usd,created_at FROM invoices WHERE user_id=? ORDER BY id DESC LIMIT 24", (u["id"],))]
    return {"user": public_user(u), "plan": q["tier"], "status": q["status"], "apps_used": q["apps_used"],
            "limits": q["limits"], "invoices": inv, "test_mode": True}


# ------------------------------------------------------------------------ public
@app.get("/api/plans")
async def plans():
    tiers, cap = await billing.tiers(), await billing.capacity()
    total = cap["capacity"]
    smallest = min(float(t["cpu_limit"]) for t in tiers.values())
    free_cpu = max(0.0, total["total_cpu_cores"] - cap["committed_cpu_cores"])
    slots_total = int(total["total_cpu_cores"] / smallest + 1e-9)
    slots_free = int(free_cpu / smallest + 1e-9)
    out = []
    for key, t in tiers.items():
        out.append({"id": key, "name": t["name"], "price": t["price_usd_monthly"], "max_apps": t["max_apps"],
                    "cpu": t["cpu_limit"], "memory_mb": t["memory_limit_mb"], "custom_domain": t["custom_domain"],
                    "sleeps": t["sleep_after_inactive_min"], "aws": AWS_COMPARE.get(key)})
    return {"plans": out, "rack": {"slots_total": slots_total, "slots_free": slots_free, "apps": cap["apps"]},
            "aws_checked": "2026-10-06"}


@app.get("/api/config")
def config():
    return {"invite_required": bool(INVITE_CODE), "base_domain": BASE_DOMAIN, "test_mode": True}


@app.get("/api/slug-check")
def slug_check(slug: str = ""):
    s = slug.strip().lower()
    if not SLUG_RE.match(s):
        return {"ok": False, "reason": "Use 3–30 lowercase letters, numbers or hyphens, starting with a letter."}
    if s in RESERVED or s.startswith("m-"):
        return {"ok": False, "reason": "That name is reserved."}
    with db() as c:
        taken = c.execute("SELECT 1 FROM apps WHERE slug=?", (s,)).fetchone()
    return {"ok": not taken, "reason": "" if not taken else "That name is taken.", "url": f"https://{s}.{BASE_DOMAIN}"}


# -------------------------------------------------------------------------- billing (test mode)
@app.post("/api/subscribe")
async def subscribe(body: SubscribeIn, request: Request):
    u = current_user(request)
    tiers = await billing.tiers()
    if body.tier not in tiers:
        raise HTTPException(400, "Unknown plan.")
    q = await billing.quota(tenant(u))
    if q["tier"] == body.tier:
        raise HTTPException(409, "You're already on this plan.")
    await billing.subscribe(tenant(u), body.tier, u["email"])
    price = tiers[body.tier]["price_usd_monthly"]
    if price > 0:
        with db() as c:
            c.execute("INSERT INTO invoices(user_id,description,amount_usd,created_at) VALUES(?,?,?,?)",
                      (u["id"], f"{tiers[body.tier]['name']} plan (test payment)", price, now_iso()))
    return {"plan": body.tier}


# ------------------------------------------------------------------------- apps
def owned_app(user, app_id: int):
    with db() as c:
        row = c.execute("SELECT * FROM apps WHERE id=? AND user_id=?", (app_id, user["id"])).fetchone()
    if not row:
        raise HTTPException(404, "App not found.")
    return row


async def describe(row) -> dict:
    uuid = row["coolify_uuid"]
    try:
        a, deps = await asyncio.gather(coolify.get(uuid), coolify.deployments(uuid))
        state = derive_state(a.get("status"), deps)
        extra = {"error_tail": tail_deploy_log(deps, 12)} if state == "failed" else {}
    except HTTPException:
        state, extra = "unknown", {}
    # Coolify reports "exited" for a few seconds between the build finishing and the container
    # starting; treat a brand-new app in that gap as still starting rather than stopped.
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(row["created_at"])).total_seconds()
    except ValueError:
        age = 9999
    if state == "stopped" and age < 90:
        state = "building"
    return {"id": row["id"], "name": row["slug"], "url": f"https://{row['slug']}.{BASE_DOMAIN}",
            "image": row["image"], "port": row["port"], "state": state, "created_at": row["created_at"], **extra}


@app.get("/api/apps")
async def list_apps(request: Request):
    u = current_user(request)
    with db() as c:
        rows = c.execute("SELECT * FROM apps WHERE user_id=? ORDER BY id DESC", (u["id"],)).fetchall()
    return {"apps": await asyncio.gather(*[describe(r) for r in rows])}


@app.get("/api/apps/{app_id}")
async def get_app(app_id: int, request: Request):
    return await describe(owned_app(current_user(request), app_id))


ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
ENV_MAX_VARS = 50
ENV_MAX_VALUE = 4096
ENV_RESERVED_PREFIXES = ("COOLIFY_", "SERVICE_", "LD_")
ENV_RESERVED = {"PATH", "HOME", "HOSTNAME"}


def check_env(key: str, value: str) -> str:
    """Return the cleaned key, or raise 422 with a message the customer can act on."""
    key = key.strip()
    if not ENV_KEY_RE.match(key):
        raise HTTPException(422, "Variable names use letters, numbers and underscores, and cannot start with a number.")
    if key.upper().startswith(ENV_RESERVED_PREFIXES) or key.upper() in ENV_RESERVED:
        raise HTTPException(422, f"{key} is reserved by the platform. Pick another name.")
    if len(value) > ENV_MAX_VALUE or "\x00" in value:
        raise HTTPException(422, f"Values can be up to {ENV_MAX_VALUE} characters.")
    # The hosting engine writes values into a quoted .env file; a single quote or a line break would break
    # that file and fail every deploy of the app (found in live testing), so refuse them with a clear reason.
    if "'" in value or "\n" in value or "\r" in value:
        raise HTTPException(422, "Values cannot contain a single quote (') or a line break. URL-encode them if you need those characters.")
    return key


def parse_image(raw: str):
    raw = raw.strip().lower()
    if "@" in raw or " " in raw or len(raw) > 200:
        raise HTTPException(422, "Enter an image like nginx:alpine or ghcr.io/you/app:1.0.")
    name, _, tag = raw.partition(":") if raw.count(":") <= 1 else (None, None, None)
    if name is None or not IMG_NAME_RE.match(name) or (tag and not IMG_TAG_RE.match(tag)):
        raise HTTPException(422, "Enter an image like nginx:alpine or ghcr.io/you/app:1.0.")
    # Docker treats a first path part containing a dot as a registry host. Only approved
    # registries are allowed, so customers cannot make the server pull from arbitrary hosts.
    parts = name.split("/")
    if "." in parts[0] or ":" in parts[0]:
        if parts[0] not in ("ghcr.io", "quay.io", "docker.io"):
            raise HTTPException(422, "Images can come from Docker Hub, ghcr.io or quay.io.")
    elif len(parts) > 2:
        raise HTTPException(422, "Enter an image like nginx:alpine or user/app:1.0.")
    return name, tag or "latest"


@app.post("/api/apps")
async def deploy(body: DeployIn, request: Request):
    u = current_user(request)
    slug = body.name.strip().lower()
    chk = slug_check(slug)
    if not chk["ok"]:
        raise HTTPException(422, chk["reason"])
    if not 1 <= body.port <= 65535:
        raise HTTPException(422, "Port must be between 1 and 65535.")
    image, tag = parse_image(body.image)
    if len(body.env) > ENV_MAX_VARS:
        raise HTTPException(422, f"You can set up to {ENV_MAX_VARS} variables.")
    env = {check_env(k, v): v for k, v in body.env.items()}

    q = await billing.quota(tenant(u))
    if q["apps_used"] >= q["limits"]["max_apps"]:
        raise HTTPException(402, f"Your {q['limits']['name']} plan includes {q['limits']['max_apps']} app"
                                 f"{'s' if q['limits']['max_apps'] != 1 else ''}. Upgrade to deploy more.")

    created = await coolify.create(slug, image, tag, body.port, q["limits"]["cpu_limit"], q["limits"]["memory_limit_mb"])
    uuid = created["uuid"]
    try:
        await billing.register(tenant(u), uuid, slug, u["email"])
    except HTTPException:
        await coolify.delete(uuid)
        raise
    try:
        with db() as c:
            c.execute("INSERT INTO apps(user_id,slug,coolify_uuid,image,port,created_at) VALUES(?,?,?,?,?,?)",
                      (u["id"], slug, uuid, f"{image}:{tag}", body.port, now_iso()))
    except sqlite3.IntegrityError:
        await billing.unregister(uuid)
        await coolify.delete(uuid)
        raise HTTPException(409, "That name was just taken. Pick another.")
    try:
        for k, v in env.items():
            await coolify.env_set(uuid, k, v)
    except HTTPException:
        # the app exists but would start without its configuration: say so instead of running it half-set
        raise HTTPException(502, "The app was created, but its variables could not be saved. Open Variables, add them, then start it.")
    await coolify.action(uuid, "start")
    with db() as c:
        row = c.execute("SELECT * FROM apps WHERE slug=?", (slug,)).fetchone()
    return {"app": {"id": row["id"], "name": slug, "url": f"https://{slug}.{BASE_DOMAIN}", "state": "building",
                    "image": f"{image}:{tag}", "port": body.port, "created_at": row["created_at"]}}


@app.post("/api/apps/{app_id}/{action}")
async def app_action(app_id: int, action: str, request: Request):
    u = current_user(request)
    if action not in ("start", "stop", "restart"):
        raise HTTPException(400, "Unknown action.")
    row = owned_app(u, app_id)
    await coolify.action(row["coolify_uuid"], action)
    return {"ok": True}


@app.get("/api/apps/{app_id}/env")
async def list_env(app_id: int, request: Request):
    row = owned_app(current_user(request), app_id)
    keys = sorted({e["key"] for e in await coolify.envs(row["coolify_uuid"]) if not e.get("is_preview")})
    return {"env": [{"key": k} for k in keys], "limit": ENV_MAX_VARS}


@app.put("/api/apps/{app_id}/env")
async def put_env(app_id: int, body: EnvIn, request: Request):
    row = owned_app(current_user(request), app_id)
    key = check_env(body.key, body.value)
    existing = {e["key"] for e in await coolify.envs(row["coolify_uuid"]) if not e.get("is_preview")}
    if key not in existing and len(existing) >= ENV_MAX_VARS:
        raise HTTPException(422, f"You can set up to {ENV_MAX_VARS} variables.")
    await coolify.env_set(row["coolify_uuid"], key, body.value)
    return {"ok": True, "restart_needed": True}


@app.delete("/api/apps/{app_id}/env/{key}")
async def delete_env(app_id: int, key: str, request: Request):
    row = owned_app(current_user(request), app_id)
    if not ENV_KEY_RE.match(key):
        raise HTTPException(422, "Unknown variable.")
    await coolify.env_delete(row["coolify_uuid"], key)
    return {"ok": True, "restart_needed": True}


@app.get("/api/apps/{app_id}/logs")
async def app_logs(app_id: int, request: Request, kind: str = "runtime"):
    row = owned_app(current_user(request), app_id)
    if kind == "build":
        return {"logs": tail_deploy_log(await coolify.deployments(row["coolify_uuid"]), 80) or "No build output yet."}
    try:
        out = await coolify.logs(row["coolify_uuid"], 200)
        return {"logs": (out.get("logs") or out.get("message") or "").strip() or "No output yet."}
    except HTTPException:
        return {"logs": "The app isn't running, so there are no live logs."}


@app.delete("/api/apps/{app_id}")
async def delete_app(app_id: int, request: Request):
    u = current_user(request)
    row = owned_app(u, app_id)
    await coolify.delete(row["coolify_uuid"])
    try:
        await billing.unregister(row["coolify_uuid"])
    except HTTPException as e:
        if e.status_code != 404:
            raise
    with db() as c:
        c.execute("DELETE FROM apps WHERE id=?", (app_id,))
    return {"ok": True}


# --------------------------------------------------------------------- virtual machines
class MachineIn(BaseModel):
    name: str
    size: str = "nano"
    public_key: str = ""


class PublicIn(BaseModel):
    enabled: bool
    port: int = 80


@app.get("/api/machines")
async def list_machines(request: Request):
    u = current_user(request)
    t = tenant(u)
    mine, catalog, q = await asyncio.gather(compute.list(t), compute.catalog(), billing.quota(t))
    rule = catalog["tiers"].get(q["tier"], {"max_machines": 0, "sizes": []})
    return {"machines": mine["machines"], "plan": q["tier"], "rule": rule, "sizes": catalog["sizes"],
            "capacity": catalog["capacity"]}


@app.post("/api/machines")
async def create_machine(body: MachineIn, request: Request):
    u = current_user(request)
    key = body.public_key.strip()
    # No key given: the platform generates one and discards the private half. Customers use the web
    # terminal; a key they paste lets their own tools log in from inside the machine network.
    created = await compute.create(tenant(u), name=body.name, size=body.size, public_key=key, generate_key=not key)
    created.pop("private_key", None)
    return {"machine": created}


@app.get("/api/machines/{mid}")
async def get_machine(mid: int, request: Request):
    return await compute.get(mid, tenant(current_user(request)))


@app.post("/api/machines/{mid}/{action}")
async def machine_action(mid: int, action: str, request: Request):
    return await compute.action(mid, tenant(current_user(request)), action)


@app.delete("/api/machines/{mid}")
async def delete_machine(mid: int, request: Request):
    return await compute.delete(mid, tenant(current_user(request)))


@app.put("/api/machines/{mid}/public")
async def machine_public(mid: int, body: PublicIn, request: Request):
    return await compute.public(mid, tenant(current_user(request)), body.enabled, body.port)


@app.websocket("/api/machines/{mid}/terminal")
async def machine_terminal(ws: WebSocket, mid: int):
    """Browser terminal: relays the signed-in owner's keystrokes to the compute service's SSH session."""
    origin, host = ws.headers.get("origin"), ws.headers.get("host", "")
    if origin and origin.split("://", 1)[-1] != host:          # cross-site WebSocket hijacking guard
        await ws.close(code=4403)
        return
    try:
        u = current_user(ws)
        t = tenant(u)
        m = await compute.get(mid, t)                          # also proves the machine belongs to this user
    except HTTPException:
        await ws.close(code=4401)
        return
    await ws.accept()
    if m["state"] != "running":
        await ws.send_text("\r\n[the machine is not running]\r\n")
        await ws.close()
        return
    try:
        up = await compute.open_terminal(mid, t)
    except Exception:
        await ws.send_text("\r\n[could not reach the machine]\r\n")
        await ws.close()
        return

    async def down():                      # machine -> browser
        try:
            async for data in up:
                await (ws.send_bytes(data) if isinstance(data, bytes) else ws.send_text(data))
        except Exception:
            pass

    pump = asyncio.create_task(down())
    try:
        while not pump.done():
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if msg.get("bytes") is not None:
                await up.send(msg["bytes"])
            elif msg.get("text") is not None:
                await up.send(msg["text"][:4096])
    except Exception:
        pass
    finally:
        pump.cancel()
        try:
            await up.close()
            await ws.close()
        except Exception:
            pass


# ------------------------------------------------------------------------ static
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/{path:path}")
def spa(path: str):
    if path.startswith("api/"):
        raise HTTPException(404, "Not found.")
    return FileResponse(STATIC_DIR / "index.html")
