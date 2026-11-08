"""Verify-and-refine gate: a whole course must be clean before a teacher reviews it, and again before it is published.

Two layers:

1. `check_pack(...)`: static checks on an assembled pack (no model call, a second or two). The gateway runs the same
   function before `publish`, so a draft that was edited after the build cannot go out broken:
   every outline lesson present, a quiz in every lesson, pack validates, asset files exist with matching size and
   sha256, no empty or placeholder block, every formula parses in KaTeX (the library the app renders with), quiz keys
   consistent, no lesson that repeats its neighbour, no duplicate quiz question, and the humanize linter's tells.
2. `Refiner.run()`: the build-time loop. It adds the model-based check (an independent re-solve of every quiz item that the
   pipeline has not verified yet) and a repair for each problem: rewrite the missing lesson, regenerate the missing quiz,
   re-ask the model with the exact KaTeX error, regenerate a quiz item whose key is wrong, re-render media that failed,
   a second humanize pass that names the tells still found, a rewrite of a lesson that repeats the previous one. It
   loops until clean or `max_rounds`; what is still wrong is returned as plain words for the teacher (never dropped silently).

Severity: `hard` problems (a lesson or quiz missing, pack/asset/KaTeX/quiz-key errors, empty blocks) block publishing;
`soft` ones (media that could not be made and was left out, writing tells, repetition) are reported but do not.
"""

from __future__ import annotations

import hashlib
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from mentor_schemas.course import (AssetRef, CalloutBlock, CoursePack, ImageBlock, Lesson, QuizBlock, QuizItem, TextBlock,
                                   VideoBlock)

from mentor_course_builder import humanize, katex_check, verify
from mentor_course_builder.assemble import Assembled, assemble
from mentor_course_builder.contracts import MediaRequest, MediaResult
from mentor_course_builder.gen import AGE_RULES, ask_json, lang_name
from mentor_course_builder.lessons import LessonDraft
from mentor_course_builder.llm import ModelClient, ModelError
from mentor_course_builder.outline import CourseOutline
from mentor_course_builder.quiz import PENDING_SHA

log = logging.getLogger("mentor_course_builder")

HARD = {"lesson_missing", "quiz_missing", "lesson_empty", "pack_invalid", "asset_missing", "asset_hash", "block_empty",
        "block_placeholder", "katex", "quiz_key", "quiz_wrong"}

# plain words for the teacher: {code: (vi, en)}; {t} = lesson title, {d} = detail
WORDS: dict[str, tuple[str, str]] = {
    "lesson_missing": ("Bài «{t}» chưa soạn được.", "Lesson «{t}» could not be written."),
    "lesson_empty": ("Bài «{t}» chưa có phần đọc.", "Lesson «{t}» has no reading text."),
    "quiz_missing": ("Bài «{t}» chưa có câu hỏi kiểm tra.", "Lesson «{t}» has no quiz."),
    "pack_invalid": ("Khóa học chưa đúng định dạng ({d}).", "The course file is not valid ({d})."),
    "asset_missing": ("Bài «{t}» thiếu một tệp hình, video hoặc âm thanh ({d}).",
                      "Lesson «{t}» is missing a picture, video or audio file ({d})."),
    "asset_hash": ("Một tệp media ở bài «{t}» bị hỏng ({d}).", "A media file in lesson «{t}» is damaged ({d})."),
    "block_empty": ("Bài «{t}» có một đoạn trống.", "Lesson «{t}» has an empty block."),
    "block_placeholder": ("Bài «{t}» còn một đoạn chữ giữ chỗ chưa viết xong.", "Lesson «{t}» still has a placeholder block."),
    "katex": ("Một công thức ở bài «{t}» không hiển thị được ({d}).", "A formula in lesson «{t}» cannot be displayed ({d})."),
    "quiz_key": ("Một câu hỏi ở bài «{t}» có đáp án không khớp các lựa chọn ({d}).",
                 "A quiz question in lesson «{t}» has an answer key that does not match its choices ({d})."),
    "quiz_wrong": ("Một câu hỏi ở bài «{t}» có đáp án mình tự giải ra khác đáp án ghi sẵn. Bạn xem lại giúp mình.",
                   "In lesson «{t}» a question's answer differs from what I got solving it myself. Please check it."),
    "media_missing": ("Bài «{t}»: {d} không tạo được nên mình bỏ qua.", "Lesson «{t}»: {d} could not be made, so I left it out."),
    "lint": ("Bài «{t}» vẫn còn vài câu nghe như văn máy.", "Lesson «{t}» still has a few phrases that sound machine-written."),
    "repeat": ("Bài «{t}» lặp lại nhiều ý của bài trước.", "Lesson «{t}» repeats a lot of the previous lesson."),
    "quiz_duplicate": ("Bài «{t}» có câu hỏi trùng với câu khác trong khóa.", "Lesson «{t}» has a question that repeats another one."),
    "block_removed": ("Bài «{t}»: mình bỏ một phần lỗi ({d}).", "Lesson «{t}»: I removed a faulty part ({d})."),
    "quiz_dropped": ("Bài «{t}»: mình bỏ một câu hỏi vì không sửa được đáp án.",
                     "Lesson «{t}»: I removed a question whose answer I could not fix."),
}
MAX_TRIES = {"lint": 1, "repeat": 1, "lesson_missing": 1, "quiz_duplicate": 1, "media_missing": 1}
PLACEHOLDER = re.compile(r"lorem ipsum|\bTODO\b|\bTBD\b|placeholder|\[\s*(?:text|nội dung|điền)[^\]]*\]|\.{4,}|…{2,}|^\W*$", re.I)


