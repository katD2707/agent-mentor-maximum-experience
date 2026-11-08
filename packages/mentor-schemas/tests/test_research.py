"""Round-trips of the examples in CONTRACTS.md section 15 (mockup sample data)."""

import pytest
from pydantic import ValidationError

from mentor_schemas.research import (
    RESEARCH_EVENT_KINDS,
    ActionItem,
    AddPaperRequest,
    Agenda,
    AgendaItem,
    DiscoveryStatus,
    Experiment,
    ExperimentInput,
    FeedbackRow,
    LiveLine,
    Meeting,
    MeetingInput,
    Milestone,
    MilestoneInput,
    PaperCard,
    PaperDetail,
    PaperFeedback,
    PaperNote,
    PaperQA,
    QaCitation,
    ReadingEntry,
    ReadingList,
    ReadNext,
    RelatedPapers,
    ResearchJob,
    ResearchOverview,
    ResearchProfile,
    ReviewResult,
    ReviewRow,
    SearchResponse,
    SourceKeysStatus,
    Suggestion,
    SummaryInput,
    UpcomingItem,
)

NOW = "2026-11-07T09:00:00+07:00"


def rt(model, data):
    obj = model.model_validate(data)
    assert model.model_validate_json(obj.model_dump_json()) == obj
    assert model.model_validate(obj.model_dump(mode="json")) == obj
    return obj


def card(**kw):
    base = {"key": "arxiv:2603.01234", "source": "arxiv", "title": "Learning Formation Energies from Fewer Than Five Thousand Crystal Structures",
            "authors": ["Haddad", "Nguyen"], "year": 2026, "venue": None, "arxiv_id": "2603.01234", "doi": None, "s2_id": None,
            "url": "https://arxiv.org/abs/2603.01234", "excerpt": "Formation energy models usually need tens of thousands of labelled structures.",
            "tldr": None, "snippet": None, "citation_count": None, "has_pdf": True, "in_reading_list": False, "paper_id": None}
    return {**base, **kw}


def pham():
    return card(key="arxiv:2601.08832", source="s2", title="Equivariant Message Passing for Formation Energy Prediction in Inorganic Crystals",
                authors=["Pham", "Okafor", "Lindqvist"], arxiv_id="2601.08832", venue="Journal of Computational Materials",
                tldr="An equivariant message passing network.", citation_count=14, in_reading_list=True, paper_id="pp-1")


def entry():
    return {"id": "pp-1", "paper": pham(), "status": "reading", "reason": "Dùng cùng bộ dữ liệu với chương 3 của bạn.", "origin": "suggestion",
            "new_this_week": False, "minutes_spent": 25, "added_at": NOW, "opened_at": NOW, "read_at": None}


def profile():
    return {"title": "Mạng nơ-ron đồ thị dự đoán năng lượng hình thành của vật liệu tinh thể khi chỉ có vài nghìn mẫu.",
            "question": "", "keywords": ["graph neural network", "formation energy", "crystal structure", "small data", "uncertainty"],
            "advisor_name": "", "asta_connected": False, "s2_connected": True, "updated_at": NOW}


def milestone():
    return {"id": "ms-1", "title": "Nộp full paper hội nghị", "due_date": "2026-11-16", "due_time": "18:59", "original_text": "23:59 AoE 15/11",
            "confirmed": True, "kind": "submission", "thesis": True, "done": False, "days_left": 9, "planned_sessions": 2, "created_at": NOW}


def experiment():
    return {"id": "EXP-2026-11-05-a", "date": "2026-11-05", "title": "Baseline mạng đồ thị trên bộ 3.200 mẫu", "status": "done", "aim": "", "setup": "",
            "result": "MAE 0,061 eV/nguyên tử, seed 3", "user_note": "gần số của paper dù dữ liệu ít hơn nhiều", "next": "", "commit": None, "seed": "3",
            "missing": ["commit"], "photo_path": None, "raw_text": "chạy xong baseline, MAE 0.061, seed 3", "structured": True,
            "created_at": NOW, "updated_at": NOW}


def test_profile_and_keys():
    p = rt(ResearchProfile, profile())
    assert p.s2_connected and not p.asta_connected
    assert "s2_key" not in ResearchProfile.model_fields and "asta_key" not in ResearchProfile.model_fields
    rt(SourceKeysStatus, {"asta_connected": False, "s2_connected": True})
    with pytest.raises(ValidationError):
        ResearchProfile.model_validate({**profile(), "s2_key": "secret"})  # keys never travel
    with pytest.raises(ValidationError):
        ResearchProfile.model_validate({**profile(), "keywords": ["k"] * 9})


def test_search_and_cards():
    rt(SearchResponse, {"query": "graph neural network formation energy small data", "page": 1, "page_size": 10, "has_more": False,
                        "sources": [{"source": "asta", "status": "not_connected"}, {"source": "s2", "status": "ok"}, {"source": "arxiv", "status": "ok"}],
                        "results": [pham(), card()]})
    c = rt(PaperCard, card(key="doi:10.1021/acs.chemmater.5c00412", source="s2", arxiv_id=None, doi="10.1021/acs.chemmater.5c00412", has_pdf=False,
                           citation_count=58, tldr="Contrastive pretraining on unlabelled structures."))
    assert c.arxiv_id is None and not c.has_pdf


