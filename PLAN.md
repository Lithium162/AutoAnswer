# AutoAnswer — 项目构建大纲

> **头脑风暴阶段 · v0.2** — 简化版
>
> AutoAnswer 是一个**游戏脚本编排层**。它的工作不是替代某个具体脚本（如 BAAS、MAA），
> 而是负责：**拉起进程 → 应用配置预设 → 启动调度 → 监听状态 → 关闭**。
>
> 下游脚本自身已经具备完整的调度能力（BAAS 的 scheduler、MAA 的任务队列），
> AutoAnswer 不重复实现这些逻辑。不同的"剧本"本质上是不同的配置预设。

---

## 1. 核心理念

```
  你（用户）
      │
      ▼
┌────────────────┐          ┌──────────────────┐
│  AutoAnswer     │────────→│  BAAS             │
│  (编排层)       │  HTTP   │  (自带调度循环)    │
│                 │         │                    │
│  1. 选预设       │         │  cafe_reward      │
│  2. 拉起         │         │  → arena          │
│  3. 配置         │         │  → lesson         │
│  4. 启动调度      │         │  → ...            │
│  5. 监听状态      │         │  (event.json 决定) │
│  6. 关闭         │         └──────────────────┘
└────────────────┘
```

- AutoAnswer **不管任务顺序**——那是下游脚本的调度职责
- AutoAnswer **不管怎么做某个任务**——那是下游脚本的模块职责
- AutoAnswer **只管拉进程、配参数、发启动/停止信号、看结果**
- 不同的"剧本" = 不同的配置预设（Profile），由 adapter 层管理

---

## 2. 模块架构

```
AutoAnswer/
│
├── orchestrator/          ← 编排核心：拉起来→配置→启动→监视→收工
│   └── engine.py          ← 状态机（管理单个脚本实例的生命周期）
│
├── adapter/               ← 脚本适配层
│   ├── base.py            ← ScriptAdapter 简化接口（6 个方法）
│   ├── registry.py        ← 适配器注册表 / 工厂
│   ├── baas/              ← BAAS 适配器
│   │   ├── adapter.py     ← 进程拉起 + HTTP API 通信
│   │   ├── profile.py     ← 配置预设（"日常"、"总力战"、"活动"）
│   │   └── schemas.py     ← BAAS 数据模型解析
│   └── maa/               ← MAA 适配器（预留）
│       └── adapter.py
│
├── monitor/               ← 观测 / 遥测
│   ├── aggregator.py      ← 日志聚合
│   ├── status.py          ← 实时状态面板数据结构
│   └── reporter.py        ← 执行报告 / 通知推送
│
├── models/                ← 共享数据模型
│   └── script.py          ← ScriptInfo, ScriptStatus, Profile
│
├── api/                   ← AutoAnswer 自身的 API
│   ├── server.py          ← HTTP API（供 Web UI / 第三方调用）
│   └── routes/
│       ├── scripts.py     ← 脚本生命周期
│       └── profiles.py    ← 预设管理
│
├── cli/                   ← 命令行入口
│   └── main.py            ← autoanswer run baas with daily
│
├── storage/
│   ├── store.py
│   └── sqlite.py          ← 执行历史记录
│
├── pyproject.toml
├── README.md
└── PLAN.md
```

---

## 3. ScriptAdapter 接口（简化版）

```python
class ScriptAdapter(ABC):
    """所有游戏脚本适配器必须实现的接口"""

    # ── 进程生命周期 ──────────────────────
    @abstractmethod
    async def launch(self) -> bool: ...
    # → 拉起脚本进程（带 --api 参数启动 BAAS.exe）

    @abstractmethod
    async def terminate(self) -> bool: ...
    # → 关闭脚本进程

    # ── 调度控制（通过 API 通信）───────────
    @abstractmethod
    async def start_scheduler(self) -> bool: ...
    # → 通知脚本开始调度循环
    #    BAAS 侧：POST /api/script/start → send('start')

    @abstractmethod
    async def stop_scheduler(self) -> bool: ...
    # → 通知脚本停止调度
    #    BAAS 侧：POST /api/script/stop → send('stop')

    # ── 配置预设 ──────────────────────────
    @abstractmethod
    async def apply_profile(self, name: str) -> None: ...
    # → 应用一个配置预设（覆盖配置文件 + 通知热加载）
    #    BAAS 侧：改写 config.json / event.json 并通知 reload

    # ── 观测 ──────────────────────────────
    @abstractmethod
    async def get_status(self) -> ScriptStatus: ...

    @abstractmethod
    async def get_logs(self, since: float) -> list[LogEntry]: ...

    # ── 事件订阅 ──────────────────────────
    @abstractmethod
    def on(self, event: str, callback: Callable) -> None: ...
```

