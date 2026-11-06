"""sympy_check: verify a learner's answer with SymPy (plan 7.3, skill math-tutoring).

Input: {kind: "solve" | "equivalent" | "simplify", problem, answer, variables?: [str]}.
Output: {correct, expected, detail, verified}. `verified` is false when the check could not be
done (unparseable input, unsupported problem); `correct` is then false and `detail` says why.
Never raises on bad math input; learner-facing `detail` is Vietnamese.

Batch: {checks: [<single input>, ...]} (at most MAX_BATCH) -> {results: [<single output>, ...],
all_correct}. One call checks a whole quiz or every step of a solution: each extra tool round is a
full model call (10-20 s), the SymPy work itself is milliseconds.

Canonical answer format (CONTRACTS section 4): SymPy-style expressions, solutions separated by ';'
("x = 2; x = -4"), variables of one system solution separated by ',' ("x = 1, y = 2"; a repeated
variable starts the next solution), and the literal "vô nghiệm" for no solution.

Also accepted (problem and answer): x^2, x², x⁻¹, x₁, implicit multiplication (2x, 2(x+1),
(x+1)(x-1), sin x), √x, √(x+1), ∛x, π, comma decimals (2,5), ':' and '÷' for division,
'×' and '·' for multiplication, Unicode minus signs, Vietnamese prose around the math
("Giải phương trình: ..."). Solution sets: "x1 = 2; x2 = -4", "x = 2 hoặc x = -4",
"S = {2; -4}", "x = ±2", "vô nghiệm", "S = ∅", "vô số nghiệm", "S = R"; roots marked
"(loại)" are dropped. Systems: one equation per line or separated by ';' / "và",
answers "(1; 2)" or "x = 1; y = 2".

Comma rule: a comma between two digits is a decimal comma when the text contains ';' or no
brackets; otherwise (e.g. "{2,5}") commas separate items.
"""

import contextlib
import os
import re
import string
import sys
import threading
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import sympy as sp
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

from mentor_scripts.common import run_cli

MAX_INPUT_CHARS = 500
MAX_BATCH = 10
# Time limits (s), under the harness's 30 s kill: one check of a batch, and the whole call.
CHECK_SECONDS = 8.0
BATCH_SECONDS = 22.0
_abandoned = False  # a timed-out check is still running in a daemon thread
SIMPLIFY_SLACK_OPS = 2

_TRANSFORMS = standard_transformations + (implicit_multiplication_application, convert_xor)
_FUNCS: dict[str, Any] = {
    "sqrt": sp.sqrt,
    "cbrt": lambda a: sp.real_root(a, 3),
    "sin": sp.sin,
    "cos": sp.cos,
    "tan": sp.tan,
    "tg": sp.tan,
    "cot": sp.cot,
    "cotg": sp.cot,
    "log": sp.log,
    "ln": sp.log,
    "exp": sp.exp,
    "abs": sp.Abs,
    "pi": sp.pi,
}
# Every single letter is a real symbol (so S, E, I, N, O, Q never hit SymPy singletons), except e.
_LOCALS: dict[str, Any] = {c: sp.Symbol(c, real=True) for c in string.ascii_letters}
_LOCALS["e"] = sp.E
_LOCALS.update(_FUNCS)
# parse_expr evals generated code; give it only the constructors it emits and no builtins.
_GLOBALS: dict[str, Any] = {
    "Integer": sp.Integer,
    "Float": sp.Float,
    "Rational": sp.Rational,
    "Number": sp.Number,
    "Symbol": sp.Symbol,
    "Function": sp.Function,
    "__builtins__": {},
}

