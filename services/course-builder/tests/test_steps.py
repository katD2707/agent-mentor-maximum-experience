"""Stepped lessons (CONTRACTS 16.2): the step mix, the new kinds through the gate, recaps, review.json, the two new jobs.
Offline: ModelClient is a fake, TTS and the media stage are stubbed."""

import json
from pathlib import Path

import pytest
from mentor_course_builder import recap, refine, steps, workflow as wf
from mentor_course_builder import render_media as rm
from mentor_course_builder.assemble import assemble
from mentor_course_builder.contracts import MediaFile, MediaRequest, MediaResult
from mentor_course_builder.lessons import blocks_from_json, write_lesson
from mentor_course_builder.outline import CourseOutline, OutlineChapter, OutlineLesson
from mentor_schemas.course import (Axis, Chapter, ChapterRecap, CoursePack, InteractiveBlock, Lesson, QuizBlock, RecallBlock,
                                   TextBlock)
from test_content import FakeClient

pytest.importorskip("mentor_gateway.content.store")
from mentor_gateway.content.store import ContentStore  # noqa: E402
from mentor_schemas.course import CourseMeta  # noqa: E402

LESSON = {"blocks": [
    {"kind": "text", "md": "Force makes things move.", "gloss": "Lực làm vật chuyển động."},
    {"kind": "text", "md": "A bigger force gives a bigger push.", "gloss": "Lực lớn thì đẩy mạnh hơn."},
    {"kind": "callout", "variant": "remember", "title": "Remember", "md": "$F = m a$"},
    {"kind": "interactive", "prompt": "Drag r until E is a quarter", "x": {"symbol": "r", "label": "Distance", "unit": "m"},
     "y": {"symbol": "E", "label": "Field", "unit": "V/m"}, "expr": "100/x^2", "x_min": 1, "x_max": 4, "x_step": 1,
     "x_start": 1, "target_y": 25, "tolerance": 0.5, "praise": "Twice as far, a quarter of the field."},
    {"kind": "text", "md": "Mass resists the push.", "gloss": "Khối lượng cản lại lực đẩy."},
    {"kind": "text", "md": "Heavy things speed up slowly.", "gloss": "Vật nặng tăng tốc chậm."},
    {"kind": "recall", "items": [{"prompt": "What does force do?", "answer": "It changes motion."},
                                 {"prompt": "What resists force?", "answer": "Mass."}]},
]}
QUIZ = {"items": [
    {"type": "SINGLE_CHOICE", "stem": "Which is a force?", "explanation": "A push is a force.", "difficulty": 1,
     "options": [{"text": "A push"}, {"text": "A colour", "feedback": "A colour is not a push."}, {"text": "A name"}],
     "correct": "A"},
    {"type": "FILL_TILES", "stem": "$F = {{gap}} \\cdot a$", "explanation": "Force is mass times acceleration.",
     "answers": ["m"], "distractors": ["v", "t"]},
    {"type": "MATCH_PAIRS", "stem": "Match", "explanation": "Units.", "pairs": [
        {"left": "F", "right": "newton"}, {"left": "m", "right": "kilogram"}, {"left": "t", "right": "second"}]},
    {"type": "ORDER_STEPS", "stem": "Order the steps", "explanation": "That is the order.",
     "steps": ["Find the mass", "Find the force", "Divide"]},
    {"type": "TRUE_FALSE_GROUP", "stem": "True or false?", "explanation": "e", "statements": [
        {"text": "Mass is a force", "answer": False}, {"text": "A push is a force", "answer": True}]},
]}


def outline(lang="en", band="g6_9"):
    ls = [OutlineLesson(id=f"l{i}", title=f"Lesson {i}", summary="s", key_ideas=["Force", "Mass"]) for i in (1, 2, 3, 4)]
    return CourseOutline(course_id="c1", title="Forces", subject="Physics", language=lang, age_band=band,
                         description_short="d", chapters=[OutlineChapter(id="ch1", title="Forces", lessons=ls[:2]),
                                                          OutlineChapter(id="ch2", title="Motion", lessons=ls[2:])])


