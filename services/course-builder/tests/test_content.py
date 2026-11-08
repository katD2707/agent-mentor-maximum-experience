"""Offline tests of the content stage (outline, quiz, lessons, humanize, verify, assemble). ModelClient and DeepTutor are fakes."""

import json
from pathlib import Path

import pytest
from mentor_course_builder import humanize, verify
from mentor_course_builder.assemble import assemble, write_to_dir, write_to_store
from mentor_course_builder.contracts import MediaFile, MediaResult
from mentor_course_builder.deeptutor import DeepTutorError, RawQuestion, parse_mastery_events, parse_quiz_events
from mentor_course_builder.intake import IntakeResult
from mentor_course_builder.lessons import blocks_from_json, write_lesson
from mentor_course_builder.models import Material, Page
from mentor_course_builder.outline import (OutlineEditError, age_band_from_note, apply_outline_edits, build_outline,
                                           detect_language, outline_from_json, outline_to_json, revise_outline)
from mentor_course_builder.pipeline import build_course
from mentor_course_builder.quiz import (LessonContext, PENDING_SHA, make_quiz, map_raw_choice, plan_types,
                                        quiz_from_dict, split_explanation)
from mentor_schemas.course import CoursePack, QuizBlock, QuizItem


class FakeClient:
    """Routes by a keyword in the system prompt to a canned reply (str or callable(system, user))."""

    def __init__(self, routes: dict[str, object]):
        self.routes, self.calls = routes, []

    def complete(self, alias, messages, *, max_tokens=8000, temperature=0.0):
        system, user = messages[0]["content"], messages[-1]["content"]
        self.calls.append((system[:40], user[:60]))
        for key, r in self.routes.items():
            if key in system:
                out = r(system, user) if callable(r) else r
                return out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)
        raise AssertionError(f"no route for system prompt: {system[:80]}")


OUTLINE_JSON = {
    "title": "Vật lí 11: Điện trường", "subject": "Vật lí", "language": "en", "age_band": "g1_5",
    "description_short": "Khóa học về điện trường. Dành cho lớp 11.", "outcomes": ["Vẽ được đường sức"],
    "chapters": [{"title": "Điện trường", "lessons": [
        {"title": "Cường độ điện trường", "est_minutes": 8, "summary": "s", "key_ideas": ["E"],
         "source_pages": ["a.pdf#1"], "grounded": True},
        {"title": "Đường sức điện", "est_minutes": 9, "summary": "s", "key_ideas": ["đường sức"],
         "source_pages": ["a.pdf#2", "nope#9"], "grounded": True},
        {"title": "Tụ điện", "est_minutes": 10, "summary": "s", "key_ideas": [], "source_pages": [], "grounded": True},
    ]}, {"title": "Dòng điện", "lessons": [{"title": "Dòng điện không đổi", "est_minutes": 7}]}],
}


def _outline(**kw):
    return outline_from_json(OUTLINE_JSON, valid_pages={"a.pdf#1", "a.pdf#2"}, detect_from="Điện trường là gì? Đường sức điện.",
                             **kw)


# ---------------------------------------------------------------- outline
def test_outline_from_json_grounding_language_and_age():
    o = _outline(teacher_note="Cho lớp 11A2, các em học trung bình")
    assert o.language == "vi"  # code beats the model's "en"
    assert o.age_band == "g10_12"  # teacher's note beats the model's g1_5
    ls = {x.title: x for x in o.lessons()}
    assert ls["Cường độ điện trường"].grounded and ls["Đường sức điện"].source_pages == ["a.pdf#2"]
    assert not ls["Tụ điện"].grounded  # no page refs -> inferred
    assert len({x.id for x in o.lessons()} | {c.id for c in o.chapters}) == 6
    assert age_band_from_note("sinh viên năm 2") == "uni" and age_band_from_note("lớp 3") == "g1_5"
    assert age_band_from_note("lớp 8") == "g6_9" and age_band_from_note("hello") is None
    assert detect_language("The quick brown fox") == "en"