@dataclass
class Issue:
    code: str
    lesson_id: str | None = None
    block_id: str | None = None
    detail: str = ""
    severity: str = ""
    fixed: bool = False
    item_hash: str | None = None  # quiz_wrong: the item as judged, so an edited item is not blocked by an old verdict
    vi: str = ""
    en: str = ""

    def __post_init__(self) -> None:
        self.severity = self.severity or ("hard" if self.code in HARD else "soft")

    def key(self) -> tuple:
        return (self.code, self.lesson_id, self.block_id or "")

    def say(self, titles: dict[str, str]) -> "Issue":
        vi, en = WORDS.get(self.code, ("{t}: {d}", "{t}: {d}"))
        t = titles.get(self.lesson_id or "", self.lesson_id or "khóa học")
        self.vi, self.en = vi.format(t=t, d=self.detail[:90]), en.format(t=t, d=self.detail[:90])
        return self

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if not self.item_hash:
            d.pop("item_hash")
        return d


# ---------------------------------------------------------------- static checks
def _lessons(pack: CoursePack) -> list[Lesson]:
    return [ls for ch in pack.chapters for ls in ch.lessons]


def _item_texts(q: QuizItem) -> str:
    parts = [q.stem, q.explanation, q.hint or "", *[o.text or "" for o in q.options], *[s.text for s in q.statements],
             *q.option_feedback.values()]
    return "\n".join(p for p in parts if p)


def quiz_key_problem(q: QuizItem) -> str | None:
    """Consistency of the answer key with the item (no model): None when fine."""
    k = q.answer_key
    if not q.stem.strip():
        return "empty question"
    if q.type in ("SINGLE_CHOICE", "PICTURE_CHOICE"):
        ids = [o.id for o in q.options]
        if k.get("correct_option_id") not in ids:
            return "the right answer is not one of the choices"
        texts = [(o.text or "").strip().lower() for o in q.options if o.text]
        if len(texts) != len(set(texts)):
            return "two choices have the same text"
    elif q.type == "TRUE_FALSE_GROUP":
        if set((k.get("statements") or {}).keys()) != {s.id for s in q.statements} or not q.statements:
            return "the true/false key does not match the statements"
    elif q.type == "SHORT_ANSWER":
        acc = [str(a) for a in k.get("accepted") or []]
        if not acc:
            return "no accepted answer"
        nums = [verify.parse_number(a) for a in acc]
        if all(n is not None for n in nums):
            tol = float(k.get("tolerance") or 0.01)
            if any(not verify.numbers_agree(nums[0], n, tol) for n in nums[1:]):  # type: ignore[arg-type]
                return f"accepted spellings differ numerically: {acc}"
    elif q.type == "TAP_COUNT":
        total = q.tap.total if q.tap else 0
        if not q.tap or not 0 <= int(k.get("count", -1)) <= total:
            return "the count is outside the picture"
    return None


