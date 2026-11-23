#!/bin/bash
# lab: router netns (bridge vmbr2 + vlan gateways + zones.nft) and one netns per guest
set -e
here=$(cd "$(dirname "$0")" && pwd)
R="ip netns exec z-router"

for t in socat nc; do
  command -v $t >/dev/null || NEED=1
done
if [ -n "$NEED" ]; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get -o DPkg::Lock::Timeout=600 update -q >/dev/null
  apt-get -o DPkg::Lock::Timeout=600 install -y -q socat netcat-openbsd >/dev/null
fi

bash "$here/teardown.sh"
for n in router mgmt srv dmz lab cust home tail isp; do
  ip netns add z-$n
  ip -n z-$n link set lo up
done

sysctl -qw net.netfilter.nf_log_all_netns=1 2>/dev/null || true
$R sysctl -qw net.ipv4.ip_forward=1
$R sysctl -qw net.ipv4.conf.all.rp_filter=0 net.ipv4.conf.default.rp_filter=0

# vmbr2: vlan aware, no ports at first, no default pvid
$R ip link add vmbr2 type bridge vlan_filtering 1 vlan_default_pvid 0
$R ip link set vmbr2 up
for v in 10 20 30 99; do
  $R bridge vlan add dev vmbr2 vid $v self
  $R ip link add link vmbr2 name vmbr2.$v type vlan id $v
  $R ip addr add 10.10.$v.1/24 dev vmbr2.$v
  $R ip link set vmbr2.$v up
done

# vlan guest: name vid ip
vguest() {
  ip -n z-router link add p-$1 type veth peer name eth0 netns z-$1
  $R ip link set p-$1 master vmbr2 up
  $R bridge vlan add dev p-$1 vid $2 pvid untagged
  ip -n z-$1 addr add $3/24 dev eth0
  ip -n z-$1 link set eth0 up
  ip -n z-$1 route add default via ${3%.*}.1
}
vguest mgmt 10 10.10.10.10
vguest srv  20 10.10.20.10
vguest dmz  30 10.10.30.10
vguest lab  99 10.10.99.10

# vmbr1: customer vms, plain bridge, has its own nat on the real host
$R ip link add vmbr1 type bridge
$R ip addr add 10.77.0.1/24 dev vmbr1
$R ip link set vmbr1 up
ip -n z-router link add p-cust type veth peer name eth0 netns z-cust
$R ip link set p-cust master vmbr1 up
ip -n z-cust addr add 10.77.0.10/24 dev eth0
ip -n z-cust link set eth0 up
ip -n z-cust route add default via 10.77.0.1

# vmbr0: home lan. router = host (.101), isp router (.1), a phone (.50)
$R ip link add vmbr0 type bridge
$R ip addr add 192.168.0.101/24 dev vmbr0
$R ip link set vmbr0 up
for pair in home:50 isp:1; do
  n=${pair%:*}; h=${pair#*:}
  ip -n z-router link add p-$n type veth peer name eth0 netns z-$n
  $R ip link set p-$n master vmbr0 up
  ip -n z-$n addr add 192.168.0.$h/24 dev eth0
  ip -n z-$n link set eth0 up
done
$R ip route add default via 192.168.0.1
# the internet: an address on the isp router
ip -n z-isp addr add 203.0.113.10/32 dev lo
ip -n z-isp route add 10.10.0.0/16 via 192.168.0.101
ip -n z-isp route add 10.77.0.0/24 via 192.168.0.101
ip -n z-home route add default via 192.168.0.1
ip -n z-home route add 10.10.0.0/16 via 192.168.0.101
ip -n z-home route add 10.77.0.0/24 via 192.168.0.101
ip -n z-home route add 100.64.0.0/10 via 192.168.0.101

# tailscale0 + one admin device
ip -n z-router link add tailscale0 type veth peer name eth0 netns z-tail
$R ip addr add 100.64.0.1/24 dev tailscale0
$R ip link set tailscale0 up
ip -n z-tail addr add 100.64.0.2/24 dev eth0
ip -n z-tail link set eth0 up
ip -n z-tail route add default via 100.64.0.1

# existing nat for vmbr1 on the real host, not part of zones.nft
$R nft -f - <<EOF
table ip custnat {
	chain post {
		type nat hook postrouting priority srcnat; policy accept;
		ip saddr 10.77.0.0/24 oifname "vmbr0" masquerade
	}
}
EOF

$R nft -c -f "$here/../nftables/zones.nft"
$R nft -f "$here/../nftables/zones.nft"

# listeners on every guest and on the router
mkdir -p /run/zones-lab
nolog="/dev/null"
for n in mgmt srv dmz lab cust home tail isp; do
  for p in 22 80 443 3306 8006 8009 10051; do
    ip netns exec z-$n setsid socat TCP-LISTEN:$p,fork,reuseaddr SYSTEM:"echo ok" >$nolog 2>&1 </dev/null &
  done
done
for p in 22 53 8006; do
  $R setsid socat TCP-LISTEN:$p,fork,reuseaddr SYSTEM:"echo ok" >$nolog 2>&1 </dev/null &
done
for p in 53 123; do
  $R setsid socat UDP-RECVFROM:$p,fork SYSTEM:"echo pong" >$nolog 2>&1 </dev/null &
done
sleep 1
echo "lab up"
