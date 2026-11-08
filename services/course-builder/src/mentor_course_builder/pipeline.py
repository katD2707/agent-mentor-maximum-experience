"""Content stage end to end: lessons (+ DeepTutor knowledge base and quiz) -> humanize -> verify -> assemble."""

from __future__ import annotations

import json
import logging
import re
import tempfile
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from mentor_schemas.course import CalloutBlock, QuizBlock, TextBlock

from mentor_course_builder import humanize, verify
from mentor_course_builder.assemble import Assembled, assemble
from mentor_course_builder.contracts import MediaResult
from mentor_course_builder.deeptutor import DeepTutor
from mentor_course_builder.gen import AGE_RULES, slugify, source_pages
from mentor_course_builder.intake import IntakeResult
from mentor_course_builder.lessons import LessonDraft, write_lesson
from mentor_course_builder.llm import ModelClient
from mentor_course_builder.outline import CourseOutline
from mentor_course_builder.quiz import LessonContext, dt_choice_count

log = logging.getLogger("mentor_course_builder")


@dataclass
class LessonReport:
    lesson_id: str
    seconds: float = 0.0
    lint_before: dict[str, int] = field(default_factory=dict)
    lint_after: dict[str, int] = field(default_factory=dict)
    humanize_rejected: dict[str, str] = field(default_factory=dict)
    verify: str = ""
    notes: list[str] = field(default_factory=list)
    error: str | None = None


def humanize_draft(draft: LessonDraft, ctx: LessonContext, client: ModelClient) -> LessonReport:
    """Rewrite text/callout md and video narration in place; report lint hits before/after."""
    rep = LessonReport(draft.lesson.id)
    texts: dict[str, str] = {}
    for b in draft.lesson.blocks:
        if isinstance(b, (TextBlock, CalloutBlock)):
            texts[b.id] = b.md
    narr = {m.id: m for m in draft.media if m.kind == "video"}
    for rid, m in narr.items():
        for i, sc in enumerate(m.spec["scenes"]):
            texts[f"{rid}.n{i}"] = sc["narration"]
    rep.lint_before = humanize.lint_count(texts.values())
    new, rep.humanize_rejected = humanize.humanize_texts(texts, client, language=ctx.language,
                                                         age_band_label=AGE_RULES[ctx.age_band]["label"])
    for idx, b in enumerate(draft.lesson.blocks):
        if b.id in new and isinstance(b, (TextBlock, CalloutBlock)) and new[b.id] != b.md:
            draft.lesson.blocks[idx] = b.model_copy(update={"md": new[b.id]})
    for rid, m in narr.items():
        for i, sc in enumerate(m.spec["scenes"]):
            sc["narration"] = new.get(f"{rid}.n{i}", sc["narration"])
    sync_tts(draft)
    final = {b.id: b.md for b in draft.lesson.blocks if isinstance(b, (TextBlock, CalloutBlock))}
    rep.lint_after = humanize.lint_count(list(final.values()) + [sc["narration"] for m in narr.values()
                                                                for sc in m.spec["scenes"]])
    return rep


def sync_tts(draft: LessonDraft) -> list[str]:
    """tts requests carry the text: keep them equal to the (rewritten) block. Returns ids whose text changed."""
    final = {b.id: b.md for b in draft.lesson.blocks if isinstance(b, (TextBlock, CalloutBlock))}
    changed = []
    for m in draft.media:
        if m.kind == "tts" and m.id in final:
            title = next((b.title for b in draft.lesson.blocks if b.id == m.id and isinstance(b, CalloutBlock)), None)
            text = (title + ". " if title else "") + final[m.id]
            if m.spec.get("text") != text:
                m.spec["text"] = text
                changed.append(m.id)
    return changed


def _kb_files(pages: dict[str, str], outline: CourseOutline, tmp: Path) -> list[Path]:
    files = []
    for ref, text in pages.items():
        f = tmp / f"{slugify(ref, 'page', 50)}.md"
        f.write_text(f"# {outline.title}: {ref}\n\n{text}\n", encoding="utf-8")
        files.append(f)
    return files


@dataclass
class BuildResult:
    assembled: Assembled
    drafts: list[LessonDraft]
    reports: list[LessonReport]
    media_requests: list
    notes: list[str]
    writer: "CourseWriter | None" = None  # kept so the refine gate can rewrite a lesson with the same setup


def lesson_context(outline: CourseOutline, ol, draft: LessonDraft) -> LessonContext:
    return LessonContext(lesson_id=ol.id, title=ol.title, summary=ol.summary, key_ideas=ol.key_ideas,
                         reading=draft.source_text or "\n\n".join(
                             b.md for b in draft.lesson.blocks if isinstance(b, (TextBlock, CalloutBlock))),
                         course_id=outline.course_id, age_band=outline.age_band, language=outline.language,
                         grounded=draft.grounded, subject=outline.subject)


_WORD = re.compile(r"[\wÀ-ỹ]+")