def test_rename_course_title():
    o = _outline()
    o2 = apply_outline_edits(o, [{"op": "rename", "id": o.course_id, "title": "Tên khóa mới"}])
    assert o2.title == "Tên khóa mới" and o2.course_id == o.course_id and o.title != o2.title


def test_edit_ops_keep_ids_and_validate():
    o = _outline()
    ids = [x.id for x in o.lessons()]
    a, b, c, d = ids
    o2 = apply_outline_edits(o, [
        {"op": "rename", "id": b, "title": "Đường sức"},
        {"op": "reorder", "ids": [c, a], "parent": o.chapters[0].id},
        {"op": "add_lesson", "chapter": o.chapters[0].id, "title": "Điện thế", "after": a},
        {"op": "add_chapter", "title": "Từ trường", "index": 0},
        {"op": "move_lesson", "id": d, "chapter": o.chapters[1].id, "index": 0},
    ])
    assert o.lessons()[1].title == "Đường sức điện"  # original untouched
    ch = {x.title: x for x in o2.chapters}
    assert [x.id for x in ch["Điện trường"].lessons][:2] == [c, a]
    assert ch["Điện trường"].lessons[2].title == "Điện thế" and not ch["Điện trường"].lessons[2].grounded
    assert o2.chapters[0].title == "Từ trường" and not o2.chapters[0].lessons
    assert b in [x.id for x in o2.lessons()] and next(x for x in o2.lessons() if x.id == b).title == "Đường sức"
    o3 = apply_outline_edits(o, [{"op": "delete", "id": d}])  # last lesson of its chapter -> chapter goes too
    assert len(o3.chapters) == 1
    o4 = apply_outline_edits(o, [{"op": "delete", "id": o.chapters[1].id}, {"op": "update", "id": a, "est_minutes": 20}])
    assert len(o4.chapters) == 1 and o4.lessons()[0].est_minutes == 20
    with pytest.raises(OutlineEditError):
        apply_outline_edits(o, [{"op": "delete", "id": "nope"}])
    with pytest.raises(OutlineEditError):
        apply_outline_edits(o, [{"op": "bogus"}])


def test_merge_and_free_text_revision():
    o = _outline()
    a, b, c, _ = [x.id for x in o.lessons()]
    m = apply_outline_edits(o, [{"op": "merge", "ids": [b, c], "title": "Đường sức và tụ"}])
    merged = next(x for x in m.lessons() if x.id == b)
    assert merged.title == "Đường sức và tụ" and merged.est_minutes == 19 and not merged.grounded
    assert c not in [x.id for x in m.lessons()]
    client = FakeClient({"edit a course outline": {"ops": [{"op": "merge", "ids": [a, b]}], "note": "Đã gộp bài 1 và 2."}})
    new, note = revise_outline(o, "gộp bài 1 và 2", client)
    assert note.startswith("Đã gộp") and len(new.lessons()) == 3
    assert "Lesson 2 [" in o.listing()


def test_build_outline_from_intake():
    intake = IntakeResult(materials=[Material("a.pdf", "pdf", [Page("a.pdf", 1, "pdf_text", text="Điện trường là gì"),
                                                                Page("a.pdf", 2, "pdf_text", text="Đường sức điện")])])
    client = FakeClient({"design a course outline": OUTLINE_JSON})
    o = build_outline(intake, client, teacher_note="lớp 11")
    assert o.age_band == "g10_12" and o.language == "vi" and o.course_id == "vat-li-11-dien-truong"


# ---------------------------------------------------------------- quiz mapping
def _ctx(band="g10_12", grounded=True):
    return LessonContext("l1", "Đường sức", "s", ["a"], "Đường sức đi ra từ điện tích dương.", "c1", band, "vi", grounded)


