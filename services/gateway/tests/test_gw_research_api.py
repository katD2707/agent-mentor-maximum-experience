"""Nghiên cứu endpoints (CONTRACTS section 15) with fakes only: no network, no model, no real S2 or Asta key."""

import time
from datetime import UTC, datetime

import httpx
import pytest
from gateway_fakes import FrozenClock, login, new_student, set_band
from research_fakes import FakeArxiv, FakeLitClient, FakeLLM, FakeSearcher, FakeSources, arxiv_paper, feed_row, s2_item

from mentor_gateway.research import fulltext
from mentor_gateway.research.tables import PaperRow, ResearchProfileRow

S2_KEY, ASTA_KEY = "s2-secret-key-1234", "asta-secret-key-5678"


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(datetime(2026, 11, 7, 2, 0, tzinfo=UTC))  # Saturday 09:00 in Vietnam


@pytest.fixture
def svc(client):
    s = client.app.state.research
    s.arx = FakeArxiv()
    s.arxiv_search = s.arx.search
    s.lit_client = FakeLitClient(s.arx)
    s.arxiv_searcher = FakeSearcher(s.arx)
    s.src = FakeSources()
    s.transport = s.src.transport()
    s.llm = FakeLLM()

    async def no_abs(aid: str) -> list:
        return []

    async def no_pdf(url: str) -> bytes:
        raise RuntimeError("no network in tests")

    s.fetch_arxiv_feed, s.fetch_pdf = no_abs, no_pdf
    return s


@pytest.fixture
def uni(client, svc):
    return new_student(client, "uni1", "uni")


def wait_job(client, job_id: str) -> dict:
    for _ in range(300):
        job = client.get(f"/api/research/jobs/{job_id}").json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.01)
    raise AssertionError(f"job stuck: {job}")


def wait_until(fn, what: str = "condition"):
    for _ in range(300):
        got = fn()
        if got:
            return got
        time.sleep(0.01)
    raise AssertionError(what)


def card(aid: str = "2603.01234", title: str = "Learning Formation Energies", **kw) -> dict:
    base = {"key": f"arxiv:{aid}", "source": "arxiv", "title": title, "authors": ["Haddad"], "year": 2026, "venue": None,
            "arxiv_id": aid, "doi": None, "s2_id": None, "url": f"https://arxiv.org/abs/{aid}", "excerpt": "Formation energy models.",
            "tldr": None, "snippet": None, "citation_count": None, "has_pdf": True, "in_reading_list": False, "paper_id": None}
    return {**base, **kw}


def add(client, aid: str, title: str = "A paper", **kw):
    return client.post("/api/research/reading-list", json={"card": card(aid, title, **kw)})


def set_topic(client, svc, title: str = "Học máy cho vật liệu") -> None:
    svc.llm.replies["profile"] = {"question": "Mô hình nào dự đoán năng lượng hình thành?", "keywords": ["formation energy", "machine learning"]}
    r = client.put("/api/research/profile", json={"title": title})
    assert r.status_code == 200, r.text


# ---- auth and the band gate -------------------------------------------------------------------------------------------

def test_auth_and_band_gate(client, svc, student, teacher):
    anon = client.get("/api/research", headers={"Authorization": ""})
    assert anon.status_code == 401 and anon.json() == {"error": "unauthorized"}
    login(client, "giaovien", "123456", "teacher")
    assert client.get("/api/research").json() == {"error": "role_mismatch"}
    login(client)  # hocsinh, born 2010: g10_12
    r = client.get("/api/research")
    assert r.status_code == 403 and r.json() == {"error": "not_university"}
    for method, path in [("get", "/api/research/profile"), ("put", "/api/research/profile"), ("get", "/api/research/search?q=x"),
                         ("post", "/api/research/discovery"), ("get", "/api/research/reading-list"), ("get", "/api/research/meetings"),
                         ("get", "/api/research/deadlines"), ("get", "/api/research/experiments")]:
        assert getattr(client, method)(path).status_code == 403, path
    set_band(client, "uni")
    assert client.get("/api/research").status_code == 200
    set_band(client, "g6_9")  # a band change takes effect at once
    assert client.get("/api/research").json() == {"error": "not_university"}


# ---- profile and keys -------------------------------------------------------------------------------------------------

def test_profile_derive_discovery_and_validation(client, svc, uni):
    assert client.get("/api/research/profile").json()["title"] == ""
    svc.arx.default = [arxiv_paper("2603.00001", "Formation energy at scale")]
    svc.llm.replies["reasons"] = {"reasons": [{"key": "arxiv:2603.00001", "reason": "Cùng chủ đề năng lượng hình thành của bạn."}]}
    set_topic(client, svc)
    p = client.get("/api/research/profile").json()
    assert p["keywords"] == ["formation energy", "machine learning"] and p["question"].startswith("Mô hình")
    assert p["asta_connected"] is False and p["s2_connected"] is False
    assert set(p) == {"title", "question", "keywords", "advisor_name", "asta_connected", "s2_connected", "updated_at"}  # no key field
    wait_until(lambda: client.get("/api/research/suggestions").json()["items"], "first discovery run")  # queued by the first title
    # validation: whitespace title, bad keyword lists
    assert client.put("/api/research/profile", json={"title": "   "}).json() == {"error": "empty_title"}
    assert client.put("/api/research/profile", json={"title": ""}).json() == {"error": "empty_title"}
    assert client.put("/api/research/profile", json={"keywords": []}).json() == {"error": "bad_keywords"}
    assert client.put("/api/research/profile", json={"keywords": [f"k{i}" for i in range(9)]}).json() == {"error": "bad_keywords"}
    r = client.put("/api/research/profile", json={"keywords": ["graph", "crystal"], "advisor_name": "TS. Nam"})
    assert r.json()["keywords"] == ["graph", "crystal"] and r.json()["advisor_name"] == "TS. Nam" and r.json()["title"].startswith("Học")


def test_profile_without_model_uses_title_words(client, svc, uni):
    svc.llm = None
    r = client.put("/api/research/profile", json={"title": "Graph neural networks for crystal materials"})
    assert r.status_code == 200 and r.json()["keywords"][:3] == ["graph", "neural", "networks"] and r.json()["question"] == ""


