#!/usr/bin/env python3
"""Load inventory.yaml into NetBox. Safe to run again: get, create if missing, patch if different."""
import os
import sys
from collections import Counter

import requests
import yaml

URL = os.environ["NETBOX_URL"].rstrip("/")
TOKEN = os.environ["NETBOX_TOKEN"]
here = os.path.dirname(os.path.abspath(__file__))

s = requests.Session()
auth = ("Bearer " if TOKEN.startswith("nbt_") else "Token ") + TOKEN  # v2 tokens use Bearer
s.headers.update({"Authorization": auth, "Accept": "application/json"})
stats = Counter()


def api(method, path, **kw):
    r = s.request(method, f"{URL}/api/{path}/", timeout=60, **kw)
    if not r.ok:
        sys.exit(f"{method} {path} -> {r.status_code}: {r.text[:500]}")
    return r.json()


def norm(v):
    # make an API value comparable with what we send
    if isinstance(v, dict):
        if "value" in v:
            return v["value"]
        return v.get("id")
    if isinstance(v, list):
        return sorted(norm(x) if not isinstance(x, dict) else x.get("id") for x in v)
    return v


def ensure(path, lookup, data, find=None):
    """get-or-create-or-update one object, returns the API object.
    lookup = identifying fields (sent on create), find = query filters if they differ,
    data = the other fields, compared and patched when they change."""
    found = api("GET", path, params={**(find or lookup), "limit": 2})["results"]
    if len(found) > 1:
        sys.exit(f"{path} {find or lookup} matched more than one object")
    if not found:
        stats["created"] += 1
        stats[f"created:{path}"] += 1
        return api("POST", path, json={**lookup, **data})
    obj = found[0]
    diff = {}
    for k, v in data.items():
        cur = obj.get(k)
        if v in ("", None) and cur in ("", None):
            continue
        if norm(cur) != norm(v):
            diff[k] = v
    if diff:
        stats["updated"] += 1
        stats[f"updated:{path}"] += 1
        print(f"  update {path} {find or lookup}: {sorted(diff)}")
        return api("PATCH", f"{path}/{obj['id']}", json=diff)
    stats["unchanged"] += 1
    return obj


def tags_for(planned=False, docker=False):
    t = []
    if planned:
        t.append(tag["planned"])
    if docker:
        t.append(tag["docker"])
    return t


inv = yaml.safe_load(open(os.path.join(here, "inventory.yaml")))

site = ensure("dcim/sites", {"slug": inv["site"]["slug"]},
              {"name": inv["site"]["name"], "status": "active", "description": inv["site"]["description"]})
man = ensure("dcim/manufacturers", {"slug": inv["manufacturer"]["slug"]}, {"name": inv["manufacturer"]["name"]})
dt = inv["device_type"]
dtype = ensure("dcim/device-types", {"slug": dt["slug"]},
               {"manufacturer": man["id"], "model": dt["model"], "u_height": dt["u_height"]})

roles = {}
for r in inv["device_roles"]:
    roles[r["slug"]] = ensure("dcim/device-roles", {"slug": r["slug"]}, {"name": r["name"], "color": r["color"]})

tag = {}
for t in inv["tags"]:
    tag[t["slug"]] = ensure("extras/tags", {"slug": t["slug"]}, {"name": t["name"], "color": t["color"]})

ctype = ensure("virtualization/cluster-types", {"slug": inv["cluster_type"]["slug"]}, {"name": inv["cluster_type"]["name"]})
cluster = ensure("virtualization/clusters", {"name": inv["cluster"]["name"]}, {"type": ctype["id"]})

prole = {}
for r in inv["prefix_roles"]:
    prole[r["slug"]] = ensure("ipam/roles", {"slug": r["slug"]}, {"name": r["name"]})

vg = ensure("ipam/vlan-groups", {"slug": inv["vlan_group"]["slug"]}, {"name": inv["vlan_group"]["name"]})
vlan = {}
for v in inv["vlans"]:
    vlan[v["vid"]] = ensure("ipam/vlans", {"group": vg["id"], "vid": v["vid"]},
                            {"name": v["name"], "status": "reserved", "description": v["description"],
                             "tags": [tag["planned"]["id"]]},
                            find={"group_id": vg["id"], "vid": v["vid"]})

for p in inv["prefixes"]:
    data = {"status": p["status"], "description": p["description"],
            "tags": [t["id"] for t in tags_for(p.get("planned"), p.get("docker"))]}
    if "role" in p:
        data["role"] = prole[p["role"]]["id"]
    if "vlan" in p:
        data["vlan"] = vlan[p["vlan"]]["id"]
    ensure("ipam/prefixes", {"prefix": p["prefix"]}, data)


def do_ips(ips, ifmap, obj_type, owner):
    primary = None
    for ip in ips:
        data = {"status": ip["status"], "assigned_object_type": obj_type,
                "assigned_object_id": ifmap[ip["interface"]]["id"],
                "tags": [t["id"] for t in tags_for(ip.get("planned"))]}
        o = ensure("ipam/ip-addresses", {"address": ip["address"]}, data)
        if ip.get("primary"):
            primary = o
    if primary:
        path = "dcim/devices" if obj_type == "dcim.interface" else "virtualization/virtual-machines"
        ensure(path, {"id": owner["id"]}, {"primary_ip4": primary["id"]})


def do_services(svcs, obj_type, owner):
    for sv in svcs:
        ensure("ipam/services", {"parent_object_type": obj_type, "parent_object_id": owner["id"], "name": sv["name"]},
               {"protocol": sv["protocol"], "ports": sv["ports"], "description": sv.get("description", "")},
               find={("device_id" if obj_type == "dcim.device" else "virtual_machine_id"): owner["id"], "name": sv["name"]})


# physical host
d = inv["device"]
dev = ensure("dcim/devices", {"name": d["name"]},
             {"role": roles[d["role"]]["id"], "device_type": dtype["id"], "site": site["id"],
              "status": d["status"], "cluster": cluster["id"], "comments": d["comments"].strip()})
dif = {}
for i in d["interfaces"]:
    data = {"type": i["type"], "description": i["description"],
            "tags": [t["id"] for t in tags_for(i.get("planned"))]}
    if "parent" in i:
        data["parent"] = dif[i["parent"]]["id"]
    if "bridge" in i:
        data["bridge"] = dif[i["bridge"]]["id"]
    dif[i["name"]] = ensure("dcim/interfaces", {"device": dev["id"], "name": i["name"]}, data,
                                   find={"device_id": dev["id"], "name": i["name"]})
do_ips(d["ips"], dif, "dcim.interface", dev)
do_services(d["services"], "dcim.device", dev)

# guests
for v in inv["virtual_machines"]:
    data = {"cluster": cluster["id"], "status": v["status"], "comments": v["comments"]}
    for k in ("vcpus", "memory", "disk"):
        if k in v:
            data[k] = v[k]
    vm = ensure("virtualization/virtual-machines", {"name": v["name"]}, data)
    vif = {}
    for i in v.get("interfaces", []):
        vif[i["name"]] = ensure("virtualization/interfaces", {"virtual_machine": vm["id"], "name": i["name"]},
                                {"description": i["description"]}, find={"virtual_machine_id": vm["id"], "name": i["name"]})
    do_ips(v.get("ips", []), vif, "virtualization.vminterface", vm)
    do_services(v.get("services", []), "virtualization.virtualmachine", vm)

print(f"\nimport done: created={stats['created']} updated={stats['updated']} unchanged={stats['unchanged']}")
for k in sorted(stats):
    if ":" in k:
        print(f"  {k} = {stats[k]}")
