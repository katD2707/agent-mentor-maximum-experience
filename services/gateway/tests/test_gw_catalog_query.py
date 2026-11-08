"""GET /catalog/query (filters, facets, sort, paging, students) and GET /search/suggest (offline: lexical only)."""

import pytest
from mentor_schemas.course import CourseMeta, OutlineChapter, OutlineLesson
from test_gw_courses import publish_course, store  # noqa: F401  (the `store` fixture)

from mentor_gateway.content import ContentStore


def add_soon(root: ContentStore, cid: str, title: str, *, subject="Toán", band="g10_12", lang="vi", teacher="Cô Lan",
             level="basic", minutes=40, media=("video", "quiz")) -> None:
    d = root.root / cid
    d.mkdir(parents=True)
    (d / "cover.webp").write_bytes(b"RIFF fake webp " + cid.encode())
    meta = CourseMeta(
        id=cid, title=title, subject=subject, age_band=band, language=lang, teacher_id="ph-teacher", teacher_name=teacher,
        description_short="Mô tả.", outcomes=["a"], cover="cover.webp", status="coming_soon", lessons_count=-(-minutes // 60),
        est_minutes=minutes, media=list(media), level=level,
        outline=[OutlineChapter(id="ch1", title="C", lessons=[
            OutlineLesson(id=f"ch1-l{n + 1}", title=f"B{n}", est_minutes=min(60, minutes - 60 * n)) for n in range(-(-minutes // 60))])])
    (d / "course.json").write_text(meta.model_dump_json(), "utf-8")
    root.regenerate_catalog()


@pytest.fixture
def cat(client, student, store):  # noqa: F811
    """2 live courses (Vật lí g10_12, Toán 1 g1_5) and 14 placeholders."""
    publish_course(store, "dien-truong")
    publish_course(store, "dem-tao", band="g1_5", title="Toán 1: Đếm táo", subject="Toán", desc="Đếm các số đến 10.",
                   lesson_title="Cún đếm táo", idea="Chạm từng quả táo")
    for i in range(12):  # 12 maths courses in g10_12, durations 30, 50, ... and levels cycling
        add_soon(store, f"ph-toan-{i:02d}", f"Toán {i + 1}: Chuyên đề {i}", minutes=30 + 20 * i,
                 level=("basic", "intermediate", "advanced")[i % 3], teacher=("Cô Lan", "Thầy Hải")[i % 2])
    add_soon(store, "ph-ielts", "IELTS Reading", subject="Tiếng Anh", lang="en", teacher="Ms. Pham", level="advanced",
             minutes=200, media=("reading", "quiz"))
    add_soon(store, "ph-tich-phan", "Giải tích: Tích phân bội", subject="Giải tích", band="uni", teacher="TS. Quang",
             level="advanced", minutes=240, media=("reading",))
    return store


def q(client, **params):
    r = client.get("/api/catalog/query", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def ids(r):
    return [x["id"] for x in r["items"]]


def facet(r, key):
    return {f["v"]: f["n"] for f in r["facets"][key]}


def test_paging_is_ten_per_page_and_last_page_is_short(client, cat):
    r = q(client)
    assert r["total"] == 16 and r["page_size"] == 10 and r["pages"] == 2 and len(r["items"]) == 10
    r2 = q(client, page=2)
    assert r2["page"] == 2 and len(r2["items"]) == 6 and not set(ids(r)) & set(ids(r2))
    assert q(client, page=99)["page"] == 2  # past the end clamps to the last page
    assert q(client, page_size=5)["pages"] == 4


def test_default_order_is_real_courses_first_then_placeholders(client, cat):
    r = q(client)
    assert set(ids(r)[:2]) == {"dien-truong", "dem-tao"} and r["items"][2]["status"] == "coming_soon"


def test_filters_combine_and_or(client, cat):
    r = q(client, band="g10_12", subject="Toán")
    assert r["total"] == 12 and all(i["subject"] == "Toán" for i in r["items"] + q(client, band="g10_12", subject="Toán", page=2)["items"])
    assert q(client, band="g10_12", subject="Toán", level="advanced")["total"] == 4
    assert q(client, band="g10_12", subject="Toán", level=["advanced", "basic"])["total"] == 8  # OR inside one facet
    assert q(client, language="en")["total"] == 1
    assert q(client, status="live")["total"] == 2 and q(client, status="coming_soon")["total"] == 14
    assert q(client, teacher="Thầy Hải")["total"] == 6
    assert q(client, media="audio")["total"] == 0
    assert q(client, media="reading")["total"] >= 4


def test_duration_buckets_come_from_est_minutes(client, cat):
    # g10_12 maths: 30, 50 | 70 .. 170 (6 courses: 70,90,110,130,150,170) | 190, 210, 230, 250
    assert q(client, subject="Toán", band="g10_12", duration="short")["total"] == 2
    assert q(client, subject="Toán", band="g10_12", duration="medium")["total"] == 6
    assert q(client, subject="Toán", band="g10_12", duration="long")["total"] == 4


def test_facet_counts_ignore_their_own_filter_but_respect_the_others(client, cat):
    r = q(client, band="g10_12", subject="Toán")
    assert facet(r, "subject")["Toán"] == 12 and facet(r, "subject")["Vật lí"] == 1  # siblings stay visible
    assert facet(r, "band") == {"g1_5": 1, "g6_9": 0, "g10_12": 12, "uni": 0}  # band count ignores the band filter, not the subject
    assert facet(r, "level") == {"basic": 4, "intermediate": 4, "advanced": 4}
    assert facet(r, "language") == {"vi": 12, "en": 0}
    assert facet(r, "status") == {"live": 0, "coming_soon": 12}
    assert facet(r, "teacher") == {"Cô Lan": 6, "Thầy Hải": 6}
    assert r["facets"]["subject"][0]["v"] == "Toán"  # most hits first
    assert q(client, band="g1_5")["facets"]["duration"][0]["n"] >= 0


def test_facets_follow_the_text_query(client, cat):
    r = q(client, q="ielts")
    assert r["total"] == 1 and facet(r, "subject") == {"Tiếng Anh": 1} and facet(r, "language")["en"] == 1


def test_sort_new_pop_duration(client, cat):
    assert client.post("/api/enrollments", json={"course_id": "dien-truong"}).status_code in (200, 201)
    r = q(client, sort="pop")
    assert ids(r)[0] == "dien-truong" and r["items"][0]["students"] == 1 and r["items"][1]["students"] == 0
    new = q(client, sort="new")
    assert [i["status"] for i in new["items"]][:2] == ["live", "live"] and new["items"][2]["status"] == "coming_soon"
    asc = [i["est_minutes"] for i in q(client, sort="dur", dir="asc", status="coming_soon")["items"]]
    desc = [i["est_minutes"] for i in q(client, sort="dur", dir="desc", status="coming_soon")["items"]]
    assert asc == sorted(asc) and asc[0] == 30
    assert desc == sorted(desc, reverse=True) and desc[0] == 250


def test_students_counts_enrollments_from_the_ops_db(client, cat):
    assert q(client, q="dien truong")["items"][0]["students"] == 0
    client.post("/api/enrollments", json={"course_id": "dien-truong"})
    client.post("/api/enrollments", json={"course_id": "dien-truong"})  # idempotent: still one student
    r = q(client, q="dien truong")
    assert r["items"][0]["id"] == "dien-truong" and r["items"][0]["students"] == 1
    assert all(i["students"] == 0 for i in q(client, status="coming_soon")["items"])
    assert client.get("/api/search", params={"q": "dien truong"}).json()["results"][0]["students"] == 1


def test_level_is_on_every_item(client, cat):
    items = q(client, status="coming_soon")["items"]
    assert {i["level"] for i in items} == {"basic", "intermediate", "advanced"}


def test_text_query_is_accent_insensitive_and_matches_teacher_and_subject(client, cat):
    assert ids(q(client, q="TÍCH PHÂN"))[0] == "ph-tich-phan"
    assert ids(q(client, q="tich phan"))[0] == "ph-tich-phan"
    assert ids(q(client, q="quang")) == ["ph-tich-phan"]  # teacher name
    assert q(client, q="thay hai")["total"] == 6
    assert q(client, q="giai tich")["items"][0]["id"] == "ph-tich-phan"  # subject
    r = q(client, q="toan 1", band="g1_5")
    assert ids(r) == ["dem-tao"]  # title "Toán 1: Đếm táo"
    assert q(client, q="english")["total"] == 1  # language word counts as a match too


def test_relevance_puts_title_prefix_first(client, cat):
    r = q(client, q="toan", band="g10_12")
    assert r["items"][0]["title"].lower().startswith("toán")
    assert r["total"] == 12


def test_did_you_mean_for_typos(client, cat):
    r = q(client, q="tich phna")
    assert r["did_you_mean"] and "phân" in r["did_you_mean"]
    r = q(client, q="ilets")
    assert r["did_you_mean"] == "ielts"
    assert q(client, q="tich phan")["did_you_mean"] is None  # fine as typed
    assert q(client, q="tích ph")["did_you_mean"] is None  # a half-typed word is not a typo
    assert q(client)["did_you_mean"] is None


def test_no_result_returns_empty_page_with_one_page(client, cat):
    r = q(client, q="zzzzzz")
    assert r["total"] == 0 and r["pages"] == 1 and r["items"] == [] and r["page"] == 1


def test_bad_params_are_rejected(client, cat):
    assert client.get("/api/catalog/query", params={"sort": "price"}).status_code == 422
    assert client.get("/api/catalog/query", params={"page": 0}).status_code == 422
    assert client.get("/api/catalog/query", params={"page_size": 500}).status_code == 422


def test_suggest_groups_courses_subjects_teachers(client, cat):
    r = client.get("/api/search/suggest", params={"q": "toan"}).json()
    assert r["subjects"] == ["Toán"] and len(r["courses"]) == 4 and all("Toán" in c["title"] for c in r["courses"])
    r = client.get("/api/search/suggest", params={"q": "THAY"}).json()
    assert r["teachers"] == ["Thầy Minh", "Thầy Hải"] and r["courses"] == []
    r = client.get("/api/search/suggest", params={"q": "tich phan"}).json()
    assert [c["id"] for c in r["courses"]] == ["ph-tich-phan"] and r["subjects"] == [] and r["did_you_mean"] is None
    r = client.get("/api/search/suggest", params={"q": "tich phna"}).json()
    assert r["courses"] == [] and "phân" in (r["did_you_mean"] or "")


def test_catalog_query_requires_auth(client, cat):
    client.headers.pop("Authorization", None)
    assert client.get("/api/catalog/query").status_code == 401
    assert client.get("/api/search/suggest", params={"q": "a"}).status_code == 401


def test_students_are_active_learners_not_every_enrollment(client, cat):
    """A student whose enrollment has been idle for more than ACTIVE_LEARNER_DAYS no longer counts (nor lifts Phổ biến)."""
    from datetime import timedelta

    from sqlalchemy import update

    from mentor_gateway.content.service import ACTIVE_LEARNER_DAYS
    from mentor_gateway.content.tables import Enrollment

    client.post("/api/enrollments", json={"course_id": "dien-truong"})
    assert q(client, q="dien truong")["items"][0]["students"] == 1
    content = client.app.state.content
    with content.db.session() as s:
        s.execute(update(Enrollment).values(updated_at=content.clock() - timedelta(days=ACTIVE_LEARNER_DAYS + 1)))
    assert all(i["students"] == 0 for i in q(client, sort="pop")["items"])
