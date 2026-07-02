from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── 下游脚本自身的运行状态（从 GET /api/status 读取）──
class ScriptStatus(Enum):
    """下游脚本当前运行状态"""
    DISCONNECTED = "disconnected"   # 连不上 / 进程没在跑
    IDLE         = "idle"           # 已连接，调度未启动
    RUNNING      = "running"        # 调度循环运行中
    ERROR        = "error"          # 异常


# ── 编排引擎自身状态（Engine 内部维护）──
class EngineState(Enum):
    """AutoAnswer Engine 执行到哪一步了"""
    UNINITIALIZED = "uninitialized"
    LAUNCHING     = "launching"
    CONFIGURING   = "configuring"
    RUNNING       = "running"
    TERMINATING   = "terminating"
    DONE          = "done"


@dataclass
class ScriptInfo:
    """从下游脚本读取的元信息"""
    name: str
    version: str
    status: ScriptStatus
    current_task: str | None = None
    connected: bool = False


@dataclass
class LogEntry:
    """单条日志"""
    timestamp: float
    level: str                        # INFO / WARNING / ERROR / DEBUG
    source: str                       # "baas" / "autoanswer"
    message: str


@dataclass
class Profile:
    """配置预设（具体结构由 adapter 子类定义）"""
    name: str
    description: str = ""
    config: dict[str, Any] = field(default_factory=dict)
