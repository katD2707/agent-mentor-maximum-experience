"""Q&A orchestration (REQUIREMENTS-PLAN 3.5). `AskService.stream` yields `(event, data)` pairs; the API turns them into SSE.

Flow: [audio -> transcript] -> intent -> learn (search + short answer + cards) | solve (photo check + OCR -> choose problem ->
step-by-step solution with the last step withheld) | other (one friendly redirect). A thread keeps the compact state a
follow-up needs (current problem, solution, withheld step, last turns); nothing else is remembered.
"""

import asyncio
import json
import logging
import re
import secrets
import shutil
import subprocess
import tempfile
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from mentor_schemas import ModelAlias

from mentor_gateway.ask import photo, prompts
from mentor_gateway.ask.jsonparse import parse_model_json
from mentor_gateway.ask.llm import ChatLLM, LLMError, audio_part, image_part
from mentor_gateway.ask.tables import AskThread
from mentor_gateway.content.service import ContentService
from mentor_gateway.db import Database, User
from mentor_gateway.planner.text import clean, unaccent
from mentor_gateway.settings import Clock

log = logging.getLogger(__name__)

# Intent without a model call (a classifier round trip costs 1-2 s): clear "learn", "solve" and greeting messages are routed
# by rules on the unaccented text; anything else is ambiguous and goes to the model, with course search running beside it.
EQUATION_RE = re.compile(r"=|\d\s*[+*/^×÷]\s*\d|\d?[a-z]\s*\^\s*\d|\\frac|sqrt")
LEARN_RE = re.compile(r"\b(muon hoc|hoc|khoa hoc|khoa|course|courses|learn|study|on thi|on tap|giao trinh|bai hoc|lesson|tu hoc)\b")
SOLVE_START_RE = re.compile(r"^(giai|tinh|tim|rut gon|chung minh|phan tich|solve|calculate|compute|find|simplify|prove|factor|expand)\b")
GREETING_RE = re.compile(r"^(xin chao|chao|hello|hi|hey|alo|cam on|thanks|thank you|ok|oke)\b")
CONCEPT_RE = re.compile(r"\b(la gi|nghia la gi|what is|what are|why|tai sao|vi sao|giai thich|explain|how does|nhu the nao)\b")

HISTORY_TURNS = 8
THREAD_TTL = timedelta(days=7)
MAX_CARDS = 3
SOON_MIN = 0.4  # lowest score at which a coming-soon course is listed beside live ones
CLEAR_MATCH = 0.5  # search score of a short message above which it is a "learn" request without asking a model
ACTIONS = ("simpler", "similar", "last_step", "choose")
ACTION_PHRASES = {
    "last_step": ("xem buoc cuoi", "show last step", "show the last step", "last step"),
    "simpler": ("giai thich de hon", "giai thich don gian", "explain simpler", "explain it easier", "explain more simply", "simpler"),
    "similar": ("lam 3 bai tuong tu", "bai tuong tu", "similar problems", "3 similar", "similar"),
}


@dataclass
class AskInput:
    text: str = ""
    image: bytes | None = None
    audio: bytes | None = None
    audio_format: str = "wav"
    thread_id: str | None = None
    lang: str = "vi"
    action: str | None = None
    problem_id: str | None = None


Event = tuple[str, dict[str, Any]]


def _json_obj(raw: str) -> dict[str, Any]:
    try:
        return parse_model_json(raw)
    except ValueError as e:
        raise LLMError(f"unparseable JSON: {e}") from e


def route_text(text: str, active_problem: bool = False) -> tuple[str, bool] | None:
    """(intent, concept_question) for a clear message, None when a model has to decide. Cheap and deterministic."""
    t = unaccent(text).strip(" .?!")
    if not t:
        return None
    if len(t.split()) <= 4 and GREETING_RE.match(t) and not LEARN_RE.search(t):
        return "other", False
    if LEARN_RE.search(t) and not EQUATION_RE.search(t):
        return "learn", bool(CONCEPT_RE.search(t))
    if not active_problem and (EQUATION_RE.search(t) or (SOLVE_START_RE.match(t) and re.search(r"\d", t))):
        return "solve", False  # with a problem on screen "x = 3 ?" may be a follow-up: let the model decide
    return None


