"""Stage 4: course outline (chapters -> lessons) from the intake, and the edits the teacher makes in the chat box.

    outline = build_outline(intake_result, client, teacher_note="Cho lớp 11A2")
    outline = apply_outline_edits(outline, [{"op": "rename", "id": "duong-suc-dien", "title": "..."}])   # no model
    outline = revise_outline(outline, "gộp bài 2 và 3", client)                                          # free text

Ids are stable slugs: an edit never changes the id of a lesson or chapter that survives (progress and teacher
comments hang on them). The agent applies every edit without asking back.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from mentor_schemas.course import AgeBand, Lang

from mentor_course_builder.gen import (ask_json, lang_name, page_label, pages_block, slugify, source_pages,
                                       unique_id)
from mentor_course_builder.intake import IntakeResult
from mentor_course_builder.llm import ModelClient


class OutlineLesson(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    est_minutes: int = Field(default=8, ge=1, le=240)
    summary: str = ""
    key_ideas: list[str] = []
    source_pages: list[str] = []  # page labels "file#index" from the intake
    grounded: bool = True  # False: the lesson is only in the outline, written from general knowledge


class OutlineChapter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    lessons: list[OutlineLesson] = []


class CourseOutline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_id: str
    title: str
    subject: str
    language: Lang
    age_band: AgeBand
    description_short: str = Field(max_length=400)  # two sentences; also the retrieval text
    outcomes: list[str] = []
    teacher_note: str | None = None
    level_suggested: Literal["basic", "intermediate", "advanced"] | None = None  # a suggestion only; the teacher confirms
    chapters: list[OutlineChapter] = []

    def lessons(self) -> list[OutlineLesson]:
        return [ls for ch in self.chapters for ls in ch.lessons]

    def est_minutes(self) -> int:
        return sum(ls.est_minutes for ls in self.lessons())

    def listing(self) -> str:
        """Numbered tree, the same numbering the teacher sees ("bài 2")."""
        lines, n = [], 0
        for ci, ch in enumerate(self.chapters, 1):
            lines.append(f"Chapter {ci} [{ch.id}] {ch.title}")
            for ls in ch.lessons:
                n += 1
                lines.append(f"  Lesson {n} [{ls.id}] {ls.title} ({ls.est_minutes} min)")
        return "\n".join(lines)


# ---------------------------------------------------------------- language / age detection
_VI_CHARS = set("ăâđêôơưĂÂĐÊÔƠƯàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ")


def detect_language(text: str) -> Lang:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return "vi"
    return "vi" if sum(c in _VI_CHARS for c in letters) / len(letters) > 0.03 else "en"


def age_band_from_note(note: str | None) -> AgeBand | None:
    """The teacher's note wins over inference ("Cho lớp 11A2" -> g10_12)."""
    if not note:
        return None
    n = note.lower()
    if re.search(r"đại học|sinh viên|university|college|undergrad", n):
        return "uni"
    m = re.search(r"(?:lớp|khối|grade|class)\s*(\d{1,2})", n)
    if m:
        g = int(m.group(1))
        return "g1_5" if g <= 5 else "g6_9" if g <= 9 else "g10_12"
    if re.search(r"tiểu học|primary", n):
        return "g1_5"
    if re.search(r"thcs|trung học cơ sở", n):
        return "g6_9"
    if re.search(r"thpt|trung học phổ thông|high school", n):
        return "g10_12"
    return None


LEVELS = ("basic", "intermediate", "advanced")
_LEVEL_RANK = {k: i for i, k in enumerate(LEVELS)}
# the highest level that makes sense for a band: primary school is never "advanced", university never "basic"
_BAND_RANGE = {"g1_5": (0, 0), "g6_9": (0, 1), "g10_12": (0, 2), "uni": (1, 2)}
_HARD_WORDS = re.compile(r"chứng minh|định lý|bổ đề|đạo hàm|tích phân|ma trận|xác suất|suy luận|thuật toán|prove|proof|theorem|"
                         r"lemma|derivative|integral|matrix|probabilit|algorithm|inference|\\int|\\sum|\\frac", re.I)


