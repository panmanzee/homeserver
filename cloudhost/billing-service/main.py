"""
cloudhost billing service - FastAPI + Stripe + Coolify enforcement.

Responsibilities:
  1. Create Stripe Checkout sessions for tier upgrades.
  2. Receive Stripe webhooks (checkout.session.completed, invoice.paid,
     customer.subscription.deleted, invoice.payment_failed) and update
     the local `subscriptions` table - the single source of truth for
     "what resource quota does this tenant currently have".
  3. Expose /quota/{tenant_id} for the deploy pipeline to check
     enforcement limits before allowing a new deploy or app.
  4. NEW: talk to the Coolify API directly - register tenant apps,
     enforce per-tier CPU/memory limits on Coolify applications, and
     block deploys that would exceed a tenant's app-count quota.
"""
import os
import logging
from datetime import datetime, timezone

import httpx
import stripe
from fastapi import FastAPI, Request, HTTPException, Depends
from sqlalchemy import create_engine, Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, Session, relationship

from tiers import TIERS, PLATFORM_CAPACITY

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("billing")

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:////data/billing.db")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8090")

COOLIFY_API_TOKEN = os.environ.get("COOLIFY_API_TOKEN", "")
COOLIFY_BASE_URL = os.environ.get("COOLIFY_BASE_URL", "http://host.docker.internal:8000")

stripe.api_key = STRIPE_SECRET_KEY

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Subscription(Base):
    __tablename__ = "subscriptions"
    tenant_id = Column(String, primary_key=True)
    email = Column(String, nullable=False)
    tier = Column(String, default="free", nullable=False)
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    status = Column(String, default="active")
    apps_used = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class TenantApp(Base):
    """Maps a Coolify application UUID to the tenant that owns it, so we
    can enforce quotas and apply per-tier resource limits."""
    __tablename__ = "tenant_apps"
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, ForeignKey("subscriptions.tenant_id"), nullable=False)
    coolify_app_uuid = Column(String, nullable=False, unique=True)
    app_name = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


Base.metadata.create_all(engine)

app = FastAPI(title="cloudhost billing")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def coolify_headers():
    return {"Authorization": f"Bearer {COOLIFY_API_TOKEN}", "Content-Type": "application/json"}


def get_or_create_sub(db: Session, tenant_id: str, email: str = "") -> Subscription:
    sub = db.get(Subscription, tenant_id)
    if not sub:
        sub = Subscription(tenant_id=tenant_id, email=email or f"{tenant_id}@unknown")
        db.add(sub)
        db.commit()
        db.refresh(sub)
    return sub


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/tiers")
def list_tiers():
    return TIERS


@app.post("/checkout/{tenant_id}/{tier}")
def create_checkout(tenant_id: str, tier: str, email: str, db: Session = Depends(get_db)):
    """Create a Stripe Checkout session to upgrade a tenant to a paid tier."""
    if tier not in TIERS or tier == "free":
        raise HTTPException(400, "invalid tier for checkout")
    tier_conf = TIERS[tier]
    if not tier_conf["stripe_price_id"]:
        raise HTTPException(500, f"stripe_price_id not configured for tier '{tier}' yet")

    sub = db.get(Subscription, tenant_id)
    stripe_customer_id = sub.stripe_customer_id if sub else None
    if not stripe_customer_id:
        customer = stripe.Customer.create(email=email, metadata={"tenant_id": tenant_id})
        stripe_customer_id = customer.id

    session = stripe.checkout.Session.create(
        customer=stripe_customer_id,
        mode="subscription",
        line_items=[{"price": tier_conf["stripe_price_id"], "quantity": 1}],
        success_url=f"{PUBLIC_BASE_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{PUBLIC_BASE_URL}/billing/cancel",
        metadata={"tenant_id": tenant_id, "tier": tier},
    )
    return {"checkout_url": session.url}


