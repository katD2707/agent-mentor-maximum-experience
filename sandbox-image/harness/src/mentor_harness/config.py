"""Harness settings, read from the environment (CONTRACTS.md section 2)."""

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from mentor_schemas import Profile

try:
    from zoneinfo import ZoneInfo

    LOCAL_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
except (ImportError, KeyError, ValueError):  # no tz database (e.g. Windows without tzdata); Vietnam has no DST
    LOCAL_TZ = timezone(timedelta(hours=7), "Asia/Ho_Chi_Minh")


def now_local() -> datetime:
    """Current time in the learner's time zone."""
    return datetime.now(LOCAL_TZ)


@dataclass
class Settings:
    workspace_root: Path
    model_mode: Literal["router", "scripted"] = "scripted"
    model_router_url: str = "http://localhost:4000"
    model_router_key: str = ""
    profile: Profile | None = None  # when set, overrides the profile in requests
    user_id: str | None = None
    max_tool_rounds: int = 12
    turn_token_cap: int = 200_000  # prompt + completion tokens across all calls in one turn
    job_token_cap: int = 600_000
    max_output_tokens: int = 4096
    approval_timeout_s: float = 300.0
    script_timeout_s: float = 30.0  # scripts have no internal timeout (sympy can hang)
    model_timeout_s: float = 120.0
    session_history_messages: int = 60

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ
        mode = env.get("MENTOR_MODEL_MODE", "router" if env.get("MODEL_ROUTER_URL") else "scripted")
        if mode not in ("router", "scripted"):
            raise ValueError(f"MENTOR_MODEL_MODE must be 'router' or 'scripted', got {mode!r}")
        profile = env.get("MENTOR_PROFILE") or None
        return cls(
            workspace_root=Path(env.get("WORKSPACE_ROOT", "/workspace")),
            model_mode=mode,  # type: ignore[arg-type]
            model_router_url=env.get("MODEL_ROUTER_URL", "http://localhost:4000"),
            model_router_key=env.get("MODEL_ROUTER_KEY", ""),
            profile=Profile(profile) if profile else None,
            user_id=env.get("MENTOR_USER_ID") or None,
            max_tool_rounds=int(env.get("MENTOR_MAX_TOOL_ROUNDS", 12)),
            turn_token_cap=int(env.get("MENTOR_TURN_TOKEN_CAP", 200_000)),
            job_token_cap=int(env.get("MENTOR_JOB_TOKEN_CAP", 600_000)),
            approval_timeout_s=float(env.get("MENTOR_APPROVAL_TIMEOUT_S", 300)),
        )