def test_source_keys_validate_store_never_return(client, svc, uni, gw):
    svc.src.valid_keys = {S2_KEY, ASTA_KEY}
    bad = client.put("/api/research/source-keys/s2", json={"key": "wrong-key-123456"})
    assert bad.status_code == 422 and bad.json() == {"error": "invalid_key"}
    assert client.get("/api/research/source-keys").json() == {"asta_connected": False, "s2_connected": False}
    svc.src.s2_status = 503  # source down: nothing saved
    down = client.put("/api/research/source-keys/s2", json={"key": S2_KEY})
    assert down.status_code == 503 and down.json() == {"error": "source_unreachable"}
    assert client.get("/api/research/source-keys").json()["s2_connected"] is False
    svc.src.s2_status = 200
    ok = client.put("/api/research/source-keys/s2", json={"key": S2_KEY})
    assert ok.status_code == 200 and ok.json() == {"asta_connected": False, "s2_connected": True}
    assert client.put("/api/research/source-keys/asta", json={"key": ASTA_KEY}).json() == {"asta_connected": True, "s2_connected": True}
    assert client.put("/api/research/source-keys/s2", json={"key": S2_KEY}).status_code == 200  # replaces
    for path in ("/api/research/source-keys", "/api/research/profile", "/api/research"):
        body = client.get(path).text
        assert S2_KEY not in body and ASTA_KEY not in body
    with gw.db.session() as s:  # stored sealed, opens only with the right owner
        row = s.get(ResearchProfileRow, client.get("/api/me").json()["id"])
        assert S2_KEY not in row.s2_key_enc and ASTA_KEY not in row.asta_key_enc
    assert svc.user_key(row.user_id, "s2") == S2_KEY and svc.user_key(row.user_id, "asta") == ASTA_KEY
    assert client.put("/api/research/source-keys/nope", json={"key": S2_KEY}).json() == {"error": "unknown_source"}
    assert client.delete("/api/research/source-keys/nope").status_code == 404
    assert client.put("/api/research/source-keys/nope", json={"key": "x"}).json() == {"error": "unknown_source"}  # source before body
    gone = client.delete("/api/research/source-keys/s2")
    assert gone.status_code == 200 and gone.json() == {"asta_connected": True, "s2_connected": False}
    assert client.delete("/api/research/source-keys/s2").json() == {"asta_connected": True, "s2_connected": False}  # idempotent
    assert client.put("/api/research/source-keys/s2", json={"key": "short"}).status_code == 422  # min 8 chars


def test_key_validation_rate_limit(client, svc, uni):
    for _ in range(5):
        assert client.put("/api/research/source-keys/s2", json={"key": S2_KEY}).status_code == 200
    r = client.put("/api/research/source-keys/s2", json={"key": S2_KEY})
    assert r.status_code == 429 and r.json()["error"] == "rate_limited" and r.json()["retry_after"] >= 1


# ---- search -----------------------------------------------------------------------------------------------------------

def connect(client, *which: str) -> None:
    for w in which:
        assert client.put(f"/api/research/source-keys/{w}", json={"key": S2_KEY if w == "s2" else ASTA_KEY}).status_code == 200


def test_search_arxiv_only_default_card_fields_no_model(client, svc, uni):
    svc.arx.default = [arxiv_paper("2603.01234v2", "Learning Formation Energies", abstract="Formation energy models usually need tens of thousands of labelled structures. "
                                   "We use fewer. " + "More words. " * 40, authors=tuple(f"Person {i}" for i in range(8)))]
    r = client.get("/api/research/search", params={"q": "formation energy"})
    assert r.status_code == 200
    body = r.json()
    assert body["sources"] == [{"source": "asta", "status": "not_connected"}, {"source": "s2", "status": "not_connected"},
                               {"source": "arxiv", "status": "ok"}]
    c = body["results"][0]
    assert c["key"] == "arxiv:2603.01234" and c["source"] == "arxiv" and c["arxiv_id"] == "2603.01234"  # version stripped
    assert c["url"] == "https://arxiv.org/abs/2603.01234" and c["has_pdf"] is True and len(c["authors"]) == 5
    assert c["tldr"] is None and c["citation_count"] is None and c["snippet"] is None and c["doi"] is None
    assert 0 < len(c["excerpt"]) <= 240 and c["excerpt"].startswith("Formation energy models usually need")
    assert c["in_reading_list"] is False and c["paper_id"] is None and body["page"] == 1 and body["page_size"] == 10
    assert svc.llm.calls == []  # a search never touches the model


def test_search_order_dedupe_and_fields_per_source(client, svc, uni):
    connect(client, "asta", "s2")
    svc.arx.default = [arxiv_paper("2504.14891", "Same paper on arXiv"), arxiv_paper("2603.00002", "Only on arXiv")]
    svc.src.s2_items = [s2_item("a" * 40, "Same paper from S2", arxiv="2504.14891", doi="10.1/zzz"),  # also in Asta: Asta wins
                        s2_item("b" * 40, "S2 only", doi="10.1/ONLY", tldr="TLDR written by S2."),
                        s2_item("c" * 40, "No ids but S2", cites=3, tldr=None)]
    r = client.get("/api/research/search", params={"q": "retrieval augmented generation evaluation"}).json()
    assert [s["status"] for s in r["sources"]] == ["ok", "ok", "ok"]
    keys = [c["key"] for c in r["results"]]
    assert keys.index("arxiv:2504.14891") < keys.index("doi:10.1/only") < keys.index("s2:" + "c" * 40) < keys.index("arxiv:2603.00002")
    assert len(keys) == len(set(keys))
    by = {c["key"]: c for c in r["results"]}
    shown = by["arxiv:2504.14891"]  # one card for the duplicate: the earlier source's (Asta, from the recorded fixture)
    assert shown["source"] == "asta" and shown["citation_count"] == 57 and shown["tldr"] is None and "Retrieval Augmented" in shown["title"]
    s2c = by["doi:10.1/only"]
    assert s2c["source"] == "s2" and s2c["tldr"] == "TLDR written by S2." and s2c["citation_count"] == 12 and s2c["venue"] == "ICML"
    assert s2c["doi"] == "10.1/only" and s2c["s2_id"] == "b" * 40 and s2c["has_pdf"] is True and len(s2c["authors"]) == 5
    assert by["s2:" + "c" * 40]["tldr"] is None  # no S2 tldr: nothing is written by us
    assert by["arxiv:2603.00002"]["source"] == "arxiv" and by["arxiv:2603.00002"]["citation_count"] is None
    assert svc.llm.calls == []
    # each key only went to its own host
    assert {(h, k) for h, k, _ in svc.src.seen if h == "s2"} == {("s2", S2_KEY)}
    assert {(h, k) for h, k, _ in svc.src.seen if h == "asta"} == {("asta", ASTA_KEY)}


def test_asta_snippet_attached_to_matching_card(client, svc, uni):
    connect(client, "asta")
    svc.src.asta_search_items = [{"paperId": "f" * 40, "title": "Attention is All you Need", "year": 2017, "citationCount": 200409,
                                  "externalIds": {"CorpusId": 13756489, "ArXiv": "1706.03762"}, "authors": [{"name": "A. Vaswani"}]},
                                 {"paperId": "e" * 40, "title": "Unrelated", "year": 2020, "externalIds": {"CorpusId": 5}}]
    r = client.get("/api/research/search", params={"q": "scaled dot-product attention"}).json()
    by = {c["title"]: c for c in r["results"]}
    assert by["Attention is All you Need"]["source"] == "asta" and by["Attention is All you Need"]["snippet"].startswith("3.2.1 Scaled")
    assert by["Unrelated"]["snippet"] is None  # a snippet only goes to the paper it came from
    assert svc.llm.calls == []
    svc.src.asta_fail["snippet_search"] = httpx.Response(503)  # no snippet is not an error: the search still works
    ok = client.get("/api/research/search", params={"q": "scaled dot-product attention again"}).json()
    assert ok["sources"][0]["status"] == "ok" and all(c["snippet"] is None for c in ok["results"])


