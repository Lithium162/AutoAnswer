# AutoAnswer

A lightweight game script orchestration layer. It manages the lifecycle of game
automation scripts (BAAS, MAA, etc.) by:

1. **Launching** the script process
2. **Applying** a configuration profile
3. **Starting** the script's built-in scheduler
4. **Monitoring** its status
5. **Terminating** when done

AutoAnswer does **not** implement per-task scheduling — that is the responsibility
of each downstream script. Different "playbooks" are simply different configuration
profiles managed by each script's adapter.


## Quick Start

```bash
# Run BAAS with a daily profile
autoanswer run baas with daily

# Stop BAAS
autoanswer stop baas

# List available profiles
autoanswer profile list
```


## Architecture

| Layer | Directory | Responsibility |
|-------|-----------|---------------|
| Orchestrator | `orchestrator/` | Lifecycle state machine |
| Adapter | `adapter/` | Script-specific interface implementations |
| Models | `models/` | Shared data types (ScriptStatus, EngineState, etc.) |
| Monitor | `monitor/` | Log aggregation, status tracking, notifications |
| API | `api/` | HTTP API for external integration |
| CLI | `cli/` | Command-line interface |
| Storage | `storage/` | SQLite-backed execution history |


## Development

```bash
pip install -e .[dev]
```

See [PLAN.md](PLAN.md) for the full project plan.


## License

MIT