@app.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        log.warning(f"webhook signature check failed: {e}")
        raise HTTPException(400, "invalid signature")

    etype = event["type"]
    obj = event["data"]["object"]
    log.info(f"stripe event: {etype}")

    if etype == "checkout.session.completed":
        tenant_id = obj["metadata"]["tenant_id"]
        tier = obj["metadata"]["tier"]
        sub = db.get(Subscription, tenant_id) or Subscription(tenant_id=tenant_id, email=obj.get("customer_details", {}).get("email", ""))
        sub.tier = tier
        sub.status = "active"
        sub.stripe_customer_id = obj["customer"]
        sub.stripe_subscription_id = obj["subscription"]
        db.merge(sub)
        db.commit()
        # Re-apply resource limits to all this tenant's existing apps for the new tier
        await _resync_tenant_limits(tenant_id, tier, db)

    elif etype == "invoice.payment_failed":
        cust_id = obj["customer"]
        sub = db.query(Subscription).filter_by(stripe_customer_id=cust_id).first()
        if sub:
            sub.status = "past_due"
            db.commit()

    elif etype == "customer.subscription.deleted":
        cust_id = obj["customer"]
        sub = db.query(Subscription).filter_by(stripe_customer_id=cust_id).first()
        if sub:
            sub.tier = "free"
            sub.status = "active"
            db.commit()
            await _resync_tenant_limits(sub.tenant_id, "free", db)

    return {"received": True}


MOCK_BILLING = os.environ.get("MOCK_BILLING", "") == "1"


@app.post("/mock/subscribe/{tenant_id}/{tier}")
async def mock_subscribe(tenant_id: str, tier: str, email: str = "", db: Session = Depends(get_db)):
    """TEST MODE ONLY (MOCK_BILLING=1): switch a tenant's tier without any payment.
    Stands in for the Stripe webhook until Stripe is connected. Refuses to
    downgrade below the number of apps the tenant already runs."""
    if not MOCK_BILLING:
        raise HTTPException(404, "mock billing is disabled")
    if tier not in TIERS:
        raise HTTPException(400, "unknown tier")
    sub = get_or_create_sub(db, tenant_id, email)
    used = db.query(TenantApp).filter_by(tenant_id=tenant_id).count()
    if used > TIERS[tier]["max_apps"]:
        raise HTTPException(
            409,
            f"You have {used} apps but {TIERS[tier]['name']} allows {TIERS[tier]['max_apps']}. "
            f"Delete {used - TIERS[tier]['max_apps']} first.",
        )
    sub.tier, sub.status = tier, "active"
    db.commit()
    await _resync_tenant_limits(tenant_id, tier, db)
    return {"tenant_id": tenant_id, "tier": tier, "status": "active", "mock": True}


@app.get("/quota/{tenant_id}")
def get_quota(tenant_id: str, db: Session = Depends(get_db)):
    """Used by the deploy pipeline to enforce per-tenant resource limits."""
    sub = db.get(Subscription, tenant_id)
    tier_name = sub.tier if sub and sub.status == "active" else "free"
    tier_conf = TIERS[tier_name]
    apps_used = db.query(TenantApp).filter_by(tenant_id=tenant_id).count()
    return {
        "tenant_id": tenant_id,
        "tier": tier_name,
        "status": sub.status if sub else "active",
        "apps_used": apps_used,
        "limits": tier_conf,
    }


def effective_tier(sub: Subscription | None) -> str:
    """Tier whose limits actually apply: anything not 'active' is treated as free."""
    return sub.tier if sub and sub.status == "active" else "free"


def committed_resources(db: Session) -> tuple[float, int, int]:
    """(cpu cores, memory MB, app count) committed across every registered app.
    Tier limits are per app, so each app counts once at its owner's effective tier."""
    cpu, mem, n = 0.0, 0, 0
    for app_row in db.query(TenantApp).all():
        t = TIERS[effective_tier(db.get(Subscription, app_row.tenant_id))]
        cpu += float(t["cpu_limit"])
        mem += t["memory_limit_mb"]
        n += 1
    return cpu, mem, n


@app.get("/capacity")
def platform_capacity(db: Session = Depends(get_db)):
    """Sanity check: resources committed across all registered apps vs. the hard
    platform ceiling. register_app refuses new apps that would exceed it."""
    cpu, mem, n_apps = committed_resources(db)
    tenants = db.query(TenantApp.tenant_id).distinct().count()
    return {
        "tenants": tenants,
        "apps": n_apps,
        "committed_cpu_cores": cpu,
        "committed_memory_mb": mem,
        "capacity": PLATFORM_CAPACITY,
        "over_capacity": cpu > PLATFORM_CAPACITY["total_cpu_cores"]
        or mem > PLATFORM_CAPACITY["total_memory_mb"],
    }


# ---------------------------------------------------------------------------
# Coolify integration: the actual billing <-> deploy wiring
# ---------------------------------------------------------------------------

