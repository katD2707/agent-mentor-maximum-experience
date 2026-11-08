"""Static checks for Track B content: AGENTS.md, skills, workspace templates, curriculum.

Run from the repo root: `uv run pytest mentor-content -q`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from mentor_schemas import (
    EvidenceMode,
    JobKind,
    LearningEvent,
    ProactivityLevel,
    Routine,
    RoutinesFile,
    is_agent_writable,
)

CONTENT = Path(__file__).resolve().parents[1]
AGENTS_MD = CONTENT / "AGENTS.md"
SKILLS_DIR = CONTENT / "skills"
TEMPLATES = CONTENT / "workspace-templates"
CURRICULUM = CONTENT / "curricula" / "math.yaml"

# CONTRACTS.md section 3 (harness tools) and section 4 (scripts). Hard-coded on purpose:
# if the contract changes, this test must change with it.
TOOLS = {
    "read_file", "list_dir", "grep", "write_file", "edit_file", "delete_file", "run_script",
    "look_at_image", "notify_user", "schedule_wake", "request_approval",
    "suggest_replies", "show_card", "start_focus", "celebrate",  # CONTRACTS section 9
}
SCRIPTS = {
    "record_event", "bkt_update", "sympy_check", "pdf_extract", "pdf_render",
}

# Other snake_case identifiers skills may legitimately put in backticks: schema field names,
# enum values, script input/output keys (CONTRACTS section 4).
SCRIPT_IO_KEYS = {
    "event_id", "skills_updated",
    "problem_attempt", "graded_work_ingested", "all_correct",
}
# Tool argument / result fields skills may refer to (CONTRACTS section 3).
TOOL_IO_KEYS = {"profile_id"}  # profile_id: show_card mock (section 10.5)
KNOWN_IDENTIFIERS = (
    TOOLS
    | TOOL_IO_KEYS
    | SCRIPTS
    | SCRIPT_IO_KEYS
    | set(LearningEvent.model_fields)
    | set(Routine.model_fields)
    | set(RoutinesFile.model_fields)
    | {e.value for e in EvidenceMode}
    | {e.value for e in JobKind}
    | {e.value for e in ProactivityLevel}
)

REQUIRED_SKILLS = {
    "core": {
        "memory-keeper", "nightly-reflection", "goal-planning", "scaffolded-help", "intake-document",
        "weekly-review", "daily-checkin",
    },
    "student": {"math-tutoring", "graded-work-review", "exam-prep", "spaced-review"},
}

COMMON_TEMPLATE_FILES = {
    "me/profile.md", "me/people.md", "me/preferences.md", "me/now.md", "me/what-works.md",
    "me/journal/.gitkeep", "goals/goals.md", "goals/plans/this-week.md", "goals/plans/term.md",
    "inbox/.gitkeep", "routines.yaml",
}
PROFILE_TEMPLATE_FILES = {
    "student": {
        "learning/math/skills.md", "learning/math/mistakes.md", "learning/math/review-queue.md",
        "learning/evidence/.gitkeep",
    },
}

SKILL_MAX_CHARS = 5_500

BACKTICK = re.compile(r"`([^`\n]+)`")
SNAKE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")
RUN_SCRIPT_NAME = re.compile(r"`run_script`\s+name\s+`([^`]+)`")
SKILL_REF = re.compile(r"\bskill\s+([a-z]+(?:-[a-z]+)+)")
CURRICULUM_DOMAINS = ("algebra.", "functions.", "sets.", "logic.", "inequalities.", "combinatorics.")


# ---------- helpers ----------

def _skill_files() -> list[Path]:
    return sorted(SKILLS_DIR.glob("*/*/SKILL.md"))


def _split_frontmatter(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path}: must start with YAML frontmatter"
    _, fm, body = text.split("---", 2)
    return yaml.safe_load(fm), body


def _all_skill_names() -> set[str]:
    return {p.parent.name for p in _skill_files()}


def _content_docs() -> list[Path]:
    return [AGENTS_MD, *_skill_files()]


def _curriculum() -> list[dict]:
    data = yaml.safe_load(CURRICULUM.read_text(encoding="utf-8"))
    assert data["subject"] == "math"
    return data["skills"]


# ---------- AGENTS.md ----------


def test_agents_md_core_rules():
    text = AGENTS_MD.read_text(encoding="utf-8")
    assert "111" in text
    assert "[suy luận]" in text


# ---------- skills ----------

def test_required_skills_exist():
    for group, names in REQUIRED_SKILLS.items():
        present = {p.parent.name for p in (SKILLS_DIR / group).glob("*/SKILL.md")}
        assert names <= present, f"missing skills in {group}: {names - present}"
    for p in _skill_files():
        assert p.parent.parent.name in REQUIRED_SKILLS, f"{p}: unknown group"


@pytest.mark.parametrize("path", _skill_files(), ids=lambda p: p.parent.name)
def test_skill_frontmatter(path: Path):
    fm, body = _split_frontmatter(path)
    assert set(fm) >= {"name", "description", "profiles", "version"}, f"{path}: frontmatter keys {set(fm)}"
    assert fm["name"] == path.parent.name
    assert isinstance(fm["description"], str) and fm["description"].strip()
    assert "\n" not in fm["description"].strip()
    assert isinstance(fm["profiles"], list) and fm["profiles"]
    assert set(fm["profiles"]) <= {"student", "teacher"}
    assert isinstance(fm["version"], int)
    group = path.parent.parent.name
    if group == "student":
        assert fm["profiles"] == [group], f"{path}: skills in {group}/ must have profiles [{group}]"
    assert body.strip()


@pytest.mark.parametrize("path", _skill_files(), ids=lambda p: p.parent.name)
def test_skill_length(path: Path):
    n = len(path.read_text(encoding="utf-8"))
    assert n <= SKILL_MAX_CHARS, f"{path} has {n} chars (max {SKILL_MAX_CHARS})"


# ---------- tool / script / skill references ----------

@pytest.mark.parametrize("path", _content_docs(), ids=lambda p: p.parent.name if p.name == "SKILL.md" else p.name)
def test_backticked_identifiers_exist(path: Path):
    text = path.read_text(encoding="utf-8")
    unknown = sorted({t for t in BACKTICK.findall(text) if SNAKE.match(t) and t not in KNOWN_IDENTIFIERS})
    assert not unknown, f"{path}: unknown tool/script/identifier names in backticks: {unknown}"


@pytest.mark.parametrize("path", _content_docs(), ids=lambda p: p.parent.name if p.name == "SKILL.md" else p.name)
def test_run_script_names_are_scripts(path: Path):
    text = path.read_text(encoding="utf-8")
    bad = sorted({n for n in RUN_SCRIPT_NAME.findall(text) if n not in SCRIPTS})
    assert not bad, f"{path}: run_script with unknown script names {bad}"


@pytest.mark.parametrize("path", _content_docs(), ids=lambda p: p.parent.name if p.name == "SKILL.md" else p.name)
def test_skill_references_exist(path: Path):
    text = path.read_text(encoding="utf-8")
    bad = sorted(set(SKILL_REF.findall(text)) - _all_skill_names())
    assert not bad, f"{path}: references to unknown skills {bad}"


def test_curriculum_ids_in_skills_exist():
    ids = {s["id"] for s in _curriculum()}
    for path in _content_docs():
        for tok in BACKTICK.findall(path.read_text(encoding="utf-8")):
            if tok.startswith(CURRICULUM_DOMAINS) and re.fullmatch(r"[a-z0-9_.]+", tok):
                assert tok in ids, f"{path}: unknown curriculum id {tok}"


# ---------- specific skill rules ----------

def test_math_tutoring_uses_sympy_check():
    text = (SKILLS_DIR / "student" / "math-tutoring" / "SKILL.md").read_text(encoding="utf-8")
    assert "`sympy_check`" in text and "`record_event`" in text


def test_graded_work_review_flow():
    text = (SKILLS_DIR / "student" / "graded-work-review" / "SKILL.md").read_text(encoding="utf-8")
    for needle in ("`look_at_image`", "`record_event`", '"classroom_graded"', "`bkt_update`"):
        assert needle in text, f"graded-work-review must mention {needle}"
    assert text.index("`record_event`") < text.index("`bkt_update`")


# ---------- workspace templates ----------

@pytest.mark.parametrize("profile", ["student"])
def test_template_files(profile: str):
    root = TEMPLATES / profile
    present = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    expected = COMMON_TEMPLATE_FILES | PROFILE_TEMPLATE_FILES[profile]
    assert expected <= present, f"missing in {profile}: {expected - present}"
    for rel in present:
        if not rel.endswith(".gitkeep"):
            assert is_agent_writable(rel), f"{profile}/{rel} is not agent-writable"


@pytest.mark.parametrize("profile", ["student"])
def test_template_profile_line(profile: str):
    text = (TEMPLATES / profile / "me" / "profile.md").read_text(encoding="utf-8")
    assert "- Vai trò: học sinh" in text


@pytest.mark.parametrize("profile", ["student"])
def test_routines_validate(profile: str):
    rf = RoutinesFile.parse_yaml((TEMPLATES / profile / "routines.yaml").read_text(encoding="utf-8"))
    by_id = {r.id: r for r in rf.routines}
    assert len(by_id) == len(rf.routines), "duplicate routine ids"
    assert rf.timezone == "Asia/Ho_Chi_Minh"
    for r in rf.routines:
        assert len(r.cron.split()) == 5, f"{r.id}: cron must have 5 fields"
        JobKind(r.job_kind)
        if r.job_kind == JobKind.ROUTINE.value:
            assert r.prompt, f"{r.id}: generic routines need a prompt naming the skill"
        if r.prompt:
            refs = set(SKILL_REF.findall(r.prompt))
            allowed = REQUIRED_SKILLS["core"] | REQUIRED_SKILLS[profile]
            assert refs <= allowed, f"{r.id}: prompt references skills outside the profile: {refs - allowed}"

    nightly = by_id["nightly_reflection"]
    assert nightly.cron == "30 23 * * *" and not nightly.user_editable
    assert by_id["weekly_review"].cron.split()[4] == "0"  # Sunday
    assert set(by_id) == {"nightly_reflection", "evening_review", "weekly_review", "morning_checkin",
                          "evening_wrapup", "review_due"}
    assert by_id["evening_review"].cron == "30 19 * * *" and by_id["evening_review"].user_editable


# ---------- curriculum ----------

def test_curriculum_shape():
    skills = _curriculum()
    assert 60 <= len(skills) <= 90  # grade 8-12 (practice bank, CONTRACTS section 10.1)
    ids = [s["id"] for s in skills]
    assert len(ids) == len(set(ids)), "duplicate curriculum ids"
    for s in skills:
        assert re.fullmatch(r"[a-z0-9_]+(\.[a-z0-9_]+)+", s["id"]), f"bad id {s['id']}"
        assert s["title"].strip()
        assert s["grade"] in (8, 9, 10, 11, 12)
        for pre in s["prerequisites"]:
            assert pre in ids, f"{s['id']}: unknown prerequisite {pre}"
    assert sum(s["grade"] == 10 for s in skills) >= 18


def test_curriculum_acyclic():
    graph = {s["id"]: list(s["prerequisites"]) for s in _curriculum()}
    state: dict[str, int] = {}  # 1 = visiting, 2 = done

    def visit(node: str, path: list[str]) -> None:
        if state.get(node) == 2:
            return
        assert state.get(node) != 1, f"cycle: {' -> '.join(path + [node])}"
        state[node] = 1
        for pre in graph[node]:
            visit(pre, path + [node])
        state[node] = 2

    for node in graph:
        visit(node, [])
