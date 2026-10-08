import asyncio
import os
import tempfile
import time
import urllib.parse
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ["COMPUTE_DB"] = f"{_tmp}/compute.db"
os.environ["PLATFORM_KEY"] = f"{_tmp}/platform_key"
os.environ["TRAEFIK_DIR"] = f"{_tmp}/traefik"
os.environ["SERVICE_KEY"] = ""

import pytest
from fastapi.testclient import TestClient

import main
from pve import PVEError

PUB = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAbCdEfGhIjKlMnOpQrStUvWxYz0123456789abcdefgh me@laptop"


class FakePVE:
    def __init__(self):
        self.vms, self.log, self.fail_clone = {}, [], False

    async def clone(self, template, newid, name, pool):
        if self.fail_clone:
            raise PVEError("clone failed")
        self.vms[newid] = {"name": name, "pool": pool, "status": "stopped", "config": {}, "disk": None}
        self.log.append(("clone", template, newid))
        return f"UPID:{newid}"

    async def wait(self, upid, timeout=300): pass

    async def configure(self, vmid, **p):
        self.vms[vmid]["config"].update(p)

    async def resize(self, vmid, disk, size):
        self.vms[vmid]["disk"] = size

    async def status(self, vmid):
        if vmid not in self.vms:
            raise PVEError("no such vm")
        return self.vms[vmid]["status"]

    async def exists(self, vmid): return vmid in self.vms

    async def action(self, vmid, name):
        self.log.append((name, vmid))
        self.vms[vmid]["status"] = {"start": "running", "stop": "stopped", "shutdown": "stopped", "reboot": "running"}[name]
        return f"UPID:{name}"

    async def delete(self, vmid):
        self.vms.pop(vmid)
        self.log.append(("delete", vmid))
        return "UPID:delete"


class FakeBilling:
    def __init__(self): self.tiers = {}
    async def tier(self, tenant): return self.tiers.get(tenant, "free")


@pytest.fixture()
def env(monkeypatch):
    f, b = FakePVE(), FakeBilling()
    monkeypatch.setattr(main, "pve", f)
    monkeypatch.setattr(main, "billing", b)

    async def up(ip, port, timeout=150): return True
    monkeypatch.setattr(main, "port_open", up)
    monkeypatch.setattr(main, "SERVICE_KEY", "")
    main.init_db()
    with main.db() as c:
        c.execute("DELETE FROM machines")
    for p in Path(os.environ["TRAEFIK_DIR"]).glob("*.yaml") if Path(os.environ["TRAEFIK_DIR"]).exists() else []:
        p.unlink()
    with TestClient(main.app) as cl:
        yield cl, f, b


def make(cl, tenant="t1", name="web1", **kw):
    body = {"tenant": tenant, "name": name, "size": "nano", "generate_key": True, **kw}
    return cl.post("/machines", json=body)


def wait_state(cl, mid, tenant, want, secs=5):
    end = time.time() + secs
    while time.time() < end:
        s = cl.get(f"/machines/{mid}", params={"tenant": tenant}).json()
        if s["state"] == want:
            return s
        time.sleep(0.05)
    raise AssertionError(f"never reached {want}: {s}")


def test_free_plan_cannot_rent(env):
    cl, f, b = env
    r = make(cl)
    assert r.status_code == 402 and "Upgrade" in r.json()["detail"]
    assert f.vms == {}


def test_create_generates_key_pair_and_boots(env):
    cl, f, b = env
    b.tiers["t1"] = "hobby"
    r = make(cl)
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["state"] == "creating" and m["ip"].startswith("10.77.0.") and m["user"] == "ubuntu"
    assert m["private_key"].startswith("-----BEGIN OPENSSH PRIVATE KEY-----")
    wait_state(cl, m["id"], "t1", "running")
    vm = f.vms[main.VMID_BASE + m["id"]]
    assert vm["pool"] == "customers" and vm["disk"] == "8G"
    c = vm["config"]
    assert c["memory"] == 512 and c["cores"] == 1 and c["balloon"] == 0
    assert c["ipconfig0"] == f"ip={m['ip']}/24,gw=10.77.0.1"
    keys = c["sshkeys"].splitlines()
    assert len(keys) == 2 and all(k.startswith("ssh-ed25519 ") for k in keys)
    assert keys[1] == asyncio.run(main.ensure_platform_key())                  # the web-terminal key rides along
    again = cl.get(f"/machines/{m['id']}", params={"tenant": "t1"}).json()
    assert "private_key" not in again                                    # shown once, never stored


def test_own_public_key_is_installed_and_no_private_key_returned(env):
    cl, f, b = env
    b.tiers["t1"] = "hobby"
    r = cl.post("/machines", json={"tenant": "t1", "name": "web1", "public_key": PUB})
    assert r.status_code == 200 and "private_key" not in r.json()
    wait_state(cl, r.json()["id"], "t1", "running")
    assert PUB in f.vms[main.VMID_BASE + r.json()["id"]]["config"]["sshkeys"]


