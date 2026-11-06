"""Mastery for practice: one source of truth, `mentor_scripts.bkt_update` (CONTRACTS 10.2, 10.4).

The gateway does not carry a second BKT. `mentor-scripts` is a gateway dependency (it is in the uv workspace, so the
prod image built by `infra/gateway.Dockerfile` already has it) and its own functions run over the learner's
`events.jsonl` text from the mirror, staged in a temp directory because those functions take a workspace root.
`bkt_update` itself writes `skills.md` and `review-queue.md` there; the gateway commits those exact bytes, so the files
equal what the sandbox's `run_script bkt_update` would produce for the same events.

Per-skill BKT feeds the engine in two ways: item targeting and the learner-facing labels use a *topic* mastery, the
mean of the topic's skills weighted by independent evidence (no evidence = "Chưa có dữ liệu").
"""

import math
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from mentor_scripts.bkt_update import (
    SkillState,
    bkt_update,
    compute_states,
    load_curriculum,
    load_events,
)

from mentor_gateway.practice.bank import Bank

LABEL_UNKNOWN = "Chưa có dữ liệu"
LABEL_NEEDS_DATA = "Cần thêm dữ liệu"
LABEL_WEAK = "Cần củng cố"
LABEL_DEVELOPING = "Đang tiến bộ"
LABEL_STRONG = "Vững"

WEAK_BELOW = 0.5
STRONG_FROM = 0.8
MIN_EVIDENCE_FOR_LABEL = 2
STRONG_MIN_EVIDENCE = 4


@dataclass(frozen=True)
class TopicMastery:
    topic: str
    mastery: float | None  # None = no independent evidence yet
    evidence: int  # independent, hint-free attempts across the topic's skills

    @property
    def has_evidence(self) -> bool:
        return self.evidence > 0

    @property
    def estimate(self) -> float:
        return 0.5 if self.mastery is None else self.mastery

    @property
    def theta(self) -> float:
        """Ability on the logit scale of item locations (the engine's difficulty axis)."""
        p = min(1 - 1e-6, max(1e-6, self.estimate))
        return max(-2.0, min(2.0, math.log(p / (1 - p))))

    @property
    def uncertainty(self) -> float:
        """0..1, shrinking with evidence (stands in for the Kotlin model's sd / prior sd)."""
        return 1.0 / (1.0 + 0.5 * self.evidence)

    @property
    def status(self) -> str:
        if not self.has_evidence:
            return "UNKNOWN"
        if self.evidence < MIN_EVIDENCE_FOR_LABEL:
            return "NEEDS_DATA"
        if self.estimate < WEAK_BELOW:
            return "WEAK"
        if self.estimate >= STRONG_FROM and self.evidence >= STRONG_MIN_EVIDENCE:
            return "STRONG"
        return "DEVELOPING"

    @property
    def label(self) -> str:
        return _LABELS[self.status]

    @property
    def confidence(self) -> str:
        return confidence_for(self.evidence)


_LABELS = {"UNKNOWN": LABEL_UNKNOWN, "NEEDS_DATA": LABEL_NEEDS_DATA, "WEAK": LABEL_WEAK,
           "DEVELOPING": LABEL_DEVELOPING, "STRONG": LABEL_STRONG}


def confidence_for(evidence: int) -> str:
    return "high" if evidence >= 6 else "medium" if evidence >= 3 else "low"


def skill_label(st: SkillState | None) -> str:
    if st is None or st.mastery_attempts == 0:
        return LABEL_UNKNOWN
    return TopicMastery("", st.mastery, st.mastery_attempts).label


def stage(root: Path, events_text: str, subject: str, curriculum_text: str | None) -> None:
    """Lay out what bkt_update reads: events.jsonl and .mentor/curricula/<subject>.yaml."""
    (root / "events.jsonl").write_text(events_text, encoding="utf-8")
    if curriculum_text:
        cur = root / ".mentor" / "curricula"
        cur.mkdir(parents=True, exist_ok=True)
        (cur / f"{subject}.yaml").write_text(curriculum_text, encoding="utf-8")


def skill_states(events_text: str, subject: str, curriculum_text: str | None) -> dict[str, SkillState]:
    """BKT state per skill from the full event log (same functions `bkt_update` runs)."""
    with tempfile.TemporaryDirectory(prefix="mentor-bkt-") as tmp:
        root = Path(tmp)
        stage(root, events_text, subject, curriculum_text)
        return compute_states(load_events(root, subject), load_curriculum(root, subject))


def recompute(events_text: str, subject: str, curriculum_text: str | None,
              today: date) -> tuple[dict[str, SkillState], str, str]:
    """(states, skills.md, review-queue.md) exactly as `bkt_update` writes them for these events."""
    with tempfile.TemporaryDirectory(prefix="mentor-bkt-") as tmp:
        root = Path(tmp)
        stage(root, events_text, subject, curriculum_text)
        bkt_update({"subject": subject, "today": today.isoformat()}, root)
        out = root / "learning" / subject
        states = compute_states(load_events(root, subject), load_curriculum(root, subject))
        return states, (out / "skills.md").read_text(encoding="utf-8"), (out / "review-queue.md").read_text(encoding="utf-8")


def topic_mastery(bank: Bank, subject: str, states: dict[str, SkillState]) -> dict[str, TopicMastery]:
    """Evidence-weighted mean of each topic's skills (CONTRACTS 10.4). Every topic of the subject gets an entry."""
    acc: dict[str, list[tuple[float, int]]] = {}
    for sid, st in states.items():
        topic = bank.skill_topic(subject, sid)
        if topic is not None and st.mastery_attempts > 0:
            acc.setdefault(topic, []).append((st.mastery, st.mastery_attempts))
    out: dict[str, TopicMastery] = {}
    for topic in set(bank.topic_ids(subject)) | set(acc):
        rows = acc.get(topic, [])
        n = sum(w for _, w in rows)
        out[topic] = TopicMastery(topic, sum(m * w for m, w in rows) / n if n else None, n)
    return out
