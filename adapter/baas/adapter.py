"""BAASAdapter — wraps the BAAS HTTP API to implement the ScriptAdapter interface.

This allows AutoAnswer's orchestrator to control a BAAS instance as if it were
any other game script: launch → apply profile → start scheduler → monitor → stop.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from adapter.base import ScriptAdapter
from models.script import ScriptStatus, ScriptInfo, LogEntry
from .schemas import parse_status, parse_logs
from .profile import get_profile, BAASProfile, list_profiles


class BAASAdapter(ScriptAdapter):
    """Controls a BAAS instance via its HTTP API."""

    PROJECT_DIR = Path(__file__).resolve().parents[3] / "blue_archive_auto_script"

    def __init__(
        self,
        baas_path: str | None = None,
        config_dir: str = "default_config",
        api_port: int = 0,
    ):
        self._baas_path = Path(baas_path) if baas_path else self.PROJECT_DIR
        self._config_dir = config_dir
        self._api_port = api_port
        self._process: subprocess.Popen | None = None
        self._api_url: str = ""
        self._listeners: dict[str, list[Callable]] = {}

        # Detect if this path is a project dir or an .exe
        self._is_project = (self._baas_path / "__main__.py").exists()

    # ── ScriptAdapter implementation ─────────────────────

    @property
    def name(self) -> str:
        return "baas"

    @property
    def info(self) -> ScriptInfo:
        return ScriptInfo(
            name="baas",
            version="1.4.3",
            status=ScriptStatus.DISCONNECTED,
            connected=False,
        )

    @property
    def capabilities(self) -> list[str]:
        return sorted(list_profiles())

    async def launch(self) -> bool:
        """Launch BAAS as a subprocess and wait for its API port file."""
        ipc_dir = os.path.join(os.path.expanduser("~"), ".autoanswer")
        os.makedirs(ipc_dir, exist_ok=True)
        port_file = os.path.join(ipc_dir, "baas.port")
        # Remove stale port file
        try:
            os.remove(port_file)
        except OSError:
            pass

        if self._is_project:
            cmd = [
                sys.executable, "-u", "__main__.py",
                "--api",
                f"--api-port={self._api_port}",
                f"--config={self._config_dir}",
            ]
        else:
            cmd = [str(self._baas_path), "--api", f"--api-port={self._api_port}"]

        self._process = subprocess.Popen(
            cmd,
            cwd=str(self._baas_path) if self._is_project else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        # Wait for port file (max 60 seconds)
        for _ in range(120):
            if os.path.isfile(port_file):
                break
            await asyncio.sleep(0.5)
        else:
            return False

        # Read the port
        with open(port_file) as f:
            port = int(f.read().strip())
        self._api_url = f"http://127.0.0.1:{port}"
        return True

    async def terminate(self) -> bool:
        """Send stop signal and kill the subprocess."""
        if self._api_url:
            try:
                async with httpx.AsyncClient() as cli:
                    await cli.post(f"{self._api_url}/api/script/stop", timeout=5)
            except Exception:
                pass
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
        self._api_url = ""
        return True

    async def start_scheduler(self) -> bool:
        return await self._req("POST", "/api/script/start", ok_check=True)

    async def stop_scheduler(self) -> bool:
        return await self._req("POST", "/api/script/stop", ok_check=True)

    async def apply_profile(self, name: str) -> None:
        profile = get_profile(name)
        async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as cli:
            # Apply config overrides
            for key, value in profile.config.items():
                await cli.put(f"{self._api_url}/api/config/{key}", json={"value": value})
            # Apply event overrides
            for task, overrides in profile.event.items():
                await cli.put(f"{self._api_url}/api/event/{task}", json=overrides)
            # Notify BAAS to reload
            await cli.post(f"{self._api_url}/api/config/reload")

    async def get_status(self) -> ScriptStatus:
        raw = await self._req("GET", "/api/status", raw_json=True)
        if raw is None:
            return ScriptStatus.DISCONNECTED
        info = parse_status(raw)
        return info.status

    async def get_logs(self, since: float) -> list[LogEntry]:
        raw = await self._req("GET", f"/api/logs?since={since}", raw_json=True)
        if raw is None:
            return []
        return parse_logs(raw)

    def on(self, event: str, callback: Callable) -> None:
        self._listeners.setdefault(event, []).append(callback)

    # ── Internal helpers ─────────────────────────────────

    async def _req(
        self,
        method: str,
        path: str,
        ok_check: bool = False,
        raw_json: bool = False,
    ):
        """Make a request to the BAAS API. Returns bool for ok_check, dict for raw_json, or None on error."""
        if not self._api_url:
            return None
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10)) as cli:
                r = await cli.request(method, f"{self._api_url}{path}")
                if r.status_code >= 400:
                    return None
                if ok_check:
                    return r.json().get("ok", False)
                if raw_json:
                    return r.json()
                return True
        except Exception:
            return None