def test_split_explanation_and_raw_mapping():
    raw = RawQuestion("Phát biểu nào **đúng**?", {"A": "A. Đúng", "B": "Sai 1", "C": "Sai 2", "D": "Sai 3"}, "A",
                      "Theo định nghĩa, A đúng [kb]. Đây là ý hai. Ý ba.\n\nBa phát biểu còn lại đều sai:\n"
                      "- **B sai:** hai đường sức không cắt nhau [kb]. Thêm.\n- **C sai:** chúng không khép kín.\n", "medium")
    expl, fb = split_explanation(raw.explanation, "A", raw.options)
    assert expl == "Theo định nghĩa, A đúng. Đây là ý hai." and fb["B"] == "hai đường sức không cắt nhau." and "A" not in fb
    item = map_raw_choice(raw, "l1-q1")
    assert item.type == "SINGLE_CHOICE" and item.options[0].text == "Đúng" and item.answer_key == {"correct_option_id": "A"}
    assert item.stem == "Phát biểu nào đúng?" and item.difficulty == 2 and set(item.option_feedback) == {"B", "C"}


def test_quiz_from_dict_every_type():
    mc, media = quiz_from_dict({"type": "SINGLE_CHOICE", "stem": "2+2?", "explanation": "Bốn. Thật vậy. Thừa.",
                                "options": [{"text": "3", "feedback": "Ít quá."}, {"text": "4"}], "correct": "B"},
                               "l1-q1", "c1", "g1_5", "vi")
    assert mc.answer_key == {"correct_option_id": "B"} and mc.option_feedback == {"A": "Ít quá."}
    assert mc.explanation == "Bốn. Thật vậy." and mc.stem_audio and mc.options[0].audio
    assert {m.id for m in media} == {"l1-q1.stem", "l1-q1.opt-A", "l1-q1.opt-B"} and all(m.kind == "tts" for m in media)
    tf, _ = quiz_from_dict({"type": "TRUE_FALSE_GROUP", "stem": "Đúng/sai", "explanation": "x",
                            "statements": [{"text": "a", "answer": True}, {"text": "b", "answer": False}]},
                           "l1-q2", "c1", "g10_12", "vi")
    assert tf.answer_key == {"statements": {"a": True, "b": False}} and [s.id for s in tf.statements] == ["a", "b"]
    sa, _ = quiz_from_dict({"type": "SHORT_ANSWER", "stem": "E?", "explanation": "x", "accepted": ["4e4", "40000"],
                            "tolerance": 0.01}, "l1-q3", "c1", "uni", "vi")
    assert sa.answer_key == {"accepted": ["4e4", "40000"], "tolerance": 0.01}
    pc, media = quiz_from_dict({"type": "PICTURE_CHOICE", "stem": "Quả táo?", "explanation": "x",
                                "options": [{"picture": "a red apple"}, {"picture": "a blue car"}], "correct": "A"},
                               "l1-q4", "c1", "g1_5", "vi")
    assert pc.options[0].image.sha256 == PENDING_SHA
    assert {m.kind for m in media if m.id.endswith("pic-A")} == {"picture"}
    tap, media = quiz_from_dict({"type": "TAP_COUNT", "stem": "Đếm", "explanation": "x", "picture": "a red apple",
                                 "total": 7, "count": 5}, "l1-q5", "c1", "g1_5", "vi")
    assert tap.tap.total == 7 and tap.answer_key == {"count": 5}
    assert next(m for m in media if m.id == "l1-q5.tap").spec == {"description": "a red apple", "count": 1}
    for bad in ({"type": "SINGLE_CHOICE", "stem": "q", "options": ["a", "b"], "correct": "Z"},
                {"type": "TAP_COUNT", "stem": "q", "picture": "x", "total": 3, "count": 9},
                {"type": "SHORT_ANSWER", "stem": "q", "accepted": []}, {"type": "NOPE", "stem": "q"}):
        with pytest.raises(ValueError):
            quiz_from_dict(bad, "l1-q9", "c1", "g10_12", "vi")


class FakeDT:
    def __init__(self, raws=None, fail=False):
        self.raws, self.fail, self.asked = raws or [], fail, []

    def available(self):
        return True

    def quiz(self, topic, kb, n=3, language="vi"):
        self.asked.append(n)
        if self.fail:
            raise DeepTutorError("down")
        return self.raws[:n]


