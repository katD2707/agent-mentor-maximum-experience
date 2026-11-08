"""/api/teacher: upload -> intake -> outline -> build -> review -> publish, offline.

The builder stages run as subprocesses in production; here `FakeRunner` stands in for them and writes the same small JSON
outputs (and records every call), so the state machine, ownership, comments, versions and restart-resume are tested
without a model.
"""

import asyncio
import io
import json
import os
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from gateway_fakes import login
from mentor_schemas.course import TextBlock
from sqlalchemy import select
from test_gw_courses import ASSETS, make_meta, make_pack

from mentor_gateway.app import create_app
from mentor_gateway.content import ContentStore
from mentor_gateway.db import NotificationRow
from mentor_gateway.teacher.service import StageJob, SubprocessRunner

OUTLINE = {
    "course_id": "c", "title": "Vật lí 11: Điện trường", "subject": "Vật lí", "language": "vi", "age_band": "g10_12",
    "description_short": "Điện trường cho lớp 11. Có ví dụ.", "outcomes": ["Tính cường độ"], "teacher_note": None,
    "chapters": [
        {"id": "ch-dien-truong", "title": "Điện trường", "lessons": [
            {"id": "duong-suc", "title": "Đường sức điện", "est_minutes": 8, "summary": "s", "key_ideas": ["a"],
             "source_pages": ["a.jpg#1"], "grounded": True},
            {"id": "cuong-do", "title": "Cường độ", "est_minutes": 9, "summary": "s", "key_ideas": [],
             "source_pages": ["b.jpg#2"], "grounded": True}]}],
}


def jpeg(path: Path) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (900, 600), (200, 210, 220)).save(path, "JPEG")


def two_lesson_pack(outline: dict, cid: str, version: int):
    """A valid pack with one lesson per outline lesson (the verify gate checks the outline is fully built)."""
    pack = make_pack(cid, version, title=outline["title"])
    first = pack.chapters[0].lessons[0]
    first.blocks[-1].items[0] = first.blocks[-1].items[0].model_copy(update={"stem": "Đường sức dày nói lên điều gì?"})
    ids = [ls["id"] for ch in outline["chapters"] for ls in ch["lessons"]]
    lessons = [first.model_copy(update={"id": ids[0], "title": "Đường sức điện"})]
    for n, lid in enumerate(ids[1:], 2):  # block ids stay unique across the pack; assets are shared
        blocks = [b.model_copy(update={"id": f"{b.id}x{n}"}) for b in first.blocks]
        blocks[-1] = blocks[-1].model_copy(update={"items": [blocks[-1].items[0].model_copy(update={"id": f"q1x{n}", "stem": f"Câu hỏi của bài {n} là gì?"})]})
        lessons.append(first.model_copy(update={"id": lid, "title": f"Bài {n}", "blocks": blocks}))
    return pack.model_copy(update={"chapters": [pack.chapters[0].model_copy(update={"lessons": lessons})]})


