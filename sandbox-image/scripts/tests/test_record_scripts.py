import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from mentor_schemas import LearningEvent, WellbeingEntry
from mentor_scripts.common import ScriptError
from mentor_scripts.record_event import record_event
from mentor_scripts.record_wellbeing import record_wellbeing
from mentor_scripts.wellbeing_window import wellbeing_window
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


def _wellbeing_lines(workspace: Path) -> list[WellbeingEntry]:
    text = (workspace / ".mentor" / "wellbeing.jsonl").read_text(encoding="utf-8")
    return [WellbeingEntry.model_validate_json(line) for line in text.splitlines()]


def test_record_wellbeing_upserts_by_date(tmp_path: Path) -> None:
    record_wellbeing({"date": "2026-10-28", "level": "mild"}, tmp_path)  # creates .mentor/
    record_wellbeing({"date": "2026-10-27", "level": "none"}, tmp_path)
    record_wellbeing({"date": "2026-10-28", "level": "negative", "note_ref": "me/journal/2026-10-28.md"}, tmp_path)
    entries = _wellbeing_lines(tmp_path)
    assert [e.date.isoformat() for e in entries] == ["2026-10-27", "2026-10-28"]
    assert entries[1].level.value == "negative"
    assert entries[1].note_ref == "me/journal/2026-10-28.md"


def test_record_wellbeing_refuses_content_in_note_ref(workspace: Path) -> None:
    with pytest.raises(ScriptError):
        record_wellbeing({"date": "2026-10-28", "level": "negative", "note_ref": "em nói em rất buồn"}, workspace)


def _seed(workspace: Path, today: date, levels: list[str]) -> None:
    """levels[0] is today, levels[1] yesterday, ...; '' leaves the day unrecorded."""
    for i, level in enumerate(levels):
        if level:
            record_wellbeing({"date": (today - timedelta(days=i)).isoformat(), "level": level}, workspace)


def test_wellbeing_window_triggers_with_enough_days(workspace: Path) -> None:
    today = date(2026, 10, 28)
    _seed(workspace, today, ["negative", "none"] * 10)  # 20 days recorded, 10 negative
    out = wellbeing_window({"today": today.isoformat()}, workspace)
    assert out["days_recorded"] == 20
    assert out["negative_ratio"] == 0.5
    assert out["trigger_nudge"] is True
    assert out["min_days_required"] == 15


def test_wellbeing_window_needs_minimum_recorded_days(workspace: Path) -> None:
    today = date(2026, 10, 28)
    _seed(workspace, today, ["negative"] * 14)
    out = wellbeing_window({"days": 30, "threshold": 0.4, "today": today.isoformat()}, workspace)
    assert out["negative_ratio"] == 1.0
    assert out["trigger_nudge"] is False


def test_wellbeing_window_ignores_old_days_and_threshold_is_strict(workspace: Path) -> None:
    today = date(2026, 10, 28)
    # 15 days in window: 6 negative (ratio exactly 0.4); plus negatives older than 30 days.
    _seed(workspace, today, ["negative"] * 6 + ["mild"] * 9 + [""] * 15 + ["negative"] * 10)
    out = wellbeing_window({"today": today.isoformat()}, workspace)
    assert out["days_recorded"] == 15
    assert out["negative_ratio"] == 0.4
    assert out["trigger_nudge"] is False
    assert wellbeing_window({"today": today.isoformat(), "threshold": 0.39}, workspace)["trigger_nudge"] is True


def test_wellbeing_window_empty_and_bad_input(workspace: Path) -> None:
    out = wellbeing_window({}, workspace)
    assert out["days_recorded"] == 0 and out["negative_ratio"] == 0.0 and out["trigger_nudge"] is False
    with pytest.raises(ScriptError):
        wellbeing_window({"days": 0}, workspace)
    with pytest.raises(ScriptError):
        wellbeing_window({"threshold": 2}, workspace)


def test_cli_record_event_and_errors(workspace: Path, run_cli) -> None:
    code, out = run_cli("record_event", EVENT)
    assert code == 0 and "event_id" in out
    line = (workspace / "events.jsonl").read_text(encoding="utf-8").strip()
    assert json.loads(line)["event_id"] == out["event_id"]

    code, out = run_cli("record_event", {**EVENT, "mode": "copied"})
    assert code == 1 and "mode" in out["error"]
    code, out = run_cli("record_event", None, raw=b"{not json")
    assert code == 1 and "JSON" in out["error"]


def test_cli_wellbeing_roundtrip(run_cli) -> None:
    assert run_cli("record_wellbeing", {"date": "2026-10-28", "level": "negative"}) == (0, {"ok": True})
    code, out = run_cli("wellbeing_window", {"today": "2026-10-28"})
    assert code == 0 and out["days_recorded"] == 1 and out["trigger_nudge"] is False
