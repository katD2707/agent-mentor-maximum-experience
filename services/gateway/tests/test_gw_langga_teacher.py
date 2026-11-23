"""Teacher labels (gv-04): `PUT /teacher/courses/{id}/versions/{v}/labels`."""

from gateway_fakes import login
from test_gw_teacher import built_course, confirm, runner, store, upload  # noqa: F401  (fixtures and helpers of the teacher tests)

L = "/api/teacher/courses/{cid}/versions/{v}/labels"


def put(client, cid, v=1, **body):
    return client.put(L.format(cid=cid, v=v), json=body)


def test_labels_on_a_draft_apply_at_publish(client, teacher, runner, store):
    cid = built_course(client, runner, store, teacher["id"])
    meta = store.load_meta(cid)
    band = meta.age_band
    wrong = "khmt" if band != "uni" else "toan"  # a chicken of the other stage
    r = put(client, cid, chicken=wrong)
    assert r.status_code == 422 and r.json() == {"error": "chicken_not_in_band"}
    assert put(client, cid, chicken="nope").status_code == 422
    assert put(client, cid, level=13).json() == {"error": "bad_level"}

    ok = "kn" if band != "uni" else "daicuong"
    r = put(client, cid, chicken=ok, level=7, difficulty="advanced")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["chicken"] == ok and body["level"] == 7 and body["difficulty"] == "advanced" and body["published"] is False
    assert store.load_meta(cid).chicken is None  # a draft: nothing reaches the course until publish
    confirm(client, cid, 1, "advanced")
    assert client.post(f"/api/teacher/courses/{cid}/versions/1/publish").status_code == 200
    meta = store.load_meta(cid)
    assert meta.chicken == ok and meta.grade == 7 and meta.level == "advanced"
    assert next(e for e in store.load_catalog().courses if e.id == cid).chicken == ok


def test_labels_on_the_published_version_change_the_catalog_at_once(client, teacher, runner, store):
    cid = built_course(client, runner, store, teacher["id"])
    confirm(client, cid, 1, "basic")
    assert client.post(f"/api/teacher/courses/{cid}/versions/1/publish").status_code == 200
    band = store.load_meta(cid).age_band
    ok = "kn" if band != "uni" else "daicuong"
    pack = store.pack_bytes_raw(cid, 1)
    r = put(client, cid, chicken=ok, difficulty="intermediate")
    assert r.status_code == 200 and r.json()["published"] is True
    assert [v.version for v in store.load_meta(cid).versions] == [1]  # labels are not content: no new version
    entry = next(e for e in store.load_catalog().courses if e.id == cid)
    assert entry.chicken == ok and entry.level == "intermediate" and store.pack_bytes_raw(cid, 1) == pack
    # students see it through the catalog
    login(client, "hocsinh", "123456", "student")
    got = client.get("/api/catalog?all=1").json()["courses"]
    assert next(e for e in got if e["id"] == cid)["chicken"] == ok


def test_labels_are_teacher_only(client, teacher, runner, store):
    cid = built_course(client, runner, store, teacher["id"])
    login(client, "hocsinh", "123456", "student")
    assert put(client, cid, chicken="kn").status_code == 403


def test_goals_language_topics_labels(client, teacher, runner, store):
    cid = built_course(client, runner, store, teacher["id"])
    det = client.get(f"/api/teacher/courses/{cid}").json()["course"]["labels"]
    assert set(det) == {"goals", "language", "topics", "suggested", "chicken", "band", "grade"} and det["topics"] == det["suggested"]["topics"]
    assert put(client, cid, goals=["a"] * 7).status_code == 422
    assert put(client, cid, topics=["t"] * 9).status_code == 422
    assert put(client, cid, language="fr").status_code == 422
    r = put(client, cid, goals=["  Hiểu  lực ", ""], language="en", topics=["Lực", "Chuyển động"])
    assert r.status_code == 200, r.text
    assert r.json()["labels"]["goals"] == ["Hiểu lực"]
    det = client.get(f"/api/teacher/courses/{cid}").json()["course"]["labels"]
    assert det["goals"] == ["Hiểu lực"] and det["language"] == "en" and det["topics"] == ["Lực", "Chuyển động"]
    confirm(client, cid, 1, "basic")
    assert client.post(f"/api/teacher/courses/{cid}/versions/1/publish").status_code == 200
    meta = store.load_meta(cid)
    assert meta.outcomes == ["Hiểu lực"] and meta.language == "en" and meta.topics == ["Lực", "Chuyển động"]
    e = next(e for e in store.load_catalog().courses if e.id == cid)
    assert e.outcomes == ["Hiểu lực"] and e.language == "en" and e.topics == ["Lực", "Chuyển động"]
    assert put(client, cid, topics=["Mới"]).status_code == 200
    assert next(e for e in store.load_catalog().courses if e.id == cid).topics == ["Mới"]


def test_saved_chicken_band_grade_come_back_in_the_detail(client, teacher, runner, store):
    cid = built_course(client, runner, store, teacher["id"])
    ok = "kn" if store.load_meta(cid).age_band != "uni" else "daicuong"
    assert put(client, cid, chicken=ok, level=7).status_code == 200
    lab = client.get(f"/api/teacher/courses/{cid}").json()["course"]["labels"]
    assert lab["chicken"] == ok and lab["grade"] == 7
    confirm(client, cid, 1, "basic")
    assert client.post(f"/api/teacher/courses/{cid}/versions/1/publish").status_code == 200
    lab = client.get(f"/api/teacher/courses/{cid}").json()["course"]["labels"]
    assert lab["chicken"] == ok and lab["grade"] == 7 and lab["band"]


def test_a_teacher_deletes_a_draft_but_not_a_published_course(client, teacher, runner, store):
    first = upload(client, "a.jpg")
    cid = first["course_id"]
    r = client.delete(f"/api/teacher/courses/{cid}")
    assert r.status_code == 204, r.text
    assert client.get(f"/api/teacher/courses/{cid}").status_code == 404
    assert cid not in [c["id"] for c in client.get("/api/teacher/courses").json()]
    pub = built_course(client, runner, store, teacher["id"])
    confirm(client, pub, 1, "basic")
    assert client.post(f"/api/teacher/courses/{pub}/versions/1/publish").status_code == 200
    r = client.delete(f"/api/teacher/courses/{pub}")
    assert r.status_code == 409 and r.json()["error"] == "published"