def suggest_level(band: str, model_level: object = None, *, text: str = "", n_lessons: int = 0) -> str:
    """Course level suggestion from the outline model's answer and the age band (no extra model call). Without a valid
    model answer: band default, nudged one step up when the material is dense with proof/calculus vocabulary and one
    step down for a very short course. The result is always inside the band's range; the teacher confirms it."""
    lo, hi = _BAND_RANGE.get(band, (0, 2))
    if model_level in _LEVEL_RANK:
        r = _LEVEL_RANK[str(model_level)]
    else:
        r = {"g1_5": 0, "g6_9": 0, "g10_12": 1, "uni": 1}.get(band, 1)
        hard = len(_HARD_WORDS.findall(text))
        if hard >= 12:
            r += 1
        elif n_lessons and n_lessons <= 2:
            r -= 1
    return LEVELS[max(lo, min(hi, r))]


# ---------------------------------------------------------------- build
OUTLINE_SYSTEM = """You design a course outline from a teacher's materials. Reply with ONE JSON object, no prose.

Schema:
{"title": str, "subject": str (in the course language, e.g. "Vật lí"), "language": "vi"|"en",
 "age_band": "g1_5"|"g6_9"|"g10_12"|"uni",
 "level": "basic"|"intermediate"|"advanced" (how demanding the material is for that age band),
 "description_short": str (exactly two short sentences: what the course covers and who it is for),
 "outcomes": [str] (3-5 items that finish "Học xong em sẽ ..." / "After this you will ...", without that prefix),
 "chapters": [{"title": str, "lessons": [{"title": str, "est_minutes": int (3-15), "summary": str (one sentence),
   "key_ideas": [str] (3-5 short phrases), "source_pages": [str] (labels like "file.pdf#3" copied from the material
   headers; [] if no page covers it), "grounded": bool}]}]}

Rules:
- Follow the order and scope of the material. One lesson = one idea a learner can finish in 3-15 minutes.
- grounded=true only when pages in the material actually cover the lesson. A lesson the material only names
  (for example in a table of contents) or that you add to complete the course gets grounded=false and source_pages [].
- Write titles and text in the language of the material. Do not invent facts.
- Age band: infer from the material's level; the teacher's note overrides your guess.
- Level: basic = first contact, worked examples, no prerequisites; intermediate = needs the basics, some multi-step
  reasoning; advanced = proofs, derivations, abstract or heavily symbolic material."""


def build_outline(intake: IntakeResult, client: ModelClient, teacher_note: str | None = None,
                  course_id: str | None = None) -> CourseOutline:
    pages = source_pages(intake)
    body = pages_block(pages)
    note = f"Teacher's note: {teacher_note}\n\n" if teacher_note else ""
    data = ask_json(client, OUTLINE_SYSTEM, f"{note}MATERIAL:\n{body}", max_tokens=6000)
    return outline_from_json(data, teacher_note=teacher_note, course_id=course_id, valid_pages={p for p, _ in pages},
                             detect_from=body)


def outline_from_json(data: dict[str, Any], *, teacher_note: str | None = None, course_id: str | None = None,
                      valid_pages: set[str] | None = None, detect_from: str = "") -> CourseOutline:
    title = str(data.get("title") or "Khóa học").strip()
    lang = data.get("language") if data.get("language") in ("vi", "en") else None
    if detect_from:
        lang = detect_language(detect_from)  # code beats the model's guess
    lang = lang or "vi"
    band = age_band_from_note(teacher_note) or (data.get("age_band") if data.get("age_band") in
                                                ("g1_5", "g6_9", "g10_12", "uni") else "g10_12")
    taken: set[str] = set()
    chapters: list[OutlineChapter] = []
    for ch in data.get("chapters") or []:
        ch_id = unique_id("ch-" + slugify(str(ch.get("title") or "chuong"), "chuong", 30), taken)
        lessons: list[OutlineLesson] = []
        for ls in ch.get("lessons") or []:
            refs = [r for r in (ls.get("source_pages") or []) if valid_pages is None or r in valid_pages]
            grounded = bool(ls.get("grounded", True)) and bool(refs)
            ideas = [str(k).strip() for k in (ls.get("key_ideas") or []) if str(k).strip()][:6]
            try:
                mins = max(1, min(240, int(ls.get("est_minutes") or 8)))
            except (TypeError, ValueError):
                mins = 8
            lessons.append(OutlineLesson(
                id=unique_id(slugify(str(ls.get("title") or "bai"), "bai"), taken),
                title=str(ls.get("title") or "Bài").strip(), est_minutes=mins,
                summary=str(ls.get("summary") or "").strip(), key_ideas=ideas, source_pages=refs, grounded=grounded))
        if lessons:
            chapters.append(OutlineChapter(id=ch_id, title=str(ch.get("title") or "Chương").strip(), lessons=lessons))
    if not chapters:
        raise ValueError("outline has no lessons")
    desc = str(data.get("description_short") or "").strip()[:400]
    n_lessons = sum(len(c.lessons) for c in chapters)
    return CourseOutline(
        level_suggested=suggest_level(band, data.get("level"), text=detect_from, n_lessons=n_lessons),  # type: ignore[arg-type]
        course_id=course_id or slugify(title, "khoa-hoc", 50), title=title,
        subject=str(data.get("subject") or title).strip(), language=lang, age_band=band,  # type: ignore[arg-type]
        description_short=desc, outcomes=[str(o).strip() for o in (data.get("outcomes") or []) if str(o).strip()][:6],
        teacher_note=teacher_note, chapters=chapters)