def client():
    return FakeClient({"write one lesson": LESSON, "write quiz items": QUIZ,
                       "Solve this quiz": lambda s, u: {"answer": "A", "answers": {"a": False, "b": True}},
                       "spoken recap": lambda s, u: {"script": ["Paragraph about force and mass. " * 12] * 8}})


def written(o=None):
    o = o or outline()
    c = client()
    return o, [write_lesson(o, ol, c, {}, quiz_items=5) for ol in o.lessons()], c


def test_lesson_is_stepped_and_valid():
    o, drafts, _ = written()
    d = drafts[0]
    kinds = [type(b).__name__ for b in d.lesson.blocks]
    assert 8 <= len(kinds) <= 14 and kinds[-1] == "RecallBlock" and kinds.count("InteractiveBlock") == 1
    qs = [q for b in d.lesson.blocks if isinstance(b, QuizBlock) for q in b.items]
    assert {q.type for q in qs} >= {"FILL_TILES", "MATCH_PAIRS", "ORDER_STEPS", "SINGLE_CHOICE"}
    # a question every 2-3 steps: no run of 3+ explanation steps without a question
    run = 0
    for k in kinds[:-1]:
        run = 0 if k == "QuizBlock" else run + 1
        assert run <= 3
    texts = [b for b in d.lesson.blocks if isinstance(b, TextBlock)]
    assert texts and all(t.gloss for t in texts)  # English course: Vietnamese gloss on every explanation
    sc = next(q for q in qs if q.type == "SINGLE_CHOICE")
    assert set(sc.option_feedback) == {"B", "C"}  # every wrong option has a line
    rec = d.lesson.blocks[-1]
    assert isinstance(rec, RecallBlock) and 2 <= len(rec.items) <= 3
    pack = assemble(o, drafts).pack
    CoursePack.model_validate(pack.model_dump(mode="json"))
    assert pack.min_app_version == "0.2.0" and pack.gloss_start == 30


def test_difficulty_spreads_over_the_course():
    _, drafts, _ = written()
    levels = {q.difficulty for d in drafts for b in d.lesson.blocks if isinstance(b, QuizBlock) for q in b.items}
    assert levels == {1, 2, 3, 4}


def test_vietnamese_course_has_no_gloss_and_g1_5_has_no_steps():
    o = outline("vi")
    d = write_lesson(o, o.lessons()[0], client(), {}, quiz_items=5)
    assert all(b.gloss is None for b in d.lesson.blocks if isinstance(b, TextBlock))
    assert assemble(o, [d]).pack.gloss_start is None
    blocks, _, notes = blocks_from_json(LESSON, course_id="c", lesson_id="l", age_band="g1_5", language="vi")
    assert not any(isinstance(b, (InteractiveBlock, RecallBlock)) for b in blocks)


def interactive(**kw):
    base = dict(id="x-b1", prompt="p", x=Axis(symbol="r", label="d", unit="m"), y=Axis(symbol="E", label="e", unit=""),
                expr="100/x^2", x_min=1, x_max=4, x_step=1, x_start=1, target_y=25, tolerance=0.5, praise="ok")
    return InteractiveBlock(**{**base, **kw})


def test_interactive_checks():
    assert steps.interactive_problem(interactive()) is None
    assert "cannot be reached" in steps.interactive_problem(interactive(target_y=26.5))  # between two grid points
    assert "cannot be computed" in steps.interactive_problem(interactive(x_min=0, x_start=0))  # 100/0
    assert "cannot be computed" in steps.interactive_problem(interactive(expr="foo(x)"))
    assert steps.eval_expr("9e9*4e-8/x^2", 2) == pytest.approx(90) and steps.eval_expr("2x+sqrt(x)", 4) == 10
    blocks, _, notes = blocks_from_json({"blocks": [{**LESSON["blocks"][3], "target_y": 26.5}]}, course_id="c",
                                        lesson_id="l", age_band="g6_9", language="en")
    assert not blocks and any("interactive block dropped" in n for n in notes)


