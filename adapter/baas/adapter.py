"""BAASAdapter — wraps the BAAS HTTP API with stdlib-only HTTP client.

No extra dependencies required — uses urllib.request under the hood.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
from collections.abc import Callable
from pathlib import Path

from adapter.base import ScriptAdapter
from models.script import ScriptStatus, ScriptInfo, LogEntry
from .schemas import parse_status, parse_logs
from .profile import get_profile, BAASProfile, list_profiles


class BAASAdapter(ScriptAdapter):
    """Controls a BAAS instance via its HTTP API."""

    PROJECT_DIR = Path(__file__).resolve().parents[3] / "blue_archive_auto_script"

    def __init__(self, baas_path: str | None = None, config_dir: str = "default_config", api_port: int = 0):
        self._baas_path = Path(baas_path) if baas_path else self.PROJECT_DIR
        self._config_dir = config_dir
        self._api_port = api_port
        self._process: subprocess.Popen | None = None
        self._api_url: str = ""
        self._listeners: dict[str, list[Callable]] = {}
        self._is_project = (self._baas_path / "__main__.py").exists()

    # ── Console helpers ──────────────────────────────────

    @staticmethod
    async def run_console(profile: str = "daily", config_dir: str = "default_config"):
        """Direct console runner — no subprocess, imports BAAS in-process."""
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "blue_archive_auto_script"))
        import main as baas_main
        from core.config.config_set import ConfigSet
        instance = baas_main.Main(ocr_needed=["en-us"])
        print("[AutoAnswer] BAAS core initialized")
        config = ConfigSet(config_dir=config_dir)
        thread = instance.get_thread(config, name="console")
        if not thread.init_all_data():
            print("[AutoAnswer] init_all_data failed")
            return
        if profile:
            from .profile import get_profile
            p = get_profile(profile)
            for key, value in p.config.items():
                thread.config_set.set(key, value)
            for task, overrides in p.event.items():
                thread.config_set.set(task, overrides)
        print(f"[AutoAnswer] Starting scheduler with profile '{profile}'")
        thread.send("start")
        try:
            while thread.flag_run:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n[AutoAnswer] Stopping...")
            thread.send("stop")

    # ── ScriptAdapter implementation ─────────────────────

    @property
    def name(self) -> str:
        return "baas"

    @property
    def info(self) -> ScriptInfo:
        return ScriptInfo(name="baas", version="1.4.3", status=ScriptStatus.DISCONNECTED, connected=False)

    @property
    def capabilities(self) -> list[str]:
        return sorted(list_profiles())

    # ── HTTP helpers (stdlib only) ───────────────────────

    def _http_req(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict | None]:
        url = f"{self._api_url}{path}"
        data = json.dumps(body).encode("utf-8") if body else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json; charset=utf-8")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8")
                return resp.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            return e.code, None
        except Exception:
            return 0, None

    def _http_get_json(self, path: str) -> tuple[int, dict | None]:
        url = f"{self._api_url}{path}"
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                raw = resp.read().decode("utf-8")
                return resp.status, json.loads(raw) if raw else None
        except Exception:
            return 0, None

    # ── Lifecycle ─────────────────────────────────────────

    async def launch(self) -> bool:
        ipc_dir = os.path.join(os.path.expanduser("~"), ".autoanswer")
        os.makedirs(ipc_dir, exist_ok=True)
        port_file = os.path.join(ipc_dir, "baas.port")
        try:
            os.remove(port_file)
        except OSError:
            pass

        if self._is_project:
            cmd = [sys.executable, "-u", "__main__.py", "--api", f"--api-port={self._api_port}", f"--config={self._config_dir}"]
        else:
            cmd = [str(self._baas_path), "--api", f"--api-port={self._api_port}"]

        self._process = subprocess.Popen(cmd, cwd=str(self._baas_path) if self._is_project else None, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        loop = asyncio.get_event_loop()

        def _wait_port():
            for _ in range(120):
                if os.path.isfile(port_file):
                    return True
                import time
                time.sleep(0.5)
            return False

        ok = await loop.run_in_executor(None, _wait_port)
        if not ok:
            return False
        with open(port_file) as f:
            self._api_url = f"http://127.0.0.1:{f.read().strip()}"
        return True

    async def terminate(self) -> bool:
        if self._api_url:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._http_req, "POST", "/api/script/stop", None)
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
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._http_req, "POST", "/api/script/start", None)
        return True

    async def stop_scheduler(self) -> bool:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._http_req, "POST", "/api/script/stop", None)
        return True

    async def apply_profile(self, name: str) -> None:
        profile = get_profile(name)
        loop = asyncio.get_event_loop()
        for key, value in profile.config.items():
            await loop.run_in_executor(None, self._http_req, "PUT", f"/api/config/{key}", {"value": value})
        for task, overrides in profile.event.items():
            await loop.run_in_executor(None, self._http_req, "PUT", f"/api/event/{task}", overrides)
        await loop.run_in_executor(None, self._http_req, "POST", "/api/config/reload", None)

    async def get_status(self) -> ScriptStatus:
        loop = asyncio.get_event_loop()
        _, body = await loop.run_in_executor(None, self._http_get_json, "/api/status")
        if body is None:
            return ScriptStatus.DISCONNECTED
        return parse_status(body).status

    async def get_logs(self, since: float) -> list[LogEntry]:
        loop = asyncio.get_event_loop()
        _, body = await loop.run_in_executor(None, self._http_get_json, f"/api/logs?since={since}")
        if body is None:
            return []
        return parse_logs(body)

    def on(self, event: str, callback: Callable) -> None:
        self._listeners.setdefault(event, []).append(callback)
