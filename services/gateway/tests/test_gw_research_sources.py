"""Asta and Semantic Scholar clients (restored from the old gateway, adapted to the learner's own key), date parsing,
paper text retrieval and the schema migration. Recorded Asta fixtures in fixtures/asta; no network."""

import re
from datetime import date, datetime, timedelta

import pytest
from research_fakes import FakeSources, s2_item

from mentor_gateway.db import Database
from mentor_gateway.research import dates, fulltext
from mentor_gateway.research.asta import AstaClient, AstaError, parse_sse, tool_result
from mentor_gateway.research.base import Limiter
from mentor_gateway.research.fulltext import Passage, quote_in, split_passages, top_passages
from mentor_gateway.research.sources import AstaSource, S2Client, SourceError, excerpt, item_to_card, paper_key, s2_ref


def _sse(name: str, rid: int) -> bytes:
    from research_fakes import _sse as load

    return load(name, rid)


# ---- Asta MCP client (ported tests) ----------------------------------------------------------------------------------

def test_parse_sse_skips_pings_and_tool_result_shapes() -> None:
    [msg] = parse_sse(_sse("get_citations.sse", 7))
    assert msg["id"] == 7 and tool_result(msg["result"])[0]["citingPaper"]["title"].startswith("Evaluation")
    [detail] = parse_sse(_sse("get_paper.sse", 1))
    assert tool_result(detail["result"])["paperId"] == "204e3073870fae3d05bcbc2f6a8e263d9b72e776"
    for text, status in [("Paper not found", 404), ("HTTP 429 Too Many Requests", 503), ("boom", 502)]:
        with pytest.raises(AstaError) as exc:
            tool_result({"isError": True, "content": [{"type": "text", "text": text}]})
        assert exc.value.status == status


async def test_client_sends_the_key_only_as_a_header_and_reuses_the_session() -> None:
    src = FakeSources()
    client = AstaClient(api_key="secret", transport=src.transport())
    await client.call_tool("get_citations", {"paper_id": "x"})
    await client.call_tool("get_citations", {"paper_id": "y"})
    assert [t for _, _, t in src.seen] == ["get_citations", "get_citations"] and set(src.keys) == {"secret"}


async def test_refused_key_is_its_own_status_and_never_in_the_message() -> None:
    src = FakeSources()
    src.valid_keys = {"good-key-123"}
    with pytest.raises(AstaError) as exc:
        await AstaClient(api_key="bad-key-123456", transport=src.transport()).call_tool("get_paper", {})
    assert exc.value.status == 401 and "bad-key-123456" not in str(exc.value)
    with pytest.raises(ValueError):
        AstaClient("http://asta-tools.allen.ai/mcp/v1")  # https only


# ---- sources: parsers and clients --------------------------------------------------------------------------------------

async def test_asta_search_card_from_recorded_response() -> None:
    src = FakeSources()
    cards = await AstaSource("k" * 10, transport=src.transport()).search("retrieval augmented generation evaluation", limit=3, year_min=2023)
    name, args = src.asta_calls[0]
    assert name == "search_papers_by_relevance" and args["publication_date_range"] == "2023:" and args["limit"] == 3
    first = cards[0]
    assert first["key"] == "arxiv:2504.14891" and first["source"] == "asta" and first["citation_count"] == 57 and first["tldr"] is None
    assert first["doi"] == "10.48550/arxiv.2504.14891" and first["has_pdf"] is False  # openAccessPdf url is empty in the recording
    assert len(first["authors"]) == 5 and first["year"] == 2025


async def test_asta_citations_sorted_and_unescaped_and_snippets() -> None:
    src = FakeSources()
    asta = AstaSource("k" * 10, transport=src.transport())
    cites = await asta.citations("ARXIV:1706.03762", limit=20)
    assert [c["citation_count"] or 0 for c in cites] == sorted((c["citation_count"] or 0 for c in cites), reverse=True)
    assert any(c["venue"] == "Computers & Chemical Engineering" for c in cites)  # html-unescaped
    assert all(c["source"] == "asta" for c in cites)
    [snip] = await asta.snippets("scaled dot-product attention", paper_ids=["ARXIV:1706.03762"])
    assert snip["corpus_id"] == "13756489" and snip["section"] == "Scaled Dot-Product Attention" and snip["score"] == pytest.approx(0.612, abs=1e-3)
    assert snip["url"] == "https://api.semanticscholar.org/CorpusId:13756489" and snip["text"].startswith("3.2.1 Scaled")
    assert src.asta_calls[-1][1]["paper_ids"] == "ARXIV:1706.03762"


