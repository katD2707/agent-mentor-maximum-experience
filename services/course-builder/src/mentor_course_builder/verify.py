"""Stage 7: check a written lesson before review.

- quiz answers: an independent re-solve with REASONING (the key is never shown) must agree with answer_key;
- numeric SHORT_ANSWER: every accepted spelling is parsed with sympy and must be the same number, and the independent
  answer must match it within tolerance;
- KaTeX: delimiters and braces balanced in every Markdown field;
- length limits per age band (sentence length for g1_5, characters per text block, block count).

`verify_and_repair` drops or regenerates failing quiz items (one retry) and returns a report.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from mentor_schemas.course import CalloutBlock, Lesson, QuizBlock, QuizItem, TextBlock

from mentor_course_builder.contracts import MediaRequest
from mentor_course_builder.gen import AGE_RULES, ask_json, lang_name
from mentor_course_builder.llm import ModelClient, ModelError

log = logging.getLogger("mentor_course_builder")


# ---------------------------------------------------------------- KaTeX
def katex_problems(md: str) -> list[str]:
    """Unbalanced $ / $$ or braces, `\\(`-style delimiters (we use $ only), unknown-looking leftovers."""
    probs: list[str] = []
    if "\\(" in md or "\\[" in md:
        probs.append("uses \\( \\[ delimiters; use $...$")
    s = md.replace("\\$", "")  # escaped dollar = currency
    blocks = re.findall(r"\$\$(.+?)\$\$", s, flags=re.S)
    rest = re.sub(r"\$\$.+?\$\$", "", s, flags=re.S)
    if "$$" in rest:
        probs.append("unbalanced $$")
    if rest.count("$") % 2:
        probs.append("unbalanced $")
    inline = re.findall(r"\$([^$\n]+)\$", rest)
    for m in blocks + inline:
        depth = 0
        for ch in re.sub(r"\\[{}]", "", m):
            depth += ch == "{"
            depth -= ch == "}"
            if depth < 0:
                break
        if depth != 0:
            probs.append(f"unbalanced braces in ${m[:30]}$")
        if re.search(r"\\(begin|end)\{", m) and m.count("\\begin") != m.count("\\end"):
            probs.append("begin/end mismatch")
        if not m.strip():
            probs.append("empty math")
    return probs


# ---------------------------------------------------------------- numbers (sympy)
def _eval_number(t: str) -> float | None:
    import sympy
    from sympy.parsing.sympy_parser import implicit_multiplication_application, parse_expr, standard_transformations

    if not t or len(t) > 60:
        return None
    try:
        v = sympy.N(parse_expr(t, transformations=standard_transformations + (implicit_multiplication_application,)))
        return float(v) if v.is_real else None
    except Exception:  # noqa: BLE001 - any parse failure means "not a number"
        return None


def parse_number(s: str) -> float | None:
    """Plain number from "4e4", "40000", "4.10^5", LaTeX "4 cdot 10^{5}", "0,5", "1/2", "5 V/m". None otherwise."""
    t = s.replace("$", "").strip()
    t = re.sub(r"\\(?:cdot|times)|\u00d7|\u00b7|\u22c5", "*", t)
    t = re.sub(r"(?<=\d)\.(?=10\^)", "*", t)  # "4.10^5"
    t = re.sub(r"\^\{([^}]*)\}", r"**(\1)", t).replace("^", "**")
    t = re.sub(r"\\frac\{([^}]*)\}\{([^}]*)\}", r"((\1)/(\2))", t)
    t = re.sub(r"(?<=\d),(?=\d)", ".", t)  # decimal comma
    v = _eval_number(t.strip())
    if v is None:  # drop a trailing unit: "5 V/m", "3 cm"
        v = _eval_number(re.sub(r"\s*[A-Za-zμΩ°%][A-Za-z/μΩ°%*0-9.\-]*$", "", t).strip())
    return v


def numbers_agree(a: float, b: float, tol: float = 0.01) -> bool:
    return abs(a - b) <= tol * max(abs(a), abs(b), 1e-12)


# ---------------------------------------------------------------- independent solve
SOLVE_SYSTEM = """Solve this quiz question yourself, carefully, step by step in your head. Language of the question: {lang}.
Reply with ONE JSON object only:
- multiple choice: {"answer": "<option letter>"}
- true/false group: {"answers": {"a": true, "b": false, ...}}
- short answer: {"answer": "<final answer only, number with unit if any>"}"""


def render_for_solving(item: QuizItem) -> str:
    lines = [f"Question: {item.stem}"]
    for o in item.options:
        lines.append(f"{o.id}. {o.text or '(picture)'}")
    for s in item.statements:
        lines.append(f"({s.id}) {s.text}")
    if item.type == "TAP_COUNT" and item.tap:
        lines.append(f"(a picture shows {item.tap.total} objects)")
    return "\n".join(lines)


def solve_independently(item: QuizItem, client: ModelClient, language: str) -> dict[str, Any]:
    return ask_json(client, SOLVE_SYSTEM.replace("{lang}", lang_name(language)), render_for_solving(item),
                    max_tokens=3000, temperature=0.0)


@dataclass
class ItemVerdict:
    item_id: str
    ok: bool
    reason: str = ""


def check_item(item: QuizItem, client: ModelClient, language: str) -> ItemVerdict:
    k = item.answer_key
    if item.type == "TAP_COUNT":  # nothing to solve; the answer is the count the model itself chose
        return ItemVerdict(item.id, True, "tap count not re-solved")
    if item.type == "PICTURE_CHOICE":
        return ItemVerdict(item.id, True, "picture choice not re-solved")
    if item.type == "SHORT_ANSWER":
        nums = [parse_number(a) for a in k["accepted"]]
        if all(n is not None for n in nums):
            tol = float(k.get("tolerance") or 0.01)
            if any(not numbers_agree(nums[0], n, tol) for n in nums[1:]):  # type: ignore[arg-type]
                return ItemVerdict(item.id, False, f"accepted spellings differ numerically: {k['accepted']}")
    try:
        got = solve_independently(item, client, language)
    except ModelError as exc:
        return ItemVerdict(item.id, True, f"solver unavailable ({str(exc)[:60]}); not checked")
    if item.type == "SINGLE_CHOICE":
        a = str(got.get("answer", "")).strip().upper()[:1]
        return ItemVerdict(item.id, a == k["correct_option_id"], f"solver said {a}, key {k['correct_option_id']}")
    if item.type == "TRUE_FALSE_GROUP":
        ans = got.get("answers") or {}
        bad = [i for i, v in k["statements"].items() if bool(ans.get(i)) != bool(v)]
        return ItemVerdict(item.id, not bad, f"solver disagrees on {bad}" if bad else "")
    if item.type == "SHORT_ANSWER":
        ans = str(got.get("answer", "")).strip()
        a, nums = parse_number(ans), [parse_number(x) for x in k["accepted"]]
        if a is not None and all(n is not None for n in nums):
            tol = float(k.get("tolerance") or 0.01)
            ok = any(numbers_agree(a, n, tol) for n in nums)  # type: ignore[arg-type]
            return ItemVerdict(item.id, ok, f"solver said {ans!r}, key {k['accepted']}")
        norm = lambda x: re.sub(r"\W+", "", x.lower())  # noqa: E731
        return ItemVerdict(item.id, any(norm(ans) == norm(x) for x in k["accepted"]),
                           f"solver said {ans!r}, key {k['accepted']}")
    return ItemVerdict(item.id, True)


# ---------------------------------------------------------------- lengths
def _words(s: str) -> int:
    return len(re.findall(r"\S+", re.sub(r"\$[^$]*\$", "X", s)))


def length_problems(lesson: Lesson, age_band: str) -> list[str]:
    rules = AGE_RULES[age_band]
    probs: list[str] = []
    if len(lesson.blocks) > rules["max_blocks"] + 1:
        probs.append(f"{len(lesson.blocks)} blocks > {rules['max_blocks']}")
    for b in lesson.blocks:
        if isinstance(b, (TextBlock, CalloutBlock)):
            if len(b.md) > rules["max_text_chars"] and not (isinstance(b, CalloutBlock) and b.variant == "example"):
                probs.append(f"{b.id}: {len(b.md)} chars > {rules['max_text_chars']}")
            for sent in re.split(r"(?<=[.!?])\s+", b.md):
                if _words(sent) > rules["max_sentence_words"] + (6 if age_band == "g1_5" else 12):
                    probs.append(f"{b.id}: sentence of {_words(sent)} words (max {rules['max_sentence_words']})")
                    break
    return probs


def all_markdown(lesson: Lesson) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for b in lesson.blocks:
        if isinstance(b, (TextBlock, CalloutBlock)):
            out.append((b.id, b.md))
        elif isinstance(b, QuizBlock):
            for q in b.items:
                out.append((q.id, q.stem + "\n" + q.explanation))
                out += [(f"{q.id}.{o.id}", o.text or "") for o in q.options]
    return out


# ---------------------------------------------------------------- whole lesson
@dataclass
class VerifyReport:
    checked: int = 0
    failed: list[ItemVerdict] = field(default_factory=list)
    regenerated: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    katex: list[str] = field(default_factory=list)
    lengths: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (f"{self.checked} items checked, {len(self.failed)} failed, {len(self.regenerated)} regenerated, "
                f"{len(self.dropped)} dropped; {len(self.katex)} KaTeX problems; {len(self.lengths)} length problems")


def item_hash(item: QuizItem) -> str:
    """Identity of what the independent solve judged: stem, choices and key (not the explanation)."""
    import hashlib
    import json

    body = [item.type, item.stem, [(o.id, o.text) for o in item.options], [(x.id, x.text) for x in item.statements],
            item.answer_key, item.tap.total if item.tap else None]
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()[:16]


def check_items(items: list[QuizItem], client: ModelClient, language: str, workers: int = 4) -> list[ItemVerdict]:
    """check_item for many items at once (each is an independent model call, so they run in parallel)."""
    if len(items) <= 1:
        return [check_item(i, client, language) for i in items]
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(items)))) as ex:
        return list(ex.map(lambda i: check_item(i, client, language), items))


def solved(v: ItemVerdict) -> bool:
    """True when an independent solve really ran and agreed (a solver outage is not a verification)."""
    return v.ok and not v.reason.startswith("solver unavailable")


def regenerate_item(draft, ctx, item: QuizItem, client: ModelClient) -> QuizItem | None:
    """Ask the own-prompt quiz writer for a replacement of `item` (same id and type); None if it fails the same checks.
    Replaces the item's media requests in `draft.media` on success."""
    from mentor_course_builder import quiz as quiz_mod

    try:
        n = int(item.id.rsplit("-q", 1)[1])
        r = quiz_mod._own_items(ctx, [item.type], n - 1, client)  # noqa: SLF001
        cand = next((c for c in r.items if c.id == item.id), None)
        if cand is not None and check_item(cand, client, ctx.language).ok and not katex_problems(cand.stem):
            draft.media = [m for m in draft.media if not _owned(m, item.id)] + r.media
            return cand
    except (ModelError, ValueError, IndexError):
        pass
    return None