_SUPERSCRIPT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺", "0123456789-+")
_SUBSCRIPT = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_SIMPLE_REPL = {
    "−": "-", "–": "-", "—": "-", "‐": "-", "×": "*", "·": "*", "⋅": "*", "∙": "*", "÷": "/",
    "π": "pi", "，": ",", "；": ";", " ": " ", "[": "(", "]": ")", "≈": "=", "∈": "=",
    "⇒": "=>", "⇔": "=>", "→": "=>", "<=>": "=>",
}
_ALLOWED_EXPR = re.compile(r"[0-9A-Za-z_+\-*/^()., \t]+")
_LABEL = re.compile(r"^\s*([A-Za-z])(?:_?\{?\d+\}?)?\s*$")
_MATH_WORDS = set(_FUNCS)
# ASCII words treated as prose (Vietnamese typed without diacritics). Kept to words that are
# unlikely products of variables.
_ASCII_PROSE = {
    "giai", "phuong", "trinh", "tim", "tinh", "rut", "gon", "bieu", "thuc", "cho", "biet", "nghiem",
    "cua", "sau", "hay", "bai", "cau", "vay", "tap", "duoc", "ket", "qua", "dap", "nen", "suy", "pt",
    "hpt", "dkxd", "hai", "mot", "bon", "nhan", "kep", "phan", "the", "solve", "solution",
    "solutions", "simplify", "answer", "roots", "root", "em", "con", "minh", "toi", "ban", "dc",
}
_SEPARATOR_WORDS = re.compile(r"(?i)(?<![^\W\d_])(hoặc|hoac|or|và|va|and)(?![^\W\d_])")
_ALL_REALS = re.compile(r"vo so nghiem|moi\s+[a-z]\b|ℝ|\bs\s*=\s*r\b|=\s*r\s*$|(thuoc|∈)\s*r\b|infinitely many|all real")
_EMPTY = re.compile(r"vo nghiem|khong co nghiem|∅|\{\s*\}|\brong\b|no (real )?solutions?")
_REJECTED = re.compile(r"loai|khong thoa|\bktm\b")
_INEQUALITY = re.compile(r"[<>≤≥]")


class MathParseError(Exception):
    """Learner-facing (Vietnamese) reason the text could not be read."""


@dataclass
class Value:
    label: str | None  # base variable of "x1 = ..." / "x = ...", None for bare values
    expr: sp.Expr
    decimals: int  # most digits after a decimal point in the literal, 0 if exact


def fold(text: str) -> str:
    """Lowercase without Vietnamese diacritics, for keyword matching."""
    t = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(ch for ch in t if unicodedata.category(ch) != "Mn").lower()


def _is_prose(word: str) -> bool:
    low = word.lower()
    if low in _MATH_WORDS:
        return False
    return any(ord(ch) > 127 for ch in word) or fold(word) in _ASCII_PROSE


def _strip_headings(text: str) -> str:
    """Drop "Bài 1: Giải phương trình:"-style headings ending with a colon."""
    while True:
        cut = None
        for m in re.finditer(r":", text):
            segment = text[: m.start()].rsplit(":", 1)[-1]
            words = re.findall(r"[^\W\d_]+", segment)
            if "=" not in segment and any(_is_prose(w) for w in words):
                cut = m.end()
        if cut is None:
            return text
        text = text[cut:]


def _remove_prose(text: str) -> str:
    marked = re.sub(r"[^\W\d_]+", lambda m: "\x00" if _is_prose(m.group()) else m.group(), text)
    marked = re.sub(r"\x00[ \t]*\d+[ \t]*(?=\x00)", "\x00", marked)  # the 2 in "có 2 nghiệm"
    return marked.replace("\x00", " ")


def normalize(text: str) -> str:
    """Unicode and handwriting-style notation -> SymPy-parseable ASCII (prose not yet removed)."""
    t = unicodedata.normalize("NFC", text)
    for a, b in _SIMPLE_REPL.items():
        t = t.replace(a, b)
    t = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺]+", lambda m: "^(" + m.group().translate(_SUPERSCRIPT) + ")", t)
    t = t.translate(_SUBSCRIPT)
    t = t.replace("+-", "±").replace("-+", "±")
    for sym, fn in (("√", "sqrt"), ("∛", "cbrt")):
        t = re.sub(sym + r"\s*\(", fn + "(", t)
        t = re.sub(sym + r"\s*(\d+(?:[.,]\d+)?|[A-Za-z])", fn + r"(\1)", t)
    return t


def apply_comma_rule(text: str) -> str:
    """Resolve decimal commas, then turn the remaining commas into ';' separators."""
    if ";" in text or not re.search(r"[{}()]", text):
        text = re.sub(r"(?<=\d),(?=\d)", ".", text)
    return text.replace(",", ";")


