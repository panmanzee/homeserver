#!/bin/bash
# walks the policy matrix in docs/zones.md plus gateway, counter and isolation checks
R="ip netns exec z-router"
tmp=$(mktemp -d)
pass=0; fail=0

declare -A IP=([mgmt]=10.10.10.10 [srv]=10.10.20.10 [dmz]=10.10.30.10 [lab]=10.10.99.10
  [cust]=10.77.0.10 [home]=192.168.0.50 [tail]=100.64.0.2 [inet]=203.0.113.10)
declare -A GW=([mgmt]=10.10.10.1 [srv]=10.10.20.1 [dmz]=10.10.30.1 [lab]=10.10.99.1 [cust]=10.77.0.1)
PORTS="22 80 443 3306 8006 8009 10051"

report() { # name expected actual
  if [ "$2" = "$3" ]; then pass=$((pass+1)); echo "PASS  $1 (expect $2)"
  else fail=$((fail+1)); echo "FAIL  $1 (expect $2, got $3)"; fi
}

inports() { case " $1 " in *" $2 "*) return 0;; esac; return 1; }

# the matrix from docs/zones.md, written out by hand
expect() { # src dst port -> allow|deny
  local s=$1 d=$2 p=$3 ok=1
  case $s-$d in
    mgmt-srv|mgmt-dmz|mgmt-cust|mgmt-home|mgmt-inet) ok=0;;
    srv-mgmt|dmz-mgmt) [ $p = 10051 ] && ok=0;;
    srv-dmz) inports "80 443" $p && ok=0;;
    dmz-srv) [ $p = 8009 ] && ok=0;;
    dmz-cust) ok=0;;
    srv-inet|dmz-inet|cust-inet|lab-inet) ok=0;;
    home-dmz) inports "80 443" $p && ok=0;;
    tail-mgmt) inports "22 8006 80 443" $p && ok=0;;
    tail-srv) ok=0;;
    tail-dmz) inports "22 80 443" $p && ok=0;;
  esac
  [ $ok = 0 ] && echo allow || echo deny
}

tcp() { # srcns dstip port [srcip]
  ip netns exec z-$1 nc -z -w1 ${4:+-s $4} $2 $3 >/dev/null 2>&1 && echo allow || echo deny
}

srcs="mgmt srv dmz lab cust home tail inet"
dsts="mgmt srv dmz lab cust home tail inet"

echo "== matrix: every source x destination x port"
for s in $srcs; do
  ns=$s; sip=""
  [ $s = inet ] && { ns=isp; sip=203.0.113.10; }
  for d in $dsts; do
    [ $s = $d ] && continue
    [ $s = home ] && [ $d = inet ] && continue
    [ $s = inet ] && { [ $d = home ] || [ $d = tail ]; } && continue
    (
      for p in $PORTS; do echo "$p $(tcp $ns ${IP[$d]} $p $sip)"; done > $tmp/$s-$d
    ) &
  done
done
wait
for s in $srcs; do
  for d in $dsts; do
    [ -f $tmp/$s-$d ] || continue
    while read p got; do
      report "$s -> $d tcp/$p" $(expect $s $d $p) $got
    done < $tmp/$s-$d
  done
done

echo "== established return traffic"
got=$(ip netns exec z-mgmt nc -w1 10.10.20.10 22 </dev/null 2>/dev/null)
[ "$got" = ok ] && got=allow || got=deny
report "mgmt -> srv tcp/22 reply data comes back" allow $got
got=$(ip netns exec z-home nc -w1 10.10.30.10 443 </dev/null 2>/dev/null)
[ "$got" = ok ] && got=allow || got=deny
report "home -> dmz tcp/443 reply data comes back" allow $got
got=$(ip netns exec z-cust nc -w1 203.0.113.10 443 </dev/null 2>/dev/null)
[ "$got" = ok ] && got=allow || got=deny
report "cust -> inet tcp/443 reply data comes back (nat)" allow $got

