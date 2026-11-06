"""Question bank, exam profiles and curricula, read from `MENTOR_CONTENT_DIR` (CONTRACTS 10.1).

The bank is platform content in agent-mentor's format (`bank/<subject>/<topic>.json`, `{questions: [...]}`) plus
`skill_ids`. Only `quality_status == "APPROVED"` items with a usable key are served; a question without `skill_ids`
falls back to its topic id as the one skill, so a bank imported before the curricula caught up still works.
The raw question document is kept: sessions store a copy of what they serve, so a later bank change never alters a
session in progress or its review.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from mentor_gateway.practice.scoring import parse_short_answer
from mentor_gateway.practice.topics import Topics

log = logging.getLogger(__name__)

SINGLE, TRUE_FALSE, SHORT = "SINGLE_CHOICE", "TRUE_FALSE_GROUP", "SHORT_ANSWER"
_LEVEL_MIDPOINT = {1: 0.18, 2: 0.40, 3: 0.65, 4: 0.86}
_QUALITY_WEIGHT = {"CALIBRATED": 1.0, "PROVISIONAL": 0.9, "UNVERIFIED": 0.8}


def location(estimate: float) -> float:
    """Rasch-style location on the logit scale: estimate 0.5 -> 0, range [-2, 2]."""
    return 4.0 * (min(1.0, max(0.0, estimate)) - 0.5)


def location_for_level(level: int) -> float:
    return location(_LEVEL_MIDPOINT.get(level, 0.5))


# one level on the location scale = mean distance between adjacent level midpoints (about 0.91 logits)
LOCATION_PER_LEVEL = (location_for_level(4) - location_for_level(1)) / 3.0


def level_for_location(b: float) -> int:
    e = b / 4.0 + 0.5
    return min(_LEVEL_MIDPOINT, key=lambda lv: abs(_LEVEL_MIDPOINT[lv] - e))


@dataclass(frozen=True)
class Item:
    """Engine-facing view of a question (selection and scoring need nothing else)."""

    id: str
    revision: int
    subject: str
    topic: str
    type: str
    level: int
    estimate: float
    seconds: int
    quality: float
    skill_ids: tuple[str, ...]
    doc: dict[str, Any] = field(compare=False, repr=False)

    @property
    def location(self) -> float:
        return location(self.estimate)


def usable_key(doc: dict[str, Any]) -> bool:
    """One key that matches the item's format (port of `QuestionDoc.hasUsableKey`)."""
    t = doc.get("type")
    options, statements = doc.get("options") or [], doc.get("statements") or []
    key = (doc.get("answer_key") or {}).get("correct_option_id")
    if t == SINGLE:
        return bool(key) and len(options) >= 2 and not statements and any(o.get("id") == key for o in options)
    if t == TRUE_FALSE:
        return len(statements) == 4 and not options and all(isinstance(s.get("truth"), bool) for s in statements)
    if t == SHORT:
        sa = doc.get("short_answer") or {}
        return parse_short_answer(sa.get("answer"), sa.get("unit")) is not None and not options and not statements
    return False


def to_item(doc: dict[str, Any]) -> Item | None:
    if doc.get("quality_status") != "APPROVED" or not usable_key(doc):
        return None
    topics = doc.get("topic_ids") or []
    if not topics:
        return None
    diff = doc.get("difficulty") or {}
    level = int(diff.get("level") or 2)
    estimate = diff.get("estimate")
    skills = tuple(str(s) for s in (doc.get("skill_ids") or [])) or (str(topics[0]),)
    return Item(
        id=str(doc["id"]), revision=int(doc.get("revision") or 1), subject=str(doc["subject_id"]), topic=str(topics[0]),
        type=str(doc["type"]), level=level,
        estimate=float(estimate if estimate is not None else _LEVEL_MIDPOINT.get(level, 0.5)),
        seconds=int(doc.get("estimated_seconds") or 60), quality=_QUALITY_WEIGHT.get(str(diff.get("confidence")), 0.8),
        skill_ids=skills, doc=doc,
    )


@dataclass(frozen=True)
class Part:
    part: int
    label: str
    type: str
    item_count: int
    points_per_item: float
    topic_matrix: dict[str, int]
    level_mix: list[float] | None


@dataclass(frozen=True)
class Profile:
    id: str
    subject: str
    type: str  # MCQ_PRACTICE_MOCK | OFFICIAL_FORMAT_MOCK
    label: str
    question_types: tuple[str, ...]
    time_limit_sec: int
    item_count: int
    topic_matrix: dict[str, int]
    level_mix: list[float]
    scoring: str
    max_score: float
    disclaimer: str
    parts: tuple[Part, ...]


@dataclass(frozen=True)
class CurriculumSkill:
    id: str
    title: str
    topic: str | None
    grade: int | None = None


def _grade(raw: Any) -> int | None:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