async def test_s2_client_search_related_validate_and_errors() -> None:
    src = FakeSources()
    src.s2_items = [s2_item("a" * 40, "Paper A", arxiv="2401.00001v3", cites=5), {"title": "no id"}]
    s2 = S2Client("my-s2-key-123", transport=src.transport())
    cards, more = await s2.search("graph-neural networks", limit=10, year_min=2022)
    assert [c["key"] for c in cards] == ["arxiv:2401.00001"] and more is True and cards[0]["tldr"] == "A one line S2 summary."
    assert src.seen[-1] == ("s2", "my-s2-key-123", "/graph/v1/paper/search")
    await s2.validate()
    src.s2_status = 429
    with pytest.raises(SourceError) as exc:
        await s2.validate()
    assert exc.value.kind == "unreachable"
    src.s2_status = 200
    src.valid_keys = {"other-key-1234"}
    with pytest.raises(SourceError) as exc:
        await s2.validate()
    assert exc.value.kind == "invalid_key" and "my-s2-key-123" not in str(exc.value)


def test_card_keys_excerpt_and_ids() -> None:
    assert paper_key("2401.00001v2", "10.1/X", "s") == "arxiv:2401.00001"
    assert paper_key(None, "10.1/ABC", "s") == "doi:10.1/abc" and paper_key(None, None, "abc") == "s2:abc" and paper_key(None, None, None) is None
    c = item_to_card(s2_item("p" * 40, "T", doi="10.1/X"), "s2")
    assert c["key"] == "doi:10.1/x" and c["tldr"] and item_to_card(s2_item("p" * 40, "T"), "asta")["tldr"] is None  # tldr is S2's own, S2 cards only
    assert s2_ref("2401.00001v2", "10.1/x", None) == "ARXIV:2401.00001" and s2_ref(None, "10.1/x", None) == "DOI:10.1/x" and s2_ref(None, None, None) is None
    long = "First sentence here. " * 30
    assert excerpt(long).endswith("here.") and len(excerpt(long)) <= 240
    assert len(excerpt("word " * 200)) <= 240 and excerpt("") == "" and excerpt(None) == ""


# ---- dates ------------------------------------------------------------------------------------------------------------

TODAY = date(2026, 11, 7)


@pytest.mark.parametrize("text,day,time,original", [
    ("nộp full paper 15/11, 23:59 AoE", date(2026, 11, 16), "18:59", "23:59 AoE 15/11"),
    ("họp thứ Tư 11/11 14:00", date(2026, 11, 11), "14:00", None),
    ("deadline Nov 16 2026 11:59pm PST", date(2026, 11, 17), "14:59", "23:59 PST 16/11"),
    ("2026-12-01 9h30", date(2026, 12, 1), "09:30", None),
    ("ngày 3 tháng 12 lúc 9h", date(2026, 12, 3), "09:00", None),
    ("23:59 UTC-5 on 1/12", date(2026, 12, 2), "11:59", "23:59 UTC-5 01/12"),
    ("trước thứ Sáu", date(2026, 11, 13), None, None),
])
def test_parse_and_convert(text, day, time, original) -> None:
    local = dates.to_vietnam(dates.parse_when(text, TODAY))
    assert (local.day, local.time, local.original) == (day, time, original)


def test_unclear_and_missing() -> None:
    assert dates.to_vietnam(dates.parse_when("một ngày nào đó", TODAY)) is None
    month = dates.to_vietnam(dates.parse_when("cuối tháng 12", TODAY))
    assert month.day == date(2026, 12, 31) and month.confirmed is False
    assert dates.to_vietnam(dates.parse_when("5/11", TODAY)).day == date(2026, 11, 5)  # a few days ago stays this year
    assert dates.to_vietnam(dates.parse_when("5/1", TODAY)).day == date(2027, 1, 5)  # long past: next year
    assert dates.zone_hours("AoE") == -12.0 and dates.zone_hours(None) == 7.0 and dates.zone_hours("Asia/Ho_Chi_Minh") == 7.0 and dates.zone_hours("Mars/Base") is None


# ---- paper text -------------------------------------------------------------------------------------------------------

TEXT = ("Abstract\nWe study formation energy of crystals with small labelled sets.\n\n1 Introduction\nIntro words about crystals and energy models.\n\n"
        "4.1 Data\nWe train on 3,000 structures drawn from the Materials Project database. The split is random.\n\n"
        "5 Conclusion\nOur model reaches 7% error with only three thousand structures.\n")