def _decimals(text: str) -> int:
    return max((len(m) for m in re.findall(r"\d\.(\d+)", text)), default=0)


def parse_math(text: str) -> sp.Expr:
    """Parse one already-normalized expression (no '=', no separators)."""
    t = text.strip().replace(":", "/")
    if not t:
        raise MathParseError("biểu thức trống")
    if len(t) > MAX_INPUT_CHARS:
        raise MathParseError("biểu thức quá dài")
    if not _ALLOWED_EXPR.fullmatch(t):
        bad = "".join(sorted({ch for ch in t if not _ALLOWED_EXPR.fullmatch(ch)}))
        raise MathParseError(f"có ký tự không đọc được: {bad}")
    if "__" in t or re.search(r"[A-Za-z_)]\s*\.", t) or re.search(r"\.\s*[A-Za-z_(]", t):
        raise MathParseError(f"không đọc được biểu thức: {text.strip()}")
    try:
        expr = parse_expr(t, local_dict=dict(_LOCALS), global_dict=dict(_GLOBALS), transformations=_TRANSFORMS)
    except Exception as e:
        raise MathParseError(f"không đọc được biểu thức: {text.strip()}") from e
    if not isinstance(expr, sp.Expr):
        raise MathParseError(f"không đọc được biểu thức: {text.strip()}")
    floats = expr.atoms(sp.Float)
    if floats:
        expr = expr.xreplace({f: sp.Rational(str(f)) for f in floats})
    return expr


def _clean_math_text(text: str) -> str:
    """Normalize, drop headings and prose; keeps '=', ';' and braces."""
    if len(text) > MAX_INPUT_CHARS * 2:
        raise MathParseError("nội dung quá dài")
    t = _strip_headings(normalize(text))
    t = _SEPARATOR_WORDS.sub(" ; ", t)
    t = _remove_prose(t)
    t = re.sub(r"\(\s*\)", " ", t)
    return t.strip().lstrip(":.;").strip()


def is_equal(a: sp.Expr, b: sp.Expr) -> bool:
    try:
        d = sp.simplify(a - b)
        if d == 0:
            return True
        return d.equals(0) is True
    except Exception:  # noqa: BLE001
        return False


def _close(student: Value, exact: sp.Expr) -> bool:
    """Decimal answers count if they match the exact value to the precision written."""
    if student.decimals == 0 or student.expr.free_symbols or exact.free_symbols:
        return False
    try:
        return abs(float(sp.N(student.expr - exact))) <= 0.5 * 10 ** (-student.decimals) + 1e-12
    except (TypeError, ValueError):
        return False


def _matches(student: Value, exact: sp.Expr) -> bool:
    return is_equal(student.expr, exact) or _close(student, exact)


def fmt(expr: sp.Expr) -> str:
    return sp.sstr(expr).replace("**", "^")


def _sort_key(v: sp.Expr) -> tuple[int, float, str]:
    try:
        return 0, float(sp.N(v)), fmt(v)
    except (TypeError, ValueError):
        return 1, 0.0, fmt(v)


def fmt_set(values: list[sp.Expr]) -> str:
    return "S = {" + "; ".join(fmt(v) for v in sorted(values, key=_sort_key)) + "}"


# ---------------------------------------------------------------- problem parsing


def parse_equations(problem: str) -> list[sp.Expr]:
    """Equations of the problem as expressions equal to zero."""
    if _INEQUALITY.search(problem):
        raise MathParseError("chưa hỗ trợ kiểm tra bất phương trình")
    t = apply_comma_rule(_clean_math_text(problem).replace("\n", ";"))
    eqs = []
    for part in (p.strip() for p in t.split(";")):
        if not part:
            continue
        sides = part.split("=")
        if len(sides) == 1:
            eqs.append(parse_math(sides[0]))
        elif len(sides) == 2:
            eqs.append(parse_math(sides[0]) - parse_math(sides[1]))
        else:
            raise MathParseError(f"phương trình có nhiều hơn một dấu '=': {part}")
    if not eqs:
        raise MathParseError("không tìm thấy phương trình trong đề")
    return eqs