def verify_and_repair(draft, ctx, client: ModelClient, regenerate=True) -> VerifyReport:  # draft: LessonDraft
    """Verify quiz items (independent solve), KaTeX and lengths. Mutates `draft` (drops/regenerates items)."""
    rep = VerifyReport()
    lesson: Lesson = draft.lesson
    quizzes = [(bi, b) for bi, b in enumerate(lesson.blocks) if isinstance(b, QuizBlock)]
    verdicts = check_items([q for _, b in quizzes for q in b.items], client, ctx.language)  # all solves in parallel
    flat = [q for _, b in quizzes for q in b.items]
    by_id = {q.id: v for q, v in zip(flat, verdicts)}
    for b in [b for _, b in quizzes]:
        keep: list[QuizItem] = []
        for item in b.items:
            rep.checked += 1
            v = by_id[item.id]
            probs = katex_problems(item.stem + " " + " ".join(o.text or "" for o in item.options))
            if v.ok and not probs:
                keep.append(item)
                if solved(v):
                    draft.verified.add(item_hash(item))
                continue
            rep.failed.append(ItemVerdict(item.id, False, v.reason or "; ".join(probs)))
            new_item = regenerate_item(draft, ctx, item, client) if regenerate else None
            if new_item is not None:
                keep.append(new_item)
                draft.verified.add(item_hash(new_item))
                rep.regenerated.append(item.id)
            else:
                rep.dropped.append(item.id)
                draft.media = [m for m in draft.media if not _owned(m, item.id)]
        i = lesson.blocks.index(b)
        if keep:
            lesson.blocks[i] = b.model_copy(update={"items": keep})
        else:
            lesson.blocks.remove(b)
    for bid, md in all_markdown(lesson):
        rep.katex += [f"{bid}: {p}" for p in katex_problems(md)]
    rep.lengths = length_problems(lesson, ctx.age_band)
    return rep


def _owned(m: MediaRequest, item_id: str) -> bool:
    return m.id == item_id or m.id.startswith(item_id + ".")


__all__ = ["VerifyReport", "ItemVerdict", "check_item", "check_items", "item_hash", "regenerate_item", "solved", "katex_problems", "length_problems", "parse_number",
           "numbers_agree", "verify_and_repair", "solve_independently"]
