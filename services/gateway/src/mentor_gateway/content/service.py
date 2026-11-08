"""ContentService: catalog filtering, course tree, search, enrollments and media tokens on top of ContentStore."""

from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import datetime, timedelta

from mentor_schemas.course import CatalogEntry, Chapter, CoursePack, Lesson, TextBlock
from sqlalchemy import func, select

from mentor_gateway.content import catalog_query as cq
from mentor_gateway.content.search import CourseSearch, Doc, RouterEmbedder, make_key, retrieval_fields, retrieval_text
from mentor_gateway.content.store import ComingSoon, ContentError, ContentStore, NotFound, block_ids
from mentor_gateway.content.tables import Enrollment
from mentor_gateway.crypto import SecretBox
from mentor_gateway.db import Database, User
from mentor_gateway.settings import Clock, Settings


ACTIVE_LEARNER_DAYS = 30  # a learner counts as active if their enrollment changed within this many days


class ContentService:
    def __init__(self, settings: Settings, db: Database, box: SecretBox, clock: Clock) -> None:
        self.settings = settings
        self.db = db
        self.clock = clock
        self.store = ContentStore(settings.courses_dir, clock)
        self.search = CourseSearch(settings.data_dir / "embeddings",
                                   RouterEmbedder(settings.model_router_url, settings.model_router_key))
        self._media_key = box.subkey("content-media-token")
        self._packs: dict[str, CoursePack] = {}  # by pack_sha256 (immutable, safe to cache)
        self._docs: dict[str, Doc] = {}  # search documents by catalog entry (id + content hash)
        self._vocab_cache: tuple[str, dict[str, str]] = ("", {})  # did-you-mean words by catalog content

    # ------------------------------------------------------------ visibility
    @staticmethod
    def is_teacher(user: User) -> bool:
        return user.role == "teacher"

    def published_version(self, course_id: str, version: int) -> bool:
        meta = self.store.load_meta(course_id)
        return self.store.version_info(meta, version).status == "published"

    def outline_pack(self, course_id: str) -> CoursePack:
        """A coming_soon course as a pack of empty lessons, so tree and search treat it like any other course.
        It is never served: the pack endpoints refuse it."""
        meta = self.store.load_meta(course_id)
        return CoursePack(
            course_id=meta.id, version=1, language=meta.language, age_band=meta.age_band, title=meta.title,
            chapters=[Chapter(id=c.id, title=c.title, lessons=[
                Lesson(id=ls.id, title=ls.title, est_minutes=ls.est_minutes,
                       blocks=[TextBlock(id=f"{ls.id}-b1", md="")]) for ls in c.lessons]) for c in meta.outline])

    def ensure_available(self, course_id: str) -> None:
        """Raises ComingSoon for a placeholder (NotFound when the course does not exist)."""
        if self.store.load_meta(course_id).status == "coming_soon":
            raise ComingSoon()

    def pack_for(self, entry: CatalogEntry) -> CoursePack:
        if entry.status == "coming_soon":
            key = f"{entry.id}:{entry.cover_sha256}"
            p = self._packs.get(key)
            if p is None:
                p = self._packs[key] = self.outline_pack(entry.id)
            return p
        p = self._packs.get(entry.pack_sha256)
        if p is None:
            p = self.store.load_pack(entry.id, entry.version)
            self._packs[entry.pack_sha256] = p
        return p

    # ------------------------------------------------------------ catalog
    def catalog_entries(self, age_band: str | None) -> list[CatalogEntry]:
        cat = self.store.load_catalog()
        return [c for c in cat.courses if age_band is None or c.age_band == age_band]

    def entry(self, course_id: str) -> CatalogEntry | None:
        return next((c for c in self.store.load_catalog().courses if c.id == course_id), None)

    # ------------------------------------------------------------ course page
    @staticmethod
    def tree(pack: CoursePack) -> list[dict]:
        return [{"id": ch.id, "title": ch.title, "lessons": [
            {"id": ls.id, "title": ls.title, "est_minutes": ls.est_minutes, "summary": ls.summary,
             "key_ideas": ls.key_ideas} for ls in ch.lessons]} for ch in pack.chapters]

    def course_detail(self, course_id: str, teacher: bool) -> dict:
        meta = self.store.load_meta(course_id)
        if meta.status == "coming_soon":
            return {**meta.model_dump(mode="json", exclude={"outline"}), "tree": self.tree(self.outline_pack(course_id))}
        if not teacher:
            if meta.latest_published is None:
                raise NotFound("course_not_found")
            meta.versions = [v for v in meta.versions if v.status == "published"]
        version = meta.latest_published
        if version is None:  # teacher viewing an unpublished course: newest version that has a pack
            for v in sorted((v.version for v in meta.versions), reverse=True):
                if self.store.pack_path(course_id, v).is_file():
                    version = v
                    break
        tree: list[dict] = []
        if version is not None:
            try:
                tree = self.tree(self.store.load_pack(course_id, version))
            except NotFound:
                pass
        return {**meta.model_dump(mode="json"), "tree": tree}

    # ------------------------------------------------------------ search
    def _search_docs(self) -> list[Doc]:
        docs = []
        for e in self.store.load_catalog().courses:
            ck = hashlib.sha256(e.model_dump_json().encode()).hexdigest()  # any catalog change makes a new document
            doc = self._docs.get(ck)
            if doc is None:
                fields = retrieval_fields(self.store.load_meta(e.id), self.pack_for(e))
                text = retrieval_text(fields)
                doc = self._docs[ck] = Doc(e, fields, text, make_key(e.pack_sha256 or e.cover_sha256, text))
            docs.append(doc)
        return docs

    def search_courses(self, q: str, age_band: str | None, *, fast: bool = False) -> dict:
        docs = self._search_docs()
        scored, mode = self.search.search(q, docs, fast=fast)
        scored.sort(key=lambda x: (-x[1], x[0].status != "live"))  # equal relevance: real courses before placeholders
        inband = [(e, s) for e, s in scored if age_band is None or e.age_band == age_band]
        students = self.student_counts()
        return {
            "query": q,
            "mode": mode,
            "results": [{**e.model_dump(mode="json"), "students": students.get(e.id, 0), "score": s} for e, s in inband],
            "suggested_all_ages": bool(scored) and not inband,
        }

    # ------------------------------------------------------------ catalog query (hs-03)
    def student_counts(self) -> dict[str, int]:
        """Active learners per course: enrolled students whose enrollment moved (opened, progressed, answered) in the last
        `ACTIVE_LEARNER_DAYS` days. Feeds the "x học sinh đang học" number and the Phổ biến sort, so students who stopped
        do not keep a course on top."""
        since = self.clock() - timedelta(days=ACTIVE_LEARNER_DAYS)
        with self.db.session() as s:
            rows = s.execute(select(Enrollment.course_id, func.count()).where(Enrollment.updated_at >= since)
                             .group_by(Enrollment.course_id)).all()
        return {cid: int(n) for cid, n in rows}

    def _vocab(self, entries: list[CatalogEntry]) -> dict[str, str]:
        key = hashlib.sha256("|".join(f"{e.id}:{e.title}:{e.subject}:{e.teacher_name}" for e in entries).encode()).hexdigest()
        if self._vocab_cache[0] != key:
            self._vocab_cache = (key, cq.vocabulary(entries))
        return self._vocab_cache[1]

    def query_catalog(self, query: cq.Query) -> dict:
        entries = self.store.load_catalog().courses
        students = self.student_counts()
        toks = cq.name_tokens(query.q)
        scores: dict[str, float] = {}
        mode = "lexical"
        matched: set[str] | None = None
        if toks:
            scored, mode = self.search.search(query.q, self._search_docs(), fast=True)
            sc = {e.id: s for e, s in scored}
            matched = {e.id for e in entries if e.id in sc or cq.name_match(e, toks)}
            scores = {e.id: cq.relevance(e, toks, sc.get(e.id, 0.0)) for e in entries if e.id in matched}
        rows = [(i, e) for i, e in enumerate(entries) if (matched is None or e.id in matched) and cq.passes_filters(e, query.filters)]
        ordered = cq.sort_entries(rows, query, scores, students)
        total = len(ordered)
        size = max(1, min(query.page_size, cq.MAX_PAGE_SIZE))
        pages = max(1, -(-total // size))
        page = min(max(1, query.page), pages)
        items = [{**e.model_dump(mode="json"), "students": students.get(e.id, 0), "score": round(scores.get(e.id, 0.0), 4)}
                 for e in ordered[(page - 1) * size: page * size]]
        hint = cq.did_you_mean(query.q, self._vocab(entries)) if toks else None
        return {"query": query.q, "mode": mode, "total": total, "page": page, "pages": pages, "page_size": size, "items": items,
                "facets": cq.facets(entries, query.filters, matched), "did_you_mean": hint}

    def suggest(self, q: str) -> dict:
        entries = self.store.load_catalog().courses
        return cq.suggest(q, entries, self._vocab(entries))

    # ------------------------------------------------------------ media token (?t=)
    def mint_media_token(self, user: User) -> tuple[str, datetime]:
        exp = self.clock() + timedelta(minutes=self.settings.media_token_minutes)
        payload = base64.urlsafe_b64encode(f"{user.id}|{int(exp.timestamp())}".encode()).decode().rstrip("=")
        sig = hmac.new(self._media_key, payload.encode(), hashlib.sha256).hexdigest()[:32]
        return f"{payload}.{sig}", exp

    def verify_media_token(self, token: str) -> str | None:
        """Returns the user id, or None when the token is malformed, forged or expired."""
        try:
            payload, sig = token.split(".", 1)
            good = hmac.new(self._media_key, payload.encode(), hashlib.sha256).hexdigest()[:32]
            if not hmac.compare_digest(sig, good):
                return None
            uid, exp = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode().split("|")
            return uid if int(exp) > self.clock().timestamp() else None
        except (ValueError, UnicodeDecodeError):
            return None

    # ------------------------------------------------------------ enrollments
    def _view(self, row: Enrollment) -> dict:
        total = done = 0
        try:
            ids = set(block_ids(self.store.load_pack(row.course_id, row.version)))
            total = len(ids)
            done = len(ids.intersection(row.completed_block_ids))
        except NotFound:
            pass
        entry = self.entry(row.course_id)
        course = None
        if entry:
            course = {k: getattr(entry, k) for k in ("id", "title", "subject", "age_band", "language", "teacher_name",
                                                    "description_short", "cover_sha256", "lessons_count", "est_minutes")}
        return {
            "course_id": row.course_id,
            "version": row.version,
            "latest_version": entry.version if entry else row.version,
            "update_available": bool(entry and entry.version > row.version),
            "enrolled_at": row.enrolled_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
            "last_lesson_id": row.last_lesson_id,
            "last_block_id": row.last_block_id,
            "completed_block_ids": list(row.completed_block_ids),
            "blocks_total": total,
            "blocks_done": done,
            "progress_pct": round(100 * done / total, 1) if total else 0.0,
            "quiz": row.quiz,
            "course": course,
        }

    def _row(self, s, user_id: str, course_id: str) -> Enrollment | None:
        return s.scalar(select(Enrollment).where(Enrollment.user_id == user_id, Enrollment.course_id == course_id))

    def enroll(self, user_id: str, course_id: str) -> tuple[dict, bool]:
        """Pins the latest published version; idempotent (an existing enrollment keeps its version). -> (view, created)"""
        with self.db.session() as s:
            row = self._row(s, user_id, course_id)
            if row is not None:
                return self._view(row), False
            entry = self.entry(course_id)
            if entry is None:
                raise NotFound("course_not_found")
            if entry.status == "coming_soon":
                raise ComingSoon()
            now = self.clock()
            row = Enrollment(user_id=user_id, course_id=course_id, version=entry.version, enrolled_at=now,
                             updated_at=now, completed_block_ids=[], quiz={})
            s.add(row)
            s.flush()
            return self._view(row), True

    def list_enrollments(self, user_id: str) -> list[dict]:
        with self.db.session() as s:
            rows = s.scalars(select(Enrollment).where(Enrollment.user_id == user_id)
                             .order_by(Enrollment.updated_at.desc())).all()
            return [self._view(r) for r in rows]

    def update_progress(self, user_id: str, course_id: str, *, lesson_id: str | None, block_id: str | None,
                        completed: list[str], quiz: dict | None) -> dict:
        with self.db.session() as s:
            row = self._row(s, user_id, course_id)
            if row is None:
                raise NotFound("not_enrolled")
            pack = self.store.load_pack(course_id, row.version)
            lessons = {ls.id for ch in pack.chapters for ls in ch.lessons}
            blocks = set(block_ids(pack))
            items = {q.id for ch in pack.chapters for ls in ch.lessons for b in ls.blocks
                     if b.kind == "quiz" for q in b.items}
            if lesson_id is not None and lesson_id not in lessons:
                raise ContentError("unknown_lesson", lesson_id)
            if block_id is not None and block_id not in blocks:
                raise ContentError("unknown_block", block_id)
            bad = [b for b in completed if b not in blocks]
            if bad:
                raise ContentError("unknown_block", ",".join(bad))
            if quiz is not None and quiz["item_id"] not in items:
                raise ContentError("unknown_quiz_item", quiz["item_id"])
            if lesson_id is not None:
                row.last_lesson_id = lesson_id
            if block_id is not None:
                row.last_block_id = block_id
            # Progress only grows (a late offline sync never un-completes a block): union with what is stored.
            row.completed_block_ids = sorted(set(row.completed_block_ids) | set(completed))
            if quiz is not None:
                prev = dict(row.quiz).get(quiz["item_id"], {})
                row.quiz = {**row.quiz, quiz["item_id"]: {
                    "correct": bool(quiz["correct"]), "seconds": quiz.get("seconds", 0),
                    "attempts": int(prev.get("attempts", 0)) + 1}}
            row.updated_at = self.clock()
            s.flush()
            return self._view(row)

    def delete_enrollment(self, user_id: str, course_id: str) -> bool:
        with self.db.session() as s:
            row = self._row(s, user_id, course_id)
            if row is None:
                return False
            s.delete(row)
            return True