def choose_variables(eqs: list[sp.Expr], requested: list[str] | None) -> list[sp.Symbol]:
    free = sorted(set().union(*(e.free_symbols for e in eqs)), key=lambda s: s.name)
    if requested:
        return [_LOCALS[v] if v in _LOCALS and isinstance(_LOCALS[v], sp.Symbol) else sp.Symbol(v, real=True) for v in requested]
    if not free:
        if len(eqs) == 1:
            return [_LOCALS["x"]]  # terms cancel, e.g. 2(x+1) = 2x + 2: identity or contradiction in x
        raise MathParseError("đề không có ẩn")
    if len(eqs) > 1:
        return free
    for name in "xyzt":
        for s in free:
            if s.name == name:
                return [s]
    return [free[0]]


# ---------------------------------------------------------------- answer parsing


def _split_items(answer: str) -> tuple[str, list[str]]:
    """Returns (folded full answer, cleaned items). Items marked "loại" are dropped."""
    raw = unicodedata.normalize("NFC", answer)
    if len(raw) > MAX_INPUT_CHARS * 2:
        raise MathParseError("câu trả lời quá dài")
    raw = re.split(r"=>|⇒|⇔|→", normalize(raw))[-1]
    raw = _SEPARATOR_WORDS.sub(" ; ", raw.replace("\n", ";"))
    raw = apply_comma_rule(raw)
    items = []
    for item in raw.split(";"):
        if _REJECTED.search(fold(item)):
            continue
        t = _remove_prose(_strip_headings(item))
        t = re.sub(r"\(\s*\)", " ", t).replace("{", " ").replace("}", " ")
        t = re.sub(r"^\s*S\s*=", " ", t).strip().strip(".")
        if t:
            items.append(t)
    return fold(answer), items


def _parse_value(item: str) -> list[Value]:
    sides = item.split("=")
    if sides[0].strip() == "" and len(sides) > 1:
        sides = sides[1:]  # "= 2"
    if any(not s.strip() for s in sides):
        raise MathParseError(f"không đọc được: {item}")
    label = None
    for lhs in sides[:-1]:
        m = _LABEL.match(lhs)
        if not m:
            raise MathParseError(f"vế trái phải là tên ẩn (ví dụ x1 = 2), nhận được: {lhs.strip()}")
        label = m.group(1)
    body = sides[-1]
    variants = [body.replace("±", "+", 1), body.replace("±", "-", 1)] if "±" in body else [body]
    return [Value(label, parse_math(v), _decimals(v)) for v in variants]


def parse_answer_values(answer: str) -> tuple[str, list[Value]]:
    """('all' | 'empty' | 'values', values)."""
    folded, items = _split_items(answer)
    if _ALL_REALS.search(folded):
        return "all", []
    if _EMPTY.search(folded):
        return "empty", []
    values = [v for item in items for v in _parse_value(item)]
    if not values:
        raise MathParseError("không tìm thấy giá trị nghiệm trong câu trả lời")
    return "values", values


# ---------------------------------------------------------------- kinds


def _result(correct: bool, expected: str, detail: str, verified: bool = True) -> dict[str, Any]:
    return {"correct": correct, "expected": expected, "detail": detail, "verified": verified}


def _domain_note(eq: sp.Expr, var: sp.Symbol, v: Value) -> bool:
    try:
        r = eq.subs(var, v.expr)
        return bool(r.has(sp.zoo, sp.nan)) or r.is_real is False
    except Exception:  # noqa: BLE001
        return False


