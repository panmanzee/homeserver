"""Proxmox VE API client (just what the compute service needs)."""
from __future__ import annotations

import asyncio
import ssl
import urllib.parse

import httpx


class PVEError(Exception):
    pass


class PVE:
    def __init__(self, base: str, token_id: str, secret: str, node: str = "pve", ca_file: str | None = None):
        self.base, self.node = base.rstrip("/"), node
        self.headers = {"Authorization": f"PVEAPIToken={token_id}={secret}"}
        # Proxmox uses its own CA. Trust that CA only (no blanket verify=False); we connect by IP, so skip the hostname check.
        if ca_file:
            ctx = ssl.create_default_context(cafile=ca_file)
            ctx.check_hostname = False
            self.verify = ctx
        else:
            self.verify = False

    async def _req(self, method: str, path: str, data: dict | None = None):
        async with httpx.AsyncClient(timeout=60, verify=self.verify) as c:
            r = await c.request(method, f"{self.base}/api2/json{path}", headers=self.headers, data=data)
        if r.status_code >= 300:
            try:
                msg = r.json().get("errors") or r.json().get("message") or r.text
            except Exception:
                msg = r.text
            raise PVEError(f"proxmox {method} {path} -> {r.status_code}: {str(msg)[:300]}")
        return r.json().get("data")

    def _q(self, vmid: int) -> str:
        return f"/nodes/{self.node}/qemu/{vmid}"

    # full=0: a linked (thin-snapshot) clone of the template, instant instead of copying 3.5 GB
    async def clone(self, template: int, newid: int, name: str, pool: str) -> str:
        return await self._req("POST", f"{self._q(template)}/clone",
                               {"newid": newid, "name": name, "full": 0, "pool": pool})

    async def wait(self, upid: str, timeout: int = 300) -> None:
        for _ in range(timeout):
            st = await self._req("GET", f"/nodes/{self.node}/tasks/{urllib.parse.quote(upid, safe='')}/status")
            if st.get("status") == "stopped":
                if st.get("exitstatus") != "OK":
                    raise PVEError(f"task failed: {st.get('exitstatus')}")
                return
            await asyncio.sleep(1)
        raise PVEError("task timed out")

    async def configure(self, vmid: int, **params) -> None:
        if "sshkeys" in params:                      # the API wants this one percent-encoded
            params["sshkeys"] = urllib.parse.quote(params["sshkeys"], safe="")
        await self._req("POST", f"{self._q(vmid)}/config", params)

    async def resize(self, vmid: int, disk: str, size: str) -> None:
        await self._req("PUT", f"{self._q(vmid)}/resize", {"disk": disk, "size": size})

    async def status(self, vmid: int) -> str:
        return (await self._req("GET", f"{self._q(vmid)}/status/current")).get("status", "unknown")

    async def exists(self, vmid: int) -> bool:
        try:
            await self.status(vmid)
            return True
        except PVEError:
            return False

    async def action(self, vmid: int, name: str) -> str:
        """start | stop (forced) | shutdown (graceful, forced after 30s) | reboot"""
        data = {"forceStop": 1, "timeout": 30} if name == "shutdown" else None
        return await self._req("POST", f"{self._q(vmid)}/status/{name}", data)

    async def delete(self, vmid: int) -> str:
        return await self._req("DELETE", f"{self._q(vmid)}?purge=1&destroy-unreferenced-disks=1")

    async def snapshots(self, vmid: int) -> list[dict]:
        return await self._req("GET", f"{self._q(vmid)}/snapshot")

    async def snapshot(self, vmid: int, name: str) -> str:
        return await self._req("POST", f"{self._q(vmid)}/snapshot", {"snapname": name})

    async def rollback(self, vmid: int, name: str) -> str:
        return await self._req("POST", f"{self._q(vmid)}/snapshot/{name}/rollback")

    async def delete_snapshot(self, vmid: int, name: str) -> str:
        return await self._req("DELETE", f"{self._q(vmid)}/snapshot/{name}")