echo "== gateways: ping, dns, ntp, everything else dropped"
for z in mgmt srv dmz lab cust; do
  ip netns exec z-$z ping -c1 -W1 ${GW[$z]} >/dev/null 2>&1 && g=allow || g=deny
  report "$z ping own gw ${GW[$z]}" allow $g
  ip netns exec z-$z nc -z -w1 ${GW[$z]} 53 >/dev/null 2>&1 && g=allow || g=deny
  report "$z tcp/53 to own gw" allow $g
  for u in 53 123; do
    echo q | ip netns exec z-$z nc -u -w1 ${GW[$z]} $u 2>/dev/null | grep -q pong && g=allow || g=deny
    report "$z udp/$u to own gw" allow $g
  done
  if [ $z = mgmt ]; then e=allow; else e=deny; fi
  for p in 22 8006; do
    ip netns exec z-$z nc -z -w1 ${GW[$z]} $p >/dev/null 2>&1 && g=allow || g=deny
    report "$z tcp/$p to own gw (host service)" $e $g
  done
done
for pair in srv:dmz dmz:mgmt cust:mgmt lab:srv; do
  s=${pair%:*}; d=${pair#*:}
  ip netns exec z-$s ping -c1 -W1 ${GW[$d]} >/dev/null 2>&1 && g=allow || g=deny
  report "$s ping $d gateway ${GW[$d]}" deny $g
done
ip netns exec z-tail nc -z -w1 100.64.0.1 22 >/dev/null 2>&1 && g=allow || g=deny
report "tail tcp/22 to host" allow $g

echo "== custvm isolation"
for d in mgmt srv dmz lab home tail; do
  ip netns exec z-cust ping -c1 -W1 ${IP[$d]} >/dev/null 2>&1 && g=allow || g=deny
  report "cust ping $d" deny $g
done
ip netns exec z-cust ping -c1 -W1 203.0.113.10 >/dev/null 2>&1 && g=allow || g=deny
report "cust ping internet" allow $g
ip netns exec z-srv ping -c1 -W1 10.77.0.10 >/dev/null 2>&1 && g=allow || g=deny
report "srv ping cust" deny $g
g=$(tcp srv 10.77.0.10 22)
report "srv -> cust tcp/22" deny $g
g=$(tcp dmz 10.77.0.10 22)
report "cloudhost 10.10.30.10 -> cust tcp/22" allow $g
ip -n z-dmz addr add 10.10.30.50/24 dev eth0
g=$(tcp dmz 10.77.0.10 22 10.10.30.50)
report "other dmz host 10.10.30.50 -> cust tcp/22" deny $g
ip -n z-dmz addr del 10.10.30.50/24 dev eth0

echo "== vlan isolation on layer 2"
ip -n z-srv addr add 10.10.10.50/24 dev eth0
ip netns exec z-srv ping -c1 -W1 -I 10.10.10.50 10.10.10.10 >/dev/null 2>&1 && g=allow || g=deny
report "srv guest with a vlan 10 address cannot arp into vlan 10" deny $g
ip -n z-srv addr del 10.10.10.50/24 dev eth0

echo "== drop counters and log"
for c in from_mgmt from_srv from_dmz from_lab from_cust from_tail from_uplink in_srv in_dmz in_lab in_cust; do
  n=$($R nft list chain inet zones $c | awk '/ drop$/ {for(i=1;i<=NF;i++) if($i=="packets") s+=$(i+1)} END{print s+0}')
  [ "$n" -gt 0 ] && g=counted || g=zero
  report "chain $c drop counter ($n packets)" counted $g
done
ip netns exec z-srv nc -z -w1 10.10.30.10 3306 >/dev/null 2>&1
sleep 0.5
if dmesg 2>/dev/null | grep -q "zn-drop srv:"; then g=logged; else g=missing; fi
report "dropped packet shows up in the kernel log with prefix" logged $g

rm -rf $tmp
echo
echo "SUMMARY: $pass passed, $fail failed, $((pass+fail)) total"
[ $fail = 0 ]
