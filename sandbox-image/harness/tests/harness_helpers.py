"""Shared test helpers for the harness tests (imported by conftest and test modules)."""

import subprocess
from pathlib import Path
from typing import Any

from mentor_harness.agent import Harness
from mentor_schemas import Profile, SandboxEvent, TurnRequest

SKILL = """---
name: {name}
description: {desc}
profiles: [{profiles}]
version: 1
---
Hướng dẫn cho {name}.
"""

FILES = {
    "AGENTS.md": "# AGENTS.md — Mentor\nBạn là Mentor.\n",
    "me/profile.md": "# profile\n- Lớp 11, trường THPT A. (chat 20/10)\n",
    "me/preferences.md": "# preferences\n- Xưng mình, gọi em.\n",
    "me/now.md": "# now.md\n## Tuần này\n- Thi giữa kỳ Toán thứ Năm. (chat 28/10)\n",
    "goals/goals.md": "# goals\n- Đạt 8 Toán cuối kỳ.\n",
    "goals/plans/this-week.md": "# this-week\n- Ôn hàm số bậc hai.\n",
    "me/journal/2026-10-24.md": "journal 24\n",
    "me/journal/2026-10-25.md": "journal 25\n",
    "me/journal/2026-10-26.md": "journal 26\n",
    "me/journal/2026-10-27.md": "journal 27\n",
    "events.jsonl": "",
    ".mentor/activity.jsonl": "",
    ".mentor/skills/core/memory-keeper/SKILL.md": SKILL.format(
        name="memory-keeper", desc="Quy tắc ghi trí nhớ.", profiles="thpt, ncs"
    ),
    ".mentor/skills/thpt/math-tutoring/SKILL.md": SKILL.format(
        name="math-tutoring", desc="Dạy Toán THPT.", profiles="thpt"
    ),
    ".mentor/skills/ncs/literature-watch/SKILL.md": SKILL.format(
        name="literature-watch", desc="Theo dõi paper mới.", profiles="ncs"
    ),
}


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "safe.directory=*", *args], cwd=root, capture_output=True, text=True, check=True
    ).stdout


class FakeScripts:
    """Stands in for `python -m mentor_scripts.<name>`; records calls."""

    def __init__(self, responses: dict[str, dict[str, Any] | Exception] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[tuple[str, dict[str, Any], Path]] = []

    async def __call__(self, name: str, payload: dict[str, Any], root: Path, timeout_s: float) -> dict[str, Any]:
        self.calls.append((name, payload, root))
        out = self.responses.get(name, {"ok": True})
        if isinstance(out, Exception):
            raise out
        return out


def turn_request(text: str = "Chào mentor", profile: Profile = Profile.THPT, session_id: str = "s1") -> TurnRequest:
    return TurnRequest(session_id=session_id, user_id="u1", profile=profile, text=text)


async def collect(harness: Harness, req: TurnRequest) -> list[SandboxEvent]:
    return [e async for e in harness.stream_turn(req)]


def activity_lines(root: Path) -> list[str]:
    return [line for line in (root / ".mentor/activity.jsonl").read_text(encoding="utf-8").splitlines() if line]
