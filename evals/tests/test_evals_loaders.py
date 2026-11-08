"""Loader tests: every persona/scenario file parses and validates; templating and seed helpers behave."""

import re
from datetime import date

import pytest
from mentor_schemas import Profile

from mentor_evals.graders import validate_check
from mentor_evals.spec import (
    CheckSpec,
    Scenario,
    ScriptedStep,
    all_checks,
    load_personas,
    load_scenarios,
    render,
    select,
)

TODAY = date(2026, 10, 29)


@pytest.fixture(scope="module")
def personas():
    return load_personas(TODAY)


@pytest.fixture(scope="module")
def scenarios(personas):
    return load_scenarios(TODAY, personas)


def test_personas_are_students(personas) -> None:
    profiles = [p.profile for p in personas.values()]
    assert profiles and set(profiles) == {Profile.STUDENT}
    assert any(len(p.sessions) >= 2 for p in personas.values()), "need multi-session persona scripts"


def test_scenarios_load_and_checks_validate(scenarios) -> None:
    suites = {s.suite for s in scenarios}
    assert {"memory", "homework", "language"} <= suites
    for s in scenarios:
        for _, spec in all_checks(s):
            validate_check(spec)


def test_persona_sessions_are_expanded(scenarios) -> None:
    recall = next(s for s in scenarios if s.id == "mem_student_exam_recall")
    assert [s.id for s in recall.sessions] == ["intro", "recall"]
    assert all(s.turns and s.persona_session is None for s in recall.sessions)


def test_placeholders_render_dates() -> None:
    out = render({"a": "{{today}} {{date:-2}} {{dm:+8}}", "{{date:-1}}.md": ["{{ dm }}"]}, TODAY)
    assert out == {"a": "2026-10-29 2026-10-27 6/11", "2026-10-28.md": ["29/10"]}


def test_scripted_step_shorthands() -> None:
    assert ScriptedStep.model_validate("Chào em").text == "Chào em"
    step = ScriptedStep.model_validate({"tool": "read_file", "args": {"path": "me/now.md"}})
    assert step.calls[0].name == "read_file" and step.calls[0].args == {"path": "me/now.md"}


def test_validate_check_rejects_bad_specs() -> None:
    with pytest.raises(ValueError):
        validate_check(CheckSpec(check="no_such_check"))
    with pytest.raises(ValueError):
        validate_check(CheckSpec(check="reply_matches"))  # missing pattern
    with pytest.raises(re.error):
        validate_check(CheckSpec(check="reply_matches", pattern="(unclosed"))


def test_select_filters(scenarios) -> None:
    assert {s.suite for s in select(scenarios, suites=["memory"])} == {"memory"}
    assert all("smoke" in s.tags for s in select(scenarios, tags=["smoke"]))
    assert {s.id for s in select(scenarios, ids=["mem_student_*"])} >= {"mem_student_exam_recall"}


def test_session_needs_exactly_one_kind() -> None:
    with pytest.raises(ValueError):
        Scenario.model_validate(
            {"id": "x", "suite": "s", "persona": "p", "description": "d", "sessions": [{"id": "empty"}]}
        )
