"""Stage 8 (assembly): outline + lesson drafts + MediaResults -> course.CoursePack + CourseMeta, written as a draft/review
version through the gateway's ContentStore (or just to a directory).

Missing media is allowed in this phase: a block that needs a file we do not have (picture, video) is skipped with a
note; read-aloud audio that is missing is left out. Quiz items whose pictures are missing are dropped.
"""

from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from mentor_schemas.course import (AssetRef, AudioBlock, CalloutBlock, CourseMeta, CoursePack, Chapter, ImageBlock,
                                   Lesson, QuizBlock, QuizItem, TextBlock, VideoBlock)

from mentor_course_builder.contracts import MediaFile, MediaResult
from mentor_course_builder.lessons import LessonDraft
from mentor_course_builder.outline import CourseOutline
from mentor_course_builder.quiz import PENDING_SHA, is_pending

log = logging.getLogger("mentor_course_builder")


@dataclass
class Assembled:
    pack: CoursePack
    meta: CourseMeta
    assets: dict[str, Path] = field(default_factory=dict)  # path under assets/ -> local file
    notes: list[str] = field(default_factory=list)
    version: int = 1
    level_suggested: str | None = None


def _mime(path: str, hint: str | None = None) -> str:
    return hint or {".vtt": "text/vtt", ".webp": "image/webp"}.get(Path(path).suffix.lower()) or \
        mimetypes.guess_type(path)[0] or "application/octet-stream"


def _ref(f: MediaFile) -> AssetRef:
    data = Path(f.file).read_bytes()
    return AssetRef(path=f.path, mime=f.mime or _mime(f.path), sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))


class _Resolver:
    def __init__(self, results: dict[str, MediaResult]) -> None:
        self.results = results
        self.assets: dict[str, Path] = {}
        self.notes: list[str] = []

    def file(self, rid: str, role: str = "main") -> AssetRef | None:
        r = self.results.get(rid)
        if r is None:
            return None
        f = next((x for x in r.files if x.role == role), None)
        if f is None and role == "main" and r.kind == "tts":
            f = next((x for x in r.files if x.role == "audio"), None)
        if f is None or not Path(f.file).is_file():
            return None
        self.assets[f.path] = Path(f.file)
        return _ref(f)

    def audio(self, rid: str, current: AssetRef | None) -> AssetRef | None:
        if current is None:
            return None
        ref = self.file(rid, "audio") or self.file(rid, "main")
        if ref is None:
            self.notes.append(f"{rid}: read-aloud audio missing, left out")
        return ref

    def quiz_item(self, q: QuizItem) -> QuizItem | None:
        upd: dict = {}
        if is_pending(q.stem_audio):
            upd["stem_audio"] = self.audio(f"{q.id}.stem", q.stem_audio)
        opts = []
        for o in q.options:
            ou = {}
            if is_pending(o.image):
                img = self.file(f"{q.id}.pic-{o.id}")
                if img is None:
                    self.notes.append(f"{q.id}: dropped (picture for option {o.id} missing)")
                    return None
                ou["image"] = img
            if is_pending(o.audio):
                ou["audio"] = self.audio(f"{q.id}.opt-{o.id}", o.audio)
            opts.append(o.model_copy(update=ou) if ou else o)
        if opts:
            upd["options"] = opts
        if q.tap is not None and is_pending(q.tap.image):
            img = self.file(f"{q.id}.tap")
            if img is None:
                self.notes.append(f"{q.id}: dropped (tap picture missing)")
                return None
            upd["tap"] = q.tap.model_copy(update={"image": img})
        return q.model_copy(update=upd) if upd else q

    def block(self, b):
        if isinstance(b, (TextBlock, CalloutBlock)):
            return b.model_copy(update={"audio": self.audio(b.id, b.audio)}) if is_pending(b.audio) else b
        if isinstance(b, ImageBlock):
            img = self.file(b.id)
            if img is None:
                self.notes.append(f"{b.id}: image block skipped (no media)")
                return None
            attr = (self.results[b.id].meta or {}).get("attribution")
            return b.model_copy(update={"image": img, "audio": self.audio(f"{b.id}.audio", b.audio)
                                        if is_pending(b.audio) else b.audio,
                                        "attribution": {k: (None if v is None else str(v)) for k, v in attr.items()} if attr else None})
        if isinstance(b, VideoBlock):
            video = self.file(b.id)
            if video is None:
                self.notes.append(f"{b.id}: video block skipped (no media)")
                return None
            r = self.results[b.id]
            return b.model_copy(update={"video": video, "poster": self.file(b.id, "poster"),
                                        "captions": self.file(b.id, "captions"),
                                        "duration_s": r.duration_s or b.duration_s})
        if isinstance(b, QuizBlock):
            items = [x for x in (self.quiz_item(q) for q in b.items) if x is not None]
            if not items:
                self.notes.append(f"{b.id}: quiz skipped (no item survived)")
                return None
            return b.model_copy(update={"items": items})
        return b


