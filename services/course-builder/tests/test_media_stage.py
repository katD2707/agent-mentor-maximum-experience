"""Media stage (P3-C), offline: model, network, Chrome, HyperFrames and ffmpeg transcodes are mocked."""

import base64
import io
import json
import wave
from pathlib import Path

import httpx
import pytest
from mentor_course_builder import illustrate, render_media as rm, tts, video
from mentor_course_builder.contracts import MediaFile, MediaRequest, MediaResult
from mentor_course_builder.media import MediaError


def req(kind, spec, **kw):
    return MediaRequest(id=kw.pop("id", "x1"), kind=kind, course_id="c1", age_band=kw.pop("age_band", "g10_12"),
                        language=kw.pop("language", "vi"), spec=spec, **kw)


# ------------------------------------------------------------------------------------------------------ TTS

def test_pcm_to_wav_roundtrip_and_riff_passthrough():
    pcm = b"\x01\x00" * 2400
    wav = tts.pcm_to_wav(pcm)
    with wave.open(io.BytesIO(wav)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()) == (24000, 1, 2, 2400)
    assert tts.pcm_to_wav(wav) == wav


def test_find_audio_b64_in_nested_response():
    raw = b"\x00\x01" * 500
    resp = {"id": "v1", "steps": [{"content": [{"data": base64.b64encode(raw).decode(), "mime_type": "audio/L16;rate=24000"}]}]}
    got = tts.find_audio_b64(resp)
    assert got and got[0] == raw and "L16" in got[1]
    assert tts.find_audio_b64({"a": "short"}) is None


def test_rate_for_age_band_and_override():
    assert tts.rate_for("g1_5", None) == "-15%"
    assert tts.rate_for("g10_12", None) == "+0%"
    assert tts.rate_for("g10_12", "slow") == "-15%"
    assert tts.rate_for("g1_5", "normal") == "+0%"


def test_parse_retry_after():
    assert tts.parse_retry_after("Please retry in 17.5s.") == pytest.approx(18.5)
    assert tts.parse_retry_after('{"retryDelay": "30s"}') == pytest.approx(31.0)
    assert tts.parse_retry_after("nothing") == 25.0


def test_rate_limiter_waits_for_rolling_minute_and_penalty():
    now = [0.0]
    slept: list[float] = []

    def sleep(s):
        slept.append(s)
        now[0] += s

    rl = tts.RateLimiter(3, clock=lambda: now[0], sleep=sleep)
    for _ in range(3):
        rl.acquire()
    assert slept == []
    rl.acquire()  # 4th must wait for the first stamp to leave the 60 s window
    assert 59.9 <= sum(slept) <= 60.2
    slept.clear()
    rl.penalise(30)
    rl.acquire()
    assert sum(slept) >= 30


class FakeProv(tts.TtsProvider):
    def __init__(self, name, fail_voices=(), fail_all=False):
        self.name, self.fail_voices, self.fail_all, self.calls = name, set(fail_voices), fail_all, []

    def synthesize(self, text, *, lang, gender, voice, rate):
        self.calls.append((voice, rate))
        if self.fail_all or voice in self.fail_voices:
            raise tts.TtsError(f"{self.name} {voice} failed")
        return b"AUDIO" * 200, "mp3"


@pytest.fixture
def fake_audio(monkeypatch):
    monkeypatch.setattr(tts, "to_mp3", lambda data, ext, dest, **k: (dest.parent.mkdir(parents=True, exist_ok=True), dest.write_bytes(data)))
    monkeypatch.setattr(tts, "audio_duration", lambda p: 4.2)


def svc(tmp_path, edge, fallback=None):
    return tts.TtsService([edge] + ([fallback] if fallback else []), cache_dir=tmp_path / "cache", sleep=lambda s: None)


def test_tts_retries_same_voice_then_succeeds(tmp_path, fake_audio):
    class Flaky(FakeProv):
        def synthesize(self, text, **kw):
            self.calls.append(kw["voice"])
            if len(self.calls) < 3:
                raise tts.TtsError("flaky")
            return b"A" * 600, "mp3"

    edge = Flaky("edge-tts")
    clip = svc(tmp_path, edge).synthesize("Xin chào", lang="vi", age_band="g1_5")
    assert edge.calls == ["vi-VN-HoaiMyNeural"] * 3 and clip.voice == "vi-VN-HoaiMyNeural"


