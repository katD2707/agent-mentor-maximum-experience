"""Item sources for Luyện tập beyond the static bank: the quiz items of the courses a student is enrolled in (P5-A).

A course `QuizItem` becomes an engine `Item` whose `doc` is in the bank's shape (`type`, `options`, `statements` with
`truth`, `answer_key`, `explanation`, `option_feedback`, `hint`) plus what only courses have: a `short_answer` with
`accepted`/`tolerance`, a `tap` target, asset references with ready URLs, and a `course` block that says where the item
came from. Items are read from the version the student's enrollment is **pinned** to, never from a later version.

Ids: the engine id of a course item is `"<course_id>:<item_id>"` (item ids are only unique inside a course; bank ids never
contain a colon). Skills: the item's own `skill_ids`, or one lesson-level skill `"<course_id>.<lesson_id>"` when the
course author gave none (so every answer still counts as evidence). Subject (the key of `learning/<subject>/`): the
bank/curriculum subject when the item's skills belong to one, else a slug of the course's subject text.
Topic (allocation and display): the lesson, `"<course_id>/<lesson_id>"`, titled with the lesson.
"""

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from mentor_schemas.course import AssetRef, CoursePack, QuizItem

from mentor_gateway.content.store import ContentError
from mentor_gateway.practice.bank import _LEVEL_MIDPOINT, Bank, Item

log = logging.getLogger(__name__)

SEPARATOR = ":"
_BASE_SECONDS = {"SINGLE_CHOICE": 40, "PICTURE_CHOICE": 25, "TAP_COUNT": 25, "TRUE_FALSE_GROUP": 120, "SHORT_ANSWER": 75}
_COURSE_QUALITY = 0.9


def slug(text: str) -> str:
    """`Vật lí` -> `vat-li` (ASCII, safe as a workspace directory name)."""
    t = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:32] or "course"


def subject_key(subject_label: str, skill_ids: list[str], bank: Bank) -> str:
    for sid in skill_ids:
        for subject, skills in bank.skills.items():
            if sid in skills:
                return subject
    return slug(subject_label)


def doc_id(course_id: str, item_id: str) -> str:
    return f"{course_id}{SEPARATOR}{item_id}"


def estimate_seconds(qtype: str, difficulty: int) -> int:
    return _BASE_SECONDS.get(qtype, 60) + 12 * (difficulty - 1)


def _ref(ref: AssetRef | None, course_id: str, version: int) -> dict | None:
    if ref is None:
        return None
    return {"path": ref.path, "mime": ref.mime, "sha256": ref.sha256,
            "url": f"/api/courses/{course_id}/versions/{version}/assets/{ref.path}"}


def quiz_to_item(q: QuizItem, *, course_id: str, version: int, course_title: str, subject_label: str, lesson_id: str,
                 lesson_title: str, lesson_index: int, bank: Bank) -> Item:
    """Map one course quiz item to an engine item (all five types)."""
    skills = tuple(q.skill_ids) or (f"{course_id}.{lesson_id}",)
    subject = subject_key(subject_label, list(q.skill_ids), bank)
    key = q.answer_key
    doc: dict[str, Any] = {
        "id": doc_id(course_id, q.id), "revision": version, "subject_id": subject, "type": q.type, "stem": q.stem,
        "stem_audio": _ref(q.stem_audio, course_id, version), "stem_image": _ref(q.stem_image, course_id, version),
        "options": [{"id": o.id, "text": o.text or "", "image": _ref(o.image, course_id, version),
                     "audio": _ref(o.audio, course_id, version)} for o in q.options],
        "statements": [{"id": s.id, "text": s.text, "truth": bool(key["statements"][s.id])} for s in q.statements]
        if q.type == "TRUE_FALSE_GROUP" else [],
        "answer_key": dict(key), "hint": q.hint, "explanation": q.explanation, "option_feedback": dict(q.option_feedback),
        "difficulty": {"level": q.difficulty, "estimate": _LEVEL_MIDPOINT[q.difficulty], "confidence": "PROVISIONAL"},
        "skill_ids": list(skills), "assets": [], "quality_status": "APPROVED",
        "course": {"course_id": course_id, "version": version, "course_title": course_title, "lesson_id": lesson_id,
                   "lesson_title": lesson_title, "lesson_index": lesson_index, "item_id": q.id},
    }
    if q.type == "SHORT_ANSWER":
        doc["short_answer"] = {"accepted": [str(a) for a in key["accepted"]], "tolerance": key.get("tolerance")}
    if q.type == "TAP_COUNT" and q.tap is not None:
        doc["tap"] = {"image": _ref(q.tap.image, course_id, version), "total": q.tap.total}
    seconds = estimate_seconds(q.type, q.difficulty)
    return Item(
        id=doc["id"], revision=version, subject=subject, topic=f"{course_id}/{lesson_id}", type=q.type, level=q.difficulty,
        estimate=_LEVEL_MIDPOINT[q.difficulty], seconds=seconds, quality=_COURSE_QUALITY, skill_ids=skills, doc=doc)