def _shingles(text: str, n: int = 4) -> set[str]:
    w = re.findall(r"[\wÀ-ỹ]+", re.sub(r"\$[^$]*\$", " ", text.lower()))
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}


def _lesson_text(ls: Lesson) -> str:
    return "\n".join(b.md for b in ls.blocks if isinstance(b, (TextBlock, CalloutBlock)))


def repeat_ratio(a: Lesson, b: Lesson) -> float:
    """Share of the shorter lesson's 4-word phrases that also occur in the other one."""
    sa, sb = _shingles(_lesson_text(a)), _shingles(_lesson_text(b))
    if min(len(sa), len(sb)) < 12:
        return 0.0
    return len(sa & sb) / min(len(sa), len(sb))


def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", re.sub(r"\$[^$]*\$", " ", s.lower())).strip()


Resolve = Callable[[AssetRef], Path | None]


def check_pack(pack: CoursePack, resolve: Resolve, outline: CourseOutline | None = None, *,
               repeat_threshold: float = 0.45) -> list[Issue]:
    """Every static check. `resolve(ref)` -> the local file of an asset (None = missing)."""
    out: list[Issue] = []
    try:
        CoursePack.model_validate(pack.model_dump(mode="json"))
    except Exception as exc:  # noqa: BLE001
        out.append(Issue("pack_invalid", detail=str(exc).splitlines()[0][:120]))
    lessons = _lessons(pack)
    have = {ls.id for ls in lessons}
    if outline is not None:
        out += [Issue("lesson_missing", ol.id) for ol in outline.lessons() if ol.id not in have]
    for ls in lessons:
        if not any(isinstance(b, QuizBlock) and b.items for b in ls.blocks):
            out.append(Issue("quiz_missing", ls.id))
        if not any(isinstance(b, (TextBlock, CalloutBlock)) and b.md.strip() for b in ls.blocks):
            out.append(Issue("lesson_empty", ls.id))
    # empty / placeholder blocks and asset files
    for ls in lessons:
        for b in ls.blocks:
            if isinstance(b, (TextBlock, CalloutBlock)):
                if not b.md.strip():
                    out.append(Issue("block_empty", ls.id, b.id))
                elif PLACEHOLDER.search(b.md):
                    out.append(Issue("block_placeholder", ls.id, b.id, PLACEHOLDER.search(b.md).group(0)[:30]))  # type: ignore[union-attr]
            elif isinstance(b, ImageBlock) and not b.alt.strip():
                out.append(Issue("block_empty", ls.id, b.id, "picture without description"))
            elif isinstance(b, QuizBlock):
                if not b.items:
                    out.append(Issue("block_empty", ls.id, b.id, "quiz without items"))
                for q in b.items:
                    if PLACEHOLDER.search(q.stem):
                        out.append(Issue("block_placeholder", ls.id, q.id, "question"))
        refs: list[tuple[str, AssetRef]] = []
        for b in ls.blocks:
            refs += [(getattr(b, "id", ""), r) for r in _block_assets(b)]
        for bid, ref in refs:
            if ref.sha256 == PENDING_SHA or ref.path.startswith("pending/"):
                out.append(Issue("block_placeholder", ls.id, bid, f"{ref.path} was never made"))
                continue
            f = resolve(ref)
            if f is None or not Path(f).is_file():
                out.append(Issue("asset_missing", ls.id, bid, ref.path))
            elif Path(f).stat().st_size != ref.bytes or _sha(Path(f)) != ref.sha256:
                out.append(Issue("asset_hash", ls.id, bid, ref.path))
    # KaTeX over every text, one node process
    texts: dict[str, str] = {}
    owner: dict[str, tuple[str, str]] = {}
    for ls in lessons:
        for b in ls.blocks:
            if isinstance(b, (TextBlock, CalloutBlock)):
                texts[b.id], owner[b.id] = b.md, (ls.id, b.id)
            elif isinstance(b, QuizBlock):
                for q in b.items:
                    texts[q.id], owner[q.id] = _item_texts(q), (ls.id, q.id)
    for tid, probs in katex_check.check_texts(texts).items():
        out.append(Issue("katex", owner[tid][0], owner[tid][1], probs[0][:110]))
    # quiz keys and duplicates
    seen: dict[str, str] = {}
    for ls in lessons:
        for b in ls.blocks:
            if not isinstance(b, QuizBlock):
                continue
            for q in b.items:
                p = quiz_key_problem(q)
                if p:
                    out.append(Issue("quiz_key", ls.id, q.id, p))
                n = _norm(q.stem)
                if n and n in seen:
                    out.append(Issue("quiz_duplicate", ls.id, q.id, f"same as {seen[n]}"))
                seen.setdefault(n, q.id)
    # neighbours
    for a, b in zip(lessons, lessons[1:]):
        r = repeat_ratio(a, b)
        if r > repeat_threshold:
            out.append(Issue("repeat", b.id, None, f"{r:.0%} of its phrases are in {a.id}"))
    # writing tells
    for ls in lessons:
        hits: dict[str, list[str]] = {}
        for b in ls.blocks:
            if isinstance(b, (TextBlock, CalloutBlock)):
                got = [f"{h.rule}: {h.text[:40]}" for h in humanize.lint(b.md)]
                if got:
                    hits[b.id] = got
        if hits:
            out.append(Issue("lint", ls.id, next(iter(hits)), "; ".join(f"{k} {v[0]}" for k, v in list(hits.items())[:3])))
    return out