def test_tts_switches_voice_then_falls_back_to_gemini(tmp_path, fake_audio):
    edge = FakeProv("edge-tts", fail_voices={"vi-VN-HoaiMyNeural"})
    clip = svc(tmp_path, edge).synthesize("Xin chào", lang="vi", age_band="g10_12")
    assert clip.voice == "vi-VN-NamMinhNeural" and len(edge.calls) == 5  # 4 on the first voice (1 + 3 retries), then the other

    edge2, gem = FakeProv("edge-tts", fail_all=True), FakeProv("gemini-tts")
    clip2 = svc(tmp_path, edge2, gem).synthesize("Một câu khác", lang="vi", age_band="g10_12")
    assert clip2.provider == "gemini-tts" and clip2.voice == "Kore" and len(edge2.calls) == 5 and len(gem.calls) == 1
    assert any("fallback" in n for n in clip2.notes)

    with pytest.raises(tts.TtsError, match="all TTS providers failed"):
        svc(tmp_path, FakeProv("e", fail_all=True), FakeProv("g", fail_all=True)).synthesize("Câu ba", lang="vi", age_band="uni")


def test_tts_cache_hit_skips_providers_and_key_depends_on_rate(tmp_path, fake_audio):
    edge = FakeProv("edge-tts")
    s = svc(tmp_path, edge)
    s.synthesize("Chào em", lang="vi", age_band="g1_5")
    again = s.synthesize("Chào   em", lang="vi", age_band="g1_5", dest=tmp_path / "out" / "a.mp3")
    assert len(edge.calls) == 1 and again.cached and again.path.is_file()
    s.synthesize("Chào em", lang="vi", age_band="g10_12")  # different rate -> new synthesis
    assert [c[1] for c in edge.calls] == ["-15%", "+0%"]


def test_gemini_provider_honours_retry_in_and_wraps_pcm():
    pcm = b"\x02\x00" * 3000
    body = {"steps": [{"content": [{"data": base64.b64encode(pcm).decode(), "mime_type": "audio/L16;rate=24000"}]}]}
    seen = {"n": 0, "body": None}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["n"] += 1
        seen["body"] = json.loads(request.content)
        assert request.headers["x-goog-api-key"] == "k"
        return httpx.Response(429, text="quota. Please retry in 7s.") if seen["n"] == 1 else httpx.Response(200, json=body)

    now, slept = [0.0], []
    rl = tts.RateLimiter(3, clock=lambda: now[0], sleep=lambda s: (slept.append(s), now.__setitem__(0, now[0] + s)))
    g = tts.GeminiTtsProvider("k", limiter=rl, transport=httpx.MockTransport(handler))
    data, ext = g.synthesize("Xin chào", lang="vi", gender="female", voice="Kore", rate="-15%")
    assert ext == "wav" and data[:4] == b"RIFF" and seen["n"] == 2 and sum(slept) >= 8
    b = seen["body"]
    assert b["model"] == "gemini-3.8-flash-lite-tts" and b["response_format"] == {"type": "audio"}
    assert b["generation_config"]["speech_config"][0]["voice"] == "Kore"
    assert b["input"][0]["content"][0]["annotations"][0]["type"] == "speech_metadata"


# ------------------------------------------------------------------------------------------------------ video helpers

def test_vtt_generation():
    scenes = [{"start": 0.0, "narr_start": 0.6, "narr_dur": 4.0, "narration": "Câu một dài. Câu hai?"},
              {"start": 6.0, "narr_start": 0.6, "narr_dur": 2.0, "narration": "Chỉ một câu"}]
    vtt = video.build_vtt(scenes)
    assert vtt.startswith("WEBVTT")
    cues = [l for l in vtt.splitlines() if "-->" in l]
    assert len(cues) == 3
    assert cues[0].startswith("00:00:00.600 --> ") and cues[2] == "00:00:06.600 --> 00:00:08.600"
    assert cues[0].split(" --> ")[1] == cues[1].split(" --> ")[0]


