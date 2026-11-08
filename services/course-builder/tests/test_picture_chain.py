"""Picture-source chain: fakes only, no network. One live smoke test at the bottom (opt-in, marked `live`)."""

import base64
import hashlib
import json
import os
from io import BytesIO

import httpx
import pytest
from mentor_course_builder import illustrate, picture_chain as pc, picture_sources as ps, render_media as rm
from mentor_course_builder.contracts import MediaRequest
from mentor_course_builder.media import MediaError
from PIL import Image


def req(kind="illustration", spec=None, **kw):
    return MediaRequest(id=kw.pop("id", "p1"), kind=kind, course_id="c1", age_band=kw.pop("age_band", "g1_5"),
                        language=kw.pop("language", "vi"), spec=spec or {"description": "a puppy beside a basket of apples"}, **kw)


def png(w=1024, h=704, color=(240, 200, 120)):
    b = BytesIO()
    Image.new("RGB", (w, h), color).save(b, "PNG")
    return b.getvalue()


class Critic:
    """Answers the plan call (CHAT) and the vision review (VISION); `verdicts` is consumed in order."""

    def __init__(self, verdicts):
        self.verdicts, self.calls = list(verdicts), []

    def complete(self, alias, messages, **kw):
        self.calls.append((str(alias), messages))
        if "VISION" in str(alias).upper():
            return self.verdicts.pop(0)
        return json.dumps({"prompt": "a happy puppy sitting next to a woven basket of red apples", "query": "puppy apples basket",
                           "expected": "a puppy and a basket with apples"})

    def close(self):
        pass


OK = '{"ok": true, "score": 9, "defects": []}'
BAD = '{"ok": false, "score": 3, "defects": ["there is text in the picture"]}'


class FakeGen(ps.Generator):
    name = "fakegen"

    def __init__(self, data=None, error=None):
        self.data, self.error, self.prompts = data if data is not None else png(), error, []

    def available(self):
        return True

    def generate(self, http, prompt, w, h, seed):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return ps.Fetched(self.data, self.name, "generated", "fake-model")


class FakeWeb(ps.WebSource):
    name = "fakeweb"

    def __init__(self, cands):
        self.cands, self.fetched, self.query = cands, [], ""

    def search(self, http, query, limit):
        self.query = query
        return self.cands

    def fetch(self, http, c):
        self.fetched.append(c.url)
        return png(800, 600, (90, 160, 90))


def cand(url="https://x/a.png", lic="by", author="Ann"):
    return ps.Candidate("fakeweb", url, "Apples", author, lic, "https://creativecommons.org/licenses/by/4.0/", "https://x/page", 800, 600)


@pytest.fixture
def sources(monkeypatch):
    ps.reset_trips()
    monkeypatch.setenv("IMAGE_SOURCES", "fakegen,fakeweb,code")
    gen, web = FakeGen(), FakeWeb([cand()])
    monkeypatch.setitem(ps.GENERATORS, "fakegen", gen)
    monkeypatch.setitem(ps.WEB_SOURCES, "fakeweb", web)
    yield gen, web
    ps.reset_trips()


def dead_http():
    return httpx.Client(transport=httpx.MockTransport(lambda q: httpx.Response(500)))


def run(r, tmp_path, client):
    return pc.try_raster_sources(r, tmp_path, client, http=dead_http())


# ------------------------------------------------------------------------------------------------ policy

def test_accuracy_requests_stay_code_drawn(sources):
    assert pc.plan_sources(req("diagram", {"description": "field lines"})) == []
    assert pc.plan_sources(req("cover", {"title": "Điện trường", "subject": "Vật lí", "idea": "đường sức"})) == []
    assert pc.plan_sources(req("picture", {"description": "apples", "count": 7})) == []
    assert pc.plan_sources(req("illustration", {"description": "x", "math": "y=x^2"})) == []
    assert pc.plan_sources(req("illustration", {"description": "x"}, id="a")) == ["fakegen", "fakeweb"]
    assert pc.plan_sources(req("cover", {"title": "Toán 1", "subject": "Toán", "idea": "quả táo"})) == ["fakegen", "fakeweb"]
    # a request may opt in or out explicitly
    assert pc.plan_sources(req("illustration", {"description": "x", "source": "code"})) == []
    assert pc.plan_sources(req("illustration", {"description": "x", "source": "web"})) == ["fakeweb"]
    assert pc.plan_sources(req("cover", {"title": "t", "subject": "Vật lí", "idea": "i", "source": "gen"})) == ["fakegen"]


