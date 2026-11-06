"""Shared helpers for the mentor CLI scripts (CONTRACTS section 4).

Protocol: JSON object on stdin, JSON object on stdout, exit 0 on success and
exit 1 with {"error": "..."} otherwise. The workspace root is env WORKSPACE_ROOT or cwd.
"""

import json
import os
import sys
import tempfile
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

M = TypeVar("M", bound=BaseModel)

# Asia/Ho_Chi_Minh has no DST, so a fixed offset avoids needing tzdata on Windows dev machines.
VN_TZ = timezone(timedelta(hours=7), "Asia/Ho_Chi_Minh")

Handler = Callable[[dict[str, Any], Path], dict[str, Any]]


class ScriptError(Exception):
    """Expected failure; its message becomes {"error": ...}."""


def workspace_root() -> Path:
    return Path(os.environ.get("WORKSPACE_ROOT") or os.getcwd()).resolve()


def now_vn() -> datetime:
    return datetime.now(VN_TZ)


def today_vn() -> date:
    return now_vn().date()


def local_date(ts: datetime) -> date:
    """Learner-facing date of a timestamp; naive timestamps are taken as Vietnam local time."""
    if ts.tzinfo is None:
        return ts.date()
    return ts.astimezone(VN_TZ).date()


def parse_today(payload: dict[str, Any]) -> date:
    """Optional `today` (ISO date) override, used by tests and backfills."""
    raw = payload.get("today")
    if raw is None:
        return today_vn()
    try:
        return date.fromisoformat(str(raw))
    except ValueError as e:
        raise ScriptError(f"invalid today: {raw!r}") from e


def resolve_in_workspace(root: Path, rel: str) -> Path:
    """Resolve a workspace-relative path, refusing absolute paths and escapes."""
    if not isinstance(rel, str) or not rel.strip():
        raise ScriptError("path is required")
    p = PurePosixPath(rel.replace("\\", "/"))
    if p.is_absolute() or ".." in p.parts or (p.parts and ":" in p.parts[0]):
        raise ScriptError(f"path must be relative to the workspace: {rel!r}")
    full = (root / p).resolve()
    if full != root and root not in full.parents:
        raise ScriptError(f"path escapes the workspace: {rel!r}")
    return full


def is_safe_relpath(rel: str) -> bool:
    p = PurePosixPath(rel.replace("\\", "/"))
    return bool(rel) and not p.is_absolute() and ".." not in p.parts and ":" not in rel


def append_line(path: Path, line: str) -> None:
    """Append one line with a single O_APPEND write so concurrent appenders never interleave."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (line.rstrip("\n") + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o644)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write_text(path: Path, text: str) -> None:
    """Write via a temp file in the same directory, then rename over the target."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Objects from a JSONL file; blank and malformed lines are skipped."""
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def validate_or_none(model: type[M], obj: dict[str, Any]) -> M | None:
    """The validated model, or None for a corrupt log line (callers skip it)."""
    try:
        return model.model_validate(obj)
    except ValidationError:
        return None


def format_validation_error(e: ValidationError) -> str:
    parts = []
    for err in e.errors():
        loc = ".".join(str(x) for x in err["loc"]) or "input"
        parts.append(f"{loc}: {err['msg']}")
    return "invalid input: " + "; ".join(parts)


def _read_stdin() -> dict[str, Any]:
    raw = sys.stdin.buffer.read().decode("utf-8-sig").strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ScriptError(f"stdin is not valid JSON: {e.msg}") from e
    if not isinstance(payload, dict):
        raise ScriptError("stdin must be a JSON object")
    return payload


def _emit(obj: dict[str, Any]) -> None:
    sys.stdout.buffer.write(json.dumps(obj, ensure_ascii=False).encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


def run_cli(handler: Handler) -> None:
    """Entry point shared by every script: stdin JSON -> handler -> stdout JSON, exit code."""
    try:
        result = handler(_read_stdin(), workspace_root())
    except ScriptError as e:
        _emit({"error": str(e)})
        sys.exit(1)
    except ValidationError as e:
        _emit({"error": format_validation_error(e)})
        sys.exit(1)
    except Exception as e:  # noqa: BLE001 - the protocol requires JSON errors, never tracebacks
        _emit({"error": f"{type(e).__name__}: {e}"})
        sys.exit(1)
    _emit(result)