RAW = RawQuestion("Q?", {"A": "x", "B": "y", "C": "z"}, "B", "Vì y. Hết.", "easy")
OWN = {"items": [{"type": "TRUE_FALSE_GROUP", "stem": "Đúng sai", "explanation": "e",
                  "statements": [{"text": "a", "answer": True}, {"text": "b", "answer": False}]},
                 {"type": "SHORT_ANSWER", "stem": "E?", "explanation": "e", "accepted": ["4e4"]},
                 {"type": "SINGLE_CHOICE", "stem": "S?", "explanation": "e", "options": ["p", "q"], "correct": "A"}]}


def test_make_quiz_deeptutor_then_own_and_fallback():
    assert plan_types("g10_12", 4, have=3) == ["TRUE_FALSE_GROUP", "SHORT_ANSWER"]
    client = FakeClient({"write quiz items": {"items": OWN["items"][:2]}})
    dt = FakeDT([RAW, RAW, RAW])
    r = make_quiz(_ctx(), client, dt=dt, kb="kb1")
    assert dt.asked == [2] and [i.type for i in r.items] == ["SINGLE_CHOICE", "SINGLE_CHOICE", "TRUE_FALSE_GROUP",
                                                              "SHORT_ANSWER"]
    assert [i.id for i in r.items] == ["l1-q1", "l1-q2", "l1-q3", "l1-q4"] and "deeptutor: 2 choice items" in r.notes
    # sidecar down -> everything from our prompt
    client2 = FakeClient({"write quiz items": OWN})
    r2 = make_quiz(_ctx(), client2, dt=FakeDT(fail=True), kb="kb1", n=3)
    assert len(r2.items) == 3 and any("deeptutor unavailable" in n for n in r2.notes)
    # ungrounded lesson never calls DeepTutor
    dt3 = FakeDT([RAW])
    make_quiz(_ctx(grounded=False), client2, dt=dt3, kb="kb1", n=3)
    assert dt3.asked == []


def test_deeptutor_event_parsing():
    ev = [{"type": "content", "content": "..."}, {"type": "result", "metadata": {"summary": {"results": [
        {"qa_pair": {"question": "Q", "options": {"A": "1", "B": "2"}, "correct_answer": "b", "explanation": "e",
                     "difficulty": "hard"}},
        {"qa_pair": {"question": "", "options": {}}}]}}}, {"type": "done"}]
    qs = parse_quiz_events(ev)
    assert len(qs) == 1 and qs[0].correct == "B"
    with pytest.raises(DeepTutorError):
        parse_quiz_events([{"type": "done"}])
    args = {"path_name": "p", "modules": [{"name": "m", "knowledge_points": []}]}
    assert parse_mastery_events([{"type": "tool_call", "content": "mastery_build", "metadata": {"args": args}}]) == args


# ---------------------------------------------------------------- humanize
def test_linter_vietnamese_and_english_tells():
    vi = ("Hãy cùng khám phá điện trường! Không chỉ quan trọng mà còn thú vị. Điều quan trọng là đường sức. "
          "Điện thế đóng vai trò quan trọng. Tóm lại, vậy đó 🚀 !!!")
    rules = {h.rule for h in humanize.lint(vi)}
    assert {"vi.lets_explore", "vi.not_only_but_also", "vi.important_is", "vi.plays_role", "vi.in_summary", "emoji",
            "multi_exclaim"} <= rules
    en = "In today's fast-paced world, let's dive in. It's important to note that it plays a crucial role — a journey."
    assert {"en.today_world", "en.lets_dive", "en.important_to_note", "en.plays_role", "em_dash"} <= \
        {h.rule for h in humanize.lint(en)}
    clean = "Đường sức đi ra từ điện tích dương. Chỗ điện trường mạnh, đường sức dày: $E = k\\frac{q}{r^2}$."
    assert humanize.lint(clean) == []
    assert humanize.lint("Công thức $a — b!!$ là đúng.") == []  # math masked
    assert humanize.lint_count([vi, en])["emoji"] == 1


