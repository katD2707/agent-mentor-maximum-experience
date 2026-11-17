"""Stage 5: write one lesson (blocks for the age band, MediaRequests for the media stage, quiz block).

    draft = write_lesson(outline, lesson, client, pages, dt=..., kb=...)
    draft.lesson     course.Lesson (assets are placeholders until the assembler fills them from MediaResults)
    draft.media      list[MediaRequest]  per contracts.py
    draft.notes      e.g. "written from general knowledge (not in the source)"
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from mentor_schemas.course import (AssetRef, Axis, CalloutBlock, ImageBlock, InteractiveBlock, Lesson, RecallBlock,
                                   RecallItem, TextBlock, VideoBlock)

from mentor_course_builder.contracts import MediaRequest
from mentor_course_builder.deeptutor import DeepTutor
from mentor_course_builder.gen import AGE_RULES, ask_json, lang_name
from mentor_course_builder.llm import ModelClient
from mentor_course_builder.mediaplan import LessonMedia
from mentor_course_builder.outline import CourseOutline, OutlineLesson
from mentor_course_builder.quiz import LessonContext, make_quiz, pending_ref
from mentor_course_builder.steps import interactive_problem, place_quiz, recall_problem, spread_difficulty

log = logging.getLogger("mentor_course_builder")


@dataclass
class LessonDraft:
    lesson: Lesson
    media: list[MediaRequest] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    grounded: bool = True
    source_text: str = ""
    verified: set[str] = field(default_factory=set)  # item_hash of quiz items already re-solved independently


BAND_SPEC = {
    "g1_5": """Primary school, grades 1-5. The child may barely read. VERY short sentences (at most 8 words), one idea per
block, 5-8 blocks. Mostly "illustration" blocks (a simple, friendly picture) each followed by one short "text" block.
No formulas, no hard words. Use "callout" variant "remember" once at the end (one short sentence). If the lesson material
mentions a film or video ("phim"), start the lesson with ONE short "video" block (2-3 scenes, about 40 s in total, narration
at most 8 words per scene, pictures first); otherwise no video.""",
    "g6_9": """Lower secondary, grades 6-9. A lesson is a chain of SHORT one-task steps (4-8 minutes). Each "text" step is 1-2
sentences (at most 16 words each), one idea. Order: optionally one short "video" (3 scenes), an "illustration" or "diagram",
then the explanation steps (a "callout" variant "example" for a worked number), and an "interactive" block when the lesson has a
numeric relation. Questions are added after your steps, do not write them.""",
    "g10_12": """Upper secondary, grades 10-12 (exam style). A lesson is a chain of SHORT one-task steps (4-8 minutes). Each
"text" step is 1-2 sentences, one idea; math in LaTeX ($...$). Order: optionally one short "video" (3-5 scenes), a "diagram" or
"illustration" if a picture helps, the explanation steps, a "callout" variant "remember" (the formula), one "callout" variant
"example" with one worked example (numbers and units), and an "interactive" block when the lesson has a numeric relation.
Questions are added after your steps, do not write them.""",
    "uni": """University. A lesson is a chain of one-task steps (4-8 minutes). Each "text" step is 1-2 precise sentences with
LaTeX ($...$) where needed; "callout" variant "definition" for every new term; a "diagram" with exact "math" when a figure helps;
a worked "callout" variant "example"; an "interactive" block when the lesson has a numeric relation. No video unless the
source is a lecture. Questions are added after your steps, do not write them.""",
}

LESSON_SYSTEM = """You write one lesson of a course. Reply with ONE JSON object {"blocks": [...]}.
Language: {lang}. Level: {band_label}.
{band_spec}

