"""Tests for the cloudhost billing service. Uses a throwaway sqlite file and a fake
Coolify client, so nothing here touches the real database or the real Coolify."""
import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["COOLIFY_API_TOKEN"] = "test-token"
os.environ["COOLIFY_BASE_URL"] = "http://coolify.invalid"

import pytest
from fastapi.testclient import TestClient

import main
from tiers import TIERS, PLATFORM_CAPACITY


class FakeResp:
    status_code = 200
    text = "ok"


class FakeClient:
    calls: list = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def patch(self, url, headers=None, json=None):
        FakeClient.calls.append((url, json))
        return FakeResp()


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.setattr(main.httpx, "AsyncClient", FakeClient)
    FakeClient.calls = []
    with main.SessionLocal() as db:
        db.query(main.TenantApp).delete()
        db.query(main.Subscription).delete()
        db.commit()
    yield


@pytest.fixture()
def client():
    return TestClient(main.app)


def set_tier(tenant, tier, status="active"):
    with main.SessionLocal() as db:
        sub = main.get_or_create_sub(db, tenant, f"{tenant}@x.test")
        sub.tier, sub.status = tier, status
        db.commit()


def reg(client, tenant, uuid):
    return client.post("/apps/register", params={"tenant_id": tenant, "coolify_app_uuid": uuid, "app_name": uuid})


def test_free_tenant_is_blocked_at_one_app(client):
    assert reg(client, "t1", "a1").status_code == 200
    r = reg(client, "t1", "a2")
    assert r.status_code == 402 and "free" in r.json()["detail"]


def test_register_applies_tier_limits_to_coolify(client):
    set_tier("t1", "hobby")
    assert reg(client, "t1", "a1").status_code == 200
    url, body = FakeClient.calls[-1]
    assert url.endswith("/api/v1/applications/a1")
    assert body == {"limits_cpus": "0.5", "limits_memory": "512M"}


def test_unregister_keeps_apps_used_correct(client):
    set_tier("t1", "hobby")   # 3 hobby apps = 1.5 CPU / 1.5 GB, which exactly fits the platform
    for u in ("a1", "a2", "a3"):
        assert reg(client, "t1", u).status_code == 200
    assert client.delete("/apps/a2").status_code == 200
    q = client.get("/quota/t1").json()
    assert q["apps_used"] == 2
    with main.SessionLocal() as db:
        assert db.get(main.Subscription, "t1").apps_used == 2   # the stored counter must agree


def test_unregister_last_app_gives_zero_not_negative(client):
    assert reg(client, "t1", "a1").status_code == 200
    client.delete("/apps/a1")
    with main.SessionLocal() as db:
        assert db.get(main.Subscription, "t1").apps_used == 0


def test_freed_quota_can_be_used_again(client):
    assert reg(client, "t1", "a1").status_code == 200
    client.delete("/apps/a1")
    assert reg(client, "t1", "a2").status_code == 200


def test_capacity_counts_every_app_not_every_tenant(client):
    set_tier("big", "hobby")
    for u in ("p1", "p2"):
        reg(client, "big", u)
    c = client.get("/capacity").json()
    assert c["committed_memory_mb"] == 2 * TIERS["hobby"]["memory_limit_mb"]
    assert c["committed_cpu_cores"] == 2 * float(TIERS["hobby"]["cpu_limit"])
    assert c["tenants"] == 1 and c["apps"] == 2 and c["over_capacity"] is False


def test_registration_refused_when_platform_would_exceed_capacity(client):
    # one Pro app (1 CPU) + one Hobby app (0.5 CPU) = 1.5 CPU, exactly the ceiling: allowed.
    set_tier("big", "pro"); set_tier("mid", "hobby")
    assert reg(client, "big", "p1").status_code == 200
    assert reg(client, "mid", "h1").status_code == 200
    set_tier("late", "free")
    r = reg(client, "late", "f1")                     # any further app would oversell the CPU
    assert r.status_code == 503 and "capacity" in r.json()["detail"].lower()
    assert client.get("/apps/late").json()["apps"] == []        # nothing recorded
    assert not any(c[0].endswith("/f1") for c in FakeClient.calls)   # no limits pushed to Coolify
    # freeing room makes it work again
    client.delete("/apps/h1")
    assert reg(client, "late", "f1").status_code == 200


def test_capacity_check_allows_exact_fit(client):
    # exactly at the ceiling is allowed, one more byte is not
    assert PLATFORM_CAPACITY["total_memory_mb"] % TIERS["free"]["memory_limit_mb"] == 0
    n_fit = min(int(PLATFORM_CAPACITY["total_memory_mb"] // TIERS["free"]["memory_limit_mb"]),
                int(PLATFORM_CAPACITY["total_cpu_cores"] // float(TIERS["free"]["cpu_limit"])))
    for i in range(n_fit):
        assert reg(client, f"u{i}", f"x{i}").status_code == 200
    assert reg(client, "overflow", "x-over").status_code == 503


def test_past_due_tenant_counts_as_free_for_capacity(client):
    set_tier("late-payer", "pro", status="past_due")
    reg(client, "late-payer", "a1")
    c = client.get("/capacity").json()
    assert c["committed_memory_mb"] == TIERS["free"]["memory_limit_mb"]


def test_downgrade_via_webhook_resyncs_limits(client, monkeypatch):
    set_tier("t1", "pro")
    reg(client, "t1", "a1")
    FakeClient.calls = []
    event = {"type": "customer.subscription.deleted", "data": {"object": {"customer": "cus_1"}}}
    with main.SessionLocal() as db:
        db.get(main.Subscription, "t1").stripe_customer_id = "cus_1"
        db.commit()
    monkeypatch.setattr(main.stripe.Webhook, "construct_event", lambda *a, **k: event)
    assert client.post("/webhook", content=b"{}", headers={"stripe-signature": "x"}).status_code == 200
    assert client.get("/quota/t1").json()["tier"] == "free"
    assert FakeClient.calls and FakeClient.calls[-1][1] == {"limits_cpus": "0.25", "limits_memory": "256M"}


def test_webhook_rejects_bad_signature(client):
    assert client.post("/webhook", content=b"{}", headers={"stripe-signature": "bad"}).status_code == 400
