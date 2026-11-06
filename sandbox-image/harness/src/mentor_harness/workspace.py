"""Workspace access for the harness: safe path resolution, activity log, transcripts, git."""

import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from mentor_schemas import ActivityEntry, WorkspacePaths

from mentor_harness.config import now_local

GIT_AUTHOR = "mentor <mentor@local>"


def ensure_git_safe_directory() -> None:
    """Trust every repo for git in this process and its children, without writing any config file.

    The gateway may run the container under an arbitrary uid whose $HOME does not exist, and the
    mounted /workspace may be owned by someone else. GIT_CONFIG_COUNT/KEY/VALUE (git >= 2.31) adds
    `safe.directory=*` through the environment, so `git config --global` (a $HOME write) is not needed.
    """
    count = int(os.environ.get("GIT_CONFIG_COUNT", "0") or 0)
    for i in range(count):
        if os.environ.get(f"GIT_CONFIG_KEY_{i}") == "safe.directory" and os.environ.get(f"GIT_CONFIG_VALUE_{i}") == "*":
            return
    os.environ[f"GIT_CONFIG_KEY_{count}"] = "safe.directory"
    os.environ[f"GIT_CONFIG_VALUE_{count}"] = "*"
    os.environ["GIT_CONFIG_COUNT"] = str(count + 1)


class PathError(ValueError):
    """A tool asked for a path outside the workspace or in a forbidden area."""


class Workspace:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()

    # ---- paths -----------------------------------------------------------------

    def normalize(self, path: str) -> str:
        """Return a clean workspace-relative POSIX path, or raise PathError."""
        raw = (path or "").strip().replace("\\", "/")
        if raw in ("", ".", "./", "/"):
            return "."
        if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
            raise PathError(f"Đường dẫn phải là tương đối trong workspace: {path}")
        parts = [p for p in PurePosixPath(raw).parts if p not in ("", ".")]
        if ".." in parts:
            raise PathError(f"Không được dùng '..' trong đường dẫn: {path}")
        return "/".join(parts) or "."

    def resolve(self, path: str) -> tuple[str, Path]:
        """Normalize `path` and return (relative POSIX path, absolute path inside the root).

        Rejects traversal, absolute paths, symlinks escaping the root and anything in `.git/`.
        """
        rel = self.normalize(path)
        if rel == ".git" or rel.startswith(".git/"):
            raise PathError("Không được truy cập .git/")
        abs_path = (self.root / rel).resolve() if rel != "." else self.root
        if abs_path != self.root and self.root not in abs_path.parents:
            raise PathError(f"Đường dẫn nằm ngoài workspace: {path}")
        return rel, abs_path

    def rel(self, abs_path: Path) -> str:
        return abs_path.resolve().relative_to(self.root).as_posix()

    def read_text(self, rel: str, default: str | None = None) -> str | None:
        """Read a workspace file as UTF-8 (harness use; no permission checks)."""
        p = self.root / rel
        try:
            return p.read_text(encoding="utf-8")
        except (FileNotFoundError, IsADirectoryError, UnicodeDecodeError):
            return default

    def write_text(self, rel: str, content: str) -> None:
        """Write a file as the harness (no agent permission checks)."""
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8", newline="\n")

    # ---- activity log ------------------------------------------------------------

    def log_activity(
        self,
        action: str,
        summary: str,
        *,
        target: str | None = None,
        session_id: str | None = None,
        job_id: str | None = None,
        actor: str = "mentor",
    ) -> ActivityEntry:
        """Append one ActivityEntry to .mentor/activity.jsonl. Never call this for crisis alerts."""
        entry = ActivityEntry(
            ts=now_local(),
            actor=actor,  # type: ignore[arg-type]
            action=action,
            target=target,
            summary=summary,
            session_id=session_id,
            job_id=job_id,
        )
        p = self.root / WorkspacePaths.ACTIVITY
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8", newline="\n") as f:
            f.write(entry.model_dump_json() + "\n")
        return entry

    # ---- transcripts ---------------------------------------------------------------

    @staticmethod
    def _safe_name(name: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "session"

    def transcript_path(self, name: str, when: datetime | None = None, suffix: str = ".md") -> str:
        when = when or now_local()
        return f"{WorkspacePaths.SESSIONS_DIR}/{when:%Y-%m-%d}/{self._safe_name(name)}{suffix}"

    def append_chat(self, name: str, records: list[dict[str, Any]], when: datetime | None = None) -> str:
        """Append visible chat messages to sessions/YYYY-MM-DD/<name>.jsonl (CONTRACTS "Sessions and chat history").

        Each record is {ts, role: "user"|"mentor", text, attachments: [path]}; never tool calls or prompts.
        """
        rel = self.transcript_path(name, when, ".jsonl")
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8", newline="\n") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return rel

    def load_chat(self, name: str, limit: int) -> list[dict[str, Any]]:
        """The last `limit` chat records of a session, across day folders, oldest first."""
        sessions = self.root / WorkspacePaths.SESSIONS_DIR
        if not sessions.is_dir():
            return []
        records: list[dict[str, Any]] = []
        for path in sorted(sessions.glob(f"*/{self._safe_name(name)}.jsonl")):
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for line in lines:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue  # a torn last line after a crash must not break the session
                if isinstance(record, dict):
                    records.append(record)
        return records[-limit:] if limit > 0 else []

    def append_transcript(self, name: str, text: str, when: datetime | None = None) -> str:
        """Append raw transcript text to sessions/YYYY-MM-DD/<name>.md; returns the path."""
        rel = self.transcript_path(name, when)
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        new = not p.exists()
        with p.open("a", encoding="utf-8", newline="\n") as f:
            if new:
                f.write(f"# Transcript {name}\n\n")
            f.write(text.rstrip() + "\n\n")
        return rel

    # ---- git ---------------------------------------------------------------------------

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-c", "safe.directory=*", "-c", "core.autocrlf=false", *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=check,
            timeout=60,
        )

    def ensure_repo(self) -> None:
        """Initialize a git repo if the workspace has none (dev only; D provisions real ones)."""
        if not (self.root / ".git").exists():
            self.root.mkdir(parents=True, exist_ok=True)
            self._git("init", "-q")

    def commit(self, message: str) -> str | None:
        """`git add -A && git commit` as mentor. Returns the new sha, or None if nothing changed."""
        self.ensure_repo()
        self._git("add", "-A")
        if not self._git("status", "--porcelain").stdout.strip():
            return None
        self._git(
            "-c", "user.name=mentor", "-c", "user.email=mentor@local",
            "commit", "-q", f"--author={GIT_AUTHOR}", "-m", message,
        )  # fmt: skip
        return self._git("rev-parse", "HEAD").stdout.strip()