def test_preserved_ok_and_rewrite_guard():
    old = "Thầy Minh dặn: tính $E = 9\\cdot 10^9$ với q = 4 nC ở 3 cm."
    assert humanize.preserved_ok(old, "Thầy Minh dặn tính $E = 9\\cdot 10^9$ khi q = 4 nC, cách 3 cm.")
    assert not humanize.preserved_ok(old, "Thầy Minh dặn tính $E = 9\\cdot 10^8$ khi q = 4 nC, cách 3 cm.")
    assert not humanize.preserved_ok(old, "Thầy Minh dặn tính $E = 9\\cdot 10^9$ khi q = 5 nC, cách 3 cm.")
    assert not humanize.preserved_ok(old, "Thầy dặn tính $E = 9\\cdot 10^9$ khi q = 4 nC, cách 3 cm.")
    texts = {"t1": "Hãy cùng khám phá đường sức. Đường sức đi ra từ điện tích dương.", "t2": "Cho q = 4 C.",
             "t3": "Hãy cùng tìm hiểu bài này."}
    client = FakeClient({"editing your own lesson": {"t1": "Đường sức đi ra từ điện tích dương.", "t2": "Cho q = 5 C.",
                                                     "t3": "Hãy cùng khám phá, tóm lại, bài này!!!"}})
    new, rej = humanize.humanize_texts(texts, client, language="vi", age_band_label="x")
    assert new["t1"] == "Đường sức đi ra từ điện tích dương." and not humanize.lint(new["t1"])
    assert new["t2"] == texts["t2"] and "t2" in rej  # number changed -> rejected
    assert new["t3"] == texts["t3"] and "t3" in rej  # more tells than before


# ---------------------------------------------------------------- verify
def test_katex_numbers_and_lengths():
    assert verify.katex_problems("ok $x^{2}$ and $$\\frac{a}{b}$$ and 5\\$") == []
    assert verify.katex_problems("bad $x^{2") and verify.katex_problems("$$a$") and verify.katex_problems("x $\\frac{a}{b$")
    assert verify.katex_problems("use \\(x\\)")
    p = verify.parse_number
    assert p("4e4") == p("40000") == p("4.10^4") == p("4\\cdot 10^{4}") == p("$4 \\cdot 10^4$ V/m") == 40000
    assert p("0,5") == 0.5 and p("1/2") == 0.5 and p("abc") is None
    from mentor_schemas.course import Lesson, TextBlock
    les = Lesson(id="l", title="t", est_minutes=3, blocks=[TextBlock(id="l-b1", md="Một hai ba bốn năm sáu bảy tám chín mười mười một.")])
    assert verify.length_problems(les, "g1_5") == []  # 12 words: within the soft margin
    long = Lesson(id="l", title="t", est_minutes=3, blocks=[TextBlock(id="l-b1", md="x " * 100)])
    assert verify.length_problems(long, "g1_5")


def _mc(key="B", iid="l1-q1"):
    return QuizItem(id=iid, type="SINGLE_CHOICE", stem="2+2?", options=[{"id": "A", "text": "3"}, {"id": "B", "text": "4"}],
                    answer_key={"correct_option_id": key}, explanation="e")


def test_check_item_independent_solve():
    ok = FakeClient({"Solve this quiz": {"answer": "B"}})
    assert verify.check_item(_mc("B"), ok, "vi").ok
    assert not verify.check_item(_mc("A"), ok, "vi").ok
    tf = QuizItem(id="l1-q2", type="TRUE_FALSE_GROUP", stem="s", statements=[{"id": "a", "text": "x"}, {"id": "b", "text": "y"}],
                  answer_key={"statements": {"a": True, "b": False}}, explanation="e")
    assert verify.check_item(tf, FakeClient({"Solve this quiz": {"answers": {"a": True, "b": False}}}), "vi").ok
    assert not verify.check_item(tf, FakeClient({"Solve this quiz": {"answers": {"a": True, "b": True}}}), "vi").ok
    sa = QuizItem(id="l1-q3", type="SHORT_ANSWER", stem="E?", answer_key={"accepted": ["4e4", "40000"]}, explanation="e")
    assert verify.check_item(sa, FakeClient({"Solve this quiz": {"answer": "4\\cdot 10^4 V/m"}}), "vi").ok
    assert not verify.check_item(sa, FakeClient({"Solve this quiz": {"answer": "10^5"}}), "vi").ok
    bad = QuizItem(id="l1-q4", type="SHORT_ANSWER", stem="E?", answer_key={"accepted": ["4e4", "50000"]}, explanation="e")
    v = verify.check_item(bad, FakeClient({}), "vi")  # accepted spellings disagree: no model call needed
    assert not v.ok and "differ" in v.reason


