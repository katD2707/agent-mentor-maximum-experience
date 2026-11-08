"""Thesis profile and the learner's own source keys (CONTRACTS 15.1: /research/profile, /research/source-keys)."""

from __future__ import annotations

import re
from datetime import timedelta

from mentor_schemas.research import ResearchProfile, ResearchProfileInput, SourceKeysStatus

from mentor_gateway.db import User
from mentor_gateway.planner.text import clean, unaccent
from mentor_gateway.research import milestones, prompts
from mentor_gateway.research.base import ModelUnavailable, ResearchBase, fail, iso
from mentor_gateway.research.sources import AstaSource, S2Client, SourceError  # noqa: F401 (S2Client/AstaSource: type use in tests)
from mentor_gateway.research.tables import ResearchProfileRow

_STOP = {"the", "and", "for", "with", "from", "using", "based", "study", "analysis", "của", "và", "cho", "các", "một",
         "trong", "với", "về", "nghiên", "cứu", "ứng", "dụng", "dựa", "trên", "bằng"}


def title_keywords(title: str) -> list[str]:
    """No model: keywords from the title words (lower case, 4+ letters, no filler), at most 5."""
    words = []
    for w in re.findall(r"[^\W\d_]{4,}", title.lower()):
        if w not in _STOP and w not in words:
            words.append(w)
    return [w[:40] for w in words[:5]] or [title.strip()[:40]]


def normalize_keywords(raw: list[str]) -> list[str]:
    out: list[str] = []
    for k in raw:
        k = " ".join(str(k).split())[:40]
        if k and unaccent(k) not in {unaccent(x) for x in out}:
            out.append(k)
    return out


class ProfileMixin(ResearchBase):
    def profile_view(self, user_id: str) -> ResearchProfile:
        row = self.profile_row(user_id)
        if row is None:
            return ResearchProfile()
        return ResearchProfile(title=row.title or "", question=row.question or "", keywords=list(row.keywords or []),
                               advisor_name=row.advisor_name or "", asta_connected=bool(row.asta_key_enc),
                               s2_connected=bool(row.s2_key_enc), updated_at=iso(row.updated_at))

    def keys_status(self, user_id: str) -> SourceKeysStatus:
        row = self.profile_row(user_id)
        return SourceKeysStatus(asta_connected=bool(row and row.asta_key_enc), s2_connected=bool(row and row.s2_key_enc))

    async def derive_profile(self, title: str, lang: str) -> tuple[str, list[str]]:
        """A research question and 3-5 English keywords from the title; keywords from the title words without a model."""
        try:
            data = await self.llm_json(prompts.PROFILE_DERIVE, f"Thesis title: {title}\nQuestion language: {prompts.lang_name(lang)}")
            question = clean(data.get("question"), 300) if isinstance(data.get("question"), str) else ""
            kws = normalize_keywords([k for k in data.get("keywords") or [] if isinstance(k, str)])[:5]
            if len(kws) >= 1:
                return question, kws
        except ModelUnavailable:
            pass
        return "", title_keywords(title)

    async def put_profile(self, user: User, inp: ResearchProfileInput) -> ResearchProfile:
        title = None
        if inp.title is not None:
            title = " ".join(inp.title.split())
            if not title:
                raise fail(422, "empty_title")
        keywords = None
        if inp.keywords is not None:
            keywords = normalize_keywords(inp.keywords)
            if not 1 <= len(keywords) <= 8:
                raise fail(422, "bad_keywords")
        before = self.profile_row(user.id)
        had_title = bool(before and before.title)
        derive = title is not None and inp.question is None and keywords is None
        question, derived_kw = ("", [])
        if derive:
            question, derived_kw = await self.derive_profile(title, user.language or "vi")
        now = self.clock()
        with self.db.session() as s:
            row = s.get(ResearchProfileRow, user.id)
            if row is None:
                row = ResearchProfileRow(user_id=user.id, title="", question="", keywords=[], advisor_name="")
                s.add(row)
            if title is not None:
                row.title = title
            if derive:
                row.question, row.keywords = question, derived_kw
            if inp.question is not None:
                row.question = " ".join(inp.question.split())[:300]
            if keywords is not None:
                row.keywords = keywords
            if inp.advisor_name is not None:
                row.advisor_name = " ".join(inp.advisor_name.split())[:100]
            row.updated_at = now
        if title is not None:
            goal, items = milestones.load(self.db, user.id)
            if goal is not None:
                milestones.save(self.db, user.id, items, title, now)
        if title is not None and (derive or not had_title):
            self.start_discovery(user, manual=False)
        elif keywords is not None and self.discovery_waiting(user.id):
            self.start_discovery(user, manual=False)  # edited keywords: the run that was waiting for a model
        return self.profile_view(user.id)

    # ---- keys ---------------------------------------------------------------------------------------------------------
    async def put_key(self, user: User, source: str, key: str) -> SourceKeysStatus:
        self.limiter.require(user.id, "key", 5, timedelta(minutes=1))
        key = key.strip()
        try:
            client = self.s2_client(key) if source == "s2" else AstaSource(key, transport=self.transport)
            await client.validate()
        except SourceError as exc:
            if exc.kind == "invalid_key":
                raise fail(422, "invalid_key") from None
            raise fail(503, "source_unreachable") from None
        sealed = self.box.seal_str(key, aad=self._aad(user.id, source))
        with self.db.session() as s:
            row = s.get(ResearchProfileRow, user.id)
            if row is None:
                row = ResearchProfileRow(user_id=user.id, title="", question="", keywords=[], advisor_name="")
                s.add(row)
            if source == "asta":
                row.asta_key_enc = sealed
            else:
                row.s2_key_enc = sealed
            row.updated_at = self.clock()
        self._asta.clear()
        return self.keys_status(user.id)

    def delete_key(self, user: User, source: str) -> SourceKeysStatus:
        with self.db.session() as s:
            row = s.get(ResearchProfileRow, user.id)
            if row is not None:
                if source == "asta":
                    row.asta_key_enc = None
                else:
                    row.s2_key_enc = None
                row.updated_at = self.clock()
        self._asta.clear()
        return self.keys_status(user.id)
