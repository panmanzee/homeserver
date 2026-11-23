#!/bin/bash
# creates the xfrm interfaces and gives them the tunnel inside IPs
# run as root on the Proxmox host before swanctl --load-all
UPLINK=${uplink}
@@LINKS@@
