"""Quiz items for a lesson: DeepTutor for multiple choice grounded in the source, our own prompt for everything else.

    items, media, notes = make_quiz(ctx, client, dt=DeepTutor.from_env(), kb="my-kb")

DeepTutor only makes multiple choice; TRUE_FALSE_GROUP, SHORT_ANSWER, PICTURE_CHOICE and TAP_COUNT always come from the
REASONING prompt below, and so does every item when the sidecar is missing/failing or the lesson has no source pages.
Items that need a picture carry a placeholder AssetRef (PENDING_SHA) and a MediaRequest; the assembler fills them from
the MediaResult or drops the item.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from mentor_schemas import ModelAlias
from mentor_schemas.course import AssetRef, QuizItem, QuizOption, TapTarget, TrueFalseStatement

from mentor_course_builder.contracts import MediaRequest
from mentor_course_builder.deeptutor import DeepTutor, DeepTutorError, RawQuestion
from mentor_course_builder.gen import AGE_RULES, ask_json, lang_name
from mentor_course_builder.llm import ModelClient, ModelError

log = logging.getLogger("mentor_course_builder")

PENDING_SHA = "0" * 64  # placeholder AssetRef.sha256 until the media stage delivers the file
LETTERS = "ABCDEFGH"


def pending_ref(request_id: str, mime: str) -> AssetRef:
    ext = {"image/png": "png", "image/webp": "webp", "audio/mpeg": "mp3"}.get(mime, "bin")
    return AssetRef(path=f"pending/{request_id}.{ext}", mime=mime, sha256=PENDING_SHA, bytes=0)


def is_pending(ref: AssetRef | None) -> bool:
    return ref is not None and ref.sha256 == PENDING_SHA


@dataclass
class LessonContext:
    lesson_id: str
    title: str
    summary: str
    key_ideas: list[str]
    reading: str  # the source text (or the written lesson) the questions must stay inside
    course_id: str
    age_band: str
    language: str
    grounded: bool = True
    subject: str = ""


@dataclass
class QuizResult:
    items: list[QuizItem] = field(default_factory=list)
    media: list[MediaRequest] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- DeepTutor -> QuizItem
_CITE = re.compile(r"\s*\[[^\]\n]{1,60}\]")  # "[dt-probe]" knowledge-base citation tags
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_WRONG = re.compile(r"^\s*[-*•]\s*\**\s*(?:Phương án\s+)?([A-H])\s*(?:sai|không đúng|is wrong|is incorrect|incorrect)"
                    r"[^:\n]*:?\**:?\s*(.+)$", re.IGNORECASE)


def _clean_md(s: str) -> str:
    s = _CITE.sub("", s)
    s = _BOLD.sub(r"\1", s)
    return re.sub(r"[ \t]+", " ", s).strip()


def first_sentences(text: str, n: int = 2, max_chars: int = 280) -> str:
    text = " ".join(text.split())
    parts = re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-Ỹ0-9$])", text)
    out = " ".join(parts[:n]).strip()
    if len(out) > max_chars:
        out = parts[0][:max_chars].rstrip()
    return out


def split_explanation(raw: str, correct: str, options: dict[str, str]) -> tuple[str, dict[str, str]]:
    """DeepTutor writes a long explanation + "- **B sai:** ..." lines. Returns (<=2 short sentences, feedback per wrong
    option, one sentence each)."""
    feedback: dict[str, str] = {}
    head: list[str] = []
    done = False
    for line in _clean_md(raw).splitlines():
        m = _WRONG.match(line)
        if m and m.group(1).upper() in options and m.group(1).upper() != correct:
            feedback[m.group(1).upper()] = first_sentences(m.group(2), 1, 200)
        elif not line.strip():
            done = bool(head)  # first paragraph only; keep scanning for the "- B sai:" lines
        elif not done and not line.lstrip().startswith(("-", "*", "•")):
            head.append(line.strip())
    expl = first_sentences(" ".join(head), 2) or first_sentences(_clean_md(raw), 2)
    return expl, feedback


def _strip_letter(s: str) -> str:
    return re.sub(r"^\s*[A-H][.)]\s+", "", s).strip()


def map_raw_choice(raw: RawQuestion, item_id: str, *, skill_ids: list[str] | None = None) -> QuizItem:
    expl, fb = split_explanation(raw.explanation, raw.correct, raw.options)
    diff = {"easy": 1, "medium": 2, "hard": 3}.get(raw.difficulty.lower(), 2)
    return QuizItem(
        id=item_id, type="SINGLE_CHOICE", stem=_clean_md(raw.stem),
        options=[QuizOption(id=k, text=_strip_letter(_clean_md(v))) for k, v in sorted(raw.options.items())],
        answer_key={"correct_option_id": raw.correct}, explanation=expl or "Đáp án đúng khớp với nội dung bài.",
        option_feedback=fb, difficulty=diff, skill_ids=skill_ids or [])


# ---------------------------------------------------------------- own prompt -> QuizItem
def quiz_from_dict(d: dict[str, Any], item_id: str, ctx_course: str, age_band: str, language: str
                   ) -> tuple[QuizItem, list[MediaRequest]]:
    """Map one model-written item (schema in QUIZ_SYSTEM) to a valid QuizItem + MediaRequests. Raises ValueError."""
    t = str(d.get("type", "")).upper()
    media: list[MediaRequest] = []
    tts = age_band == "g1_5"

    def req(rid: str, kind: str, spec: dict, lesson: str | None = None) -> MediaRequest:
        return MediaRequest(id=rid, kind=kind, course_id=ctx_course, lesson_id=lesson, age_band=age_band,  # type: ignore[arg-type]
                            language=language, spec=spec)  # type: ignore[arg-type]

    lesson_id = item_id.split("-q")[0]
    common: dict[str, Any] = {"id": item_id, "stem": str(d.get("stem", "")).strip(),
                              "explanation": first_sentences(str(d.get("explanation", "")), 2) or "Xem lại phần bài đọc.",
                              "hint": (str(d["hint"]).strip() if d.get("hint") else None),
                              "difficulty": max(1, min(4, int(d.get("difficulty") or 2)))}
    if not common["stem"]:
        raise ValueError("empty stem")
    if tts:
        stem_audio = pending_ref(f"{item_id}.stem", "audio/mpeg")
        common["stem_audio"] = stem_audio
        media.append(req(f"{item_id}.stem", "tts", {"text": common["stem"]}, lesson_id))
    if t in ("SINGLE_CHOICE", "PICTURE_CHOICE"):
        raw_opts = d.get("options") or []
        if not 2 <= len(raw_opts) <= 6:
            raise ValueError("options")
        opts, fb = [], {}
        for i, o in enumerate(raw_opts):
            oid = LETTERS[i]
            o = {"text": o} if isinstance(o, str) else o
            text = _strip_letter(str(o.get("text") or "")) or None
            opt = QuizOption(id=oid, text=text)
            if t == "PICTURE_CHOICE":
                desc = str(o.get("picture") or o.get("text") or "").strip()
                if not desc:
                    raise ValueError("picture option needs a description")
                opt.image = pending_ref(f"{item_id}.pic-{oid}", "image/png")
                media.append(req(f"{item_id}.pic-{oid}", "picture", {"description": desc}, lesson_id))
            if tts and text:
                opt.audio = pending_ref(f"{item_id}.opt-{oid}", "audio/mpeg")
                media.append(req(f"{item_id}.opt-{oid}", "tts", {"text": text}, lesson_id))
            if o.get("feedback"):
                fb[oid] = first_sentences(str(o["feedback"]), 1, 200)
            opts.append(opt)
        correct = str(d.get("correct") or "").strip().upper()[:1]
        if correct not in {o.id for o in opts}:
            raise ValueError("correct option")
        fb.pop(correct, None)
        item = QuizItem(type=t, options=opts, answer_key={"correct_option_id": correct},  # type: ignore[arg-type]
                        option_feedback=fb, **common)
    elif t == "TRUE_FALSE_GROUP":
        sts = d.get("statements") or []
        if not 2 <= len(sts) <= 4:
            raise ValueError("statements")
        statements = [TrueFalseStatement(id="abcd"[i], text=str(s["text"]).strip()) for i, s in enumerate(sts)]
        key = {"abcd"[i]: bool(s["answer"]) for i, s in enumerate(sts)}
        item = QuizItem(type=t, statements=statements, answer_key={"statements": key}, **common)
    elif t == "SHORT_ANSWER":
        acc = [str(a).strip() for a in (d.get("accepted") or []) if str(a).strip()]
        if not acc:
            raise ValueError("accepted")
        key: dict[str, Any] = {"accepted": acc}
        if d.get("tolerance") is not None:
            key["tolerance"] = float(d["tolerance"])
        item = QuizItem(type=t, answer_key=key, **common)
    elif t == "TAP_COUNT":
        total, count = int(d.get("total") or 0), int(d.get("count") if d.get("count") is not None else -1)
        desc = str(d.get("picture") or "").strip()
        if not desc or not 1 <= total <= 20 or not 0 <= count <= total:
            raise ValueError("tap count")
        media.append(req(f"{item_id}.tap", "picture", {"description": desc, "count": 1}, lesson_id))
        item = QuizItem(type=t, tap=TapTarget(image=pending_ref(f"{item_id}.tap", "image/png"), total=total),
                        answer_key={"count": count}, **common)
    else:
        raise ValueError(f"unknown type {t}")
    return item, media


QUIZ_SYSTEM = """You write quiz items for a lesson. Reply with ONE JSON object {"items": [...]}. Use ONLY facts in the
LESSON TEXT (and ordinary common knowledge when the lesson says it is general knowledge). Language: {lang}. Level: {band}.

