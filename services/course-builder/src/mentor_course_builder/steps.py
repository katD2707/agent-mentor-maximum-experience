"""Stepped-lesson helpers (CONTRACTS 16.2): checks of the new kinds and the placement of questions between steps.

- `eval_expr` / `interactive_problem`: the "Kéo sơ đồ" block must evaluate over its range and its target must be reachable
  at some x on the step grid (what the learner can actually drag to);
- `step_item_problem`: FILL_TILES / MATCH_PAIRS / ORDER_STEPS answer keys consistent with their parts (no model);
- `recall_problem`: a "Nhớ lại" block has real prompts and answers;
- `place_quiz`: one question per quiz block, a question every 2-3 steps, the recall block last;
- `spread_difficulty`: difficulty 1..4 over the course by lesson position.
"""

from __future__ import annotations

import ast
import math
import re
from typing import Any

from mentor_schemas.course import GAP, InteractiveBlock, QuizBlock, QuizItem, RecallBlock

_FUNCS = {"sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "exp": math.exp, "log": math.log, "abs": abs}
_CONSTS = {"pi": math.pi}


def _ev(node: ast.AST, x: float) -> float:
    if isinstance(node, ast.Expression):
        return _ev(node.body, x)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id == "x":
            return x
        if node.id in _CONSTS:
            return _CONSTS[node.id]
        raise ValueError(f"unknown name {node.id}")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        v = _ev(node.operand, x)
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.BinOp):
        a, b = _ev(node.left, x), _ev(node.right, x)
        if isinstance(node.op, ast.Add):
            return a + b
        if isinstance(node.op, ast.Sub):
            return a - b
        if isinstance(node.op, ast.Mult):
            return a * b
        if isinstance(node.op, ast.Div):
            return a / b
        if isinstance(node.op, ast.Pow):
            return a ** b
        raise ValueError("operator not allowed")
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS and len(node.args) == 1:
        return float(_FUNCS[node.func.id](_ev(node.args[0], x)))
    raise ValueError("expression not allowed")


def eval_expr(expr: str, x: float) -> float:
    """y = f(x) for the app's expression language (+ - * / ^, sqrt, sin, cos, exp, log, pi). Raises ValueError."""
    if len(expr) > 200:
        raise ValueError("expression too long")
    src = re.sub(r"(?<=[\d)x])\s*(?=[x(])", "*", expr.replace("^", "**"))  # "2x", "(a)(b)" -> implicit product
    try:
        v = _ev(ast.parse(src, mode="eval"), x)
    except (SyntaxError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError(str(exc)) from exc
    if isinstance(v, complex) or not math.isfinite(v):
        raise ValueError("not a finite number")
    return v


def interactive_problem(b: InteractiveBlock) -> str | None:
    """None when the drag block works: expr evaluates on the range and some x on the step grid hits the target."""
    n = int(math.floor((b.x_max - b.x_min) / b.x_step + 1e-9))
    if n < 1 or n > 100000:
        return "the step does not fit the range"
    best = math.inf
    for k in range(n + 1):
        x = b.x_min + k * b.x_step
        try:
            y = eval_expr(b.expr, x)
        except (ValueError, TypeError) as exc:
            return f"the formula cannot be computed at x={x:g} ({str(exc)[:40]})"
        best = min(best, abs(y - b.target_y))
    if best > b.tolerance:
        return "the target value cannot be reached by dragging"
    try:
        if abs(eval_expr(b.expr, b.x_start) - b.target_y) <= b.tolerance:
            return "the start position already meets the target"
    except ValueError:
        pass
    return None


def step_item_problem(q: QuizItem) -> str | None:
    """Consistency of FILL_TILES / MATCH_PAIRS / ORDER_STEPS items (the schema checks shapes; this checks sense)."""
    if q.type not in ("FILL_TILES", "MATCH_PAIRS", "ORDER_STEPS"):
        return None
    texts = [p.text.strip().lower() for p in q.parts]
    if any(not t for t in texts):
        return "a tile has no text"
    k = q.answer_key
    if q.type == "FILL_TILES":
        if q.stem.count(GAP) != len(k.get("gaps") or []):
            return "gaps and {{gap}} marks differ"
        if len(q.parts) <= len(set(k["gaps"])):
            return "no spare tile to choose from"
    elif q.type == "MATCH_PAIRS":
        if len(k.get("pairs") or {}) < 2:
            return "fewer than two pairs"
    elif len(q.parts) < 3 and q.type == "ORDER_STEPS":
        return "fewer than three steps to order"
    if len(set(texts)) != len(texts) and q.type != "FILL_TILES":
        return "two parts have the same text"
    return None


def recall_problem(b: RecallBlock) -> str | None:
    for it in b.items:
        if not it.prompt.strip() or not it.answer.strip():
            return "a recall item has no prompt or no answer"
    return None


def spread_difficulty(items: list[QuizItem], lesson_index: int, lessons_total: int) -> list[QuizItem]:
    """Difficulty 1..4 over the course: a lesson's base grows with its position; items around it vary by one."""
    base = 1 + round(3 * lesson_index / max(1, lessons_total - 1)) if lessons_total > 1 else 2
    wave = (-1, 0, 1, 0)
    return [q.model_copy(update={"difficulty": max(1, min(4, base + wave[i % 4]))}) for i, q in enumerate(items)]


def place_quiz(content: list[Any], items: list[QuizItem], lesson_id: str) -> list[Any]:
    """Content steps (text, callout, image, video, interactive, recall) with one QuizBlock per item between them: a
    question every 2-3 steps. A recall block, if any, stays last. Quiz blocks are `<lesson>-k<n>` (content keeps
    `<lesson>-b<n>`, which media requests are keyed by)."""
    recall = [b for b in content if isinstance(b, RecallBlock)]
    body = [b for b in content if not isinstance(b, RecallBlock) and not isinstance(b, QuizBlock)]
    out: list[Any] = []
    n, m = len(body), len(items)
    nxt = 0
    for i, b in enumerate(body):
        out.append(b)
        while nxt < m and (i + 1) * m >= (nxt + 1) * n and (i + 1 >= 2 or n < 2):
            out.append(QuizBlock(id=f"{lesson_id}-k{nxt + 1}", items=[items[nxt]]))
            nxt += 1
    for j in range(nxt, m):
        out.append(QuizBlock(id=f"{lesson_id}-k{j + 1}", items=[items[j]]))
    return out + recall


__all__ = ["eval_expr", "interactive_problem", "step_item_problem", "recall_problem", "spread_difficulty", "place_quiz"]
