#!/usr/bin/env python3
"""Fill the strongSwan / FRR templates from `terraform output -json`.

usage: ./render.py tf-output.json [--local-id IP] [--uplink vmbr0] [--out out]
  (cd ../terraform && terraform output -json > ../homelab-side/tf-output.json)
"""
import argparse
import json
import os
from string import Template

here = os.path.dirname(os.path.abspath(__file__))


def tpl(name):
    with open(os.path.join(here, name)) as f:
        return f.read()


ap = argparse.ArgumentParser()
ap.add_argument("tfjson")
ap.add_argument("--local-id", default="%any", help="home public IP (IKE id)")
ap.add_argument("--uplink", default="vmbr0")
ap.add_argument("--router-id", default="10.10.10.1")
ap.add_argument("--mode", choices=["xfrm", "vti"], default="xfrm",
                help="xfrm needs CONFIG_XFRM_INTERFACE (kernel 4.19+), vti is the fallback")
ap.add_argument("--local-addr", default="", help="vti only: IP of the uplink")
ap.add_argument("--out", default=os.path.join(here, "out"))
a = ap.parse_args()

with open(a.tfjson) as f:
    o = json.load(f)

tunnels = o["tunnels"]["value"]
if not tunnels:
    raise SystemExit("no tunnels in output (create_vpn_connection=false?)")
home_asn = o["homelab_asn"]["value"]
aws_asn = o["amazon_side_asn"]["value"]

conns, secrets, nbrs, af, links = [], [], [], [], []
for i, t in enumerate(tunnels, start=1):
    if a.mode == "xfrm":
        ike_if = f"        if_id_in = {i}\n        if_id_out = {i}"
        child_if = f"                if_id_in = {i}\n                if_id_out = {i}"
    else:
        ike_if = ""
        child_if = f"                mark_in = {i}\n                mark_out = {i}"
    t = dict(t, local_id=a.local_id, ike_if=ike_if, child_if=child_if)
    conns.append(Template(tpl("conn.tpl")).substitute(t))
    secrets.append(Template(tpl("secret.tpl")).substitute(t))
    ip = t["aws_inside"]
    nbrs.append(f" neighbor {ip} remote-as {aws_asn}\n"
                f" neighbor {ip} description aws-{t['name']}\n"
                f" neighbor {ip} timers 10 30")
    af.append(f"  neighbor {ip} route-map FROM-AWS in\n"
              f"  neighbor {ip} route-map TO-AWS out")
    if a.mode == "xfrm":
        mk = f"ip link add {t['name']} type xfrm dev $$UPLINK if_id {i}\n"
    else:
        mk = (f"ip link add {t['name']} type vti local {a.local_addr} remote {t['aws_outside']} key {i}\n"
              f"sysctl -qw net.ipv4.conf.{t['name']}.disable_policy=1\n")
    links.append(mk +
                 f"ip addr add {t['cgw_inside']}/30 dev {t['name']}\n"
                 f"ip link set {t['name']} up mtu 1400")

sw = tpl("swanctl.conf.tpl").replace("@@CONNS@@", "\n".join(conns)).replace(
    "@@SECRETS@@", "\n".join(secrets))
frr = Template(tpl("frr.conf.tpl").replace("@@NEIGHBORS@@", "\n".join(nbrs))
               .replace("@@AF@@", "\n".join(af))).substitute(
    home_asn=home_asn, router_id=a.router_id)
sh = Template(tpl("setup-xfrm.sh.tpl").replace("@@LINKS@@", "\n".join(links))
              ).substitute(uplink=a.uplink)

os.makedirs(a.out, exist_ok=True)
for name, txt in (("swanctl.conf", sw), ("frr.conf", frr), ("setup-xfrm.sh", sh),
                  ("strongswan-routes.conf", tpl("strongswan-routes.conf"))):
    p = os.path.join(a.out, name)
    with open(p, "w") as f:
        f.write(txt)
    os.chmod(p, 0o600)
    print("wrote", p)
