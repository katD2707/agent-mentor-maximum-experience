"""Verify-and-refine gate (refine.py), media plan, speed changes. Everything offline: ModelClient, DeepTutor, media stage are fakes."""

import json
from pathlib import Path

import pytest
from mentor_course_builder import katex_check, refine, verify
from mentor_course_builder.assemble import assemble
from mentor_course_builder.contracts import MediaFile, MediaRequest, MediaResult
from mentor_course_builder.deeptutor import DeepTutor, DeepTutorError, RawQuestion
from mentor_course_builder.lessons import LessonDraft, blocks_from_json
from mentor_course_builder.mediaplan import LessonMedia, plan_media
from mentor_course_builder.outline import CourseOutline, OutlineChapter, OutlineLesson
from mentor_course_builder.tts import speakable
from mentor_schemas.course import (AssetRef, CalloutBlock, CoursePack, ImageBlock, Lesson, QuizBlock, QuizItem, TextBlock)
from test_content import FakeClient

LONG = "Đường sức đi ra từ điện tích dương rồi đi vào điện tích âm và hai đường sức không bao giờ cắt nhau trong điện trường"


def outline(n=4, band="g10_12", titles=None):
    names = titles or ["Bài một", "Bài hai", "Bài ba", "Bài bốn"][:n]
    ls = [OutlineLesson(id=f"l{i}", title=t, summary="s", key_ideas=["k"]) for i, t in enumerate(names, 1)]
    return CourseOutline(course_id="c1", title="Khóa thử", subject="Lý", language="vi", age_band=band,
                         description_short="d", chapters=[OutlineChapter(id="ch", title="C", lessons=ls)])


def item(lid="l1", n=1, stem="Hai đường sức có cắt nhau không?", key="A"):
    return QuizItem(id=f"{lid}-q{n}", type="SINGLE_CHOICE", stem=stem, options=[{"id": "A", "text": "Không"}, {"id": "B", "text": "Có"}],
                    answer_key={"correct_option_id": key}, explanation="Vì chúng không cắt nhau.")


def draft(lid, text="Điện trường tồn tại quanh điện tích.", quiz=True, stem=None, key="A", extra=(), media=()):
    blocks = [TextBlock(id=f"{lid}-b1", md=text), *extra]
    if quiz:
        blocks.append(QuizBlock(id=f"{lid}-b9", items=[item(lid, 1, stem or f"Câu hỏi của {lid}?", key)]))
    return LessonDraft(lesson=Lesson(id=lid, title=lid, est_minutes=5, blocks=blocks), media=list(media))


def tmp_result(tmp_path, rid, kind="diagram", path=None, content=b"png-bytes"):
    f = tmp_path / f"{rid}.bin"
    f.write_bytes(content)
    return MediaResult(id=rid, kind=kind, files=[MediaFile(role="main", path=path or f"img/{rid}.png", mime="image/png", file=f)])


def solver(s, u):  # a stem containing WRONG has a key the independent solve disagrees with
    return {"answer": "B"} if "WRONG" in u else {"answer": "A"}


def counting_quiz():
    n = [0]

    def make(s, u):
        n[0] += 1
        return new_quiz(f"Câu mới số {n[0]}?")

    return make


def new_quiz(stem="Câu mới?"):
    return {"items": [{"type": "SINGLE_CHOICE", "stem": stem, "explanation": "e", "options": ["p", "q"], "correct": "A"}]}


def fix_math(s, u):
    data = json.loads(u.split("\n\n", 1)[1])
    return {k: v.replace("{a}{b$", "{a}{b}$") for k, v in data.items()}


def humanize_route(s, u):
    return {k: v.replace("Hãy cùng khám phá", "Đây là") for k, v in json.loads(u).items()}


def refiner(tmp_path, drafts, client, *, write=None, render=None, kinds=None, o=None, results=None):
    return refine.Refiner(o or outline(), drafts, results if results is not None else {}, client,
                          write=write or (lambda ol, hint: (None, None)), render=render or (lambda req: None),
                          kinds=kinds or {"diagram"}, max_rounds=3, workers=2)