def test_gate_accepts_and_checks_the_new_kinds():
    o, drafts, _ = written()
    pack = assemble(o, drafts).pack
    assert not [i for i in refine.check_pack(pack, lambda r: None, o) if i.severity == "hard"]
    bad = pack.model_copy(deep=True)
    ls = bad.chapters[0].lessons[0]
    ib = next(i for i, b in enumerate(ls.blocks) if isinstance(b, InteractiveBlock))
    ls.blocks[ib] = interactive(id=ls.blocks[ib].id, target_y=26.5)
    fill = next(q for b in ls.blocks if isinstance(b, QuizBlock) for q in b.items if q.type == "FILL_TILES")
    fill.parts = fill.parts[:1]  # no spare tile: not a real choice
    fill.answer_key = {"gaps": [fill.parts[0].id]}
    rec = next(b for b in ls.blocks if isinstance(b, RecallBlock))
    rec.items[0].answer = " "
    codes = {i.code for i in refine.check_pack(bad, lambda r: None, o)}
    assert {"interactive_bad", "recall_bad", "quiz_key"} <= codes


def test_recap_script_audio_and_assembly(tmp_path):
    o, drafts, c = written()
    scripts = recap.write_recaps(o, drafts, c)
    assert set(scripts) == {"ch1", "ch2"} and 180 * 0.8 <= recap.estimate_seconds(scripts["ch1"], "en") <= 300 * 1.2
    req = recap.recap_request(o, "ch1", scripts["ch1"])
    assert req.kind == "recap" and req.id == "recap-ch1"
    f = tmp_path / "r.mp3"
    f.write_bytes(b"mp3")
    res = {"recap-ch1": MediaResult(id="recap-ch1", kind="recap", duration_s=200.0, files=[
        MediaFile(role="main", path="audio/recap-ch1.mp3", mime="audio/mpeg", file=f)])}
    a = assemble(o, drafts, res, recaps=scripts)
    r1, r2 = a.pack.chapters[0].recap, a.pack.chapters[1].recap
    assert r1.audio and r1.duration_s == 200.0 and r1.script == scripts["ch1"]
    assert r2.audio is None and any("recap-ch2" in n for n in a.notes)  # the script is kept when the voice is missing
    assert "audio/recap-ch1.mp3" in a.assets


def test_recap_media_request_renders_one_mp3(tmp_path):
    class Svc:
        def synthesize(self, text, *, dest, **kw):
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
            Path(dest).write_bytes(b"a" * 10)
            return type("Clip", (), {"path": Path(dest), "duration_s": 4.0, "notes": []})()

    req = MediaRequest(id="recap-ch1", kind="recap", course_id="c1", age_band="g6_9", language="en",
                       spec={"script": ["One.", "Two.", " "]})
    out = rm.render_media(req, tmp_path, tts=Svc())
    assert out.duration_s == 8.0 and out.files[0].path == "audio/recap-ch1.mp3"
    assert (tmp_path / "audio" / "recap-ch1.mp3").read_bytes() == b"a" * 20
    with pytest.raises(Exception):
        rm.validate_request(req.model_copy(update={"spec": {}}))


