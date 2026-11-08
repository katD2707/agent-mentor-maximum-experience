import json
import subprocess
import wave

import pytest
from mentor_course_builder import documents
from mentor_course_builder.intake import IntakeOptions, intake, write_outputs
from mentor_course_builder.llm import ModelError
from mentor_course_builder.media import find_ffmpeg
from synth import blurred, clean_page

VISION_OK = {"readable": True, "readable_fraction": 0.98, "reason_vi": "", "reason_en": "", "text": "# Trang\n$x^2$"}


class FakeClient:
    """Stands in for ModelClient: canned vision JSON / transcript, records the alias of every call."""

    def __init__(self, vision=None, transcript="Xin chào các em"):
        self.calls = []
        self.vision = vision or VISION_OK
        self.transcript = transcript

    def complete(self, alias, messages, **kw):
        self.calls.append(alias.value)
        if alias.value == "mentor-vision":
            return "```json\n" + json.dumps(self.vision) + "\n```"
        return self.transcript


def opts(**kw):
    return IntakeOptions(workers=1, **kw)


def test_images_jpg_png_webp_heic(tmp_path):
    import pillow_heif

    pillow_heif.register_heif_opener()
    img = clean_page()
    files = []
    for ext in ("jpg", "png", "webp", "heic"):
        f = tmp_path / f"p.{ext}"
        img.save(f)
        files.append(f)
    c = FakeClient()
    r = intake(files, tmp_path / "out", client=c, options=opts())
    assert [m.kind for m in r.materials] == ["image"] * 4
    assert [m.pages[0].index for m in r.materials] == [1, 2, 3, 4]
    exts = [m.pages[0].image_path.rsplit(".", 1)[1] for m in r.materials]
    assert exts == ["jpg", "png", "jpg", "jpg"]  # heic and webp are normalised to jpg
    assert all(c_.ok and c_.text for c_ in r.checks)
    assert r.materials[0].pages[0].text == "# Trang\n$x^2$"
    assert c.calls == ["mentor-vision"] * 4


def test_blurry_photo_listed_for_retake_even_if_model_says_readable(tmp_path):
    f = tmp_path / "blur.jpg"
    blurred(clean_page(), 5).save(f)
    r = intake([f], tmp_path / "o", client=FakeClient(), options=opts())
    assert len(r.retake) == 1 and r.retake[0].reasons == ["blurry"]
    assert "cần chụp lại" in r.summary() and "Ảnh 1 (blur.jpg)" in r.summary()
    write_outputs(r, tmp_path / "o")
    assert json.loads((tmp_path / "o" / "checks.json").read_text("utf-8"))[0]["ok"] is False


def test_model_unreadable_fails_page(tmp_path):
    f = tmp_path / "x.jpg"
    clean_page().save(f)
    v = {"readable": False, "readable_fraction": 0.4, "reason_vi": "Chữ bị che", "reason_en": "text covered", "text": "a"}
    r = intake([f], tmp_path / "o", client=FakeClient(vision=v), options=opts())
    c = r.checks[0]
    assert c.reasons == ["model_unreadable"] and "Chữ bị che" in c.message_vi


def test_model_error_does_not_crash(tmp_path):
    class Boom(FakeClient):
        def complete(self, *a, **k):
            raise ModelError("down")

    f = tmp_path / "x.jpg"
    clean_page().save(f)
    r = intake([f], tmp_path / "o", client=Boom(), options=opts())
    assert r.checks[0].ok and r.checks[0].metrics["model_error"] == 1.0 and r.checks[0].text is None


def make_text_pdf(path, text="Hello world this is a page with enough text"):
    body = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(body) + body + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offs)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n" % (len(objs) + 1, xref) + b"%%EOF"
    path.write_bytes(out)


