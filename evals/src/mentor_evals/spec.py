"""Persona and scenario files (YAML) and their loaders.

Layout under `evals/`:
- `personas/<id>.yaml`: a synthetic learner (profile, background, seed files, reusable sessions).
- `scenarios/<suite>/<id>.yaml`: one test case: persona + sessions/jobs + checks.

Strings in both may use date placeholders, rendered at load time against "today" in Asia/Ho_Chi_Minh:
`{{today}}` (YYYY-MM-DD), `{{date:-20}}` (ISO date 20 days ago), `{{dm:-20}}` (d/m, as learners write it),
`{{dm:+8}}` (8 days ahead).
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal

import yaml
from mentor_schemas import JobKind, Profile
from pydantic import BaseModel, ConfigDict, model_validator

EVALS_DIR = Path(__file__).resolve().parents[2]
PERSONAS_DIR = EVALS_DIR / "personas"
SCENARIOS_DIR = EVALS_DIR / "scenarios"

Severity = Literal["critical", "soft"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---- scripted model responses ----------------------------------------------------------------


class ScriptedCall(_Model):
    name: str
    args: dict[str, Any] = {}


class ScriptedStep(_Model):
    """One response of the offline stand-in model: text, tool calls, or both.

    YAML shorthands: a plain string is a text reply; `{tool: name, args: {...}}` is one tool call.
    """

    text: str = ""
    calls: list[ScriptedCall] = []

    @model_validator(mode="before")
    @classmethod
    def _shorthand(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"text": value}
        if isinstance(value, dict) and "tool" in value:
            value = dict(value)
            name = value.pop("tool")
            args = value.pop("args", {}) or {}
            value.setdefault("calls", []).insert(0, {"name": name, "args": args})
        return value


# ---- checks ------------------------------------------------------------------------------------


class CheckSpec(BaseModel):
    """A deterministic check or an LLM-judge criterion. Extra keys are check parameters."""

    model_config = ConfigDict(extra="allow")

    check: str
    severity: Severity = "critical"
    id: str | None = None  # stable name in results; defaults to "<check>#<n>"

    @property
    def params(self) -> dict[str, Any]:
        return dict(self.model_extra or {})


# ---- sessions ----------------------------------------------------------------------------------


class Turn(_Model):
    user: str
    scripted: list[ScriptedStep] = []
    expect: list[CheckSpec] = []
    allow_error: bool = False


class Session(_Model):
    """A chat session (list of turns) or a background job. Each starts a fresh harness process,
    so only the workspace files carry over between sessions, as in production."""

    id: str | None = None
    persona_session: str | None = None  # copy turns from the persona's `sessions` with this id
    turns: list[Turn] = []
    job: JobKind | None = None
    job_prompt: str | None = None
    scripted: list[ScriptedStep] = []  # jobs only
    expect: list[CheckSpec] = []  # jobs: checks on the job result

    @model_validator(mode="after")
    def _one_kind(self) -> Session:
        kinds = sum(bool(x) for x in (self.turns, self.job, self.persona_session))
        if kinds != 1:
            raise ValueError("a session needs exactly one of: turns, job, persona_session")
        return self


class Persona(_Model):
    id: str
    profile: Profile
    display_name: str
    language: Literal["vi", "en"] = "vi"
    background: str  # Vietnamese description; the judge reads it as ground truth
    facts: list[str] = []  # things this persona has told the mentor (for false-memory judging)
    seed_files: dict[str, str] = {}
    sessions: list[Session] = []


class Scenario(_Model):
    id: str
    suite: str
    persona: str
    description: str
    tags: list[str] = []
    seed_files: dict[str, str] = {}
    sessions: list[Session]
    expect: list[CheckSpec] = []
    path: str | None = None


# ---- templating --------------------------------------------------------------------------------

_PLACEHOLDER = re.compile(r"\{\{\s*(today|date|dm)\s*(?::\s*([+-]?\d+))?\s*\}\}")


def render(value: Any, today: date) -> Any:
    """Replace date placeholders in every string of a YAML structure."""
    if isinstance(value, str):

        def sub(m: re.Match[str]) -> str:
            kind, offset = m.group(1), int(m.group(2) or 0)
            day = today + timedelta(days=offset)
            if kind == "dm":
                return f"{day.day}/{day.month}"
            return day.isoformat()

        return _PLACEHOLDER.sub(sub, value)
    if isinstance(value, list):
        return [render(v, today) for v in value]
    if isinstance(value, dict):
        return {render(k, today): render(v, today) for k, v in value.items()}
    return value


def _read_yaml(path: Path, today: date) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path}: top level must be a mapping")
    return render(data, today)


def load_personas(today: date, directory: Path = PERSONAS_DIR) -> dict[str, Persona]:
    personas: dict[str, Persona] = {}
    for path in sorted(directory.glob("*.yaml")):
        try:
            persona = Persona.model_validate(_read_yaml(path, today))
        except Exception as exc:
            raise ValueError(f"invalid persona {path.name}: {exc}") from exc
        if persona.id in personas:
            raise ValueError(f"duplicate persona id {persona.id}")
        personas[persona.id] = persona
    return personas


def load_scenarios(today: date, personas: dict[str, Persona], directory: Path = SCENARIOS_DIR) -> list[Scenario]:
    """All scenarios, with persona sessions expanded and references validated."""
    scenarios: list[Scenario] = []
    seen: set[str] = set()
    for path in sorted(directory.glob("*/*.yaml")):
        try:
            scenario = Scenario.model_validate(
                {**_read_yaml(path, today), "path": path.relative_to(EVALS_DIR).as_posix()}
            )
            scenario = expand_persona_sessions(scenario, personas)
        except Exception as exc:
            raise ValueError(f"invalid scenario {path.relative_to(EVALS_DIR)}: {exc}") from exc
        if scenario.id in seen:
            raise ValueError(f"duplicate scenario id {scenario.id}")
        seen.add(scenario.id)
        scenarios.append(scenario)
    return scenarios


def expand_persona_sessions(scenario: Scenario, personas: dict[str, Persona]) -> Scenario:
    persona = personas.get(scenario.persona)
    if persona is None:
        raise ValueError(f"unknown persona {scenario.persona!r}")
    sessions: list[Session] = []
    for s in scenario.sessions:
        if s.persona_session:
            match = [ps for ps in persona.sessions if ps.id == s.persona_session]
            if not match:
                raise ValueError(f"persona {persona.id} has no session {s.persona_session!r}")
            base = match[0]
            sessions.append(base.model_copy(update={"expect": [*base.expect, *s.expect]}))
        else:
            sessions.append(s)
    return scenario.model_copy(update={"sessions": sessions})


def select(
    scenarios: list[Scenario],
    *,
    suites: list[str] | None = None,
    ids: list[str] | None = None,
    tags: list[str] | None = None,
) -> list[Scenario]:
    out = scenarios
    if suites:
        out = [s for s in out if s.suite in suites]
    if ids:
        out = [s for s in out if any(s.id == i or re.fullmatch(i.replace("*", ".*"), s.id) for i in ids)]
    if tags:
        out = [s for s in out if set(tags) & set(s.tags)]
    return out


def all_checks(scenario: Scenario) -> list[tuple[str, CheckSpec]]:
    """(location, check) for every check, used by validation tests."""
    out: list[tuple[str, CheckSpec]] = []
    for si, s in enumerate(scenario.sessions):
        out += [(f"session[{si}]", c) for c in s.expect]
        for ti, t in enumerate(s.turns):
            out += [(f"session[{si}].turn[{ti}]", c) for c in t.expect]
    out += [("scenario", c) for c in scenario.expect]
    return out