### 数据模型

```python
# ── 下游脚本的状态（从 GET /api/status 读取）──
class ScriptStatus(Enum):
    """下游脚本自身当前的运行状态"""
    DISCONNECTED = "disconnected"  # 连不上 / 进程没在跑
    IDLE         = "idle"          # 已连接，调度未启动
    RUNNING      = "running"       # 调度循环运行中
    ERROR        = "error"         # 异常

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
    name: str
    version: str
    status: ScriptStatus
    current_task: str | None
    connected: bool

@dataclass
class LogEntry:
    timestamp: float
    level: str
    source: str
    message: str

@dataclass
class Profile:
    name: str
    description: str
    # 具体结构由 adapter 子类定义
    # baas.Profile 包含 config/event/switch 的覆盖值
```

---

## 4. 配置预设（Profile）设计

配置预设是 adapter 层的概念，不同类型的脚本有不同的 Profile 结构。
每种脚本的 Profile 定义在该脚本的 adapter 目录下。

### BAAS 的 Profile

```python
# adapter/baas/profile.py

@dataclass
class BAASProfile:
    """BAAS 配置预设"""
    name: str
    description: str
    config: dict      # 覆盖 config.json 的字段
    event: dict       # 覆盖 event.json（启用/禁用任务）
    switch: dict      # 覆盖 switch.json


PROFILES: dict[str, BAASProfile] = {
    "daily": BAASProfile(
        name="daily",
        description="日常一条龙",
        config={},
        event={
            "cafe_reward":     {"enabled": True},
            "arena":           {"enabled": True},
            "lesson":          {"enabled": True},
            "common_shop":     {"enabled": True},
            "collect_reward":  {"enabled": True},
            "scrimmage":       {"enabled": True},
            "total_assault":   {"enabled": False},  # 日常不碰总力战
        },
    ),
    "total_assault": BAASProfile(
        name="total_assault",
        description="只清总力战票",
        config={
            "totalForceFightDifficulty": "TORMENT",
        },
        event={
            "total_assault": {"enabled": True, "priority": -999},
            "cafe_reward":   {"enabled": False},
            "arena":         {"enabled": False},
            "lesson":        {"enabled": False},
        },
    ),
    "all_in": BAASProfile(
        name="all_in",
        description="全开",
        event={task: {"enabled": True} for task in [
            "cafe_reward", "arena", "lesson", "common_shop",
            "collect_reward", "scrimmage", "total_assault",
            "friend", "rewarded_task", "momo_talk",
        ]},
    ),
}
```

`apply_profile` 的实现：

```python
# adapter/baas/adapter.py

async def apply_profile(self, name: str) -> None:
    profile = PROFILES[name]

    # 读取当前配置
    current_config = await self._api.get("/api/config/all")
    current_event = await self._api.get("/api/event/all")

    # 覆盖
    for key, value in profile.config.items():
        await self._api.put(f"/api/config/{key}", json={"value": value})

    for task_name, overrides in profile.event.items():
        await self._api.put(f"/api/event/{task_name}", json=overrides)

    # 通知 BAAS 热加载
    await self._api.post("/api/config/reload")
```

### MAA 的 Profile（预留） 

```python
# adapter/maa/profile.py

@dataclass
class MAAProfile:
    name: str
    description: str
    tasks: list[str]   # MAA 通过任务列表控制调度
    config: dict
```

