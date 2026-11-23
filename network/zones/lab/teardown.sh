#!/bin/bash
# remove the lab namespaces and listeners
for p in $(ip netns pids z-router z-mgmt z-srv z-dmz z-lab z-cust z-home z-tail z-isp 2>/dev/null); do
  kill "$p" 2>/dev/null
done
sleep 0.3
for n in router mgmt srv dmz lab cust home tail isp; do
  ip netns del z-$n 2>/dev/null
done
rm -rf /run/zones-lab
exit 0
