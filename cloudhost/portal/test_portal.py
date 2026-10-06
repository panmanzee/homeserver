import os
import tempfile

os.environ["PORTAL_DB"] = tempfile.mktemp(suffix=".db")
os.environ["COOKIE_SECURE"] = "0"

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import main

TIERS = {
    "free": {"name": "Free", "price_usd_monthly": 0, "max_apps": 1, "cpu_limit": "0.25", "memory_limit_mb": 256,
             "custom_domain": False, "sleep_after_inactive_min": 30},
    "hobby": {"name": "Hobby", "price_usd_monthly": 5, "max_apps": 3, "cpu_limit": "0.5", "memory_limit_mb": 512,
              "custom_domain": True, "sleep_after_inactive_min": None},
}


class FakeBilling:
    def __init__(self):
        self.tier, self.apps, self.fail_register = {}, {}, False

    async def tiers(self): return TIERS
    async def capacity(self):
        return {"apps": len(self.apps), "committed_cpu_cores": 0.25 * len(self.apps), "committed_memory_mb": 0,
                "capacity": {"total_cpu_cores": 1.5, "total_memory_mb": 2048}}
    async def quota(self, t):
        tier = self.tier.get(t, "free")
        used = sum(1 for v in self.apps.values() if v == t)
        return {"tier": tier, "status": "active", "apps_used": used, "limits": TIERS[tier]}
    async def register(self, t, uuid, name, email):
        if self.fail_register:
            raise HTTPException(503, "Platform is at capacity right now.")
        self.apps[uuid] = t
    async def unregister(self, uuid): self.apps.pop(uuid, None)
    async def subscribe(self, t, tier, email):
        used = sum(1 for v in self.apps.values() if v == t)
        if used > TIERS[tier]["max_apps"]:
            raise HTTPException(409, "Delete some apps first.")
        self.tier[t] = tier


class FakeCoolify:
    def __init__(self):
        self.apps, self.n, self.calls = {}, 0, []

    async def create(self, slug, image, tag, port, cpus, mem):
        self.n += 1
        u = f"uuid{self.n}"
        self.apps[u] = {"status": "exited:unhealthy", "slug": slug, "cpus": cpus, "mem": mem, "image": f"{image}:{tag}"}
        return {"uuid": u}
    async def get(self, uuid): return {"status": self.apps[uuid]["status"]}
    async def deployments(self, uuid): return [{"status": self.apps[uuid].get("dep", "finished")}]
    async def action(self, uuid, action): self.calls.append((uuid, action)); return {}
    async def logs(self, uuid, lines=200): return {"logs": "hello from the app"}
    async def delete(self, uuid): self.apps.pop(uuid, None)


@pytest.fixture()
def env(monkeypatch):
    b, c = FakeBilling(), FakeCoolify()
    monkeypatch.setattr(main, "billing", b)
    monkeypatch.setattr(main, "coolify", c)
    monkeypatch.setattr(main, "INVITE_CODE", "")
    main._fails.clear()
    with main.db() as conn:
        for t in ("sessions", "apps", "invoices", "users"):
            conn.execute(f"DELETE FROM {t}")
    return b, c


def client():
    return TestClient(main.app)


def signup(cl, email="a@example.com", name="Ann", pw="correct horse battery"):
    return cl.post("/api/signup", json={"name": name, "email": email, "password": pw})


def test_signup_login_logout_me(env):
    cl = client()
    assert signup(cl).status_code == 200
    me = cl.get("/api/me").json()
    assert me["user"]["email"] == "a@example.com" and me["plan"] == "free"
    cl.post("/api/logout")
    assert cl.get("/api/me").status_code == 401
    assert cl.post("/api/login", json={"email": "A@Example.com", "password": "correct horse battery"}).status_code == 200
    assert cl.get("/api/me").status_code == 200


def test_signup_validation(env):
    cl = client()
    assert signup(cl, pw="short").status_code == 422
    assert signup(cl, email="nope").status_code == 422
    assert signup(cl).status_code == 200
    assert signup(client()).status_code == 409


def test_password_is_hashed_not_stored(env):
    signup(client())
    with main.db() as c:
        h = c.execute("SELECT pw_hash FROM users").fetchone()[0]
    assert h.startswith("scrypt$") and "correct horse" not in h


def test_wrong_password_and_throttle(env):
    cl = client()
    signup(cl)
    cl.post("/api/logout")
    for _ in range(5):
        assert cl.post("/api/login", json={"email": "a@example.com", "password": "wrongwrongwrong"}).status_code == 401
    r = cl.post("/api/login", json={"email": "a@example.com", "password": "correct horse battery"})
    assert r.status_code == 429


def test_invite_code(env, monkeypatch):
    monkeypatch.setattr(main, "INVITE_CODE", "letmein")
    cl = client()
    assert signup(cl).status_code == 403
    r = cl.post("/api/signup", json={"name": "A", "email": "b@example.com", "password": "correct horse battery", "invite": "letmein"})
    assert r.status_code == 200


def test_cross_origin_post_refused(env):
    r = client().post("/api/login", json={"email": "a@b.co", "password": "x" * 12},
                      headers={"origin": "https://evil.example"})
    assert r.status_code == 403


def test_requires_login(env):
    cl = client()
    for path in ("/api/me", "/api/apps"):
        assert cl.get(path).status_code == 401
    assert cl.post("/api/apps", json={"name": "abc", "image": "nginx"}).status_code == 401


def test_slug_rules(env):
    cl = client()
    assert cl.get("/api/slug-check?slug=Hello").json()["ok"] is True  # normalised to lowercase
    assert cl.get("/api/slug-check?slug=admin").json()["ok"] is False
    assert cl.get("/api/slug-check?slug=a").json()["ok"] is False
    assert cl.get("/api/slug-check?slug=-bad-").json()["ok"] is False