def test_source_order_configuration(monkeypatch):
    ps.reset_trips()
    for k in ("IMAGE_API_BASE", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN", "PEXELS_API_KEY", "PIXABAY_API_KEY",
              "POLLINATIONS_API_KEY", "IMAGE_GEMINI_ENABLE", "IMAGE_POLLINATIONS_ANON", "GEMINI_API_KEY"):
        monkeypatch.setenv(k, "")
    monkeypatch.setenv("IMAGE_SOURCES", "auto")
    assert ps.source_order() == ["hf_space", "openverse", "wikimedia", "code"]  # keyless defaults
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acc")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok-0123456789")
    monkeypatch.setenv("PEXELS_API_KEY", "pex-0123456789")
    assert ps.source_order() == ["cloudflare", "hf_space", "pexels", "openverse", "wikimedia", "code"]
    assert ps.source_order("gen") == ["cloudflare", "hf_space", "code"]
    monkeypatch.setenv("IMAGE_SOURCES", "openverse,cloudflare")
    assert ps.source_order() == ["openverse", "cloudflare", "code"]
    monkeypatch.setenv("IMAGE_SOURCES", "code,openverse")
    assert pc.plan_sources(req("illustration")) == []  # code listed first: SVG only
    monkeypatch.setenv("IMAGE_SOURCES", "svg")
    assert ps.source_order() == ["code"]
    ps.trip("hf_space")
    monkeypatch.setenv("IMAGE_SOURCES", "auto")
    assert "hf_space" not in ps.source_order()
    ps.reset_trips()


# ------------------------------------------------------------------------------------------------ the chain

def test_generated_image_is_reviewed_and_stored_as_webp(sources, tmp_path):
    gen, _ = sources
    res, notes = run(req(), tmp_path, Critic([OK]))
    f = res.files[0]
    assert f.path == "images/p1.webp" and f.mime == "image/webp" and f.file.is_file()
    assert Image.open(f.file).format == "WEBP"
    assert res.meta["sha256"] == hashlib.sha256(f.file.read_bytes()).hexdigest() and res.meta["bytes"] == f.file.stat().st_size
    assert res.meta["kind"] == "generated" and res.meta["provider"] == "fakegen" and res.meta["attribution"] is None
    assert json.loads((res.source_dir / "image.json").read_text(encoding="utf-8"))["sha256"] == res.meta["sha256"]
    assert "no text" in gen.prompts[0] and "children" in gen.prompts[0] and "puppy" in gen.prompts[0]
    assert "illustration: generated image via fakegen" in res.notes
    assert any("fakegen score 9" in n for n in notes)


def test_failed_critique_regenerates_with_feedback_then_falls_to_web(sources, tmp_path):
    gen, web = sources
    res, _ = run(req(), tmp_path, Critic([BAD, BAD, OK]))  # two generated tries rejected, the web candidate approved
    assert len(gen.prompts) == 2 and "there is text in the picture" in gen.prompts[1]
    assert res.meta["kind"] == "web" and res.meta["provider"] == "fakeweb"
    assert res.meta["attribution"] == {"provider": "fakeweb", "title": "Apples", "author": "Ann", "license": "by",
                                       "license_url": "https://creativecommons.org/licenses/by/4.0/", "source_url": "https://x/page"}
    assert web.query == "puppy apples basket"