Item shapes (all: "stem", "explanation" (one or two SHORT sentences: why the right answer is right), "hint" (optional),
"difficulty" 1-4):
{"type":"SINGLE_CHOICE","options":[{"text","feedback" (one sentence for a WRONG option, omit on the right one)}] (3-4),
   "correct":"A".."D"}
{"type":"TRUE_FALSE_GROUP","statements":[{"text","answer":true|false}] (3-4; mix true and false)}
{"type":"SHORT_ANSWER","accepted":["4e4","40000"] (every accepted spelling; numbers only when numeric),
   "tolerance": 0.01 (optional, relative, numeric answers only)}
{"type":"PICTURE_CHOICE","options":[{"picture":"plain description of a simple object picture"}] (2-3),"correct":"A".."C"}
{"type":"TAP_COUNT","picture":"one small object, e.g. a red apple","total":int<=10,"count":int<=total}
Math in LaTeX between $...$. No HTML. The correct option must not be longer or more detailed than the others. Do not
reveal the answer in the stem. Write what a good teacher would ask, not trivia."""


def plan_types(age_band: str, n: int, have: int = 0) -> list[str]:
    """Types the own prompt must produce after DeepTutor made `have` multiple-choice items."""
    if age_band == "g1_5":
        base = ["PICTURE_CHOICE", "TAP_COUNT", "SINGLE_CHOICE"]
    elif age_band == "g6_9":
        base = ["SINGLE_CHOICE", "TRUE_FALSE_GROUP", "SINGLE_CHOICE"]
    elif age_band == "g10_12":
        base = ["SINGLE_CHOICE", "SINGLE_CHOICE", "TRUE_FALSE_GROUP", "SHORT_ANSWER", "SINGLE_CHOICE"]
    else:
        base = ["SINGLE_CHOICE", "SHORT_ANSWER", "TRUE_FALSE_GROUP", "SINGLE_CHOICE"]
    wanted = base[:n]
    out = []
    for t in wanted:
        if t == "SINGLE_CHOICE" and have > 0:
            have -= 1
            continue
        out.append(t)
    return out


def _own_items(ctx: LessonContext, types: list[str], start: int, client: ModelClient) -> QuizResult:
    res = QuizResult()
    if not types:
        return res
    rules = AGE_RULES[ctx.age_band]
    system = QUIZ_SYSTEM.replace("{lang}", lang_name(ctx.language)).replace("{band}", rules["label"])
    user = (f"LESSON: {ctx.title}\nKey ideas: {'; '.join(ctx.key_ideas)}\n\nLESSON TEXT:\n{ctx.reading[:8000]}\n\n"
            f"Write exactly {len(types)} items with these types in order: {', '.join(types)}.")
    if ctx.age_band == "g1_5":
        user += "\nVery short stems (one short sentence). Options are single words or very short phrases."
    if ctx.age_band == "g10_12":
        user += "\nExam style: numbers and units where the lesson has them."
    data = ask_json(client, system, user, max_tokens=4000, temperature=0.4)
    for d in data.get("items") or []:
        iid = f"{ctx.lesson_id}-q{start + len(res.items) + 1}"
        try:
            item, media = quiz_from_dict(d, iid, ctx.course_id, ctx.age_band, ctx.language)
        except (ValueError, TypeError, KeyError) as exc:
            res.notes.append(f"{iid}: dropped model item ({exc})")
            continue
        res.items.append(item)
        res.media += media
    return res


def dt_choice_count(age_band: str, n: int | None, grounded: bool) -> int:
    """How many multiple-choice items DeepTutor is asked for (0 = not used for this lesson)."""
    if not grounded or age_band == "g1_5":
        return 0
    return sum(1 for t in _base_types(age_band, n or AGE_RULES[age_band]["quiz_items"]) if t == "SINGLE_CHOICE")


def make_quiz(ctx: LessonContext, client: ModelClient, dt: DeepTutor | None = None, kb: str | None = None,
              n: int | None = None, prefetched: Any = None) -> QuizResult:
    """n items for the lesson (default by age band). DeepTutor first for grounded lessons, own prompt for the rest.
    `prefetched`: a Future of dt.quiz(...) already running (the pipeline starts it while the lesson is written)."""
    n = n or AGE_RULES[ctx.age_band]["quiz_items"]
    out = QuizResult()
    n_choice = sum(1 for t in _base_types(ctx.age_band, n) if t == "SINGLE_CHOICE")
    if dt is not None and kb and ctx.grounded and n_choice and ctx.age_band != "g1_5":
        try:
            raws = prefetched.result() if prefetched is not None else dt.quiz(ctx.title, kb, n=n_choice, language=ctx.language)
            for i, raw in enumerate(raws[:n_choice], 1):
                out.items.append(map_raw_choice(raw, f"{ctx.lesson_id}-q{i}"))
            out.notes.append(f"deeptutor: {len(out.items)} choice items")
        except (DeepTutorError, ValueError) as exc:
            out.notes.append(f"deeptutor unavailable, own prompts used ({str(exc)[:120]})")
    types = plan_types(ctx.age_band, n, have=len(out.items))
    own = _own_items(ctx, types, len(out.items), client)
    out.items += own.items
    out.media += own.media
    out.notes += own.notes
    return out


def _base_types(age_band: str, n: int) -> list[str]:
    return plan_types(age_band, n, have=0)


__all__ = ["LessonContext", "QuizResult", "make_quiz", "dt_choice_count", "map_raw_choice", "quiz_from_dict", "plan_types",
           "split_explanation", "pending_ref", "is_pending", "PENDING_SHA", "ModelAlias", "ModelError"]