def _draft(band="g10_12"):
    client = FakeClient({"write one lesson": {"blocks": [
        {"kind": "video", "title": "Đường sức", "target_s": 120, "scenes": [
            {"caption": "c", "narration": "Đường sức đi ra từ cực dương.", "visual": "v"}] * 3},
        {"kind": "text", "md": "Đường sức đi ra từ điện tích dương."},
        {"kind": "callout", "variant": "remember", "title": "Nhớ", "md": "- Không cắt nhau"},
        {"kind": "diagram", "description": "field lines", "labels": ["+"], "math": "E=kq/r^2", "alt": "a", "caption": "h"},
        {"kind": "weird"}]},
        "write quiz items": {"items": [OWN["items"][1], OWN["items"][2]]},
        "Solve this quiz": lambda s, u: {"answer": "A" if "S?" in u else "4e4"}})
    o = outline_from_json({**OUTLINE_JSON, "language": "vi"}, valid_pages={"a.pdf#1", "a.pdf#2"}, teacher_note="lớp 11")
    ol = o.lessons()[1]
    pages = {"a.pdf#2": "Đường sức điện là đường vẽ trong điện trường."}
    return o, ol, pages, client


def test_write_lesson_blocks_and_media_contract():
    o, ol, pages, client = _draft()
    d = write_lesson(o, ol, client, pages, dt=FakeDT([RAW]), kb="kb", quiz_items=3)
    kinds = [type(b).__name__ for b in d.lesson.blocks]
    assert kinds == ["VideoBlock", "TextBlock", "CalloutBlock", "ImageBlock", "QuizBlock"]
    assert [b.id for b in d.lesson.blocks][:3] == [f"{ol.id}-b{i}" for i in (1, 2, 3)]
    by = {m.id: m for m in d.media}
    v = by[f"{ol.id}-b1"]
    assert v.kind == "video" and len(v.spec["scenes"]) == 3 and set(v.spec["scenes"][0]) == {"caption", "narration", "visual"}
    assert by[f"{ol.id}-b4"].kind == "diagram" and by[f"{ol.id}-b4"].spec["math"] == "E=kq/r^2"
    assert not any(m.kind == "tts" for m in d.media)  # g10_12: no read-aloud
    q = d.lesson.blocks[-1]
    assert isinstance(q, QuizBlock) and len(q.items) == 3 and q.items[0].id == f"{ol.id}-q1"
    assert d.grounded and "deeptutor: 1 choice items" in d.notes


def test_g1_5_has_tts_for_every_text_callout_and_option():
    data = {"blocks": [{"kind": "text", "md": "Một quả táo."}, {"kind": "callout", "variant": "remember", "md": "Nhớ: 1."},
                       {"kind": "illustration", "description": "an apple", "alt": "quả táo", "caption": "Táo"}]}
    blocks, media, _ = blocks_from_json(data, course_id="c", lesson_id="l", age_band="g1_5", language="vi")
    tts = {m.id for m in media if m.kind == "tts"}
    assert tts == {"l-b1", "l-b2", "l-b3.audio"} and blocks[0].audio and blocks[1].audio and blocks[2].audio