class FakeRunner:
    """Same files the real stages write, no model. `calls` = [(kind, args)] for assertions."""

    def __init__(self, store: ContentStore) -> None:
        self.store = store
        self.calls: list[tuple[str, dict]] = []
        self.bad: set[str] = set()  # refs "file#page" that stay unreadable
        self.fail: set[str] = set()
        self.gates: dict[str, threading.Event] = {}
        self.hang = False

    async def __call__(self, job: StageJob) -> int:
        args = json.loads(job.args_file.read_text("utf-8"))
        self.calls.append((job.kind, args))
        if self.hang:
            await asyncio.sleep(3600)
        if job.kind in self.gates:
            await asyncio.to_thread(self.gates[job.kind].wait, 10)
        if job.kind in self.fail:
            job.result_file.write_text(json.dumps({"ok": False, "error": "boom"}))
            return 1
        res = getattr(self, "do_" + job.kind)(job, args)
        job.result_file.write_text(json.dumps({"ok": True, **res}))
        return 0

    # -- stages
    def do_intake(self, job, args):
        d = job.base / "intake"
        pages = json.loads((d / "pages.json").read_text(encoding="utf-8")) if (d / "pages.json").is_file() else []
        checks = json.loads((d / "checks.json").read_text(encoding="utf-8")) if (d / "checks.json").is_file() else []
        for ref in args["replace"]:
            for c in checks:
                if f"{c['source_file']}#{c['page']}" == ref:
                    c.update(ok=True, reasons=[], message_vi="", message_en="")
        replaced = len(args["replace"])
        for i, name in enumerate(args["files"][replaced:] if replaced else args["files"], len(pages) + 1):
            img = d / "images" / name
            jpeg(img)
            pages.append({"source_file": name, "kind": "image", "notes": [],
                          "pages": [{"source_file": name, "index": i, "kind": "image", "image_path": str(img), "text": "x"}]})
            bad = f"{name}#{i}" in self.bad or name in self.bad
            if bad:
                self.bad.add(f"{name}#{i}")
            checks.append({"page": i, "source_file": name, "kind": "image", "ok": not bad,
                           "reasons": ["blurry"] if bad else [], "message_vi": f"Ảnh {i}: mờ" if bad else "",
                           "message_en": f"Photo {i}: blurry" if bad else ""})
        (d).mkdir(parents=True, exist_ok=True)
        (d / "pages.json").write_text(json.dumps(pages))
        (d / "checks.json").write_text(json.dumps(checks))
        if not (job.base / "outline.json").is_file():
            (job.base / "outline.json").write_text(json.dumps({**OUTLINE, "course_id": args["course_id"], "level_suggested": "basic"}))
        return {"message_vi": "ok"}

    def do_outline_chat(self, job, args):
        f = job.base / "outline.json"
        o = json.loads(f.read_text(encoding="utf-8"))
        o["title"] += " (đã sửa)"
        f.write_text(json.dumps(o))
        return {"message_vi": "Đã đổi tên khóa.", "message_en": "Renamed."}

    def do_build(self, job, args):
        o = json.loads((job.base / "outline.json").read_text(encoding="utf-8"))
        cid = args["course_id"]
        meta = make_meta(cid, title=o["title"]).model_copy(update={"teacher_id": args["teacher_id"], "cover": "cover.webp"})
        meta_versions = self.store.load_meta(cid).versions if (self.store.root / cid / "course.json").is_file() else []
        open_v = [v.version for v in meta_versions if v.status != "published"]
        version = max(open_v) if open_v else self.store.create_draft(meta)
        self.store.write_pack(cid, version, two_lesson_pack(o, cid, version), ASSETS)
        if o.get("level_suggested"):
            self.store.set_level(cid, version, suggested=o["level_suggested"])
        (self.store.course_dir(cid) / "cover.webp").write_bytes(b"cover")
        self.store.set_status(cid, version, "review")
        vdir = job.base / "versions" / str(version)
        (vdir / "media" / "sources" / "b1").mkdir(parents=True, exist_ok=True)
        (vdir / "media" / "sources" / "b3").mkdir(parents=True, exist_ok=True)
        (vdir / "media.json").write_text(json.dumps({
            "b1": {"request": {"id": "b1", "kind": "video"}, "files": [], "source_dir": "sources/b1"},
            "b3": {"request": {"id": "b3", "kind": "illustration"}, "files": [], "source_dir": "sources/b3"}}))
        prog = json.loads((job.base / "build" / "progress.json").read_text(encoding="utf-8"))
        for ls in prog["lessons"]:
            ls["state"] = "done"
        prog["stage"] = "done"
        (job.base / "build" / "progress.json").write_text(json.dumps(prog))
        return {"message_vi": "Đã soạn xong 2/2 bài.", "version": version}

    def _edit_text(self, args, fn):
        pack = self.store.load_pack(args["course_id"], args["version"])
        for ls in pack.chapters[0].lessons:
            ls.blocks = [b.model_copy(update={"md": fn(b.md)}) if isinstance(b, TextBlock) else b for b in ls.blocks]
        self.store.write_pack(args["course_id"], args["version"], pack, {})

    def do_revise_text(self, job, args):
        self._edit_text(args, lambda md: "Đã sửa: " + args["comment"])
        return {"message_vi": "Đã sửa khối.", "note": "text rewritten"}

    def do_revise_media(self, job, args):
        return {"message_vi": "Đã sửa phần video/ảnh.", "note": "revised"}

    def do_revise_all(self, job, args):
        self._edit_text(args, lambda md: md + " (ngắn hơn)")
        return {"message_vi": "Đã sửa 1 khối."}


@pytest.fixture
def store(client, tmp_path) -> ContentStore:
    s = ContentStore(tmp_path / "courses", client.app.state.gw.clock)
    client.app.state.content.store = s
    return s


@pytest.fixture
def runner(client, store) -> FakeRunner:
    r = FakeRunner(store)
    client.app.state.builder.runner = r
    return r


def files(*names):
    return [("files", (n, b"\xff\xd8fake", "image/jpeg")) for n in names]


def wait_status(client, cid, want, timeout=8):
    end = time.time() + timeout
    while time.time() < end:
        r = client.get(f"/api/teacher/courses/{cid}")
        if r.json()["status"] == want:
            return r.json()
        time.sleep(0.05)
    raise AssertionError(f"status {r.json()['status']!r}, wanted {want!r}")


def upload(client, *names, note=None):
    r = client.post("/api/teacher/uploads", files=files(*names), data={"note": note} if note else None)
    assert r.status_code == 200, r.text
    return r.json()


def built_course(client, runner, store, teacher_id) -> str:
    cid = upload(client, "a.jpg", "b.jpg")["course_id"]
    wait_status(client, cid, "outline_ready")
    assert client.post(f"/api/teacher/courses/{cid}/build").status_code == 200
    wait_status(client, cid, "review")
    return cid


def confirm(client, cid, version=1, level="intermediate"):
    """The teacher picks the course level; publishing is refused until someone has."""
    r = client.put(f"/api/teacher/courses/{cid}/versions/{version}/level", json={"level": level})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- ownership
def test_role_and_ownership(client, teacher, runner):
    cid = upload(client, "a.jpg")["course_id"]
    wait_status(client, cid, "outline_ready")
    assert [c["id"] for c in client.get("/api/teacher/courses").json()] == [cid]
    client.app.state.gw.users.create(username="thay2", password="123456", role="teacher", display_name="Cô Hoa")
    mine = dict(client.headers)
    login(client, "thay2", "123456", "teacher")
    assert client.get("/api/teacher/courses").json() == []
    for method, path in [("get", ""), ("post", "/build"), ("post", "/chat"), ("get", "/versions/1/comments"),
                         ("put", "/outline"), ("post", "/versions"), ("post", "/materials"),
                         ("post", "/versions/1/publish")]:
        r = getattr(client, method)(f"/api/teacher/courses/{cid}{path}",
                                    **({"json": {"text": "x"} if path == "/chat" else {"ops": []}} if method in ("put",) or path == "/chat" else {}))
        assert r.status_code == 403 and r.json()["error"] == "not_owner", (method, path, r.text)
    assert client.get("/api/teacher/courses/c-nope").status_code == 404
    client.headers.update(mine)
    login(client, "hocsinh", "123456", "student")
    for path in ("/courses", f"/courses/{cid}", "/events"):
        assert client.get("/api/teacher" + path).status_code == 403
    assert client.post("/api/teacher/uploads", files=files("a.jpg")).json()["error"] == "role_mismatch"


