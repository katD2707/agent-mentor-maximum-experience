"""Pure, deterministic scoring (port of agent-mentor `Scoring.kt` / `AnswerFormats.kt`). No LLM anywhere.

Policies: `mcq-v1` (single choice, 1 point) and `scoring-v2` (adds true/false groups and short answers). For
single-choice items both give the same result, so a session records `scoring-v2` as soon as any other format is
present or its profile says so. Changing any number below needs a new policy version.

Answer encodings (what `POST /answer` receives):
- single choice: the option id (`"A"`, case-insensitive);
- true/false group: one character per statement a-d, `T` = Đúng, `F` = Sai, `-` = not answered (`"TF-T"`);
  lenient forms (`ĐSĐS`, `1010`, `a:Đ b:S ...`) are accepted too;
- short answer: the number as typed (`"-0,5"`, `"1.25"`, `"119 triệu đồng"` with the unit).
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

MCQ_V1 = "mcq-v1"
SCORING_V2 = "scoring-v2"
# share of a group's points by number of statements right, index 0..4 (QĐ 764/QĐ-BGDĐT)
TRUE_FALSE_SHARE = (0.0, 0.1, 0.25, 0.5, 1.0)
STATEMENT_IDS = ("a", "b", "c", "d")


@dataclass
class ItemScore:
    correct: bool | None  # None = left blank; for a group: True only when all four statements are right
    points: float
    max_points: float
    statement_correct: list[bool] = field(default_factory=list)  # true/false groups only


# ---- true/false groups -------------------------------------------------------------------------

_LABELLED = re.compile(r"(?iu)\b([abcd])\s*[:)=.\-]\s*(đúng|sai|true|false|đ|s|t|f|1|0)")


def parse_truths(raw: str | None, n: int = 4) -> list[bool | None] | None:
    """`n` entries (None = blank; 4 for the bank, 3-4 for course groups) from a stored answer, or None when the text does
    not describe `n` statements."""
    text = (raw or "").strip()
    if not text:
        return None
    labelled = _LABELLED.findall(text)
    if labelled:
        by_id = {k.lower(): v.lower() in ("đúng", "true", "đ", "t", "1") for k, v in labelled}
        return [by_id.get(i) for i in STATEMENT_IDS[:n]] if set(by_id) == set(STATEMENT_IDS[:n]) else None
    tokens = text.upper().replace("ĐÚNG", "Đ").replace("SAI", "S").replace("TRUE", "T").replace("FALSE", "F")
    chars = [c for c in tokens if not c.isspace() and c not in ",;|"]
    if len(chars) != n:
        return None
    out: list[bool | None] = []
    for c in chars:
        if c in "TĐ1":
            out.append(True)
        elif c in "FS0":
            out.append(False)
        elif c in "-_?":
            out.append(None)
        else:
            return None
    return out


def encode_truths(choices: list[bool | None]) -> str:
    return "".join("T" if c is True else "F" if c is False else "-" for c in choices)


def score_true_false(answer: str | None, truths: list[bool], max_points: float = 1.0) -> ItemScore:
    """Four statements: the official shares. Course groups with 1-3 statements: the share of statements right."""
    n = len(truths)
    given = parse_truths(answer, n) or [None] * n
    if all(g is None for g in given):
        return ItemScore(None, 0.0, max_points, [False] * n)
    right = [given[i] == truths[i] for i in range(n)]  # a blank statement counts as not right
    share = TRUE_FALSE_SHARE[sum(right)] if n == 4 else sum(right) / n
    return ItemScore(all(right), round(share * max_points, 4), max_points, right)


# ---- short answers -----------------------------------------------------------------------------

_NUMBER = re.compile(r"^([+-]?)(\d*)(?:[.,](\d+))?$")


@dataclass(frozen=True)
class ParsedNumber:
    value: Decimal
    sheet: str  # the form on the answer sheet: minus sign, digits, decimal comma


def parse_short_answer(text: str | None, unit: str | None = None) -> ParsedNumber | None:
    """Trim, drop the unit, spaces and a leading `+`; `,` or `.` is the decimal mark and `−` a minus."""
    if text is None:
        return None
    s = str(text).strip().replace("−", "-").replace(" ", " ")
    if unit and unit.strip() and s.lower().endswith(unit.strip().lower()):
        s = s[: -len(unit.strip())].strip()
    s = s.replace(" ", "")
    m = _NUMBER.match(s)
    if not m:
        return None
    sign, whole, frac = m.group(1), m.group(2), m.group(3) or ""
    if not whole and not frac:
        return None
    try:
        value = Decimal(("-" if sign == "-" else "") + (whole or "0") + (f".{frac}" if frac else ""))
    except InvalidOperation:
        return None
    return ParsedNumber(value, ("-" if sign == "-" else "") + (whole or "0") + (f",{frac}" if frac else ""))


def short_answer_matches(text: str | None, key: dict[str, Any]) -> bool:
    """Correct iff a number that fits the sheet (`max_chars`) and equals the key at its precision (`1,30` = `1,3`,
    `1,27` is not `1,3`), or lies within the item's explicit `tolerance`."""
    unit = key.get("unit")
    given = parse_short_answer(text, unit)
    expected = parse_short_answer(key.get("answer"), unit)
    if given is None or expected is None:
        return False
    max_chars = key.get("max_chars")
    if max_chars is not None and len(given.sheet) > int(max_chars):
        return False
    tol = float(key.get("tolerance") or 0.0)
    if tol > 0.0:
        return abs(float(given.value - expected.value)) <= tol + 1e-12
    return given.value == expected.value


