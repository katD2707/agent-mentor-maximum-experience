"""record_wellbeing: upsert one day's wellbeing level into .mentor/wellbeing.jsonl (THPT only).

Input: {date, level: none|mild|negative, note_ref?}. Output: {"ok": true}.
Only a level and an optional journal path are stored, never content: note_ref must be a
workspace-relative .md path (normally me/journal/YYYY-MM-DD.md), which keeps quotes out.
"""

import re
from pathlib import Path
from typing import Any

from mentor_schemas import WellbeingEntry, WorkspacePaths

from mentor_scripts.common import ScriptError, atomic_write_text, is_safe_relpath, read_jsonl, run_cli, validate_or_none

_NOTE_REF = re.compile(r"^[\w./-]+\.md$")


def record_wellbeing(payload: dict[str, Any], root: Path) -> dict[str, Any]:
    entry = WellbeingEntry(**payload)
    if entry.note_ref is not None and not (_NOTE_REF.match(entry.note_ref) and is_safe_relpath(entry.note_ref)):
        raise ScriptError("note_ref must be a workspace-relative .md path such as me/journal/2026-10-28.md")

    path = root / WorkspacePaths.WELLBEING
    by_date: dict[str, str] = {}
    for obj in read_jsonl(path):
        old = validate_or_none(WellbeingEntry, obj)  # drop corrupt lines rather than fail the write
        if old is not None:
            by_date[old.date.isoformat()] = old.model_dump_json()
    by_date[entry.date.isoformat()] = entry.model_dump_json()

    atomic_write_text(path, "".join(by_date[d] + "\n" for d in sorted(by_date)))
    return {"ok": True}


def main() -> None:
    run_cli(record_wellbeing)


if __name__ == "__main__":
    main()