def test_upload_needs_files(client, teacher, runner):
    r = client.post("/api/teacher/uploads", data={"note": "x"})
    assert r.status_code == 422 and r.json()["error"] == "no_files"
    assert client.get("/api/teacher/courses").json() == []


# ---------------------------------------------------------------- state machine and retake
def test_upload_to_outline_ready(client, teacher, runner, gw):
    out = upload(client, "a.jpg", "b.jpg", note="Cho lớp 11A2")
    cid = out["course_id"]
    d = wait_status(client, cid, "outline_ready")
    kind, args = runner.calls[0]
    assert kind == "intake" and args["files"] == ["a.jpg", "b.jpg"] and args["note"] == "Cho lớp 11A2" and args["replace"] == []
    assert d["retake"] == [] and d["course"]["title"] == "Vật lí 11: Điện trường"
    assert d["status_line_vi"] == "Cần bạn xem cấu trúc"
    assert [ls["id"] for ch in d["outline"]["chapters"] for ls in ch["lessons"]] == ["duong-suc", "cuong-do"]
    kinds = [m["kind"] for m in d["chat"]]
    assert kinds[0] == "text" and d["chat"][0]["role"] == "teacher" and "outline" in kinds
    assert d["build"]["lessons"] == [{"id": "duong-suc", "title": "Đường sức điện", "state": "waiting"},
                                     {"id": "cuong-do", "title": "Cường độ", "state": "waiting"}]
    # the desktop app gets a notification when the job finishes
    with gw.db.session() as s:
        texts = [r.text for r in s.scalars(select(NotificationRow).where(NotificationRow.user_id == teacher["id"]))]
    assert any("Đã đọc xong" in t for t in texts)
    row = client.get("/api/teacher/courses").json()[0]
    assert row["status"] == "outline_ready" and row["versions"] == [] and row["latest_version"] == 0
    assert client.get("/api/teacher/courses", params={"since": "2999-01-01T00:00:00+00:00"}).json() == []
    assert len(client.get("/api/teacher/courses", params={"since": "2000-01-01T00:00:00+00:00"}).json()) == 1


def test_retake_flow(client, teacher, runner):
    runner.bad.add("b.jpg")
    cid = upload(client, "a.jpg", "b.jpg")["course_id"]
    d = wait_status(client, cid, "needs_retake")
    assert d["outline"] is not None  # the readable pages are still used
    [rt] = d["retake"]
    assert rt["ref"] == "b.jpg#2" and rt["source_file"] == "b.jpg" and rt["page"] == 2 and rt["reasons"] == ["blurry"]
    assert rt["message_vi"] and rt["message_en"]
    assert client.get("/api/teacher/courses").json()[0]["status_line_vi"] == "Cần chụp lại 1 trang"
    t = client.get(rt["thumb_url"])
    assert t.status_code == 200 and t.headers["content-type"] == "image/jpeg"
    runner.bad.discard("b.jpg#2")
    r = client.post(f"/api/teacher/courses/{cid}/materials", files=files("b2.jpg"), data={"replace": "b.jpg#2"})
    assert r.status_code == 200 and "job_id" in r.json()
    d = wait_status(client, cid, "outline_ready")
    kind, args = runner.calls[-1]
    assert kind == "intake" and args["replace"] == ["b.jpg#2"] and args["files"] == ["b2.jpg"]
    assert d["retake"] == []
    # extra material without `replace` just adds pages
    client.post(f"/api/teacher/courses/{cid}/materials", files=files("c.jpg"))
    wait_status(client, cid, "outline_ready")
    assert runner.calls[-1][1]["replace"] == []


def test_failed_intake_reports_and_keeps_going(client, teacher, runner):
    runner.fail.add("intake")
    cid = upload(client, "a.jpg")["course_id"]
    end = time.time() + 20
    while time.time() < end and not any(m["kind"] == "notice" and "Chưa đọc" in (m["text"] or "")
                                        for m in client.get(f"/api/teacher/courses/{cid}").json()["chat"]):
        time.sleep(0.05)
    d = client.get(f"/api/teacher/courses/{cid}").json()
    assert d["status"] == "reading" and any("boom" in (m["text"] or "") for m in d["chat"])


def test_flaky_intake_is_retried(client, teacher, runner):
    class FailOnce(set):
        def __contains__(self, k):
            hit = k == "intake" and not getattr(self, "used", False)
            self.used = self.used or hit if hasattr(self, "used") else hit
            return hit

    runner.fail = FailOnce()  # the model gateway flakes once, then recovers
    cid = upload(client, "a.jpg")["course_id"]
    wait_status(client, cid, "outline_ready")
    assert [c[0] for c in runner.calls].count("intake") == 2
    assert any("đọc lại" in (m["text"] or "") for m in client.get(f"/api/teacher/courses/{cid}").json()["chat"])