@app.post("/apps/register")
async def register_app(tenant_id: str, coolify_app_uuid: str, app_name: str, email: str = "", db: Session = Depends(get_db)):
    """Call this right after creating a Coolify application (via the
    Coolify API) for a given tenant. Enforces the tenant's app-count quota
    BEFORE allowing the registration, and immediately applies the tenant's
    tier resource limits (CPU/memory) to the new Coolify app.

    This is the piece that makes billing real: a tenant on the Free tier
    physically cannot deploy a 6th app or run an app with more than
    256MB RAM, because we set those limits directly on the Coolify
    application object via its API.
    """
    sub = get_or_create_sub(db, tenant_id, email)
    tier_name = effective_tier(sub)
    tier_conf = TIERS[tier_name]

    current_count = db.query(TenantApp).filter_by(tenant_id=tenant_id).count()
    if current_count >= tier_conf["max_apps"]:
        raise HTTPException(
            402,
            f"App limit reached for tier '{tier_name}' ({tier_conf['max_apps']} apps). "
            f"Upgrade your plan to deploy more apps.",
        )

    # Platform-wide ceiling: the box is small, so refuse an app that would oversell it.
    cpu_now, mem_now, _ = committed_resources(db)
    if (cpu_now + float(tier_conf["cpu_limit"]) > PLATFORM_CAPACITY["total_cpu_cores"]
            or mem_now + tier_conf["memory_limit_mb"] > PLATFORM_CAPACITY["total_memory_mb"]):
        raise HTTPException(503, "Platform is at capacity right now. Please try again later.")

    # Apply real resource limits on the Coolify application
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.patch(
            f"{COOLIFY_BASE_URL}/api/v1/applications/{coolify_app_uuid}",
            headers=coolify_headers(),
            json={
                "limits_cpus": tier_conf["cpu_limit"],
                "limits_memory": f"{tier_conf['memory_limit_mb']}M",
            },
        )
        if r.status_code >= 300:
            log.warning(f"failed to set Coolify limits for {coolify_app_uuid}: {r.status_code} {r.text}")

    record = TenantApp(tenant_id=tenant_id, coolify_app_uuid=coolify_app_uuid, app_name=app_name)
    db.add(record)
    sub.apps_used = current_count + 1
    db.commit()

    return {
        "registered": True,
        "tenant_id": tenant_id,
        "coolify_app_uuid": coolify_app_uuid,
        "tier": tier_name,
        "limits_applied": {"cpus": tier_conf["cpu_limit"], "memory_mb": tier_conf["memory_limit_mb"]},
        "apps_used": current_count + 1,
        "apps_allowed": tier_conf["max_apps"],
    }


@app.delete("/apps/{coolify_app_uuid}")
def unregister_app(coolify_app_uuid: str, db: Session = Depends(get_db)):
    """Call this when a tenant deletes an app in Coolify, to free up their quota."""
    record = db.query(TenantApp).filter_by(coolify_app_uuid=coolify_app_uuid).first()
    if not record:
        raise HTTPException(404, "app not registered")
    tenant_id = record.tenant_id
    db.delete(record)
    db.flush()  # make the delete visible to the count below
    sub = db.get(Subscription, tenant_id)
    if sub:
        sub.apps_used = db.query(TenantApp).filter_by(tenant_id=tenant_id).count()
    db.commit()
    return {"unregistered": True, "coolify_app_uuid": coolify_app_uuid}


@app.get("/apps/{tenant_id}")
def list_tenant_apps(tenant_id: str, db: Session = Depends(get_db)):
    """List all Coolify apps a tenant owns, for their dashboard/billing page."""
    apps = db.query(TenantApp).filter_by(tenant_id=tenant_id).all()
    return {
        "tenant_id": tenant_id,
        "apps": [{"coolify_app_uuid": a.coolify_app_uuid, "app_name": a.app_name, "created_at": a.created_at.isoformat()} for a in apps],
    }


async def _resync_tenant_limits(tenant_id: str, tier_name: str, db: Session):
    """After a tier change (upgrade/downgrade/cancel), re-apply the new
    resource limits to every app this tenant already has deployed."""
    tier_conf = TIERS[tier_name]
    apps = db.query(TenantApp).filter_by(tenant_id=tenant_id).all()
    async with httpx.AsyncClient(timeout=15) as client:
        for a in apps:
            try:
                await client.patch(
                    f"{COOLIFY_BASE_URL}/api/v1/applications/{a.coolify_app_uuid}",
                    headers=coolify_headers(),
                    json={
                        "limits_cpus": tier_conf["cpu_limit"],
                        "limits_memory": f"{tier_conf['memory_limit_mb']}M",
                    },
                )
            except Exception as e:
                log.warning(f"resync limits failed for {a.coolify_app_uuid}: {e}")
