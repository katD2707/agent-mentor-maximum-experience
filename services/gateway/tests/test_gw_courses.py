"""Course content store, /api catalog, packs, assets, enrollments and search (offline: no router)."""

from datetime import UTC, datetime

import pytest
from gateway_fakes import login
from mentor_schemas.course import (
    Chapter,
    CourseMeta,
    CoursePack,
    ImageBlock,
    Lesson,
    QuizBlock,
    QuizItem,
    QuizOption,
    TextBlock,
    VideoBlock,
)

from mentor_gateway.content import ContentStore, Immutable, asset_ref_for
from mentor_gateway.content.store import ContentError

VIDEO = bytes(range(256)) * 40  # 10240 bytes
IMG = b"\x89PNG fake image bytes"


def make_meta(cid="dien-truong", title="Vật lí 11: Điện trường", subject="Vật lí", band="g10_12",
              desc="Đường sức điện và cường độ điện trường."):
    return CourseMeta(id=cid, title=title, subject=subject, age_band=band, language="vi", teacher_id="giaovien",
                      teacher_name="Thầy Minh", description_short=desc, outcomes=["Tính cường độ điện trường"],
                      cover="cover.png")


def make_pack(cid, version, band="g10_12", title="Vật lí 11: Điện trường", lesson_title="Đường sức điện",
              idea="Đường sức dày thì điện trường mạnh", extra_block=False):
    vid = asset_ref_for("l1/v.mp4", VIDEO, "video/mp4")
    img = asset_ref_for("l1/a.png", IMG, "image/png")
    blocks = [
        VideoBlock(id="b1", video=vid, duration_s=10),
        TextBlock(id="b2", md="Nội dung"),
        ImageBlock(id="b3", image=img, alt="hình"),
        QuizBlock(id="b4", items=[QuizItem(
            id="q1", type="SINGLE_CHOICE", stem="?", options=[QuizOption(id="A", text="x"), QuizOption(id="B", text="y")],
            answer_key={"correct_option_id": "A"}, explanation="vì")]),
    ]
    if extra_block:
        blocks.append(TextBlock(id="b5", md="thêm"))
    return CoursePack(course_id=cid, version=version, language="vi", age_band=band, title=title, chapters=[
        Chapter(id="ch1", title="Điện trường", lessons=[Lesson(
            id="l1", title=lesson_title, est_minutes=10, summary="s", key_ideas=[idea], blocks=blocks)])])


ASSETS = {"l1/v.mp4": VIDEO, "l1/a.png": IMG}


def publish_course(store: ContentStore, cid="dien-truong", band="g10_12", **kw):
    meta_kw = {k: kw.pop(k) for k in ("title", "subject", "desc") if k in kw}
    store.create_draft(make_meta(cid, band=band, **meta_kw))
    (store.course_dir(cid) / "cover.png").write_bytes(IMG + cid.encode())
    store.write_pack(cid, 1, make_pack(cid, 1, band=band, title=meta_kw.get("title", "Vật lí 11: Điện trường"), **kw), ASSETS)
    return store.publish(cid, 1)


@pytest.fixture
def store(client, tmp_path) -> ContentStore:
    s = ContentStore(tmp_path / "courses", client.app.state.gw.clock)
    client.app.state.content.store = s
    return s


@pytest.fixture
def two_courses(store):
    publish_course(store, "dien-truong")
    publish_course(store, "dem-tao", band="g1_5", title="Toán 1: Đếm táo", subject="Toán", desc="Đếm các số đến 10 cùng Cún.",
                   lesson_title="Cún đếm táo", idea="Chạm từng quả táo")


# ---------------------------------------------------------------- store
def test_publish_freezes_version_and_regenerates_catalog(store):
    info = publish_course(store)
    assert info.status == "published" and len(info.pack_sha256) == 64
    assert info.pack_bytes == len(store.pack_bytes_raw("dien-truong", 1)) + len(VIDEO) + len(IMG)
    meta = store.load_meta("dien-truong")
    assert meta.latest_published == 1 and meta.lessons_count == 1 and meta.est_minutes == 10
    assert meta.media == ["video", "reading", "quiz"]
    cat = store.load_catalog()
    assert [c.id for c in cat.courses] == ["dien-truong"] and cat.courses[0].pack_sha256 == info.pack_sha256