def test_validation(env):
    cl, f, b = env
    b.tiers["t1"] = "pro"
    for bad in ("ab", "1web", "web_1", "-web", "web-", "x" * 31):
        assert make(cl, name=bad).status_code == 422, bad
    assert cl.post("/machines", json={"tenant": "t1", "name": "okname"}).status_code == 422         # no key at all
    assert cl.post("/machines", json={"tenant": "t1", "name": "okname", "public_key": "not a key"}).status_code == 422
    assert cl.post("/machines", json={"tenant": "t1", "name": "okname", "public_key": PUB + "\nssh-rsa AAAA"}).status_code == 422
    assert make(cl, size="huge").status_code == 422
    assert make(cl, image="windows").status_code == 422
    assert f.vms == {}


def test_plan_limits(env):
    cl, f, b = env
    b.tiers["t1"] = "hobby"
    assert make(cl, size="small").status_code == 402                  # hobby: nano only
    assert make(cl, name="one").status_code == 200
    assert make(cl, name="two").status_code == 402                    # hobby: one machine
    b.tiers["t1"] = "pro"
    assert make(cl, name="two", size="small").status_code == 200
    assert make(cl, name="three").status_code == 402                  # pro: two machines


def test_capacity_is_enforced(env, monkeypatch):
    cl, f, b = env
    monkeypatch.setitem(main.CAPACITY, "memory_mb", 700)
    for t in ("a", "b"):
        b.tiers[t] = "hobby"
    assert make(cl, tenant="a", name="first").status_code == 200
    r = make(cl, tenant="b", name="second")
    assert r.status_code == 503 and "capacity" in r.json()["detail"]


def test_duplicate_name_across_tenants(env):
    cl, f, b = env
    b.tiers["a"] = b.tiers["b"] = "hobby"
    assert make(cl, tenant="a", name="same").status_code == 200
    assert make(cl, tenant="b", name="same").status_code == 409


def test_ips_are_unique_and_reused_after_delete(env):
    cl, f, b = env
    for t in ("a", "b", "c"):
        b.tiers[t] = "hobby"
    ms = [make(cl, tenant=t, name=f"m-{t}").json() for t in ("a", "b", "c")]
    assert len({m["ip"] for m in ms}) == 3
    wait_state(cl, ms[1]["id"], "b", "running")
    assert cl.delete(f"/machines/{ms[1]['id']}", params={"tenant": "b"}).status_code == 200
    again = make(cl, tenant="b", name="again").json()
    assert again["ip"] == ms[1]["ip"]                                  # the freed address comes back


def test_tenants_are_isolated(env):
    cl, f, b = env
    b.tiers["a"] = b.tiers["b"] = "hobby"
    m = make(cl, tenant="a", name="mine").json()
    wait_state(cl, m["id"], "a", "running")
    q = {"tenant": "b"}
    assert cl.get(f"/machines/{m['id']}", params=q).status_code == 404
    assert cl.post(f"/machines/{m['id']}/stop", params=q).status_code == 404
    assert cl.delete(f"/machines/{m['id']}", params=q).status_code == 404
    assert cl.put(f"/machines/{m['id']}/public", params=q, json={"enabled": True, "port": 80}).status_code == 404
    assert cl.get("/machines", params=q).json()["machines"] == []
    assert len(f.vms) == 1


def test_start_stop_reboot(env):
    cl, f, b = env
    b.tiers["t1"] = "hobby"
    m = make(cl).json()
    wait_state(cl, m["id"], "t1", "running")
    assert cl.post(f"/machines/{m['id']}/stop", params={"tenant": "t1"}).status_code == 200
    assert cl.get(f"/machines/{m['id']}", params={"tenant": "t1"}).json()["state"] == "stopped"
    assert cl.post(f"/machines/{m['id']}/start", params={"tenant": "t1"}).status_code == 200
    assert cl.get(f"/machines/{m['id']}", params={"tenant": "t1"}).json()["state"] == "running"
    assert cl.post(f"/machines/{m['id']}/reboot", params={"tenant": "t1"}).status_code == 200
    assert cl.post(f"/machines/{m['id']}/explode", params={"tenant": "t1"}).status_code == 400
    assert ("shutdown", main.VMID_BASE + m["id"]) in f.log               # graceful, not a power cut


def test_actions_refused_while_creating(env, monkeypatch):
    cl, f, b = env
    b.tiers["t1"] = "hobby"

    async def never(ip, port, timeout=150):
        await asyncio.sleep(30)
    monkeypatch.setattr(main, "port_open", never)
    m = make(cl).json()
    assert cl.post(f"/machines/{m['id']}/stop", params={"tenant": "t1"}).status_code == 409


