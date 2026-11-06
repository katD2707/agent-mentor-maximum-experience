import pytest
from mentor_scripts.sympy_check import sympy_check

QUADRATIC = "x² + 2x − 8 = 0"


def check(kind: str, problem: str, answer: str) -> dict:
    return sympy_check({"kind": kind, "problem": problem, "answer": answer})


@pytest.mark.parametrize(
    "answer",
    [
        "x1 = 2; x2 = -4",
        "x = 2 hoặc x = −4",
        "x = 2 hoac x = -4",
        "S = {2; -4}",
        "S={-4;2}",
        "{2, -4}",
        "Vậy phương trình có 2 nghiệm x₁ = 2 và x₂ = -4",
        "(x - 2)(x + 4) = 0 ⇔ x = 2 hoặc x = -4",
    ],
)
def test_quadratic_correct_forms(answer: str) -> None:
    out = check("solve", QUADRATIC, answer)
    assert out["correct"] is True, out
    assert out["expected"] == "S = {-4; 2}"
    assert out["verified"] is True


def test_quadratic_sign_error_is_wrong() -> None:
    out = check("solve", QUADRATIC, "S = {4; -2}")
    assert out["correct"] is False
    assert out["expected"] == "S = {-4; 2}"
    assert "ngược dấu" in out["detail"]
    assert "không thỏa phương trình" in out["detail"]


def test_problem_with_vietnamese_heading_and_ascii_powers() -> None:
    out = check("solve", "Bài 1: Giải phương trình: x^2 + 2x - 8 = 0", "x = 2; x = -4")
    assert out["correct"] is True


def test_missing_root() -> None:
    out = check("solve", QUADRATIC, "x = 2")
    assert out["correct"] is False and "thiếu" in out["detail"]


@pytest.mark.parametrize(
    ("problem", "answer", "correct"),
    [
        ("x^2 + 1 = 0", "vô nghiệm", True),
        ("x^2 + 1 = 0", "S = ∅", True),
        ("x^2 + 1 = 0", "x = 1", False),
        ("x/(x - 1) = 1/(x - 1)", "Phương trình vô nghiệm", True),
        ("x/(x - 1) = 1/(x - 1)", "x = 1", False),
        ("2(x + 1) = 2x + 2", "vô số nghiệm", True),
        ("2(x + 1) = 2x + 2", "x = 0", False),
        ("x^2 - 2 = 0", "x = ±√2", True),
        ("x^2 - 2 = 0", "x = 1,41 hoặc x = -1,41", True),  # comma decimals, rounded
        ("x^2 - 2 = 0", "x = 1,3 hoặc x = -1,3", False),
        ("2,5x = 5", "x = 2", True),
        ("x^2 - 4x + 4 = 0", "x1 = x2 = 2", True),
        ("x^2 - 5x + 6 = 0", "x = 1 (loại); x = 2; x = 3", True),
        ("√(x + 3) = 2", "x = 1", True),
        ("x + y = 3\nx - y = 1", "(2; 1)", True),
        ("x + y = 3; x - y = 1", "x = 2, y = 1", True),
        ("x + y = 3 và x - y = 1", "x = 1; y = 2", False),
    ],
)
def test_solve_cases(problem: str, answer: str, correct: bool) -> None:
    out = check("solve", problem, answer)
    assert out["correct"] is correct, out
    assert out["verified"] is True


@pytest.mark.parametrize(
    ("problem", "answer", "correct"),
    [
        # Canonical format pinned in CONTRACTS section 4.
        ("x**2 + 2*x - 8 = 0", "x = 2; x = -4", True),
        ("x**2 + 2*x - 8 = 0", "x = 4; x = -2", False),
        ("x**2 - 2 = 0", "x = sqrt(2); x = -sqrt(2)", True),
        ("x**2 - x - 1 = 0", "x = (1 + sqrt(5))/2; x = (1 - sqrt(5))/2", True),
        ("x**2 + 1 = 0", "vô nghiệm", True),
        ("x + y = 3; x - y = 1", "x = 2, y = 1", True),
        ("x + y = 3; x - y = 1", "x = 1, y = 2", False),
        ("x + y = 1; x + y = 2", "vô nghiệm", True),
        ("x + y = 1; x + y = 2", "x = 1, y = 0", False),
        ("x**2 + y**2 = 2; x - y = 0", "x = 1, y = 1; x = -1, y = -1", True),
        ("x**2 + y**2 = 2; x - y = 0", "x = 1, y = 1", False),
    ],
)
def test_contract_answer_format(problem: str, answer: str, correct: bool) -> None:
    out = check("solve", problem, answer)
    assert out["correct"] is correct, out
    assert out["verified"] is True