def test_published_version_is_immutable(store):
    publish_course(store)
    with pytest.raises(Immutable):
        store.write_pack("dien-truong", 1, make_pack("dien-truong", 1), ASSETS)
    with pytest.raises(Immutable):
        store.publish("dien-truong", 1)
    with pytest.raises(Immutable):
        store.set_status("dien-truong", 1, "draft")


def test_draft_not_in_catalog_and_v2_flow(store):
    publish_course(store)
    assert store.create_draft(make_meta()) == 2
    store.write_pack("dien-truong", 2, make_pack("dien-truong", 2, extra_block=True), ASSETS)
    assert store.load_meta("dien-truong").latest_published == 1  # v2 still a draft
    assert store.load_catalog().courses[0].version == 1
    store.publish("dien-truong", 2, note="thêm khối")
    assert store.load_catalog().courses[0].version == 2


def test_refresh_meta_keeps_versions_and_counters(store):
    store.create_draft(make_meta("c1"))  # first build: a draft, not yet published
    store.refresh_meta(make_meta("c1", title="Tên mới"))  # rebuild after the teacher renamed the course
    m = store.load_meta("c1")
    assert m.title == "Tên mới" and [v.version for v in m.versions] == [1] and m.versions[0].status == "draft"


def test_publish_rejects_missing_or_changed_asset(store):
    store.create_draft(make_meta())
    (store.course_dir("dien-truong") / "cover.png").write_bytes(IMG)
    store.write_pack("dien-truong", 1, make_pack("dien-truong", 1), {"l1/v.mp4": VIDEO})  # image missing
    with pytest.raises(ContentError):
        store.publish("dien-truong", 1)
    store.write_pack("dien-truong", 1, make_pack("dien-truong", 1), {"l1/v.mp4": VIDEO, "l1/a.png": b"changed"})
    with pytest.raises(ContentError) as e:
        store.publish("dien-truong", 1)
    assert e.value.code == "asset_mismatch"


# ---------------------------------------------------------------- catalog, course page, auth
def test_catalog_filters_by_age_band_with_etag(client, student, two_courses):
    r = client.get("/api/catalog")
    assert [c["id"] for c in r.json()["courses"]] == ["dien-truong"]  # student is g10_12
    assert [c["id"] for c in client.get("/api/catalog?all=1").json()["courses"]] == ["dem-tao", "dien-truong"]
    etag = r.headers["etag"]
    r2 = client.get("/api/catalog", headers={"If-None-Match": etag})
    assert r2.status_code == 304 and not r2.content
    assert client.get("/api/catalog?all=1", headers={"If-None-Match": etag}).status_code == 200


def test_catalog_requires_auth(client, two_courses):
    assert client.get("/api/catalog").status_code == 401


def test_course_page_has_tree(client, student, two_courses):
    d = client.get("/api/courses/dien-truong").json()
    assert d["latest_published"] == 1 and d["title"].startswith("Vật lí")
    lesson = d["tree"][0]["lessons"][0]
    assert lesson == {"id": "l1", "title": "Đường sức điện", "est_minutes": 10, "summary": "s",
                      "key_ideas": ["Đường sức dày thì điện trường mạnh"]}
    assert client.get("/api/courses/nope").status_code == 404


def test_student_cannot_see_drafts_teacher_can(client, student, store, two_courses):
    store.create_draft(make_meta())  # v2 draft
    store.write_pack("dien-truong", 2, make_pack("dien-truong", 2), ASSETS)
    assert client.get("/api/courses/dien-truong/versions/2/pack").status_code == 404
    assert client.get("/api/courses/dien-truong/versions/2/assets/l1/v.mp4").status_code == 404
    assert client.get("/api/courses/dien-truong").json()["versions"][-1]["status"] == "published"
    assert client.get("/api/courses/dien-truong/versions/1/pack").status_code == 200
    # unpublished course is invisible to students
    store.create_draft(make_meta("nhap"))
    assert client.get("/api/courses/nhap").status_code == 404
    login(client, "giaovien", "123456", "teacher")
    assert client.get("/api/courses/dien-truong/versions/2/pack").status_code == 200
    assert client.get("/api/courses/nhap").status_code == 200


