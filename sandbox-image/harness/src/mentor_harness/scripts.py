"""Runs the platform scripts (`python -m mentor_scripts.<name>`, CONTRACTS.md section 4)."""

import asyncio
import json
import os
import subprocess
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from mentor_schemas import Profile

SCRIPT_ALLOWLIST: frozenset[str] = frozenset(
    {
        "record_event",
        "record_wellbeing",
        "wellbeing_window",
        "bkt_update",
        "sympy_check",
        "pdf_extract",
        "pdf_render",
        "check_report",
    }
)
THPT_ONLY_SCRIPTS: frozenset[str] = frozenset({"record_wellbeing", "wellbeing_window"})
MAX_SCRIPT_OUTPUT = 200_000


class ScriptError(Exception):
    """The script failed (exit code != 0, timeout or invalid output)."""


# (name, input, workspace_root, timeout_s) -> parsed JSON output
ScriptRunner = Callable[[str, dict[str, Any], Path, float], Awaitable[dict[str, Any]]]


def script_allowed(name: str, profile: Profile) -> bool:
    if name not in SCRIPT_ALLOWLIST:
        return False
    return profile == Profile.THPT or name not in THPT_ONLY_SCRIPTS


def _run_blocking(name: str, payload: dict[str, Any], root: Path, timeout_s: float) -> dict[str, Any]:
    env = {**os.environ, "WORKSPACE_ROOT": str(root), "PYTHONIOENCODING": "utf-8"}
    try:
        proc = subprocess.run(
            [sys.executable, "-m", f"mentor_scripts.{name}"],
            input=json.dumps(payload, ensure_ascii=False),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=root,
            env=env,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        raise ScriptError(f"{name} chạy quá {timeout_s:.0f}s") from exc
    out = proc.stdout[:MAX_SCRIPT_OUTPUT]
    try:
        data = json.loads(out) if out.strip() else {}
    except json.JSONDecodeError:
        data = None
    if proc.returncode != 0:
        msg = data.get("error") if isinstance(data, dict) else None
        raise ScriptError(msg or (proc.stderr.strip()[-500:] or f"{name} thoát với mã {proc.returncode}"))
    if not isinstance(data, dict):
        raise ScriptError(f"{name} trả về dữ liệu không phải JSON object")
    return data


async def run_mentor_script(name: str, payload: dict[str, Any], root: Path, timeout_s: float) -> dict[str, Any]:
    """Default ScriptRunner: subprocess in a worker thread (works on any event loop)."""
    if name not in SCRIPT_ALLOWLIST:
        raise ScriptError(f"Script không được phép: {name}")
    return await asyncio.to_thread(_run_blocking, name, payload, root, timeout_s)