# ---------------------------------------------------------------- structured edits (the chat box)
class OutlineEditError(ValueError):
    pass


def _find_lesson(o: CourseOutline, lid: str) -> tuple[OutlineChapter, int]:
    for ch in o.chapters:
        for i, ls in enumerate(ch.lessons):
            if ls.id == lid:
                return ch, i
    raise OutlineEditError(f"no lesson {lid}")


def _find_chapter(o: CourseOutline, cid: str) -> OutlineChapter:
    for ch in o.chapters:
        if ch.id == cid:
            return ch
    raise OutlineEditError(f"no chapter {cid}")


def _all_ids(o: CourseOutline) -> set[str]:
    return {ch.id for ch in o.chapters} | {ls.id for ls in o.lessons()}


def _insert(items: list, item: Any, index: int | None, after: str | None) -> None:
    if after is not None:
        pos = next((i + 1 for i, x in enumerate(items) if x.id == after), None)
        if pos is None:
            raise OutlineEditError(f"no item {after} to insert after")
        items.insert(pos, item)
    elif index is None or index >= len(items):
        items.append(item)
    else:
        items.insert(max(0, index), item)


def apply_outline_edits(outline: CourseOutline, ops: list[dict[str, Any]]) -> CourseOutline:
    """Apply structured edits in order to a copy. Ops (all ids are lesson/chapter ids):

    {"op": "rename", "id", "title"}                          lesson, chapter, or the course itself (id = outline.course_id)
    {"op": "update", "id", "summary"?, "est_minutes"?, "key_ideas"?}   lesson fields
    {"op": "reorder", "ids": [...], "parent": chapter id | null}      new order of that chapter's lessons (or of the
                                                                      chapters when parent is null); ids not listed keep
                                                                      their relative order after the listed ones
    {"op": "delete", "id"}                                   lesson or chapter (a chapter takes its lessons along)
    {"op": "add_lesson", "chapter", "title", "after"?|"index"?, "summary"?, "est_minutes"?, "key_ideas"?}
    {"op": "add_chapter", "title", "after"?|"index"?}
    {"op": "move_lesson", "id", "chapter", "index"?|"after"?}
    {"op": "merge", "ids": [a, b, ...], "title"?}            into the first lesson (its id stays); a chapter left empty
                                                             is removed
    A new lesson is not grounded in the source (grounded=false). Raises OutlineEditError on a bad op.
    """
    o = outline.model_copy(deep=True)
    for op in ops:
        kind = op.get("op")
        if kind == "rename":
            title = str(op["title"]).strip()
            if not title:
                raise OutlineEditError("empty title")
            ids = {ch.id: ch for ch in o.chapters}
            if op["id"] == o.course_id:
                o.title = title
            elif op["id"] in ids:
                ids[op["id"]].title = title
            else:
                ch, i = _find_lesson(o, op["id"])
                ch.lessons[i].title = title
        elif kind == "update":
            ch, i = _find_lesson(o, op["id"])
            ls = ch.lessons[i]
            if "summary" in op:
                ls.summary = str(op["summary"])
            if "est_minutes" in op:
                ls.est_minutes = max(1, min(240, int(op["est_minutes"])))
            if "key_ideas" in op:
                ls.key_ideas = [str(k) for k in op["key_ideas"]]
        elif kind == "reorder":
            ids = list(op["ids"])
            if op.get("parent") is None:
                items = o.chapters
            else:
                items = _find_chapter(o, op["parent"]).lessons
            known = {x.id for x in items}
            if not set(ids) <= known:
                raise OutlineEditError(f"reorder: unknown ids {sorted(set(ids) - known)}")
            first = [next(x for x in items if x.id == i) for i in dict.fromkeys(ids)]
            rest = [x for x in items if x.id not in set(ids)]
            items[:] = first + rest
        elif kind == "delete":
            tid = op["id"]
            before = len(o.chapters)
            o.chapters = [ch for ch in o.chapters if ch.id != tid]
            if len(o.chapters) == before:
                ch, i = _find_lesson(o, tid)
                del ch.lessons[i]
                if not ch.lessons:
                    o.chapters.remove(ch)
        elif kind == "add_lesson":
            ch = _find_chapter(o, op["chapter"])
            title = str(op["title"]).strip()
            taken = _all_ids(o)
            ls = OutlineLesson(id=unique_id(slugify(title, "bai"), taken), title=title,
                               est_minutes=max(1, min(240, int(op.get("est_minutes") or 8))),
                               summary=str(op.get("summary") or ""), key_ideas=[str(k) for k in op.get("key_ideas") or []],
                               grounded=False)
            _insert(ch.lessons, ls, op.get("index"), op.get("after"))
        elif kind == "add_chapter":
            title = str(op["title"]).strip()
            ch = OutlineChapter(id=unique_id("ch-" + slugify(title, "chuong", 30), _all_ids(o)), title=title)
            _insert(o.chapters, ch, op.get("index"), op.get("after"))
        elif kind == "move_lesson":
            src, i = _find_lesson(o, op["id"])
            dest = _find_chapter(o, op["chapter"])
            ls = src.lessons.pop(i)
            _insert(dest.lessons, ls, op.get("index"), op.get("after"))
        elif kind == "merge":
            ids = list(dict.fromkeys(op["ids"]))
            if len(ids) < 2:
                raise OutlineEditError("merge needs two or more lessons")
            keep_ch, ki = _find_lesson(o, ids[0])
            keep = keep_ch.lessons[ki]
            for other in ids[1:]:
                ch, i = _find_lesson(o, other)
                ls = ch.lessons.pop(i)
                keep.est_minutes = min(240, keep.est_minutes + ls.est_minutes)
                keep.key_ideas = list(dict.fromkeys(keep.key_ideas + ls.key_ideas))[:8]
                keep.source_pages = list(dict.fromkeys(keep.source_pages + ls.source_pages))
                keep.grounded = keep.grounded and ls.grounded
                if not ls.summary or ls.summary in keep.summary:
                    pass
                else:
                    keep.summary = (keep.summary + " " + ls.summary).strip()
            if op.get("title"):
                keep.title = str(op["title"]).strip()
            o.chapters = [ch for ch in o.chapters if ch.lessons]
        else:
            raise OutlineEditError(f"unknown op {kind!r}")
    if not o.chapters:
        raise OutlineEditError("the outline would be empty")
    return o