def _block_assets(b) -> list[AssetRef]:
    refs: list[AssetRef] = []
    if isinstance(b, (TextBlock, CalloutBlock)):
        refs += [b.audio] if b.audio else []
    elif isinstance(b, ImageBlock):
        refs += [r for r in (b.image, b.audio) if r]
    elif isinstance(b, VideoBlock):
        refs += [r for r in (b.video, b.poster, b.captions) if r]
    elif isinstance(b, QuizBlock):
        for q in b.items:
            refs += [r for r in (q.stem_audio, q.stem_image) if r]
            for o in q.options:
                refs += [r for r in (o.image, o.audio) if r]
            if q.tap:
                refs.append(q.tap.image)
    return refs


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def titles_of(pack: CoursePack | None, outline: CourseOutline | None) -> dict[str, str]:
    t = {ls.id: ls.title for ls in (_lessons(pack) if pack else [])}
    t.update({ol.id: ol.title for ol in (outline.lessons() if outline else [])})
    return t


def publish_blockers(pack: CoursePack, resolve: Resolve, outline: CourseOutline | None = None,
                     stored: list[dict] | None = None) -> list[Issue]:
    """Hard problems that must stop `publish`: the live static checks plus the build's independent-solve verdicts that
    still apply (the item has not been edited since: same hash)."""
    live = [i for i in check_pack(pack, resolve, outline) if i.severity == "hard"]
    hashes = {verify.item_hash(q): (ls.id, q.id) for ls in _lessons(pack) for b in ls.blocks if isinstance(b, QuizBlock)
              for q in b.items}
    for row in stored or []:
        h = row.get("item_hash")
        if row.get("code") == "quiz_wrong" and h in hashes and not row.get("fixed"):
            live.append(Issue("quiz_wrong", hashes[h][0], hashes[h][1], row.get("detail", ""), item_hash=h))
    titles = titles_of(pack, outline)
    return [i.say(titles) for i in live]


def check_store_version(store, course_id: str, version: int, outline: CourseOutline | None = None,
                        stored: list[dict] | None = None) -> list[Issue]:
    """`publish_blockers` for a version in a ContentStore (what the gateway calls before publishing)."""
    pack = store.load_pack(course_id, version)

    def resolve(ref: AssetRef) -> Path | None:
        try:
            return store.asset_path(course_id, version, ref.path)
        except Exception:  # noqa: BLE001
            return None

    return publish_blockers(pack, resolve, outline, stored)


# ---------------------------------------------------------------- repair prompts
FIX_MATH_SYSTEM = """You repair LaTeX in a school text so that KaTeX can display it. Language: {lang}.
You receive JSON {"<field>": "<text with $...$ / $$...$$ formulas>"} and the KaTeX errors. Reply with the same JSON keys.
Change ONLY what the error needs: close braces, fix commands, use $...$ (never \\( \\)), escape a currency dollar as \\$.
Keep every word, number and the meaning exactly. If a field is fine, return it unchanged."""


def _numbers(s: str) -> list[str]:
    return sorted(re.findall(r"\d+(?:[.,]\d+)?", s))


