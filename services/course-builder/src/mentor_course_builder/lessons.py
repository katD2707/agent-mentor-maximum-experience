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

from mentor_schemas.course import (AssetRef, CalloutBlock, ImageBlock, Lesson, QuizBlock, TextBlock, VideoBlock)

from mentor_course_builder.contracts import MediaRequest
from mentor_course_builder.deeptutor import DeepTutor
from mentor_course_builder.gen import AGE_RULES, ask_json, lang_name
from mentor_course_builder.llm import ModelClient
from mentor_course_builder.mediaplan import LessonMedia
from mentor_course_builder.outline import CourseOutline, OutlineLesson
from mentor_course_builder.quiz import LessonContext, make_quiz, pending_ref

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
    "g6_9": """Lower secondary, grades 6-9. Short sentences (at most 16 words). Blocks in order: one short "video" (3 scenes),
an "illustration", 2-3 short "text" blocks, one "callout" variant "remember", one "callout" variant "example".""",
    "g10_12": """Upper secondary, grades 10-12 (exam style). Blocks in order: "video" first (3-5 scenes, 90-180 s), a short
reading ("text" blocks, 120-200 words in total), one "callout" variant "remember" (3-4 bullet points), one "diagram" or
"illustration" if a picture helps, one "callout" variant "example" with a fully worked example (numbers and units, every
step), optional "callout" variant "mistake". Math in LaTeX ($...$, $$...$$).""",
    "uni": """University. Blocks: deep "text" reading (several blocks, precise, with derivations in LaTeX $...$ / $$...$$),
"callout" variant "definition" for every new term, a "diagram" block with exact "math" (the formula or data to plot) when a
figure helps, a worked "callout" variant "example", one "callout" variant "remember" with the key results. No video unless
the source is a lecture. Serif-reading tone: formal but plain.""",
}

LESSON_SYSTEM = """You write one lesson of a course. Reply with ONE JSON object {"blocks": [...]}.
Language: {lang}. Level: {band_label}.
{band_spec}

Block shapes ("md" is Markdown with KaTeX math between $...$, no raw HTML):
{"kind":"text","md":str}
{"kind":"callout","variant":"remember"|"definition"|"example"|"tip"|"mistake","title":str|null,"md":str}
{"kind":"illustration","description":"what to draw, plain words, no text inside the picture","alt":str,"caption":str|null}
{"kind":"diagram","description":str,"labels":[str],"math":"exact formula / data to plot, or null","alt":str,"caption":str|null}
{"kind":"video","title":str,"target_s":int,"scenes":[{"caption":"on-screen text, short","narration":"what the voice says","visual":"what to draw and animate"}]}

Rules:
- {grounding}
- Natural, short, direct; the way a good teacher talks. No filler openers, no "Hãy cùng khám phá", no summary of the summary.
- Numbers and formulas must be right; show units. Do not invent names, dates or sources.
- At most {max_blocks} blocks. Each "text" at most {max_chars} characters."""

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
                blocks.append(TextBlock(id=i, md=md, audio=pending_ref(i, "audio/mpeg") if tts else None))
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
            else:
                notes.append(f"skipped block of kind {kind!r}")
        except (ValueError, TypeError) as exc:
            notes.append(f"skipped {kind} block: {str(exc)[:80]}")
    return blocks, media, notes


def write_lesson(outline: CourseOutline, lesson: OutlineLesson, client: ModelClient, pages: dict[str, str],
                 dt: DeepTutor | None = None, kb: str | None = None, quiz_items: int | None = None,
                 plan: "LessonMedia | None" = None, hint: str | None = None, dt_quiz: Any = None) -> LessonDraft:
    """`plan`: media this lesson may carry (mediaplan.py). `hint`: a refine instruction (what to fix or avoid).
    `dt_quiz`: a Future of dt.quiz(...) started while the lesson was still being written."""
    band = outline.age_band
    rules = AGE_RULES[band]
    source = "\n\n".join(f"[{r}]\n{pages[r]}" for r in lesson.source_pages if r in pages)
    grounded = lesson.grounded and bool(source)
    system = (LESSON_SYSTEM.replace("{lang}", lang_name(outline.language)).replace("{band_label}", rules["label"])
              .replace("{band_spec}", BAND_SPEC[band]).replace("{grounding}", GROUNDED if grounded else UNGROUNDED)
              .replace("{max_blocks}", str(rules["max_blocks"])).replace("{max_chars}", str(rules["max_text_chars"])))
    user = (f"COURSE: {outline.title} ({outline.subject})\nLESSON: {lesson.title}\nSummary: {lesson.summary}\n"
            f"Key ideas: {'; '.join(lesson.key_ideas)}\n\n"
            + (f"SOURCE:\n{source[:14000]}" if grounded else "SOURCE: (none)"))
    data = ask_json(client, system, user, max_tokens=7000, temperature=0.4, retries=3)
    blocks, media, notes = blocks_from_json(data, course_id=outline.course_id, lesson_id=lesson.id, age_band=band,
                                            language=outline.language)
    if not blocks:
        raise ValueError(f"lesson {lesson.id}: the model produced no usable blocks")
    reading = "\n\n".join(b.md for b in blocks if isinstance(b, (TextBlock, CalloutBlock))) or source
    ctx = LessonContext(lesson_id=lesson.id, title=lesson.title, summary=lesson.summary, key_ideas=lesson.key_ideas,
                        reading=(source + "\n\n" + reading) if grounded else reading, course_id=outline.course_id,
                        age_band=band, language=outline.language, grounded=grounded, subject=outline.subject)
    quiz = make_quiz(ctx, client, dt=dt, kb=kb, n=quiz_items, prefetched=dt_quiz)
    notes += quiz.notes
    media += quiz.media
    if quiz.items:
        blocks.append(QuizBlock(id=f"{lesson.id}-b{len(blocks) + 1}", title="Kiểm tra" if outline.language == "vi"
                                else "Check", items=quiz.items))
    else:
        notes.append("no quiz items could be made")
    if not grounded:
        notes.append("written from general knowledge (not covered by the source pages)")
    return LessonDraft(lesson=Lesson(id=lesson.id, title=lesson.title, est_minutes=lesson.est_minutes,
                                     summary=lesson.summary or None, key_ideas=lesson.key_ideas, blocks=blocks),
                       media=media, notes=notes, grounded=grounded, source_text=source)


__all__ = ["LessonDraft", "write_lesson", "blocks_from_json", "ImageBlock"]