def test_domain_rejection_detail() -> None:
    out = check("solve", "(x^2 - 1)/(x - 1) = 0", "x = 1; x = -1")
    assert out["correct"] is False and "tập xác định" in out["detail"]


@pytest.mark.parametrize(
    ("kind", "problem", "answer", "correct"),
    [
        ("equivalent", "(x + 1)^2", "x^2 + 2x + 1", True),
        ("equivalent", "(x + 1)²", "x² + 1", False),
        ("equivalent", "2(x + 3)", "2x + 6", True),
        ("simplify", "A = (x^2 - 1)/(x - 1)", "A = x + 1", True),
        ("simplify", "(x^2 - 1)/(x - 1)", "= (x - 1)(x + 1)/(x - 1) = x + 1", True),
        ("simplify", "(x^2 - 1)/(x - 1)", "(x^2 - 1)/(x - 1)", False),  # equivalent, not simplified
        ("simplify", "(x^2 - 1)/(x - 1)", "= (x - 1)(x - 1)/(x - 1) = x + 1", False),  # wrong middle step
        ("simplify", "√8", "2√2", True),
        ("simplify", "√(x²)", "x", False),  # |x| over the reals
        ("simplify", "0,5x + 0,5x", "x", True),
    ],
)
def test_expression_kinds(kind: str, problem: str, answer: str, correct: bool) -> None:
    out = check(kind, problem, answer)
    assert out["correct"] is correct, out
    assert out["verified"] is True


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "solve", "problem": "x^2 = 4", "answer": "__import__('os').system('echo hi')"},
        {"kind": "solve", "problem": "x^2 = 4", "answer": "lambda: 1"},
        {"kind": "solve", "problem": "x^2 = 4", "answer": "x = ((("},
        {"kind": "solve", "problem": "x^2 > 4", "answer": "x > 2"},
        {"kind": "solve", "problem": "sin x = 0", "answer": "x = kπ"},
        {"kind": "solve", "problem": "", "answer": "x = 1"},
        {"kind": "solve", "problem": "x = 1", "answer": None},
        {"kind": "integrate", "problem": "x", "answer": "x"},
        {"kind": "simplify", "problem": "x" * 2000, "answer": "x"},
        {},
    ],
)
def test_bad_input_never_raises(payload: dict) -> None:
    out = sympy_check(payload)
    assert out["correct"] is False
    assert out["verified"] is False
    assert out["detail"]


def test_cli_sympy_check(run_cli) -> None:
    code, out = run_cli("sympy_check", {"kind": "solve", "problem": QUADRATIC, "answer": "S = {4; -2}"})
    assert code == 0
    assert out["correct"] is False and out["expected"] == "S = {-4; 2}"
    assert "Chưa đúng" in out["detail"]


def test_batch_checks_each_item() -> None:
    out = sympy_check({"checks": [
        {"kind": "solve", "problem": QUADRATIC, "answer": "x = -4; x = 2"},
        {"kind": "equivalent", "problem": "(x + 1)**2", "answer": "x**2 + 2*x + 1"},
        {"kind": "solve", "problem": QUADRATIC, "answer": "x = 4; x = -2"},
        "not an object",
    ]})
    assert [r["correct"] for r in out["results"]] == [True, True, False, False]
    assert out["results"][3]["verified"] is False
    assert out["all_correct"] is False


@pytest.mark.parametrize("checks", [[], "x", [{"kind": "solve"}] * 11])
def test_batch_rejects_bad_list(checks) -> None:
    out = sympy_check({"checks": checks})
    assert out["results"] == [] and out["all_correct"] is False and out["detail"]


def test_batch_slow_check_does_not_sink_the_rest(monkeypatch) -> None:
    import time

    from mentor_scripts import sympy_check as mod

    real = mod._check_one
    monkeypatch.setattr(mod, "CHECK_SECONDS", 0.2)
    monkeypatch.setattr(mod, "_check_one", lambda p: time.sleep(2) or {} if p["problem"] == "slow" else real(p))
    t = time.monotonic()
    out = sympy_check({"checks": [
        {"kind": "solve", "problem": "slow", "answer": "x = 1"},
        {"kind": "solve", "problem": QUADRATIC, "answer": "x = -4; x = 2"},
    ]})
    assert time.monotonic() - t < 1.5
    assert out["results"][0]["verified"] is False and "quá lâu" in out["results"][0]["detail"]
    assert out["results"][1]["correct"] is True
