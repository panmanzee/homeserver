#!/bin/bash
# vti because the WSL2 kernel on the lab PC has no xfrm interface support
ip link add aws1 type vti local 172.31.0.20 remote 172.31.0.10 key 1
sysctl -qw net.ipv4.conf.aws1.disable_policy=1
ip addr add 169.254.10.1/30 dev aws1
ip link set aws1 up mtu 1400