def test_pack_headers_and_etag(client, student, two_courses, store):
    r = client.get("/api/courses/dien-truong/versions/1/pack")
    assert r.status_code == 200 and "immutable" in r.headers["cache-control"]
    assert CoursePack.model_validate_json(r.content).version == 1
    sha = store.load_catalog().courses[1].pack_sha256
    assert r.headers["etag"] == f'"{sha}"'
    assert client.get("/api/courses/dien-truong/versions/1/pack", headers={"If-None-Match": f'"{sha}"'}).status_code == 304


def test_cover(client, student, two_courses):
    r = client.get("/api/courses/dien-truong/cover")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.headers["etag"]
    sha = client.get("/api/catalog").json()["courses"][0]["cover_sha256"]
    assert "immutable" in client.get(f"/api/courses/dien-truong/cover?v={sha}").headers["cache-control"]


# ---------------------------------------------------------------- assets: Range and media token
def test_asset_range_and_mime(client, student, two_courses):
    url = "/api/courses/dien-truong/versions/1/assets/l1/v.mp4"
    r = client.get(url)
    assert r.status_code == 200 and r.headers["content-type"] == "video/mp4" and r.content == VIDEO
    assert "immutable" in r.headers["cache-control"] and r.headers["accept-ranges"] == "bytes"
    p = client.get(url, headers={"Range": "bytes=100-199"})
    assert p.status_code == 206 and p.content == VIDEO[100:200]
    assert p.headers["content-range"] == f"bytes 100-199/{len(VIDEO)}"
    tail = client.get(url, headers={"Range": "bytes=-50"})
    assert tail.status_code == 206 and tail.content == VIDEO[-50:]
    assert client.get("/api/courses/dien-truong/versions/1/assets/../pack.json").status_code in (404, 422)
    assert client.get("/api/courses/dien-truong/versions/1/assets/nope.mp4").status_code == 404


def test_media_token_works_on_assets_only(client, student, two_courses):
    token = client.post("/api/media-token").json()["token"]
    anon = client.__class__(client.app)
    url = "/api/courses/dien-truong/versions/1/assets/l1/v.mp4"
    assert anon.get(url).status_code == 401
    assert anon.get(url, params={"t": token}, headers={"Range": "bytes=0-9"}).status_code == 206
    assert anon.get("/api/courses/dien-truong/cover", params={"t": token}).status_code == 200
    assert anon.get("/api/courses/dien-truong/versions/1/pack", params={"t": token}).status_code == 401
    assert anon.get("/api/catalog", params={"t": token}).status_code == 401
    assert anon.get(url, params={"t": token[:-2] + "xx"}).status_code == 401


def test_media_token_expires(client, student, two_courses, clock):
    token = client.post("/api/media-token").json()["token"]
    anon = client.__class__(client.app)
    clock.advance(hours=5)
    assert anon.get("/api/courses/dien-truong/cover", params={"t": token}).status_code == 401


# ---------------------------------------------------------------- enrollments
def test_enrollment_pins_version_and_progress(client, student, store, two_courses):
    r = client.post("/api/enrollments", json={"course_id": "dien-truong"})
    assert r.status_code == 201 and r.json()["version"] == 1 and r.json()["progress_pct"] == 0
    again = client.post("/api/enrollments", json={"course_id": "dien-truong"})
    assert again.status_code == 200 and again.json()["version"] == 1  # idempotent

    store.create_draft(make_meta())
    store.write_pack("dien-truong", 2, make_pack("dien-truong", 2, extra_block=True), ASSETS)
    store.publish("dien-truong", 2)
    e = client.get("/api/enrollments").json()[0]
    assert e["version"] == 1 and e["latest_version"] == 2 and e["update_available"] is True
    assert e["blocks_total"] == 4 and e["course"]["title"].startswith("Vật lí")
    # a new learner enrolling now gets v2
    assert client.post("/api/enrollments", json={"course_id": "dem-tao"}).json()["version"] == 1

    p = client.put("/api/enrollments/dien-truong/progress",
                   json={"lesson_id": "l1", "block_id": "b2", "completed_block_ids": ["b1", "b2"],
                         "quiz": {"item_id": "q1", "correct": False, "seconds": 7}}).json()
    assert p["progress_pct"] == 50.0 and p["last_block_id"] == "b2" and p["quiz"]["q1"]["attempts"] == 1
    p = client.put("/api/enrollments/dien-truong/progress", json={"completed_block_ids": ["b3"],
                                                                 "quiz": {"item_id": "q1", "correct": True}}).json()
    assert p["completed_block_ids"] == ["b1", "b2", "b3"] and p["progress_pct"] == 75.0
    assert p["quiz"]["q1"]["attempts"] == 2 and p["quiz"]["q1"]["correct"] is True
    # b5 exists only in v2: not valid for the pinned v1
    bad = client.put("/api/enrollments/dien-truong/progress", json={"completed_block_ids": ["b5"]})
    assert bad.status_code == 422 and bad.json()["error"] == "unknown_block"