REVISE_SYSTEM = """You edit a course outline for a teacher who typed a request in free text. Do exactly what was asked, do not
ask questions back, change nothing else. Reply with ONE JSON object {"ops": [...], "note": str} where note is one short
sentence in the teacher's language saying what you did. Allowed ops (ids are in square brackets in the outline; "bài 2"
means the lesson numbered 2):
{"op":"rename","id","title"} {"op":"update","id","summary"?,"est_minutes"?,"key_ideas"?}
{"op":"reorder","ids":[...],"parent":chapterId|null} {"op":"delete","id"}
{"op":"add_lesson","chapter","title","after"?,"summary"?,"est_minutes"?,"key_ideas"?}
{"op":"add_chapter","title","after"?} {"op":"move_lesson","id","chapter","index"?,"after"?}
{"op":"merge","ids":[...],"title"?}   (the first id survives)"""


def revise_outline(outline: CourseOutline, instruction: str, client: ModelClient) -> tuple[CourseOutline, str]:
    """Free-text edit ("gộp bài 2 và 3"). Returns (new outline, one-line note). Never asks back."""
    data = ask_json(client, REVISE_SYSTEM, f"OUTLINE:\n{outline.listing()}\n\nREQUEST: {instruction}", max_tokens=2000,
                    temperature=0.0)
    ops = [op for op in data.get("ops") or [] if isinstance(op, dict)]
    return apply_outline_edits(outline, ops), str(data.get("note") or "")


def outline_to_json(o: CourseOutline) -> str:
    return json.dumps(o.model_dump(), ensure_ascii=False, indent=2)


__all__ = ["CourseOutline", "OutlineChapter", "OutlineLesson", "OutlineEditError", "apply_outline_edits",
           "build_outline", "revise_outline", "suggest_level", "detect_language", "age_band_from_note", "outline_to_json",
           "outline_from_json", "Literal", "lang_name", "page_label"]