Block shapes ("md" is Markdown with KaTeX math between $...$, no raw HTML):
{"kind":"text","md":str{gloss_field}}
{"kind":"callout","variant":"remember"|"definition"|"example"|"tip"|"mistake","title":str|null,"md":str}
{"kind":"illustration","description":"what to draw, plain words, no text inside the picture","alt":str,"caption":str|null}
{"kind":"diagram","description":str,"labels":[str],"math":"exact formula / data to plot, or null","alt":str,"caption":str|null}
{"kind":"video","title":str,"target_s":int,"scenes":[{"caption":"on-screen text, short","narration":"what the voice says","visual":"what to draw and animate"}]}
{extra_shapes}
Rules:
- {grounding}
- Natural, short, direct; the way a good teacher talks. No filler openers, no "Hãy cùng khám phá", no summary of the summary.
- Numbers and formulas must be right; show units. Do not invent names, dates or sources.
- At most {max_blocks} blocks. Each "text" at most {max_chars} characters. {recall_rule}"""

INTERACTIVE_SHAPE = (
    '{"kind":"interactive","prompt":"the task in one line, e.g. Kéo để E còn 1/4","x":{"symbol":"r","label":"Khoảng cách","unit":"m"},'
    '"y":{"symbol":"E","label":"Cường độ","unit":"V/m"},"expr":"y as a formula of x using + - * / ^ sqrt sin cos exp log pi",'
    '"x_min":num,"x_max":num,"x_step":num,"x_start":num (not the answer),"target_y":num (must be reachable at some x on the '
    'step grid),"tolerance":num,"praise":"one sentence when reached"}  (ONLY when the lesson has a numeric relation between two '
    'quantities; at most one)\n')
RECALL_SHAPE = ('{"kind":"recall","items":[{"prompt":"a question that makes the learner say the idea","answer":"the idea, one '
                'short sentence"}]}  (LAST block; 2-3 items from the key ideas)\n')
GLOSS_FIELD = ',"gloss":"the same text in Vietnamese (required on every text block)"'
RECALL_RULE = "End with ONE recall block built from the key ideas."

GROUNDED = ("Use ONLY the SOURCE text for facts, definitions, numbers and examples. You may reorder and simplify, "
            "never contradict or add facts the source does not support.")
UNGROUNDED = ("The source does NOT cover this lesson; it is only named in the course outline. Write it from standard, "
              "well-established general knowledge of the subject and keep to the key ideas listed.")


def _req(kind: str, rid: str, course: str, lesson: str, band: str, lang: str, spec: dict) -> MediaRequest:
    return MediaRequest(id=rid, kind=kind, course_id=course, lesson_id=lesson, age_band=band,  # type: ignore[arg-type]
                        language=lang, spec=spec)  # type: ignore[arg-type]


def blocks_from_json(data: dict[str, Any], *, course_id: str, lesson_id: str, age_band: str, language: str,
                     plan: "LessonMedia | None" = None) -> tuple[list, list[MediaRequest], list[str]]:
    """Model blocks -> course blocks + MediaRequests (tts for EVERY text/callout in g1_5). Unknown blocks are skipped."""
    blocks: list = []
    media: list[MediaRequest] = []
    notes: list[str] = []
    tts = age_band == "g1_5"
    stepped = age_band != "g1_5"
    videos_left = plan.video if plan else 99
    pictures_left = plan.pictures if plan else 99

    def bid() -> str:
        return f"{lesson_id}-b{len(blocks) + 1}"

    for raw in data.get("blocks") or []:
        kind = str(raw.get("kind", "")).lower()
        try:
            if kind == "text" and str(raw.get("md", "")).strip():
                i = bid()
                md = str(raw["md"]).strip()
                gloss = (str(raw.get("gloss") or "").strip() or None) if language == "en" else None
                if language == "en" and not gloss:
                    notes.append(f"{i}: text has no Vietnamese gloss")
                blocks.append(TextBlock(id=i, md=md, gloss=gloss, audio=pending_ref(i, "audio/mpeg") if tts else None))
                if tts:
                    media.append(_req("tts", i, course_id, lesson_id, age_band, language, {"text": md}))
            elif kind == "callout" and str(raw.get("md", "")).strip():
                i = bid()
                md = str(raw["md"]).strip()
                variant = raw.get("variant") if raw.get("variant") in ("remember", "definition", "example", "tip",
                                                                       "mistake") else "tip"
                title = (str(raw["title"]).strip() if raw.get("title") else None)
                blocks.append(CalloutBlock(id=i, variant=variant, title=title, md=md,
                                           audio=pending_ref(i, "audio/mpeg") if tts else None))
                if tts:
                    media.append(_req("tts", i, course_id, lesson_id, age_band, language,
                                      {"text": (title + ". " if title else "") + md}))
            elif kind in ("illustration", "diagram") and str(raw.get("description", "")).strip():
                if pictures_left <= 0:
                    notes.append(f"{kind} dropped by the media plan (not needed for this lesson)")
                    continue
                pictures_left -= 1
                i = bid()
                caption = str(raw["caption"]).strip() if raw.get("caption") else None
                alt = str(raw.get("alt") or raw["description"]).strip()
                spec: dict[str, Any] = {"description": str(raw["description"]).strip()}
                if kind == "diagram":
                    if raw.get("labels"):
                        spec["labels"] = [str(x) for x in raw["labels"]]
                    if raw.get("math"):
                        spec["math"] = str(raw["math"])
                blocks.append(ImageBlock(id=i, image=pending_ref(i, "image/png"), alt=alt, caption=caption,
                                         audio=pending_ref(f"{i}.audio", "audio/mpeg") if tts else None))
                media.append(_req(kind, i, course_id, lesson_id, age_band, language, spec))
                if tts:
                    media.append(_req("tts", f"{i}.audio", course_id, lesson_id, age_band, language,
                                      {"text": caption or alt}))
            elif kind == "video":
                if videos_left <= 0:
                    notes.append("video dropped by the media plan (not needed for this lesson)")
                    continue
                scenes = [{"caption": str(s.get("caption", "")), "narration": str(s.get("narration", "")),
                           "visual": str(s.get("visual", ""))} for s in raw.get("scenes") or []
                          if isinstance(s, dict) and s.get("narration")]
                if not 2 <= len(scenes) <= 6:
                    notes.append("video block dropped: needs 3-5 scenes with narration")
                    continue
                videos_left -= 1
                i = bid()
                target = max(30, min(300, int(raw.get("target_s") or 30 * len(scenes))))
                title = str(raw.get("title") or "").strip()
                blocks.append(VideoBlock(id=i, video=AssetRef(path=f"pending/{i}.mp4", mime="video/mp4",
                                                              sha256="0" * 64, bytes=0),
                                         duration_s=float(target), title=title or None))
                media.append(_req("video", i, course_id, lesson_id, age_band, language,
                                  {"title": title or "Video", "target_s": target, "scenes": scenes}))
            elif kind == "interactive" and stepped:
                i = bid()
                ib = None
                try:
                    ib = InteractiveBlock(id=i, prompt=str(raw["prompt"]).strip(), x=Axis(**_axis(raw["x"])),
                                          y=Axis(**_axis(raw["y"])), expr=str(raw["expr"]).strip(), x_min=float(raw["x_min"]),
                                          x_max=float(raw["x_max"]), x_step=float(raw["x_step"]),
                                          x_start=float(raw["x_start"]), target_y=float(raw["target_y"]),
                                          tolerance=float(raw.get("tolerance") or 0), praise=str(raw.get("praise") or "").strip())
                    bad = interactive_problem(ib)
                except (KeyError, ValueError, TypeError) as exc:
                    bad = f"incomplete ({str(exc)[:60]})"
                if bad or ib is None:
                    notes.append(f"interactive block dropped: {bad}")
                    continue
                blocks.append(ib)
            elif kind == "recall" and stepped:
                items = [RecallItem(prompt=str(x["prompt"]).strip(), answer=str(x["answer"]).strip())
                         for x in (raw.get("items") or [])[:4] if isinstance(x, dict) and x.get("prompt") and x.get("answer")]
                rb = RecallBlock(id=bid(), items=items) if items else None
                if rb is None or recall_problem(rb):
                    notes.append("recall block dropped: no usable items")
                    continue
                blocks.append(rb)
            else:
                notes.append(f"skipped block of kind {kind!r}")
        except (ValueError, TypeError) as exc:
            notes.append(f"skipped {kind} block: {str(exc)[:80]}")
    return blocks, media, notes


def _axis(a: Any) -> dict[str, str]:
    a = a if isinstance(a, dict) else {}
    return {"symbol": str(a.get("symbol") or "x"), "label": str(a.get("label") or ""), "unit": str(a.get("unit") or "")}


def content_cap(band: str, n_items: int) -> int:
    """Steps the lesson text may have so that steps + one question per item + the recall stay within the band's block limit."""
    rules = AGE_RULES[band]
    return max(4, rules["max_blocks"] - n_items - (0 if band == "g1_5" else 1))