TIMELINE_JSON = {"timeline": {"duration": 20, "tracks": [{"kind": "graphics", "rows": [
    {"elementId": "s1", "absStart": 0, "absEnd": 8, "file": "index.html", "children": [
        {"elementId": "s1-title", "absStart": 0.6, "absEnd": 8, "file": "compositions/s1.html"},
        {"elementId": "s1-arrow", "absStart": 3.0, "absEnd": 5.0, "file": "compositions/s1.html"}]},
    {"elementId": "s2", "absStart": 8, "absEnd": 20, "file": "index.html", "children": [
        {"elementId": "s2-field", "absStart": 8.5, "absEnd": 20, "file": "compositions/s2.html"}]},
    {"elementId": "narration", "absStart": 0, "absEnd": 20, "file": "index.html"}]}]}}


def test_timeline_lookup_for_revise():
    tl = video.flatten_timeline(TIMELINE_JSON)
    assert {e["element"] for e in tl} >= {"s1", "s1-arrow", "s2-field", "narration"}
    hit = video.find_element_at(tl, 4.0)
    assert hit["element"] == "s1-arrow" and hit["file"] == "compositions/s1.html"  # most specific
    assert video.find_element_at(tl, 7.0)["element"] == "s1-title"
    assert video.find_element_at(tl, 12.0)["file"] == "compositions/s2.html"
    assert video.find_element_at(tl, 8.2)["element"] == "s2"  # before s2's first element: the scene host itself


def test_scene_file_follows_the_hyperframes_contract():
    parts = video.parse_scene_reply(
        "```html\n<h1 id=\"s1-t\" class=\"clip\" data-start=\"0\" data-duration=\"4\">Xin chào</h1>\n```\n"
        "```css\n#s1-t{position:absolute}\n```\n"
        "```js\nconst tl = gsap.timeline({paused:true});\ntl.fromTo('#s1-t',{opacity:0},{opacity:1,duration:.4},0.3);\n"
        "window.__timelines['s1'] = tl;\n```")
    f = video.scene_file("s1", parts, ["@font-face{font-family:'Lexend'}"])
    assert f.startswith("<template>") and f.rstrip().endswith("</template>")
    assert f.count("gsap.timeline(") == 1 and f.count("__timelines") == 1 and 'window.__timelines["s1"] = tl;' in f
    assert 'data-composition-id="s1"' in f and "tl.fromTo" in f
    idx = video.index_html([{"id": "s1", "start": 0, "duration": 5}], 5, "T", "vi")
    assert 'id="s1"' in idx and 'data-composition-id="s1"' in idx and 'data-composition-src="compositions/s1.html"' in idx
    assert 'data-width="1280"' in idx and 'id="narration"' in idx
    with pytest.raises(MediaError):
        video.parse_scene_reply("no blocks")


# ------------------------------------------------------------------------------------------------------ SVG

GOOD_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100"/><circle r="5"/><path d="M0 0"/><g/></svg>'


def test_svg_sanity():
    assert illustrate.validate_svg(GOOD_SVG, allow_text=False) is None
    with_text = GOOD_SVG.replace("<g/>", "<text>+q</text>")
    assert "no <text>" in illustrate.validate_svg(with_text, allow_text=False)
    assert illustrate.validate_svg(with_text, allow_text=True) is None  # diagrams may carry labels
    assert "invalid XML" in illustrate.validate_svg("<svg><g></svg>", allow_text=False)
    assert "script" in illustrate.validate_svg(GOOD_SVG.replace("<g/>", "<script>1</script>"), allow_text=True)
    assert "external" in illustrate.validate_svg(GOOD_SVG.replace("<g/>", '<g fill="url(http://x/y)"/>'), allow_text=True)
    assert "viewBox" in illustrate.validate_svg(GOOD_SVG.replace(' viewBox="0 0 100 100"', ""), allow_text=False)


def test_diagram_script_sandboxing():
    assert "import os" in illustrate.validate_script("import os") or "not allowed" in illustrate.validate_script("import os")
    assert illustrate.validate_script("print(open('x').read())")
    assert illustrate.validate_script("print((1).__class__)")
    assert illustrate.validate_script("import math\nprint(math.pi)") is None
    svg = illustrate.run_diagram_script(f"import math\nprint('''{GOOD_SVG}''')")
    assert svg.startswith("<svg")
    with pytest.raises(MediaError):
        illustrate.run_diagram_script("raise ValueError('x')")


class FakeClient:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def complete(self, alias, messages, **kw):
        self.calls.append((str(alias), messages))
        return self.replies.pop(0)

    def close(self):
        pass