def test_related():
    rt(RelatedPapers, {"available": False, "reason": "no_source_key", "sources": [], "partial": False,
                       "citing": {"count": 0, "items": []}, "cited": {"count": 0, "items": []}})
    rt(RelatedPapers, {"available": True, "reason": None, "sources": ["s2"], "partial": False,
                       "citing": {"count": 14, "items": [card()]}, "cited": {"count": 38, "items": []}})


def test_reading_list_and_add():
    rt(ReadingEntry, entry())
    rt(ReadingList, {"limit": 5, "active_count": 1, "items": [entry()]})
    assert AddPaperRequest(link="10.1021/acs.chemmater.5c00412").card is None
    for bad in ({}, {"link": "x", "upload_path": "inbox/a.pdf"}):
        with pytest.raises(ValidationError):
            AddPaperRequest.model_validate(bad)
    rt(Suggestion, {"id": "sg-1", "week_of": "2026-11-02", "paper": card(), "reason": "So sánh các phương pháp trên vài nghìn mẫu, giống thiết lập của bạn.",
                    "query": "formation energy small data", "featured": True, "status": "pending", "created_at": NOW})


def test_reader():
    fb = {"rows": [{"kind": "right", "text": "Một mạng truyền thông điệp bất biến theo phép quay để dự đoán năng lượng hình thành."},
                   {"kind": "inaccurate", "text": "Bạn viết hơn 18%. Bài đạt 18% trên toàn bộ dữ liệu, còn với 3.000 cấu trúc chỉ là 7%."},
                   {"kind": "missing", "text": "Mô hình giả định cấu trúc đã được tối ưu (mục 2.1)."}],
          "for_thesis": "họ dùng 90.000 mẫu, bạn có 3.200.", "created_at": NOW}
    rt(PaperFeedback, fb)
    note = {"my_summary": "Bài đề xuất một mạng truyền thông điệp để dự đoán năng lượng hình thành.", "summary_updated_at": NOW, "feedback": fb}
    rt(PaperNote, note)
    rt(PaperDetail, {"entry": entry(), "abstract": "We propose an E(3)-equivariant message passing network.", "pdf_url": "https://arxiv.org/pdf/2601.08832",
                     "fulltext": "ready", "thesis_tag": "Mục 3 của bạn", "note": note, "qa_count": 3})
    with pytest.raises(ValidationError):
        SummaryInput(text="quá ngắn")
    assert FeedbackRow(kind="missing", text="x").kind == "missing"


def test_qa_found_and_not_found():
    rt(PaperQA, {"id": "qa-1", "question": "Bài này huấn luyện trên bộ dữ liệu nào?", "answer": "Huấn luyện trên 90.211 cấu trúc, chia 80/10/10 theo công thức hóa học.",
                 "found": True, "not_found_reason": None,
                 "citations": [{"section": "Mục 4.1, Dữ liệu", "snippet": "We split by composition.", "url": None}],
                 "course_hint": {"course_id": "xs-bayes", "lesson_id": None, "title": "Xác suất thống kê: Suy luận Bayes", "deep_link": "/khoa-hoc/xs-bayes"},
                 "created_at": NOW})
    q = rt(PaperQA, {"id": "qa-2", "question": "Họ có báo độ lệch chuẩn qua nhiều seed không?", "answer": "Mình không tìm thấy đoạn nào nói về điều này trong paper.",
                     "found": False, "not_found_reason": "no_passage", "citations": [], "course_hint": None, "created_at": NOW})
    assert not q.found and QaCitation(section="s", snippet="x", url=None)


def test_review_job_and_discovery():
    res = {"query": "graph neural network formation energy small data", "papers": [card()],
           "matrix": [{"key": "arxiv:2603.01234", "problem": "Dự đoán năng lượng hình thành khi chỉ có dưới 5.000 cấu trúc",
                       "method": "Mạng tương đẳng, có tăng cường dữ liệu huấn luyện", "data": "Dưới 5.000 cấu trúc", "result": None}],
           "followups": ["equivariant graph network small dataset", "contrastive pretraining crystal structures"],
           "searches": [{"query": "graph neural network formation energy small data", "count": 8}], "coverage": "arXiv only"}
    r = rt(ReviewResult, res)
    assert "abstract" in r.caveat_en.lower() and r.matrix[0].result is None
    with pytest.raises(ValidationError):
        ReviewResult.model_validate({**res, "followups": ["a", "b", "c", "d"]})
    job = rt(ResearchJob, {"id": "j1", "kind": "review", "status": "done", "progress": None, "result": res, "error": None,
                           "created_at": NOW, "finished_at": NOW})
    assert isinstance(job.result, ReviewResult)
    run = rt(ResearchJob, {"id": "j2", "kind": "review", "status": "running", "progress": {"stage": "reading", "total": 8, "done": 3},
                           "result": None, "error": None, "created_at": NOW, "finished_at": None})
    assert run.progress.done == 3
    d = rt(ResearchJob, {"id": "j3", "kind": "discovery", "status": "done", "progress": None,
                         "result": {"status": "papers_found", "queries": ["a", "b"], "new_suggestions": 4}, "error": None, "created_at": NOW, "finished_at": NOW})
    assert d.result.new_suggestions == 4
    assert ReviewRow(key="k").problem is None