def test_deploy_flow_and_limits(env):
    b, c = env
    cl = client()
    signup(cl)
    r = cl.post("/api/apps", json={"name": "myapp", "image": "nginx:alpine", "port": 80})
    assert r.status_code == 200, r.text
    assert r.json()["app"]["url"] == "https://myapp.pandeploy.dev" and r.json()["app"]["state"] == "building"
    assert c.apps["uuid1"]["cpus"] == "0.25" and c.apps["uuid1"]["mem"] == 256  # free-plan limits applied at creation
    assert ("uuid1", "start") in c.calls
    assert cl.get("/api/slug-check?slug=myapp").json()["ok"] is False
    r = cl.post("/api/apps", json={"name": "second", "image": "nginx"})
    assert r.status_code == 402 and "Upgrade" in r.json()["detail"]
    assert len(c.apps) == 1  # nothing created behind the refusal


def test_image_validation(env):
    cl = client()
    signup(cl)
    for bad in ("nginx@sha256:abc", "has space", "UPPER/../x", "evil.io/x/y", "a:b:c", "-bad"):
        assert cl.post("/api/apps", json={"name": "okname", "image": bad}).status_code == 422, bad
    assert cl.post("/api/apps", json={"name": "okname", "image": "ghcr.io/me/app:1.0", "port": 8080}).status_code == 200


def test_capacity_refusal_rolls_back_coolify(env):
    b, c = env
    b.fail_register = True
    cl = client()
    signup(cl)
    r = cl.post("/api/apps", json={"name": "myapp", "image": "nginx"})
    assert r.status_code == 503
    assert c.apps == {}  # the half-created Coolify app was removed
    assert cl.get("/api/apps").json()["apps"] == []


def test_tenants_are_isolated(env):
    b, c = env
    a, other = client(), client()
    signup(a, "a@example.com")
    signup(other, "b@example.com", "Bob")
    app_id = a.post("/api/apps", json={"name": "annsapp", "image": "nginx"}).json()["app"]["id"]
    assert other.get("/api/apps").json()["apps"] == []
    for method, path in (("get", f"/api/apps/{app_id}"), ("post", f"/api/apps/{app_id}/stop"),
                         ("get", f"/api/apps/{app_id}/logs"), ("delete", f"/api/apps/{app_id}")):
        assert getattr(other, method)(path).status_code == 404, path
    assert "uuid1" in c.apps  # still alive
    assert a.get(f"/api/apps/{app_id}").status_code == 200


def test_delete_frees_quota_and_name(env):
    b, c = env
    cl = client()
    signup(cl)
    app_id = cl.post("/api/apps", json={"name": "myapp", "image": "nginx"}).json()["app"]["id"]
    assert cl.delete(f"/api/apps/{app_id}").status_code == 200
    assert c.apps == {} and b.apps == {}
    assert cl.get("/api/me").json()["apps_used"] == 0
    assert cl.post("/api/apps", json={"name": "myapp", "image": "nginx"}).status_code == 200


def test_state_mapping(env):
    b, c = env
    cl = client()
    signup(cl)
    app_id = cl.post("/api/apps", json={"name": "myapp", "image": "nginx"}).json()["app"]["id"]
    u = "uuid1"
    c.apps[u].update(status="exited:unhealthy", dep="in_progress")
    assert cl.get(f"/api/apps/{app_id}").json()["state"] == "building"
    c.apps[u].update(status="running:unknown", dep="finished")
    assert cl.get(f"/api/apps/{app_id}").json()["state"] == "running"
    c.apps[u].update(status="exited:unhealthy", dep="failed")
    assert cl.get(f"/api/apps/{app_id}").json()["state"] == "failed"
    c.apps[u].update(status="exited:unhealthy", dep="finished")
    with main.db() as conn:  # past the startup grace period
        conn.execute("UPDATE apps SET created_at='2020-01-01T00:00:00+00:00'")
    assert cl.get(f"/api/apps/{app_id}").json()["state"] == "stopped"


def test_subscribe_upgrade_invoice_and_blocked_downgrade(env):
    b, c = env
    cl = client()
    signup(cl)
    assert cl.post("/api/subscribe", json={"tier": "free"}).status_code == 409  # already on it
    assert cl.post("/api/subscribe", json={"tier": "nope"}).status_code == 400
    assert cl.post("/api/subscribe", json={"tier": "hobby"}).status_code == 200
    me = cl.get("/api/me").json()
    assert me["plan"] == "hobby" and me["invoices"][0]["amount_usd"] == 5
    for n in ("one", "two"):
        assert cl.post("/api/apps", json={"name": f"app-{n}", "image": "nginx"}).status_code == 200
    assert cl.post("/api/subscribe", json={"tier": "free"}).status_code == 409  # 2 apps > free's 1


def test_plans_public_with_rack(env):
    r = client().get("/api/plans").json()
    assert [p["id"] for p in r["plans"]] == ["free", "hobby"]
    assert r["rack"]["slots_total"] == 6 and r["rack"]["slots_free"] == 6


def test_new_app_in_startup_gap_reads_as_building_not_stopped(env):
    b, c = env
    cl = client()
    signup(cl)
    app_id = cl.post("/api/apps", json={"name": "myapp", "image": "nginx"}).json()["app"]["id"]
    c.apps["uuid1"].update(status="exited:unhealthy", dep="finished")  # the gap right after the build
    assert cl.get(f"/api/apps/{app_id}").json()["state"] == "building"
    with main.db() as conn:  # an old app that is genuinely stopped
        conn.execute("UPDATE apps SET created_at='2020-01-01T00:00:00+00:00'")
    assert cl.get(f"/api/apps/{app_id}").json()["state"] == "stopped"
