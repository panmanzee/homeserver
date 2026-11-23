#!/bin/bash
# container entrypoint: ROLE=home|aws, config mounted at /cfg
# (SIMULATED: a second strongSwan+FRR box stands in for the AWS VGW)
set -e
sysctl -qw net.ipv4.ip_forward=1 net.ipv4.conf.all.rp_filter=0 net.ipv4.conf.default.rp_filter=0 || true

# fake LAN / VPC prefix on lo so we have something to ping
ip addr add "$LOCAL_NET" dev lo

bash /cfg/setup-xfrm.sh

cp /cfg/strongswan-routes.conf /etc/strongswan.d/zz-routes.conf
cp /cfg/swanctl.conf /etc/swanctl/conf.d/sim.conf
/usr/lib/ipsec/charon >/var/log/charon.log 2>&1 &
sleep 3
swanctl --load-all

cp /cfg/frr.conf /etc/frr/frr.conf
sed -i 's/^bgpd=no/bgpd=yes/; s/^staticd=no/staticd=yes/' /etc/frr/daemons
/usr/lib/frr/frrinit.sh start

echo "$ROLE up"
sleep infinity