def derive_media(pack: CoursePack) -> list[str]:
    has = dict.fromkeys(("video", "reading", "audio", "quiz", "interactive"), False)
    for ch in pack.chapters:
        for ls in ch.lessons:
            for b in ls.blocks:
                has["video"] |= isinstance(b, VideoBlock)
                has["reading"] |= isinstance(b, TextBlock)
                has["audio"] |= isinstance(b, AudioBlock) or bool(getattr(b, "audio", None))
                if isinstance(b, QuizBlock):
                    has["quiz"] = True
                    if any(q.type in ("TAP_COUNT", "PICTURE_CHOICE") for q in b.items):
                        has["interactive"] = True
    return [k for k, v in has.items() if v]


def assemble(outline: CourseOutline, drafts: list[LessonDraft], results: dict[str, MediaResult] | None = None, *,
             teacher_id: str = "teacher", teacher_name: str = "Giáo viên", version: int = 1,
             cover_path: str = "cover.webp") -> Assembled:
    res = _Resolver(results or {})
    by_id = {d.lesson.id: d for d in drafts}
    chapters: list[Chapter] = []
    for och in outline.chapters:
        lessons: list[Lesson] = []
        for ol in och.lessons:
            d = by_id.get(ol.id)
            if d is None:
                res.notes.append(f"{ol.id}: not written, skipped")
                continue
            blocks = [x for x in (res.block(b) for b in d.lesson.blocks) if x is not None]
            if not blocks:
                res.notes.append(f"{ol.id}: no block left, lesson skipped")
                continue
            lessons.append(d.lesson.model_copy(update={"blocks": blocks}))
        if lessons:
            chapters.append(Chapter(id=och.id, title=och.title, lessons=lessons))
    if not chapters:
        raise ValueError("nothing to assemble: no lesson has any block")
    pack = CoursePack(course_id=outline.course_id, version=version, language=outline.language,
                      age_band=outline.age_band, title=outline.title, chapters=chapters)
    pack = pack.model_copy(update={"min_app_version": pack.required_app_version()})
    stray = [a.path for a in pack.assets() if a.sha256 == PENDING_SHA]
    if stray:  # cannot happen if the resolver is complete; never ship placeholders
        raise ValueError(f"unresolved placeholder assets: {stray[:3]}")
    lessons_all = [ls for c in chapters for ls in c.lessons]
    meta = CourseMeta(id=outline.course_id, title=outline.title, subject=outline.subject, age_band=outline.age_band,
                      language=outline.language, teacher_id=teacher_id, teacher_name=teacher_name,
                      description_short=outline.description_short, outcomes=outline.outcomes, cover=cover_path,
                      media=derive_media(pack), lessons_count=len(lessons_all),  # type: ignore[arg-type]
                      est_minutes=sum(ls.est_minutes for ls in lessons_all))
    return Assembled(pack=pack, meta=meta, assets=res.assets, notes=res.notes, version=version,
                     level_suggested=outline.level_suggested)


def write_to_store(a: Assembled, store_root: Path, *, cover_file: Path | None = None, note: str | None = None,
                   status: str = "review") -> int:
    """create_draft -> write_pack -> set_status through the gateway ContentStore. Returns the version number."""
    from mentor_gateway.content.store import ContentStore  # lazy: the gateway is not a dependency of this package

    store = ContentStore(Path(store_root))
    version = store.create_draft(a.meta, note=note)
    pack = a.pack.model_copy(update={"version": version})
    if a.level_suggested:
        store.set_level(a.pack.course_id, version, suggested=a.level_suggested)
    store.write_pack(a.pack.course_id, version, pack, assets=a.assets)
    if cover_file and Path(cover_file).is_file():
        shutil.copyfile(cover_file, store.course_dir(a.pack.course_id) / a.meta.cover)
    store.set_status(a.pack.course_id, version, status)
    return version


def write_to_dir(a: Assembled, out: Path) -> None:
    """Plain files: pack.json, course.json, assets/ (for inspection without the store)."""
    out.mkdir(parents=True, exist_ok=True)
    (out / "pack.json").write_text(a.pack.model_dump_json(indent=2), encoding="utf-8")
    (out / "course.json").write_text(a.meta.model_dump_json(indent=2), encoding="utf-8")
    for rel, src in a.assets.items():
        dest = out / "assets" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)


__all__ = ["Assembled", "assemble", "write_to_store", "write_to_dir", "derive_media", "json"]
