"""Opt-in: `uv run --package mentor-course-builder pytest -m live` (needs .env.dev.local; calls the real model)."""

import os

import pytest
from mentor_course_builder.llm import ModelClient
from mentor_course_builder.models import Page
from mentor_course_builder.quality import check_page
from synth import clean_page


@pytest.mark.live
def test_live_vision_page(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSE_BUILDER_DIRECT", os.environ.get("COURSE_BUILDER_DIRECT", "1"))
    client = ModelClient.from_env()
    p = tmp_path / "p.jpg"
    clean_page().save(p)
    c = check_page(Page("p.jpg", 1, "image", image_path=str(p)), client)
    assert c.ok and c.text and "quick brown fox" in c.text.lower()


# ---- media stage (P3-C): opt-in, real network / model / Chrome / HyperFrames ------------------------------------------

def _mreq(kind, spec, **kw):
    from mentor_course_builder.contracts import MediaRequest

    return MediaRequest(id=kw.pop("id", f"live-{kind}"), kind=kind, course_id="c", age_band=kw.pop("age_band", "g10_12"),
                        language=kw.pop("language", "vi"), spec=spec)


@pytest.mark.live
def test_live_tts_edge_vi(tmp_path):
    from mentor_course_builder.render_media import render_media
    from mentor_course_builder.tts import TtsService

    r = render_media(_mreq("tts", {"text": "Chào các em, hôm nay chúng ta học về điện trường."}, age_band="g1_5"), tmp_path,
                     tts=TtsService(cache_dir=tmp_path / "cache"))
    assert r.files[0].file.stat().st_size > 2000 and 2 < r.duration_s < 15


@pytest.mark.live
def test_live_cover_toan(tmp_path, monkeypatch):
    from mentor_course_builder.render_media import render_media

    monkeypatch.setenv("COURSE_BUILDER_DIRECT", os.environ.get("COURSE_BUILDER_DIRECT", "1"))
    r = render_media(_mreq("cover", {"title": "Toán 1: Các số đến 10", "subject": "Toán", "idea": "nhóm đồ vật đếm được từ 1 đến 10"},
                           age_band="g1_5"), tmp_path)
    assert r.files[0].file.suffix == ".webp" and "<text" not in (r.source_dir / "source.svg").read_text(encoding="utf-8")


@pytest.mark.live
def test_live_diagram_two_like_charges(tmp_path, monkeypatch):
    from mentor_course_builder.render_media import render_media

    monkeypatch.setenv("COURSE_BUILDER_DIRECT", os.environ.get("COURSE_BUILDER_DIRECT", "1"))
    r = render_media(_mreq("diagram", {"description": "Đường sức điện của hai điện tích dương bằng nhau", "labels": ["+q", "+q"]}), tmp_path)
    assert r.files[0].file.suffix == ".svg"


@pytest.mark.live
def test_live_video_three_scenes(tmp_path, monkeypatch):
    from mentor_course_builder.render_media import render_media

    monkeypatch.setenv("COURSE_BUILDER_DIRECT", os.environ.get("COURSE_BUILDER_DIRECT", "1"))
    scenes = [{"caption": f"Cảnh {i}", "narration": "Đường sức điện cho ta biết hướng của lực điện.", "visual": "Một điện tích dương màu san hô, các đường sức tỏa ra."}
              for i in (1, 2, 3)]
    r = render_media(_mreq("video", {"title": "Đường sức điện", "target_s": 25, "scenes": scenes}), tmp_path)
    assert r.files[0].file.stat().st_size > 20_000 and r.timeline


@pytest.mark.live
def test_live_outline_and_lesson(monkeypatch):
    """Opt-in: real outline + one lesson (no DeepTutor sidecar) from a few lines of physics."""
    from mentor_course_builder.intake import IntakeResult
    from mentor_course_builder.lessons import write_lesson
    from mentor_course_builder.models import Material
    from mentor_course_builder.outline import build_outline

    monkeypatch.setenv("COURSE_BUILDER_DIRECT", os.environ.get("COURSE_BUILDER_DIRECT", "1"))
    client = ModelClient.from_env()
    text = ("Đường sức điện là đường vẽ trong điện trường sao cho tiếp tuyến tại mỗi điểm trùng với hướng của vectơ "
            "cường độ điện trường. Đường sức đi ra từ điện tích dương, đi vào điện tích âm. Các đường sức không cắt nhau.")
    intake = IntakeResult(materials=[Material("b.pdf", "pdf", [Page("b.pdf", 1, "pdf_text", text=text)])])
    o = build_outline(intake, client, teacher_note="lớp 11")
    assert o.age_band == "g10_12" and o.language == "vi" and o.lessons()
    d = write_lesson(o, o.lessons()[0], client, {"b.pdf#1": text})
    assert d.lesson.blocks