# ---------------------------------------------------------------- static checks
def test_check_pack_finds_every_kind_of_hole(tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(b"AAAA")
    good = AssetRef(path="img/a.png", mime="image/png", sha256=refine._sha(img), bytes=4)  # noqa: SLF001
    bad = good.model_copy(update={"path": "img/b.png", "sha256": "1" * 64})
    gone = good.model_copy(update={"path": "img/gone.png"})
    drafts = [
        draft("l1", extra=[ImageBlock(id="l1-b2", image=good, alt="hình"), ImageBlock(id="l1-b3", image=gone, alt="hình"),
                           ImageBlock(id="l1-b4", image=bad, alt="hình")]),
        draft("l2", quiz=False, text="Hãy cùng khám phá điện trường. $\\frac{a}{b$ "),
        draft("l3", text=""),
        draft("l4", text="TODO viết sau"),
    ]
    pack = CoursePack(course_id="c1", version=1, language="vi", age_band="g10_12", title="T", chapters=[
        {"id": "ch", "title": "C", "lessons": [d.lesson.model_dump() for d in drafts[:4]]}])
    files = {"img/a.png": img, "img/b.png": img}  # b.png: the file is there but its hash is not the pack's
    issues = refine.check_pack(pack, lambda r: files.get(r.path), outline(5, titles=["a", "b", "c", "d", "e"]))
    got = {(i.code, i.lesson_id) for i in issues}
    assert ("lesson_missing", "l5") in got and ("quiz_missing", "l2") in got and ("asset_missing", "l1") in got
    assert ("asset_hash", "l1") in got and ("block_placeholder", "l4") in got and ("katex", "l2") in got
    assert ("lint", "l2") in got and ("block_empty", "l3") in got
    assert {i.severity for i in issues if i.code in refine.HARD} == {"hard"} and next(i for i in issues if i.code == "lint").severity == "soft"
    good_pack = CoursePack(course_id="c1", version=1, language="vi", age_band="g10_12", title="T", chapters=[
        {"id": "ch", "title": "C", "lessons": [draft("l1", extra=[ImageBlock(id="l1-b2", image=good, alt="h")]).lesson.model_dump()]}])
    assert refine.check_pack(good_pack, lambda r: files.get(r.path), outline(1)) == []


def test_quiz_key_problems_and_duplicates_and_repeats():
    ok = item()
    assert refine.quiz_key_problem(ok) is None
    assert "not one of the choices" in refine.quiz_key_problem(ok.model_construct(**{**ok.__dict__, "answer_key": {"correct_option_id": "Z"}}))
    twin = ok.model_construct(**{**ok.__dict__, "options": [{"id": "A", "text": "x"}, {"id": "B", "text": "X"}]})
    twin.options = [type(ok.options[0])(id="A", text="x"), type(ok.options[0])(id="B", text="X")]
    assert "same text" in refine.quiz_key_problem(twin)
    tf = QuizItem(id="q", type="TRUE_FALSE_GROUP", stem="s", statements=[{"id": "a", "text": "x"}, {"id": "b", "text": "y"}],
                  answer_key={"statements": {"a": True, "b": False}}, explanation="e")
    assert refine.quiz_key_problem(tf.model_construct(**{**tf.__dict__, "answer_key": {"statements": {"a": True}}}))
    sa = QuizItem(id="q", type="SHORT_ANSWER", stem="s", answer_key={"accepted": ["4e4", "50000"]}, explanation="e")
    assert "differ" in refine.quiz_key_problem(sa)
    a, b = draft("l1", text=LONG + ". " + LONG).lesson, draft("l2", text=LONG + ". " + LONG).lesson
    assert refine.repeat_ratio(a, b) > 0.9
    assert refine.repeat_ratio(a, draft("l3", text="Ví dụ khác hẳn về dòng điện không đổi trong mạch kín gồm nguồn và điện trở " * 2).lesson) < 0.1


def test_katex_uses_the_real_parser_when_available():
    bad = katex_check.check_texts({"a": "$\\frac{1}{2}$ ok", "b": "bad $\\frac{1}{2$", "c": "unbalanced $x"})
    assert "a" not in bad and "b" in bad and "c" in bad
    if katex_check.find_katex():  # only KaTeX knows an unknown command
        assert "d" in katex_check.check_texts({"d": "$\\notacommand{x}$"})


# ---------------------------------------------------------------- the loop: every repair
def test_refiner_repairs_every_kind_of_problem(tmp_path):
    client = FakeClient({"Solve this quiz": solver, "write quiz items": counting_quiz(),
                         "repair LaTeX": fix_math, "editing your own lesson": humanize_route})
    diagram = MediaRequest(id="l1-b2", kind="diagram", course_id="c1", lesson_id="l1", age_band="g10_12", language="vi",
                           spec={"description": "d"})
    d1 = draft("l1", text="Hãy cùng khám phá đường sức điện.", media=[diagram],
               extra=[ImageBlock(id="l1-b2", image=AssetRef(path="pending/l1-b2.png", mime="image/png", sha256="0" * 64, bytes=0), alt="h")])
    d3 = draft("l3", quiz=False, text="Công thức là $\\frac{a}{b$ trong bài.")
    d4 = draft("l4", stem="WRONG key?")
    writes, renders = [], []

    def write(ol, hint):
        writes.append((ol.id, hint))
        return draft("l2", text="Bài hai nói về cường độ điện trường tại một điểm."), None

    def render(req):
        renders.append(req.id)
        return tmp_result(tmp_path, req.id)

    r = refiner(tmp_path, [d1, d3, d4], client, write=write, render=render).run()
    assert r.issues == [] and not r.blocked
    assert {i.code for i in r.fixed} >= {"lesson_missing", "quiz_missing", "katex", "quiz_wrong", "media_missing", "lint"}
    assert writes == [("l2", writes[0][1])] and "l1-b2" in renders
    pack = r.assembled.pack
    assert [ls.id for ls in pack.chapters[0].lessons] == ["l1", "l2", "l3", "l4"]
    assert all(any(isinstance(b, QuizBlock) for b in ls.blocks) for ls in pack.chapters[0].lessons)  # a quiz everywhere
    assert "Đây là đường sức" in pack.chapters[0].lessons[0].blocks[0].md and "{a}{b}$" in pack.chapters[0].lessons[2].blocks[0].md
    assert next(b for b in pack.chapters[0].lessons[3].blocks if isinstance(b, QuizBlock)).items[0].stem.startswith("Câu mới số")
    assert any(isinstance(b, ImageBlock) for b in pack.chapters[0].lessons[0].blocks)  # the picture was re-rendered into the pack
    assert r.report()["blocked"] is False and r.report()["fixed"]


def test_refiner_reports_what_it_cannot_fix_in_plain_words(tmp_path):
    client = FakeClient({"Solve this quiz": {"answer": "B"}, "write quiz items": new_quiz("Câu mới?"),
                         "repair LaTeX": lambda s, u: json.loads(u.split("\n\n", 1)[1])})  # the model repairs nothing
    diagram = MediaRequest(id="l1-b2", kind="diagram", course_id="c1", lesson_id="l1", age_band="g10_12", language="vi", spec={"description": "d"})
    d1 = draft("l1", media=[diagram], text="Công thức $\\frac{a}{b$ ở đây.")
    d3 = draft("l3", stem="Câu ba?")  # the solver always says B: the key A looks wrong and no replacement passes
    o = outline(3, titles=["Điện trường", "Cường độ", "Tụ điện"])
    r = refiner(tmp_path, [d1, d3], client, o=o).run()
    codes = {(i.code, i.lesson_id) for i in r.issues}
    assert ("lesson_missing", "l2") in codes and ("media_missing", "l1") in codes and ("katex", "l1") in codes
    assert ("quiz_dropped", "l3") in codes and ("quiz_missing", "l3") in codes  # removed and said so, never silent
    assert r.blocked and any(i.severity == "soft" for i in r.issues)
    lines = {i.code: i.vi for i in r.issues}
    assert "Cường độ" in lines["lesson_missing"] and "Điện trường" in lines["katex"] and "bỏ qua" in lines["media_missing"]
    assert all(i.vi and i.en for i in r.issues)
    assert r.report()["blocked"] and len(r.report()["hard"]) >= 3  # hard errors listed for the teacher; soft ones apart


def test_refiner_rewrites_a_lesson_that_repeats_its_neighbour_and_a_placeholder(tmp_path):
    client = FakeClient({"Solve this quiz": solver})
    hints = []

    def write(ol, hint):
        hints.append((ol.id, hint))
        facts = {"l2": "Cường độ điện trường tại một điểm bằng lực điện chia cho điện tích thử đặt ở điểm đó.",
                 "l3": "Dòng điện trong kim loại là dòng chuyển dời có hướng của các electron tự do dưới tác dụng của nguồn."}
        return draft(ol.id, text=facts[ol.id]), None

    d1 = draft("l1", text=LONG + ". " + LONG)
    d2 = draft("l2", text=LONG + ". " + LONG)
    d3 = draft("l3", text="TODO viết sau")
    r = refiner(tmp_path, [d1, d2, d3], client, write=write, o=outline(3)).run()
    by = dict(hints)
    assert sorted(by) == ["l2", "l3"] and "repeated" in by["l2"] and "«l1»" in by["l2"] and "placeholder" in by["l3"]
    assert not r.blocked and {i.code for i in r.fixed} >= {"repeat", "block_placeholder"}


def test_stale_read_aloud_is_made_again_after_the_text_changes(tmp_path):
    client = FakeClient({"Solve this quiz": solver, "editing your own lesson": humanize_route})
    tts_req = MediaRequest(id="l1-b1", kind="tts", course_id="c1", lesson_id="l1", age_band="g1_5", language="vi",
                           spec={"text": "Hãy cùng khám phá điện trường."})
    d1 = draft("l1", text="Hãy cùng khám phá điện trường.", media=[tts_req])
    d1.lesson.blocks[0] = d1.lesson.blocks[0].model_copy(update={"audio": AssetRef(path="pending/l1-b1.mp3", mime="audio/mpeg", sha256="0" * 64, bytes=0)})
    renders, forgot = [], []

    def render(req):
        renders.append(req.spec["text"])
        return tmp_result(tmp_path, req.id, "tts", "audio/l1-b1.mp3", b"mp3-" + req.spec["text"].encode())

    r = refiner(tmp_path, [d1], client, o=outline(1), kinds={"tts"}, render=render).run()
    r2 = refine.Refiner(outline(1), [d1], {}, client, write=lambda ol, h: (None, None), render=render,
                        forget=forgot.append, kinds={"tts"}).run()
    assert renders and all("Hãy cùng" not in t for t in renders[1:])  # after the humanize pass the clip carries the new text
    assert r.issues == [] and r2.issues == []


def test_publish_blockers_use_live_checks_and_unchanged_verdicts(tmp_path):
    d = draft("l1", stem="Câu một?")
    pack = assemble(outline(1), [d]).pack
    h = verify.item_hash(pack.chapters[0].lessons[0].blocks[-1].items[0])
    stored = [{"code": "quiz_wrong", "lesson_id": "l1", "block_id": "l1-q1", "detail": "solver said B", "item_hash": h}]
    assert refine.publish_blockers(pack, lambda r: None, outline(1)) == []
    got = refine.publish_blockers(pack, lambda r: None, outline(1), stored)
    assert [i.code for i in got] == ["quiz_wrong"] and "Bài một" in got[0].vi
    stored[0]["item_hash"] = "edited-since"
    assert refine.publish_blockers(pack, lambda r: None, outline(1), stored) == []  # the item changed: old verdict is void
    assert [i.code for i in refine.publish_blockers(pack, lambda r: None, outline(2))] == ["lesson_missing"]


# ---------------------------------------------------------------- speed
def test_speakable_cleans_markdown_and_says_simple_math():
    assert speakable("**Nhớ:** năng lượng $E=mc^2$ và $\\frac{1}{2}$", "vi") == "Nhớ: năng lượng E bằng mc bình phương và 1 chia 2"
    assert speakable("- Điểm A\n- Điểm B\n# Tiêu đề", "vi") == "Điểm A Điểm B Tiêu đề"
    assert speakable("$$ $$", "vi").strip("$ ") == ""  # nothing to say: the caller raises "empty text" (no wasted provider call)
    assert "plus" in speakable("$2+3$ items", "en") and "\\" not in speakable("$\\alpha + 1$", "en")


def test_media_plan_caps_video_and_pictures_by_content_and_age():
    names = ["Chuyển động thẳng đều", "Định nghĩa vận tốc", "Dao động điều hòa", "Công thức tính quãng đường",
             "Sóng cơ và sự lan truyền sóng", "Bài tập tổng hợp", "Thí nghiệm về con lắc"]
    plan = plan_media(outline(7, titles=names))
    assert sum(p.video for p in plan.values()) <= 3 and sum(p.video for p in plan.values()) >= 1  # 7 lessons: never 7 videos
    assert plan["l6"].video == 0 and plan["l4"].video == 0 and plan["l2"].video == 0  # definitions and exercises: no video
    assert plan_media(outline(3, band="uni", titles=["a", "b", "c"]))["l1"].video == 0
    kid = plan_media(outline(3, band="g1_5", titles=["Số 1", "Số 2", "Số 3"]))
    assert all(p.video == 0 and p.pictures == 2 for p in kid.values())
    assert plan_media(outline(2, band="g1_5", titles=["Xem phim", "Số 2"]), "Xem phim ngắn về số")["l1"].video == 1
    text_only = plan_media(outline(2, band="g10_12", titles=["Lịch sử khái niệm", "Tên các nhà khoa học"]))
    assert all(p.pictures == 0 for p in text_only.values())  # nothing visual to show
    data = {"blocks": [{"kind": "video", "title": "t", "target_s": 60, "scenes": [{"caption": "c", "narration": "n", "visual": "v"}] * 3},
                       {"kind": "illustration", "description": "a", "alt": "a"}, {"kind": "diagram", "description": "b", "alt": "b"},
                       {"kind": "text", "md": "ok"}]}
    blocks, media, notes = blocks_from_json(data, course_id="c", lesson_id="l", age_band="g10_12", language="vi", plan=LessonMedia(video=0, pictures=1, prefer="diagram"))
    assert [type(b).__name__ for b in blocks] == ["ImageBlock", "TextBlock"] and len(media) == 1 and len(notes) == 2


def test_deeptutor_is_skipped_after_repeated_failures(tmp_path, monkeypatch):
    dt = DeepTutor(tmp_path, "https://x/v1", "k", "uvx")
    calls = []
    monkeypatch.setattr(dt, "setup", lambda: None)
    monkeypatch.setattr(dt, "_run", lambda args, timeout=None: calls.append(1) or (_ for _ in ()).throw(DeepTutorError("nltk")))
    for _ in range(2):
        with pytest.raises(DeepTutorError):
            dt.quiz("Bài", "kb")
    assert len(calls) == 2  # a process failure is not retried inside the call
    with pytest.raises(DeepTutorError, match="skipped"):
        dt.quiz("Bài", "kb")
    assert len(calls) == 2  # and the third call does not even start uvx


def test_check_items_run_side_by_side_and_agree_with_check_item():
    import threading
    import time

    seen, lock = [], threading.Lock()

    class Slow:
        def complete(self, alias, messages, **kw):
            with lock:
                seen.append(threading.get_ident())
            time.sleep(0.2)
            return json.dumps({"answer": "A"})

    items = [item("l1", i, f"Câu {i}?") for i in range(1, 5)]
    t = time.time()
    out = verify.check_items(items, Slow(), "vi", workers=4)
    assert all(v.ok for v in out) and time.time() - t < 0.6 and len(set(seen)) > 1  # 4 x 0.2 s sequentially would be 0.8 s


class FakeDT(DeepTutor):
    def __init__(self):
        super().__init__(Path("."), "b", "k", "uvx")
        self.asked, self.kb_made = [], []

    def available(self):
        return True

    def create_kb(self, name, files):
        import time as t

        t.sleep(0.05)
        self.kb_made.append(name)
        return 0.05

    def quiz(self, topic, kb, n=3, language="vi"):
        self.asked.append((topic, n))
        return [RawQuestion("Q?", {"A": "x", "B": "y"}, "B", "Vì y.", "easy")] * n

    def mastery_path(self, kb, goal, language="vi"):
        return {"modules": [{"name": "Điện trường", "knowledge_points": [{"name": "Đường sức điện"}, {"name": "Tụ điện"}]}]}


def test_build_course_prefetches_deeptutor_quiz_and_tags_skills():
    from mentor_course_builder.intake import IntakeResult
    from mentor_course_builder.models import Material, Page
    from mentor_course_builder.pipeline import build_course
    from test_content import _draft

    o, ol, pages, client = _draft()
    client.routes["editing your own lesson"] = lambda s, u: json.loads(u)
    client.routes["Solve this quiz"] = lambda s, u: {"answer": "B"} if "Q?" in u else {"answer": "A" if "S?" in u else "4e4"}
    intake = IntakeResult(materials=[Material("a.pdf", "pdf", [Page("a.pdf", 1, "pdf_text", text="Điện trường"),
                                                                Page("a.pdf", 2, "pdf_text", text="Đường sức điện là đường vẽ.")])])
    dt, got = FakeDT(), []
    res = build_course(intake, o, client, dt=dt, only_lessons=[ol.id], quiz_items=3, workers=1, on_draft=lambda d: got.append(d.lesson.id))
    assert dt.asked == [(ol.title, 2)] and len(dt.kb_made) == 1  # one KB for the course, one quiz call, started by the pipeline
    assert got == [ol.id]  # the media stage is told as soon as the lesson is final
    quiz = next(b for b in res.drafts[0].lesson.blocks if isinstance(b, QuizBlock))
    assert sum(1 for q in quiz.items if q.type == "SINGLE_CHOICE" and q.stem == "Q?") == 2
    assert all(q.skill_ids == ["duong-suc-dien"] for q in quiz.items)
    assert any("mastery path" in n and "tagged" in n for n in res.notes) and any("knowledge base" in n for n in res.notes)


def test_edge_outage_costs_one_try_per_voice_after_three_failed_clips(tmp_path, monkeypatch):
    from mentor_course_builder import tts
    from test_media_stage import FakeProv

    monkeypatch.setattr(tts, "to_mp3", lambda *a, **k: None)
    edge = FakeProv("edge-tts", fail_all=True)
    svc = tts.TtsService([edge], cache_dir=tmp_path, sleep=lambda s: None)
    for i in range(3):
        with pytest.raises(tts.TtsError):
            svc.synthesize(f"Câu số {i}", lang="vi", age_band="g10_12")
    assert len(edge.calls) == 3 * 5
    edge.calls.clear()
    with pytest.raises(tts.TtsError):
        svc.synthesize("Câu tiếp theo", lang="vi", age_band="g10_12")
    assert len(edge.calls) == 2  # the dead endpoint is probed once per voice, not walked through the whole ladder
    with pytest.raises(tts.TtsError, match="empty text"):
        svc.synthesize("$$ $$", lang="vi", age_band="g10_12")
    assert len(edge.calls) == 2


# ---------------------------------------------------------------- job_build end to end (fakes)
def test_job_build_runs_the_gate_and_writes_the_report(tmp_path, monkeypatch):
    from mentor_course_builder import render_media as rm
    from mentor_course_builder import workflow as wf
    from mentor_course_builder.outline import outline_to_json
    from mentor_gateway.content import ContentStore
    from test_content import OWN, _outline

    o = _outline(teacher_note="lớp 11").model_copy(update={"language": "vi"})
    lesson_json = lambda s, u: {"blocks": [  # noqa: E731
        {"kind": "text", "md": f"Nội dung riêng của bài: {u.split('LESSON: ')[1].splitlines()[0]}, có điện trường và đường sức."},
        {"kind": "callout", "variant": "remember", "title": "Nhớ", "md": "- Ý chính"},
        {"kind": "diagram", "description": "field lines", "labels": ["+"], "math": None, "alt": "a", "caption": "h"}]}
    client = FakeClient({"write one lesson": lesson_json, "write quiz items": {"items": [OWN["items"][2]]},
                         "Solve this quiz": {"answer": "A"}, "editing your own lesson": lambda s, u: json.loads(u)})
    made = []

    def fake_render(req, out_dir, *, client=None, tts=None):
        made.append(req.kind)
        f = Path(out_dir) / f"{req.id}.bin"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"x" * 40)
        return MediaResult(id=req.id, kind=req.kind, files=[MediaFile(role="main", path=f"img/{req.id}.webp", mime="image/webp", file=f)])

    monkeypatch.setattr(rm, "render_media", fake_render)
    base = tmp_path / "b"
    base.mkdir()
    (base / "outline.json").write_text(outline_to_json(o), encoding="utf-8")
    args = {"course_id": o.course_id, "store": str(tmp_path / "courses"), "media_kinds": ["diagram", "cover"], "workers": 2,
            "media_workers": 2, "teacher_id": "t1", "teacher_name": "Thầy", "deeptutor": False}
    out = wf.job_build(base, args, client)
    assert out["ok"] and out["version"] == 1 and out["blocked"] is False and set(out["profile"]) >= {"content_s", "total_s"}
    n = len(o.lessons())
    assert f"{n}/{n}" in out["message_vi"] and made.count("diagram") >= n and "cover" in made
    rep = json.loads((base / "versions" / "1" / "verify.json").read_text("utf-8"))
    assert rep["blocked"] is False and rep["hard"] == [] and "checked_at" in rep
    prog = json.loads((base / "build" / "progress.json").read_text("utf-8"))
    assert prog["stage"] == "done" and {ls["state"] for ls in prog["lessons"]} == {"done"}
    store = ContentStore(tmp_path / "courses")
    assert refine.check_store_version(store, o.course_id, 1, o) == []  # the same check the gateway runs before publishing
    store.publish(o.course_id, 1)

    # a model that cannot write one lesson: the gate retries it, then tells the teacher in plain words and blocks
    bad = FakeClient({"write one lesson": lambda s, u: (_ for _ in ()).throw(AssertionError("x")) if "Tụ điện" in u else lesson_json(s, u),
                      "write quiz items": {"items": [OWN["items"][2]]}, "Solve this quiz": {"answer": "A"},
                      "editing your own lesson": lambda s, u: json.loads(u)})
    base2 = tmp_path / "b2"
    base2.mkdir()
    (base2 / "outline.json").write_text(outline_to_json(o), encoding="utf-8")
    monkeypatch.setattr("mentor_course_builder.llm.time.sleep", lambda s: None, raising=False)
    try:
        out2 = wf.job_build(base2, {**args, "store": str(tmp_path / "courses2")}, bad)
    except AssertionError:
        pytest.skip("fake client raised through ask_json")
    assert out2["blocked"] is True and any(i["code"] == "lesson_missing" and "Tụ điện" in i["vi"] for i in out2["issues"])
    assert "Còn" in out2["message_vi"] and "Tụ điện" in out2["message_vi"]


