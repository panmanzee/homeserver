#!/bin/bash
# SIMULATED vpn test: two containers, IKEv2 tunnel + eBGP. Runs on the lab PC (docker).
# home config is rendered from the real templates in ../homelab-side
cd "$(dirname "$0")" || exit 1
HERE=$(pwd)
export DOCKER_CONFIG=$(mktemp -d)   # wsl docker has a broken windows cred helper
echo '{}' > "$DOCKER_CONFIG/config.json"

cleanup() { docker rm -f sim-home sim-aws >/dev/null 2>&1; docker network rm sim-vpn >/dev/null 2>&1; }
cleanup
trap cleanup EXIT

echo "=== SIMULATED: strongSwan+FRR 'home' (AS65010) <-> strongSwan+FRR 'aws' (AS64512) ==="
date
rm -rf out && python3 ../homelab-side/render.py home-tf.json --local-id 172.31.0.10 --mode vti --local-addr 172.31.0.10 --uplink eth0 --out out/home --router-id 10.10.10.1 || exit 1

docker build -q -t vpn-sim . || exit 1
docker network create --subnet 172.31.0.0/24 sim-vpn >/dev/null

run() { # name role ip localnet cfgdir
  docker run -d --name "$1" --hostname "$1" --network sim-vpn --ip "$3" \
    --cap-add NET_ADMIN --cap-add NET_RAW --privileged \
    -e ROLE="$2" -e LOCAL_NET="$4" -v "$5:/cfg:ro" vpn-sim >/dev/null
}
run sim-aws  aws  172.31.0.20 10.50.11.1/24 "$HERE/aws"
run sim-home home 172.31.0.10 10.10.10.1/24 "$HERE/out/home"

echo "--- waiting for bgp"
for i in $(seq 1 40); do
  docker exec sim-home vtysh -c 'show bgp neighbors 169.254.10.1' 2>/dev/null | grep -q 'state = Established' && break
  sleep 3
done

echo; echo '--- swanctl --list-sas (home)'
docker exec sim-home swanctl --list-sas
echo; echo "--- home: vtysh -c 'show bgp summary'"
docker exec sim-home vtysh -c 'show bgp summary'
echo; echo "--- aws: vtysh -c 'show bgp summary'"
docker exec sim-aws vtysh -c 'show bgp summary'
echo; echo "--- home: show ip bgp"
docker exec sim-home vtysh -c 'show ip bgp'
echo; echo "--- aws: show ip bgp"
docker exec sim-aws vtysh -c 'show ip bgp'
echo; echo "--- home kernel routes"
docker exec sim-home ip route
echo; echo "--- tunnel counters (must be > 0, proves traffic went through ESP)"
docker exec sim-home swanctl --list-sas 2>/dev/null | grep -E '^ +(in|out) '
echo; echo "--- ping home 10.10.10.1 -> aws 10.50.11.1 through the tunnel"
docker exec sim-home ping -c 4 -I 10.10.10.1 10.50.11.1
rc=$?
echo; echo "--- ping aws -> home"
docker exec sim-aws ping -c 4 -I 10.50.11.1 10.10.10.1
echo; echo "--- tunnel counters after pings"
docker exec sim-home swanctl --list-sas 2>/dev/null | grep -E '^ +(in|out) '
echo; echo "--- home route to the vpc"
docker exec sim-home ip route get 10.50.11.1

echo
if docker exec sim-home vtysh -c 'show bgp neighbors 169.254.10.1' | grep -q 'state = Established' \
   && docker exec sim-home vtysh -c 'show ip bgp' | grep -q '10.50.0.0/16' \
   && docker exec sim-aws vtysh -c 'show ip bgp' | grep -q '10.10.0.0/16' && [ $rc -eq 0 ]; then
  echo "RESULT: PASS (bgp established, prefixes exchanged, ping ok) - SIMULATED"
else
  echo "RESULT: FAIL"
  docker logs sim-home 2>&1 | tail -20
  docker exec sim-home tail -30 /var/log/charon.log
  exit 1
fi