不同脚本的 Profile 结构不一样，这是合理的——因为它们的配置模型本来就不同。
AutoAnswer 的编排层不关心 Profile 内部长什么样，它只调用 `adapter.apply_profile(name)`。

---

## 5. Orchestrator Engine

整个编排层的核心——一个简单的状态机，控制"一个脚本实例"的完整生命周期。

### 状态图

```
UNINITIALIZED --> LAUNCHING --> CONFIGURING --> RUNNING --> TERMINATING --> DONE
                                                                       |
                                                                       fail/disconnect
                                                                       |
                                                                       v
                                                                       DONE
`

### Engine 代码骨架

```python
@dataclass
class EngineResult:
    """一次编排执行的结果"""
    success: bool
    error: str | None = None
    run_duration: float | None = None


class ScriptEngine:
   """管理一个脚本实例的生命周期"""

    def __init__(self, adapter: ScriptAdapter):
        self.adapter = adapter
        self.state = EngineState.UNINITIALIZED

    async def run(self, profile_name: str) -> EngineResult:
        """一键执行：拉起进程 → 应用预设 → 启动调度 → 监听 → 关停"""
        self.state = EngineState.LAUNCHING
        ok = await self.adapter.launch()
        if not ok:
            return EngineResult(success=False, error="launch failed")

        self.state = EngineState.CONFIGURING
        await self.adapter.apply_profile(profile_name)

        self.state = EngineState.RUNNING
        ok = await self.adapter.start_scheduler()
        if not ok:
            return EngineResult(success=False, error="start failed")

        # 监听，直到脚本自己结束或被用户停掉
        while True:
            status = await self.adapter.get_status()
            if status != ScriptStatus.RUNNING:
                break
            await asyncio.sleep(2)

        self.state = EngineState.TERMINATING
        await self.adapter.terminate()

        self.state = EngineState.DONE
        return EngineResult(success=True)

    async def stop(self):
        """手动停止"""
        await self.adapter.stop_scheduler()
        await self.adapter.terminate()
        self.state = EngineState.DONE
```

Engine 的定位到此为止：它不决定跑什么任务，只管把这个脚本实例从生管到死。
更复杂的编排策略交给 shell 脚本 / cron / 外部调度器组合多个 autoanswer run 调用来实现。

---

## 6. 通信协议

### 6.1 AutoAnswer ↔ 目标脚本（本地 HTTP + SSE）

目标脚本（BAAS）启动一个轻量 HTTP 服务，绑定 127.0.0.1，随机端口，
端口号写入 `~/.autoanswer/{script_name}.port`。

| 方法 | 路径 | 对应接口 |
|------|------|----------|
| POST | /api/script/start | start_scheduler() |
| POST | /api/script/stop | stop_scheduler() |
| GET | /api/status | get_status() |
| GET | /api/config/{key} | 读配置 |
| PUT | /api/config/{key} | 写配置 |
| GET | /api/config/all | 读全部配置 |
| PUT | /api/event/{task} | 修改单个任务开关 |
| POST | /api/config/reload | 通知热加载 |
| GET | /api/logs?since=ts | get_logs() |
| GET | /api/events | SSE 事件流 |

### 6.2 连接流程

```
AutoAnswer                     BAAS (with HTTP API)
    │                                │
    │  1. launch()                    │
    │     subprocess.Popen(baas --api)│
    │     ───────────────────────────→│
    │                                │
    │  2. 等待端口就绪                 │
    │     while not 端口文件存在:      │
    │         sleep(0.5)              │
    │                                │
    │  3. 读端口文件                   │
    │     ~/.autoanswer/baas.port     │
    │     ←───────── 37421 ─────────→ │
    │                                │
    │  4. GET /api/status             │
    │     ←── ScriptInfo ─────────── │
    │                                │
    │  5. apply_profile("daily")     │
    │     PUT /api/event/cafe ...     │
    │     PUT /api/event/arena ...    │
    │     POST /api/config/reload     │
    │                                │
    │  6. POST /api/script/start      │
    │     ←── {"ok": true} ───────── │
    │                                │
    │  7. GET /api/events  (SSE)     │
    │     ←── {event: "task_change"} │
```

