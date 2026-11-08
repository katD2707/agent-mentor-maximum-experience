"""Real KaTeX parse of every formula of a course, in ONE node process (the app renders with the same library).

`parse_errors(spans)` -> {index: message} for the spans KaTeX rejects. The katex package is looked up in
$KATEX_DIR, then `node_modules/katex` (or `apps/app/node_modules/katex`) above the cwd and above this file. When node or
katex is missing it returns None and callers keep the regex check of verify.katex_problems.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger("mentor_course_builder")

_JS = r"""
const katex = require(process.argv[1]);
const spans = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const out = {};
spans.forEach((s, i) => {
  try { katex.renderToString(s.tex, {displayMode: !!s.display, throwOnError: true, strict: 'ignore'}); }
  catch (e) { out[i] = String(e.message || e).slice(0, 160); }
});
process.stdout.write(JSON.stringify(out));
"""

_MATH = re.compile(r"\$\$(.+?)\$\$|\$([^$\n]+)\$", re.S)


def find_katex() -> Path | None:
    explicit = os.environ.get("KATEX_DIR")
    if explicit and (Path(explicit) / "package.json").is_file():
        return Path(explicit)
    for start in (Path.cwd(), Path(__file__).resolve()):
        for d in (start, *start.parents):
            for rel in ("node_modules/katex", "apps/app/node_modules/katex"):
                if (d / rel / "package.json").is_file():
                    return d / rel
    return None


def math_spans(md: str) -> list[dict]:
    """[{"tex", "display"}] for every $...$ / $$...$$ of a Markdown text (escaped \\$ is currency, not math)."""
    s = md.replace("\\$", "  ")
    return [{"tex": (m.group(1) if m.group(1) is not None else m.group(2)).strip(), "display": m.group(1) is not None}
            for m in _MATH.finditer(s)]


def parse_errors(spans: list[dict], timeout_s: float = 60.0) -> dict[int, str] | None:
    if not spans:
        return {}
    node, kdir = shutil.which("node"), find_katex()
    if not node or not kdir:
        return None
    try:
        p = subprocess.run([node, "-e", _JS, str(kdir).replace("\\", "/")], input=json.dumps(spans).encode("utf-8"),
                           capture_output=True, timeout=timeout_s)
        if p.returncode != 0:
            log.warning("katex check failed: %s", p.stderr.decode("utf-8", "replace")[-200:])
            return None
        return {int(k): v for k, v in json.loads(p.stdout.decode("utf-8")).items()}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def check_texts(texts: dict[str, str]) -> dict[str, list[str]]:
    """{text id: [problems]} using KaTeX when available, else the regex check of verify.py."""
    from mentor_course_builder.verify import katex_problems

    flat: list[tuple[str, dict]] = [(k, s) for k, t in texts.items() for s in math_spans(t)]
    got = parse_errors([s for _, s in flat])
    out: dict[str, list[str]] = {}
    if got is None:
        for k, t in texts.items():
            probs = katex_problems(t)
            if probs:
                out[k] = probs
        return out
    for k, t in texts.items():  # delimiters outside any span ($ left open, \( \[ ) KaTeX never sees
        probs = [p for p in katex_problems(t) if p.startswith(("unbalanced $", "uses \\("))]
        if probs:
            out[k] = probs
    for i, (k, s) in enumerate(flat):
        if i in got:
            out.setdefault(k, []).append(f"KaTeX: {got[i]} in ${s['tex'][:40]}$")
    return out
