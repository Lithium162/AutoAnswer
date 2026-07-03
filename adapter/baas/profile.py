"""BAAS configuration profiles — presets that combine config + event + switch overrides.

A profile is applied via the BAAS API (PUT /api/config/{key}, PUT /api/event/{task}).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from models.script import Profile


@dataclass
class BAASProfile(Profile):
    """BAAS-specific profile with config/event/switch override maps."""
    event: dict[str, dict[str, Any]] = field(default_factory=dict)
    switch: dict[str, Any] = field(default_factory=dict)


# ── Built-in profiles ───────────────────────────────────

PROFILES: dict[str, BAASProfile] = {
    "daily": BAASProfile(
        name="daily",
        description="Everyday routine — cafe, arena, shop, lessons, scrimmage (no total assault)",
        config={},
        event={
            "restart":                {"enabled": True},
            "cafe_reward":            {"enabled": True},
            "arena":                  {"enabled": True},
            "lesson":                 {"enabled": True},
            "common_shop":            {"enabled": True},
            "collect_reward":         {"enabled": True},
            "collect_daily_power":    {"enabled": True},
            "scrimmage":              {"enabled": True},
            "rewarded_task":          {"enabled": True},
            "friend":                 {"enabled": True},
            "mail":                   {"enabled": True},
            "momo_talk":              {"enabled": True},
            "create":                 {"enabled": True},
            "total_assault":          {"enabled": False},
            "tactical_challenge_shop":{"enabled": False},
        },
    ),

    "total_assault": BAASProfile(
        name="total_assault",
        description="Total assault only — disable everything else",
        config={
            "totalForceFightDifficulty": "TORMENT",
        },
        event={
            "total_assault":          {"enabled": True,  "priority": -999},
            "restart":                {"enabled": True},
            "cafe_reward":            {"enabled": False},
            "arena":                  {"enabled": False},
            "lesson":                 {"enabled": False},
            "common_shop":            {"enabled": False},
            "collect_reward":         {"enabled": False},
            "scrimmage":              {"enabled": False},
            "rewarded_task":          {"enabled": False},
            "friend":                 {"enabled": False},
            "mail":                   {"enabled": False},
            "momo_talk":              {"enabled": False},
            "create":                 {"enabled": False},
            "tactical_challenge_shop":{"enabled": False},
        },
    ),

    "all_in": BAASProfile(
        name="all_in",
        description="Enable everything",
        event={task: {"enabled": True} for task in [
            "restart", "cafe_reward", "arena", "lesson", "common_shop",
            "collect_reward", "collect_daily_power", "scrimmage",
            "rewarded_task", "friend", "mail", "momo_talk", "create",
            "total_assault", "tactical_challenge_shop",
            "explore_normal_task", "explore_hard_task", "main_story",
            "group_story", "mini_story",
        ]},
    ),

    "idle": BAASProfile(
        name="idle",
        description="Do nothing — disable all scheduled tasks",
        event={},
    ),
}


def list_profiles() -> list[str]:
    """Return names of all built-in profiles."""
    return list(PROFILES.keys())


def get_profile(name: str) -> BAASProfile:
    """Get a profile by name.  Raises KeyError if not found."""
    if name not in PROFILES:
        raise KeyError(f"Unknown BAAS profile '{name}'. Available: {list_profiles()}")
    return PROFILES[name]
