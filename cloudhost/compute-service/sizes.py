"""What customers can rent, and who may rent what. Sized for one small home server."""

SIZES = {
    "nano": {"label": "Nano", "vcpu": 1, "memory_mb": 512, "disk_gb": 8},
    "small": {"label": "Small", "vcpu": 1, "memory_mb": 1024, "disk_gb": 16},
}

IMAGES = {
    "ubuntu-24.04": {"label": "Ubuntu 24.04 LTS", "template_vmid": 9000, "user": "ubuntu"},
}

# machines allowed per billing plan, and the largest size each plan may use
TIER_RULES = {
    "free": {"max_machines": 0, "sizes": []},
    "hobby": {"max_machines": 1, "sizes": ["nano"]},
    "pro": {"max_machines": 2, "sizes": ["nano", "small"]},
}

# Everything sold together must fit on the host: the Proxmox box has ~8 GB RAM shared with the
# cloudhost containers, workhub and Proxmox itself, so customer VMs get a fixed slice.
CAPACITY = {"memory_mb": 2560, "disk_gb": 60}

IP_POOL = ("10.77.0.", range(10, 251))      # 10.77.0.10 - 10.77.0.250
GATEWAY = "10.77.0.1"