# ---------------------------------------------------------------- outline edits and chat
def test_outline_ops(client, teacher, runner):
    cid = upload(client, "a.jpg")["course_id"]
    wait_status(client, cid, "outline_ready")
    r = client.put(f"/api/teacher/courses/{cid}/outline", json={"ops": [
        {"op": "rename", "id": "duong-suc", "title": "Đường sức"}, {"op": "delete", "id": "cuong-do"},
        {"op": "add_lesson", "chapter": "ch-dien-truong", "title": "Thế năng", "after": "duong-suc"}]})
    assert r.status_code == 200, r.text
    lessons = r.json()["chapters"][0]["lessons"]
    assert [ls["title"] for ls in lessons] == ["Đường sức", "Thế năng"] and lessons[1]["grounded"] is False
    assert client.get(f"/api/teacher/courses/{cid}").json()["outline"]["chapters"][0]["lessons"][0]["title"] == "Đường sức"
    bad = client.put(f"/api/teacher/courses/{cid}/outline", json={"ops": [{"op": "delete", "id": "khong-co"}]})
    assert bad.status_code == 422 and bad.json()["error"] == "bad_outline_edit"
    assert client.put(f"/api/teacher/courses/{cid}/outline", json={"ops": [{"op": "rename"}]}).status_code == 422
    # an edited outline is not rebuilt by a later intake
    client.post(f"/api/teacher/courses/{cid}/materials", files=files("c.jpg"))
    wait_status(client, cid, "outline_ready")
    assert runner.calls[-1][1]["outline_edited"] is True


def test_outline_busy_while_agent_works(client, teacher, runner):
    runner.gates["intake"] = threading.Event()
    cid = upload(client, "a.jpg")["course_id"]
    r = client.put(f"/api/teacher/courses/{cid}/outline", json={"ops": []})
    assert r.status_code == 409 and r.json()["error"] == "busy"
    assert client.get("/api/teacher/courses").json()[0]["status"] == "reading"
    runner.gates["intake"].set()
    wait_status(client, cid, "outline_ready")


def test_chat_before_build_edits_outline(client, teacher, runner):
    cid = upload(client, "a.jpg")["course_id"]
    wait_status(client, cid, "outline_ready")
    r = client.post(f"/api/teacher/courses/{cid}/chat", json={"text": "gộp bài 1 và 2"})
    assert r.status_code == 200
    msgs = r.json()
    assert [m["role"] for m in msgs][:2] == ["teacher", "agent"] and msgs[0]["text"] == "gộp bài 1 và 2"
    assert msgs[-1]["kind"] == "outline" and msgs[-1]["text"] == "Đã đổi tên khóa."  # the agent's answer, no question back
    assert runner.calls[-1] == ("outline_chat", {"course_id": cid, "instruction": "gộp bài 1 và 2"})
    assert client.get(f"/api/teacher/courses/{cid}").json()["course"]["title"].endswith("(đã sửa)")


def test_chat_needs_an_outline(client, teacher, runner):
    runner.gates["intake"] = threading.Event()
    cid = upload(client, "a.jpg")["course_id"]
    (client.app.state.builder.course_dir(cid) / "outline.json").unlink(missing_ok=True)
    r = client.post(f"/api/teacher/courses/{cid}/chat", json={"text": "x"})
    assert r.status_code == 409 and r.json()["error"] == "outline_not_ready"
    runner.gates["intake"].set()


# ---------------------------------------------------------------- build
def test_build_statuses_and_review(client, teacher, runner, store):
    cid = upload(client, "a.jpg", "b.jpg")["course_id"]
    wait_status(client, cid, "outline_ready")
    runner.gates["build"] = threading.Event()
    assert client.post(f"/api/teacher/courses/{cid}/build").status_code == 200
    d = wait_status(client, cid, "building")
    assert d["status_line_vi"].startswith("Đang soạn") and len(d["build"]["lessons"]) == 2
    row = client.get("/api/teacher/courses").json()[0]
    assert row["status"] == "building" and row["build"] == {"done": 0, "total": 2}
    assert client.post(f"/api/teacher/courses/{cid}/build").status_code == 409  # one job at a time
    runner.gates["build"].set()
    d = wait_status(client, cid, "review")
    assert [ls["state"] for ls in d["build"]["lessons"]] == ["done", "done"]
    assert d["course"]["versions"] == [{"version": 1, "status": "review", "students": 0, "level_suggested": "basic",
                                       "level_confirmed": None}]
    args = next(a for k, a in runner.calls if k == "build")
    assert args["store"] == str(store.root) and args["teacher_id"] == teacher["id"] and "tts" in args["media_kinds"]
    assert d["chat"][-1]["kind"] == "build"
    # draft pack and assets are readable by the owner only
    assert client.get(f"/api/teacher/courses/{cid}/versions/1/pack").json()["version"] == 1
    tok = client.post("/api/media-token").json()["token"]
    a = client.get(f"/api/teacher/courses/{cid}/versions/1/assets/l1/v.mp4", params={"t": tok}, headers={"Authorization": ""})
    assert a.status_code == 200 and a.headers["cache-control"] == "private, no-store"
    assert client.get(f"/api/teacher/courses/{cid}/versions/1/assets/l1/v.mp4").status_code == 200
    # students never see the draft
    mine = dict(client.headers)
    login(client, "hocsinh", "123456", "student")
    assert client.get(f"/api/teacher/courses/{cid}/versions/1/pack").status_code == 403
    assert client.get(f"/api/courses/{cid}/versions/1/pack").status_code == 404
    client.headers.update(mine)


