from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from models.script import LogEntry, ScriptInfo, ScriptStatus


class ScriptAdapter(ABC):
    """所有游戏脚本适配器必须实现的接口

    AutoAnswer 通过这个接口统一管理下游脚本的生命周期。
    每种脚本（BAAS、MAA 等）各自实现这个接口。
    """

    # ── 进程生命周期 ──────────────────────────────────

    @abstractmethod
    async def launch(self) -> bool:
        """拉起下游脚本进程（如带 --api 参数启动 BAAS.exe）"""
        ...

    @abstractmethod
    async def terminate(self) -> bool:
        """关闭下游脚本进程"""
        ...

    # ── 调度控制 ──────────────────────────────────────

    @abstractmethod
    async def start_scheduler(self) -> bool:
        """通知下游脚本开始调度循环"""
        ...

    @abstractmethod
    async def stop_scheduler(self) -> bool:
        """通知下游脚本停止调度"""
        ...

    # ── 配置预设 ──────────────────────────────────────

    @abstractmethod
    async def apply_profile(self, name: str) -> None:
        """应用一个配置预设（覆盖配置文件 + 通知热加载）"""
        ...

    # ── 观测 ──────────────────────────────────────────

    @abstractmethod
    async def get_status(self) -> ScriptStatus:
        """读取下游脚本当前运行状态"""
        ...

    @abstractmethod
    async def get_logs(self, since: float) -> list[LogEntry]:
        """获取指定时间戳之后的日志"""
        ...

    # ── 事件订阅 ──────────────────────────────────────

    @abstractmethod
    def on(self, event: str, callback: Callable) -> None:
        """订阅事件（status_change / task_complete / error / log）"""
        ...

    # ── 脚本元信息 ────────────────────────────────────

    @property
    @abstractmethod
    def name(self) -> str:
        """脚本标识符，如 'baas'、'maa'"""
        ...

    @property
    @abstractmethod
    def info(self) -> ScriptInfo:
        """脚本完整元信息"""
        ...

    @property
    @abstractmethod
    def capabilities(self) -> list[str]:
        """该脚本支持的任务列表"""
        ...