---

## 7. BAAS 端改动清单

### 7.1 新增文件

```
api/__init__.py
api/server.py       ← http.server 实现
api/discovery.py    ← 端口文件写入
```

### 7.2 需要改动的文件

- `main.py`：新增 `--api` / `--api-port` 参数，启动时拉起 API Server
- `core/config/config_set.py`：新增 `reload()` 方法（从文件重新加载配置）

### 7.3 不改的文件

- `core/Baas_thread.py` ── 直接复用 `send()` / `flag_run`
- `core/scheduler.py` ── 不改
- `window.py` ── 极小改动或无改动

### 7.4 API 路由映射

| 路由 | 内部调用 |
|------|---------|
| POST /api/script/start | main.get_thread(config).send('start') |
| POST /api/script/stop | thread.send('stop') |
| GET /api/status | 读 thread.flag_run, scheduler, connection |
| GET /api/config/{key} | thread.config_set.get(key) |
| PUT /api/config/{key} | thread.config_set.set(key, value) |
| GET /api/config/all | 序列化 thread.config_set.config |
| PUT /api/event/{task} | 读 event.json → 改对应项的 enabled/priority → 写回 |
| POST /api/config/reload | thread.config_set._init_config() |
| GET /api/logs | 从 Logger 的环形缓冲区读取 |
| GET /api/events | SSE 事件流（用队列桥接 Logger + button_signal） |

---

## 8. 用户界面

### CLI（主要入口）

```bash
# 跑一个脚本
autoanswer run baas with daily
autoanswer run baas with total_assault

# 查看状态
autoanswer status

# 手动停止
autoanswer stop baas

# 管理预设
autoanswer profile list
autoanswer profile show daily
```

### AutoAnswer API（供 Web UI 调用）

```bash
GET  /api/scripts                          # 列出所有已知脚本
POST /api/scripts/baas/run?profile=daily   # 启动 BAAS 日常
POST /api/scripts/baas/stop                # 停止 BAAS
GET  /api/scripts/baas/status              # 查 BAAS 状态
GET  /api/profiles                         # 列出所有可用预设
```

命令行支持 + API 支持，Web Dashboard 作为可选后续。

---

## 9. 技术选型

| 层面 | 选择 | 理由 |
|------|------|------|
| 语言 | Python 3.10+ | 与 BAAS 一致 |
| API 框架 | FastAPI / Starlette | 异步友好 |
| 持久化 | SQLite（aiosqlite） | 零配置 |
| CLI | Click / Typer | 简洁 |
| BAAS 端 API | Python 标准库 http.server | 零额外依赖 |

---

## 10. 开发路线

| Phase | 内容 | 预估 |
|-------|------|------|
| 1 — 骨架 | pyproject.toml, models/, adapter/base.py | 第 1 周 |
| 2 — BAAS 集成 | BAAS API Server + BAASAdapter + 端到端跑通 | 第 2-3 周 |
| 3 — 预设系统 | adapter/baas/profile.py + reload 机制 | 第 3 周 |
| 4 — 指挥层 | orchestrator/engine, CLI, 日志聚合 | 第 4 周 |
| 5 — API + Web | AutoAnswer 自身 API，可选 Dashboard | 第 5-6 周 |
| 6 — 扩展 | MAA 适配器 | 后续 |

---

## A. 关键决策记录

| 编号 | 决策 | 理由 |
|------|------|------|
| ADR-001 | AutoAnswer 不实现任务级调度 | 下游脚本已自带调度循环 |
| ADR-002 | 配置预设（Profile）放在 adapter 层 | 不同脚本的配置模型不同 |
| ADR-003 | 跨进程 HTTP + SSE 通信 | 解耦，非 Python 脚本也能接 |
| ADR-004 | BAAS API 用 Python 标准库 | 零额外依赖 |
| ADR-005 | CLI 是主要入口，API 是辅助 | 降低门槛，Web 是可选增值 |
