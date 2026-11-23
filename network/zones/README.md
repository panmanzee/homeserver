# zones

Zone firewall for the homelab (policy in `../docs/zones.md`): VLAN-aware bridge `vmbr2`,
one gateway sub-interface per zone, nftables between zones.

- `nftables/zones.nft` – own tables only (`inet zones`, `ip zones_nat`), reloadable, interface names are `define`s at the top
- `network/vmbr2.interfaces` – snippet for `/etc/network/interfaces` on the Proxmox host (not applied yet)
- `lab/build.sh` – builds the same layout in network namespaces (router ns with vmbr2/vmbr1/vmbr0/tailscale0, one ns per zone guest, home, tailnet and an ISP/internet ns) and loads zones.nft
- `lab/test.sh` – every source x destination pair on 7 ports (22, 80, 443, 3306, 8006, 8009, 10051, which covers all ports named in the matrix), return traffic, gateway ping/dns/ntp, CUSTVM isolation, VLAN isolation, drop counters and log prefix
- `lab/teardown.sh` – removes the namespaces

## Run (root, Linux with nft, iproute2, socat, netcat-openbsd)

    bash lab/build.sh && bash lab/test.sh | tee lab/results/test-$(date +%F).log
    bash lab/teardown.sh

Result (`lab/results/test-2026-11-21.log`, WSL on the lab PC):

    SUMMARY: 433 passed, 0 failed, 433 total

## Notes

- Drops are logged with prefix `zn-drop <zone>: `; the lab sets `nf_log_all_netns=1` so they reach dmesg.
- The input chain has policy accept: only guest-facing interfaces are filtered, vmbr0 host services are untouched.
- LAB is not in the matrix; it only gets internet (not HOME).
- The lab adds its own masquerade for 10.77.0.0/24 to stand in for the existing vmbr1 NAT on the host.
- If `br_netfilter` is loaded on the host, traffic inside one zone also hits the forward hook; not tested here.
