#!/usr/bin/env python3
"""Provision Zabbix for the homelab through the API (stdlib only).

usage: python3 provision.py setup        # password, group, hosts, triggers, telegram media
       python3 provision.py alert-test   # enable action, temp trigger, wait for alert, clean up
       python3 provision.py proof        # host availability -> results/hosts-<date>.txt
"""
import json, os, secrets, sys, time, datetime, urllib.request

URL = os.environ.get("ZBX_URL", "http://100.108.65.118:8088/api_jsonrpc.php")
PASS_FILE = "/root/.config/zabbix-admin.pass"
ENV_FILE = os.environ.get("ZBX_ENV_FILE", "")  # file with TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_USERS
HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
TODAY = datetime.date.today().isoformat()

HOSTS = {
    "panhomelab": {"ip": "100.109.143.18", "docker": False},
    "workhub": {"ip": "100.108.65.118", "docker": True},
    "cloudhost": {"ip": "100.102.34.29", "docker": True},
}

_auth = None
_id = 0


def api(method, params=None, auth=True):
    global _id
    _id += 1
    body = json.dumps({"jsonrpc": "2.0", "method": method, "params": params if params is not None else {}, "id": _id}).encode()
    hdr = {"Content-Type": "application/json-rpc"}
    if auth and _auth:
        hdr["Authorization"] = "Bearer " + _auth
    req = urllib.request.Request(URL, body, hdr)
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.load(r)
    if "error" in out:
        raise RuntimeError("%s: %s" % (method, out["error"].get("data") or out["error"].get("message")))
    return out["result"]


def read_env(key):
    for line in open(ENV_FILE):
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("missing " + key)


def login():
    global _auth
    if os.path.exists(PASS_FILE):
        pw = open(PASS_FILE).read().strip()
        try:
            _auth = api("user.login", {"username": "Admin", "password": pw}, auth=False)
            return pw
        except RuntimeError:
            pass
    _auth = api("user.login", {"username": "Admin", "password": "zabbix"}, auth=False)
    new = secrets.token_urlsafe(18)
    fd = os.open(PASS_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(new + "\n")
    uid = api("user.get", {"filter": {"username": "Admin"}})[0]["userid"]
    api("user.update", {"userid": uid, "current_passwd": "zabbix", "passwd": new})
    _auth = api("user.login", {"username": "Admin", "password": new}, auth=False)
    print("admin password changed, stored in", PASS_FILE)
    return new


def one(method, params):
    r = api(method, params)
    return r[0] if r else None


def setup():
    login()
    g = one("hostgroup.get", {"filter": {"name": "Homelab"}})
    gid = g["groupid"] if g else api("hostgroup.create", {"name": "Homelab"})["groupids"][0]

    tpl = {}
    for t in ["Linux by Zabbix agent", "Docker by Zabbix agent 2"]:
        tpl[t] = one("template.get", {"filter": {"host": t}})["templateid"]

    for name, h in HOSTS.items():
        templates = [{"templateid": tpl["Linux by Zabbix agent"]}]
        if h["docker"]:
            templates.append({"templateid": tpl["Docker by Zabbix agent 2"]})
        ex = one("host.get", {"filter": {"host": name}})
        if ex:
            hid = ex["hostid"]
            print("host exists", name)
        else:
            hid = api("host.create", {
                "host": name,
                "groups": [{"groupid": gid}],
                "templates": templates,
                "interfaces": [{"type": 1, "main": 1, "useip": 1, "ip": h["ip"], "dns": "", "port": "10050"}],
            })["hostids"][0]
            print("host created", name)
        h["id"] = hid

        # own disk item, the template one is low level discovery (hourly)
        if not one("item.get", {"hostids": hid, "filter": {"key_": "vfs.fs.size[/,pused]"}}):
            ifid = api("hostinterface.get", {"hostids": hid})[0]["interfaceid"]
            api("item.create", {"hostid": hid, "name": "Disk / used %", "key_": "vfs.fs.size[/,pused]",
                                "type": 0, "value_type": 0, "delay": "1m", "interfaceid": ifid, "units": "%"})

        trig = [
            ("Available memory below 10%% for 5m on %s" % name, "avg(/%s/vm.memory.size[pavailable],5m)<10" % name, 4),
            ("Swap used above 70%% on %s" % name, "avg(/%s/system.swap.size[,pfree],5m)<30" % name, 3),
            ("Disk / above 85%% on %s" % name, "last(/%s/vfs.fs.size[/,pused])>85" % name, 3),
            ("Agent unreachable for 3m on %s" % name, "nodata(/%s/agent.ping,3m)=1" % name, 4),
        ]
        for desc, expr, prio in trig:
            if not one("trigger.get", {"hostids": hid, "filter": {"description": desc}}):
                api("trigger.create", {"description": desc, "expression": expr, "priority": prio})
                print("trigger", desc)

    # stock "Zabbix server" host has no agent in the container, only noise: remove
    zs = one("host.get", {"filter": {"host": "Zabbix server"}})
    if zs:
        api("host.delete", [zs["hostid"]])

    # telegram media type
    mt = one("mediatype.get", {"filter": {"name": "Telegram"}, "selectParameters": "extend"})
    params = [{"name": p["name"], "value": p["value"]} for p in mt["parameters"]]
    for p in params:
        if p["name"] == "api_token":
            p["value"] = read_env("TELEGRAM_BOT_TOKEN")
        if p["name"] == "api_parse_mode":
            p["value"] = ""  # plain text
    api("mediatype.update", {"mediatypeid": mt["mediatypeid"], "status": 0, "parameters": params})
    chat = read_env("TELEGRAM_ALLOWED_USERS").split(",")[0].strip()

    uid = one("user.get", {"filter": {"username": "Admin"}})["userid"]
    api("user.update", {"userid": uid, "medias": [{
        "mediatypeid": mt["mediatypeid"], "sendto": [chat], "active": 0,
        "severity": 30, "period": "1-7,00:00-24:00"}]})
    print("telegram media attached to Admin (warning and above)")


def save(name, text):
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, name), "w") as f:
        f.write(text)