def test_web_licence_filter_and_unreviewed_web_images_are_rejected(sources, tmp_path):
    gen, web = sources
    gen.error = ps.ProviderError("no network")
    web.cands = [cand("https://x/nc.png", lic="by-nc"), cand("https://x/nd.png", lic="by-nd")]
    res, notes = run(req(), tmp_path, Critic([]))
    assert res is None and web.fetched == [] and any("found no usable" in n for n in notes)
    web.cands = [cand("https://x/ok.png", lic="cc0")]

    class NoCritic(Critic):
        def complete(self, alias, messages, **kw):
            if "VISION" in str(alias).upper():
                raise pc.ModelError("down")
            return super().complete(alias, messages, **kw)

    res, notes = run(req(), tmp_path, NoCritic([]))
    assert res is None and any("critic unavailable" in n for n in notes)  # a web image nobody checked is never used
    gen.error = None
    res, notes = run(req(), tmp_path, NoCritic([]))  # a generated one is accepted, with a note
    assert res.meta["provider"] == "fakegen" and any("without review" in n for n in notes)


def test_fatal_provider_error_trips_it_for_later_requests(sources, tmp_path):
    gen, web = sources
    gen.error = ps.ProviderError("quota", fatal=True)
    res, _ = run(req(), tmp_path, Critic([OK]))
    assert res.meta["provider"] == "fakeweb" and ps.is_tripped("fakegen")
    gen.prompts.clear()
    run(req(id="p2"), tmp_path, Critic([OK]))
    assert gen.prompts == []  # not called again


def test_nothing_available_falls_back_to_code_drawn_svg(sources, tmp_path, monkeypatch):
    gen, web = sources
    gen.error, web.cands = ps.ProviderError("down"), []

    def rast(svg, out, w, h, **k):
        out.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (w, h), "#F7F1E3").save(out)

    monkeypatch.setattr(illustrate, "rasterize_svg", rast)
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100"/><circle r="5"/><path d="M0 0"/><g/></svg>'

    class C(Critic):
        def complete(self, alias, messages, **kw):
            if "REASONING" in str(alias).upper():
                return f"IDEA: apples\n```svg\n{svg}\n```"
            return super().complete(alias, messages, **kw)

    monkeypatch.setattr(ps, "make_http", dead_http)
    r = rm.render_media(req(), tmp_path, client=C([OK]))
    assert r.files[0].path == "images/p1.webp" and r.meta is None
    assert "illustration: deepseek svg" in r.notes and any("code-drawn SVG used" in n for n in r.notes)
    assert (r.source_dir / "source.svg").is_file()


def test_picture_kind_is_square_webp_and_cover_is_cropped(sources, tmp_path):
    sources[0].data = png(1024, 1024)  # square generator output: pictures keep it, covers are centre-cropped to 1.6
    res, _ = run(req("picture", {"description": "a red apple"}, id="pk"), tmp_path, Critic([OK]))
    assert Image.open(res.files[0].file).size == (400, 400)
    res, _ = run(req("cover", {"title": "Toán 1", "subject": "Toán", "idea": "quả táo"}, id="cv"), tmp_path, Critic([OK]))
    assert Image.open(res.files[0].file).size == (1024, 640)  # 1.6 aspect kept, not upscaled


def test_encode_webp_caps_size_and_rejects_tiny_or_corrupt(monkeypatch):
    noisy = Image.frombytes("RGB", (1200, 800), os.urandom(1200 * 800 * 3))
    b = BytesIO()
    noisy.save(b, "PNG")
    monkeypatch.setenv("IMAGE_MAX_BYTES", "150000")
    data, w, h = pc.encode_webp(b.getvalue(), "illustration")
    assert len(data) <= 150000 and w <= 1200
    with pytest.raises(ps.ProviderError, match="too small"):
        pc.encode_webp(png(100, 100), "illustration")
    with pytest.raises(ps.ProviderError, match="cannot decode"):
        pc.encode_webp(b"<html>nope</html>", "illustration")


# ------------------------------------------------------------------------------------------------ revise

def test_revise_regenerates_with_comment_and_point(sources, tmp_path):
    gen, _ = sources
    res, _ = run(req(), tmp_path / "v1", Critic([OK]))
    gen.prompts.clear()
    r2 = req(revise={"comment": "make the apples red", "x": 0.8, "y": 0.2, "source_dir": str(res.source_dir)})
    out = pc.revise_picture(r2, tmp_path / "v2", Critic([OK]), http=dead_http())
    assert "make the apples red" in gen.prompts[0] and "top right" in gen.prompts[0]
    assert out.files[0].file.is_file() and out.notes[0].startswith("revised by regenerating")
    # a source dir without image.json is an SVG revision: not handled here
    assert pc.revise_picture(req(revise={"comment": "x", "source_dir": str(tmp_path)}), tmp_path, None) is None