def test_review_rows_are_plain_and_point_at_blocks():
    o, drafts, _ = written()
    pack = assemble(o, drafts).pack
    q = next(q for b in pack.chapters[0].lessons[0].blocks if isinstance(b, QuizBlock) for q in b.items)
    issues = [refine.Issue("quiz_wrong", "l1", q.id, "x").say({"l1": "Lesson 1"}),
              refine.Issue("lint", "l1", None).say({"l1": "Lesson 1"})]
    rows = refine.review_rows(pack, issues)
    assert rows[0]["item_id"] == q.id and rows[0]["block_id"] != q.id and rows[0]["reason_vi"] and rows[0]["reason_en"]
    assert rows[1]["block_id"] == pack.chapters[0].lessons[0].blocks[0].id and "item_id" not in rows[1]
    drafts_by_id = {d.lesson.id: d for d in drafts}
    un = wf.unsure_rows(pack, [], drafts_by_id)  # nothing was independently solved in this fake build
    assert un and all(set(r) <= {"block_id", "item_id", "reason_vi", "reason_en"} for r in un)
    json.dumps({"unsure": un}, ensure_ascii=False)


@pytest.fixture
def course(tmp_path):
    o, drafts, c = written()
    pack = assemble(o, drafts, recaps={"ch1": ["Old script."]}).pack
    store = ContentStore(tmp_path / "courses")
    meta = CourseMeta(id="c1", title="Forces", subject="Physics", age_band="g6_9", language="en", teacher_id="t",
                      teacher_name="T", description_short="d", cover="cover.webp")
    v = store.create_draft(meta)
    store.write_pack("c1", v, pack, {})
    base = tmp_path / "b"
    base.mkdir()
    return store, base, {"version": v, "store": str(store.root), "course_id": "c1"}


def test_job_recap_rewrites_script_and_audio(course, tmp_path, monkeypatch):
    store, base, common = course
    seen = []

    def fake_render(req, out_dir, *, client=None, tts=None):
        seen.append(req)
        f = tmp_path / "new.mp3"
        f.write_bytes(b"new-voice")
        return MediaResult(id=req.id, kind="recap", duration_s=215.5, files=[
            MediaFile(role="main", path="audio/recap-ch1.mp3", mime="audio/mpeg", file=f)])

    monkeypatch.setattr(rm, "render_media", fake_render)
    out = wf.run_job("recap", base, {**common, "chapter_id": "ch1", "script": ["New one.", "New two."]}, lambda: None)
    assert out["ok"] and out["duration_s"] == 215.5 and seen[0].spec["script"] == ["New one.", "New two."]
    rc = store.load_pack("c1", common["version"]).chapters[0].recap
    assert rc.script == ["New one.", "New two."] and rc.audio.bytes == len(b"new-voice") and rc.duration_s == 215.5
    assert store.asset_path("c1", common["version"], "audio/recap-ch1.mp3").read_bytes() == b"new-voice"
    with pytest.raises(wf.JobError):
        wf.run_job("recap", base, {**common, "chapter_id": "nope", "script": ["x"]}, lambda: None)
    with pytest.raises(wf.JobError):
        wf.run_job("recap", base, {**common, "chapter_id": "ch1", "script": []}, lambda: None)


def test_job_retts_block_redoes_one_read_aloud(course, tmp_path, monkeypatch):
    store, base, common = course
    pack = store.load_pack("c1", common["version"])
    blk = next(b for b in pack.chapters[0].lessons[0].blocks if isinstance(b, TextBlock))
    from mentor_course_builder.assemble import _ref
    from mentor_schemas.course import AssetRef

    clip = tmp_path / "old.mp3"
    clip.write_bytes(b"old")
    ref = _ref(MediaFile(role="audio", path="audio/b1.mp3", mime="audio/mpeg", file=clip))
    pack = pack.model_copy(deep=True)
    next(b for b in pack.chapters[0].lessons[0].blocks if b.id == blk.id).audio = ref
    store.write_pack("c1", common["version"], pack, {"audio/b1.mp3": clip})
    said = []

    def fake_retts(text, dest, pack_, rel):
        said.append(text)
        f = tmp_path / "again.mp3"
        f.write_bytes(b"again!")
        return _ref(MediaFile(role="audio", path=rel, mime="audio/mpeg", file=f)), f

    monkeypatch.setattr(wf, "_retts", fake_retts)
    out = wf.run_job("retts_block", base, {**common, "block_id": blk.id}, lambda: None)
    assert out["ok"] and said == [blk.md]
    assert store.asset_path("c1", common["version"], "audio/b1.mp3").read_bytes() == b"again!"
    other = next(b for b in pack.chapters[0].lessons[0].blocks if isinstance(b, QuizBlock))
    with pytest.raises(wf.JobError):
        wf.run_job("retts_block", base, {**common, "block_id": other.id}, lambda: None)
    assert {"recap", "retts_block"} <= set(wf.JOBS)


