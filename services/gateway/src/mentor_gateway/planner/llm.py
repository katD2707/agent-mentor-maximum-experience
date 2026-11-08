"""Layer 3 (3.7): the planner agent. One REASONING call (router alias `mentor-reasoning`) with the study profile, goals,
enrollments (lesson tree + minutes), FSRS due items, the current week and the history of moves as input, and the
adapted education-agent-skills (planner/skills/, CC BY-SA 4.0) in the system prompt. Strict JSON out.

The model never sees names or free text of the student, only ids, titles of courses and numbers.
"""

import json
import logging
import re
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

import httpx
from mentor_schemas import ModelAlias

from mentor_gateway.planner import research_plan
from mentor_gateway.planner.bands import TZ, hhmm
from mentor_gateway.planner.fallback import weekly_cap
from mentor_gateway.planner.text import HUMANIZE_RULES
from mentor_gateway.planner.types import WEEKDAYS_EN, PlanContext

log = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).parent / "skills"
SKILL_ORDER = ("spaced-practice-scheduler", "individual-spacing-algorithm-explainer", "study-strategy-selector",
               "interleaving-unit-planner", "flow-state-condition-designer", "implementation-intention-designer",
               "motivation-diagnostic-task-redesign", "weekly-agency-review")


class PlannerLLM(Protocol):
    async def plan(self, system: str, user: str) -> str: ...


class PlannerLLMError(Exception):
    pass


@lru_cache(maxsize=1)
def skills_text() -> str:
    parts = []
    for name in SKILL_ORDER:
        body = (SKILLS_DIR / f"{name}.md").read_text(encoding="utf-8")
        parts.append(re.sub(r"^<!--.*?-->\s*", "", body, flags=re.DOTALL).strip())
    return "\n\n".join(parts)


SCHEMA = """Return ONLY one JSON object (no prose, no markdown fence):
{
 "items": [{"date": "YYYY-MM-DD", "start": "HH:MM", "minutes": int, "kind": "lesson|review|practice|break",
            "course_id": str|null, "lesson_id": str|null, "reason_vi": str, "reason_en": str}],
 "reminders": [{"at": "YYYY-MM-DDTHH:MM:00+07:00", "kind": "study|break|nudge", "text_vi": str, "text_en": str, "deep_link": str}],
 "goals": [{"goal_id": str, "status": "on_track|slightly_behind|behind|new", "line_vi": str, "line_en": str}],
 "week_note_vi": str, "week_note_en": str
}
deep_link formats: "/khoa-hoc/<course_id>?lesson=<lesson_id>" for lessons, "/khoa-hoc/<course_id>" for a course, "/luyen-tap" for practice."""

RULES = """You are Mentor's study planner for ONE student. You plan the next 7 days and never ask the student anything: every input is measured data. Your plan passes a strict code validator, so respect these hard limits (violations are repaired or the whole plan is replaced by a rule-based plan):
- Plan only dates today..today+6 (local time, Asia/Ho_Chi_Minh). Times are local HH:MM.
- Session minutes inside age_band.bounds. No session before 06:30 or at/after age_band.bedtime. No overlaps. At most 6 study days; keep at least one rest day.
- At most 2 reminders per day, usually 1 (at the start of a planned session). No reminder in the past, before quiet_until, after bedtime, or in a slot where the student already started studying today. Never remind in profile.avoid_slots or profile.self_start_slots (the student starts there alone).
- At most one "nudge" in the whole plan, only when profile.days_since_study >= 2 and none was sent since the last study day.
- Total planned minutes must stay near the student's real pace (weekly cap in limits.weekly_minutes_cap). Required pace above reality is solved by smart ordering and shorter sessions, not by piling on minutes.
- Use only course_id / lesson_id values that appear in courses. lesson items need lesson_id. Keep lessons of a course in order, skip lessons with done=true.
- Put sessions in the student's real habit windows (profile.windows by weekday, else profile.overall_slots, else age_band defaults). If profile.skip_weekdays lists a day, leave it empty and explain moved work in the reason.
- profile.ask_14d counts the student's questions in Hỏi đáp (learn = wants a course, solve = stuck on a problem) and course cards opened from an answer. Many "solve" questions mean they are stuck on homework: keep sessions short and leave room for practice. "learn" questions with no course opened are curiosity, not a commitment: do not add courses because of them.
- Every item gets reason_vi and reason_en: ONE short sentence, in the student's terms, naming what changed or why (what is due, where they stopped, which goal is behind). Do not repeat the time or minutes in the reason, the screen already shows them. Every goal in goals_input gets exactly one entry in "goals"; keep the status given unless data says otherwise.
- profile.research (counts only) says the student also has thesis work: deadlines, an advisor meeting, a weekly reading block. Code adds those as kind "research" items and reminders AFTER your plan, so never write kind "research" yourself; just leave room (keep sessions short and do not fill every evening).
- Return the plan for ALL 7 days, not a diff. History of moves (moves) shows what already changed: do not flip-flop the same item.
"""


def system_prompt(mode: str) -> str:
    extra = ""
    if mode == "weekly_review":
        extra = ("\nThis run is the weekly review: apply the weekly pattern review first (read the last 7 days of recorded data "
                 "for patterns), then plan the next 7 days.\n")
    return (f"{RULES}{extra}\n{HUMANIZE_RULES}\n\n# Skills you are equipped with (adapted from education-agent-skills, "
            f"CC BY-SA 4.0)\n\n{skills_text()}\n\n# Output\n{SCHEMA}")


