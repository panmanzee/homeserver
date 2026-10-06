"""Local UI preview with fake Coolify/billing (never shipped in the image)."""
import os, tempfile, time
os.environ["PORTAL_DB"] = tempfile.mktemp(suffix=".db"); os.environ["COOKIE_SECURE"] = "0"
import uvicorn, main
from fastapi import HTTPException
T = {"free": {"name": "Free", "price_usd_monthly": 0, "max_apps": 1, "cpu_limit": "0.25", "memory_limit_mb": 256, "custom_domain": False, "sleep_after_inactive_min": 30},
     "hobby": {"name": "Hobby", "price_usd_monthly": 5, "max_apps": 3, "cpu_limit": "0.5", "memory_limit_mb": 512, "custom_domain": True, "sleep_after_inactive_min": None},
     "pro": {"name": "Pro", "price_usd_monthly": 15, "max_apps": 10, "cpu_limit": "1.0", "memory_limit_mb": 1024, "custom_domain": True, "sleep_after_inactive_min": None}}
class B:
    tier, apps = {}, {}
    async def tiers(s): return T
    async def capacity(s): return {"apps": len(s.apps) + 1, "committed_cpu_cores": 0.25 * (len(s.apps) + 1), "committed_memory_mb": 0, "capacity": {"total_cpu_cores": 1.5, "total_memory_mb": 2048}}
    async def quota(s, t):
        k = s.tier.get(t, "free"); return {"tier": k, "status": "active", "apps_used": sum(v == t for v in s.apps.values()), "limits": T[k]}
    async def register(s, t, u, n, e): s.apps[u] = t
    async def unregister(s, u): s.apps.pop(u, None)
    async def subscribe(s, t, k, e):
        if sum(v == t for v in s.apps.values()) > T[k]["max_apps"]: raise HTTPException(409, "Delete some apps first.")
        s.tier[t] = k
class C:
    apps, n = {}, 0
    async def create(s, slug, image, tag, port, cpus, mem):
        s.n += 1; u = f"u{s.n}"; s.apps[u] = {"t": None, "slug": slug}; return {"uuid": u}
    async def get(s, u):
        a = s.apps[u]; up = a["t"] and time.time() - a["t"] > 7 and not a.get("stopped")
        return {"status": "running:healthy" if up else "exited:unhealthy"}
    async def deployments(s, u):
        a = s.apps[u]; building = a["t"] and time.time() - a["t"] <= 7
        return [{"status": "in_progress" if building else "finished"}]
    async def action(s, u, act):
        a = s.apps[u]
        if act in ("start", "restart"): a["t"] = time.time(); a["stopped"] = False
        if act == "stop": a["stopped"] = True
        return {}
    async def logs(s, u, lines=200): return {"logs": "10.0.0.1 - GET / 200\n10.0.0.1 - GET /favicon.ico 404"}
    async def delete(s, u): s.apps.pop(u, None)
main.billing, main.coolify = B(), C()
uvicorn.run(main.app, host="127.0.0.1", port=8101, log_level="warning")