def test_failed_sources_are_skipped_not_errors(client, svc, uni):
    connect(client, "asta", "s2")
    svc.src.s2_status = 429
    svc.src.asta_status = 503
    svc.arx.default = [arxiv_paper("2603.00002", "Only on arXiv")]
    r = client.get("/api/research/search", params={"q": "x y"})
    assert r.status_code == 200
    assert [s["status"] for s in r.json()["sources"]] == ["failed", "failed", "ok"]
    assert [c["key"] for c in r.json()["results"]] == ["arxiv:2603.00002"]
    svc.arx.fail = True  # arXiv down too: empty results, still 200
    r = client.get("/api/research/search", params={"q": "x z"})
    assert r.status_code == 200 and r.json()["results"] == [] and r.json()["sources"][2]["status"] == "failed"


def test_search_depth_limits_sources(client, svc, uni):
    connect(client, "asta", "s2")
    svc.arx.default = [arxiv_paper("2603.00002", "Only on arXiv")]
    svc.src.s2_items = [s2_item("b" * 40, "S2 only", doi="10.1/ONLY")]
    status = lambda r: [s["status"] for s in r["sources"]]  # noqa: E731  (asta, s2, arxiv)
    n0 = len(svc.src.seen)
    quick = client.get("/api/research/search", params={"q": "depth one", "depth": "quick"}).json()
    assert status(quick) == ["skipped", "skipped", "ok"] and {c["source"] for c in quick["results"]} == {"arxiv"}
    assert len(svc.src.seen) == n0  # keys left out are not called at all
    thorough = client.get("/api/research/search", params={"q": "depth two", "depth": "thorough"}).json()
    assert status(thorough) == ["skipped", "ok", "ok"] and "doi:10.1/only" in [c["key"] for c in thorough["results"]]
    assert {h for h, _, _ in svc.src.seen[n0:]} == {"s2"}
    assert status(client.get("/api/research/search", params={"q": "depth three", "depth": "deep"}).json()) == ["ok", "ok", "ok"]
    client.delete("/api/research/source-keys/s2")  # deep without an S2 key: Asta + arXiv, S2 not connected
    assert status(client.get("/api/research/search", params={"q": "depth four", "depth": "deep"}).json()) == ["ok", "not_connected", "ok"]
    assert client.get("/api/research/search", params={"q": "x", "depth": "max"}).status_code == 422


def test_search_filters_paging_and_validation(client, svc, uni):
    connect(client, "s2")
    svc.arx.default = [arxiv_paper(f"2603.{i:05d}", f"arXiv paper {i}", year=2026 if i % 2 else 2020) for i in range(1, 7)]
    svc.src.s2_items = [s2_item(f"{i:040x}", f"S2 paper {i}", year=2024, pdf=i % 2 == 0) for i in range(1, 13)]
    r = client.get("/api/research/search", params={"q": "topic words", "year_min": 2023}).json()
    assert all(c["year"] >= 2023 for c in r["results"]) and len(r["results"]) == 10 and r["has_more"] is True
    page2 = client.get("/api/research/search", params={"q": "topic words", "year_min": 2023, "page": 2}).json()
    assert page2["page"] == 2 and {c["key"] for c in page2["results"]}.isdisjoint({c["key"] for c in r["results"]})
    pdf = client.get("/api/research/search", params={"q": "topic words", "pdf": "true"}).json()
    assert pdf["results"] and all(c["has_pdf"] for c in pdf["results"])
    assert client.get("/api/research/search", params={"q": "   "}).status_code == 422
    assert client.get("/api/research/search", params={"q": "   "}).json() == {"error": "empty_query"}
    assert client.get("/api/research/search", params={"q": "x" * 301}).status_code == 422


def test_search_in_reading_list_and_rate_limit(client, svc, uni):
    svc.arx.default = [arxiv_paper("2603.00001", "Stored paper")]
    assert add(client, "2603.00001", "Stored paper").status_code == 201
    c = client.get("/api/research/search", params={"q": "stored paper"}).json()["results"][0]
    assert c["in_reading_list"] is True and c["paper_id"]
    for i in range(29):
        assert client.get("/api/research/search", params={"q": f"query {i}"}).status_code == 200
    r = client.get("/api/research/search", params={"q": "one too many"})
    assert r.status_code == 429 and r.json()["error"] == "rate_limited" and "retry-after" in r.headers


# ---- related ----------------------------------------------------------------------------------------------------------

def test_related_no_key_then_s2_and_asta(client, svc, uni):
    pid = add(client, "2603.00001", "Stored paper").json()["id"]
    r = client.get(f"/api/research/papers/{pid}/related")
    assert r.status_code == 200 and r.json() == {"available": False, "reason": "no_source_key", "sources": [], "partial": False,
                                                 "citing": {"count": 0, "items": []}, "cited": {"count": 0, "items": []}}
    assert client.get("/api/research/papers/p-nope/related").json() == {"error": "paper_not_found"}
    connect(client, "s2", "asta")
    svc.src.s2_related = {"paperId": "p", "citationCount": 14, "referenceCount": 38,
                          "citations": [{"citingPaper": None, **s2_item("c1" + "0" * 38, "Cites us", cites=5)}],
                          "references": [s2_item("d1" + "0" * 38, "Cited by us", cites=900), s2_item("d2" + "0" * 38, "Less cited", cites=2)]}
    r = client.get(f"/api/research/papers/{pid}/related").json()
    assert r["available"] is True and r["sources"] == ["asta", "s2"] and r["partial"] is False
    assert r["citing"]["count"] == 14 and r["cited"]["count"] == 38
    assert [c["title"] for c in r["cited"]["items"]] == ["Cited by us", "Less cited"] and r["cited"]["items"][0]["source"] == "s2"
    assert any(c["source"] == "s2" for c in r["citing"]["items"]) and any(c["source"] == "asta" for c in r["citing"]["items"])
    again = client.get(f"/api/research/papers/{pid}/related").json()  # cached 24 h per (user, paper)
    assert again == r and sum(1 for h, _, p in svc.src.seen if h == "s2" and "/paper/" in p and not p.endswith("search")) == 1