def test_chat_after_build_revises_the_draft(client, teacher, runner, store):
    cid = built_course(client, runner, store, teacher["id"])
    msgs = client.post(f"/api/teacher/courses/{cid}/chat", json={"text": "ngắn hơn"}).json()
    kind, args = runner.calls[-1]
    assert kind == "revise_all" and args["version"] == 1 and args["instruction"] == "ngắn hơn"
    assert msgs[-1]["text"] == "Đã sửa 1 khối."
    assert store.load_pack(cid, 1).chapters[0].lessons[0].blocks[1].md.endswith("(ngắn hơn)")


# ---------------------------------------------------------------- comments
def comment(client, cid, v, block, anchor, body="sửa giúp"):
    return client.post(f"/api/teacher/courses/{cid}/versions/{v}/comments", json={"block_id": block, "anchor": anchor, "body": body})


def wait_comment(client, cid, v, cm_id, want):
    end = time.time() + 8
    while time.time() < end:
        got = next(c for c in client.get(f"/api/teacher/courses/{cid}/versions/{v}/comments").json() if c["id"] == cm_id)
        if got["status"] == want:
            return got
        time.sleep(0.05)
    raise AssertionError(got)


def test_comment_text_rewrites_only_that_block(client, teacher, runner, store):
    cid = built_course(client, runner, store, teacher["id"])
    before = store.load_pack(cid, 1)
    r = comment(client, cid, 1, "b2", {"kind": "text", "start": 0, "end": 5, "quote": "Nội dung"}, "viết ngắn hơn")
    assert r.status_code == 200 and r.json()["status"] == "open"
    cm = wait_comment(client, cid, 1, r.json()["id"], "applied")
    assert cm["note"] == "text rewritten" and cm["anchor"]["quote"] == "Nội dung"
    kind, args = runner.calls[-1]
    assert kind == "revise_text" and args["block_id"] == "b2" and args["comment"] == "viết ngắn hơn"
    assert args["anchor"] == {"kind": "text", "start": 0, "end": 5, "quote": "Nội dung"} and args["version"] == 1
    after = store.load_pack(cid, 1)
    assert after.chapters[0].lessons[0].blocks[1].md == "Đã sửa: viết ngắn hơn"
    assert [b.id for b in after.chapters[0].lessons[0].blocks] == [b.id for b in before.chapters[0].lessons[0].blocks]
    assert client.get(f"/api/teacher/courses/{cid}").json()["status"] == "review"


def test_comment_video_time_and_image_point(client, teacher, runner, store):
    cid = built_course(client, runner, store, teacher["id"])
    v = comment(client, cid, 1, "b1", {"kind": "time", "t": 12.5}, "chữ nhỏ quá")
    wait_comment(client, cid, 1, v.json()["id"], "applied")
    assert runner.calls[-1][0] == "revise_media"
    assert runner.calls[-1][1]["anchor"] == {"kind": "time", "t": 12.5} and runner.calls[-1][1]["block_id"] == "b1"
    p = comment(client, cid, 1, "b3", {"kind": "point", "x": 0.25, "y": 0.75}, "mũi tên sai")
    wait_comment(client, cid, 1, p.json()["id"], "applied")
    assert runner.calls[-1][0] == "revise_media"
    assert runner.calls[-1][1]["anchor"] == {"kind": "point", "x": 0.25, "y": 0.75} and runner.calls[-1][1]["block_id"] == "b3"
    # quiz: a text anchor is allowed and re-verified by the builder
    q = comment(client, cid, 1, "b4", {"kind": "text", "quote": "?"})
    wait_comment(client, cid, 1, q.json()["id"], "applied")
    assert runner.calls[-1][0] == "revise_text"


def test_comment_validation_and_failure(client, teacher, runner, store):
    cid = built_course(client, runner, store, teacher["id"])
    assert comment(client, cid, 1, "b1", {"kind": "text", "quote": "x"}).json()["error"] == "anchor_mismatch"  # video
    assert comment(client, cid, 1, "b2", {"kind": "time", "t": 3}).json()["error"] == "anchor_mismatch"  # text block
    assert comment(client, cid, 1, "b2", {"kind": "point", "x": 0.5, "y": 0.5}).status_code == 422
    assert comment(client, cid, 1, "zz", {"kind": "text", "quote": "x"}).json()["error"] == "unknown_block"
    assert comment(client, cid, 1, "b3", {"kind": "point", "x": 1.5, "y": 0.5}).status_code == 422  # outside the image
    assert comment(client, cid, 9, "b2", {"kind": "text", "quote": "x"}).json()["error"] == "version_not_found"
    runner.fail.add("revise_text")
    r = comment(client, cid, 1, "b2", {"kind": "text", "quote": "Nội"})
    cm = wait_comment(client, cid, 1, r.json()["id"], "failed")
    assert cm["note"] == "boom"