def test_pdf_text_page_and_scanned_page_routing(tmp_path, monkeypatch):
    monkeypatch.setattr(documents, "docling_pages", lambda p: {1: "# Hello\ntext layer"})
    text_pdf = tmp_path / "t.pdf"
    make_text_pdf(text_pdf)
    scan_pdf = tmp_path / "s.pdf"
    clean_page(800, 1100).save(scan_pdf)  # image-only PDF = scan
    c = FakeClient()
    r = intake([text_pdf, scan_pdf], tmp_path / "o", client=c, options=opts())
    t, s = r.materials
    assert t.pages[0].kind == "pdf_text" and t.pages[0].text == "# Hello\ntext layer" and t.pages[0].image_path is None
    assert s.pages[0].kind == "scanned_pdf" and s.pages[0].image_path.endswith(".jpg")
    assert c.calls == ["mentor-vision"]  # only the scanned page reaches the model
    assert r.checks[0].ok and r.checks[0].text == "# Hello\ntext layer"
    assert s.pages[0].text == "# Trang\n$x^2$"


def test_docx_and_pptx_use_docling(tmp_path, monkeypatch):
    md = {1: "# Chương 1\nA\n\n## Bài 1\nB", 2: "# Slide 2\nC"}
    monkeypatch.setattr(documents, "docling_pages", lambda p: md)
    monkeypatch.setattr(documents, "render_slides", lambda *a, **k: {})
    d, p = tmp_path / "a.docx", tmp_path / "b.pptx"
    d.write_bytes(b"x")
    p.write_bytes(b"x")
    r = intake([d, p], tmp_path / "o", client=None, options=opts())
    docx, pptx = r.materials
    assert [pg.kind for pg in docx.pages] == ["docx_section"] * 3 and docx.pages[0].text.startswith("# Chương 1")
    assert [pg.kind for pg in pptx.pages] == ["slide", "slide"] and pptx.pages[1].text.startswith("# Slide 2")
    assert any("LibreOffice" in n for n in pptx.notes)
    assert all(c.ok for c in r.checks)


def test_unsupported_and_failing_file_do_not_stop_batch(tmp_path):
    bad = tmp_path / "x.xyz"
    bad.write_bytes(b"1")
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"not a pdf")
    good = tmp_path / "g.jpg"
    clean_page().save(good)
    r = intake([bad, broken, good], tmp_path / "o", client=FakeClient(), options=opts())
    assert r.materials[0].notes and r.materials[1].notes and r.materials[2].pages


needs_ffmpeg = pytest.mark.skipif(find_ffmpeg() is None, reason="ffmpeg not available")


def make_wav(path, seconds=2):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x01" * 16000 * seconds)


@needs_ffmpeg
def test_audio_transcribed(tmp_path):
    f = tmp_path / "a.wav"
    make_wav(f)
    c = FakeClient(transcript="Hôm nay học định lý Pythagoras")
    r = intake([f], tmp_path / "o", client=c, options=opts())
    pg = r.materials[0].pages[0]
    assert pg.kind == "audio" and pg.transcript == "Hôm nay học định lý Pythagoras"
    assert c.calls == ["mentor-audio"] and r.checks[0].ok


@needs_ffmpeg
def test_audio_no_speech_listed(tmp_path):
    f = tmp_path / "a.wav"
    make_wav(f)
    r = intake([f], tmp_path / "o", client=FakeClient(transcript="[NO_SPEECH]"), options=opts())
    assert r.checks[0].reasons == ["no_speech"]


@needs_ffmpeg
def test_video_audio_and_keyframes(tmp_path):
    f = tmp_path / "v.mp4"
    subprocess.run(
        [find_ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=5:duration=6",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=6", "-shortest", "-pix_fmt", "yuv420p", str(f)],
        check=True,
    )
    c = FakeClient()
    r = intake([f], tmp_path / "o", client=c, options=opts(keyframe_every_s=2.0))
    kinds = [p.kind for p in r.materials[0].pages]
    assert kinds.count("video_audio") == 1 and kinds.count("video_frame") >= 3
    frames = [p for p in r.materials[0].pages if p.kind == "video_frame"]
    assert frames[0].timestamp_s == 0.0 and frames[-1].timestamp_s >= 4.0
    assert all(c_.ok for c_ in r.checks)  # frames are never gated
    assert frames[0].text == "# Trang\n$x^2$"  # but their text is extracted