def test_related_partial_when_a_connected_source_fails(client, svc, uni):
    pid = add(client, "2603.00001", "Stored paper").json()["id"]
    connect(client, "s2", "asta")
    svc.src.asta_status = 503
    svc.src.s2_related = {"paperId": "p", "citationCount": 1, "referenceCount": 0, "citations": [s2_item("c" * 40, "Cites us")], "references": []}
    r = client.get(f"/api/research/papers/{pid}/related").json()
    assert r["available"] is True and r["partial"] is True and r["sources"] == ["s2"] and r["citing"]["count"] == 1


# ---- quick review job -------------------------------------------------------------------------------------------------

REVIEW_PAPERS = [arxiv_paper(f"2603.{i:05d}", f"Review paper {i}", abstract=f"Paper {i} studies X on dataset D{i} and reaches {i}0% accuracy.") for i in range(1, 11)]


def test_review_job_lifecycle(client, svc, uni):
    set_topic(client, svc)
    svc.arx.by_query = {"graph networks": REVIEW_PAPERS[:6], "graph networks survey": REVIEW_PAPERS[4:10]}
    svc.llm.replies["review"] = lambda _m: {
        "rows": [{"key": f"arxiv:2603.{i:05d}", "problem": f"problem {i}", "method": None if i == 2 else "method", "data": "Abstract không nêu" if i == 3 else "D",
                  "result": f"{i}0% accuracy"} for i in range(1, 9)],
        "followups": ["graph networks benchmark", "graph networks", "x", "crystal property prediction", "four", "five words here"]}
    start = client.post("/api/research/review", json={"query": "graph networks", "followups": ["graph networks survey"]})
    assert start.status_code == 202 and start.json()["status"] in ("queued", "running")
    job = wait_job(client, start.json()["job_id"])
    assert job["status"] == "done" and job["kind"] == "review" and job["error"] is None and job["finished_at"]
    res = job["result"]
    assert len(res["papers"]) == 8 and all(p["source"] == "arxiv" for p in res["papers"])
    assert [r["key"] for r in res["matrix"]] == [p["key"] for p in res["papers"]]  # one row per paper, same key
    rows = {r["key"]: r for r in res["matrix"]}
    assert rows["arxiv:2603.00002"]["method"] is None and rows["arxiv:2603.00003"]["data"] is None  # not stated: null, never inferred
    assert rows["arxiv:2603.00001"]["result"] == "10% accuracy"
    assert res["followups"] == ["graph networks benchmark", "crystal property prediction", "five words here"]  # <= 3, not the query itself
    assert [s["query"] for s in res["searches"]] == ["graph networks", "graph networks survey"]
    assert res["caveat_vi"].startswith("Chỉ dựa trên abstract") and res["caveat_en"] and res["coverage"]
    assert svc.llm.count("review") == 1  # one model call for the whole matrix
    assert client.get("/api/research/jobs/rj-nope").json() == {"error": "job_not_found"}


def test_review_job_errors_and_isolation(client, svc, uni, gw):
    svc.arx.by_query = {"q one": REVIEW_PAPERS[:2]}
    start = client.post("/api/research/review", json={"query": "q one"})  # no scripted reply: the model is unavailable
    job = wait_job(client, start.json()["job_id"])
    assert job["status"] == "failed" and job["error"] == "model_unavailable" and job["result"] is None
    svc.arx.fail = True
    job = wait_job(client, client.post("/api/research/review", json={"query": "q two"}).json()["job_id"])
    assert job["status"] == "failed" and job["error"] == "search_failed"
    jid = client.post("/api/research/review", json={"query": "q three"}).json()["job_id"]
    wait_job(client, jid)
    new_student(client, "uni2", "uni")  # another learner cannot read the job
    assert client.get(f"/api/research/jobs/{jid}").json() == {"error": "job_not_found"}


def test_review_job_conflict_followup_limit_and_rate(client, svc, uni):
    import asyncio

    orig = svc.literature

    async def slow(*a, **kw):
        await asyncio.sleep(0.4)
        return await orig(*a, **kw)

    svc.literature = slow
    first = client.post("/api/research/review", json={"query": "slow query"})
    conflict = client.post("/api/research/review", json={"query": "another"})
    assert conflict.status_code == 409 and conflict.json() == {"error": "job_running", "job_id": first.json()["job_id"]}
    wait_job(client, first.json()["job_id"])
    assert client.post("/api/research/review", json={"query": "q", "followups": ["a", "b", "c", "d"]}).status_code == 422
    svc.literature = orig
    svc.arx.by_query = {}
    for i in range(9):  # 10 per hour: the first and the conflict-free ones count
        wait_job(client, client.post("/api/research/review", json={"query": f"rate {i}"}).json()["job_id"])
    r = client.post("/api/research/review", json={"query": "eleventh"})
    assert r.status_code == 429 and r.json()["error"] == "rate_limited"


# ---- discovery and suggestions ----------------------------------------------------------------------------------------

DISCO = [arxiv_paper(f"2611.{i:05d}", f"Fresh paper {i}", abstract=f"Fresh paper {i} on formation energy and machine learning.") for i in range(1, 13)]


def run_discovery(client) -> dict:
    r = client.post("/api/research/discovery")
    assert r.status_code == 202, r.text
    return wait_job(client, r.json()["job_id"])


def test_discovery_suggestions_accept_dismiss_never_again(client, svc, gw, clock):
    new_student(client, "uni3", "uni")
    set_topic(client, svc)
    svc.arx.default = DISCO
    svc.llm.replies["frontier"] = {"queries": ["formation energy prediction", "machine learning materials"]}
    svc.llm.replies["reasons"] = lambda _m: {"reasons": [{"key": f"arxiv:2611.{i:05d}", "reason": f"Lý do {i}!"} for i in range(1, 13)]}
    wait_until(lambda: not svc._running(client.get("/api/me").json()["id"], "discovery"), "auto run done")
    clock.advance(hours=7)  # past the 6 hour limit of the manual run; the automatic one does not count
    job = run_discovery(client)
    assert job["kind"] == "discovery" and job["result"] == {"status": "papers_found", "queries": ["formation energy prediction", "machine learning materials"],
                                                            "new_suggestions": 10}
    sug = client.get("/api/research/suggestions").json()
    assert len(sug["items"]) == 10 and sug["week_of"] == "2026-11-02"  # the Monday of the run
    assert [s["featured"] for s in sug["items"]] == [True] * 5 + [False] * 5
    first = sug["items"][0]
    assert first["status"] == "pending" and first["paper"]["source"] == "arxiv" and first["reason"] == "Lý do 1." and first["query"]
    assert sug["discovery"]["state"] == "idle" and sug["discovery"]["last_status"] == "papers_found"
    assert sug["discovery"]["next_run_at"].startswith("2026-11-09T06:00:00")  # next Monday 06:00 local
    # accept -> reading entry with the suggestion's reason
    acc = client.post(f"/api/research/suggestions/{first['id']}/accept")
    assert acc.status_code == 201 and acc.json()["origin"] == "suggestion" and acc.json()["reason"] == "Lý do 1." and acc.json()["status"] == "new"
    assert client.post(f"/api/research/suggestions/{first['id']}/accept").status_code == 404  # already decided
    # dismiss -> never suggested again
    second = sug["items"][1]
    assert client.post(f"/api/research/suggestions/{second['id']}/dismiss").status_code == 204
    assert client.post(f"/api/research/suggestions/{second['id']}/dismiss").json() == {"error": "suggestion_not_found"}
    clock.advance(hours=7)
    job = run_discovery(client)
    assert job["result"]["new_suggestions"] == 8  # the library returns at most 10 papers, minus the accepted and the dismissed one
    keys = {s["paper"]["key"] for s in client.get("/api/research/suggestions").json()["items"]}
    assert second["paper"]["key"] not in keys and first["paper"]["key"] not in keys
    assert client.post("/api/research/suggestions/sg-nope/accept").json() == {"error": "suggestion_not_found"}


