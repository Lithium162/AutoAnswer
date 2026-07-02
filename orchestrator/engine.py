from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from adapter.base import ScriptAdapter
from models.script import EngineState, ScriptStatus


@dataclass
class EngineResult:
    """一次编排执行的结果"""
    success: bool
    error: str | None = None
    run_duration: float | None = None
    profile: str = ""


class ScriptEngine:
    """管理一个脚本实例的完整生命周期

    状态流程:
        UNINITIALIZED → LAUNCHING → CONFIGURING → RUNNING → TERMINATING → DONE
    """

    def __init__(self, adapter: ScriptAdapter):
        self.adapter = adapter
        self.state: EngineState = EngineState.UNINITIALIZED
        self._observers: dict[str, list] = field(default_factory=dict)

    async def run(self, profile: str = "") -> EngineResult:
        """一键执行：拉起进程 → 应用预设 → 启动调度 → 监听 → 关停"""
        import time
        t0 = time.time()

        self.state = EngineState.LAUNCHING
        ok = await self.adapter.launch()
        if not ok:
            self.state = EngineState.DONE
            return EngineResult(
                success=False, error="launch failed", profile=profile
            )

        self.state = EngineState.CONFIGURING
        if profile:
            await self.adapter.apply_profile(profile)

        self.state = EngineState.RUNNING
        ok = await self.adapter.start_scheduler()
        if not ok:
            self.state = EngineState.DONE
            return EngineResult(
                success=False, error="start_scheduler failed", profile=profile
            )

        # 监听循环 — 直到下游脚本退出 IDLE 或 ERROR
        while True:
            status = await self.adapter.get_status()
            if status != ScriptStatus.RUNNING:
                break
            await asyncio.sleep(2)

        self.state = EngineState.TERMINATING
        await self.adapter.terminate()

        self.state = EngineState.DONE
        duration = time.time() - t0
        return EngineResult(success=True, run_duration=duration, profile=profile)

    async def stop(self) -> None:
        """手动停止编排"""
        await self.adapter.stop_scheduler()
        await self.adapter.terminate()
        self.state = EngineState.DONE

    @property
    def is_running(self) -> bool:
        return self.state == EngineState.RUNNING
