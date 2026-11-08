"""Short, natural wording. The course-builder has a humanize pass but it lives in another package (no cross-package
imports), so the gateway keeps a compact rule list: given to the model in the prompt and enforced in code."""

import re
import unicodedata

HUMANIZE_RULES = """Wording rules for every *_vi / *_en text:
- One or two short sentences, plain words, like a friendly older sibling. Vietnamese: "em" for the student, "Mentor" for yourself.
- Say what and when, concretely (minutes, lesson name). No praise filler, no slogans, no emoji, no hashtags.
- No em dashes or en dashes; use a comma or a full stop. No exclamation marks. No rhetorical questions except a gentle "nhé?" invitation.
- Never judge ("lười", "yếu", "you failed"). Say "hơi chậm" or "cần củng cố".
- Do not start with "Hãy", "Don't forget", "Remember to", "It's time to". Do not use "Let's dive", "unlock", "journey".
- Reminder text is under 90 characters; a plan reason is one sentence under 140 characters."""

_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️]")
_DASH = re.compile(r"\s*[–—]\s*")
_BAD_START = re.compile(r"^(hãy|đừng quên|don't forget|remember to|it's time to)\s+", re.IGNORECASE)


def clean(text: object, limit: int = 140) -> str:
    """Enforce the rules above on model output (and on templates): no emoji, no dashes, no '!', length cap."""
    t = str(text or "")
    t = _EMOJI.sub("", t)
    t = _DASH.sub(", ", t)
    t = t.replace("!", ".")
    t = re.sub(r"\.{2,}", ".", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = _BAD_START.sub("", t)
    if t and t[0].islower():
        t = t[0].upper() + t[1:]
    if len(t) > limit:
        cut = t[:limit]
        stop = max(cut.rfind(". "), cut.rfind(", "))
        t = (cut[:stop] if stop >= limit // 2 else cut.rsplit(" ", 1)[0]).rstrip(",. ") + "."
    return t


def unaccent(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower().replace("đ", "d"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", unaccent(s)) if len(w) >= 3}