def test_accept_needs_a_free_slot_and_discovery_guards(client, svc, uni, clock):
    svc.arx.default = DISCO[:3]
    assert client.post("/api/research/discovery").json() == {"error": "empty_title"}  # no topic yet
    set_topic(client, svc)
    wait_until(lambda: client.get("/api/research/suggestions").json()["items"], "auto discovery")
    wait_until(lambda: not svc._running(client.get("/api/me").json()["id"], "discovery"))
    assert client.post("/api/research/discovery").status_code == 202  # the first manual run
    wait_until(lambda: not svc._running(client.get("/api/me").json()["id"], "discovery"))
    again = client.post("/api/research/discovery")
    assert again.status_code == 429 and again.json()["error"] == "rate_limited"  # 1 per 6 hours
    for i in range(5):
        assert add(client, f"2601.{i:05d}", f"Listed {i}").status_code == 201
    sid = client.get("/api/research/suggestions").json()["items"][0]["id"]
    full = client.post(f"/api/research/suggestions/{sid}/accept")
    assert full.status_code == 409 and full.json() == {"error": "reading_list_full"}
    assert client.get("/api/research/suggestions").json()["items"][0]["status"] == "pending"  # still there


def test_discovery_none_found_and_failed(client, svc, uni, clock):
    set_topic(client, svc)
    wait_until(lambda: not svc._running(client.get("/api/me").json()["id"], "discovery"))
    svc.arx.default = []
    clock.advance(hours=7)
    job = run_discovery(client)
    assert job["status"] == "done" and job["result"]["status"] == "papers_not_found" and job["result"]["new_suggestions"] == 0
    assert client.get("/api/research/suggestions").json()["discovery"]["last_status"] == "papers_not_found"
    clock.advance(hours=7)

    async def boom(*a, **k):
        raise RuntimeError("down")

    svc.frontier = boom
    job = run_discovery(client)
    assert job["status"] == "failed" and job["error"] == "search_failed"
    assert client.get("/api/research/suggestions").json()["discovery"]["last_status"] == "failed"


def test_discovery_waits_for_a_model_without_english_keywords(client, svc, uni, clock):
    svc.llm = None
    svc.arx.default = DISCO
    uid = client.get("/api/me").json()["id"]
    r = client.put("/api/research/profile", json={"title": "Học máy dự đoán năng lượng"})  # no model: Vietnamese title words
    assert r.status_code == 200
    wait_until(lambda: svc.discovery_waiting(uid), "waiting state")
    assert svc.arx.queries == []  # nothing was searched with "đoán", "năng" ...
    assert client.get("/api/research/suggestions").json()["items"] == []
    assert client.get("/api/research").json()["discovery"]["last_status"] == "waiting_model"
    # the user's own keywords count, even without a model
    client.put("/api/research/profile", json={"keywords": ["formation energy"]})
    wait_until(lambda: client.get("/api/research/suggestions").json()["items"], "run after keyword edit")
    assert client.get("/api/research").json()["discovery"]["last_status"] == "papers_found"


def test_discovery_waiting_runs_again_when_a_model_is_back(client, svc, uni, clock):
    saved, svc.llm = svc.llm, None
    svc.arx.default = DISCO
    uid = client.get("/api/me").json()["id"]
    client.put("/api/research/profile", json={"title": "Học máy dự đoán năng lượng"})
    wait_until(lambda: svc.discovery_waiting(uid), "waiting state")
    svc.llm = saved
    import asyncio
    asyncio.run(svc._tick_user(next(u for u in svc.users.all_provisioned() if u.id == uid), clock()))
    wait_until(lambda: client.get("/api/research/suggestions").json()["items"], "run after the model is back")


# ---- reading list -----------------------------------------------------------------------------------------------------

def test_reading_list_cap_status_remove_and_restore(client, svc, uni):
    ids = []
    for i in range(5):
        r = add(client, f"2601.{i:05d}", f"Listed {i}")
        assert r.status_code == 201 and r.json()["status"] == "new" and r.json()["origin"] == "search" and r.json()["new_this_week"] is True
        ids.append(r.json()["id"])
    full = add(client, "2601.00099", "Sixth")
    assert full.status_code == 409 and full.json() == {"error": "reading_list_full"}
    dup = add(client, "2601.00000", "Listed 0")  # already there: 200 with the existing entry
    assert dup.status_code == 200 and dup.json()["id"] == ids[0]
    rl = client.get("/api/research/reading-list").json()
    assert rl["limit"] == 5 and rl["active_count"] == 5 and len(rl["items"]) == 5
    done = client.put(f"/api/research/papers/{ids[0]}/status", json={"status": "read"})  # read frees a slot
    assert done.status_code == 200 and done.json()["status"] == "read" and done.json()["read_at"]
    assert client.get("/api/research/reading-list").json()["active_count"] == 4
    assert add(client, "2601.00099", "Sixth").status_code == 201
    back = client.put(f"/api/research/papers/{ids[0]}/status", json={"status": "reading"})  # 5 active again: 409
    assert back.status_code == 409 and back.json() == {"error": "reading_list_full"}
    assert client.delete(f"/api/research/reading-list/{ids[1]}").status_code == 204
    assert client.delete(f"/api/research/reading-list/{ids[1]}").json() == {"error": "paper_not_found"}
    assert client.put(f"/api/research/papers/{ids[0]}/status", json={"status": "reading"}).status_code == 200
    assert client.put("/api/research/papers/p-nope/status", json={"status": "read"}).json() == {"error": "paper_not_found"}
    # a read entry stays listed for 14 days only
    client.put(f"/api/research/papers/{ids[2]}/status", json={"status": "read"})
    assert ids[2] in [e["id"] for e in client.get("/api/research/reading-list").json()["items"]]


