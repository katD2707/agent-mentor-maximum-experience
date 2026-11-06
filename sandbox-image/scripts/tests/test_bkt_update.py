import itertools
import json
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from mentor_scripts.bkt_update import (
    DEFAULT_PARAMS,
    bkt_step,
    bkt_update,
    compute_states,
    load_curriculum,
    load_events,
    review_interval,
)
from mentor_scripts.common import VN_TZ, ScriptError

QUAD = "algebra.quadratic.formula"
LINEAR = "algebra.linear.solve"
VIETA = "algebra.quadratic.vieta"


def write_events(workspace: Path, specs: list[tuple[str, bool, str, str]], hint_count: int = 0) -> None:
    """specs: (skill_id, correct, mode, 'YYYY-MM-DD'); written in order, one hour apart."""
    with (workspace / "events.jsonl").open("a", encoding="utf-8") as f:
        for i, (skill, correct, mode, day) in enumerate(specs):
            ts = datetime.fromisoformat(day).replace(hour=8, tzinfo=VN_TZ) + timedelta(hours=i)
            event = {
                "event_id": str(uuid.uuid4()),
                "ts": ts.isoformat(),
                "type": "problem_attempt",
                "subject": "math",
                "skill_ids": [skill],
                "correct": correct,
                "mode": mode,
                "hint_count": hint_count,
                "source_ref": "learning/evidence/x.md",
            }
            f.write(json.dumps(event) + "\n")


def mastery(workspace: Path, skill: str) -> float:
    states = compute_states(load_events(workspace, "math"), load_curriculum(workspace, "math"))
    return states[skill].mastery


def test_bkt_step_direction() -> None:
    p = DEFAULT_PARAMS["p_init"]
    assert bkt_step(p, True, DEFAULT_PARAMS) > p
    assert bkt_step(p, False, DEFAULT_PARAMS) < p
    assert 0 < bkt_step(0.99, True, DEFAULT_PARAMS) <= 1


def test_correct_independent_answers_raise_mastery(workspace: Path) -> None:
    history = []
    for i in range(5):
        write_events(workspace, [(QUAD, True, "independent", f"2026-10-{20 + i}")])
        history.append(mastery(workspace, QUAD))
    assert all(b > a for a, b in itertools.pairwise(history))
    assert history[0] > DEFAULT_PARAMS["p_init"]
    assert history[-1] > 0.9


def test_guided_answers_do_not_change_mastery(workspace: Path) -> None:
    write_events(workspace, [(QUAD, True, "independent", "2026-10-20")])
    before = mastery(workspace, QUAD)
    write_events(workspace, [(QUAD, True, "guided", "2026-10-21"), (QUAD, False, "guided", "2026-10-22")])
    write_events(workspace, [(QUAD, True, "independent", "2026-10-23")], hint_count=2)  # hints = process only
    states = compute_states(load_events(workspace, "math"), load_curriculum(workspace, "math"))
    assert states[QUAD].mastery == before
    assert states[QUAD].guided_attempts == 3
    assert states[QUAD].mastery_attempts == 1
    assert states[QUAD].last_event == date(2026, 10, 23)


def test_classroom_graded_counts_and_wrong_answers_lower_mastery(workspace: Path) -> None:
    write_events(workspace, [(QUAD, True, "classroom_graded", "2026-10-20")] * 3)
    high = mastery(workspace, QUAD)
    write_events(workspace, [(QUAD, False, "classroom_graded", "2026-10-21")])
    assert mastery(workspace, QUAD) < high


def test_review_interval_ladder() -> None:
    assert [review_interval(m) for m in (0.1, 0.5, 0.7, 0.9, 0.97)] == [1, 3, 7, 14, 30]