def test_revise_without_generator_is_a_clear_error(sources, tmp_path, monkeypatch):
    res, _ = run(req(), tmp_path / "v1", Critic([OK]))
    monkeypatch.setenv("IMAGE_SOURCES", "fakeweb,code")
    with pytest.raises(MediaError, match="no image generator"):
        pc.revise_picture(req(revise={"comment": "x", "source_dir": str(res.source_dir)}), tmp_path / "v2", Critic([]),
                          http=dead_http())


# ------------------------------------------------------------------------------------------------ providers (mock HTTP)

def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_openverse_parsing_and_licence_filter():
    seen = {}

    def handler(q):
        seen.update(dict(q.url.params))
        return httpx.Response(200, json={"results": [
            {"url": "https://f/1.jpg", "title": "A", "creator": "Bo", "license": "by", "license_version": "2.0",
             "license_url": "https://cc/by/2.0", "foreign_landing_url": "https://flickr/1", "width": 800, "height": 600},
            {"url": "https://f/2.jpg", "title": "B", "creator": "Cy", "license": "by-nc", "license_version": "2.0"},
            {"url": "https://f/3.jpg", "title": "C", "creator": None, "license": "cc0", "license_version": "1.0"}]})

    out = ps.OpenverseSource().search(client_for(handler), "apple", 4)
    assert [c.license for c in out] == ["by", "cc0"] and out[0].author == "Bo" and out[0].source_url == "https://flickr/1"
    assert seen["mature"] == "false" and "by-nc" not in seen["license"]


def test_wikimedia_parsing_normalises_licence_and_strips_html():
    page = {"title": "File:Red apple.jpg", "imageinfo": [{"mime": "image/jpeg", "thumburl": "https://t/a.jpg", "thumbwidth": 1280,
            "thumbheight": 960, "descriptionurl": "https://commons/File:Red_apple.jpg", "extmetadata": {
                "LicenseShortName": {"value": "CC BY-SA 4.0"}, "LicenseUrl": {"value": "https://cc/by-sa/4.0"},
                "Artist": {"value": '<a href="//u">Jane &amp; Co</a>'}}}]}
    nc = {"title": "File:nc.jpg", "imageinfo": [{"mime": "image/jpeg", "thumburl": "https://t/b.jpg", "extmetadata": {
        "LicenseShortName": {"value": "All rights reserved"}}}]}
    svg = {"title": "File:x.svg", "imageinfo": [{"mime": "image/svg+xml", "thumburl": "https://t/c.png", "extmetadata": {
        "LicenseShortName": {"value": "CC0"}}}]}
    body = {"query": {"pages": {"1": page, "2": nc, "3": svg}}}
    out = ps.WikimediaSource().search(client_for(lambda q: httpx.Response(200, json=body)), "apple", 3)
    assert len(out) == 1 and out[0].license == "by-sa" and out[0].author == "Jane & Co" and out[0].source_url.endswith("Red_apple.jpg")
    assert ps.normalise_license("Public domain") == "pdm" and ps.normalise_license("CC0") == "cc0"
    assert ps.normalise_license("CC BY-NC 2.0") == "by-nc" and ps.normalise_license("GFDL") == ""