# ---------------------------------------------------------------- the loop
@dataclass
class RefineResult:
    assembled: Assembled
    issues: list[Issue]  # still wrong after the last round
    fixed: list[Issue] = field(default_factory=list)
    rounds: int = 0
    engine: str = "regex"

    @property
    def blocked(self) -> bool:
        return any(i.severity == "hard" for i in self.issues)

    def report(self) -> dict[str, Any]:
        return {"rounds": self.rounds, "katex": self.engine, "blocked": self.blocked,
                "hard": [i.as_dict() for i in self.issues if i.severity == "hard"],
                "soft": [i.as_dict() for i in self.issues if i.severity != "hard"],
                "fixed": [i.as_dict() for i in self.fixed]}


class Refiner:
    """Check, repair, re-check. All side effects go through the injected callables, so tests drive it with fakes.

    write(ol, hint) -> (LessonDraft | None, report)   the pipeline's CourseWriter.write
    render(req)     -> MediaResult | None              media stage (None = failed); stores into `results` itself or not
    forget(req_id)                                     drop a stale media result (text changed)
    """

    def __init__(self, outline: CourseOutline, drafts: list[LessonDraft], results: dict[str, MediaResult],
                 client: ModelClient, *, write: Callable[[Any, str | None], tuple[LessonDraft | None, Any]],
                 render: Callable[[MediaRequest], MediaResult | None],
                 forget: Callable[[str], None] = lambda rid: None, kinds: set[str] | None = None, max_rounds: int = 3,
                 teacher_id: str = "teacher", teacher_name: str = "Giáo viên", workers: int = 3,
                 log_fn: Callable[[str], None] = lambda s: None) -> None:
        self.outline, self.client, self.results = outline, client, results
        self.drafts = {d.lesson.id: d for d in drafts}
        self.write, self.render, self.forget = write, render, forget
        self.kinds = kinds or {"tts", "video", "diagram", "illustration", "picture", "cover"}
        self.max_rounds, self.teacher_id, self.teacher_name, self.workers, self.log_fn = max_rounds, teacher_id, teacher_name, workers, log_fn
        self.tries: dict[tuple, int] = {}
        self.fixed: list[Issue] = []
        self.removed: list[Issue] = []
        self.engine = "katex" if katex_check.find_katex() else "regex"

    # ---- assembling and checking
    def ordered(self) -> list[LessonDraft]:
        return [self.drafts[ol.id] for ol in self.outline.lessons() if ol.id in self.drafts]

    def assemble(self) -> Assembled:
        return assemble(self.outline, self.ordered(), self.results, teacher_id=self.teacher_id, teacher_name=self.teacher_name)

    def media_issues(self, asm: Assembled | None = None) -> list[Issue]:
        out = []
        for d in self.ordered():
            for m in d.media:
                if m.kind not in self.kinds:
                    continue
                r = self.results.get(m.id)
                if r is None or not r.files or not all(Path(f.file).is_file() for f in r.files):
                    what = {"tts": "giọng đọc", "video": "video", "diagram": "sơ đồ", "illustration": "hình minh họa",
                            "picture": "hình"}.get(m.kind, m.kind)
                    out.append(Issue("media_missing", d.lesson.id, m.id, what))
        return out

    def solve_issues(self, asm: Assembled) -> list[Issue]:
        """Independent re-solve of every quiz item the pipeline did not already verify."""
        todo: list[tuple[str, QuizItem]] = []
        for ls in _lessons(asm.pack):
            d = self.drafts.get(ls.id)
            for b in ls.blocks:
                if isinstance(b, QuizBlock):
                    todo += [(ls.id, q) for q in b.items if d is None or verify.item_hash(q) not in d.verified]
        if not todo:
            return []
        verdicts = verify.check_items([q for _, q in todo], self.client, self.outline.language, self.workers)
        out = []
        for (lid, q), v in zip(todo, verdicts):
            if verify.solved(v):
                self.drafts[lid].verified.add(verify.item_hash(q)) if lid in self.drafts else None
            elif not v.ok:
                out.append(Issue("quiz_wrong", lid, q.id, v.reason, item_hash=verify.item_hash(q)))
        return out

    def check(self) -> tuple[Assembled | None, list[Issue]]:
        try:
            asm = self.assemble()
        except ValueError as exc:
            return None, [Issue("pack_invalid", detail=str(exc)[:120])]
        files = asm.assets
        issues = check_pack(asm.pack, lambda ref: files.get(ref.path), self.outline)
        issues += self.media_issues(asm)
        issues += self.solve_issues(asm)
        return asm, issues

    # ---- repairs
    def _ctx(self, d: LessonDraft):
        from mentor_course_builder.pipeline import lesson_context

        return lesson_context(self.outline, next(ol for ol in self.outline.lessons() if ol.id == d.lesson.id), d)

    def _render_all(self, reqs: list[MediaRequest]) -> None:
        todo = [r for r in reqs if r.kind in self.kinds]
        if not todo:
            return
        with ThreadPoolExecutor(max_workers=max(1, min(self.workers, len(todo)))) as ex:
            for r, res in zip(todo, ex.map(self.render, todo)):
                if res is not None:
                    self.results[r.id] = res

    def _stale(self, lid: str, rids: list[str]) -> None:
        """Read-aloud whose text changed: drop the old clip and let it be made again (a fresh try)."""
        for rid in rids:
            self.forget(rid)
            self.results.pop(rid, None)
            self.tries.pop(("media_missing", lid, rid), None)

    def _rewrite_lesson(self, lid: str, hint: str | None) -> bool:
        ol = next((x for x in self.outline.lessons() if x.id == lid), None)
        if ol is None:
            return False
        draft, _ = self.write(ol, hint)
        if draft is None:
            return False
        old = self.drafts.get(lid)
        for m in (old.media if old else []):
            self.forget(m.id)
            self.results.pop(m.id, None)
        self.drafts[lid] = draft
        self._render_all(draft.media)
        return True

    def _add_quiz(self, lid: str) -> bool:
        from mentor_course_builder import quiz as quiz_mod

        d = self.drafts.get(lid)
        if d is None:
            return False
        ctx = self._ctx(d)
        q = quiz_mod.make_quiz(ctx, self.client, dt=None)
        verdicts = verify.check_items(q.items, self.client, ctx.language, self.workers)
        items = [it for it, v in zip(q.items, verdicts) if v.ok]
        for it, v in zip(q.items, verdicts):
            if verify.solved(v):
                d.verified.add(verify.item_hash(it))
        if not items:
            return False
        keep = {it.id for it in items}
        new_media = [m for m in q.media if m.id.split(".")[0] in keep]
        d.lesson.blocks = [b for b in d.lesson.blocks if not isinstance(b, QuizBlock)]
        d.lesson.blocks.append(QuizBlock(id=f"{lid}-b{len(d.lesson.blocks) + 1}", title="Kiểm tra" if self.outline.language == "vi"
                                         else "Check", items=items))
        d.media = [m for m in d.media if not m.id.startswith(f"{lid}-q")] + new_media
        self._render_all(new_media)
        return True

    def _fix_math(self, lid: str, bid: str, detail: str) -> bool:
        d = self.drafts.get(lid)
        if d is None:
            return False
        block_i = next((i for i, b in enumerate(d.lesson.blocks) if getattr(b, "id", None) == bid), None)
        fields: dict[str, str] = {}
        quiz_item = None
        if block_i is not None and isinstance(d.lesson.blocks[block_i], (TextBlock, CalloutBlock)):
            fields = {"md": d.lesson.blocks[block_i].md}  # type: ignore[union-attr]
        else:
            for qi, b in enumerate(d.lesson.blocks):
                if isinstance(b, QuizBlock):
                    for q in b.items:
                        if q.id == bid:
                            quiz_item, block_i = q, qi
            if quiz_item is None:
                return False
            fields = {"stem": quiz_item.stem, "explanation": quiz_item.explanation,
                      **{f"opt_{o.id}": o.text or "" for o in quiz_item.options},
                      **{f"stmt_{s.id}": s.text for s in quiz_item.statements}}
        system = FIX_MATH_SYSTEM.replace("{lang}", lang_name(self.outline.language))
        import json
        from mentor_schemas import ModelAlias

        try:
            data = ask_json(self.client, system, f"ERRORS: {detail}\n\n" + json.dumps(fields, ensure_ascii=False),
                            alias=ModelAlias.CHAT, max_tokens=3000, temperature=0.0)
        except ModelError:
            return False
        new = {k: str(data.get(k, v)) for k, v in fields.items()}
        if new == fields or any(_numbers(new[k]) != _numbers(fields[k]) for k in fields) or katex_check.check_texts(new):
            return False
        if quiz_item is None:
            b = d.lesson.blocks[block_i]
            d.lesson.blocks[block_i] = b.model_copy(update={"md": new["md"]})  # type: ignore[union-attr]
            from mentor_course_builder.pipeline import sync_tts

            self._stale(lid, sync_tts(d))
        else:
            q = quiz_item.model_copy(update={
                "stem": new["stem"], "explanation": new["explanation"],
                "options": [o.model_copy(update={"text": new.get(f"opt_{o.id}") or o.text}) for o in quiz_item.options],
                "statements": [s.model_copy(update={"text": new.get(f"stmt_{s.id}", s.text)}) for s in quiz_item.statements]})
            qb = d.lesson.blocks[block_i]
            d.lesson.blocks[block_i] = qb.model_copy(update={"items": [q if x.id == q.id else x for x in qb.items]})  # type: ignore[union-attr]
            d.verified.discard(verify.item_hash(quiz_item))
        return True

    def _replace_item(self, lid: str, qid: str, why: Issue) -> bool:
        d = self.drafts.get(lid)
        if d is None:
            return False
        for bi, b in enumerate(d.lesson.blocks):
            if not isinstance(b, QuizBlock) or not any(q.id == qid for q in b.items):
                continue
            item = next(q for q in b.items if q.id == qid)
            ctx = self._ctx(d)
            before = list(d.media)
            new = verify.regenerate_item(d, ctx, item, self.client)
            if new is not None:
                d.lesson.blocks[bi] = b.model_copy(update={"items": [new if q.id == qid else q for q in b.items]})
                d.verified.add(verify.item_hash(new))
                self._render_all([m for m in d.media if m not in before])
                return True
            # no clean replacement: remove it, and say so
            d.media = [m for m in d.media if not verify._owned(m, qid)]  # noqa: SLF001
            left = [q for q in b.items if q.id != qid]
            if left:
                d.lesson.blocks[bi] = b.model_copy(update={"items": left})
            else:
                d.lesson.blocks.remove(b)
            self.removed.append(Issue("quiz_dropped", lid, qid, why.detail))
            return True
        return False

    def _remove_block(self, lid: str, bid: str, detail: str) -> bool:
        d = self.drafts.get(lid)
        if d is None:
            return False
        n = len(d.lesson.blocks)
        d.lesson.blocks = [b for b in d.lesson.blocks if getattr(b, "id", None) != bid]
        d.media = [m for m in d.media if not verify._owned(m, bid)]  # noqa: SLF001
        if len(d.lesson.blocks) != n:
            self.removed.append(Issue("block_removed", lid, bid, detail))
            return True
        return False

    def _lint(self, lid: str) -> bool:
        d = self.drafts.get(lid)
        if d is None:
            return False
        texts, hints = {}, {}
        for b in d.lesson.blocks:
            if isinstance(b, (TextBlock, CalloutBlock)):
                hits = humanize.lint(b.md)
                if hits:
                    texts[b.id], hints[b.id] = b.md, [f"{h.rule} («{h.text[:40]}»)" for h in hits]
        if not texts:
            return False
        ctx = self._ctx(d)
        new, _ = humanize.humanize_texts(texts, self.client, language=ctx.language,
                                         age_band_label=AGE_RULES[ctx.age_band]["label"], hints=hints)
        changed = False
        for i, b in enumerate(d.lesson.blocks):
            if b.id in new and new[b.id] != getattr(b, "md", None):
                d.lesson.blocks[i] = b.model_copy(update={"md": new[b.id]})
                changed = True
        if changed:
            from mentor_course_builder.pipeline import sync_tts

            self._stale(lid, sync_tts(d))
        return changed

    def _repeat(self, lid: str, detail: str) -> bool:
        lessons = self.ordered()
        i = next((k for k, d in enumerate(lessons) if d.lesson.id == lid), 0)
        prev = lessons[i - 1] if i else None
        titles = f"«{prev.lesson.title}»" if prev else "the previous lesson"
        hint = (f"The lesson repeated {titles} ({detail}). Cover only what is NEW in this lesson, refer back in at most one "
                f"short sentence, and use different examples and different wording.")
        return self._rewrite_lesson(lid, hint)

    def _rerender(self, lid: str, rid: str) -> bool:
        d = self.drafts.get(lid)
        req = next((m for m in (d.media if d else []) if m.id == rid), None)
        if req is None:
            return False
        res = self.render(req)
        if res is not None:
            self.results[rid] = res
            return True
        return False

    def repair(self, issue: Issue) -> bool:
        c, lid, bid = issue.code, issue.lesson_id or "", issue.block_id or ""
        if c == "lesson_missing":
            return self._rewrite_lesson(lid, "the lesson did not come out; write it fully and keep the JSON short and valid")
        if c == "quiz_missing":
            return self._add_quiz(lid)
        if c == "katex":
            return self._fix_math(lid, bid, issue.detail)
        if c in ("quiz_key", "quiz_wrong", "quiz_duplicate"):
            return self._replace_item(lid, bid, issue)
        if c == "block_empty":
            return self._remove_block(lid, bid, "empty")
        if c == "block_placeholder":
            if self.tries.get(("ph", lid), 0) == 0:
                self.tries[("ph", lid)] = 1
                return self._rewrite_lesson(lid, f"block {bid} was left as a placeholder ({issue.detail}); write real content")
            return self._remove_block(lid, bid, "placeholder text")
        if c == "media_missing":
            return self._rerender(lid, bid)
        if c == "lint":
            return self._lint(lid)
        if c == "repeat":
            return self._repeat(lid, issue.detail)
        return False

    def _safe(self, i: Issue) -> bool:
        try:
            return self.repair(i)
        except Exception as exc:  # noqa: BLE001 - one failed repair must not stop the others
            self.log_fn(f"refine {i.code} {i.lesson_id}: {type(exc).__name__}: {str(exc)[:100]}")
            return False

    def run(self) -> RefineResult:
        asm, issues = self.check()
        rounds = 0
        while rounds < self.max_rounds and issues:
            todo, rewritten = [], set()
            fresh = [i for i in issues if self.tries.get(i.key(), 0) < MAX_TRIES.get(i.code, 2)]
            for i in sorted((x for x in fresh if x.code != "media_missing"),
                            key=lambda x: (x.severity != "hard", x.code not in ("lesson_missing", "repeat"))):
                if i.lesson_id in rewritten and i.code not in ("lesson_missing",):
                    continue  # the whole lesson was just redone: judge it again before patching it
                todo.append(i)
                self.tries[i.key()] = self.tries.get(i.key(), 0) + 1
                ok = self._safe(i)
                if ok and i.code in ("lesson_missing", "repeat", "block_placeholder"):
                    rewritten.add(i.lesson_id)
                self.log_fn(f"refine {i.code} {i.lesson_id or ''} {i.block_id or ''}: {'repaired' if ok else 'not repaired'}")
            # media last: the text repairs above may have made clips stale; re-renders are independent, so side by side
            media = [i.say({}) for i in self.media_issues(None) if self.tries.get(i.key(), 0) < MAX_TRIES.get("media_missing", 1)]
            for i in media:
                self.tries[i.key()] = self.tries.get(i.key(), 0) + 1
            if media:
                with ThreadPoolExecutor(max_workers=max(1, min(self.workers, len(media)))) as ex:
                    for i, ok in zip(media, ex.map(self._safe, media)):
                        self.log_fn(f"refine media {i.block_id}: {'repaired' if ok else 'not repaired'}")
                todo += media
            if not todo:
                break
            rounds += 1
            before = {i.key() for i in issues}
            asm, issues = self.check()
            self.fixed += [i for i in todo if i.key() in before and i.key() not in {x.key() for x in issues}]
        if asm is None:  # could not assemble even after the repairs
            raise ValueError("; ".join(i.detail for i in issues) or "course could not be assembled")
        titles = titles_of(asm.pack, self.outline)
        final = [i.say(titles) for i in issues + self.removed]
        for i in self.fixed:
            i.fixed = True
            i.say(titles)
        return RefineResult(asm, final, self.fixed, rounds, self.engine)


__all__ = ["Issue", "Refiner", "RefineResult", "check_pack", "check_store_version", "publish_blockers", "quiz_key_problem",
           "repeat_ratio", "titles_of", "HARD", "WORDS"]
