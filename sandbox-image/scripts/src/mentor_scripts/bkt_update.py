"""bkt_update: Bayesian Knowledge Tracing over events.jsonl (plan 7.3).

Input: {subject: "math", today?: "YYYY-MM-DD"}. Output: {skills_updated, due_count}.
Writes learning/<subject>/skills.md and learning/<subject>/review-queue.md, recomputed from
the full event log every run, so the result is idempotent and deterministic.

Mastery rules:
- Only `independent` and `classroom_graded` events update mastery. `guided` events, and
  `independent` events that report hint_count > 0, are counted as process only.
- Standard BKT per skill: posterior given the observation, then the learning transition.
  Defaults p_init 0.2, p_learn 0.15, p_guess 0.2, p_slip 0.1; a curriculum skill may override
  any of them with an optional `bkt: {p_init, p_learn, p_guess, p_slip}` mapping.

Review ladder (days after the last correct mastery attempt), by mastery:
  < 0.4 → 1, < 0.6 → 3, < 0.8 → 7, < 0.95 → 14, else 30.
A skill whose latest mastery attempt was wrong is due the next day; a guided-only skill is due
the day after its last practice, to get one independent check.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from mentor_schemas import EvidenceMode, LearningEvent, WorkspacePaths

from mentor_scripts.common import (
    VN_TZ,
    ScriptError,
    atomic_write_text,
    local_date,
    parse_today,
    read_jsonl,
    run_cli,
    validate_or_none,
)

DEFAULT_PARAMS: dict[str, float] = {"p_init": 0.2, "p_learn": 0.15, "p_guess": 0.2, "p_slip": 0.1}
LOW_MASTERY = 0.6
REVIEW_LADDER: tuple[tuple[float, int], ...] = ((0.4, 1), (0.6, 3), (0.8, 7), (0.95, 14))
MAX_INTERVAL = 30

_SUBJECT = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}$")


@dataclass
class CurriculumSkill:
    id: str
    title: str = ""
    prerequisites: list[str] = field(default_factory=list)
    params: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_PARAMS))


@dataclass
class SkillState:
    skill_id: str
    mastery: float
    mastery_attempts: int = 0
    mastery_correct: int = 0
    guided_attempts: int = 0
    last_event: date | None = None
    last_mastery_event: date | None = None
    last_mastery_correct: bool | None = None
    last_success: date | None = None


def bkt_step(p: float, correct: bool, params: dict[str, float]) -> float:
    """One BKT observation update followed by the learning transition."""
    guess, slip, learn = params["p_guess"], params["p_slip"], params["p_learn"]
    if correct:
        num, den = p * (1 - slip), p * (1 - slip) + (1 - p) * guess
    else:
        num, den = p * slip, p * slip + (1 - p) * (1 - guess)
    posterior = num / den if den > 0 else p
    return posterior + (1 - posterior) * learn


def counts_toward_mastery(e: LearningEvent) -> bool:
    if e.mode == EvidenceMode.CLASSROOM_GRADED:
        return True
    return e.mode == EvidenceMode.INDEPENDENT and e.hint_count == 0


def _params(raw: Any) -> dict[str, float]:
    params = dict(DEFAULT_PARAMS)
    if isinstance(raw, dict):
        for k in DEFAULT_PARAMS:
            v = raw.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 1:
                params[k] = float(v)
    return params


def load_curriculum(root: Path, subject: str) -> dict[str, CurriculumSkill]:
    """Skills from .mentor/curricula/<subject>.yaml; empty if the file is absent."""
    path = root / WorkspacePaths.CURRICULA_DIR / f"{subject}.yaml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: dict[str, CurriculumSkill] = {}
    for item in data.get("skills") or []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        sid = str(item["id"])
        prereqs = item.get("prerequisites") or []
        out[sid] = CurriculumSkill(
            id=sid,
            title=str(item.get("title") or ""),
            prerequisites=[str(p) for p in prereqs] if isinstance(prereqs, list) else [],
            params=_params(item.get("bkt")),
        )
    return out


def load_events(root: Path, subject: str) -> list[LearningEvent]:
    events: list[LearningEvent] = []
    for obj in read_jsonl(root / WorkspacePaths.EVENTS):
        e = validate_or_none(LearningEvent, obj)  # one bad line must not block the learner model
        if e is not None and e.subject == subject:
            events.append(e)

    def key(e: LearningEvent) -> datetime:
        return e.ts if e.ts.tzinfo else e.ts.replace(tzinfo=VN_TZ)

    return sorted(events, key=key)  # stable: equal timestamps keep append order


def compute_states(events: list[LearningEvent], curriculum: dict[str, CurriculumSkill]) -> dict[str, SkillState]:
    states: dict[str, SkillState] = {}
    for e in events:
        day = local_date(e.ts)
        for sid in dict.fromkeys(e.skill_ids):  # de-duplicate, keep order
            params = curriculum[sid].params if sid in curriculum else DEFAULT_PARAMS
            st = states.setdefault(sid, SkillState(skill_id=sid, mastery=params["p_init"]))
            st.last_event = max(st.last_event or day, day)
            if not counts_toward_mastery(e):
                st.guided_attempts += 1
                continue
            st.mastery = bkt_step(st.mastery, e.correct, params)
            st.mastery_attempts += 1
            st.last_mastery_event = day
            st.last_mastery_correct = e.correct
            if e.correct:
                st.mastery_correct += 1
                st.last_success = day
    return states


def review_interval(mastery: float) -> int:
    for bound, days in REVIEW_LADDER:
        if mastery < bound:
            return days
    return MAX_INTERVAL


def next_due(st: SkillState) -> date:
    if st.mastery_attempts == 0:
        assert st.last_event is not None
        return st.last_event + timedelta(days=1)
    if not st.last_mastery_correct or st.last_success is None:
        assert st.last_mastery_event is not None
        return st.last_mastery_event + timedelta(days=1)
    return st.last_success + timedelta(days=review_interval(st.mastery))


def prerequisite_notes(st: SkillState, states: dict[str, SkillState], curriculum: dict[str, CurriculumSkill]) -> list[str]:
    skill = curriculum.get(st.skill_id)
    if skill is None:
        return []
    notes = []
    for pid in sorted(skill.prerequisites):
        pre = states.get(pid)
        if pre is not None and pre.mastery_attempts > 0:
            if pre.mastery < LOW_MASTERY:
                notes.append(f"nền tảng yếu: {pid} ({pre.mastery:.2f})")
        elif st.mastery < LOW_MASTERY:
            notes.append(f"chưa kiểm tra nền tảng: {pid}")
    return notes


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip() or "—"


def _evidence(st: SkillState) -> str:
    parts = []
    if st.mastery_attempts:
        parts.append(f"{st.mastery_correct} đúng trên {st.mastery_attempts} bài độc lập")
    else:
        parts.append("chưa có bài độc lập")
    if st.guided_attempts:
        parts.append(f"{st.guided_attempts} bài có gợi ý")
    return "; ".join(parts)


def render_skills_md(subject: str, today: date, states: dict[str, SkillState], curriculum: dict[str, CurriculumSkill]) -> str:
    lines = [
        f"# Mức độ thành thạo — {subject}",
        "",
        (
            f"Tự động sinh bởi `bkt_update` ngày {today.isoformat()}; không sửa tay. "
            "Chỉ bài làm độc lập và bài kiểm tra đã chấm trên lớp mới được tính vào mastery."
        ),
        "",
        "| skill_id | Tên | Mastery | Bằng chứng | Lần cuối |",
        "|---|---|---|---|---|",
    ]
    for sid in sorted(states):
        st = states[sid]
        title = curriculum[sid].title if sid in curriculum else ""
        last = st.last_event.isoformat() if st.last_event else ""
        lines.append(f"| {_cell(sid)} | {_cell(title)} | {st.mastery:.2f} | {_cell(_evidence(st))} | {_cell(last)} |")
    return "\n".join(lines) + "\n"


def render_review_md(
    subject: str, today: date, states: dict[str, SkillState], curriculum: dict[str, CurriculumSkill]
) -> tuple[str, int]:
    rows = []
    for sid, st in states.items():
        notes = prerequisite_notes(st, states, curriculum)
        if st.mastery_attempts == 0:
            notes.insert(0, "cần làm một bài độc lập")
        elif not st.last_mastery_correct:
            notes.insert(0, "lần gần nhất làm sai")
        rows.append((next_due(st), st.mastery, sid, notes))
    rows.sort(key=lambda r: (r[0], r[1], r[2]))

    def table(items: list[tuple[date, float, str, list[str]]]) -> list[str]:
        if not items:
            return ["Không có.", ""]
        out = ["| skill_id | Tên | Mastery | Đến hạn | Ghi chú |", "|---|---|---|---|---|"]
        for due, mastery, sid, notes in items:
            title = curriculum[sid].title if sid in curriculum else ""
            out.append(f"| {_cell(sid)} | {_cell(title)} | {mastery:.2f} | {due.isoformat()} | {_cell('; '.join(notes))} |")
        return out + [""]

    due_rows = [r for r in rows if r[0] <= today]
    later_rows = [r for r in rows if r[0] > today]
    lines = [
        f"# Lịch ôn tập — {subject}",
        "",
        (
            f"Tự động sinh bởi `bkt_update` ngày {today.isoformat()}; không sửa tay. "
            "Khoảng ôn theo mastery: 1, 3, 7, 14, 30 ngày sau lần làm đúng gần nhất."
        ),
        "",
        "## Đến hạn hôm nay hoặc quá hạn",
        "",
        *table(due_rows),
        "## Sắp tới",
        "",
        *table(later_rows),
    ]
    return "\n".join(lines).rstrip("\n") + "\n", len(due_rows)


def bkt_update(payload: dict[str, Any], root: Path) -> dict[str, Any]:
    subject = payload.get("subject")
    if not isinstance(subject, str) or not _SUBJECT.match(subject):
        raise ScriptError("subject must be a lowercase slug such as 'math'")
    today = parse_today(payload)
    curriculum = load_curriculum(root, subject)
    states = compute_states(load_events(root, subject), curriculum)

    out_dir = root / WorkspacePaths.LEARNING_DIR / subject
    atomic_write_text(out_dir / "skills.md", render_skills_md(subject, today, states, curriculum))
    review, due_count = render_review_md(subject, today, states, curriculum)
    atomic_write_text(out_dir / "review-queue.md", review)
    return {"skills_updated": len(states), "due_count": due_count}


def main() -> None:
    run_cli(bkt_update)


if __name__ == "__main__":
    main()
