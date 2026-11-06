"""Practice engine units: scoring, assembler constraints and determinism, recommender rules (no HTTP)."""

import pytest
from practice_fixtures import TOPICS, build_content

from mentor_gateway.practice import assembler as asm
from mentor_gateway.practice import scoring
from mentor_gateway.practice.bank import Bank
from mentor_gateway.practice.mastery import TopicMastery
from mentor_gateway.practice.recommender import History, TopicInput, recommend

FIXTURE_CONTENT = __import__("pathlib").Path(__file__).parent / "fixtures" / "mentor-content"


@pytest.fixture(scope="module")
def bank(tmp_path_factory) -> Bank:
    return Bank(build_content(FIXTURE_CONTENT, tmp_path_factory.mktemp("content") / "c"))


# ---- scoring -------------------------------------------------------------------------------------


@pytest.mark.parametrize("given,points,correct", [("TTFF", 1.0, True), ("TTFT", 0.5, False), ("FTFT", 0.25, False),
                                                   ("FFFT", 0.1, False), ("FFTT", 0.0, False), ("", 0.0, None), ("----", 0.0, None),
                                                   ("ĐĐSS", 1.0, True), ("a:Đ b:Đ c:S d:S", 1.0, True)])
def test_true_false_partial_credit(given, points, correct):
    sc = scoring.score_true_false(given, [True, True, False, False])
    assert (sc.points, sc.correct) == (points, correct)


def test_true_false_blank_statement_counts_as_not_right_and_scales_with_part_points():
    sc = scoring.score_true_false("TT-F", [True, True, False, False], max_points=1.0)
    assert sc.points == 0.5 and sc.statement_correct == [True, True, False, True] and sc.correct is False
    assert scoring.score_true_false("TTFT", [True, True, False, False], 0.5).points == 0.25


@pytest.mark.parametrize("typed,ok", [("-0,5", True), ("-0.5", True), ("−0,5", True), ("-0,50", False), ("-0,5 m", True),
                                       (" +0,5", False), ("-0,6", False), ("abc", False), ("-0,555", False), ("", False)])
def test_short_answer_normalisation(typed, ok):
    key = {"answer": "-0,5", "decimals": 1, "unit": "m", "max_chars": 4}
    assert scoring.short_answer_matches(typed, key) is ok


def test_short_answer_precision_tolerance_and_sheet_length():
    assert scoring.short_answer_matches("1,30", {"answer": "1,3", "max_chars": 4})
    assert not scoring.short_answer_matches("1,27", {"answer": "1,3", "max_chars": 4})
    assert scoring.short_answer_matches("1,27", {"answer": "1,3", "tolerance": 0.05})
    assert not scoring.short_answer_matches("12345", {"answer": "12345", "max_chars": 4})  # does not fit the sheet


def test_score_item_single_choice_and_policy():
    doc = {"type": "SINGLE_CHOICE", "answer_key": {"correct_option_id": "B"}}
    assert scoring.score_item(doc, " b ").correct is True
    assert scoring.score_item(doc, "A").correct is False
    assert scoring.score_item(doc, None).correct is None
    assert scoring.policy_for({"SINGLE_CHOICE"}) == "mcq-v1"
    assert scoring.policy_for({"SINGLE_CHOICE", "SHORT_ANSWER"}) == "scoring-v2"
    assert scoring.scaled(7.25, 10) == 7.25 and scoring.scaled(1, 3) == 3.33


# ---- assembler -----------------------------------------------------------------------------------


def _mastery(**by_topic: tuple[float, int]) -> dict[str, TopicMastery]:
    return {t: TopicMastery(t, m, e) for t, (m, e) in by_topic.items()}


def test_level_sequence_and_distribution_keep_the_mix():
    assert asm.level_sequence(10, [0.4, 0.3, 0.2, 0.1]) == [1] * 4 + [2] * 3 + [3] * 2 + [4]
    dealt = asm.distribute_levels({"a": 4, "b": 3, "c": 3}, [0.4, 0.3, 0.2, 0.1], seed=1)
    assert sorted(lv for v in dealt.values() for lv in v) == asm.level_sequence(10, [0.4, 0.3, 0.2, 0.1])
    assert [len(v) for v in dealt.values()] == [4, 3, 3]