def user_payload(ctx: PlanContext) -> dict[str, Any]:
    now = ctx.now.astimezone(TZ)
    b = ctx.band
    by_course_due: dict[str, int] = {}
    for d in ctx.due_items:
        by_course_due[d.get("course_id") or "practice"] = by_course_due.get(d.get("course_id") or "practice", 0) + 1
    return {
        "now": now.isoformat(), "today": now.date().isoformat(), "weekday": WEEKDAYS_EN[now.weekday()],
        "week_dates": [{"date": (now.date() + timedelta(days=i)).isoformat(),
                        "weekday_index": (now.weekday() + i) % 7, "weekday": WEEKDAYS_EN[(now.weekday() + i) % 7]}
                       for i in range(7)],
        "mode": ctx.trigger, "weekday_index_note": "0=Mon ... 6=Sun (profile.windows.weekday uses the same)",
        "age_band": {"id": b.id, "bounds": [b.min_minutes, b.max_minutes], "bedtime": hhmm(b.bedtime_min),
                     "break_after_minutes": b.break_after, "default_start": hhmm(b.start_min),
                     "default_minutes": b.minutes},
        "limits": {"weekly_minutes_cap": weekly_cap(ctx)},
        "quiet_until": ctx.quiet_until.astimezone(TZ).isoformat() if ctx.quiet_until else None,
        "profile": {k: v for k, v in ctx.profile.items() if k not in ("age_defaults", "research")},
        "research": (research_plan.model_view(ctx.profile["research"]) if ctx.profile.get("research") else None),
        "goals_input": [{"goal_id": g.id, "title": g.title, "kind": g.kind,
                         "deadline": g.deadline.isoformat() if g.deadline else None, "course_ids": g.course_ids,
                         "progress_pct": g.progress_pct, "remaining_minutes": g.remaining_minutes,
                         "required_min_per_day": g.required_min_per_day, "status": g.status} for g in ctx.goals],
        "courses": [{"course_id": c.id, "title": c.title, "subject": c.subject, "progress_pct": c.progress_pct,
                     "last_lesson_id": c.last_lesson_id,
                     "lessons": [{"lesson_id": ls.id, "title": ls.title, "minutes": ls.minutes, "done": ls.done,
                                  "started": ls.started} for ls in c.lessons]} for c in ctx.courses],
        "due_items": {"count": len(ctx.due_items), "by_course": by_course_due,
                      "top": [{"course_id": d.get("course_id"), "lesson_id": d.get("lesson_id"),
                               "overdue_days": d["overdue_days"]} for d in ctx.due_items[:12]]},
        "current_week_plan": [{k: i[k] for k in ("date", "start", "minutes", "kind", "course_id", "lesson_id")}
                              for i in ctx.old_items],
        "moves": ctx.moves[-10:],
        "missed_recent": ctx.missed_recent,
    }


def parse(text: str) -> dict:
    """Strict JSON out of a model reply (tolerates a <think> block and a ```json fence, nothing else)."""
    t = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL).strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", t, flags=re.DOTALL)
    if m:
        t = m.group(1)
    try:
        out = json.loads(t)
    except ValueError as e:
        raise PlannerLLMError(f"not JSON: {e}") from e
    if not isinstance(out, dict):
        raise PlannerLLMError("JSON is not an object")
    return out


class RouterPlannerLLM:
    """POST {router}/v1/chat/completions with the `mentor-reasoning` alias. Streams (a reasoning model can think for
    minutes; a non-streamed call can hit a gateway timeout, spike P0) and retries once on a transient failure."""

    def __init__(self, url: str, key: str | None, model: str = ModelAlias.REASONING.value, timeout: float = 240.0) -> None:
        self.url, self.key, self.model, self.timeout = url.rstrip("/"), key or "", model, timeout

    async def _once(self, system: str, user: str) -> str:
        body = {"model": self.model, "temperature": 0.2, "stream": True, "max_tokens": 8000,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        parts: list[str] = []
        client = httpx.AsyncClient(timeout=httpx.Timeout(self.timeout, connect=15.0))
        headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
        async with client, client.stream("POST", f"{self.url}/v1/chat/completions", json=body, headers=headers) as r:
            if r.status_code >= 400:
                raise PlannerLLMError(f"router HTTP {r.status_code}: {(await r.aread())[:200]!r}")
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    delta = json.loads(payload)["choices"][0].get("delta") or {}
                except (ValueError, KeyError, IndexError):
                    continue
                parts.append(delta.get("content") or "")
        text = "".join(parts)
        if not text.strip():
            raise PlannerLLMError("empty reply")
        return text

    async def plan(self, system: str, user: str) -> str:
        last: Exception | None = None
        for _ in range(2):
            try:
                return await self._once(system, user)
            except PlannerLLMError as e:
                last = e
            except httpx.HTTPError as e:
                last = e
        raise PlannerLLMError(f"router call failed: {last}") from last


async def llm_plan(llm: PlannerLLM, ctx: PlanContext) -> dict:
    raw = await llm.plan(system_prompt(ctx.trigger), json.dumps(user_payload(ctx), ensure_ascii=False, default=str))
    return parse(raw)