def test_add_by_link_doi_and_bad_refs(client, svc, uni):
    async def abs_feed(aid: str) -> list:
        return [feed_row(aid, "Resolved from arXiv", abstract="The full abstract of the resolved paper. It has two sentences.")] if aid == "2603.55555" else []

    svc.fetch_arxiv_feed = abs_feed
    r = client.post("/api/research/reading-list", json={"link": "https://arxiv.org/abs/2603.55555v2"})
    assert r.status_code == 201 and r.json()["origin"] == "link" and r.json()["paper"]["title"] == "Resolved from arXiv"
    assert r.json()["paper"]["key"] == "arxiv:2603.55555"
    again = client.post("/api/research/reading-list", json={"link": "arXiv:2603.55555"})
    assert again.status_code == 200 and again.json()["id"] == r.json()["id"]
    assert client.post("/api/research/reading-list", json={"link": "https://arxiv.org/abs/2603.99999"}).json() == {"error": "paper_unresolved"}
    assert client.post("/api/research/reading-list", json={"link": "10.1000/xyz123"}).json() == {"error": "paper_unresolved"}  # no key: no source
    assert client.post("/api/research/reading-list", json={"link": "https://example.org/some/page"}).json() == {"error": "paper_unresolved"}
    assert client.post("/api/research/reading-list", json={"link": "hello there"}).json() == {"error": "bad_paper_ref"}
    assert client.post("/api/research/reading-list", json={"card": card(), "link": "x"}).status_code == 422  # exactly one of
    assert client.post("/api/research/reading-list", json={"upload_path": "inbox/missing.pdf"}).json() == {"error": "upload_not_found"}
    bad = card(title="  ", arxiv_id=None, key="x")
    assert client.post("/api/research/reading-list", json={"card": {**bad, "doi": None, "s2_id": None}}).json() == {"error": "bad_paper_ref"}
    connect(client, "s2")
    svc.src.s2_items = []

    async def s2_get(ref):
        return {"key": "doi:10.1000/xyz123", "source": "s2", "title": "Via S2", "authors": [], "year": 2024, "doi": "10.1000/xyz123",
                "s2_id": "e" * 40, "arxiv_id": None, "url": "https://s2/x", "abstract": "Abstract.", "has_pdf": False}

    class Cli:
        get_paper = staticmethod(s2_get)

    svc.s2_client = lambda key: Cli()
    ok = client.post("/api/research/reading-list", json={"link": "https://doi.org/10.1000/xyz123"})
    assert ok.status_code == 201 and ok.json()["paper"]["title"] == "Via S2"


def test_first_paper_derives_the_profile(client, svc, uni):
    svc.llm.replies["profile"] = {"question": "Q?", "keywords": ["alpha beta"]}
    svc.llm.replies["entry_reason"] = {"reason": "Khớp đề tài của bạn."}
    r = add(client, "2603.00001", "Quantum kernels for chemistry")
    assert r.status_code == 201 and r.json()["reason"] == "Khớp đề tài của bạn."
    p = client.get("/api/research/profile").json()
    assert p["title"] == "Quantum kernels for chemistry" and p["keywords"] == ["alpha beta"]
    add(client, "2603.00002", "Second paper", )
    assert client.get("/api/research/profile").json()["title"] == "Quantum kernels for chemistry"  # only the first paper derives
    reason = client.post("/api/research/reading-list", json={"card": card("2603.00003", "Third"), "reason": "Của riêng tôi"}).json()["reason"]
    assert reason == "Của riêng tôi"


# ---- reader: summary, feedback ----------------------------------------------------------------------------------------

FEEDBACK = {"rows": [{"kind": "right", "text": "Bạn nắm đúng vấn đề chính."},
                     {"kind": "inaccurate", "text": "Bạn viết hơn 18%. Bài đạt 18% trên toàn bộ dữ liệu, còn với 3.000 cấu trúc chỉ là 7%. Bạn muốn nói trường hợp nào?"},
                     {"kind": "missing", "text": "Bạn chưa nhắc tập dữ liệu."}],
            "for_thesis": "Với luận văn của bạn: dữ liệu ít có đủ cho mục 3 không?", "thesis_section": "3"}


def test_summary_then_feedback_flow(client, svc, uni, gw):
    set_topic(client, svc)
    pid = add(client, "2603.01234", "Learning Formation Energies").json()["id"]
    detail = client.get(f"/api/research/papers/{pid}")
    assert detail.status_code == 200 and detail.json()["entry"]["status"] == "reading"  # first open: new -> reading
    assert detail.json()["note"] == {"my_summary": None, "summary_updated_at": None, "feedback": None} and detail.json()["qa_count"] == 0
    no = client.post(f"/api/research/papers/{pid}/feedback")
    assert no.status_code == 409 and no.json() == {"error": "summary_required"}  # Mentor never reviews before the learner writes
    assert svc.llm.count("feedback") == 0
    assert client.put(f"/api/research/papers/{pid}/summary", json={"text": "too short"}).status_code == 422
    summary = "Bài nói mô hình đạt hơn 18% độ chính xác nhờ ít dữ liệu hơn. Mục 3 của mình dùng cách này."
    note = client.put(f"/api/research/papers/{pid}/summary", json={"text": summary})
    assert note.status_code == 200 and note.json()["my_summary"] == summary and note.json()["feedback"] is None
    svc.llm.replies["feedback"] = FEEDBACK
    fb = client.post(f"/api/research/papers/{pid}/feedback")
    assert fb.status_code == 200
    assert [r["kind"] for r in fb.json()["rows"]] == ["right", "inaccurate", "missing"]
    assert fb.json()["for_thesis"].startswith("Với luận văn của bạn:") and fb.json()["created_at"]
    assert "!" not in str(fb.json())  # planner.text.clean applies to what Mentor writes
    again = client.post(f"/api/research/papers/{pid}/feedback")
    assert again.json() == fb.json() and svc.llm.count("feedback") == 1  # returned as stored while the summary is unchanged
    det = client.get(f"/api/research/papers/{pid}").json()
    assert det["note"]["feedback"] == fb.json() and det["thesis_tag"] == "Mục 3 của bạn"
    changed = client.put(f"/api/research/papers/{pid}/summary", json={"text": summary + " Thêm một câu mới."})
    assert changed.json()["feedback"] is None  # a changed summary drops the old feedback
    same = client.put(f"/api/research/papers/{pid}/summary", json={"text": summary + " Thêm một câu mới."})
    assert same.json()["my_summary"].endswith("mới.")
    svc.llm.replies["feedback"] = RuntimeError("quota")
    down = client.post(f"/api/research/papers/{pid}/feedback")
    assert down.status_code == 503 and down.json() == {"error": "model_unavailable"}
    assert client.put("/api/research/papers/p-x/summary", json={"text": "x" * 30}).status_code == 404
    assert client.post("/api/research/papers/p-x/feedback").json() == {"error": "paper_not_found"}