def check_single(eq: sp.Expr, var: sp.Symbol, answer: str) -> dict[str, Any]:
    sol = sp.solveset(eq, var, sp.S.Reals)
    if sol == sp.S.Reals:
        expected = "Vô số nghiệm (S = R)"
    elif sol == sp.S.EmptySet:
        expected = "Vô nghiệm (S = ∅)"
    elif isinstance(sol, sp.FiniteSet):
        expected = fmt_set(list(sol))
    else:
        return _result(False, "", "Phương trình có vô số nghiệm dạng họ nghiệm hoặc nghiệm phụ thuộc tham số; "
                       "chưa kiểm tra tự động được, cần kiểm tra thủ công.", verified=False)

    kind, values = parse_answer_values(answer)
    if sol == sp.S.Reals or sol == sp.S.EmptySet:
        want = "all" if sol == sp.S.Reals else "empty"
        if kind == want:
            return _result(True, expected, f"Đúng. {expected}.")
        if kind == "values":
            return _result(False, expected, f"Chưa đúng. Phương trình {expected[0].lower() + expected[1:]}.")
        return _result(False, expected, f"Chưa đúng. Đáp án đúng: {expected}.")

    exact = list(sol)
    if kind != "values":
        return _result(False, expected, f"Chưa đúng. Phương trình có nghiệm: {expected}.")
    missing = [e for e in exact if not any(_matches(v, e) for v in values)]
    extra = [v for v in values if not any(_matches(v, e) for e in exact)]
    if not missing and not extra:
        approx = any(v.decimals and not any(is_equal(v.expr, e) for e in exact) for v in values)
        note = " (giá trị gần đúng chấp nhận được)" if approx else ""
        return _result(True, expected, f"Đúng{note}. {expected}.")

    parts = ["Chưa đúng."]
    domain_bad = [v for v in extra if _domain_note(eq, var, v)]
    plain_bad = [v for v in extra if v not in domain_bad]
    if plain_bad:
        parts.append(f"Giá trị {'; '.join(fmt(v.expr) for v in plain_bad)} không thỏa phương trình.")
    if domain_bad:
        parts.append(f"Giá trị {'; '.join(fmt(v.expr) for v in domain_bad)} không thuộc tập xác định, cần loại.")
    if missing:
        parts.append(f"Còn thiếu nghiệm ({len(missing)} giá trị).")
    if extra and len(values) == len(exact) and all(any(is_equal(-v.expr, e) for e in exact) for v in values):
        parts.append("Các giá trị bị ngược dấu so với nghiệm đúng; kiểm tra lại dấu khi phân tích nhân tử hoặc dùng công thức nghiệm.")
    return _result(False, expected, " ".join(parts))


def _parse_system_answer(answer: str, variables: list[sp.Symbol]) -> tuple[str, list[dict[sp.Symbol, Value]]]:
    names = [v.name for v in variables]
    folded = fold(answer)
    if _ALL_REALS.search(folded) or "vo so" in folded:
        return "all", []
    if _EMPTY.search(folded):
        return "empty", []
    text = normalize(unicodedata.normalize("NFC", answer))
    text = re.split(r"=>", text)[-1]
    tuples = re.findall(r"\(([^()]*[;,][^()]*)\)", text)
    sols: list[dict[sp.Symbol, Value]] = []
    if tuples:
        for tup in tuples:
            if re.fullmatch(r"\s*[A-Za-z](\s*[;,]\s*[A-Za-z])+\s*", tup):
                continue  # "(x; y) = (1; 2)" header
            parts = [p for p in apply_comma_rule("(" + tup + ")")[1:-1].split(";")]
            if len(parts) != len(variables):
                raise MathParseError(f"bộ nghiệm cần {len(variables)} thành phần: ({tup})")
            sols.append({var: _parse_value(p)[0] for var, p in zip(variables, parts)})
        return "values", sols
    _, items = _split_items(answer)
    current: dict[sp.Symbol, Value] = {}
    for item in items:
        for v in _parse_value(item):
            if v.label is None or v.label not in names:
                raise MathParseError("hãy ghi rõ giá trị từng ẩn, ví dụ x = 1; y = 2 hoặc (1; 2)")
            var = variables[names.index(v.label)]
            if var in current:
                sols.append(current)
                current = {}
            current[var] = v
    if current:
        sols.append(current)
    if not sols:
        raise MathParseError("không tìm thấy nghiệm trong câu trả lời")
    return "values", sols