def test_verify_drops_and_regenerates():
    o, ol, pages, client = _draft()
    d = write_lesson(o, ol, client, pages, dt=None, kb=None, quiz_items=3)
    first = next(b for b in d.lesson.blocks if isinstance(b, QuizBlock)).items
    ids = [q.id for q in first]
    # solver contradicts the key of the first item and agrees with everything after; regeneration returns the same item
    solver = FakeClient({"Solve this quiz": {"answer": "Z"}, "write quiz items": {"items": [OWN["items"][2]]}})
    from mentor_course_builder.verify import verify_and_repair

    ctx = LessonContext(ol.id, ol.title, "s", [], "Đường sức.", o.course_id, "g10_12", "vi", True)
    rep = verify_and_repair(d, ctx, solver)
    assert rep.checked == len(ids) and rep.failed
    assert set(rep.dropped) | set(rep.regenerated) == set(ids)  # solver says "Z" for all: nothing is silently kept
    left = [b for b in d.lesson.blocks if isinstance(b, QuizBlock)]
    assert not left or all(q.id in ids for q in left[0].items)


# ---------------------------------------------------------------- assemble
def test_assemble_without_media_skips_and_is_valid(tmp_path):
    o, ol, pages, client = _draft()
    d = write_lesson(o, ol, client, pages, dt=None, kb=None, quiz_items=2)
    a = assemble(o, [d])
    CoursePack.model_validate(a.pack.model_dump())
    assert [type(b).__name__ for b in a.pack.chapters[0].lessons[0].blocks] == ["TextBlock", "CalloutBlock", "QuizBlock"]
    assert any("video block skipped" in n for n in a.notes) and any("image block skipped" in n for n in a.notes)
    assert a.meta.lessons_count == 1 and not a.assets and a.meta.id == o.course_id
    write_to_dir(a, tmp_path / "out")
    assert (tmp_path / "out" / "pack.json").is_file()


def test_assemble_sets_min_app_version_from_what_the_pack_uses(monkeypatch):
    from mentor_schemas import course

    o, ol, pages, client = _draft()
    d = write_lesson(o, ol, client, pages, dt=None, kb=None, quiz_items=2)
    assert assemble(o, [d]).pack.min_app_version == "0.1.0"
    qtype = d.lesson.blocks[-1].items[0].type
    monkeypatch.setitem(course.APP_VERSION_FOR, qtype, "0.10.0")
    monkeypatch.setitem(course.APP_VERSION_FOR, "callout", "0.2.3")
    assert assemble(o, [d]).pack.min_app_version == "0.10.0"  # numeric, not string, comparison


def test_assemble_with_media_and_store(tmp_path):
    o, ol, pages, client = _draft()
    d = write_lesson(o, ol, client, pages, dt=None, kb=None, quiz_items=2)
    mp4, png = tmp_path / "v.mp4", tmp_path / "d.png"
    mp4.write_bytes(b"video"), png.write_bytes(b"png")
    res = {f"{ol.id}-b1": MediaResult(id=f"{ol.id}-b1", kind="video", duration_s=61.5, files=[
               MediaFile(role="main", path="video/b1.mp4", mime="video/mp4", file=mp4)]),
           f"{ol.id}-b4": MediaResult(id=f"{ol.id}-b4", kind="diagram", files=[
               MediaFile(role="main", path="img/b4.png", mime="image/png", file=png)])}
    a = assemble(o, [d], res)
    blocks = a.pack.chapters[0].lessons[0].blocks
    assert [type(b).__name__ for b in blocks] == ["VideoBlock", "TextBlock", "CalloutBlock", "ImageBlock", "QuizBlock"]
    assert blocks[0].duration_s == 61.5 and blocks[0].video.sha256 != PENDING_SHA and set(a.assets) == {"video/b1.mp4", "img/b4.png"}
    assert "video" in a.meta.media and "quiz" in a.meta.media
    pytest.importorskip("mentor_gateway.content.store")
    v = write_to_store(a, tmp_path / "courses", note="test")
    from mentor_gateway.content.store import ContentStore

    store = ContentStore(tmp_path / "courses")
    assert v == 1 and store.version_info(store.load_meta(o.course_id), 1).status == "review"
    assert store.load_pack(o.course_id, 1).title == o.title and store.asset_path(o.course_id, 1, "img/b4.png").is_file()
    assert store.version_info(store.load_meta(o.course_id), 1).level_suggested == o.level_suggested  # reaches the draft
    assert store.version_info(store.load_meta(o.course_id), 1).level_confirmed is None  # only the teacher confirms


