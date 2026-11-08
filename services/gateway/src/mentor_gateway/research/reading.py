"""Reading list, paper reader and suggestions (CONTRACTS 15.5). The reader order is fixed: the learner writes the summary,
then asks for feedback; Mentor never reviews before that.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from datetime import datetime, timedelta
from typing import Any

from mentor_schemas.research import (
    READING_LIST_LIMIT,
    AddPaperRequest,
    DiscoveryStatus,
    FeedbackRow,
    PaperDetail,
    PaperFeedback,
    PaperNote,
    PaperQA,
    QaCitation,
    ReadingEntry,
    ReadingList,
    ResearchProfileInput,
    Suggestion,
    SuggestionList,
)
from sqlalchemy import select

from mentor_gateway.db import User
from mentor_gateway.mirror import normalize_path
from mentor_gateway.planner.bands import TZ
from mentor_gateway.planner.text import clean
from mentor_gateway.research import fulltext, prompts
from mentor_gateway.research.base import ModelUnavailable, ResearchBase, fail, iso
from mentor_gateway.research.sources import SourceError, paper_key
from mentor_gateway.research.tables import (
    PaperNoteRow,
    PaperQARow,
    PaperRow,
    ReadingEntryRow,
    SuggestionRow,
)
from mentor_gateway.research.vendor.deeptutor import research_primitives as prim

log = logging.getLogger(__name__)

_DOI = re.compile(r"(10\.\d{4,9}/[^\s?#]+)", re.IGNORECASE)
_S2_URL = re.compile(r"semanticscholar\.org/paper/(?:[^/]+/)?([0-9a-f]{40})", re.IGNORECASE)
_ARXIV_ARG = re.compile(r"^(?:arxiv:)?\s*((?:\d{4}\.\d{4,5}|[a-z][a-z.-]+/\d{7})(?:v\d+)?)$", re.IGNORECASE)


def next_monday_6(now: datetime) -> datetime:
    loc = now.astimezone(TZ)
    target = loc.replace(hour=6, minute=0, second=0, microsecond=0)
    days = (7 - loc.weekday()) % 7
    target += timedelta(days=days)
    if target <= loc:
        target += timedelta(days=7)
    return target


class ReadingMixin(ResearchBase):
    # ---- list ---------------------------------------------------------------------------------------------------------
    def reading_list(self, user_id: str) -> ReadingList:
        now = self.clock()
        minutes = self.minutes_map(user_id, now)
        with self.db.session() as s:
            rows = s.execute(select(PaperRow, ReadingEntryRow).join(ReadingEntryRow, ReadingEntryRow.paper_id == PaperRow.id)
                             .where(ReadingEntryRow.user_id == user_id, ReadingEntryRow.removed_at.is_(None))).all()
            s.expunge_all()
        rank = {"reading": 0, "new": 1, "read": 2}
        items = [(p, e) for p, e in rows if e.status != "read" or (e.read_at and now - e.read_at <= timedelta(days=14))]
        items.sort(key=lambda pe: (rank[pe[1].status], -(pe[1].read_at or pe[1].opened_at or pe[1].added_at).timestamp()))
        active = sum(1 for _, e in rows if e.status in ("new", "reading"))
        return ReadingList(limit=READING_LIST_LIMIT, active_count=active,
                           items=[self.entry_model(p, e, now, minutes) for p, e in items])

    # ---- adding -------------------------------------------------------------------------------------------------------
    async def _resolve_link(self, user: User, link: str) -> dict[str, Any]:
        text = link.strip()
        if m := _ARXIV_ARG.match(text):
            arxiv = m.group(1)
        elif "arxiv.org/" in text.lower():
            try:
                arxiv = prim.arxiv_id(text)
            except prim.ResearchError:
                raise fail(422, "bad_paper_ref") from None
        elif (d := _DOI.search(text)) and d.group(1).lower().startswith("10.48550/arxiv."):
            arxiv = d.group(1)[len("10.48550/arXiv."):]
        else:
            arxiv = None
        if arxiv:
            return await self._arxiv_fields(arxiv)
        doi = _DOI.search(text)
        s2 = _S2_URL.search(text)
        if not doi and not s2:
            if re.match(r"^https?://", text, re.IGNORECASE):
                raise fail(422, "paper_unresolved")
            raise fail(422, "bad_paper_ref")
        ref = s2.group(1).lower() if s2 else "DOI:" + doi.group(1).rstrip(".,);").lower()  # type: ignore[union-attr]
        card = None
        s2_key, asta_key = self.user_key(user.id, "s2"), self.user_key(user.id, "asta")
        for fetch in ([lambda: self.s2_client(s2_key).get_paper(ref)] if s2_key else []) + (
                [lambda: self.asta_source(user.id, asta_key).get_paper(ref)] if asta_key else []):
            try:
                card = await fetch()
            except SourceError:
                continue
            if card:
                break
        if not card:
            raise fail(422, "paper_unresolved")
        if card.get("arxiv_id"):  # the arXiv record has the full abstract and the PDF; the card is the fallback
            return await self._arxiv_fields(card["arxiv_id"], fallback=card)
        return card

    async def _arxiv_fields(self, arxiv_id: str, fallback: dict | None = None) -> dict[str, Any]:
        try:
            rows = await asyncio.wait_for(self.fetch_arxiv_feed(re.sub(r"v\d+$", "", arxiv_id)), 20)
        except Exception:  # noqa: BLE001 - arXiv down or no such id: nothing resolves it
            rows = []
        if not rows:
            if fallback:
                return fallback
            raise fail(422, "paper_unresolved")
        r = rows[0]
        aid = re.sub(r"v\d+$", "", r["arxiv_id"])
        year = int(r["published"][:4]) if str(r.get("published", ""))[:4].isdigit() else None
        return {"key": f"arxiv:{aid}", "source": "arxiv", "title": r["title"], "authors": r["authors"], "year": year,
                "arxiv_id": aid, "url": f"https://arxiv.org/abs/{aid}", "abstract": r["abstract"], "has_pdf": True,
                "pdf_url": f"https://arxiv.org/pdf/{aid}"}

    async def _from_upload(self, user: User, path: str) -> tuple[dict[str, Any], str]:
        try:
            norm = normalize_path(path)
        except ValueError:
            raise fail(404, "upload_not_found") from None
        got = await asyncio.to_thread(self.mirror.read, user.id, norm)
        if got is None:
            raise fail(404, "upload_not_found")
        data = got[0]
        if not data.startswith(b"%PDF"):
            raise fail(422, "bad_paper_ref")
        text = await asyncio.to_thread(fulltext.extract_pdf_text, data)
        first = next((ln.strip() for ln in text.splitlines() if len(ln.strip()) > 8), "")
        name = norm.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        title = (first or re.sub(r"^\d{4}-\d{2}-\d{2}-\d{6}-", "", name).replace("-", " "))[:200]
        m = re.search(r"abstract\s*[:.\-—]?\s*(.{80,1800}?)(?:\n\s*\n|\n\s*(?:1\.?\s+)?introduction)", text, re.IGNORECASE | re.DOTALL)
        abstract = " ".join(m.group(1).split()) if m else ""
        digest = hashlib.sha256(data).hexdigest()[:16]
        return ({"key": f"up:{digest}", "source": "arxiv", "title": title, "authors": [], "year": None, "url": "",
                 "abstract": abstract, "has_pdf": True, "upload_path": norm}, text)

    async def _reason_for(self, user: User, f: dict[str, Any], given: str | None) -> str:
        if given and given.strip():
            return " ".join(given.split())[:300]
        title, _q, kws = self.topic(user.id)
        lang = user.language or "vi"
        try:
            data = await self.llm_json(
                prompts.fill(prompts.ENTRY_REASON, lang=prompts.lang_name(lang)),
                f"Thesis title: {title or '(not set)'}\nKeywords: {', '.join(kws)}\nPaper title: {f['title']}\n"
                f"Abstract: {(f.get('abstract') or f.get('excerpt') or '')[:1500]}", timeout=15)
            if isinstance(data.get("reason"), str) and data["reason"].strip():
                return clean(data["reason"], 200)
        except ModelUnavailable:
            pass
        return self.fallback_reason(f, kws, lang)

    @staticmethod
    def fallback_reason(f: dict[str, Any], kws: list[str], lang: str, query: str = "") -> str:
        text = f"{f.get('title', '')} {f.get('abstract') or f.get('excerpt') or ''}".lower()
        for k in kws:
            if k.lower() in text:
                return f"Matches keyword {k}." if lang == "en" else f"Khớp từ khóa {k}."
        if query:
            return f"Matches the search \"{query}\"." if lang == "en" else f"Khớp truy vấn \"{query}\"."
        return "You added this paper to your list." if lang == "en" else "Bạn đã thêm paper này vào danh sách đọc."

    def _attach(self, user_id: str, paper_id: str, *, reason: str, origin: str, now: datetime) -> tuple[bool, ReadingEntryRow]:
        """Creates the entry, or restores a removed one. -> (created_or_restored, entry). Raises 409 when the list is full."""
        with self.db.session() as s:
            e = s.get(ReadingEntryRow, paper_id)
            if e is not None and e.removed_at is None:
                s.expunge(e)
                return False, e
            restoring = e is not None
            status = e.status if restoring else "new"
            if status in ("new", "reading") and self.active_count(user_id) >= READING_LIST_LIMIT:
                raise fail(409, "reading_list_full")
            if e is None:
                e = ReadingEntryRow(paper_id=paper_id, user_id=user_id, status="new", reason=reason, origin=origin, added_at=now,
                                    minutes_spent=0)
                s.add(e)
            else:
                e.removed_at = None
                if reason:
                    e.reason = reason
            s.flush()
            s.expunge(e)
            return True, e

    async def add_paper(self, user: User, req: AddPaperRequest) -> tuple[ReadingEntry, bool]:
        """-> (entry, created). `created` False = the paper was already in the list (200)."""
        upload_text: str | None = None
        origin = "search"
        if req.card is not None:
            c = req.card
            key = paper_key(c.arxiv_id, c.doi, c.s2_id) or ""
            if not c.title.strip() or not key:
                raise fail(422, "bad_paper_ref")
            f = {**c.model_dump(exclude={"in_reading_list", "paper_id", "excerpt", "snippet"}), "key": key,
                 "abstract": c.excerpt or "", "pdf_url": None}
            known = self._known(user.id, key)
            if not known and c.arxiv_id:
                try:
                    f = {**f, **await self._arxiv_fields(c.arxiv_id, fallback=f)}
                except Exception:  # noqa: BLE001 - keep the card's own fields
                    log.info("arXiv abstract not fetched for %s", c.arxiv_id)
        elif req.link is not None:
            f = await self._resolve_link(user, req.link)
            origin = "link"
        else:
            f, upload_text = await self._from_upload(user, req.upload_path or "")
            origin = "pdf"
        existing_pid = self._known(user.id, f["key"])
        if existing_pid:
            got = self.entry_for(user.id, existing_pid, allow_removed=True)
            if got is not None and got[1].removed_at is None:
                return self.entry_view(user.id, existing_pid), False  # type: ignore[return-value]
        elif self.active_count(user.id) >= READING_LIST_LIMIT:
            raise fail(409, "reading_list_full")
        now = self.clock()
        reason = await self._reason_for(user, f, req.reason)
        pid = existing_pid or self.upsert_paper(user.id, f)
        self._attach(user.id, pid, reason=reason, origin=origin, now=now)
        await self._after_add(user, pid, f, upload_text)
        return self.entry_view(user.id, pid), True  # type: ignore[return-value]

    def _known(self, user_id: str, key: str) -> str | None:
        with self.db.session() as s:
            return s.scalar(select(PaperRow.id).where(PaperRow.user_id == user_id, PaperRow.key == key))

    async def _after_add(self, user: User, pid: str, f: dict[str, Any], upload_text: str | None) -> None:
        """The first paper of a learner with no topic derives the profile; the paper's text is indexed."""
        title, _q, _k = self.topic(user.id)
        if not title:
            await self.put_profile(user, ResearchProfileInput(title=f["title"][:300]))
        if upload_text is not None:
            if upload_text.strip():
                self.texts.write(user.id, pid, upload_text)
                self._set_fulltext(pid, "ready")
        else:
            self.index_fulltext_later(user, pid)

    # ---- full text ----------------------------------------------------------------------------------------------------
    def _set_fulltext(self, pid: str, state: str) -> None:
        with self.db.session() as s:
            p = s.get(PaperRow, pid)
            if p is not None:
                p.fulltext_state = state

    def index_fulltext_later(self, user: User, pid: str) -> None:
        with self.db.session() as s:
            p = s.get(PaperRow, pid)
            if p is None or p.fulltext_state != "none" or not (p.arxiv_id and p.pdf_url):
                return
            p.fulltext_state = "indexing"
            url = p.pdf_url
        self.bg(self._index_fulltext(user.id, pid, url, user.language or "vi"))

    async def _index_fulltext(self, user_id: str, pid: str, url: str, lang: str) -> None:
        state = "none"
        try:
            data = await asyncio.wait_for(self.fetch_pdf(url), 120)
            text = await asyncio.to_thread(fulltext.extract_pdf_text, data)
            if len(text) >= 500:
                self.texts.write(user_id, pid, text)
                state = "ready"
        except Exception as exc:  # noqa: BLE001 - no PDF text is not an error for the learner
            log.info("fulltext of %s not indexed: %s", pid, exc.__class__.__name__)
        self._set_fulltext(pid, state)

    # ---- remove, status, detail ---------------------------------------------------------------------------------------
    def remove_paper(self, user: User, pid: str) -> None:
        with self.db.session() as s:
            e = s.get(ReadingEntryRow, pid)
            if e is None or e.user_id != user.id or e.removed_at is not None:
                raise fail(404, "paper_not_found")
            e.removed_at = self.clock()

    def set_status(self, user: User, pid: str, status: str) -> ReadingEntry:
        now = self.clock()
        with self.db.session() as s:
            e = s.get(ReadingEntryRow, pid)
            if e is None or e.user_id != user.id or e.removed_at is not None:
                raise fail(404, "paper_not_found")
            was_active = e.status in ("new", "reading")
            if status in ("new", "reading") and not was_active and self.active_count(user.id) >= READING_LIST_LIMIT:
                raise fail(409, "reading_list_full")
            e.status = status
            if status == "read":
                e.read_at = now
            elif status == "reading" and e.opened_at is None:
                e.opened_at = now
        if status == "read":
            self.event(user, "paper_read", pid, {"paper_id": pid})
        return self.entry_view(user.id, pid)  # type: ignore[return-value]

    def _note_model(self, n: PaperNoteRow | None) -> PaperNote:
        if n is None:
            return PaperNote()
        fb = n.feedback
        return PaperNote(my_summary=n.user_summary, summary_updated_at=iso(n.summary_updated_at),
                         feedback=PaperFeedback(**fb) if fb else None)

    def paper_detail(self, user: User, pid: str) -> PaperDetail:
        got = self.entry_for(user.id, pid)
        if got is None:
            raise fail(404, "paper_not_found")
        now = self.clock()
        with self.db.session() as s:
            e = s.get(ReadingEntryRow, pid)
            e.opened_at = now
            if e.status == "new":
                e.status = "reading"
        self.event(user, "paper_opened", pid, {"paper_id": pid})
        self.index_fulltext_later(user, pid)
        p, _ = self.entry_for(user.id, pid)  # type: ignore[misc]
        note = self.note_row(pid)
        with self.db.session() as s:
            qa_count = len(s.scalars(select(PaperQARow.id).where(PaperQARow.paper_id == pid)).all())
        return PaperDetail(entry=self.entry_view(user.id, pid), abstract=p.abstract or "", pdf_url=p.pdf_url,  # type: ignore[arg-type]
                           fulltext=p.fulltext_state, thesis_tag=note.thesis_tag if note else None,
                           note=self._note_model(note), qa_count=qa_count)

    # ---- summary and feedback -----------------------------------------------------------------------------------------
    def put_summary(self, user: User, pid: str, text: str) -> PaperNote:
        if self.entry_for(user.id, pid) is None:
            raise fail(404, "paper_not_found")
        text = text.strip()
        now = self.clock()
        with self.db.session() as s:
            n = s.get(PaperNoteRow, pid)
            if n is None:
                n = PaperNoteRow(paper_id=pid)
                s.add(n)
            if n.user_summary != text:
                n.feedback = None  # a changed summary drops the old feedback
                n.thesis_tag = None
            n.user_summary, n.summary_updated_at = text, now
        self.event(user, "summary_written", pid, {"paper_id": pid, "chars": len(text)})
        return self._note_model(self.note_row(pid))

    async def feedback(self, user: User, pid: str) -> PaperFeedback:
        got = self.entry_for(user.id, pid)
        if got is None:
            raise fail(404, "paper_not_found")
        p = got[0]
        note = self.note_row(pid)
        if note is None or not note.user_summary or len(note.user_summary.strip()) < 20:
            raise fail(409, "summary_required")  # Mentor never reviews before the learner writes
        if note.feedback:
            return PaperFeedback(**note.feedback)
        lang = user.language or "vi"
        title = self.topic(user.id)[0]
        passages = []
        raw = self.texts.read(user.id, pid) if p.fulltext_state == "ready" else None
        if raw:
            passages = fulltext.top_passages(fulltext.split_passages(raw, lang), note.user_summary, k=6)
        body = [f"Paper title: {p.title}", f"Abstract: {p.abstract or '(not available)'}"]
        body += [f"Passage [{i}] ({ps.section or 'text'}): {ps.text}" for i, ps in enumerate(passages, 1)]
        body += [f"Thesis title: {title or '(none)'}", f"Student's summary: {note.user_summary}"]
        try:
            data = await self.llm_json(prompts.fill(prompts.FEEDBACK, lang=prompts.lang_name(lang)), "\n\n".join(body), max_tokens=1400)
        except ModelUnavailable:
            raise fail(503, "model_unavailable") from None
        rows = []
        for r in data.get("rows") or []:
            if isinstance(r, dict) and r.get("kind") in ("right", "inaccurate", "missing") and isinstance(r.get("text"), str):
                text = clean(r["text"], 400)
                if text:
                    rows.append(FeedbackRow(kind=r["kind"], text=text))
        if not rows:
            raise fail(503, "model_unavailable")
        for_thesis = clean(data["for_thesis"], 300) if title and isinstance(data.get("for_thesis"), str) and data["for_thesis"].strip() else None
        fb = PaperFeedback(rows=rows, for_thesis=for_thesis, created_at=iso(self.clock()))
        tag = None
        if isinstance(data.get("thesis_section"), str) and (m := re.search(r"(?:mục|section)\s*(\d+(?:\.\d+)*)", note.user_summary, re.IGNORECASE)):
            tag = f"Section {m.group(1)} of yours" if lang == "en" else f"Mục {m.group(1)} của bạn"
        with self.db.session() as s:
            n = s.get(PaperNoteRow, pid)
            if n is not None and n.user_summary == note.user_summary:
                n.feedback = fb.model_dump(mode="json")
                n.thesis_tag = tag
        return fb

    def qa_list(self, user: User, pid: str) -> list[PaperQA]:
        if self.entry_for(user.id, pid) is None:
            raise fail(404, "paper_not_found")
        with self.db.session() as s:
            rows = list(s.scalars(select(PaperQARow).where(PaperQARow.paper_id == pid, PaperQARow.user_id == user.id)
                                  .order_by(PaperQARow.created_at, PaperQARow.id)))
        return [self.qa_model(r) for r in rows]

    @staticmethod
    def qa_model(r: PaperQARow) -> PaperQA:
        return PaperQA(id=r.id, question=r.question, answer=r.answer, found=r.found, not_found_reason=r.not_found_reason,
                       citations=[QaCitation(**c) for c in r.citations or []], course_hint=r.course_hint,
                       created_at=iso(r.created_at))

    # ---- suggestions --------------------------------------------------------------------------------------------------
    def discovery_status(self, user_id: str) -> DiscoveryStatus:
        row = self.profile_row(user_id)
        running = any(j["user_id"] == user_id and j["kind"] == "discovery" and j["status"] in ("queued", "running")
                      for j in self.jobs.values())
        return DiscoveryStatus(state="running" if running else "idle", last_run_at=iso(row.discovery_last_run_at) if row else None,
                               last_status=row.discovery_last_status if row else None,  # type: ignore[arg-type]
                               next_run_at=iso(next_monday_6(self.clock())))

    def suggestion_model(self, sg: SuggestionRow, p: PaperRow) -> Suggestion:
        return Suggestion(id=sg.id, week_of=sg.week_of, paper=self.card_of(p, False), reason=sg.reason, query=sg.query,
                          featured=sg.featured, status=sg.status, created_at=iso(sg.created_at))

    def suggestions(self, user_id: str, *, featured_only: bool = False) -> list[Suggestion]:
        with self.db.session() as s:
            q = (select(SuggestionRow, PaperRow).join(PaperRow, PaperRow.id == SuggestionRow.paper_id)
                 .where(SuggestionRow.user_id == user_id, SuggestionRow.status == "pending")
                 .order_by(SuggestionRow.featured.desc(), SuggestionRow.created_at, SuggestionRow.id))
            if featured_only:
                q = q.where(SuggestionRow.featured.is_(True))
            rows = s.execute(q.limit(10)).all()
            s.expunge_all()
        return [self.suggestion_model(sg, p) for sg, p in rows]

    def suggestion_list(self, user_id: str) -> SuggestionList:
        items = self.suggestions(user_id)
        return SuggestionList(week_of=items[0].week_of if items else None, items=items,
                              discovery=self.discovery_status(user_id))

    def accept_suggestion(self, user: User, sid: str) -> ReadingEntry:
        with self.db.session() as s:
            sg = s.get(SuggestionRow, sid)
            if sg is None or sg.user_id != user.id or sg.status != "pending":
                raise fail(404, "suggestion_not_found")
            pid, reason = sg.paper_id, sg.reason
        now = self.clock()
        self._attach(user.id, pid, reason=reason, origin="suggestion", now=now)  # 409 reading_list_full when no slot
        with self.db.session() as s:
            sg = s.get(SuggestionRow, sid)
            sg.status, sg.decided_at = "accepted", now
            e = s.get(ReadingEntryRow, pid)
            e.origin = "suggestion"
        self.index_fulltext_later(user, pid)
        return self.entry_view(user.id, pid)  # type: ignore[return-value]

    def dismiss_suggestion(self, user: User, sid: str) -> None:
        with self.db.session() as s:
            sg = s.get(SuggestionRow, sid)
            if sg is None or sg.user_id != user.id or sg.status != "pending":
                raise fail(404, "suggestion_not_found")
            sg.status, sg.decided_at = "dismissed", self.clock()