def check_system(eqs: list[sp.Expr], variables: list[sp.Symbol], answer: str) -> dict[str, Any]:
    header = "(" + "; ".join(v.name for v in variables) + ")"
    if len(eqs) != len(variables):
        return _result(False, "", f"Hệ có {len(eqs)} phương trình nhưng {len(variables)} ẩn; chưa kiểm tra tự động được.",
                       verified=False)
    raw = sp.solve(eqs, variables, dict=True)
    sols = [s for s in raw if all(val.is_real is not False for val in s.values())]
    if any(set(s) != set(variables) or any(val.free_symbols for val in s.values()) for s in sols):
        return _result(False, f"{header}: vô số nghiệm", "Hệ có vô số nghiệm; chưa kiểm tra tự động được.", verified=False)
    tuples = sorted((tuple(s[v] for v in variables) for s in sols), key=lambda t: [_sort_key(x) for x in t])
    expected = (" hoặc ".join(f"{header} = (" + "; ".join(fmt(x) for x in t) + ")" for t in tuples)
                if tuples else "Hệ vô nghiệm")

    kind, student = _parse_system_answer(answer, variables)
    if not tuples:
        ok = kind == "empty"
        return _result(ok, expected, "Đúng. Hệ vô nghiệm." if ok else "Chưa đúng. Hệ vô nghiệm.")
    if kind != "values":
        return _result(False, expected, f"Chưa đúng. Hệ có nghiệm {expected}.")
    if any(set(s) != set(variables) for s in student):
        return _result(False, expected, f"Chưa đủ: cần giá trị của tất cả các ẩn {header}.")

    def same(s: dict[sp.Symbol, Value], t: tuple[sp.Expr, ...]) -> bool:
        return all(_matches(s[v], x) for v, x in zip(variables, t))

    missing = [t for t in tuples if not any(same(s, t) for s in student)]
    extra = [s for s in student if not any(same(s, t) for t in tuples)]
    if not missing and not extra:
        return _result(True, expected, f"Đúng. {expected}.")
    parts = ["Chưa đúng."]
    if extra:
        bad = ", ".join("(" + "; ".join(fmt(s[v].expr) for v in variables) + ")" for s in extra)
        parts.append(f"Bộ {bad} không thỏa hệ.")
    if missing:
        parts.append(f"Còn thiếu {len(missing)} bộ nghiệm.")
    return _result(False, expected, " ".join(parts))


def check_solve(problem: str, answer: str, requested: list[str] | None) -> dict[str, Any]:
    eqs = parse_equations(problem)
    variables = choose_variables(eqs, requested)
    if len(eqs) == 1 and len(variables) == 1:
        return check_single(eqs[0], variables[0], answer)
    return check_system(eqs, variables, answer)


def _parse_expression_problem(problem: str) -> sp.Expr:
    t = apply_comma_rule(_clean_math_text(problem))
    if ";" in t:
        raise MathParseError("đề chỉ được có một biểu thức")
    sides = t.split("=")
    if len(sides) > 1:
        if len(sides) != 2 or not _LABEL.match(sides[0]):
            raise MathParseError("đề rút gọn/so sánh phải là một biểu thức, ví dụ A = (x^2 - 1)/(x - 1)")
        sides = sides[1:]
    return parse_math(sides[0])


def _parse_steps(answer: str) -> list[sp.Expr]:
    t = apply_comma_rule(_clean_math_text(answer))
    if ";" in t:
        raise MathParseError("câu trả lời chỉ được có một biểu thức (có thể viết chuỗi A = ... = ...)")
    segments = t.split("=")
    if len(segments) > 1 and re.fullmatch(r"\s*[A-Z](?:_?\d+)?\s*", segments[0]):
        segments = segments[1:]  # "A = ..." names the expression
    steps = [s for s in segments if s.strip()]
    if not steps:
        raise MathParseError("câu trả lời trống")
    return [parse_math(s) for s in steps]


def simplest_forms(expr: sp.Expr) -> list[sp.Expr]:
    forms = [expr]
    for fn in (sp.simplify, sp.factor, sp.expand, sp.cancel, sp.radsimp):
        with contextlib.suppress(Exception):  # a rewrite SymPy cannot do is just not a candidate
            forms.append(fn(expr))
    return sorted(forms, key=lambda f: (sp.count_ops(f), len(fmt(f))))


