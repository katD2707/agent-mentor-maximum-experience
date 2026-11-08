"""Shared helpers of the content stage: JSON-out model calls, slugs, source text, age-band rules."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from mentor_schemas import ModelAlias

from mentor_course_builder.intake import IntakeResult
from mentor_course_builder.jsonparse import parse_model_json
from mentor_course_builder.llm import ModelClient, ModelError


def slugify(text: str, fallback: str = "x", max_len: int = 40) -> str:
    t = text.replace("đ", "d").replace("Đ", "D")
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:max_len].strip("-")
    return t or fallback


def unique_id(base: str, taken: set[str]) -> str:
    i, cand = 2, base
    while cand in taken:
        cand = f"{base}-{i}"
        i += 1
    taken.add(cand)
    return cand


def ask_json(client: ModelClient, system: str, user: str, *, alias: ModelAlias = ModelAlias.REASONING,
             max_tokens: int = 8000, temperature: float = 0.2, retries: int = 1) -> dict[str, Any]:
    """One model call that must return a JSON object; re-asks once when the reply does not parse."""
    msgs: list[dict[str, Any]] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    last = ""
    for _ in range(retries + 1):
        raw = client.complete(alias, msgs, max_tokens=max_tokens, temperature=temperature)
        try:
            return parse_model_json(raw)
        except ValueError as exc:
            last = str(exc)
            msgs = msgs + [{"role": "assistant", "content": raw[:2000]},
                           {"role": "user", "content": "That was not valid JSON. Reply with the JSON object only."}]
    raise ModelError(f"model did not return JSON: {last}")


def ask_text(client: ModelClient, system: str, user: str, *, alias: ModelAlias = ModelAlias.REASONING,
             max_tokens: int = 4000, temperature: float = 0.4) -> str:
    return client.complete(alias, [{"role": "system", "content": system}, {"role": "user", "content": user}],
                           max_tokens=max_tokens, temperature=temperature).strip()


def page_label(source_file: str, index: int) -> str:
    return f"{source_file.replace(chr(92), '/').rsplit('/', 1)[-1]}#{index}"


def source_pages(intake: IntakeResult) -> list[tuple[str, str]]:
    """[(page label, text)] for every page with text (page text, transcript, or the quality check's OCR)."""
    checks = {(c.source_file, c.page): c.text for c in intake.checks if c.text}
    out: list[tuple[str, str]] = []
    for m in intake.materials:
        for p in m.pages:
            text = p.text or p.transcript or checks.get((p.source_file, p.index)) or ""
            if text.strip():
                out.append((page_label(p.source_file, p.index), text.strip()))
    return out


def pages_block(pages: list[tuple[str, str]], max_chars: int = 60000) -> str:
    parts, used = [], 0
    for label, text in pages:
        chunk = f"[{label}]\n{text}\n"
        if used + len(chunk) > max_chars:
            chunk = chunk[: max(0, max_chars - used)]
        parts.append(chunk)
        used += len(chunk)
        if used >= max_chars:
            break
    return "\n".join(parts)


# Rules per age band (REQUIREMENTS-PLAN §3.8). max_sentence_words is a soft cap checked by verify.py.
AGE_RULES: dict[str, dict[str, Any]] = {
    "g1_5": {"max_sentence_words": 9, "max_text_chars": 160, "max_blocks": 10, "quiz_items": 3,
             "label": "primary school (grades 1-5)"},
    "g6_9": {"max_sentence_words": 16, "max_text_chars": 600, "max_blocks": 9, "quiz_items": 3,
             "label": "lower secondary (grades 6-9)"},
    "g10_12": {"max_sentence_words": 24, "max_text_chars": 900, "max_blocks": 9, "quiz_items": 4,
               "label": "upper secondary (grades 10-12)"},
    "uni": {"max_sentence_words": 40, "max_text_chars": 3500, "max_blocks": 10, "quiz_items": 3,
            "label": "university"},
}


def lang_name(lang: str) -> str:
    return {"vi": "Vietnamese", "en": "English"}.get(lang, lang)


def load_intake(directory: str | Path) -> IntakeResult:
    """Read pages.json + checks.json written by `mcb intake` back into an IntakeResult."""
    from mentor_course_builder.models import Material, Page, PageCheck

    d = Path(directory)
    mats = [Material(source_file=m["source_file"], kind=m["kind"], pages=[Page(**p) for p in m.get("pages", [])],
                     notes=m.get("notes", [])) for m in json.loads((d / "pages.json").read_text("utf-8"))]
    cf = d / "checks.json"
    checks = [PageCheck(**c) for c in json.loads(cf.read_text("utf-8"))] if cf.is_file() else []
    return IntakeResult(materials=mats, checks=checks)