def enable_action():
    a = one("action.get", {"filter": {"name": "Report problems to Zabbix administrators"}, "selectFilter": "extend"})
    api("action.update", {"actionid": a["actionid"], "status": 0, "filter": {
        "evaltype": 0, "conditions": [{"conditiontype": 4, "operator": 5, "value": "2"}]}})
    return a["actionid"]


def alert_test():
    login()
    aid = enable_action()
    hid = one("host.get", {"filter": {"host": "panhomelab"}})["hostid"]
    desc = "Telegram alert test (temporary)"
    tid = api("trigger.create", {"description": desc, "expression": "last(/panhomelab/system.uptime)>0",
                                 "priority": 2})["triggerids"][0]
    lines = ["action 'Report problems to Zabbix administrators' enabled (actionid %s), severity >= Warning" % aid,
             "temporary trigger %s created at %s" % (tid, time.strftime("%F %T"))]
    ev = None
    for _ in range(40):
        time.sleep(15)
        evs = api("problem.get", {"objectids": tid, "recent": True})
        if evs:
            ev = evs[0]
            break
    if not ev:
        lines.append("no problem event within 10 minutes")
    else:
        lines.append("problem event %s clock %s name '%s'" % (ev["eventid"], time.strftime("%F %T", time.localtime(int(ev["clock"]))), ev["name"]))
        lines += wait_alert(ev["eventid"], "problem")
    # resolve: flip the expression so it recovers normally, then delete
    api("trigger.update", {"triggerid": tid, "expression": "last(/panhomelab/system.uptime)<0"})
    for _ in range(40):
        time.sleep(15)
        e = api("event.get", {"objectids": tid, "value": 0, "output": "extend", "sortfield": "clock", "sortorder": "DESC", "limit": 1})
        if e:
            lines.append("recovery event %s clock %s" % (e[0]["eventid"], time.strftime("%F %T", time.localtime(int(e[0]["clock"])))))
            lines += wait_alert(e[0]["eventid"], "recovery")
            break
    else:
        lines.append("no recovery event within 10 minutes")
    api("trigger.delete", [tid])
    lines.append("temporary trigger deleted")
    save("alert-test-%s.txt" % TODAY, "\n".join(lines) + "\n")
    print("\n".join(lines))


STATUS = {0: "not sent", 1: "sent", 2: "failed", 3: "new"}


def wait_alert(eventid, kind):
    out = []
    for _ in range(20):
        al = api("alert.get", {"eventids": eventid, "output": ["alertid", "status", "retries", "error", "clock", "sendto", "subject"]})
        al = [a for a in al if a.get("sendto")] or al
        if al and all(a["status"] in ("1", "2") for a in al):
            break
        time.sleep(10)
    for a in al:
        # sendto is the chat id: hide it
        out.append("%s alert %s status=%s (%s) retries=%s error='%s' subject='%s'" % (
            kind, a["alertid"], a["status"], STATUS[int(a["status"])], a["retries"], a["error"], a["subject"]))
    if not al:
        out.append("%s: no alert row found" % kind)
    return out


def proof():
    login()
    hs = api("host.get", {"output": ["host", "status", "active_available"], "selectInterfaces": ["ip", "port", "available", "error"],
                          "filter": {"host": list(HOSTS)}})
    lines = ["# date %s" % time.strftime("%F %T"), "# host.get (agent availability; 1 = available)"]
    for h in sorted(hs, key=lambda x: x["host"]):
        i = h["interfaces"][0]
        lines.append("host=%s passive_available=%s active_available=%s iface=%s:%s error='%s'" % (
            h["host"], i["available"], h["active_available"], i["ip"], i["port"], i["error"]))
        it = one("item.get", {"hostids": h["hostid"], "filter": {"key_": "system.uptime"}, "output": ["lastvalue", "lastclock"]})
        up = int(float(it["lastvalue"])) if it and it["lastvalue"] else None
        lines.append("  system.uptime lastvalue=%s s lastclock=%s" % (up, it["lastclock"] if it else None))
        tr = api("trigger.get", {"hostids": h["hostid"], "filter": {"status": 0}, "countOutput": True})
        lines.append("  enabled triggers=%s" % tr)
    save("hosts-%s.txt" % TODAY, "\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"setup": setup, "alert-test": alert_test, "proof": proof}.get(cmd, lambda: print(__doc__))()
