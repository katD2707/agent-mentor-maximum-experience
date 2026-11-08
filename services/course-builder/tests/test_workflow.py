"""Teacher-flow stages (workflow.py), offline: retake merge, revise calls, model and media stage mocked."""

import json
from pathlib import Path

import pytest
from mentor_course_builder import render_media as rm
from mentor_course_builder import workflow as wf
from mentor_course_builder.contracts import MediaFile, MediaResult
from mentor_course_builder.intake import IntakeResult
from mentor_course_builder.models import Material, Page, PageCheck
from mentor_course_builder.quality import page_label
from mentor_gateway.content import ContentStore, asset_ref_for
from mentor_schemas.course import Chapter, CourseMeta, CoursePack, ImageBlock, Lesson, TextBlock, VideoBlock


def img_page(src, i, text=None):
    return Page(src, i, "image", image_path=f"/x/{src}-{i}.jpg", text=text)


def img_check(p, ok=True, reasons=()):
    return PageCheck(page=p.index, source_file=p.source_file, kind=p.kind, ok=ok, reasons=list(reasons),
                     message_vi="" if ok else f"{page_label(p)}: mờ", text=p.text)


def test_merge_intake_retake_replaces_the_page_and_new_photos_continue_numbering():
    a, b = img_page("/up/a.jpg", 1, "A"), img_page("/up/b.jpg", 2, "B")
    old = IntakeResult([Material("/up/a.jpg", "image", [a]), Material("/up/b.jpg", "image", [b])],
                       [img_check(a), img_check(b, False, ["blurry"])])
    assert [c.source_file for c in old.retake] == ["/up/b.jpg"]
    nb = img_page("/up/b2.jpg", 1, "B again")
    got = wf.merge_intake(old, IntakeResult([Material("/up/b2.jpg", "image", [nb])], [img_check(nb)]), ["b.jpg#2"])
    assert got.retake == []
    pages = [(p.source_file, p.index, p.text) for m in got.materials for p in m.pages]
    assert pages == [("/up/a.jpg", 1, "A"), ("/up/b.jpg", 2, "B again")]  # same label, new content
    assert sorted((c.source_file, c.page) for c in got.checks) == [("/up/a.jpg", 1), ("/up/b.jpg", 2)]
    # a plain addition is numbered after the existing photos
    c = img_page("/up/c.jpg", 1, "C")
    got2 = wf.merge_intake(got, IntakeResult([Material("/up/c.jpg", "image", [c])], [img_check(c, False, ["dark"])]))
    assert [(p.source_file, p.index) for m in got2.materials for p in m.pages][-1] == ("/up/c.jpg", 3)
    assert got2.retake[0].page == 3 and "Ảnh 3 (c.jpg)" in got2.retake[0].message_vi


class FakeClient:
    def __init__(self):
        self.prompts = []

    def complete(self, alias, messages, **kw):
        self.prompts.append(messages[-1]["content"])
        return json.dumps({"md": "Văn bản mới.", "b": "Văn bản mới."})

    def close(self):
        pass


@pytest.fixture
def course(tmp_path):
    store = ContentStore(tmp_path / "courses")
    meta = CourseMeta(id="c1", title="T", subject="Lý", age_band="g10_12", language="vi", teacher_id="t", teacher_name="T",
                      description_short="d", cover="cover.webp")
    v = store.create_draft(meta)
    vid, png = asset_ref_for("video/b1.mp4", b"v" * 50, "video/mp4"), asset_ref_for("images/b3.webp", b"i" * 30, "image/webp")
    pack = CoursePack(course_id="c1", version=v, language="vi", age_band="g10_12", title="T", chapters=[Chapter(
        id="ch", title="C", lessons=[Lesson(id="l1", title="L", est_minutes=5, blocks=[
            VideoBlock(id="b1", video=vid, duration_s=9), TextBlock(id="b2", md="Cũ."), ImageBlock(id="b3", image=png, alt="h")])])])
    store.write_pack("c1", v, pack, {"video/b1.mp4": b"v" * 50, "images/b3.webp": b"i" * 30})
    base = tmp_path / "b"
    media = base / "versions" / "1" / "media"
    (media / "sources" / "b1").mkdir(parents=True)
    (media / "sources" / "b3").mkdir(parents=True)
    (base / "versions" / "1" / "media.json").write_text(json.dumps({
        "b1": {"request": {"id": "b1", "kind": "video", "course_id": "c1", "lesson_id": "l1", "age_band": "g10_12",
                           "language": "vi", "spec": {"title": "t", "scenes": []}}, "files": [], "source_dir": "sources/b1"},
        "b3": {"request": {"id": "b3", "kind": "illustration", "course_id": "c1", "lesson_id": "l1", "age_band": "g10_12",
                           "language": "vi", "spec": {"description": "d"}}, "files": [], "source_dir": "sources/b3"}}))
    return store, base, {"course_id": "c1", "version": 1, "store": str(store.root)}


