"""Stage 6 (R6): make lesson prose sound like a real teacher wrote it.

Two parts:
- `lint(text)`: deterministic detector of AI tells (English and Vietnamese). Used before and after the rewrite to
  report hits, and by verify.py.
- `humanize_texts(...)`: one REASONING call per lesson that rewrites only the prose, guarded by `preserved_ok`
  (numbers, math, names and units must survive; otherwise the original text is kept).

Rules distilled from (both MIT-licensed):
- the local skill `unslop` (claytonkim, v2.3.0): references/core-contract.md, taboo-phrases.md, fact-preservation.md
  (smallest repair, preserve facts/quantities/names, delete empty framing instead of substituting filler);
- github.com/jooray/humanizer (MIT): its pattern list (inflated significance, promotional language, negative
  parallelisms, rule of three, em dashes, emojis, chatbot artifacts, filler and hedging, generic conclusions).
The Vietnamese list below is ours. Our own regexes only; no text of either skill is copied into the product.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from mentor_schemas import ModelAlias

from mentor_course_builder.gen import ask_json, lang_name
from mentor_course_builder.llm import ModelClient, ModelError


@dataclass(frozen=True)
class Hit:
    rule: str
    text: str
    pos: int


_I = re.IGNORECASE
# (rule name, compiled regex). Vietnamese tells first.
RULES: list[tuple[str, re.Pattern[str]]] = [(n, re.compile(p, _I)) for n, p in [
    # ---- Vietnamese
    ("vi.lets_explore", r"\bhãy cùng (?:nhau )?(?:khám phá|tìm hiểu|bắt đầu|tìm|đi sâu|cùng)"),
    ("vi.lets_go", r"\bchúng ta (?:hãy )?cùng (?:nhau )?(?:khám phá|tìm hiểu|đi sâu)"),
    ("vi.not_only_but_also", r"\bkhông chỉ\b[^.!?\n]{1,80}\bmà còn\b"),
    ("vi.plays_role", r"đóng vai trò (?:quan trọng|then chốt|thiết yếu|cốt lõi|chủ chốt|to lớn)"),
    ("vi.in_summary", r"(?:^|[.!?]\s+|\n)\s*(?:tóm lại|nói tóm lại|tựu trung|tổng kết lại|nhìn chung)\s*,"),
    ("vi.important_is", r"\b(?:điều quan trọng là|điều đáng chú ý là|điều đáng nói là|cần lưu ý rằng|cần nhấn mạnh rằng)"),
    ("vi.today_world", r"\b(?:trong thế giới (?:ngày nay|hiện đại|hiện nay)|trong bối cảnh (?:hiện nay|ngày nay|hiện đại)|"
                       r"trong thời đại (?:ngày nay|hiện nay|công nghệ))"),
    ("vi.inflated", r"\b(?:không ngừng (?:phát triển|đổi mới)|nền tảng vững chắc|bức tranh toàn cảnh|hành trình khám phá|"
                    r"mở ra (?:cánh cửa|chân trời|những cơ hội)|chìa khóa (?:vàng|để mở)|tấm thảm|bước đệm quan trọng|"
                    r"đa dạng và phong phú|phong phú và đa dạng)"),
    ("vi.intensifier", r"\b(?:vô cùng|cực kỳ|hết sức) (?:quan trọng|thú vị|hấp dẫn|thiết yếu|ý nghĩa|cần thiết)"),
    ("vi.greeting_scaffold", r"(?:chào mừng (?:các )?(?:em|bạn)[^.!?\n]{0,20}đến với|trong bài học này,? (?:chúng ta|em) sẽ|"
                             r"bài học hôm nay (?:sẽ|chúng ta)|hy vọng (?:bài|các em|em|bạn)|chúc (?:các )?(?:em|bạn) (?:học tốt|thành công))"),
    ("vi.reassure", r"\b(?:đừng lo lắng|đừng ngại|hãy nhớ rằng|bạn hoàn toàn có thể|em hoàn toàn có thể)"),
    ("vi.chatbot", r"\b(?:tôi hy vọng|dưới đây là|sau đây là (?:một số|những)|hãy cho tôi biết|rất vui được)"),
    # ---- English
    ("en.lets_dive", r"\b(?:let'?s (?:dive|delve|explore|unpack)|delve into|dive (?:in|into|deeper))"),
    ("en.not_only", r"\bnot only\b[^.!?\n]{1,80}\bbut also\b"),
    ("en.plays_role", r"\bplays? an? (?:crucial|vital|key|pivotal|important|significant) role"),
    ("en.in_conclusion", r"(?:^|[.!?]\s+|\n)\s*(?:in conclusion|in summary|overall|to summari[sz]e|ultimately),"),
    ("en.important_to_note", r"\b(?:it'?s (?:important|worth|crucial) (?:to note|noting|to remember)|it should be noted)"),
    ("en.today_world", r"\bin (?:today'?s|the modern|an increasingly)[^.!?\n]{0,30}(?:world|landscape|era|age)"),
    ("en.inflated", r"\b(?:rich tapestry|testament to|game-?changer|unlock(?:ing)? the (?:power|potential)|"
                    r"seamless(?:ly)?|leverag(?:e|es|ing)|foster(?:s|ing)?|cornerstone of|pivotal|journey)\b"),
    ("en.throat_clearing", r"\b(?:here'?s the thing|let that sink in|make no mistake|the truth is|let me be clear)"),
    ("en.chatbot", r"(?:i hope this helps|certainly!|great question|happy to help|let me know if)"),
    ("en.ing_tail", r",\s+(?:highlighting|showcasing|underscoring|demonstrating|reflecting|paving the way)\b"),
    # ---- both
    ("emoji", r"[\U0001F300-\U0001FAFF☀-➿⭐✅❌]"),
    ("multi_exclaim", r"!{2,}|\?{2,}|!\?"),
    ("em_dash", r"[—–]|\s--\s"),
]]


def lint(text: str) -> list[Hit]:
    """AI tells in `text`. Math ($...$) and code are masked first so formulas never trigger a rule."""
    masked = re.sub(r"\$\$.+?\$\$|\$[^$\n]+\$|`[^`\n]+`", lambda m: " " * len(m.group(0)), text, flags=re.S)
    hits = [Hit(name, m.group(0).strip(), m.start()) for name, rx in RULES for m in rx.finditer(masked)]
    # rule of three: two or more "x, y và z" / "x, y, and z" lists of single words in one text
    triads = list(re.finditer(r"\b[\wÀ-ỹ]+, [\wÀ-ỹ]+,? (?:và|and|hoặc|or) [\wÀ-ỹ]+\b", masked))
    if len(triads) >= 2:
        hits += [Hit("rule_of_three", m.group(0), m.start()) for m in triads]
    if masked.count("**") > 6:
        hits.append(Hit("bold_overuse", "**", masked.index("**")))
    return sorted(hits, key=lambda h: h.pos)


def lint_count(texts: Iterable[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for t in texts:
        for h in lint(t):
            out[h.rule] = out.get(h.rule, 0) + 1
    return out


# ---------------------------------------------------------------- preservation guard
_NUM = re.compile(r"\d+(?:[.,]\d+)?")
_MATH = re.compile(r"\$\$.+?\$\$|\$[^$\n]+\$", re.S)


def _names(text: str) -> set[str]:
    """Capitalised words that do not start a sentence (people, places, units like Cu-long): must survive a rewrite."""
    out: set[str] = set()
    prev_end = True
    for tok in re.findall(r"\S+", text):
        w = tok.strip(".,;:!?()\"'")
        if w and w[0].isupper() and not prev_end:
            out.add(w)
        prev_end = tok[-1] in ".!?:"
    return out


def preserved_ok(before: str, after: str) -> bool:
    """Math spans, every number and capitalised name (mid-sentence) of `before` must still be in `after`."""
    if sorted(m.group(0).replace(" ", "") for m in _MATH.finditer(before)) != \
            sorted(m.group(0).replace(" ", "") for m in _MATH.finditer(after)):
        return False
    b, a = _NUM.findall(_MATH.sub(" ", before)), _NUM.findall(_MATH.sub(" ", after))
    if sorted(b) != sorted(a):
        return False
    names = _names(_MATH.sub(" ", before))
    return all(n in after for n in names)


# ---------------------------------------------------------------- rewrite
HUMANIZE_SYSTEM = """You are a teacher editing your own lesson notes so they sound like a real teacher talking to a student.
Language: {lang}. Audience: {band}. You receive JSON {"<id>": "<text>"} and return JSON with the same ids.