@dataclass
class LessonRef:
    id: str
    title: str
    index: int  # 1-based position in the course
    studied: bool = False
    current: bool = False  # the lesson the student is on, or the one before it


@dataclass
class CourseBundle:
    """One enrolled course at its pinned version: its lessons, which of them were studied, and every quiz item."""

    course_id: str
    title: str
    subject: str  # the course's own subject text
    cover_sha256: str | None
    age_band: str
    version: int
    lessons: list[LessonRef] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)
    last_seen: str | None = None  # enrollment updated_at

    def studied_lesson_ids(self) -> set[str]:
        return {ls.id for ls in self.lessons if ls.studied}

    def studied_items(self) -> list[Item]:
        ok = self.studied_lesson_ids()
        return [i for i in self.items if i.doc["course"]["lesson_id"] in ok]

    def lessons_range(self) -> tuple[int, int] | None:
        done = [ls.index for ls in self.lessons if ls.studied]
        return (min(done), max(done)) if done else None


def _studied(pack: CoursePack, enrollment: dict) -> tuple[list[LessonRef], int]:
    """Lessons up to the furthest one the student touched (a block done, the last lesson, a quiz item answered)."""
    done = set(enrollment.get("completed_block_ids") or [])
    answered = set((enrollment.get("quiz") or {}).keys())
    last = enrollment.get("last_lesson_id")
    lessons: list[LessonRef] = []
    furthest = -1
    for ch in pack.chapters:
        for ls in ch.lessons:
            ids = {b.id for b in ls.blocks}
            quiz_ids = {q.id for b in ls.blocks if b.kind == "quiz" for q in b.items}
            touched = bool(ids & done) or ls.id == last or bool(quiz_ids & answered)
            lessons.append(LessonRef(ls.id, ls.title, len(lessons) + 1))
            if touched:
                furthest = len(lessons) - 1
    for i, ref in enumerate(lessons):
        ref.studied = i <= furthest
        ref.current = furthest >= 0 and furthest - 1 <= i <= furthest
    return lessons, furthest


def load_bundles(content: Any, bank: Bank, user_id: str, only_course: str | None = None) -> list[CourseBundle]:
    """The student's enrolled courses at their pinned versions (a pack that cannot be read is skipped)."""
    if content is None:
        return []
    out: list[CourseBundle] = []
    for e in content.list_enrollments(user_id):
        if only_course and e["course_id"] != only_course:
            continue
        try:
            pack = content.store.load_pack(e["course_id"], e["version"])
        except (ContentError, OSError, ValueError):
            log.warning("practice: pack of %s v%s unreadable", e["course_id"], e["version"])
            continue
        course = e.get("course") or {}
        title = course.get("title") or pack.title
        subject = course.get("subject") or ""
        lessons, _ = _studied(pack, e)
        bundle = CourseBundle(e["course_id"], title, subject, course.get("cover_sha256"), pack.age_band, e["version"],
                              lessons, last_seen=e.get("updated_at"))
        by_id = {ref.id: ref for ref in lessons}
        for ch in pack.chapters:
            for ls in ch.lessons:
                for b in ls.blocks:
                    if b.kind != "quiz":
                        continue
                    for q in b.items:
                        bundle.items.append(quiz_to_item(
                            q, course_id=e["course_id"], version=e["version"], course_title=title, subject_label=subject,
                            lesson_id=ls.id, lesson_title=ls.title, lesson_index=by_id[ls.id].index, bank=bank))
        out.append(bundle)
    return out
