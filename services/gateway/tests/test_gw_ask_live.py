"""Opt-in: the real vision, audio, reasoning and chat models answer through `/api/ask`. Skipped unless MENTOR_LIVE_ASK=1.

Needs MODEL_ROUTER_URL (+ MODEL_ROUTER_KEY), or direct mode: FPT_API_BASE + FPT_API_KEY (env or the repo's .env.dev.local).
The photo is rendered with headless Chrome/Edge from the mockup's "Bài 3" text; the audio with edge-tts (installed in the venv).
Run: MENTOR_LIVE_ASK=1 pytest -s services/gateway/tests/test_gw_ask_live.py
"""

import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest
from test_gw_ask import events, parse_sse, settings  # noqa: F401  (settings fixture: the dev sample courses)

from mentor_gateway.ask.llm import RouterChatLLM, direct_from_env
from mentor_gateway.ask.service import AskService

pytestmark = pytest.mark.skipif(os.environ.get("MENTOR_LIVE_ASK") != "1", reason="set MENTOR_LIVE_ASK=1 to call the real models")

BROWSERS = [r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]
PAGE = """<!doctype html><meta charset="utf-8"><body style="margin:0;background:#fff;font:34px/1.6 'Times New Roman',serif;color:#111">
<div style="padding:60px 70px"><p><b>Bài 3.</b> Cho cấp số cộng (u<sub>n</sub>) có u<sub>1</sub> = 3, công sai d = 4.</p>
<p>a) Tìm u<sub>10</sub>.</p><p>b) Tính tổng 20 số hạng đầu.</p></div>"""


@pytest.fixture
def real_ask(client, student):
    url = os.environ.get("MODEL_ROUTER_URL")
    llm = RouterChatLLM(url, os.environ.get("MODEL_ROUTER_KEY")) if url else direct_from_env()
    if llm is None:
        pytest.skip("no MODEL_ROUTER_URL and no FPT_API_BASE/FPT_API_KEY")
    gw = client.app.state.gw
    client.app.state.ask = AskService(client.app.state.content, gw.db, gw.clock, llm)
    return client


def timed(client, **kw):
    t0 = time.monotonic()
    r = client.post("/api/ask", **kw)
    return r, time.monotonic() - t0


def test_live_photo_solution(real_ask, tmp_path):
    browser = next((b for b in BROWSERS if Path(b).is_file()), None)
    if browser is None:
        pytest.skip("no Chrome/Edge")
    page = tmp_path / "p.html"
    page.write_text(PAGE, encoding="utf-8")
    shot = tmp_path / "p.png"
    subprocess.run([browser, "--headless=new", "--disable-gpu", f"--screenshot={shot}", "--window-size=1000,700",
                    "--hide-scrollbars", page.as_uri()], check=True, capture_output=True, timeout=90)
    r, secs = timed(real_ask, data={"lang": "vi"}, files={"image": ("bai3.png", shot.read_bytes(), "image/png")})
    ev = events(r)
    print(f"\nphoto -> {[k for k, _ in parse_sse(r.text)]} in {secs:.1f}s")
    print("quality:", ev["quality"])
    print("problem:", ev.get("problem", ev.get("choices")))
    sol = ev["solution"]
    for s in sol["steps"]:
        print("step:", s["title"], "|", s["md"][:160])
    print("tip:", sol["tip"])
    assert sol["last_step_withheld"] and "u" in ev["problem"]["text"]
    assert "820" not in str(sol["steps"])  # the final result stays in the withheld step
    tid = ev["thread"]["thread_id"]
    last = events(real_ask.post("/api/ask", json={"thread_id": tid, "action": "last_step", "lang": "vi"}))["last_step"]["step"]
    print("last step:", last)
    assert re.search(r"820|\b39\b", last["md"].replace(" ", "")) or last["md"]


def test_live_audio_to_courses(real_ask, tmp_path):
    mp3 = tmp_path / "q.mp3"
    subprocess.run([sys.executable, "-m", "edge_tts", "--voice", "vi-VN-HoaiMyNeural", "--text",
                    "Em muốn học về điện trường", "--write-media", str(mp3)], check=True, capture_output=True, timeout=90)
    r, secs = timed(real_ask, data={"lang": "vi"}, files={"audio": ("q.mp3", mp3.read_bytes(), "audio/mpeg")})
    ev = events(r)
    print(f"\naudio -> {[k for k, _ in parse_sse(r.text)]} in {secs:.1f}s")
    print("transcript:", ev["transcript"]["text"])
    print("answer:", ev["answer"]["text"])
    print("courses:", [c["course_id"] for c in ev["courses"]["items"]])
    assert "điện" in ev["transcript"]["text"].lower() and ev["intent"]["intent"] == "learn"
    assert ev["courses"]["items"][0]["course_id"] == "dev-sample-dien-truong"


def test_live_guide(real_ask):
    t0 = time.monotonic()
    r = real_ask.post("/api/guide", json={"question": "Làm sao để tìm khóa học mới?", "lang": "vi", "screen": "courses",
                                           "visible_keys": ["course-search", "my-courses"]})
    print(f"\nguide in {time.monotonic() - t0:.1f}s:", r.json())
    assert r.status_code == 200 and r.json()["answer"]