def test_feedback_without_thesis_profile_has_no_for_thesis(client, svc, uni):
    pid = add(client, "2603.01234", "Learning Formation Energies").json()["id"]
    client.put("/api/research/profile", json={"title": "x"})  # a profile exists now, so use a fresh learner instead
    new_student(client, "uni9", "uni")
    pid = add(client, "2603.00077", "Another").json()["id"]
    with svc.db.session() as s:  # make the profile empty again
        s.query(ResearchProfileRow).delete()
    client.put(f"/api/research/papers/{pid}/summary", json={"text": "A summary that is long enough to count."})
    svc.llm.replies["feedback"] = FEEDBACK
    assert client.post(f"/api/research/papers/{pid}/feedback").json()["for_thesis"] is None


# ---- Q&A over SSE -----------------------------------------------------------------------------------------------------

def parse_sse(text: str) -> list[tuple[str, dict]]:
    import json

    out = []
    for block in text.strip().split("\n\n"):
        lines = dict(ln.split(": ", 1) for ln in block.splitlines() if ": " in ln)
        out.append((lines["event"], json.loads(lines["data"])))
    return out


PAPER_TEXT = ("Abstract\nWe study formation energies of crystals.\n\n1 Introduction\nFormation energy models usually need tens of thousands of "
              "labelled structures. " * 3 + "\n\n4 Experiments\n4.1 Data\nWe train on 3,000 structures drawn from the Materials Project database. "
              "The test split holds 500 structures. " * 4 + "\n\n5 Conclusion\nOur model reaches 7% error with only 3,000 structures.\n")


def ask(client, pid: str, text: str, **kw):
    r = client.post(f"/api/research/papers/{pid}/ask", json={"text": text, **kw})
    return r, (parse_sse(r.text) if r.status_code == 200 else None)


def index_paper(client, svc, monkeypatch, pid: str, text: str = PAPER_TEXT) -> None:
    async def pdf(url: str) -> bytes:
        return b"%PDF-1.4 fake"

    svc.fetch_pdf = pdf
    monkeypatch.setattr(fulltext, "extract_pdf_text", lambda data: text)
    client.get(f"/api/research/papers/{pid}")  # opening starts the background fetch
    wait_until(lambda: client.get(f"/api/research/papers/{pid}").json()["fulltext"] == "ready", "fulltext ready")


def test_qa_with_fulltext_citations_and_thread(client, svc, uni, monkeypatch):
    pid = add(client, "2603.01234", "Learning Formation Energies").json()["id"]
    assert client.get(f"/api/research/papers/{pid}").json()["fulltext"] in ("indexing", "none", "ready")
    index_paper(client, svc, monkeypatch, pid)
    import re

    def reply(m):
        idx = int(re.search(r"^\[(\d+)\] [^\n]*Materials Project", m[-1]["content"], re.MULTILINE).group(1))
        return {"found": True, "answer": "Dữ liệu huấn luyện gồm 3.000 cấu trúc từ Materials Project.",
                "citations": [{"passage": idx, "quote": "We train on 3,000 structures drawn from the Materials Project database."},
                              {"passage": 1, "quote": "A sentence the passage does not contain at all"}]}

    svc.llm.replies["qa"] = reply
    r, events = ask(client, pid, "Bài dùng bao nhiêu dữ liệu huấn luyện?")
    assert r.headers["content-type"].startswith("text/event-stream")
    assert [e for e, _ in events] == ["status", "status", "qa", "done"]
    assert events[0][1] == {"stage": "searching"} and events[1][1] == {"stage": "reading"}
    qa = events[2][1]
    assert qa["found"] is True and qa["not_found_reason"] is None and qa["question"].startswith("Bài dùng")
    assert len(qa["citations"]) == 1 and qa["citations"][0]["snippet"].startswith("We train on 3,000")  # the invented quote was dropped
    assert qa["citations"][0]["section"].startswith("Mục 4.1") or "Data" in qa["citations"][0]["section"]
    assert events[3][1] == {"qa_id": qa["id"]}
    thread = client.get(f"/api/research/papers/{pid}/qa").json()
    assert [q["id"] for q in thread] == [qa["id"]] and thread[0]["answer"] == qa["answer"]
    assert client.get(f"/api/research/papers/{pid}").json()["qa_count"] == 1
    from mentor_gateway.planner import events as ev

    assert all(e["kind"] != "ask_question" for e in ev.stored(svc.db, client.get("/api/me").json()["id"], datetime(2026, 1, 1, tzinfo=UTC)))


def test_qa_honest_not_found(client, svc, uni, monkeypatch):
    pid = add(client, "2603.01234", "Learning Formation Energies").json()["id"]
    index_paper(client, svc, monkeypatch, pid)
    svc.llm.replies["qa"] = {"found": True, "answer": "Bài dùng GPU A100.", "citations": [{"passage": 1, "quote": "quote that is nowhere in the text"}]}
    _, events = ask(client, pid, "Dùng GPU gì?")
    qa = events[2][1]
    assert qa["found"] is False and qa["not_found_reason"] == "no_passage" and qa["citations"] == []  # a claim without a citation is not kept
    assert qa["answer"].startswith("Mình không tìm thấy đoạn nào nói về điều này")
    svc.llm.replies["qa"] = {"found": False, "answer": "x", "citations": []}
    assert ask(client, pid, "Hỏi khác")[1][2][1]["not_found_reason"] == "no_passage"


def test_qa_no_fulltext_no_asta_uses_abstract_only(client, svc, uni):
    pid = add(client, "2603.01234", "Learning Formation Energies").json()["id"]
    with svc.db.session() as s:
        s.get(PaperRow, pid).abstract = "Formation energy models usually need tens of thousands of labelled structures."
    svc.llm.replies["qa"] = {"found": True, "answer": "Cần hàng chục nghìn cấu trúc (theo abstract).",
                             "citations": [{"passage": 1, "quote": "need tens of thousands of labelled structures"}]}
    _, events = ask(client, pid, "Cần bao nhiêu cấu trúc?")
    qa = events[2][1]
    assert qa["found"] is True and qa["citations"][0]["section"] == "Abstract"
    svc.llm.replies["qa"] = {"found": False, "answer": "", "citations": []}
    qa = ask(client, pid, "Dùng GPU gì?")[1][2][1]
    assert qa["found"] is False and qa["not_found_reason"] == "no_fulltext"  # no PDF text and no Asta key
    with svc.db.session() as s:
        s.get(PaperRow, pid).abstract = ""
    calls = svc.llm.count("qa")
    qa = ask(client, pid, "Gì nữa?")[1][2][1]
    assert qa["not_found_reason"] == "no_fulltext" and svc.llm.count("qa") == calls  # nothing to read: the model is not asked