def test_recall_falls_back_to_the_key_ideas():
    from mentor_course_builder.lessons import recall_from_key_ideas

    rb = recall_from_key_ideas("ch1-l2", "Đường sức điện", ["Đường sức không cắt nhau", " ", "Dày thì mạnh", "a", "b"], "vi")
    assert rb is not None and rb.id == "ch1-l2-r1" and len(rb.items) == 3
    assert rb.items[0].prompt == "Ý chính 1 của bài «Đường sức điện» là gì?" and rb.items[1].answer == "Dày thì mạnh"
    assert recall_from_key_ideas("l1", "T", [], "en") is None
    assert recall_from_key_ideas("l1", "Fields", ["Field lines never cross"], "en").items[0].prompt == "The key idea of “Fields”?"


def test_ask_json_asks_again_after_an_empty_reply():
    from mentor_course_builder.gen import ask_json
    from mentor_course_builder.llm import ModelError

    class Flaky:
        calls = 0

        def complete(self, *a, **k):
            Flaky.calls += 1
            if Flaky.calls == 1:
                raise ModelError("empty model reply")
            return '{"ok": true}'

    assert ask_json(Flaky(), "s", "u", retries=1) == {"ok": True}
    assert Flaky.calls == 2


def test_json_reply_with_code_fences_inside_strings():
    from mentor_course_builder.jsonparse import parse_model_json

    body = '{"blocks": [{"kind": "text", "md": "Ví dụ:\n```sql\nSELECT * FROM hoc_sinh;\n```\nXong."}]}'
    assert parse_model_json(body)["blocks"][0]["md"].startswith("Ví dụ:")
    fenced = "```json\n" + body + "\n```"
    assert "SELECT" in parse_model_json(fenced)["blocks"][0]["md"]
    assert parse_model_json('Here you go:\n```json\n{"a": 1}\n```')["a"] == 1


def test_paren_math_becomes_dollar_math():
    from mentor_course_builder.gen import dollar_math
    from mentor_course_builder.verify import katex_problems

    out = dollar_math({"md": "Hàm \(f(x)=x^2\) liên tục: \[\lim_{x\to a} f(x) = f(a)\]", "n": 3, "l": ["\(a\)"]})
    assert out["md"] == "Hàm $f(x)=x^2$ liên tục: $$\lim_{x\to a} f(x) = f(a)$$" and out["l"] == ["$a$"] and out["n"] == 3
    assert katex_problems(out["md"]) == []
    assert dollar_math("re.compile(r'\(')") == "re.compile(r'\(')"  # a lone \( is not math


def test_prices_are_escaped_only_when_dollars_do_not_pair_up():
    from mentor_course_builder.gen import dollar_math
    from mentor_course_builder.verify import katex_problems

    s = dollar_math("The ticket costs $15 and the bag $3.")
    assert s == "The ticket costs \$15 and the bag \$3." and katex_problems(s) == []
    one = dollar_math("It costs $15.")
    assert one == "It costs \$15." and katex_problems(one) == []
    math = "Let $x = 2$ and $y = 3$."
    assert dollar_math(math) == math  # balanced: left alone


def test_formulas_starting_with_a_number_stay_math():
    from mentor_course_builder.gen import dollar_math

    for m in ("Ta có $2x + 3 = 7$ nên $x = 2$.", "Diện tích $3 \cdot 4 = 12$ cm².", "$$2^{10} = 1024$$"):
        assert dollar_math(m) == m
