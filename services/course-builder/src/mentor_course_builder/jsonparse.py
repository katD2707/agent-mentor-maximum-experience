"""Robust parsing of JSON emitted by a vision model (code fences, raw LaTeX backslashes, truncation)."""

import json
import re
from typing import Any

# LaTeX commands whose first letter collides with a valid JSON escape (\b \f \n \r \t): a model that forgot to
# double the backslash would otherwise silently turn `\frac` into form-feed + "rac".
_LATEX_AMBIGUOUS = {
    "beta", "bar", "binom", "begin", "bigl", "bigr", "big", "bmod", "boldsymbol", "bullet", "backslash", "because",
    "frac", "forall", "flat", "footnote",
    "neq", "nu", "nabla", "ne", "not", "newline", "neg", "nolimits", "notin", "nmid",
    "rightarrow", "right", "rho", "rangle", "rceil", "rfloor", "Rightarrow", "ref", "renewcommand", "rm",
    "theta", "tau", "times", "text", "tilde", "tan", "to", "top", "triangle", "tfrac", "textbf", "textit", "tanh",
    "Theta",
}


def _fix_backslashes(s: str) -> str:
    out: list[str] = []
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c != "\\":
            out.append(c)
            i += 1
            continue
        nxt = s[i + 1] if i + 1 < n else ""
        if nxt == "\\":  # already an escaped backslash: keep the pair
            out.append("\\\\")
            i += 2
            continue
        if nxt == '"' or nxt == "/":
            out.append(c + nxt)
            i += 2
            continue
        run = re.match(r"[A-Za-z]+", s[i + 1 :])
        word = run.group(0) if run else ""
        if nxt == "u" and re.match(r"u[0-9a-fA-F]{4}", s[i + 1 : i + 6]):
            out.append(s[i : i + 6])
            i += 6
        elif nxt in "bfnrt" and word not in _LATEX_AMBIGUOUS:
            out.append(c + nxt)  # genuine JSON escape (\n, \t ...)
            i += 2
        else:  # LaTeX command or any invalid escape: keep the backslash literally
            out.append("\\\\")
            i += 1
    return "".join(out)


def _extract_object(s: str) -> str | None:
    start = s.find("{")
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return s[start:]  # unterminated (truncated output)


def _try(s: str) -> dict[str, Any] | None:
    try:
        v = json.loads(s, strict=False)
    except ValueError:
        return None
    return v if isinstance(v, dict) else None


def _regex_salvage(s: str) -> dict[str, Any] | None:
    out: dict[str, Any] = {}
    m = re.search(r'"readable"\s*:\s*(true|false)', s, re.IGNORECASE)
    if m:
        out["readable"] = m.group(1).lower() == "true"
    m = re.search(r'"readable_fraction"\s*:\s*([0-9.]+)', s)
    if m:
        try:
            out["readable_fraction"] = float(m.group(1).rstrip("."))
        except ValueError:
            pass
    for key in ("reason_vi", "reason_en"):
        m = re.search(rf'"{key}"\s*:\s*"((?:[^"\\]|\\.)*)"', s, re.DOTALL)
        if m:
            out[key] = m.group(1)
    m = re.search(r'"text"\s*:\s*"(.*)', s, re.DOTALL)
    if m:
        body = m.group(1)
        end = re.search(r'"\s*[,}]\s*(?:"\w+"\s*:|\}|$)', body)
        body = body[: end.start()] if end else body
        out["text"] = _fix_backslashes(body).encode("utf-8", "replace").decode("utf-8")
        try:
            out["text"] = json.loads('"' + out["text"].replace("\n", "\n").replace('"', '\\"') + '"')
        except ValueError:
            pass
    return out or None


def parse_model_json(raw: str) -> dict[str, Any]:
    """Parse a JSON object out of model output. Raises ValueError when nothing usable is found."""
    s = raw.strip()
    fence = re.search(r"```(?:json|JSON)?\s*(.*?)```", s, re.DOTALL)
    if fence:
        s = fence.group(1).strip()
    else:
        s = re.sub(r"^```(?:json)?", "", s).strip()  # unterminated fence
    obj = _extract_object(s)
    if obj is None:
        raise ValueError("no JSON object in model output")
    for cand in (_fix_backslashes(obj), obj, re.sub(r",\s*([}\]])", r"\1", _fix_backslashes(obj))):
        v = _try(cand)
        if v is not None:
            return v
    fixed = _fix_backslashes(obj)
    for tail in ('"}', "}", '"]}', '""}'):  # truncated output: try to close it
        v = _try(fixed + tail)
        if v is not None:
            return v
    v = _regex_salvage(obj)
    if v is not None:
        return v
    raise ValueError("could not parse model JSON")
