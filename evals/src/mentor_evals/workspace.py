"""A fresh, provisioned learner workspace per scenario.

Uses the gateway's real `provision_workspace` (templates, AGENTS.md, skills, curricula, placeholders,
routines) with a local stand-in for `WorkspaceSync` that commits but has no mirror to push to.
"""

from __future__ import annotations

import json
import random
import subprocess
from datetime import date, timedelta
from pathlib import Path

from mentor_gateway.provisioning import provision_workspace
from mentor_schemas import Profile, WorkspacePaths

from mentor_evals.spec import EVALS_DIR

CONTENT_DIR = EVALS_DIR.parent / "mentor-content"
MEMORY_DIRS = ("me", "goals", "learning", "research", "reports")


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "safe.directory=*", "-c", "core.autocrlf=false", "-c", "commit.gpgsign=false", *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout


class _LocalSync:
    """Duck-typed `WorkspaceSync` for `provision_workspace`: one directory, no mirror, no push."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, user_id: str) -> Path:
        return self.root

    def init_from_dir(self, user_id: str) -> None:
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "add", "-A")
        git(
            self.root,
            "-c", "user.name=system", "-c", "user.email=system@local",
            "commit", "-q", "--allow-empty", "-m", "Khởi tạo workspace",
        )  # fmt: skip


def provision(
    root: Path,
    *,
    user_id: str,
    profile: Profile,
    display_name: str,
    language: str,
    seed_files: dict[str, str],
    content_dir: Path = CONTENT_DIR,
) -> list[str]:
    """Provision `root` (replacing it), write seed files on top and commit them as `system`."""
    warnings = provision_workspace(content_dir, _LocalSync(root), user_id, profile, display_name, language)
    if seed_files:
        for rel, content in seed_files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8", newline="\n")
        git(root, "add", "-A")
        git(root, "-c", "user.name=system", "-c", "user.email=system@local", "commit", "-q", "-m", "eval seed")
    return warnings


def wellbeing_series(today: date, *, days: int, negative: int, recorded: int | None = None, seed: int = 7) -> str:
    """`.mentor/wellbeing.jsonl` content: `recorded` of the last `days` days, `negative` of them negative."""
    recorded = days if recorded is None else recorded
    if not 0 <= negative <= recorded <= days:
        raise ValueError("need 0 <= negative <= recorded <= days")
    rng = random.Random(seed)
    dates = sorted(rng.sample([today - timedelta(days=i) for i in range(days)], recorded))
    negative_days = set(rng.sample(dates, negative))
    lines = []
    for d in dates:
        level = "negative" if d in negative_days else rng.choice(["none", "mild"])
        entry = {"date": d.isoformat(), "level": level, "note_ref": f"me/journal/{d.isoformat()}.md"}
        lines.append(json.dumps(entry, ensure_ascii=False))
    return "".join(line + "\n" for line in lines)


WELLBEING_PATH = WorkspacePaths.WELLBEING


def snapshot(root: Path, dirs: tuple[str, ...] = MEMORY_DIRS) -> dict[str, str]:
    """Text content of every file under the memory directories (workspace-relative POSIX paths)."""
    out: dict[str, str] = {}
    for d in dirs:
        base = root / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_file():
                try:
                    out[p.relative_to(root).as_posix()] = p.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
    return out