Do:
- Short, plain, natural sentences. Say the thing directly; start with the content, not with a frame.
- Delete empty framing instead of replacing it ("Hãy cùng khám phá", "Tóm lại", "Điều quan trọng là", "Trong thế giới ngày nay",
  "It's important to note", "In conclusion", welcome lines, cheerleading, reassurance).
- Replace inflated words with plain ones ("đóng vai trò quan trọng" -> say what it does; "không chỉ... mà còn" -> two plain
  statements). Use "là" / "is" instead of fancy verbs.
- Vary sentence length a little; no list of three just for rhythm; no em dashes; no emoji; one "!" at most in a whole lesson.
- Keep a calm, kind, direct voice. A teacher who knows the subject, not a brochure.
Never change: facts, numbers, units, names, formulas ($...$ and $$...$$ must stay character for character), Markdown
structure (lists, bold, line breaks), or the meaning. Add no new claims, examples or advice. If a text is already fine,
return it unchanged. Do not make it longer."""


def humanize_texts(texts: dict[str, str], client: ModelClient, *, language: str, age_band_label: str,
                   hints: dict[str, list[str]] | None = None) -> tuple[dict[str, str], dict[str, str]]:
    """Rewrite prose. Returns (new texts, {id: reason} for ids whose rewrite was rejected and kept as is).
    `hints` {id: [tell, ...]}: second pass of the refine gate; the model is told which phrases the linter still found
    (the unslop skill's "diagnose, then repair the smallest span" order). A plain editing job: the CHAT alias is enough."""
    if not texts:
        return {}, {}
    system = HUMANIZE_SYSTEM.replace("{lang}", lang_name(language)).replace("{band}", age_band_label)
    if hints:
        listing = "\n".join(f"- {k}: {'; '.join(v)[:200]}" for k, v in hints.items())
        system += "\nA linter found these AI tells that MUST go (delete or restate plainly, change nothing else):\n" + listing
    import json

    cap = min(8000, max(1500, int(sum(len(t) for t in texts.values()) / 1.2) + 800))  # Vietnamese ~ 2-3 chars per token
    try:
        data = ask_json(client, system, json.dumps(texts, ensure_ascii=False), alias=ModelAlias.CHAT, max_tokens=cap,
                        temperature=0.3)
    except ModelError as exc:
        return dict(texts), {k: f"model error: {str(exc)[:80]}" for k in texts}
    out, rejected = {}, {}
    for k, old in texts.items():
        new = data.get(k)
        if not isinstance(new, str) or not new.strip():
            out[k], rejected[k] = old, "missing"
        elif not preserved_ok(old, new):
            out[k], rejected[k] = old, "numbers/math/names changed"
        elif len(new) > len(old) * 1.25 + 20:
            out[k], rejected[k] = old, "longer"
        elif len(lint(new)) > len(lint(old)):
            out[k], rejected[k] = old, "more tells than before"
        else:
            out[k] = new.strip()
    return out, rejected


__all__ = ["Hit", "RULES", "lint", "lint_count", "preserved_ok", "humanize_texts", "ModelAlias"]
