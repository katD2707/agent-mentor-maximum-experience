"""Chapter recap ("Nghe tóm tắt"): a 3-5 minute spoken summary per chapter, written from the lessons and read by the TTS voice.

    script = write_recap(outline, chapter, drafts, client)       list of short paragraphs
    req = recap_request(outline, chapter.id, script)             MediaRequest kind "recap" (id "recap-<chapter id>")
"""

from __future__ import annotations

import re

from mentor_course_builder.contracts import MediaRequest
from mentor_course_builder.gen import AGE_RULES, ask_json, lang_name
from mentor_course_builder.lessons import LessonDraft
from mentor_course_builder.llm import ModelClient
from mentor_course_builder.outline import CourseOutline, OutlineChapter

WORDS_PER_MIN = {"vi": 170, "en": 150}
MIN_S, MAX_S = 180, 300

RECAP_SYSTEM = """You write the spoken recap of ONE chapter of a course: a person listens to it (3 to 5 minutes, about
{words} words) to revise before a test. Language: {lang}. Level: {band}.
Reply with ONE JSON object {"script": [paragraph, ...]}: 6-10 short paragraphs of 2-4 plain sentences each, in the order of
the lessons, one idea per sentence, spoken style (no bullet points, no headings, no tables, no symbols the voice cannot say;
write a formula in words). Open with what the chapter is about in one sentence, go lesson by lesson with the key ideas and one
tiny example where it helps, finish with the three things to remember.
Use ONLY what the lessons below say. No filler openers, no "let's dive in"."""


def estimate_seconds(script: list[str], lang: str) -> float:
    words = sum(len(re.findall(r"\S+", p)) for p in script)
    return words / WORDS_PER_MIN.get(lang, 150) * 60


def recap_source(chapter: OutlineChapter, drafts: dict[str, LessonDraft]) -> str:
    from mentor_schemas.course import CalloutBlock, TextBlock

    parts = []
    for ol in chapter.lessons:
        d = drafts.get(ol.id)
        if d is None:
            continue
        body = " ".join(b.md for b in d.lesson.blocks if isinstance(b, (TextBlock, CalloutBlock)))
        parts.append(f"LESSON: {ol.title}\nKey ideas: {'; '.join(ol.key_ideas)}\n{body[:2500]}")
    return "\n\n".join(parts)


def write_recap(outline: CourseOutline, chapter: OutlineChapter, drafts: dict[str, LessonDraft], client: ModelClient
                ) -> list[str]:
    """Paragraphs for the chapter, or [] when none of its lessons was written. Too short or too long scripts are asked again once."""
    src = recap_source(chapter, drafts)
    if not src:
        return []
    mid = (MIN_S + MAX_S) // 2
    system = (RECAP_SYSTEM.replace("{words}", str(int(mid / 60 * WORDS_PER_MIN.get(outline.language, 150))))
              .replace("{lang}", lang_name(outline.language)).replace("{band}", AGE_RULES[outline.age_band]["label"]))
    user = f"CHAPTER: {chapter.title}\n\n{src}"
    script: list[str] = []
    for attempt in range(2):
        data = ask_json(client, system, user + (f"\n\nYour previous script was {int(estimate_seconds(script, outline.language))} "
                                                f"seconds long; it must be {MIN_S}-{MAX_S} seconds." if script else ""),
                        max_tokens=9000, temperature=0.4, retries=2)
        script = [str(p).strip() for p in data.get("script") or [] if str(p).strip()]
        if script and MIN_S * 0.8 <= estimate_seconds(script, outline.language) <= MAX_S * 1.2:
            break
    return script


def recap_request(outline: CourseOutline, chapter_id: str, script: list[str]) -> MediaRequest:
    return MediaRequest(id=f"recap-{chapter_id}", kind="recap", course_id=outline.course_id, age_band=outline.age_band,
                        language=outline.language, spec={"script": script})


def write_recaps(outline: CourseOutline, drafts: list[LessonDraft], client: ModelClient, log_fn=lambda s: None
                 ) -> dict[str, list[str]]:
    by_id = {d.lesson.id: d for d in drafts}
    out: dict[str, list[str]] = {}
    for ch in outline.chapters:
        try:
            script = write_recap(outline, ch, by_id, client)
        except Exception as exc:  # noqa: BLE001 - a recap is a bonus, never a reason to fail the build
            log_fn(f"recap {ch.id}: {type(exc).__name__}: {str(exc)[:100]}")
            continue
        if script:
            out[ch.id] = script
    return out


__all__ = ["write_recap", "write_recaps", "recap_request", "estimate_seconds"]