def test_practice_is_deterministic_per_seed_and_respects_constraints(bank):
    m = _mastery(**{"math.function": (0.9, 6), "math.exp-log": (0.3, 4)})
    c = asm.Constraints(time_budget_sec=20 * 60)
    a1 = asm.assemble_practice(bank, "math", m, c, 7)
    a2 = asm.assemble_practice(bank, "math", m, c, 7)
    assert [s.item.id for s in a1.items] == [s.item.id for s in a2.items]
    ids = [s.item.id for s in a1.items]
    assert len(set(ids)) == len(ids) and 5 <= len(ids) <= 40
    n = len(ids)
    cap = max(1, int(n * 0.4)) + 1  # allocation cap, plus one for the time-fit padding
    assert max(a1.per_topic().values()) <= cap
    assert abs(a1.total_seconds - 20 * 60) <= 20 * 60 * 0.15 + 120


def test_practice_goals_shift_the_topic_mix(bank):
    m = _mastery(**{"math.function": (0.95, 8), "math.exp-log": (0.2, 8), "math.integral": (0.2, 8)})
    weak = asm.assemble_practice(bank, "math", m, asm.Constraints(time_budget_sec=1200, goal="weak"), 3).per_topic()
    chal = asm.assemble_practice(bank, "math", m, asm.Constraints(time_budget_sec=1200, goal="challenge"), 3).per_topic()
    assert weak.get("math.function", 0) < chal.get("math.function", 0)


def test_weak_topic_gets_no_stretch_and_easy_levels(bank):
    m = _mastery(**{"math.function": (0.2, 8)})
    a = asm.assemble_practice(bank, "math", m, asm.Constraints(time_budget_sec=900, topic_filter={"math.function"}), 5)
    assert all("STRETCH_ITEM" not in s.reasons for s in a.items)
    assert all(s.item.level <= 3 for s in a.items)


def test_recently_seen_items_are_avoided_and_exclusions_hold(bank):
    c0 = asm.Constraints(time_budget_sec=600, topic_filter={"math.function"})
    first = {s.item.id for s in asm.assemble_practice(bank, "math", {}, c0, 2).items}
    c1 = asm.Constraints(time_budget_sec=600, topic_filter={"math.function"}, recently_seen=dict.fromkeys(first, 1))
    second = {s.item.id for s in asm.assemble_practice(bank, "math", {}, c1, 2).items}
    assert len(second & first) < len(first)
    c2 = asm.Constraints(time_budget_sec=600, exclude_ids=first)
    assert not {s.item.id for s in asm.assemble_practice(bank, "math", {}, c2, 2).items} & first


def test_too_few_items_is_an_error_never_padding(bank):
    with pytest.raises(asm.InsufficientContent) as e:
        asm.assemble_practice(bank, "math", {}, asm.Constraints(time_budget_sec=600, min_items=500), 1)
    assert e.value.required == 500 and e.value.available > 0


def test_mock_follows_matrix_and_level_mix_and_is_deterministic(bank):
    p = bank.profiles["math.mcq.t"]
    c = asm.Constraints(time_budget_sec=p.time_limit_sec)
    a = asm.assemble_mock(bank, p, c, 11)
    assert [s.item.id for s in a.items] == [s.item.id for s in asm.assemble_mock(bank, p, c, 11).items]
    assert a.per_topic() == {t: 3 for t in sorted(TOPICS)}
    assert all(s.item.type == "SINGLE_CHOICE" for s in a.items)
    assert sum(a.level_mix()) == 9 and a.level_mix()[0] >= 3  # 0.4/0.3/0.2/0.1 of 9; level fallback allowed
    assert [s.item.level for s in a.items] == sorted(s.item.level for s in a.items)


