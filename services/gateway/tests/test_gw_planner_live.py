"""Opt-in: the real REASONING model plans for a synthetic learner. Skipped unless MENTOR_LIVE_PLANNER=1.

Needs MODEL_ROUTER_URL (+ MODEL_ROUTER_KEY), or direct mode: FPT_API_BASE + FPT_API_KEY (env or the repo's
.env.dev.local) with PLANNER_LIVE_MODEL (default fai/Alibaba:DeepSeek-V4.1-Flash). Run: MENTOR_LIVE_PLANNER=1 pytest -s <this file>
"""

import asyncio
import os
from pathlib import Path

import pytest
from planner_fixtures import NOW, TZ, goal_for, make_courses, make_ctx, simulate

from mentor_gateway.planner.llm import RouterPlannerLLM, llm_plan
from mentor_gateway.planner.validator import validate

pytestmark = pytest.mark.skipif(os.environ.get("MENTOR_LIVE_PLANNER") != "1", reason="set MENTOR_LIVE_PLANNER=1 to call the real model")


def _env_file_values() -> dict[str, str]:
    for d in Path(__file__).resolve().parents:
        f = d / ".env.dev.local"
        if f.is_file():
            out = {}
            for line in f.read_text(encoding="utf-8-sig").splitlines():
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip().strip('"')
            return out
    return {}


def _llm() -> RouterPlannerLLM:
    url = os.environ.get("MODEL_ROUTER_URL")
    if url:
        return RouterPlannerLLM(url, os.environ.get("MODEL_ROUTER_KEY"))
    vals = {**_env_file_values(), **os.environ}
    if not (vals.get("FPT_API_BASE") and vals.get("FPT_API_KEY")):
        pytest.skip("no MODEL_ROUTER_URL and no FPT_API_BASE/FPT_API_KEY")
    return RouterPlannerLLM(vals["FPT_API_BASE"], vals["FPT_API_KEY"], os.environ.get("PLANNER_LIVE_MODEL", "fai/Alibaba:DeepSeek-V4.1-Flash"))


def test_real_model_plan_passes_the_validator_and_tracks_the_habit():
    course = make_courses(10, 15, done=2, partial=2)
    ctx = make_ctx(simulate(NOW, "19:30", {0, 1, 3, 4, 6}), courses=[course], goals=[goal_for(course, status="slightly_behind")])
    raw = asyncio.run(llm_plan(_llm(), ctx))
    ok, fixed, notes = validate(raw, ctx)
    print("\nvalidator notes:", notes)
    print("first items:", fixed.get("items", [])[:3])
    assert ok, notes
    assert fixed["items"] and fixed["goals"]
    starts = [i["start"] for i in fixed["items"]]
    near = sum(abs(int(s[:2]) * 60 + int(s[3:]) - (19 * 60 + 30)) <= 60 for s in starts) / len(starts)
    assert near >= 0.6, starts
    assert TZ  # dates are local