def test_delete_destroys_vm_and_frees_quota(env):
    cl, f, b = env
    b.tiers["t1"] = "hobby"
    m = make(cl).json()
    wait_state(cl, m["id"], "t1", "running")
    assert cl.delete(f"/machines/{m['id']}", params={"tenant": "t1"}).status_code == 200
    assert f.vms == {} and ("delete", main.VMID_BASE + m["id"]) in f.log
    assert make(cl, name="next").status_code == 200                      # the slot is free again
    assert ("stop", main.VMID_BASE + m["id"]) in f.log                   # a running VM is stopped before it is destroyed


def test_failed_provisioning_cleans_up_and_does_not_count(env):
    cl, f, b = env
    b.tiers["t1"] = "hobby"
    f.fail_clone = True
    m = make(cl).json()
    s = wait_state(cl, m["id"], "t1", "error")
    assert "could not be created" in s["error"] and "clone failed" not in s["error"]   # no internals leak to the customer
    f.fail_clone = False
    assert make(cl, name="retry").status_code == 200                      # a broken machine does not use up the plan


def test_failed_boot_destroys_the_half_built_vm(env, monkeypatch):
    cl, f, b = env
    b.tiers["t1"] = "hobby"

    async def dead(ip, port, timeout=150): return False
    monkeypatch.setattr(main, "port_open", dead)
    m = make(cl).json()
    wait_state(cl, m["id"], "t1", "error")
    assert f.vms == {}


def test_public_address(env):
    cl, f, b = env
    b.tiers["t1"] = "hobby"
    m = make(cl).json()
    wait_state(cl, m["id"], "t1", "running")
    r = cl.put(f"/machines/{m['id']}/public", params={"tenant": "t1"}, json={"enabled": True, "port": 8080})
    assert r.status_code == 200 and r.json()["public"]["url"] == "https://m-web1.pandeploy.dev"
    text = (Path(os.environ["TRAEFIK_DIR"]) / "vm-web1.yaml").read_text()
    assert "Host(`m-web1.pandeploy.dev`)" in text and f"http://{m['ip']}:8080" in text
    assert cl.put(f"/machines/{m['id']}/public", params={"tenant": "t1"}, json={"enabled": True, "port": 22}).status_code == 422
    assert cl.put(f"/machines/{m['id']}/public", params={"tenant": "t1"}, json={"enabled": True, "port": 70000}).status_code == 422
    r = cl.put(f"/machines/{m['id']}/public", params={"tenant": "t1"}, json={"enabled": False})
    assert r.json()["public"] is None and not (Path(os.environ["TRAEFIK_DIR"]) / "vm-web1.yaml").exists()


def test_delete_removes_public_route(env):
    cl, f, b = env
    b.tiers["t1"] = "hobby"
    m = make(cl).json()
    wait_state(cl, m["id"], "t1", "running")
    cl.put(f"/machines/{m['id']}/public", params={"tenant": "t1"}, json={"enabled": True, "port": 80})
    cl.delete(f"/machines/{m['id']}", params={"tenant": "t1"})
    assert not (Path(os.environ["TRAEFIK_DIR"]) / "vm-web1.yaml").exists()


def test_service_key_is_required_when_set(env, monkeypatch):
    cl, f, b = env
    monkeypatch.setattr(main, "SERVICE_KEY", "s3cret")
    assert cl.get("/machines", params={"tenant": "t1"}).status_code == 401
    assert cl.get("/machines", params={"tenant": "t1"}, headers={"x-service-key": "wrong"}).status_code == 401
    assert cl.get("/machines", params={"tenant": "t1"}, headers={"x-service-key": "s3cret"}).status_code == 200
    assert cl.get("/health").status_code == 200


def test_catalog_reports_capacity(env):
    cl, f, b = env
    c = cl.get("/catalog").json()
    assert c["sizes"]["nano"]["memory_mb"] == 512 and c["tiers"]["free"]["max_machines"] == 0
    assert c["capacity"]["memory_total_mb"] == main.CAPACITY["memory_mb"]


def test_restart_cleans_up_half_built_machines(env):
    cl, f, b = env
    f.vms[main.VMID_BASE + 99] = {"name": "x", "pool": "customers", "status": "running", "config": {}, "disk": None}
    with main.db() as c:
        c.execute("INSERT INTO machines(id,tenant,name,vmid,ip,size,image,state,created_at) VALUES(99,'t1','stuck',?,?,?,?,?,?)",
                  (main.VMID_BASE + 99, "10.77.0.99", "nano", "ubuntu-24.04", "creating", main.now_iso()))
    asyncio.run(main.startup())
    assert (main.VMID_BASE + 99) not in f.vms
    with main.db() as c:
        assert c.execute("SELECT state FROM machines WHERE id=99").fetchone()["state"] == "error"
