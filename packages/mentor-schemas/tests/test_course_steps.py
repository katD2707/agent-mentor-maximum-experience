"""Stepped-lesson content (app 0.2.0): tiles, pairs, order, the drag diagram, recall, chapter recap, gloss."""

import pytest
from pydantic import ValidationError

from mentor_schemas.course import (
    AssetRef, ChapterRecap, CoursePack, InteractiveBlock, QuizBlock, QuizItem, RecallBlock, TextBlock,
)

SHA = "0" * 64


def item(**kw) -> QuizItem:
    base = dict(id="q1", stem="?", explanation="Vì vậy.")
    return QuizItem(**{**base, **kw})


def test_fill_tiles_needs_one_gap_per_answer():
    ok = item(type="FILL_TILES", stem="E = k·|q| / {{gap}}", parts=[{"id": "p1", "text": "r"}, {"id": "p2", "text": "r²"}],
              answer_key={"gaps": ["p2"]})
    assert ok.answer_key["gaps"] == ["p2"]
    with pytest.raises(ValidationError):
        item(type="FILL_TILES", stem="no gap", parts=[{"id": "p1", "text": "r"}, {"id": "p2", "text": "r²"}],
             answer_key={"gaps": ["p2"]})
    with pytest.raises(ValidationError):
        item(type="FILL_TILES", stem="{{gap}}", parts=[{"id": "p1", "text": "r"}, {"id": "p2", "text": "r²"}],
             answer_key={"gaps": ["zz"]})


def test_match_pairs_maps_every_left_to_one_right():
    parts = [{"id": "l1", "text": "E", "side": "left"}, {"id": "l2", "text": "F", "side": "left"},
             {"id": "r1", "text": "V/m", "side": "right"}, {"id": "r2", "text": "N", "side": "right"}]
    item(type="MATCH_PAIRS", parts=parts, answer_key={"pairs": {"l1": "r1", "l2": "r2"}})
    with pytest.raises(ValidationError):
        item(type="MATCH_PAIRS", parts=parts, answer_key={"pairs": {"l1": "r1"}})
    with pytest.raises(ValidationError):
        item(type="MATCH_PAIRS", parts=parts, answer_key={"pairs": {"l1": "r1", "l2": "r1"}})


def test_order_steps_lists_every_part_once():
    parts = [{"id": "s1", "text": "Đọc đề"}, {"id": "s2", "text": "Chọn công thức"}, {"id": "s3", "text": "Thay số"}]
    item(type="ORDER_STEPS", parts=parts, answer_key={"order": ["s1", "s2", "s3"]})
    with pytest.raises(ValidationError):
        item(type="ORDER_STEPS", parts=parts, answer_key={"order": ["s1", "s2"]})


def drag(**kw) -> InteractiveBlock:
    base = dict(id="d1", prompt="Kéo để E còn 1/4", x={"symbol": "r", "label": "Khoảng cách", "unit": "m"},
                y={"symbol": "E", "label": "Cường độ", "unit": "V/m"}, expr="9e9*4e-8/x^2", x_min=0.05, x_max=0.4,
                x_step=0.05, x_start=0.1, target_y=9000, tolerance=1, praise="Xa gấp đôi thì E còn 1/4.")
    return InteractiveBlock(**{**base, **kw})


def test_interactive_range():
    assert drag().kind == "interactive"
    with pytest.raises(ValidationError):
        drag(x_start=1.0)


def test_pack_with_new_kinds_needs_app_020_and_lists_recap_audio():
    audio = AssetRef(path="recap/ch1.mp3", mime="audio/mpeg", sha256=SHA, bytes=10)
    pack = CoursePack(
        course_id="c-x", version=1, language="en", age_band="g10_12", title="T", gloss_start=30,
        chapters=[{
            "id": "ch1", "title": "C1", "recap": ChapterRecap(script=["Đoạn 1."], audio=audio, duration_s=240),
            "lessons": [{
                "id": "l1", "title": "L1", "est_minutes": 6, "key_ideas": ["a"],
                "blocks": [
                    TextBlock(id="b1", md="Fields weaken with distance.", gloss="Càng xa, trường càng yếu."),
                    drag(id="b2"),
                    QuizBlock(id="b3", items=[item(id="q9", type="ORDER_STEPS",
                                                   parts=[{"id": "s1", "text": "a"}, {"id": "s2", "text": "b"}],
                                                   answer_key={"order": ["s1", "s2"]})]),
                    RecallBlock(id="b4", items=[{"prompt": "What surrounds a charge?", "answer": "A field."}]),
                ],
            }],
        }],
    )
    assert pack.required_app_version() == "0.2.0"
    assert audio in pack.assets()
    old = CoursePack(course_id="c-y", version=1, language="vi", age_band="g10_12", title="T",
                     chapters=[{"id": "ch1", "title": "C", "lessons": [{"id": "l1", "title": "L", "est_minutes": 3,
                                                                       "blocks": [{"kind": "text", "id": "b1", "md": "x"}]}]}])
    assert old.required_app_version() == "0.1.0"