# ---------------------------------------------------------------- publish and versions
def test_publish_then_new_version_keeps_students_pinned(client, teacher, runner, store):
    cid = built_course(client, runner, store, teacher["id"])
    confirm(client, cid, 1)
    r = client.post(f"/api/teacher/courses/{cid}/versions/1/publish")
    assert r.status_code == 200 and r.json()["version"]["status"] == "published"
    assert r.json()["course"]["status"] == "published" and r.json()["course"]["status_line_vi"] == "Đã xuất bản (bản 1, 0 học sinh)"
    assert comment(client, cid, 1, "b2", {"kind": "text", "quote": "x"}).json()["error"] == "version_published"
    assert client.post(f"/api/teacher/courses/{cid}/build").json()["error"] == "use_new_version"
    mine = dict(client.headers)
    login(client, "hocsinh", "123456", "student")
    assert client.post("/api/enrollments", json={"course_id": cid}).json()["version"] == 1
    client.headers.update(mine)
    v1_pack = store.pack_bytes_raw(cid, 1)

    r = client.post(f"/api/teacher/courses/{cid}/versions")
    assert r.status_code == 201 and r.json()["version"] == 2
    assert client.post(f"/api/teacher/courses/{cid}/versions").json()["error"] == "draft_exists"
    d = client.get(f"/api/teacher/courses/{cid}").json()
    assert d["status"] == "revising"
    assert d["course"]["versions"] == [{"version": 1, "status": "published", "students": 1, "level_suggested": "basic",
                                        "level_confirmed": "intermediate"},
                                       {"version": 2, "status": "draft", "students": 0, "level_suggested": "basic",
                                        "level_confirmed": "intermediate"}]
    c = comment(client, cid, 2, "b2", {"kind": "text", "quote": "Nội dung"}, "thêm ví dụ")
    wait_comment(client, cid, 2, c.json()["id"], "applied")
    assert store.pack_bytes_raw(cid, 1) == v1_pack  # the published version never changes
    assert store.load_pack(cid, 2).chapters[0].lessons[0].blocks[1].md == "Đã sửa: thêm ví dụ"
    confirm(client, cid, 2)
    client.post(f"/api/teacher/courses/{cid}/versions/2/publish")

    mine = dict(client.headers)
    login(client, "hocsinh", "123456", "student")
    e = client.get("/api/enrollments").json()[0]
    assert e["version"] == 1 and e["latest_version"] == 2 and e["update_available"] is True
    client.headers.update(mine)
    assert client.get("/api/teacher/courses").json()[0]["versions"][0]["students"] == 1


def test_chat_after_publish_starts_a_new_version(client, teacher, runner, store):
    cid = built_course(client, runner, store, teacher["id"])
    confirm(client, cid, 1)
    client.post(f"/api/teacher/courses/{cid}/versions/1/publish")
    client.post(f"/api/teacher/courses/{cid}/chat", json={"text": "ngắn hơn"})
    assert runner.calls[-1][0] == "revise_all" and runner.calls[-1][1]["version"] == 2


def test_seeded_course_is_listed_for_its_owner(client, teacher, runner, store):
    from test_gw_courses import publish_course

    publish_course(store, "sample-x")  # teacher_id "giaovien" = the seeded teacher's username
    row = next(c for c in client.get("/api/teacher/courses").json() if c["id"] == "sample-x")
    assert row["status"] == "published" and row["cover_sha256"]
    assert client.post("/api/teacher/courses/sample-x/versions").json()["version"] == 2
    c = comment(client, "sample-x", 2, "b2", {"kind": "text", "quote": "x"})
    assert wait_comment(client, "sample-x", 2, c.json()["id"], "applied")


# ---------------------------------------------------------------- restart, events
def test_restart_resumes_running_stage(settings, clock, executor, tmp_path):
    from mentor_gateway.app import create_app

    app1 = create_app(settings, clock=clock, executor=executor)
    store = ContentStore(tmp_path / "courses", clock)
    app1.state.content.store = store
    hang = FakeRunner(store)
    hang.hang = True
    app1.state.builder.runner = hang
    with TestClient(app1) as c1:
        login(c1, "giaovien", "123456", "teacher")
        cid = upload(c1, "a.jpg")["course_id"]
        end = time.time() + 5
        while not hang.calls and time.time() < end:
            time.sleep(0.02)
        assert c1.get(f"/api/teacher/courses/{cid}").json()["status"] == "reading"
    state = json.loads((settings.data_dir / "builder" / cid / "state.json").read_text("utf-8"))
    assert [j["status"] for j in state["jobs"]] == ["running"]  # the process stopped mid-stage

    app2 = create_app(settings, clock=clock, executor=executor)
    app2.state.content.store = store
    fake = FakeRunner(store)
    app2.state.builder.runner = fake
    with TestClient(app2) as c2:
        login(c2, "giaovien", "123456", "teacher")
        d = wait_status(c2, cid, "outline_ready")
        assert fake.calls[0][0] == "intake" and fake.calls[0][1]["files"] == ["a.jpg"]
        assert d["outline"]["title"]


