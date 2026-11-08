"""Questions about one paper over SSE (CONTRACTS 15.5): its own thread in `paper_qa`, no `ask_question` event.

Text to read, in order: the paper's own text when it is indexed (an uploaded PDF, or the arXiv PDF fetched in the
background); Asta `snippet_search` for this paper when the learner has an Asta key and there is no text; always the
abstract. The model may answer only from the numbered passages and must cite a quote word for word; code drops every
citation whose quote is not in the passage it names, and a "found" answer left with no citation becomes an honest
"not found". Events: `status` (searching, reading), `qa`, `error`, and always `done`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from mentor_schemas import ModelAlias
from mentor_schemas.research import CourseRef, PaperQA, QaCitation

from mentor_gateway.ask import prompts as ask_prompts
from mentor_gateway.ask.llm import audio_part
from mentor_gateway.db import User
from mentor_gateway.planner.text import clean
from mentor_gateway.research import fulltext, prompts
from mentor_gateway.research.base import ModelUnavailable, ResearchBase, fail, new_id
from mentor_gateway.research.reading import ReadingMixin
from mentor_gateway.research.sources import s2_ref
from mentor_gateway.research.tables import PaperQARow, PaperRow

log = logging.getLogger(__name__)

NOT_FOUND = {
    ("no_passage", "vi"): "Mình không tìm thấy đoạn nào nói về điều này trong paper. Bạn thử hỏi cụ thể hơn, hoặc xem lại mục liên quan.",
    ("no_passage", "en"): "I could not find a passage about this in the paper. Try a more specific question, or look at the related section.",
    ("no_fulltext", "vi"): "Mình chưa có toàn văn của paper này (chưa có PDF và chưa kết nối Asta), nên chỉ đọc được abstract và không thấy câu trả lời ở đó.",
    ("no_fulltext", "en"): "I do not have this paper's full text (no PDF and no Asta key), only the abstract, and the answer is not there.",
}


class QaMixin(ReadingMixin, ResearchBase):
    async def transcribe(self, audio: bytes, fmt: str) -> str:
        from mentor_gateway.ask.service import to_wav

        if self.llm is None:
            raise ModelUnavailable("no model configured")
        data, fmt = await asyncio.to_thread(to_wav, audio, fmt)
        try:
            heard = await asyncio.wait_for(self.llm.complete(
                ModelAlias.AUDIO.value, [{"role": "user", "content": [{"type": "text", "text": ask_prompts.TRANSCRIBE},
                                                                        audio_part(data, fmt)]}], max_tokens=800, temperature=0.0),
                self.llm_timeout)
        except Exception as exc:
            raise ModelUnavailable(exc.__class__.__name__) from exc
        heard = heard.strip()
        if not heard or heard == "NO_SPEECH":
            raise ModelUnavailable("no speech")
        return heard

    async def _passages(self, user: User, p: PaperRow, question: str, lang: str) -> tuple[list[fulltext.Passage], bool]:
        """-> (passages, has_text_source). `has_text_source` is False when only the abstract could be read."""
        out: list[fulltext.Passage] = []
        has_source = False
        raw = self.texts.read(user.id, p.id) if p.fulltext_state == "ready" else None
        if raw:
            has_source = True
            link = p.pdf_url or p.url or None
            out = [fulltext.Passage(ps.section, ps.text, link, "fulltext")
                   for ps in fulltext.top_passages(fulltext.split_passages(raw, lang), question, k=8)]
        else:
            key = self.user_key(user.id, "asta")
            ref = s2_ref(p.arxiv_id, p.doi, p.s2_id)
            if key and ref:
                has_source = True
                try:
                    snips = await self.asta_source(user.id, key).snippets(question, limit=8, paper_ids=[ref])
                    out = [fulltext.Passage(s["section"] or "", s["text"], s["url"], "asta") for s in snips]
                except Exception as exc:  # noqa: BLE001 - Asta down: the abstract is still there
                    log.info("asta snippets failed: %s", exc.__class__.__name__)
        if p.abstract:
            out.insert(0, fulltext.Passage("Abstract", p.abstract, p.url or None, "abstract"))
        return out, has_source

    def _course_hint(self, user: User, p: PaperRow, question: str) -> CourseRef | None:
        """A course the learner is enrolled in that the paper's topic matches (course search, CONTRACTS 11)."""
        try:
            enrolled = {e["course_id"] for e in self.content.list_enrollments(user.id)}
            if not enrolled:
                return None
            found = self.content.search_courses(f"{p.title} {question}"[:240], None, fast=True)
            for r in found.get("results", []):
                if r["id"] in enrolled and (r.get("score") or 0) >= 0.35:
                    return CourseRef(course_id=r["id"], lesson_id=None, title=r["title"], deep_link=f"/khoa-hoc/{r['id']}")
        except Exception:
            log.info("course hint failed", exc_info=True)
        return None

    def _store_qa(self, user: User, pid: str, question: str, answer: str, found: bool, reason: str | None,
                  cites: list[QaCitation], hint: CourseRef | None) -> PaperQA:
        row = PaperQARow(id=new_id("qa-"), paper_id=pid, user_id=user.id, question=question, answer=answer, found=found,
                         not_found_reason=reason, citations=[c.model_dump() for c in cites],
                         course_hint=hint.model_dump() if hint else None, created_at=self.clock())
        with self.db.session() as s:
            s.add(row)
        return self.qa_model(row)

    async def ask_events(self, user: User, pid: str, question: str, lang: str | None = None) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """(event, data) pairs; the caller has already checked that the paper is the learner's (404 before the stream)."""
        lang = lang or user.language or "vi"
        qa_id: str | None = None
        try:
            yield "status", {"stage": "searching"}
            got = self.entry_for(user.id, pid)
            if got is None:
                raise fail(404, "paper_not_found")
            p = got[0]
            passages, has_source = await self._passages(user, p, question, lang)
            yield "status", {"stage": "reading"}
            reason = "no_fulltext" if not has_source else "no_passage"
            if not passages:
                qa = self._store_qa(user, pid, question, NOT_FOUND[("no_fulltext", lang)], False, "no_fulltext", [], None)
            else:
                body = "\n\n".join(f"[{i}] ({ps.section or 'text'}) {ps.text}" for i, ps in enumerate(passages, 1))
                data = await self.llm_json(prompts.fill(prompts.QA, lang=prompts.lang_name(lang)),
                                           f"Paper: {p.title}\n\nQuestion: {question}\n\nPassages:\n{body}", max_tokens=1200)
                cites: list[QaCitation] = []
                for c in data.get("citations") or []:
                    idx = c.get("passage") if isinstance(c, dict) else None
                    quote = c.get("quote") if isinstance(c, dict) else None
                    if isinstance(idx, int) and isinstance(quote, str) and 1 <= idx <= len(passages) \
                            and fulltext.quote_in(quote, passages[idx - 1].text):
                        ps = passages[idx - 1]
                        cites.append(QaCitation(section=ps.section, snippet=" ".join(quote.split())[:300], url=ps.url))
                if data.get("found") and cites and isinstance(data.get("answer"), str) and data["answer"].strip():
                    qa = self._store_qa(user, pid, question, clean(data["answer"], 700), True, None, cites,
                                        self._course_hint(user, p, question))
                else:
                    qa = self._store_qa(user, pid, question, NOT_FOUND[(reason, lang)], False, reason, [], None)
            qa_id = qa.id
            yield "qa", qa.model_dump(mode="json")
        except ModelUnavailable:
            yield "error", {"code": "model_unavailable", "message": "The model is not available right now."}
        except Exception as exc:
            log.exception("paper question failed")
            yield "error", {"code": "internal", "message": exc.__class__.__name__}
        yield "done", {"qa_id": qa_id}