def test_milestones_and_deadline_input():
    m = rt(Milestone, milestone())
    assert m.due_time == "18:59"
    assert MilestoneInput(text="nộp full paper 16/11, 23:59 AoE").title is None
    assert MilestoneInput(title="Báo cáo tiến độ cho khoa", due_date="2026-12-01").due_time is None
    for bad in ({}, {"text": "x", "title": "y", "due_date": "2026-12-01"}, {"title": "y"}, {"title": "y", "due_date": "01/12/2026"}):
        with pytest.raises(ValidationError):
            MilestoneInput.model_validate(bad)
    with pytest.raises(ValidationError):
        Milestone.model_validate({**milestone(), "due_time": "25:00"})


def test_meeting():
    agenda = {"promised": [{"text": "Chạy lại baseline trên bộ dữ liệu B", "done": True}, {"text": "Viết xong mục 3.2 (mới được nửa)", "done": False}],
              "new_results": "", "open_questions": "", "drafted_at": NOW, "edited_at": None}
    rt(Agenda, agenda)
    m = rt(Meeting, {"id": "mt-1", "at": "2026-11-11T14:00:00+07:00", "title": "Họp GVHD", "status": "scheduled", "agenda": agenda, "notes_md": None,
                     "action_items": [{"id": "ai-1", "text": "Thử learning rate 1e-3", "due_date": "2026-11-14", "done": False, "in_plan": True}],
                     "created_at": NOW})
    assert m.action_items[0].in_plan and AgendaItem(text="x", done=False) and ActionItem(id="a", text="t").due_date is None
    assert MeetingInput(text="họp GVHD thứ Tư 11/11 14:00").at is None
    with pytest.raises(ValidationError):
        MeetingInput.model_validate({"text": "x", "at": "2026-11-11T14:00:00+07:00"})
    with pytest.raises(ValidationError):
        MeetingInput.model_validate({"at": "2026-11-11 14:00"})


def test_experiment():
    e = rt(Experiment, experiment())
    assert e.missing == ["commit"] and e.id.startswith("EXP-2026-11-05-")
    rt(Experiment, {**experiment(), "id": "EXP-2026-11-03-a", "date": "2026-11-03", "status": "failed", "missing": []})
    assert ExperimentInput(text="chạy xong baseline, MAE 0.061, seed 3").photo_path is None


def test_overview_and_events():
    ov = {"profile": profile(), "status_line": {"line_vi": "Hạn nộp bài còn 9 ngày, 2 paper mới", "line_en": "Paper due in 9 days, 2 new papers"},
          "hero": {"paper_id": "pp-1", "title": pham()["title"], "authors_line": "Pham, Okafor, Lindqvist · 2026", "status": "reading", "minutes_spent": 25,
                   "reason": "Bài full paper của bạn còn 9 ngày nữa đến hạn, và mục 3 của bài so sánh với paper này.", "deep_link": "/nghien-cuu/paper/pp-1"},
          "upcoming": [{"kind": "meeting", "id": "mt-1", "title": "Họp GVHD", "date": "2026-11-11", "time": "14:00", "days_left": 4, "confirmed": True,
                        "agenda_ready": True, "original_text": None, "planned_sessions": 0},
                       {"kind": "deadline", "id": "ms-1", "title": "Nộp full paper hội nghị", "date": "2026-11-16", "time": "18:59", "days_left": 9,
                        "confirmed": True, "agenda_ready": None, "original_text": "23:59 AoE 15/11", "planned_sessions": 2},
                       {"kind": "deadline", "id": "ms-2", "title": "Báo cáo tiến độ cho khoa", "date": "2026-12-01", "time": None, "days_left": 24,
                        "confirmed": False, "agenda_ready": None, "original_text": None, "planned_sessions": 0}],
          "reading_list": {"limit": 5, "active_count": 1, "items": [entry()]}, "suggestions": [], "milestones": [milestone()], "goal_id": "res-thesis",
          "experiments": [experiment()], "discovery": {"state": "idle", "last_run_at": NOW, "last_status": "papers_found", "next_run_at": "2026-11-09T06:00:00+07:00"}}
    o = rt(ResearchOverview, ov)
    assert o.upcoming[2].confirmed is False and o.hero.minutes_spent == 25
    rt(LiveLine, ov["status_line"])
    rt(DiscoveryStatus, ov["discovery"])
    assert ReadNext.model_fields["reason"].is_required() and UpcomingItem.model_fields["days_left"].is_required()
    assert RESEARCH_EVENT_KINDS == ("paper_opened", "paper_read", "summary_written", "experiment_logged")