def test_enrollment_errors_and_delete(client, student, two_courses, teacher):
    assert client.post("/api/enrollments", json={"course_id": "nhap"}).status_code == 403  # teacher token is active
    login(client)
    assert client.post("/api/enrollments", json={"course_id": "nope"}).status_code == 404
    assert client.put("/api/enrollments/dien-truong/progress", json={}).json()["error"] == "not_enrolled"
    client.post("/api/enrollments", json={"course_id": "dien-truong"})
    assert client.delete("/api/enrollments/dien-truong").status_code == 204
    assert client.get("/api/enrollments").json() == []
    assert client.delete("/api/enrollments/dien-truong").status_code == 404


# ---------------------------------------------------------------- search (lexical fallback)
def test_search_lexical_is_diacritic_insensitive_and_band_aware(client, student, two_courses):
    r = client.get("/api/search", params={"q": "dien truong"}).json()
    assert r["mode"] == "lexical" and [x["id"] for x in r["results"]] == ["dien-truong"]
    assert r["results"][0]["score"] > 0 and r["suggested_all_ages"] is False
    r = client.get("/api/search", params={"q": "em muốn học Điện trường"}).json()
    assert [x["id"] for x in r["results"]] == ["dien-truong"]
    # in the key ideas only
    assert [x["id"] for x in client.get("/api/search", params={"q": "đường sức dày"}).json()["results"]] == ["dien-truong"]
    # a g1_5 course matches but the student is g10_12: suggest all ages
    r = client.get("/api/search", params={"q": "đếm táo"}).json()
    assert r["results"] == [] and r["suggested_all_ages"] is True
    r = client.get("/api/search", params={"q": "đếm táo", "all": 1}).json()
    assert [x["id"] for x in r["results"]] == ["dem-tao"] and r["suggested_all_ages"] is False
    r = client.get("/api/search", params={"q": "hóa học hữu cơ"}).json()
    assert r["results"] == [] and r["suggested_all_ages"] is False


def test_search_ranks_title_over_body(client, student, store):
    publish_course(store, "a", title="Điện trường", desc="Khóa về đường sức.")
    publish_course(store, "b", title="Sóng cơ", subject="Vật lí", desc="Có nhắc điện trường một lần.",
                   lesson_title="Sóng", idea="Sóng ngang")
    res = client.get("/api/search", params={"q": "điện trường"}).json()["results"]
    assert [x["id"] for x in res][0] == "a" and res[0]["score"] > res[1]["score"]


class FakeEmbedder:
    available = True

    def __init__(self):
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        # 2-d "semantic" vectors: physics-ish vs maths-ish
        return [[1.0, 0.0] if ("điện" in t.lower() or "electric" in t.lower()) else [0.0, 1.0] for t in texts]


def test_search_hybrid_uses_embeddings_and_disk_cache(client, student, two_courses):
    content = client.app.state.content
    content.search.embedder = FakeEmbedder()
    r = client.get("/api/search", params={"q": "electric charge"}).json()  # no lexical overlap, semantic hit
    assert r["mode"] == "hybrid" and [x["id"] for x in r["results"]] == ["dien-truong"]
    calls = content.search.embedder.calls
    client.get("/api/search", params={"q": "electric field"})
    assert content.search.embedder.calls == calls + 1  # only the new query; doc vectors come from the disk cache
    assert list(content.search.cache_dir.glob("*.json"))