def test_bkt_update_writes_tables(workspace: Path) -> None:
    write_events(
        workspace,
        [
            (LINEAR, False, "independent", "2026-10-20"),
            (LINEAR, False, "independent", "2026-10-21"),
            (QUAD, True, "independent", "2026-10-20"),
            (QUAD, True, "independent", "2026-10-22"),
            (VIETA, True, "guided", "2026-10-25"),
            ("geometry.unknown", True, "independent", "2026-10-26"),
        ],
    )
    out = bkt_update({"subject": "math", "today": "2026-10-23"}, workspace)
    assert out["skills_updated"] == 4

    skills = (workspace / "learning/math/skills.md").read_text(encoding="utf-8")
    assert "| skill_id | Tên | Mastery | Bằng chứng | Lần cuối |" in skills
    rows = [line for line in skills.splitlines() if line.startswith(("| algebra", "| geometry"))]
    assert [r.split("|")[1].strip() for r in rows] == sorted([LINEAR, QUAD, VIETA, "geometry.unknown"])
    quad_row = next(r for r in rows if QUAD in r)
    assert "Công thức nghiệm phương trình bậc hai" in quad_row
    assert "2 đúng trên 2 bài độc lập" in quad_row and "2026-10-22" in quad_row
    vieta_row = next(r for r in rows if VIETA in r)
    assert "0.20" in vieta_row and "1 bài có gợi ý" in vieta_row

    review = (workspace / "learning/math/review-queue.md").read_text(encoding="utf-8")
    due_part, later_part = review.split("## Sắp tới")
    # Linear: last attempt wrong on 10-21 -> due 10-22 (overdue on 10-23), flagged.
    assert LINEAR in due_part and "lần gần nhất làm sai" in due_part
    # Quadratic: mastery ~0.8+ after two correct answers -> due well after 10-22, prerequisite is weak.
    quad_line = next(line for line in later_part.splitlines() if QUAD in line)
    assert f"nền tảng yếu: {LINEAR}" in quad_line
    # Guided-only Vi-ét: due the day after practice, asks for an independent attempt.
    vieta_line = next(line for line in later_part.splitlines() if VIETA in line)
    assert "2026-10-26" in vieta_line and "cần làm một bài độc lập" in vieta_line
    assert out["due_count"] == 1


def test_bkt_update_is_deterministic(workspace: Path) -> None:
    write_events(workspace, [(QUAD, True, "independent", "2026-10-20"), (LINEAR, False, "independent", "2026-10-21")])
    bkt_update({"subject": "math", "today": "2026-10-28"}, workspace)
    first = [(workspace / f"learning/math/{n}").read_bytes() for n in ("skills.md", "review-queue.md")]
    bkt_update({"subject": "math", "today": "2026-10-28"}, workspace)
    second = [(workspace / f"learning/math/{n}").read_bytes() for n in ("skills.md", "review-queue.md")]
    assert first == second


def test_bkt_update_without_curriculum_or_events(tmp_path: Path) -> None:
    out = bkt_update({"subject": "math", "today": "2026-10-28"}, tmp_path)
    assert out == {"skills_updated": 0, "due_count": 0}
    assert "Không có." in (tmp_path / "learning/math/review-queue.md").read_text(encoding="utf-8")


def test_bkt_update_rejects_bad_subject(workspace: Path) -> None:
    with pytest.raises(ScriptError):
        bkt_update({"subject": "../me"}, workspace)


def test_bkt_params_override_from_curriculum(workspace: Path) -> None:
    path = workspace / ".mentor/curricula/math.yaml"
    path.write_text(path.read_text(encoding="utf-8") + "    bkt: {p_init: 0.5}\n", encoding="utf-8")
    assert load_curriculum(workspace, "math")[VIETA].params["p_init"] == 0.5
    write_events(workspace, [(VIETA, True, "guided", "2026-10-20")])
    assert mastery(workspace, VIETA) == 0.5


REAL_CURRICULUM = Path(__file__).resolve().parents[3] / "mentor-content" / "curricula" / "math.yaml"


def test_real_curriculum_loads(workspace: Path) -> None:
    """Track B's real skill graph parses and drives bkt_update."""
    assert REAL_CURRICULUM.is_file(), REAL_CURRICULUM
    target = workspace / ".mentor/curricula/math.yaml"
    target.write_bytes(REAL_CURRICULUM.read_bytes())
    curriculum = load_curriculum(workspace, "math")
    assert len(curriculum) >= 20
    assert all(skill.title for skill in curriculum.values())
    assert all(p in curriculum for skill in curriculum.values() for p in skill.prerequisites)
    assert QUAD in curriculum and LINEAR in curriculum[QUAD].prerequisites

    write_events(workspace, [(QUAD, True, "independent", "2026-10-20")])
    out = bkt_update({"subject": "math", "today": "2026-10-21"}, workspace)
    assert out["skills_updated"] == 1
    assert curriculum[QUAD].title in (workspace / "learning/math/skills.md").read_text(encoding="utf-8")


def test_cli_bkt_update(workspace: Path, run_cli) -> None:
    write_events(workspace, [(QUAD, True, "independent", "2026-10-20")])
    code, out = run_cli("bkt_update", {"subject": "math", "today": "2026-10-21"})
    assert code == 0 and out["skills_updated"] == 1
    assert (workspace / "learning/math/skills.md").exists()
