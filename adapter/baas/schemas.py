"""Parsing helpers that convert BAAS API JSON responses into AutoAnswer models."""
from __future__ import annotations

from models.script import ScriptInfo, ScriptStatus, LogEntry


def parse_status(raw: dict) -> ScriptInfo:
    """Build ScriptInfo from GET /api/status response."""
    connected = raw.get("connected", False)
    flag_run = raw.get("flag_run", False)

    if not connected:
        status = ScriptStatus.DISCONNECTED
    elif flag_run:
        status = ScriptStatus.RUNNING
    else:
        status = ScriptStatus.IDLE

    return ScriptInfo(
        name="baas",
        version="1.4.3",
        status=status,
        current_task=raw.get("current_task"),
        connected=connected,
    )


def parse_logs(raw: list[dict]) -> list[LogEntry]:
    """Build LogEntry list from GET /api/logs response."""
    return [
        LogEntry(
            timestamp=e["timestamp"],
            level=e["level"],
            source=e.get("source", "baas"),
            message=e["message"],
        )
        for e in raw
    ]