def assign_skills(outline: CourseOutline, drafts: list[LessonDraft], path: dict) -> int:
    """Tag quiz items with the DeepTutor mastery-path knowledge points of their lesson (best word overlap with the
    lesson's title and key ideas, at most two), so practice and mastery can follow the same skills. Returns tagged items."""
    kps = [(kp.get("name", ""), mod.get("name", "")) for mod in path.get("modules") or []
           for kp in mod.get("knowledge_points") or [] if kp.get("name")]
    if not kps:
        return 0
    by_id = {ol.id: ol for ol in outline.lessons()}
    n = 0
    for d in drafts:
        ol = by_id.get(d.lesson.id)
        if ol is None:
            continue
        words = {w.lower() for w in _WORD.findall(" ".join([ol.title, *ol.key_ideas])) if len(w) > 2}
        scored = sorted(((len(words & {w.lower() for w in _WORD.findall(name)}), name) for name, _ in kps), reverse=True)
        best = scored[0][0]  # only the knowledge points that match as well as the best one (at most two)
        picks = [slugify(name, "skill", 48) for score, name in scored[:2] if score > 0 and score == best]
        if not picks:
            continue
        for bi, b in enumerate(d.lesson.blocks):
            if isinstance(b, QuizBlock):
                d.lesson.blocks[bi] = b.model_copy(update={"items": [q.model_copy(update={"skill_ids": picks})
                                                                     for q in b.items]})
                n += len(b.items)
    return n


class CourseWriter:
    """Everything needed to (re)write one lesson: the pages, the DeepTutor knowledge base, the media plan.

    DeepTutor is the slow part of a quiz (a `uvx` process of 20-60 s per call), so it never waits for the lesson: the
    knowledge base is built in the background while the first lessons are written, and each lesson's DeepTutor quiz is
    started the moment the knowledge base is ready, in a pool next to the lesson workers. `write` collects it when the
    lesson text is done. The mastery path (DeepTutor `mastery_path`) runs last in the same pool and only tags quiz items
    with skill ids.
    """

    def __init__(self, intake: IntakeResult, outline: CourseOutline, client: ModelClient, *, dt: DeepTutor | None = None,
                 quiz_items: int | None = None, plan: dict | None = None, log_fn: Callable[[str], None] = lambda s: None,
                 on_lesson: Callable[[str, str], None] = lambda i, st: None) -> None:
        self.intake, self.outline, self.client = intake, outline, client
        self.pages = dict(source_pages(intake))
        self.quiz_items, self.plan, self.log_fn, self.on_lesson = quiz_items, plan, log_fn, on_lesson
        self.notes: list[str] = []
        usable = dt is not None and dt.available() and self.pages and any(ls.grounded for ls in outline.lessons())
        self.dt = dt if usable else None
        self.kb = f"{outline.course_id[:24]}-{int(time.time()) % 100000}" if self.dt else None
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mcb-dt") if self.dt else None
        self._kb_future: Future | None = self._pool.submit(self._make_kb) if self._pool else None
        self._quiz: dict[str, Future] = {}
        self.mastery: Future | None = None

    def _make_kb(self) -> float:
        assert self.dt is not None and self.kb is not None
        with tempfile.TemporaryDirectory(prefix="mcb-kb-") as tmp:
            return self.dt.create_kb(self.kb, _kb_files(self.pages, self.outline, Path(tmp)))

    def start_dt(self, only: list[str] | None = None) -> None:
        """Queue the DeepTutor quiz of every grounded lesson (and the mastery path) behind the knowledge base."""
        if not self._pool or self.dt is None or self._kb_future is None:
            return
        dt, kb, ready, lang = self.dt, self.kb, self._kb_future, self.outline.language

        def quiz(title: str, n: int):
            ready.result()  # raises when the knowledge base failed: the lesson then falls back to its own prompts
            return dt.quiz(title, kb, n=n, language=lang)

        for ol in (x for x in self.outline.lessons() if not only or x.id in only):
            grounded = ol.grounded and any(r in self.pages for r in ol.source_pages)
            n = dt_choice_count(self.outline.age_band, self.quiz_items, grounded)
            if n:
                self._quiz[ol.id] = self._pool.submit(quiz, ol.title, n)

        def mastery():
            ready.result()
            return dt.mastery_path(kb, self.outline.title, lang)

        self.mastery = self._pool.submit(mastery)

    def finish_dt(self, drafts: list[LessonDraft], wait_s: float = 90.0) -> None:
        if self._kb_future is None:
            return
        try:
            self.notes.append(f"deeptutor knowledge base '{self.kb}' built in {self._kb_future.result(timeout=5):.0f}s")
        except Exception as exc:  # noqa: BLE001
            self.notes.append(f"deeptutor unavailable, own prompts used: {str(exc)[:150]}")
        if self.mastery is not None:
            try:
                path = self.mastery.result(timeout=wait_s)
                tagged = assign_skills(self.outline, drafts, path)
                self.notes.append(f"deeptutor mastery path: {len(path.get('modules') or [])} modules, "
                                  f"{tagged} quiz items tagged with skills")
            except Exception as exc:  # noqa: BLE001 - skills are a bonus, never a reason to fail the build
                self.notes.append(f"deeptutor mastery path skipped: {type(exc).__name__}: {str(exc)[:100]}")
        if self._pool:
            self._pool.shutdown(wait=False, cancel_futures=True)

    def _try(self, ol, hint: str | None) -> tuple[LessonDraft | None, LessonReport]:
        t = time.time()
        rep = LessonReport(ol.id)
        self.on_lesson(ol.id, "writing")
        try:
            draft = write_lesson(self.outline, ol, self.client, self.pages, dt=self.dt, kb=self.kb,
                                 quiz_items=self.quiz_items, plan=(self.plan or {}).get(ol.id), hint=hint,
                                 dt_quiz=None if hint else self._quiz.get(ol.id))
            ctx = lesson_context(self.outline, ol, draft)
            rep = humanize_draft(draft, ctx, self.client)
            vr = verify.verify_and_repair(draft, ctx, self.client)
            rep.verify = vr.summary()
            rep.notes = draft.notes + [f"katex: {p}" for p in vr.katex] + [f"length: {p}" for p in vr.lengths] + \
                [f"quiz {v.item_id}: {v.reason}" for v in vr.failed]
            rep.seconds = time.time() - t
            self.log_fn(f"{ol.id}: done in {rep.seconds:.0f}s ({rep.verify})")
            return draft, rep
        except Exception as exc:  # noqa: BLE001 - one bad lesson must not stop the course
            rep.error = f"{type(exc).__name__}: {str(exc)[:200]}"
            rep.seconds = time.time() - t
            self.log_fn(f"{ol.id}: FAILED {rep.error}")
            return None, rep

    def write(self, ol, hint: str | None = None) -> tuple[LessonDraft | None, LessonReport]:
        """Model gateways drop streams and return broken JSON now and then: a lesson gets one more try before it is dropped."""
        draft, rep = self._try(ol, hint)
        if draft is None:
            self.log_fn(f"{ol.id}: trying once more")
            draft, rep = self._try(ol, hint)
        return draft, rep