def test_generators_parse_replies_and_never_leak_keys(monkeypatch):
    img = png(64, 64)
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cf-secret-token-123")
    seen = {}

    def cf(q):
        seen["auth"], seen["url"] = q.headers["authorization"], str(q.url)
        return httpx.Response(200, json={"result": {"image": base64.b64encode(img).decode()}, "success": True})

    got = ps.CloudflareGenerator().generate(client_for(cf), "p", 1024, 704, 1)
    assert got.data == img and "flux-1-schnell" in seen["url"] and seen["auth"] == "Bearer cf-secret-token-123"

    monkeypatch.setenv("IMAGE_API_BASE", "https://img.local/v1")
    monkeypatch.setenv("IMAGE_API_KEY", "oa-secret-key-456")
    ok = httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(img).decode()}]})
    assert ps.OpenAICompatGenerator().generate(client_for(lambda q: ok), "p", 512, 512, 1).data == img

    monkeypatch.setenv("GEMINI_API_KEY", "gem-secret-key-789")
    monkeypatch.setenv("IMAGE_GEMINI_ENABLE", "1")
    body = {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "image/png", "data": base64.b64encode(img).decode()}}]}}]}
    assert ps.GeminiGenerator().generate(client_for(lambda q: httpx.Response(200, json=body)), "p", 512, 512, 1).data == img
    with pytest.raises(ps.ProviderError) as e:  # free-tier key: quota 0 -> fatal, and the message has no key
        ps.GeminiGenerator().generate(client_for(lambda q: httpx.Response(429, text="quota gem-secret-key-789")), "p", 512, 512, 1)
    assert e.value.fatal and "gem-secret-key-789" not in str(e.value)
    with pytest.raises(ps.ProviderError) as e:
        ps.CloudflareGenerator().generate(client_for(lambda q: httpx.Response(400, text="bad cf-secret-token-123")), "p", 1, 1, 1)
    assert "cf-secret-token-123" not in str(e.value)

    def boom(q):
        raise httpx.ConnectError("x")

    with pytest.raises(ps.ProviderError):  # a network failure is a ProviderError, not a crash
        ps.CloudflareGenerator().generate(client_for(boom), "p", 1, 1, 1)


def test_hf_space_gradio_flow():
    img = png(64, 64)
    base = "https://black-forest-labs-flux-1-schnell.hf.space"

    def handler(q):
        u = str(q.url)
        if u.endswith("/call/infer"):
            assert json.loads(q.content)["data"][3:5] == [1024, 704]
            return httpx.Response(200, json={"event_id": "e1"})
        if u.endswith("/call/infer/e1"):
            return httpx.Response(200, text=f'event: complete\ndata: [{{"url": "{base}/gradio_api/file=/tmp/i.webp"}}]\n\n')
        return httpx.Response(200, content=img, headers={"content-type": "image/webp"})

    assert ps.HFSpaceGenerator().generate(client_for(handler), "p", 1024, 700, 5).data == img

    def err(q):
        if q.method == "POST":
            return httpx.Response(200, json={"event_id": "e"})
        return httpx.Response(200, text="event: error\ndata: null\n\n")

    with pytest.raises(ps.ProviderError) as e:
        ps.HFSpaceGenerator().generate(client_for(err), "p", 1024, 704, 5)
    assert e.value.fatal


def test_download_refuses_http_and_non_images():
    with pytest.raises(ps.ProviderError, match="non-https"):
        ps.download(client_for(lambda q: httpx.Response(200)), "http://x/a.jpg", "t")
    with pytest.raises(ps.ProviderError, match="not an image"):
        ps.download(client_for(lambda q: httpx.Response(200, text="<html>", headers={"content-type": "text/html"})), "https://x/a", "t")


# ------------------------------------------------------------------------------------------------ live (opt-in)

@pytest.mark.live
def test_live_picture_chain_real_sources(tmp_path, monkeypatch):
    """Real image source + real vision critique. Run: MENTOR_LIVE_BUILDER=1 pytest -m live tests/test_picture_chain.py
    (needs .env.dev.local; uses IMAGE_SOURCES / keys when configured, else the keyless Hugging Face Space, then Openverse
    and Wikimedia)."""
    from mentor_course_builder.llm import ModelClient

    monkeypatch.setenv("COURSE_BUILDER_DIRECT", os.environ.get("COURSE_BUILDER_DIRECT", "1"))
    monkeypatch.setenv("IMAGE_SOURCES", os.environ.get("MENTOR_LIVE_IMAGE_SOURCES", "auto"))
    ps.reset_trips()
    client = ModelClient.from_env()
    try:
        res, notes = pc.try_raster_sources(
            req("illustration", {"description": "a happy puppy sitting beside a basket of red apples"}, id="live-pic"),
            tmp_path, client)
    finally:
        client.close()
    assert res is not None, notes
    assert res.files[0].file.stat().st_size <= 400_000 and Image.open(res.files[0].file).format == "WEBP"
    assert res.meta["sha256"] and res.meta["provider"]