# ---------------------------------------------------------------- coming_soon placeholders
def add_placeholder(store: ContentStore, cid="ph-dien-truong-mau", title="Điện trường cơ bản", band="g10_12", n=1):
    from mentor_schemas.course import OutlineChapter, OutlineLesson

    d = store.root / cid
    d.mkdir(parents=True)
    (d / "cover.webp").write_bytes(b"RIFF fake webp " + cid.encode())
    meta = CourseMeta(
        id=cid, title=title, subject="Vật lí", age_band=band, language="vi", teacher_id="ph-teacher", teacher_name="Thầy Dũng",
        description_short="Điện trường qua ví dụ.", outcomes=["Tính E"], cover="cover.webp", status="coming_soon",
        lessons_count=n, est_minutes=12 * n, outline=[OutlineChapter(id="ch1", title="Chương 1", lessons=[
            OutlineLesson(id=f"ch1-l{i}", title=f"Bài {i}", est_minutes=12) for i in range(1, n + 1)])])
    (d / "course.json").write_text(meta.model_dump_json(), "utf-8")
    store.regenerate_catalog()


def test_placeholder_catalog_detail_and_cover(client, student, store, two_courses):
    add_placeholder(store)
    cat = client.get("/api/catalog").json()["courses"]
    assert [c["id"] for c in cat] == ["dien-truong", "ph-dien-truong-mau"]  # real first, then placeholders
    ph = cat[1]
    assert ph["status"] == "coming_soon" and ph["version"] == 0 and ph["published_at"] is None and ph["lessons_count"] == 1
    assert cat[0]["status"] == "live"
    d = client.get("/api/courses/ph-dien-truong-mau").json()
    assert d["status"] == "coming_soon" and d["versions"] == [] and "outline" not in d
    assert d["tree"] == [{"id": "ch1", "title": "Chương 1", "lessons": [
        {"id": "ch1-l1", "title": "Bài 1", "est_minutes": 12, "summary": None, "key_ideas": []}]}]
    assert client.get("/api/courses/ph-dien-truong-mau/cover").status_code == 200


def test_placeholder_refuses_pack_assets_enroll_practice(client, student, store, two_courses):
    add_placeholder(store)
    for url in ("/api/courses/ph-dien-truong-mau/versions/1/pack", "/api/courses/ph-dien-truong-mau/versions/1/assets/a.png"):
        r = client.get(url)
        assert r.status_code == 409 and r.json()["error"] == "coming_soon"
    r = client.post("/api/enrollments", json={"course_id": "ph-dien-truong-mau"})
    assert r.status_code == 409 and r.json()["error"] == "coming_soon"
    assert client.get("/api/enrollments").json() == []
    r = client.post("/api/practice/sessions", json={"source": "course:ph-dien-truong-mau"})
    assert r.status_code == 409 and r.json()["code"] == "coming_soon"


def test_placeholder_search_ranks_real_first_on_ties(client, student, store, two_courses):
    add_placeholder(store, "ph-aaa", title="Điện trường")  # same title as the real course, sorts first alphabetically
    res = client.get("/api/search", params={"q": "điện trường"}).json()["results"]
    ids = [x["id"] for x in res]
    assert "ph-aaa" in ids and ids.index("dien-truong") < ids.index("ph-aaa")
    assert next(x for x in res if x["id"] == "ph-aaa")["status"] == "coming_soon"


def test_embedding_cache_fills_in_batches(client, student, store):
    from mentor_gateway.content import search as srch

    for i in range(srch.EMBED_BATCH + 5):
        add_placeholder(store, f"ph-c{i:03d}", title=f"Điện trường {i}")
    content = client.app.state.content
    content.search.embedder = FakeEmbedder()
    client.get("/api/search", params={"q": "electric charge"})
    assert content.search.embedder.calls == 1 + 2  # the query + two doc batches
    client.get("/api/search", params={"q": "electric field"})
    assert content.search.embedder.calls == 1 + 2 + 1  # docs now come from the cache