def fake_raster(monkeypatch):
    def rast(svg, png, w, h, **k):
        png.parent.mkdir(parents=True, exist_ok=True)
        from PIL import Image
        Image.new("RGB", (w, h), "#F7F1E3").save(png)

    monkeypatch.setattr(illustrate, "rasterize_svg", rast)


def test_cover_flow_with_one_critique_regeneration(tmp_path, monkeypatch):
    fake_raster(monkeypatch)
    bad = "IDEA: a\n```svg\n" + GOOD_SVG.replace("<g/>", "<text>hi</text>") + "\n```"
    ok = "IDEA: ten-frame of apples\n```svg\n" + GOOD_SVG + "\n```"
    c = FakeClient([ok, '{"ok": false, "defects": ["glyph is a blob"]}', ok])
    r = rm.render_media(req("cover", {"title": "Toán 1", "subject": "Toán", "idea": "đếm táo"}, id="cv"), tmp_path, client=c)
    assert r.files[0].path == "images/cv.webp" and r.files[0].file.is_file() and r.files[0].mime == "image/webp"
    assert "regenerated once after critique" in r.notes
    assert "<text" not in (r.source_dir / "source.svg").read_text()
    assert "mentor-reasoning" in c.calls[0][0] or "REASONING" in c.calls[0][0].upper()
    assert "glyph is a blob" in c.calls[2][1][-1]["content"]
    # an invalid first SVG (has <text>) is bounced back to the model before anything is rasterised
    c2 = FakeClient([bad, ok, '{"ok": true, "defects": []}'])
    r2 = rm.render_media(req("cover", {"title": "T", "subject": "Toán", "idea": "i"}, id="cv2"), tmp_path, client=c2)
    assert "critique: ok" in r2.notes and "rejected" in c2.calls[1][1][-1]["content"]


def test_diagram_flow_retries_failed_script(tmp_path):
    script_bad = "IDEA: x\n```python\nimport os\nprint(1)\n```"
    script_ok = f"IDEA: two charges\n```python\nprint('''{GOOD_SVG}''')\n```"
    c = FakeClient([script_bad, script_ok])
    r = rm.render_media(req("diagram", {"description": "two like charges", "labels": ["+q", "+q"]}, id="dg"), tmp_path, client=c)
    assert r.files[0].mime == "image/svg+xml" and (r.source_dir / "diagram.py").is_file()


def test_svg_revise_edits_around_point(tmp_path):
    src = tmp_path / "prev"
    src.mkdir()
    (src / "source.svg").write_text(GOOD_SVG, encoding="utf-8")
    new = GOOD_SVG.replace("<g/>", '<circle cx="50" cy="50" r="9"/>')
    c = FakeClient([f"```svg\n{new}\n```"])
    r = rm.render_media(req("picture", {"description": "apple"}, id="pc",
                            revise={"comment": "bigger apple", "x": 0.5, "y": 0.25, "source_dir": str(src)}), tmp_path / "o", client=c)
    assert 'r="9"' in r.files[0].file.read_text(encoding="utf-8")
    assert "x=50, y=25" in c.calls[0][1][-1]["content"]  # fractions mapped into the SVG viewBox (100x100)


def test_rasterize_svg_retries_chrome_timeouts(tmp_path, monkeypatch):
    import subprocess

    from mentor_course_builder import illustrate

    svg = tmp_path / "a.svg"
    svg.write_text("<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'/>")
    calls = []

    def fake_run(cmd, capture_output=True, timeout=0):
        calls.append(1)
        if len(calls) < 3:
            raise subprocess.TimeoutExpired(cmd, timeout)
        shot = next(a.split("=", 1)[1] for a in cmd if a.startswith("--screenshot="))
        Path(shot).write_bytes(b"png")

    monkeypatch.setattr(illustrate, "find_chrome", lambda: "chrome")
    monkeypatch.setattr(illustrate.subprocess, "run", fake_run)
    illustrate.rasterize_svg(svg, tmp_path / "o.png", 10, 10)
    assert len(calls) == 3 and (tmp_path / "o.png").read_bytes() == b"png"
    calls.clear()
    monkeypatch.setattr(illustrate.subprocess, "run", lambda cmd, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired(cmd, 1)))
    with pytest.raises(illustrate.MediaError):
        illustrate.rasterize_svg(svg, tmp_path / "o2.png", 10, 10)
