# Proxmox host setup for customer virtual machines

These are the host-side pieces behind the compute service. They are applied by hand once; nothing here is
secret. (The API token secret lives only in `/root/.compute.env` on the cloudhost server.)

| File | Where it goes | What it does |
|---|---|---|
| `vmbr1.interfaces` | `/etc/network/interfaces.d/vmbr1` | the private VM network, 10.77.0.1/24, no physical port |
| `vm-net.nft` | `/etc/cloudhost/vm-net.nft` | NAT out, block everything private, block VM-to-VM, host offers nothing to VMs |
| `cloudhost-vm-net.service` | `/etc/systemd/system/` | loads those rules at boot (only its own nft tables) |
| `vmnet-route.service` | in the cloudhost LXC | route 10.77.0.0/24 via the Proxmox host so the service can reach the VMs |
| `proxmox-setup.sh` | run once on the host | template VM, pool, role, user and token |

Host also needs `net.ipv4.ip_forward=1` (`/etc/sysctl.d/99-cloudhost-vm.conf`).

Check the isolation any time: SSH into a customer VM and try to reach 192.168.0.1, the host on 22 or 8006, and
another VM. All must fail, and `curl https://example.com` must work.