def check_expression(kind: str, problem: str, answer: str) -> dict[str, Any]:
    ref = _parse_expression_problem(problem)
    steps = _parse_steps(answer)
    best = simplest_forms(ref)[0]
    expected = fmt(best)
    for i, step in enumerate(steps, start=1):
        if not is_equal(step, ref):
            where = f"Bước {i} ({fmt(step)})" if len(steps) > 1 else f"Biểu thức {fmt(step)}"
            return _result(False, expected, f"Chưa đúng. {where} không bằng biểu thức ban đầu.")
    final = steps[-1]
    if kind == "simplify" and sp.count_ops(final) > sp.count_ops(best) + SIMPLIFY_SLACK_OPS:
        return _result(False, expected, f"Biểu thức tương đương nhưng chưa rút gọn hết. Dạng gọn hơn: {expected}.")
    return _result(True, expected, "Đúng. Hai biểu thức bằng nhau." if kind == "equivalent" else f"Đúng. Kết quả rút gọn: {fmt(final)}.")


def _timed(payload: dict[str, Any], seconds: float) -> dict[str, Any]:
    """`_check_one` with a time limit. SymPy can grind for minutes on some inputs (nested radicals, parameters),
    and the harness kills the whole script at 30 s, which in a batch would lose every other result too. A check
    that runs over is reported unverified; its thread is abandoned and `main` exits without waiting for it."""
    global _abandoned
    box: dict[str, dict[str, Any]] = {}
    worker = threading.Thread(target=lambda: box.update(r=_check_one(payload)), daemon=True)
    worker.start()
    worker.join(seconds)
    if "r" in box:
        return box["r"]
    _abandoned = True
    return _result(False, "", "Không kiểm tra được tự động (SymPy tính quá lâu); cần kiểm tra thủ công hoặc viết đề gọn hơn.",
                   verified=False)


def sympy_check(payload: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    checks = payload.get("checks")
    if checks is None:
        return _timed(payload, BATCH_SECONDS)
    if not isinstance(checks, list) or not checks or len(checks) > MAX_BATCH:
        return {"results": [], "all_correct": False, "detail": f"checks phải là danh sách 1-{MAX_BATCH} phép kiểm."}
    deadline = time.monotonic() + BATCH_SECONDS
    results = []
    for c in checks:
        if not isinstance(c, dict):
            results.append(_result(False, "", "Mỗi phép kiểm phải là một object.", verified=False))
        elif (left := deadline - time.monotonic()) < 0.5:
            results.append(_result(False, "", "Không kiểm tra được: hết thời gian của lần gọi này; gọi lại riêng câu này.",
                                   verified=False))
        else:
            results.append(_timed(c, min(CHECK_SECONDS, left)))
    return {"results": results, "all_correct": all(r["correct"] for r in results)}


def _check_one(payload: dict[str, Any]) -> dict[str, Any]:
    kind = payload.get("kind")
    problem = payload.get("problem")
    answer = payload.get("answer")
    if kind not in ("solve", "equivalent", "simplify"):
        return _result(False, "", "kind phải là solve, equivalent hoặc simplify.", verified=False)
    if not isinstance(problem, str) or not problem.strip():
        return _result(False, "", "Thiếu đề bài (problem).", verified=False)
    if not isinstance(answer, str) or not answer.strip():
        return _result(False, "", "Thiếu câu trả lời (answer).", verified=False)
    requested = payload.get("variables")
    if requested is not None and not (isinstance(requested, list) and all(isinstance(v, str) and v.isidentifier() for v in requested)):
        return _result(False, "", "variables phải là danh sách tên ẩn, ví dụ [\"x\"].", verified=False)
    try:
        if kind == "solve":
            return check_solve(problem, answer, requested)
        return check_expression(kind, problem, answer)
    except MathParseError as e:
        return _result(False, "", f"Không kiểm tra được: {e}.", verified=False)
    except Exception as e:  # noqa: BLE001 - SymPy internals; never fail the script on math input
        return _result(False, "", f"Không kiểm tra được tự động ({type(e).__name__}); cần kiểm tra thủ công.", verified=False)


def main() -> None:
    run_cli(sympy_check)
    if _abandoned:  # the answer is out; do not let interpreter shutdown wait on (or crash in) a busy SymPy thread
        sys.stdout.flush()
        os._exit(0)


if __name__ == "__main__":
    main()
