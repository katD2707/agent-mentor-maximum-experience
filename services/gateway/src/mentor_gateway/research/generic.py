"""Words that match half of arXiv ("paper", "study"...): never worth a search of their own, nor a "matches keyword" reason."""

from __future__ import annotations

import re

GENERIC_KEYWORDS = {"paper", "papers", "study", "studies", "research", "method", "methods", "approach", "approaches", "analysis",
                    "technique", "techniques", "review", "survey", "article", "work", "results"}

_KW_REASON = re.compile(r"^(?:Khớp từ khóa|Matches keyword)\s+(.+?)\.?\s*$", re.IGNORECASE)


def specific_keywords(kws: list[str]) -> list[str]:
    """The keywords without the generic ones; when nothing else is left the list is kept as the user wrote it."""
    keep = [k for k in kws if k.strip().lower() not in GENERIC_KEYWORDS]
    return keep or list(kws)


def generic_match(reason: str | None) -> bool:
    """A reason that only says "matches keyword paper": left over from before generic keywords were filtered when seeding."""
    m = _KW_REASON.match(reason or "")
    return bool(m and m.group(1).strip().lower() in GENERIC_KEYWORDS)


_MD = re.compile(r"`+|\*\*|__|^#+\s*")


def tidy_title(title: str | None) -> str:
    """A paper title for display: no raw markdown marks (backticks, bold stars), one line."""
    return " ".join(_MD.sub("", title or "").replace("\\_", "_").split())