def test_qa_with_asta_snippets_and_errors(client, svc, uni):
    connect(client, "asta")
    pid = add(client, "2603.01234", "Learning Formation Energies").json()["id"]
    svc.llm.replies["qa"] = {"found": True, "answer": "Dùng tích vô hướng có chia tỉ lệ.",
                             "citations": [{"passage": 2, "quote": "We compute the dot products of the query with all keys"}]}
    _, events = ask(client, pid, "Attention tính thế nào?")
    qa = events[2][1]
    snip_call = [c for c in svc.src.asta_calls if c[0] == "snippet_search"][0]
    assert snip_call[1]["paper_ids"] == "ARXIV:2603.01234" and qa["found"] is True
    assert qa["citations"][0]["section"] == "Scaled Dot-Product Attention" and "CorpusId" in (qa["citations"][0]["url"] or "")
    svc.llm.replies["qa"] = RuntimeError("model down")
    r, events = ask(client, pid, "Câu nữa?")
    assert [e for e, _ in events] == ["status", "status", "error", "done"]
    assert events[2][1]["code"] == "model_unavailable" and events[3][1] == {"qa_id": None}
    assert client.post("/api/research/papers/p-nope/ask", json={"text": "x"}).status_code == 404
    assert client.post(f"/api/research/papers/{pid}/ask", json={"text": ""}).status_code == 422


# ---- experiments ------------------------------------------------------------------------------------------------------

EXP = {"title": "Baseline trên bộ dữ liệu B", "status": "done", "aim": "Chạy baseline", "setup": "ResNet-18, lr 1e-3, bộ dữ liệu B",
       "result": "Accuracy 71.2%, F1 0.69", "user_note": "Mình thấy hơi thấp", "next": "Thử lr 1e-4", "commit": None, "seed": None}


def test_experiment_structured_and_missing_nudges(client, svc, uni):
    svc.llm.replies["experiment"] = EXP
    r = client.post("/api/research/experiments", json={"text": "Chạy baseline ResNet-18 lr 1e-3 trên B, acc 71.2%, F1 0.69. Mình thấy hơi thấp. Mai thử lr 1e-4."})
    assert r.status_code == 201
    e = r.json()
    assert e["id"] == "EXP-2026-11-07-a" and e["date"] == "2026-11-07" and e["structured"] is True and e["status"] == "done"
    assert e["result"] == "Accuracy 71.2%, F1 0.69" and e["missing"] == ["commit", "seed"] and e["raw_text"].startswith("Chạy baseline")
    sys_prompt = svc.llm.calls[-1][2][0]["content"]
    assert "NEVER interpret" in sys_prompt  # the structuring prompt forbids interpretation
    second = client.post("/api/research/experiments", json={"text": "Run 2, commit a1b2c3d, seed 42, accuracy 72%"})
    assert second.json()["id"] == "EXP-2026-11-07-b" and second.json()["commit"] == "a1b2c3d" and second.json()["seed"] == "42"
    assert second.json()["missing"] == []  # taken from the text when present
    patched = client.patch(f"/api/research/experiments/{e['id']}", json={"commit": "deadbeef", "status": "failed"})
    assert patched.json()["missing"] == ["seed"] and patched.json()["status"] == "failed" and patched.json()["commit"] == "deadbeef"
    assert client.patch(f"/api/research/experiments/{e['id']}", json={"seed": "7"}).json()["missing"] == []
    assert client.get(f"/api/research/experiments/{e['id']}").json()["commit"] == "deadbeef"
    assert client.get("/api/research/experiments/EXP-nope").json() == {"error": "experiment_not_found"}
    assert client.patch("/api/research/experiments/EXP-nope", json={"seed": "1"}).status_code == 404
    from mentor_gateway.planner import events as ev

    kinds = [x["kind"] for x in ev.stored(svc.db, client.get("/api/me").json()["id"], datetime(2026, 1, 1, tzinfo=UTC))]
    assert kinds.count("experiment_logged") == 2


def test_experiment_unstructured_fallback_pagination_and_photo(client, svc, uni):
    svc.llm = None
    r = client.post("/api/research/experiments", json={"text": "x" * 100})
    assert r.status_code == 201  # never 503
    e = r.json()
    assert e["structured"] is False and e["title"] == "x" * 60 and e["status"] == "done" and e["aim"] == "" and e["result"] == ""
    assert e["raw_text"] == "x" * 100 and e["missing"] == ["commit", "seed"]
    g = client.post("/api/research/experiments", json={"text": "GNN seed 42 commit a1b2c3d, MAE 0.12"}).json()
    assert g["commit"] == "a1b2c3d" and g["seed"] == "42" and g["missing"] == []  # taken from the text even without a model
    for i in range(23):
        client.post("/api/research/experiments", json={"text": f"run {i}"})
    ids = [x["id"] for x in client.get("/api/research/experiments", params={"limit": 50}).json()["items"]]
    assert len(ids) == 25 and ids[-1] == "EXP-2026-11-07-a" and ids[0] == "EXP-2026-11-07-y"
    client.post("/api/research/experiments", json={"text": "run 25"})
    last = client.post("/api/research/experiments", json={"text": "run 26"}).json()
    assert last["id"] == "EXP-2026-11-07-aa"  # `aa` after 26 in a day
    page1 = client.get("/api/research/experiments", params={"limit": 20}).json()
    assert len(page1["items"]) == 20 and page1["items"][0]["id"] == "EXP-2026-11-07-aa" and page1["next_before"]
    page2 = client.get("/api/research/experiments", params={"limit": 20, "before": page1["next_before"]}).json()
    assert len(page2["items"]) == 7 and page2["next_before"] is None
    assert {x["id"] for x in page2["items"]}.isdisjoint({x["id"] for x in page1["items"]})
    assert client.post("/api/research/experiments", json={"text": "with photo", "photo_path": "inbox/none.jpg"}).json() == {"error": "upload_not_found"}
    assert client.get("/api/research/experiments", params={"limit": 51}).status_code == 422


def test_experiment_ids_are_per_learner_and_photo_read_by_vision(client, svc, uni, gw):
    from mentor_gateway.mirror import normalize_path

    uid = client.get("/api/me").json()["id"]
    gw.mirror.commit_files(uid, {normalize_path("inbox/table.png"): b"\x89PNG fake"}, author="user", message="photo")
    svc.llm.replies["experiment"] = EXP
    svc.llm.replies["mentor-vision"] = "model | acc\nbase | 71.2"
    r = client.post("/api/research/experiments", json={"text": "bảng kết quả", "photo_path": "inbox/table.png"})
    assert r.status_code == 201 and r.json()["photo_path"] == "inbox/table.png"
    vision = [c for c in svc.llm.calls if c[1] == "mentor-vision"]
    assert len(vision) == 1 and "model | acc" in svc.llm.user_text("experiment")  # the copied table reaches the structuring call
    new_student(client, "uni4", "uni")
    assert client.post("/api/research/experiments", json={"text": "mine"}).json()["id"] == "EXP-2026-11-07-a"  # same id, other learner
    assert client.get("/api/research/experiments/EXP-2026-11-07-a").json()["raw_text"] == "mine"