def test_revise_text_rewrites_only_the_commented_block(course):
    store, base, common = course
    client = FakeClient()
    out = wf.job_revise_text(base, {**common, "block_id": "b2", "comment": "ngắn hơn",
                                    "anchor": {"kind": "text", "quote": "Cũ"}}, client)
    assert out["ok"]
    blocks = store.load_pack("c1", 1).chapters[0].lessons[0].blocks
    assert [b.id for b in blocks] == ["b1", "b2", "b3"] and blocks[1].md == "Văn bản mới."
    assert "ngắn hơn" in client.prompts[0] and "«Cũ»" in client.prompts[0]
    with pytest.raises(wf.JobError):  # a video block has no text
        wf.job_revise_text(base, {**common, "block_id": "b1", "comment": "x", "anchor": {"kind": "text", "quote": "q"}}, client)


def test_revise_media_calls_the_media_stage_with_the_anchor(course, tmp_path, monkeypatch):
    store, base, common = course
    seen = []

    def fake_render(req, out_dir, *, client=None, tts=None):
        seen.append(req)
        f = tmp_path / f"{req.id}.out"
        f.write_bytes(b"new-" + req.id.encode())
        mime, path = ("video/mp4", "video/b1.mp4") if req.kind == "video" else ("image/webp", "images/b3.webp")
        return MediaResult(id=req.id, kind=req.kind, duration_s=11.0, source_dir=Path(req.revise["source_dir"]),
                           files=[MediaFile(role="main", path=path, mime=mime, file=f)])

    monkeypatch.setattr(rm, "render_media", fake_render)
    wf.job_revise_media(base, {**common, "block_id": "b1", "comment": "chữ nhỏ", "anchor": {"kind": "time", "t": 12.5}}, FakeClient())
    wf.job_revise_media(base, {**common, "block_id": "b3", "comment": "mũi tên", "anchor": {"kind": "point", "x": 0.25, "y": 0.75}}, FakeClient())
    v, i = seen
    assert v.kind == "video" and v.revise["at_s"] == 12.5 and v.revise["comment"] == "chữ nhỏ"
    assert v.revise["source_dir"].replace("\\", "/").endswith("versions/1/media/sources/b1")
    assert i.kind == "illustration" and (i.revise["x"], i.revise["y"]) == (0.25, 0.75) and "at_s" not in i.revise
    pack = store.load_pack("c1", 1)
    blocks = pack.chapters[0].lessons[0].blocks
    assert blocks[0].duration_s == 11.0 and blocks[0].video.bytes == len(b"new-b1")
    assert store.asset_path("c1", 1, "images/b3.webp").read_bytes() == b"new-b3"
    assert store._verify_assets("c1", 1, pack) > 0  # noqa: SLF001
    with pytest.raises(wf.JobError):
        wf.job_revise_media(base, {**common, "block_id": "b2", "comment": "x", "anchor": {"kind": "time", "t": 1}}, FakeClient())


def test_move_tree_survives_locked_files(tmp_path, monkeypatch):
    import os

    from mentor_course_builder import workflow

    src, dst = tmp_path / "media", tmp_path / "v1" / "media"
    (src / "sources" / "a").mkdir(parents=True)
    (src / "sources" / "a" / "x.txt").write_text("x")
    dst.mkdir(parents=True)
    (dst / "stale.txt").write_text("old")
    monkeypatch.setattr(os, "rename", lambda *a, **k: (_ for _ in ()).throw(PermissionError("WinError 5")))
    monkeypatch.setattr(workflow.time, "sleep", lambda s: None)
    workflow._move_tree(src, dst)
    assert (dst / "sources" / "a" / "x.txt").read_text() == "x" and not (dst / "stale.txt").exists()