def trim_steps(blocks: list, cap: int) -> list:
    """Keep at most `cap` blocks without the recall: the last plain text steps go first."""
    recall = [b for b in blocks if isinstance(b, RecallBlock)]
    body = [b for b in blocks if not isinstance(b, RecallBlock)]
    while len(body) > cap:
        k = next((i for i in range(len(body) - 1, -1, -1) if isinstance(body[i], TextBlock)), len(body) - 1)
        body.pop(k)
    return body + recall


def recall_from_key_ideas(lesson_id: str, title: str, key_ideas: list[str], language: str) -> RecallBlock | None:
    """Every lesson ends with "Nhớ lại": when the model left it out, ask for the lesson's key ideas (at most 3)."""
    ideas = [k.strip() for k in key_ideas if k and k.strip()][:3]
    if not ideas:
        return None
    n = len(ideas)

    def prompt(i: int) -> str:
        return (f"Ý chính {i} của bài «{title}» là gì?" if n > 1 else f"Ý chính của bài «{title}» là gì?") if language != "en" \
            else (f"Key idea {i} of “{title}”?" if n > 1 else f"The key idea of “{title}”?")

    return RecallBlock(id=f"{lesson_id}-r1", items=[RecallItem(prompt=prompt(i), answer=a) for i, a in enumerate(ideas, 1)])