class Bank:
    """All approved items by subject, the profiles, and the skill -> (title, topic) lookup."""

    def __init__(self, content_dir: Path) -> None:
        self.content_dir = content_dir
        self.topics = Topics(content_dir)
        self.items: dict[str, Item] = {}
        self.by_subject: dict[str, list[Item]] = {}
        self.profiles: dict[str, Profile] = {}
        self.skills: dict[str, dict[str, CurriculumSkill]] = {}
        self._load_items()
        self._load_profiles()
        self._load_curricula()

    def _load_items(self) -> None:
        for path in sorted((self.content_dir / "bank").glob("*/*.json")):
            if path.name == "topics.json":
                continue
            try:
                docs = json.loads(path.read_text(encoding="utf-8")).get("questions") or []
            except (OSError, ValueError):
                log.warning("practice: unreadable bank file %s", path.name)
                continue
            for doc in docs:
                item = to_item(doc) if isinstance(doc, dict) else None
                if item is not None:
                    self.items[item.id] = item
        for item in sorted(self.items.values(), key=lambda i: i.id):
            self.by_subject.setdefault(item.subject, []).append(item)

    def _load_profiles(self) -> None:
        path = self.content_dir / "exam-profiles.json"
        if not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8")).get("profiles") or []
        except (OSError, ValueError):
            return
        for p in raw:
            parts = tuple(
                Part(int(x["part"]), str(x.get("label") or ""), str(x["type"]), int(x["item_count"]),
                     float(x.get("points_per_item") or 1.0),
                     {k: int(v) for k, v in (x.get("topic_matrix") or {}).items()}, x.get("level_mix"))
                for x in (p.get("parts") or [])
            )
            self.profiles[p["id"]] = Profile(
                id=p["id"], subject=p["subject_id"], type=p.get("type", "MCQ_PRACTICE_MOCK"),
                label=p.get("label", p["id"]), question_types=tuple(p.get("question_types") or [SINGLE]),
                time_limit_sec=int(p["time_limit_sec"]), item_count=int(p["item_count"]),
                topic_matrix={k: int(v) for k, v in (p.get("topic_matrix") or {}).items()},
                level_mix=list(p.get("level_mix") or [0.4, 0.3, 0.2, 0.1]), scoring=p.get("scoring_policy_version", "mcq-v1"),
                max_score=float(p.get("max_score") or 10.0), disclaimer=p.get("disclaimer", ""), parts=parts,
            )

    def _load_curricula(self) -> None:
        for path in sorted((self.content_dir / "curricula").glob("*.yaml")):
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError):
                continue
            subject = str(data.get("subject") or path.stem)
            self.skills[subject] = {
                str(s["id"]): CurriculumSkill(str(s["id"]), str(s.get("title") or s["id"]), s.get("topic"), _grade(s.get("grade")))
                for s in data.get("skills") or [] if isinstance(s, dict) and s.get("id")
            }

    # ---- lookups -------------------------------------------------------------------------------

    def subjects(self) -> list[str]:
        known = ("math", "physics", "english")
        return [s for s in known if s in self.by_subject] + sorted(s for s in self.by_subject if s not in known)

    def topic_ids(self, subject: str) -> list[str]:
        """Topics of the subject that have at least one served item, most important first."""
        counts: dict[str, int] = {}
        for it in self.by_subject.get(subject, []):
            counts[it.topic] = counts.get(it.topic, 0) + 1
        return sorted(counts, key=lambda t: (-self.topics.get(t).weight, t))

    def topic_grade(self, subject: str, topic: str) -> int | None:
        """Grade a topic starts at: the minimum `grade` of the curriculum skills tagged with it (the lowest grade that
        teaches any of it; later grades extend it). None when no skill of the topic states a grade."""
        grades = [cs.grade for cs in self.skills.get(subject, {}).values() if cs.topic == topic and cs.grade is not None]
        return min(grades) if grades else None

    def item_count(self, subject: str, topic: str) -> int:
        return sum(1 for it in self.by_subject.get(subject, []) if it.topic == topic)

    def skill_topic(self, subject: str, skill_id: str) -> str | None:
        """Curriculum `topic:` if C gave one, else the topic most of the skill's questions belong to."""
        cs = self.skills.get(subject, {}).get(skill_id)
        if cs is not None and cs.topic:
            return cs.topic
        tally: dict[str, int] = {}
        for it in self.by_subject.get(subject, []):
            if skill_id in it.skill_ids:
                tally[it.topic] = tally.get(it.topic, 0) + 1
        if tally:
            return min(tally, key=lambda t: (-tally[t], t))
        return skill_id if skill_id in self.topics.by_id else None

    def skill_title(self, subject: str, skill_id: str) -> str:
        cs = self.skills.get(subject, {}).get(skill_id)
        if cs:
            return cs.title
        return self.topics.get(skill_id).title if skill_id in self.topics.by_id else skill_id

    def curriculum_path(self, subject: str) -> Path:
        return self.content_dir / "curricula" / f"{subject}.yaml"