def detect_action(text: str) -> str | None:
    t = unaccent(text).strip(" .?!")
    for action, phrases in ACTION_PHRASES.items():
        if any(t == p or (len(t) <= 40 and p in t) for p in phrases):
            return action
    return None


def to_wav(data: bytes, fmt: str) -> tuple[bytes, str]:
    """Models take wav/mp3. Browsers record webm/ogg/mp4: convert with ffmpeg when it exists, else pass through."""
    if fmt in ("wav", "mp3") or not shutil.which("ffmpeg"):
        return data, fmt
    with tempfile.TemporaryDirectory() as d:
        src, dst = Path(d, f"in.{fmt}"), Path(d, "out.wav")
        src.write_bytes(data)
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ac", "1", "-ar", "16000", str(dst)],
                           capture_output=True, timeout=60, check=False)
        if r.returncode == 0 and dst.is_file():
            return dst.read_bytes(), "wav"
    return data, fmt


class AskService:
    def __init__(self, content: ContentService, db: Database, clock: Clock, llm: ChatLLM | None) -> None:
        self.content, self.db, self.clock, self.llm = content, db, clock, llm

    # ------------------------------------------------------------------ threads
    def load_thread(self, user_id: str, thread_id: str) -> dict[str, Any] | None:
        with self.db.session() as s:
            row = s.get(AskThread, thread_id)
            return json.loads(json.dumps(row.state)) if row is not None and row.user_id == user_id else None

    def _save(self, user_id: str, thread_id: str, state: dict[str, Any]) -> None:
        now = self.clock()
        state["history"] = state.get("history", [])[-HISTORY_TURNS:]
        with self.db.session() as s:
            row = s.get(AskThread, thread_id)
            if row is None:
                for old in s.query(AskThread).filter(AskThread.user_id == user_id, AskThread.updated_at < now - THREAD_TTL):
                    s.delete(old)
                s.add(AskThread(id=thread_id, user_id=user_id, updated_at=now, state=state))
            else:
                row.state, row.updated_at = state, now

    @staticmethod
    def _remember(state: dict[str, Any], role: str, text: str) -> None:
        if text:
            state.setdefault("history", []).append({"role": role, "text": text[:400]})

    # ------------------------------------------------------------------ model helpers
    async def _call(self, alias: ModelAlias, messages: list[dict[str, Any]], *, effort: str | None = None, **kw: Any) -> str:
        if self.llm is None:
            raise LLMError("no model router configured")
        if effort and getattr(self.llm, "supports_effort", False):
            kw["effort"] = effort  # less hidden thinking: vision reads 7 s -> 1.5 s, solving a school problem saves a few s
        return await self.llm.complete(alias.value, messages, **kw)

    async def _json(self, alias: ModelAlias, system: str, payload: dict[str, Any], *, max_tokens: int,
                    user_parts: list | None = None, temperature: float = 0.2, effort: str | None = None) -> dict[str, Any]:
        """One call returning a JSON object; one re-ask when the reply is not parseable."""
        text = json.dumps(payload, ensure_ascii=False)
        content: Any = [{"type": "text", "text": text}, *user_parts] if user_parts else text
        messages = [{"role": "system", "content": system}, {"role": "user", "content": content}]
        last: Exception | None = None
        for _ in range(2):
            raw = await self._call(alias, messages, max_tokens=max_tokens, temperature=temperature, effort=effort)
            try:
                return _json_obj(raw)
            except LLMError as e:
                last = e
        raise LLMError(str(last))

    async def _text(self, system: str, payload: dict[str, Any], *, max_tokens: int = 400) -> str:
        raw = await self._call(ModelAlias.CHAT, [{"role": "system", "content": f"{system}\n\n{prompts.STYLE}"},
                                                  {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                               max_tokens=max_tokens, temperature=0.4)
        return clean(re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL), 280)

    # ------------------------------------------------------------------ the stream
    async def stream(self, user: User, inp: AskInput) -> AsyncIterator[Event]:
        lang = inp.lang if inp.lang in ("vi", "en") else "vi"
        thread_id = inp.thread_id or f"a-{secrets.token_hex(8)}"
        state = (self.load_thread(user.id, thread_id) if inp.thread_id else None) or {"history": []}
        yield "thread", {"thread_id": thread_id}
        try:
            async for ev in self._run(user, inp, lang, state):
                yield ev
        except LLMError as e:
            log.warning("ask model failure: %s", e)
            yield "error", {"code": "model_unavailable", "message": (
                "Mình đang bận một chút, em thử lại sau ít phút nhé." if lang == "vi" else
                "I'm a bit busy right now, please try again in a few minutes.")}
        except Exception:
            log.exception("ask failed")
            yield "error", {"code": "internal", "message": ""}
        finally:
            self._save(user.id, thread_id, state)
        yield "done", {"thread_id": thread_id}

    async def _run(self, user: User, inp: AskInput, lang: str, state: dict[str, Any]) -> AsyncIterator[Event]:
        text = inp.text.strip()
        if inp.audio:
            yield "status", {"stage": "listening"}
            heard = await self.transcribe(inp.audio, inp.audio_format)
            if not heard:
                yield "message", {"kind": "no_speech", "text": "Mình chưa nghe rõ, em nói lại nhé." if lang == "vi"
                                  else "I couldn't hear you clearly, please say it again."}
                return
            yield "transcript", {"text": heard}
            text = f"{text} {heard}".strip()

        action = inp.action if inp.action in ACTIONS else (detect_action(text) if not inp.image and state.get("problem") else None)
        if action is None and state.get("choices") and not inp.image:
            pid = self._match_problem(state, text)
            if pid:
                action, inp.problem_id = "choose", pid
        if action:
            yield "intent", {"intent": "solve"}
            async for ev in self._followup(action, inp, user, lang, state):
                yield ev
            return

        if inp.image:
            intent, query, followup, reply = "solve", "", False, ""
        else:
            if not text:
                yield "message", {"kind": "empty", "text": "Em muốn hỏi gì nào?" if lang == "vi" else "What would you like to ask?"}
                return
            routed = route_text(text, bool(state.get("problem")))
            search_task: asyncio.Future | None = None
            if routed is not None:
                intent, concept = routed
                query, followup, reply = text, False, ""
                if intent == "other":
                    reply = self._canned_other(lang)
                elif intent == "learn":
                    search_task = asyncio.ensure_future(self._search(text))
            else:
                # ambiguous: search first. A short message that clearly matches a course is a learn request and needs no
                # model; otherwise the model decides (its call starts once the quick search has not settled it).
                search_task = asyncio.ensure_future(self._search(text))
                await asyncio.wait({search_task}, timeout=0.15)
                query, followup, reply, concept = text, False, "", False
                if not state.get("problem") and await self._clear_match(text, search_task):
                    intent, concept = "learn", bool(CONCEPT_RE.search(unaccent(text)))
                else:
                    try:
                        intent, query, followup, reply = await self._classify(text, lang, state)
                        concept = bool(reply) and intent == "learn"
                    except LLMError:
                        intent, query, followup, reply = await self._guess_intent(text, search_task)
        yield "intent", {"intent": intent}
        self._remember(state, "user", text or "[photo]")

        if intent == "learn":
            async for ev in self._learn(user, text, query, reply, lang, state, concept=concept, search_task=search_task):
                yield ev
        elif intent == "solve" and followup and state.get("problem"):
            ans = await self._text(prompts.FOLLOWUP, {"question": text, "problem": state["problem"],
                                                       "solution": state.get("solution"), "lang": lang})
            self._remember(state, "assistant", ans)
            yield "answer", {"text": ans}
        elif intent == "solve":
            async for ev in self._solve_new(user, text, inp.image, lang, state):
                yield ev
        else:
            ans = clean(reply, 200) or self._canned_other(lang)
            self._remember(state, "assistant", ans)
            yield "answer", {"text": ans}

    # ------------------------------------------------------------------ audio, intent
    async def transcribe(self, audio: bytes, fmt: str) -> str:
        data, fmt = await asyncio.to_thread(to_wav, audio, fmt)
        raw = await self._call(ModelAlias.AUDIO, [{"role": "user", "content": [
            {"type": "text", "text": prompts.TRANSCRIBE}, audio_part(data, fmt)]}], max_tokens=800, temperature=0.0)
        t = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip().strip('"')
        return "" if not t or "NO_SPEECH" in t.upper() else t

    @staticmethod
    def _canned_other(lang: str) -> str:
        return ("Mình giúp em tìm khóa học hoặc giải bài tập nhé. Em muốn học gì?" if lang == "vi"
                else "I can help you find a course or solve an exercise. What do you want to learn?")

    async def _classify(self, text: str, lang: str, state: dict[str, Any]) -> tuple[str, str, bool, str]:
        """The model's call for an ambiguous message (raises LLMError when the router is down)."""
        d = await self._json(ModelAlias.CHAT, prompts.INTENT, {
            "message": text[:1000], "lang": lang, "active_problem": (state.get("problem") or {}).get("text", "")[:300] or None,
            "recent": state.get("history", [])[-4:]}, max_tokens=300, temperature=0.0)
        intent = d.get("intent") if d.get("intent") in ("learn", "solve", "other") else "other"
        return intent, str(d.get("query") or text)[:120], bool(d.get("followup")), str(d.get("reply") or "")

    @staticmethod
    async def _clear_match(text: str, search_task: asyncio.Future) -> bool:
        """A short message whose best course scores high (a topic like "điện trường", "Bayes là gì")."""
        if len(text.split()) > 8 or EQUATION_RE.search(unaccent(text)):
            return False
        try:
            found = await search_task
        except Exception:  # noqa: BLE001 - treated as no match; _learn raises it again if it matters
            return False
        return bool(found["results"]) and found["results"][0]["score"] >= CLEAR_MATCH

    @staticmethod
    async def _guess_intent(text: str, search_task: asyncio.Future) -> tuple[str, str, bool, str]:
        """No model: a message that finds a course is a learn request, a digit with letters looks like a problem."""
        try:
            found = await search_task
        except Exception:  # noqa: BLE001
            found = None
        if found and found["results"]:
            return "learn", text, False, ""
        if re.search(r"\d", text) and re.search(r"[a-zA-Z]", text):
            return "solve", "", False, ""
        return "other", "", False, ""

    @staticmethod
    def _match_problem(state: dict[str, Any], text: str) -> str | None:
        t = unaccent(text)
        for p in state.get("choices", []):
            label = unaccent(str(p.get("label", "")))
            if label and re.search(rf"\b{re.escape(label)}\b", t):
                return str(p["id"])
        return None

    # ------------------------------------------------------------------ learn
    def _cards(self, user: User, results: list[dict]) -> list[dict[str, Any]]:
        enrolled = {e["course_id"] for e in self.content.list_enrollments(user.id)} if user.role == "student" else set()
        cards = []
        # live courses first: a placeholder ("coming soon") only fills the remaining places
        ordered = sorted(results, key=lambda r: r.get("status", "live") != "live")
        for r in ordered[:MAX_CARDS]:
            entry = self.content.entry(r["id"])
            if entry is None:
                continue
            tree = self.content.tree(self.content.pack_for(entry))
            first = next(({"lesson_id": ls["id"], "title": ls["title"]} for ch in tree for ls in ch["lessons"]), None)
            cards.append({"course_id": r["id"], "title": r["title"], "cover_sha256": r["cover_sha256"],
                          "description_short": r["description_short"], "language": r["language"],
                          "lessons_count": r["lessons_count"], "est_minutes": r["est_minutes"], "tree": tree,
                          "age_band": r["age_band"], "score": r.get("score"), "enrolled": r["id"] in enrolled,
                          "status": r.get("status", "live"), "first_lesson": first if r.get("status", "live") == "live" else None})
        return cards

    async def _search(self, query: str) -> dict[str, Any]:
        """Course search over every age band (one embedding call at most); `_learn` splits by the student's band."""
        return await asyncio.to_thread(self.content.search_courses, query, None, fast=True)

    async def _learn(self, user: User, text: str, query: str, reply: str, lang: str, state: dict[str, Any], *,
                     concept: bool = False, search_task: asyncio.Future | None = None) -> AsyncIterator[Event]:
        found = await (search_task or self._search(query or text))
        if not found["results"] and query and query != text and search_task is not None:
            found = await self._search(query)  # the model rephrased the question into keywords
        band = user.age_band
        # live courses first, then the student's band (a bonus, not a filter: an exact match for "lớp 11" beats a loose
        # in-band one), then score
        ranked = sorted(found["results"], key=lambda r: (r.get("status", "live") != "live",
                                                          -(r["score"] + (0.15 if band is None or r["age_band"] == band else 0))))
        if any(r.get("status", "live") == "live" for r in ranked):  # a weak placeholder does not pad a real answer
            ranked = [r for r in ranked if r.get("status", "live") == "live" or r["score"] >= SOON_MIN]
        cards = self._cards(user, ranked)
        suggested_all = bool(cards) and cards[0]["status"] == "live" and band is not None and cards[0]["age_band"] != band
        start = cards[0] if cards and cards[0]["status"] == "live" else None
        # cards first: the student sees them at once; wording (and a model's sentence for a concept question) follows
        yield "courses", {"items": cards, "suggested_all_ages": suggested_all, "start_with": (
            {"course_id": start["course_id"], **(start["first_lesson"] or {})} if start else None)}
        lead = reply
        if concept and cards and not lead:
            try:
                lead = await self._text(prompts.CONCEPT, {"question": text, "lang": lang}, max_tokens=200)
            except LLMError:
                lead = ""
        ans = clean(f"{lead} {self._learn_text(cards, lang, suggested_all)}", 280)
        self._remember(state, "assistant", ans)
        yield "answer", {"text": ans}

    @staticmethod
    def _learn_text(cards: list[dict], lang: str, suggested_all: bool = False) -> str:
        if not cards:
            return ("Mình chưa có khóa nào về chủ đề này. Em nói rõ môn và lớp hơn nhé?" if lang == "vi"
                    else "I have no course on this topic yet. Could you tell me the subject and grade?")
        live = [c for c in cards if c["status"] == "live"]
        if not live:  # only placeholders matched: never say "start with" a course that cannot be opened
            names = ", ".join(c["title"] for c in cards[:2])
            return (f"Khóa về chủ đề này sắp có: {names}. Em xem trước phần mục lục nhé." if lang == "vi"
                    else f"A course on this topic is coming soon: {names}. You can preview its outline.")
        soon = max((c for c in cards if c["status"] != "live"), key=lambda c: c["score"] or 0, default=None)
        if soon and (soon["score"] or 0) >= (live[0]["score"] or 0) + 0.15:  # the real match is not open yet
            return (f"Khóa {soon['title']} sắp có. Trong lúc chờ, em thử {live[0]['title']} nhé." if lang == "vi"
                    else f"{soon['title']} is coming soon. Meanwhile, try {live[0]['title']}.")
        cards = live
        first = cards[0]["title"]
        if suggested_all:
            return (f"Khóa này đúng chủ đề em hỏi, dù dành cho lớp khác với em: {first}." if lang == "vi"
                    else f"This course is on your topic, though it is for a different grade: {first}.")
        if len(cards) == 1:
            return f"Khóa này hợp với em: {first}." if lang == "vi" else f"This course fits: {first}."
        return (f"Có {len(cards)} khóa hợp với em, nên bắt đầu từ {first}." if lang == "vi"
                else f"{len(cards)} courses fit, start with {first}.")

    # ------------------------------------------------------------------ solve: photo, problem choice
    async def _solve_new(self, user: User, text: str, image: bytes | None, lang: str,
                         state: dict[str, Any]) -> AsyncIterator[Event]:
        state.update(problem=None, solution=None, choices=[], revealed=False)
        if image is None:  # a typed problem
            async for ev in self._solve(user.age_band, {"id": "1", "label": "", "text": text}, lang, state):
                yield ev
            return
        yield "status", {"stage": "reading"}
        try:
            img = await asyncio.to_thread(photo.open_image, image)
        except ValueError:
            yield "message", {"kind": "bad_image", "text": "Mình không mở được ảnh này. Em chụp lại giúp mình nhé."
                              if lang == "vi" else "I can't open this image. Please take the photo again."}
            return
        det = await asyncio.to_thread(photo.check_photo, img)
        reasons = det.reasons
        yield "quality", {"ok": not reasons, "reasons": reasons, "metrics": {k: round(v, 3) for k, v in det.metrics.items()}}
        if "blank_page" in reasons or photo.hopeless(det):  # no model call can read this: ask for a retake at once
            yield "message", self._retake(lang, [], reasons, [])
            return
        jpeg = await asyncio.to_thread(photo.to_jpeg, img)
        d = await self._json(ModelAlias.VISION, prompts.OCR, {"lang": lang, "note": text[:200]}, max_tokens=8000,
                             user_parts=[image_part(jpeg)], temperature=0.0, effort="low")
        problems = [{"id": str(p.get("id") or i + 1), "label": str(p.get("label") or ""), "text": str(p.get("text") or "").strip()}
                    for i, p in enumerate(d.get("problems") or []) if isinstance(p, dict) and str(p.get("text") or "").strip()]
        unreadable = [u for u in (d.get("unreadable") or []) if isinstance(u, dict)]
        if not problems or unreadable:
            yield "message", self._retake(lang, unreadable, reasons, problems)
        if not problems:
            return
        state["choices"] = problems
        if len(problems) == 1 and not unreadable:
            async for ev in self._solve(user.age_band, problems[0], lang, state):
                yield ev
            return
        yield "choices", {"problems": problems, "reason": "partial" if unreadable else "multiple"}

    @staticmethod
    def _retake(lang: str, unreadable: list[dict], reasons: list[str], problems: list[dict]) -> dict[str, Any]:
        where = "; ".join(dict.fromkeys(str(u.get("where") or u.get("what") or "").strip() for u in unreadable)).strip("; ")
        if where[:1].isupper() and where[1:2].islower():
            where = where[0].lower() + where[1:]  # it follows "Mình chưa đọc được" in the sentence
        why = "; ".join(dict.fromkeys(str(u["reason"]).strip() for u in unreadable if u.get("reason")))
        if why[:1].isupper() and why[1:2].islower():
            why = why[0].lower() + why[1:]
        if not why and reasons:
            why = ", ".join(photo.REASON_TEXT[r][0 if lang == "vi" else 1] for r in reasons if r in photo.REASON_TEXT)
        if lang == "vi":
            text = f"Mình chưa đọc được {where or 'ảnh này'}." + (f" Lí do: {why}." if why else "")
            if problems:
                text += f" {', '.join(p['label'] or 'Một bài' for p in problems)} đọc được, mình giải phần đó trước nhé?"
        else:
            text = f"I can't read {where or 'this photo'} yet." + (f" Reason: {why}." if why else "")
            if problems:
                text += f" {', '.join(p['label'] or 'One problem' for p in problems)} is readable, shall I solve that first?"
        if "blurry" in reasons:
            order = ["steady", "straight", "light"]
        elif {"too_dark", "low_contrast"} & set(reasons):
            order = ["light", "steady", "straight"]
        else:
            order = ["light", "straight", "steady"]
        return {"kind": "retake", "text": clean(text, 400), "where": where, "reasons": reasons,
                "tips": [prompts.RETAKE_TIPS[k][lang] for k in order], "offer_readable": bool(problems)}

    # ------------------------------------------------------------------ solve: solution
    async def _solve(self, grade: str | None, problem: dict[str, Any], lang: str, state: dict[str, Any], *,
                     simpler: bool = False) -> AsyncIterator[Event]:
        yield "problem", {"id": problem["id"], "label": problem.get("label", ""), "text": problem["text"]}
        yield "status", {"stage": "solving"}
        sol = await self._make_solution(problem["text"], grade, lang, simpler=simpler,
                                        previous=state.get("solution") if simpler else None)
        state.update(problem=problem, solution=sol, revealed=False, choices=[])
        yield "solution", self._public_solution(sol, problem)
        self._remember(state, "assistant", f"[solved] {problem['text'][:120]}")

    async def _make_solution(self, problem: str, grade: str | None, lang: str, *, simpler: bool,
                             previous: dict | None) -> dict[str, Any]:
        system = prompts.SOLVE + (f"\n\n{prompts.SIMPLER}" if simpler else "") + f"\n\n{prompts.STYLE}"
        payload = {"problem": problem, "lang": lang, "grade": grade or "unknown", "previous_solution": previous}
        for _ in range(2):
            d = await self._json(ModelAlias.REASONING, system, payload, max_tokens=8000, temperature=0.2, effort="low")
            steps = [{"title": clean(s.get("title"), 60), "md": str(s.get("md") or "").strip()}
                     for s in d.get("steps") or [] if isinstance(s, dict) and str(s.get("md") or "").strip()]
            if steps:
                return {"problem_md": str(d.get("problem_md") or problem).strip(), "steps": steps,
                        "tip": clean(d.get("tip"), 220)}
        raise LLMError("solution had no steps")

    @staticmethod
    def _public_solution(sol: dict[str, Any], problem: dict[str, Any]) -> dict[str, Any]:
        steps = sol["steps"]
        withheld = len(steps) >= 2
        return {"problem_id": problem["id"], "problem_md": sol["problem_md"], "steps": steps[:-1] if withheld else steps,
                "last_step_withheld": withheld, "tip": sol["tip"]}

    # ------------------------------------------------------------------ follow-ups
    async def _followup(self, action: str, inp: AskInput, user: User, lang: str,
                        state: dict[str, Any]) -> AsyncIterator[Event]:
        if action == "choose":
            problem = next((p for p in state.get("choices", []) if str(p["id"]) == str(inp.problem_id)), None)
            if problem is None:
                yield "message", {"kind": "no_problem", "text": "Em gửi lại ảnh giúp mình nhé." if lang == "vi"
                                  else "Please send the photo again."}
                return
            async for ev in self._solve(user.age_band, problem, lang, state):
                yield ev
            return
        problem, sol = state.get("problem"), state.get("solution")
        if not problem or not sol:
            yield "message", {"kind": "no_problem", "text": "Em gửi bài cần giải trước nhé." if lang == "vi"
                              else "Send me the problem first."}
            return
        if action == "last_step":
            if len(sol["steps"]) < 2:
                yield "message", {"kind": "no_last_step", "text": "Lời giải đã hiện đủ rồi." if lang == "vi"
                                  else "The solution is already complete."}
                return
            state["revealed"] = True
            yield "last_step", {"problem_id": problem["id"], "step": sol["steps"][-1]}
        elif action == "simpler":
            async for ev in self._solve(user.age_band, problem, lang, state, simpler=True):
                yield ev
        elif action == "similar":
            yield "status", {"stage": "solving"}
            d = await self._json(ModelAlias.REASONING, f"{prompts.SIMILAR}\n\n{prompts.STYLE}",
                                 {"problem": problem["text"], "lang": lang}, max_tokens=6000, temperature=0.5, effort="low")
            items = [{"problem_md": str(i.get("problem_md") or "").strip(), "answer_md": str(i.get("answer_md") or "").strip()}
                     for i in d.get("items") or [] if isinstance(i, dict) and i.get("problem_md")][:3]
            if not items:
                raise LLMError("no similar items")
            yield "similar", {"items": items}