def test_events_replay_and_job_log(client, teacher, runner):
    cid = upload(client, "a.jpg")["course_id"]
    wait_status(client, cid, "outline_ready")
    r = client.get("/api/teacher/events", params={"limit": 2}, headers={"Last-Event-ID": "0"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    datas = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]
    assert len(datas) == 2 and all(d["course_id"] == cid and d["type"] == "course" for d in datas)
    assert "status_line_vi" in datas[0] and "updated_at" in datas[0]


def test_subprocess_runner_command_line(tmp_path):
    job = StageJob("j1", "build", "c-1", tmp_path / "c-1", tmp_path / "a.json", tmp_path / "r.json", tmp_path / "l.log", 5)
    assert SubprocessRunner.argv("py", job) == ["py", "-m", "mentor_course_builder.cli", "job", "build", "--dir",
                                                str(tmp_path / "c-1"), "--args", str(tmp_path / "a.json"), "--result",
                                                str(tmp_path / "r.json")]


@pytest.mark.skipif(os.environ.get("MENTOR_LIVE_TEACHER") != "1", reason="set MENTOR_LIVE_TEACHER=1 to call the real models")
def test_live_upload_to_outline(client, teacher, store):
    """Opt-in: the real `mcb job intake` subprocess and model on one rendered page of text (needs the model env or
    .env.dev.local, like the builder CLI). Run: MENTOR_LIVE_TEACHER=1 pytest -s services/gateway/tests/test_gw_teacher.py"""
    from PIL import Image, ImageDraw, ImageFont

    from mentor_gateway.settings import _repo_root

    client.app.state.builder.runner = SubprocessRunner(None, _repo_root())
    img = Image.new("RGB", (1200, 700), "white")
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype("arial.ttf", 44) if Path("C:/Windows/Fonts/arial.ttf").is_file() else None
    for i, line in enumerate(["Bai 1. Dien truong", "Dien truong la moi truong bao quanh dien tich.", "Bai 2. Duong suc dien",
                              "Duong suc dien la duong cong co huong cua vecto cuong do dien truong."]):
        d.text((60, 60 + i * 110), line, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    r = client.post("/api/teacher/uploads", files=[("files", ("trang1.jpg", buf.getvalue(), "image/jpeg"))])
    cid = r.json()["course_id"]
    end = time.time() + 600
    while time.time() < end:
        d = client.get(f"/api/teacher/courses/{cid}").json()
        if d["status"] in ("outline_ready", "needs_retake"):
            break
        time.sleep(3)
    assert d["outline"] and d["outline"]["chapters"], d["chat"]


# ---------------------------------------------------------------- verify gate before publish
def test_publish_is_blocked_while_hard_errors_remain(client, teacher, runner, store):
    cid = built_course(client, runner, store, teacher["id"])
    ok = client.get(f"/api/teacher/courses/{cid}/versions/1/verify").json()
    assert ok == {"blocked": False, "issues": []}
    pack = store.load_pack(cid, 1)
    ls = pack.chapters[0].lessons[1]
    ls.blocks = [b for b in ls.blocks if b.kind != "quiz"]  # a lesson without its quiz
    pack.chapters[0].lessons[0].blocks[1] = pack.chapters[0].lessons[0].blocks[1].model_copy(update={"md": "Công thức $\frac{a}{b$."})
    store.write_pack(cid, 1, pack, ASSETS)
    confirm(client, cid, 1)
    r = client.post(f"/api/teacher/courses/{cid}/versions/1/publish")
    assert r.status_code == 409 and r.json()["error"] == "verify_failed"
    got = {(i["code"], i["lesson_id"]) for i in r.json()["issues"]}
    assert ("quiz_missing", "cuong-do") in got and ("katex", "duong-suc") in got
    assert all(i["vi"] and i["en"] and i["severity"] == "hard" for i in r.json()["issues"])
    assert store.version_info(store.load_meta(cid), 1).status == "review"  # nothing was published
    assert client.get(f"/api/teacher/courses/{cid}/versions/1/verify").json()["blocked"] is True
    # the teacher (or the agent) fixes both, and publishing goes through
    quiz = pack.chapters[0].lessons[0].blocks[-1]
    ls.blocks.append(quiz.model_copy(update={"id": "bqx", "items": [quiz.items[0].model_copy(update={"id": "q1y"})]}))
    pack.chapters[0].lessons[0].blocks[1] = pack.chapters[0].lessons[0].blocks[1].model_copy(update={"md": "Công thức $\frac{a}{b}$."})
    store.write_pack(cid, 1, pack, ASSETS)
    confirm(client, cid, 1)
    assert client.post(f"/api/teacher/courses/{cid}/versions/1/publish").status_code == 200


def test_build_verdicts_block_until_the_item_is_edited(client, teacher, runner, store):
    from mentor_course_builder.verify import item_hash

    cid = built_course(client, runner, store, teacher["id"])
    pack = store.load_pack(cid, 1)
    item = pack.chapters[0].lessons[0].blocks[-1].items[0]
    vdir = client.app.state.builder.course_dir(cid) / "versions" / "1"
    (vdir / "verify.json").write_text(json.dumps({"blocked": True, "hard": [
        {"code": "quiz_wrong", "lesson_id": "duong-suc", "block_id": item.id, "detail": "solver said B", "item_hash": item_hash(item)}],
        "soft": [], "fixed": []}))
    d = client.get(f"/api/teacher/courses/{cid}").json()
    assert d["verify"]["blocked"] is True
    confirm(client, cid, 1)
    r = client.post(f"/api/teacher/courses/{cid}/versions/1/publish")
    assert r.status_code == 409 and r.json()["issues"][0]["code"] == "quiz_wrong"
    # an edited question is a new question: the old verdict no longer applies
    pack.chapters[0].lessons[0].blocks[-1].items[0] = item.model_copy(update={"answer_key": {"correct_option_id": "B"}})
    store.write_pack(cid, 1, pack, ASSETS)
    confirm(client, cid, 1)
    r = client.post(f"/api/teacher/courses/{cid}/versions/1/publish")
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------- course level: the agent suggests, the teacher confirms
def test_level_suggestion_is_stored_and_publish_waits_for_the_teacher(client, teacher, runner, store):
    cid = built_course(client, runner, store, teacher["id"])
    c = client.get(f"/api/teacher/courses/{cid}").json()["course"]
    assert (c["level"], c["level_suggested"], c["level_confirmed"]) == (None, "basic", None)
    assert client.get("/api/teacher/courses").json()[0]["level_suggested"] == "basic"

    r = client.post(f"/api/teacher/courses/{cid}/versions/1/publish")
    assert r.status_code == 409 and r.json()["error"] == "level_unconfirmed"
    assert store.version_info(store.load_meta(cid), 1).status == "review"

    assert client.put(f"/api/teacher/courses/{cid}/versions/1/level", json={"level": "expert"}).status_code == 422
    r = client.put(f"/api/teacher/courses/{cid}/versions/1/level", json={"level": "advanced"})
    assert r.status_code == 200 and r.json() == {"version": 1, "new_version": False, "level": None,
                                                 "level_suggested": "basic", "level_confirmed": "advanced"}
    assert client.post(f"/api/teacher/courses/{cid}/versions/1/publish").status_code == 200
    meta = store.load_meta(cid)
    assert meta.level == "advanced"
    assert next(e for e in store.load_catalog().courses if e.id == cid).level == "advanced"
    assert client.get("/api/teacher/courses").json()[0]["level"] == "advanced"


def test_level_is_teacher_only_and_owner_only(client, teacher, runner, store):
    cid = built_course(client, runner, store, teacher["id"])
    mine = dict(client.headers)
    login(client, "hocsinh", "123456", "student")
    assert client.put(f"/api/teacher/courses/{cid}/versions/1/level", json={"level": "basic"}).status_code == 403
    client.headers.update(mine)
    assert client.put(f"/api/teacher/courses/nope/versions/1/level", json={"level": "basic"}).status_code in (403, 404)
    assert client.put(f"/api/teacher/courses/{cid}/versions/9/level", json={"level": "basic"}).status_code == 404


def test_changing_the_level_of_a_published_course_makes_version_2(client, teacher, runner, store):
    cid = built_course(client, runner, store, teacher["id"])
    confirm(client, cid, 1, "basic")
    assert client.post(f"/api/teacher/courses/{cid}/versions/1/publish").status_code == 200
    mine = dict(client.headers)
    login(client, "hocsinh", "123456", "student")
    assert client.post("/api/enrollments", json={"course_id": cid}).json()["version"] == 1
    client.headers.update(mine)
    v1_pack = store.pack_bytes_raw(cid, 1)

    same = client.put(f"/api/teacher/courses/{cid}/versions/1/level", json={"level": "basic"}).json()
    assert same["new_version"] is False and same["version"] == 1  # nothing changed, no new version
    assert [v.version for v in store.load_meta(cid).versions] == [1]

    r = client.put(f"/api/teacher/courses/{cid}/versions/1/level", json={"level": "advanced"})
    assert r.status_code == 200
    assert r.json() == {"version": 2, "new_version": True, "level": "basic", "level_suggested": "basic",
                        "level_confirmed": "advanced"}
    meta = store.load_meta(cid)
    assert meta.level == "basic"  # students and the catalog still show v1's level
    assert store.version_info(meta, 1).level_confirmed == "basic" and store.pack_bytes_raw(cid, 1) == v1_pack
    # a second change goes to the same draft
    r = client.put(f"/api/teacher/courses/{cid}/versions/1/level", json={"level": "intermediate"}).json()
    assert r["version"] == 2 and r["new_version"] is False and r["level_confirmed"] == "intermediate"

    assert client.post(f"/api/teacher/courses/{cid}/versions/2/publish").status_code == 200
    assert store.load_meta(cid).level == "intermediate"
    assert next(e for e in store.load_catalog().courses if e.id == cid).level == "intermediate"
    login(client, "hocsinh", "123456", "student")
    e = client.get("/api/enrollments").json()[0]
    assert e["version"] == 1 and e["latest_version"] == 2 and e["update_available"] is True
    assert store.pack_bytes_raw(cid, 1) == v1_pack
    client.headers.update(mine)


def test_a_new_version_starts_with_the_published_level_and_publishes_without_asking_again(client, teacher, runner, store):
    cid = built_course(client, runner, store, teacher["id"])
    confirm(client, cid, 1, "advanced")
    client.post(f"/api/teacher/courses/{cid}/versions/1/publish")
    assert client.post(f"/api/teacher/courses/{cid}/versions").status_code == 201
    c = client.get(f"/api/teacher/courses/{cid}").json()["course"]
    assert c["level"] == "advanced" and c["level_confirmed"] == "advanced"
    assert client.post(f"/api/teacher/courses/{cid}/versions/2/publish").status_code == 200


def test_course_id_is_readable_and_unique(client, teacher, runner):
    a = upload(client, "Điện trường đường sức.jpg")["course_id"]
    b = upload(client, "Điện trường đường sức.jpg")["course_id"]
    assert a == "dien-truong-duong-suc" and b == "dien-truong-duong-suc-2"
    assert upload(client, "???.jpg")["course_id"] == "khoa-hoc"


def test_rebuild_hides_old_comments_but_keeps_them(client, teacher, runner, store):
    cid = built_course(client, runner, store, teacher["id"])
    r = comment(client, cid, 1, "b2", {"kind": "text", "start": 0, "end": 5, "quote": "Nội dung"})
    wait_comment(client, cid, 1, r.json()["id"], "applied")
    url = f"/api/teacher/courses/{cid}/versions/1/comments"
    assert len(client.get(url).json()) == 1
    assert client.post(f"/api/teacher/courses/{cid}/build").status_code == 200
    wait_status(client, cid, "review")
    assert client.get(url).json() == []
    old = client.get(url, params={"stale": "true"}).json()
    assert len(old) == 1 and old[0]["stale"] is True