def test_official_format_mock_fills_part_by_part_and_relaxes_a_level_mix_the_bank_cannot_meet(bank):
    p = bank.profiles["math.parts.t"]
    a = asm.assemble_mock(bank, p, asm.Constraints(time_budget_sec=p.time_limit_sec), 4)
    assert [s.part for s in a.items] == [1] * 6 + [2] * 3 + [3] * 3
    assert [s.points_each for s in a.items][6] == 1.0
    assert any(f.startswith("LEVEL_FALLBACK") for f in a.fallbacks)  # every TF is level 3, part II wanted 2/3/4: best effort
    with pytest.raises(asm.InsufficientContent):
        asm.assemble_mock(bank, bank.profiles["math.too-big.t"], asm.Constraints(time_budget_sec=600), 4)


def test_diagnostic_is_two_items_on_up_to_six_topics_single_choice_only(bank):
    a = asm.assemble_diagnostic(bank, "math", 9)
    assert len(a.items) == 6 and set(a.per_topic().values()) == {2}
    assert all(s.item.type == "SINGLE_CHOICE" for s in a.items)
    assert [s.item.id for s in a.items] == [s.item.id for s in asm.assemble_diagnostic(bank, "math", 9).items]
    assert len({s.item.topic for s in a.items[:3]}) == 3  # round-robin: every topic early


def test_bank_hides_unapproved_and_unusable_items(tmp_path):
    root = build_content(FIXTURE_CONTENT, tmp_path / "c")
    import json

    f = next((root / "bank" / "math").glob("function.json"))
    d = json.loads(f.read_text(encoding="utf-8"))
    d["questions"][0]["quality_status"] = "NEEDS_HUMAN_REVIEW"
    d["questions"][1]["answer_key"] = {"correct_option_id": "Z"}
    f.write_text(json.dumps(d), encoding="utf-8")
    ids = {i.id for i in Bank(root).items.values()}
    assert "math.function.001" not in ids and "math.function.002" not in ids and "math.function.003" in ids


# ---- recommender ---------------------------------------------------------------------------------


def _topics(**states: tuple[float | None, int]) -> list[TopicInput]:
    return [TopicInput(t, t.split(".")[1], 0.1, TopicMastery(t, m, e)) for t, (m, e) in states.items()]


def test_recommender_rules_and_wording():
    none = _topics(**{"math.a": (None, 0), "math.b": (None, 0)})
    r = recommend("math", none, History(False, 0, 0, 0))
    assert [x["code"] for x in r] == ["TAKE_DIAGNOSTIC"] and r[0]["reason"].startswith("Vì sao:")
    assert r[0]["action"] == {"kind": "diagnostic", "params": {"subject": "math"}}

    mixed = _topics(**{"math.weak": (0.2, 5), "math.dev": (0.6, 3), "math.strong": (0.95, 6), "math.new": (None, 0)})
    codes = [x["code"] for x in recommend("math", mixed, History(True, 1, 1, 0), "p")]
    assert codes == ["PRACTICE_WEAK", "PROBE_UNKNOWN", "CHALLENGE_STRONG"]
    practice = recommend("math", mixed, History(True, 1, 1, 0), "p")[0]
    assert practice["action"]["params"]["topics"] == ["math.weak", "math.dev"] and "yếu" not in practice["title"].lower()

    good = _topics(**{"math.a": (0.95, 6), "math.b": (0.6, 3)})
    assert [x["code"] for x in recommend("math", good, History(True, 2, 3, 0), "math.mcq")][-1] == "TAKE_MOCK"
    assert recommend("math", good, History(True, 7, 1, 0))[-1]["code"] == "REDIAGNOSE"


def test_take_a_break_after_two_hours_comes_first_and_total_is_capped_at_three():
    mixed = _topics(**{"math.weak": (0.2, 5), "math.strong": (0.95, 6), "math.new": (None, 0)})
    r = recommend("math", mixed, History(True, 7, 4, 120), "p")
    assert r[0]["code"] == "TAKE_A_BREAK" and r[0]["action"]["kind"] == "break" and len(r) == 3
    assert recommend("math", mixed, History(True, 0, 0, 119), "p")[0]["code"] != "TAKE_A_BREAK"