def test_passages_sections_retrieval_and_quote_check() -> None:
    ps = split_passages(TEXT * 3, "vi")
    labels = {p.section for p in ps}
    assert "Mục 4.1, Data" in labels and "Abstract" in labels and any(p.section.startswith("Mục 5") for p in ps)
    assert {p.section for p in split_passages(TEXT, "en")} >= {"Section 4.1, Data"}
    best = top_passages(ps, "How many structures were used to train from the Materials Project?", k=2)
    assert best and "Materials Project" in best[0].text
    spread = top_passages(ps, "Bao nhiêu dữ liệu?", k=3)  # no shared words (another language): passages spread through the paper
    assert len(spread) == 3
    assert quote_in("we train on 3,000 structures  drawn from", "We train on 3,000 Structures drawn from the Materials Project.")
    assert not quote_in("completely different words in here", "We train on 3,000 structures.") and not quote_in("short", "short text")
    assert top_passages([], "x") == []
    p = Passage("s", "t")
    assert p.origin == "fulltext"


def test_pdf_extraction_with_pypdf_and_bad_input() -> None:
    body = b"BT /F1 24 Tf 72 700 Td (Hello Mentor paper) Tj ET"
    objs = [b"<</Type/Catalog/Pages 2 0 R>>", b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
            b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>",
            b"<</Length " + str(len(body)).encode() + b">>\nstream \n" + body + b"\nendstream",
            b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>"]
    pdf, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(pdf))
        pdf += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(pdf)
    pdf += b"xref\n0 6\n0000000000 65535 f \n" + b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    pdf += b"trailer<</Root 1 0 R/Size 6>>\nstartxref\n" + str(xref).encode() + b"\n%%EOF"
    assert "Hello Mentor paper" in fulltext.extract_pdf_text(pdf)
    assert fulltext.extract_pdf_text(b"not a pdf at all") == ""


def test_text_cache_is_per_learner(tmp_path) -> None:
    cache = fulltext.TextCache(tmp_path)
    cache.write("u1", "p-1", "hello")
    assert cache.read("u1", "p-1") == "hello" and cache.read("u2", "p-1") is None


# ---- limiter, migration -----------------------------------------------------------------------------------------------

def test_limiter_window_is_per_user_and_per_name() -> None:
    now = [datetime(2026, 11, 7, 9, 0)]
    lim = Limiter(lambda: now[0])
    for _ in range(3):
        assert lim.check("u", "x", 3, timedelta(minutes=1)) is None
    wait = lim.check("u", "x", 3, timedelta(minutes=1))
    assert wait is not None and 1 <= wait <= 61
    assert lim.check("v", "x", 3, timedelta(minutes=1)) is None and lim.check("u", "y", 3, timedelta(minutes=1)) is None
    now[0] += timedelta(seconds=61)
    assert lim.check("u", "x", 3, timedelta(minutes=1)) is None


def test_migration_adds_goal_columns_once_and_create_all_is_idempotent(tmp_path) -> None:
    from sqlalchemy import inspect, text

    url = f"sqlite:///{(tmp_path / 'old.db').as_posix()}"
    old = Database(url)
    with old.engine.begin() as conn:  # a study_goals table as it was before Nghiên cứu
        conn.execute(text("CREATE TABLE study_goals (id VARCHAR(64) PRIMARY KEY, user_id VARCHAR(64), kind VARCHAR(10), title VARCHAR(200), "
                          "deadline DATE, course_ids JSON, dismissed BOOLEAN, created_at DATETIME, updated_at DATETIME)"))
        conn.execute(text("INSERT INTO study_goals VALUES ('g-1','u','student','t',NULL,'[]',0,'2026-01-01','2026-01-01')"))
    import mentor_gateway.planner.tables
    import mentor_gateway.research.tables  # noqa: F401

    old.create_all()
    old.create_all()  # idempotent
    cols = {c["name"] for c in inspect(old.engine).get_columns("study_goals")}
    assert {"source", "milestones"} <= cols
    with old.engine.begin() as conn:
        assert conn.execute(text("SELECT source FROM study_goals WHERE id='g-1'")).scalar() == "learning"  # existing rows default to learning
    for table in ("research_profile", "paper", "reading_entry", "paper_note", "paper_qa", "experiment", "meeting", "suggestion"):
        assert inspect(old.engine).has_table(table)
    assert re.fullmatch(r"[a-z_]+", "research_profile")
    old.dispose()