def test_build_course_end_to_end_offline():
    o, ol, pages, client = _draft()
    client.routes["editing your own lesson"] = lambda s, u: json.loads(u)  # identity rewrite
    intake = IntakeResult(materials=[Material("a.pdf", "pdf", [Page("a.pdf", 1, "pdf_text", text="Điện trường"),
                                                                Page("a.pdf", 2, "pdf_text", text="Đường sức điện là đường vẽ.")])])
    res = build_course(intake, o, client, dt=None, only_lessons=[ol.id], quiz_items=2, workers=1)
    assert len(res.drafts) == 1 and res.reports[0].error is None and res.reports[0].verify
    assert res.assembled.pack.chapters[0].lessons[0].id == ol.id
    assert {m.kind for m in res.media_requests} == {"video", "diagram"}


def test_build_course_retries_a_lesson_once():
    import mentor_course_builder.pipeline as pl
    o, ol, pages, client = _draft()
    client.routes["editing your own lesson"] = lambda s, u: json.loads(u)
    intake = IntakeResult(materials=[Material("a.pdf", "pdf", [Page("a.pdf", 1, "pdf_text", text="Điện trường"),
                                                                Page("a.pdf", 2, "pdf_text", text="Đường sức điện là đường vẽ.")])])
    real, calls = pl.write_lesson, []

    def flaky(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise ValueError("could not parse model JSON")  # first attempt breaks, the second works
        return real(*a, **k)

    pl.write_lesson = flaky
    try:
        res = build_course(intake, o, client, dt=None, only_lessons=[ol.id], quiz_items=2, workers=1)
    finally:
        pl.write_lesson = real
    assert len(calls) == 2 and len(res.drafts) == 1 and res.reports[0].error is None


# ---------------------------------------------------------------- course level suggestion
def test_level_suggestion_uses_the_model_answer_inside_the_age_band():
    from mentor_course_builder.outline import suggest_level

    assert suggest_level("g10_12", "advanced") == "advanced" and suggest_level("g10_12", "basic") == "basic"
    assert suggest_level("g1_5", "advanced") == "basic"  # primary school is never advanced
    assert suggest_level("g6_9", "advanced") == "intermediate"
    assert suggest_level("uni", "basic") == "intermediate"  # university is never basic


def test_level_suggestion_falls_back_to_band_and_material():
    from mentor_course_builder.outline import suggest_level

    assert suggest_level("g1_5") == "basic" and suggest_level("g10_12") == "intermediate" and suggest_level("uni") == "intermediate"
    hard = "Chứng minh định lý. Tích phân và đạo hàm. " * 6
    assert suggest_level("uni", None, text=hard, n_lessons=6) == "advanced"
    assert suggest_level("g10_12", "nonsense", text=hard) == "advanced"
    assert suggest_level("g10_12", None, text="x", n_lessons=2) == "basic"


def test_outline_carries_the_level_suggestion():
    assert _outline().level_suggested == "basic"  # model said nothing, the band (g1_5 guess) decides
    o = outline_from_json({**OUTLINE_JSON, "level": "advanced"}, teacher_note="Cho lớp 11A2",
                          valid_pages={"a.pdf#1"}, detect_from="Điện trường là gì?")
    assert o.age_band == "g10_12" and o.level_suggested == "advanced"
    o = outline_from_json({**OUTLINE_JSON, "level": "advanced"}, teacher_note="lớp 3", valid_pages={"a.pdf#1"})
    assert o.level_suggested == "basic"
    assert json.loads(outline_to_json(o))["level_suggested"] == "basic"  # persisted in outline.json for the gateway
    intake = IntakeResult(materials=[Material("a.pdf", "pdf", [Page("a.pdf", 1, "pdf_text", text="Điện trường là gì")])])
    client = FakeClient({"design a course outline": {**OUTLINE_JSON, "level": "intermediate"}})
    assert build_outline(intake, client, teacher_note="lớp 11").level_suggested == "intermediate"
    assert len(client.calls) == 1  # the suggestion rides on the outline call; no extra model call
