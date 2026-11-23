#!/usr/bin/env python3
"""Read the state back from the NetBox API: counts per object type + IP plan csv."""
import csv
import datetime
import os
import sys
from ipaddress import ip_interface, ip_network

import requests

URL = os.environ["NETBOX_URL"].rstrip("/")
s = requests.Session()
tok = os.environ["NETBOX_TOKEN"]
s.headers.update({"Authorization": ("Bearer " if tok.startswith("nbt_") else "Token ") + tok, "Accept": "application/json"})
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
os.makedirs(out, exist_ok=True)
day = datetime.date.today().isoformat()


def get_all(path, **params):
    url, res = f"{URL}/api/{path}/", []
    params = {"limit": 200, **params}
    while url:
        r = s.get(url, params=params, timeout=60)
        r.raise_for_status()
        j = r.json()
        res += j["results"]
        url, params = j["next"], None
    return res


kinds = [
    ("sites", "dcim/sites"), ("manufacturers", "dcim/manufacturers"), ("device types", "dcim/device-types"),
    ("device roles", "dcim/device-roles"), ("devices", "dcim/devices"), ("device interfaces", "dcim/interfaces"),
    ("clusters", "virtualization/clusters"), ("virtual machines", "virtualization/virtual-machines"),
    ("vm interfaces", "virtualization/interfaces"), ("vlan groups", "ipam/vlan-groups"), ("vlans", "ipam/vlans"),
    ("prefixes", "ipam/prefixes"), ("ip addresses", "ipam/ip-addresses"), ("services", "ipam/services"),
    ("tags", "extras/tags"),
]
ver = s.get(f"{URL}/api/status/").json().get("netbox-version")
txt = [f"netbox export {day}  {URL}  netbox {ver}", "", "counts per object type"]
for label, path in kinds:
    n = s.get(f"{URL}/api/{path}/", params={"limit": 1}).json()["count"]
    txt.append(f"  {label:20} {n}")

prefixes = get_all("ipam/prefixes", ordering="prefix")
ips = get_all("ipam/ip-addresses", ordering="address")


def owner(ip):
    ao = ip.get("assigned_object")
    if not ao:
        return "", ""
    host = (ao.get("device") or ao.get("virtual_machine") or {}).get("name", "")
    return host, ao["name"]


txt += ["", "ipam: prefix, status, vlan, role, ips inside"]
rows = []
for p in prefixes:
    net = ip_network(p["prefix"])
    inside = [i for i in ips if ip_interface(i["address"]).ip in net]
    vid = p["vlan"]["vid"] if p["vlan"] else "-"
    role = p["role"]["name"] if p["role"] else "-"
    txt.append(f"  {p['prefix']:18} {p['status']['value']:10} vlan={str(vid):3} {role:12} ips={len(inside)}")
    for i in inside:
        host, ifname = owner(i)
        txt.append(f"      {i['address']:20} {i['status']['value']:9} {host}:{ifname}")
        rows.append([p["prefix"], p["status"]["value"], i["address"], i["status"]["value"], host, ifname])

txt += ["", "virtual machines"]
for v in get_all("virtualization/virtual-machines", ordering="name"):
    prim = v["primary_ip4"]["address"] if v["primary_ip4"] else "-"
    txt.append(f"  {v['name']:22} {v['status']['value']:8} vcpus={v['vcpus']} mem={v['memory']}MB disk={v['disk']}MB primary={prim}")

with open(os.path.join(out, f"netbox-export-{day}.txt"), "w") as f:
    f.write("\n".join(txt) + "\n")
with open(os.path.join(out, f"netbox-ip-plan-{day}.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["prefix", "prefix_status", "ip", "ip_status", "device_or_vm", "interface"])
    w.writerows(rows)
print("\n".join(txt))
print(f"wrote results/netbox-export-{day}.txt and results/netbox-ip-plan-{day}.csv", file=sys.stderr)
