import json
from datetime import timedelta
from pathlib import Path

import pytest
from mentor_schemas import LearningEvent
from mentor_scripts.common import ScriptError
from mentor_scripts.record_event import record_event
from pydantic import ValidationError

EVENT = {
    "type": "problem_attempt",
    "subject": "math",
    "skill_ids": ["algebra.quadratic.formula"],
    "correct": True,
    "mode": "independent",
    "source_ref": "learning/evidence/2026-10-25-kiem-tra-15p.md",
    "grader": "sympy",
}


def test_record_event_appends_valid_lines(workspace: Path) -> None:
    first = record_event(dict(EVENT), workspace)
    second = record_event({**EVENT, "correct": False, "event_id": "ignored", "ts": "2000-01-01T00:00:00"}, workspace)
    lines = (workspace / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    events = [LearningEvent.model_validate_json(line) for line in lines]
    assert [e.event_id for e in events] == [first["event_id"], second["event_id"]]
    assert events[1].event_id != "ignored" and events[1].ts.year > 2000
    assert events[0].ts.utcoffset() == timedelta(hours=7)


@pytest.mark.parametrize(
    "bad",
    [
        {**EVENT, "mode": "copied"},
        {**EVENT, "skill_ids": []},
        {**EVENT, "source_ref": "../outside.md"},
        {k: v for k, v in EVENT.items() if k != "correct"},
    ],
)
def test_record_event_rejects_invalid(workspace: Path, bad: dict) -> None:
    with pytest.raises((ScriptError, ValidationError)):
        record_event(bad, workspace)
    assert not (workspace / "events.jsonl").exists()


def test_cli_record_event_and_errors(workspace: Path, run_cli) -> None:
    code, out = run_cli("record_event", EVENT)
    assert code == 0 and "event_id" in out
    line = (workspace / "events.jsonl").read_text(encoding="utf-8").strip()
    assert json.loads(line)["event_id"] == out["event_id"]

    code, out = run_cli("record_event", {**EVENT, "mode": "copied"})
    assert code == 1 and "mode" in out["error"]
    code, out = run_cli("record_event", None, raw=b"{not json")
    assert code == 1 and "JSON" in out["error"]
