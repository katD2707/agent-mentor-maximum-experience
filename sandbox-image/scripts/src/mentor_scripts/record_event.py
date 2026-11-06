"""record_event: validate a LearningEvent and append it to events.jsonl.

Input: LearningEvent fields minus event_id and ts (both are generated here; caller values are ignored).
Output: {"event_id": "<uuid4>"}.
"""

import uuid
from pathlib import Path
from typing import Any

from mentor_schemas import LearningEvent, WorkspacePaths

from mentor_scripts.common import ScriptError, append_line, is_safe_relpath, now_vn, run_cli


def record_event(payload: dict[str, Any], root: Path) -> dict[str, Any]:
    fields = {k: v for k, v in payload.items() if k not in ("event_id", "ts")}
    event = LearningEvent(event_id=str(uuid.uuid4()), ts=now_vn(), **fields)
    if not event.skill_ids or any(not s.strip() for s in event.skill_ids):
        raise ScriptError("skill_ids must be a non-empty list of skill ids")
    if not event.subject.strip():
        raise ScriptError("subject is required")
    if event.hint_count < 0:
        raise ScriptError("hint_count must be >= 0")
    if not is_safe_relpath(event.source_ref):
        raise ScriptError("source_ref must be a workspace-relative path")
    append_line(root / WorkspacePaths.EVENTS, event.model_dump_json())
    return {"event_id": event.event_id}


def main() -> None:
    run_cli(record_event)


if __name__ == "__main__":
    main()
