"""
Subscription tier definitions for the cloudhost PaaS.
Resource limits are honest for the underlying hardware:
  cloudhost LXC = 2 cores / 3GB RAM / 50GB disk total, shared across ALL tenants.
  These tiers are deliberately modest — oversell would just crash the box.
"""

TIERS = {
    "free": {
        "name": "Free",
        "price_usd_monthly": 0,
        "stripe_price_id": None,  # no Stripe object needed for free tier
        "max_apps": 1,
        "cpu_limit": "0.25",       # docker --cpus
        "memory_limit_mb": 256,
        "disk_limit_mb": 512,
        "custom_domain": False,
        "sleep_after_inactive_min": 30,  # spin down idle free apps to save resources
    },
    "hobby": {
        "name": "Hobby",
        "price_usd_monthly": 5,
        "stripe_price_id": None,  # filled in once Stripe product/price is created
        "max_apps": 3,
        "cpu_limit": "0.5",
        "memory_limit_mb": 512,
        "disk_limit_mb": 2048,
        "custom_domain": True,
        "sleep_after_inactive_min": None,
    },
    "pro": {
        "name": "Pro",
        "price_usd_monthly": 15,
        "stripe_price_id": None,
        "max_apps": 10,
        "cpu_limit": "1.0",
        "memory_limit_mb": 1024,
        "disk_limit_mb": 5120,
        "custom_domain": True,
        "sleep_after_inactive_min": None,
    },
}

# Hard ceiling: total resources sellable across ALL tenants combined.
# Prevents oversubscription crashing the shared box.
PLATFORM_CAPACITY = {
    "total_cpu_cores": 1.5,     # leave 0.5 core headroom for Coolify + Docker itself
    "total_memory_mb": 2048,    # leave ~1GB headroom out of 3GB container limit
    "total_disk_mb": 30720,     # leave ~13GB headroom out of 50GB
}