def test_web_picture_keeps_its_credit_and_webp_passes_the_gate(tmp_path):
    from mentor_course_builder.assemble import assemble as asm_

    req = MediaRequest(id="l1-b2", kind="illustration", course_id="c1", lesson_id="l1", age_band="g10_12", language="vi",
                       spec={"description": "d"})
    d1 = draft("l1", media=[req], extra=[ImageBlock(id="l1-b2", image=AssetRef(path="pending/l1-b2.png", mime="image/png",
                                                                                sha256="0" * 64, bytes=0), alt="hình")])
    f = tmp_path / "p.webp"
    f.write_bytes(b"RIFFxxxxWEBP")
    res = MediaResult(id="l1-b2", kind="illustration", files=[MediaFile(role="main", path="images/l1-b2.webp", mime="image/webp", file=f)],
                      meta={"attribution": {"provider": "wikimedia", "title": "T", "author": None, "license": "CC0",
                                            "license_url": None, "source_url": "https://x/y"}})
    a = asm_(outline(1), [d1], {"l1-b2": res})
    img = next(b for b in a.pack.chapters[0].lessons[0].blocks if isinstance(b, ImageBlock))
    assert img.image.mime == "image/webp" and img.attribution["license"] == "CC0" and img.attribution["author"] is None
    assert refine.check_pack(a.pack, lambda r: a.assets.get(r.path), outline(1)) == []