def write_lesson(outline: CourseOutline, lesson: OutlineLesson, client: ModelClient, pages: dict[str, str],
                 dt: DeepTutor | None = None, kb: str | None = None, quiz_items: int | None = None,
                 plan: "LessonMedia | None" = None, hint: str | None = None, dt_quiz: Any = None) -> LessonDraft:
    """`plan`: media this lesson may carry (mediaplan.py). `hint`: a refine instruction (what to fix or avoid).
    `dt_quiz`: a Future of dt.quiz(...) started while the lesson was still being written."""
    band = outline.age_band
    rules = AGE_RULES[band]
    source = "\n\n".join(f"[{r}]\n{pages[r]}" for r in lesson.source_pages if r in pages)
    grounded = lesson.grounded and bool(source)
    n_items = quiz_items or rules["quiz_items"]
    cap = content_cap(band, n_items)
    lessons_all = outline.lessons()
    pos = next((i for i, x in enumerate(lessons_all) if x.id == lesson.id), 0)
    extra = "" if band == "g1_5" else INTERACTIVE_SHAPE + RECALL_SHAPE
    system = (LESSON_SYSTEM.replace("{extra_shapes}", extra).replace("{gloss_field}", GLOSS_FIELD if outline.language == "en" else "")
              .replace("{recall_rule}", "" if band == "g1_5" else RECALL_RULE).replace("{lang}", lang_name(outline.language)).replace("{band_label}", rules["label"])
              .replace("{band_spec}", BAND_SPEC[band]).replace("{grounding}", GROUNDED if grounded else UNGROUNDED)
              .replace("{max_blocks}", str(cap + (0 if band == "g1_5" else 1))).replace("{max_chars}", str(rules["max_text_chars"])))
    user = (f"COURSE: {outline.title} ({outline.subject})\nLESSON: {lesson.title}\nSummary: {lesson.summary}\n"
            f"Key ideas: {'; '.join(lesson.key_ideas)}\n\n"
            + (f"SOURCE:\n{source[:14000]}" if grounded else "SOURCE: (none)"))
    data = ask_json(client, system, user, max_tokens=7000, temperature=0.4, retries=3)
    blocks, media, notes = blocks_from_json(data, course_id=outline.course_id, lesson_id=lesson.id, age_band=band,
                                            language=outline.language)
    if not blocks:
        raise ValueError(f"lesson {lesson.id}: the model produced no usable blocks")
    blocks = trim_steps(blocks, cap)
    reading = "\n\n".join(b.md for b in blocks if isinstance(b, (TextBlock, CalloutBlock))) or source
    ctx = LessonContext(lesson_id=lesson.id, title=lesson.title, summary=lesson.summary, key_ideas=lesson.key_ideas,
                        reading=(source + "\n\n" + reading) if grounded else reading, course_id=outline.course_id,
                        age_band=band, language=outline.language, grounded=grounded, subject=outline.subject)
    quiz = make_quiz(ctx, client, dt=dt, kb=kb, n=quiz_items, prefetched=dt_quiz)
    notes += quiz.notes
    media += quiz.media
    if quiz.items:
        blocks = place_quiz(blocks, spread_difficulty(quiz.items, pos, len(lessons_all)), lesson.id)
    else:
        notes.append("no quiz items could be made")
    if band != "g1_5" and not any(isinstance(b, RecallBlock) for b in blocks):
        fallback = recall_from_key_ideas(lesson.id, lesson.title, lesson.key_ideas, outline.language)
        if fallback:
            blocks = blocks + [fallback]  # recall stays last
            notes.append("recall block made from the key ideas")
        else:
            notes.append("no recall block")
    if not grounded:
        notes.append("written from general knowledge (not covered by the source pages)")
    return LessonDraft(lesson=Lesson(id=lesson.id, title=lesson.title, est_minutes=lesson.est_minutes,
                                     summary=lesson.summary or None, key_ideas=lesson.key_ideas, blocks=blocks),
                       media=media, notes=notes, grounded=grounded, source_text=source)


__all__ = ["LessonDraft", "write_lesson", "blocks_from_json", "ImageBlock"]