def build_course(intake: IntakeResult, outline: CourseOutline, client: ModelClient, *,
                 dt: DeepTutor | None = None, results: dict[str, MediaResult] | None = None,
                 only_lessons: list[str] | None = None, quiz_items: int | None = None, workers: int = 2,
                 teacher_name: str = "Giáo viên", log_fn: Callable[[str], None] = lambda s: None,
                 on_lesson: Callable[[str, str], None] = lambda lesson_id, state: None,
                 on_draft: Callable[[LessonDraft], None] | None = None, plan: dict | None = None) -> BuildResult:
    """Write every lesson (or `only_lessons`), humanize, verify, assemble. Lesson failures are reported, not fatal.
    `on_draft(draft)` runs in the worker the moment a lesson is final, so its media can render while later lessons are
    still being written. `plan` = mediaplan.plan_media(outline): what media each lesson may carry."""
    writer = CourseWriter(intake, outline, client, dt=dt, quiz_items=quiz_items, plan=plan, log_fn=log_fn,
                          on_lesson=on_lesson)
    wanted = [ls for ls in outline.lessons() if not only_lessons or ls.id in only_lessons]
    writer.start_dt([ls.id for ls in wanted] if only_lessons else None)

    def one(ol) -> tuple[LessonDraft | None, LessonReport]:
        draft, rep = writer.write(ol)
        if draft is not None and on_draft is not None:
            on_draft(draft)
        return draft, rep

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        out = list(ex.map(one, wanted))
    drafts = [d for d, _ in out if d is not None]
    reports = [r for _, r in out]
    writer.finish_dt(drafts)
    sub = outline.model_copy(deep=True)
    if only_lessons:
        for ch in sub.chapters:
            ch.lessons = [ls for ls in ch.lessons if ls.id in only_lessons]
        sub.chapters = [ch for ch in sub.chapters if ch.lessons]
    asm = assemble(sub, drafts, results, teacher_name=teacher_name)
    asm.notes += [f"{d.lesson.id}: {n}" for d in drafts for n in d.notes if "general knowledge" in n]
    return BuildResult(asm, drafts, reports, [m for d in drafts for m in d.media], writer.notes, writer)


def save_build(res: BuildResult, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "media-requests.json").write_text(
        json.dumps([m.model_dump() for m in res.media_requests], ensure_ascii=False, indent=2), encoding="utf-8")
    rep = [r.__dict__ for r in res.reports]
    (out / "report.json").write_text(json.dumps({"notes": res.notes + res.assembled.notes, "lessons": rep},
                                                ensure_ascii=False, indent=2), encoding="utf-8")