# ---- items -------------------------------------------------------------------------------------


# ---- course quiz items (same semantics as apps/app `lib/quiz.ts`) -----------------------------------

_LOOSE = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)(e[+-]?\d+)?$")


def parse_loose_number(text: str) -> float | None:
    """`0,5` = `0.5`, spaces ignored, `4.10^5`-style spellings are matched as text only; `4e5` and `4×10^5` are numbers."""
    t = re.sub(r"\s+", "", str(text).strip().lower()).replace(",", ".")
    t = t.replace("×10^", "e").replace("·10^", "e").replace("*10^", "e")
    if not _LOOSE.match(t):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).strip().lower())


def course_short_answer_matches(text: str | None, accepted: list[str], tolerance: float | None = None) -> bool:
    """Matches one accepted spelling as text or, when both are numbers, as a number; `tolerance` is relative
    (0.01 = within 1 %), absolute against an accepted 0."""
    v = _norm(text or "")
    if not v:
        return False
    vn = parse_loose_number(v)
    for a in accepted:
        if _norm(a) == v:
            return True
        an = parse_loose_number(a)
        if vn is None or an is None:
            continue
        if vn == an:
            return True
        if tolerance and abs(vn - an) <= tolerance * (1.0 if an == 0 else abs(an)):
            return True
    return False


def score_item(doc: dict[str, Any], answer: str | None, max_points: float = 1.0) -> ItemScore:
    """Score one answer against the question document (the key never leaves the gateway)."""
    blank = answer is None or not str(answer).strip()
    t = doc["type"]
    if t == "TRUE_FALSE_GROUP":
        return score_true_false(answer, [bool(s["truth"]) for s in doc["statements"]], max_points)
    if blank:
        return ItemScore(None, 0.0, max_points)
    if t == "TAP_COUNT":
        try:
            ok = int(str(answer).strip()) == int(doc["answer_key"]["count"])
        except ValueError:
            ok = False
    elif t == "SHORT_ANSWER" and "accepted" in doc["short_answer"]:
        sa = doc["short_answer"]
        ok = course_short_answer_matches(answer, [str(a) for a in sa["accepted"]], sa.get("tolerance"))
    elif t == "SHORT_ANSWER":
        ok = short_answer_matches(answer, doc["short_answer"])
    else:
        ok = str(answer).strip().upper() == str(doc["answer_key"]["correct_option_id"]).upper()
    return ItemScore(ok, max_points if ok else 0.0, max_points)


def correct_answer_text(doc: dict[str, Any]) -> str:
    """The key as a string in the same encoding as answers (shown after the learner answered)."""
    t = doc["type"]
    if t == "TRUE_FALSE_GROUP":
        return encode_truths([bool(s["truth"]) for s in doc["statements"]])
    if t == "SHORT_ANSWER":
        sa = doc["short_answer"]
        if "accepted" in sa:
            return str(sa["accepted"][0])
        return str(sa["answer"]) + (f" {sa['unit']}" if sa.get("unit") else "")
    if t == "TAP_COUNT":
        return str(doc["answer_key"]["count"])
    return str(doc["answer_key"]["correct_option_id"])


def policy_for(types: set[str], profile_policy: str | None = None) -> str:
    if profile_policy == SCORING_V2 or types - {"SINGLE_CHOICE"}:
        return SCORING_V2
    return MCQ_V1


def scaled(raw: float, max_raw: float, max_score: float = 10.0) -> float:
    if max_raw <= 0:
        return 0.0
    return round(min(max_score, max(0.0, raw / max_raw * max_score)) + 1e-9, 2)
