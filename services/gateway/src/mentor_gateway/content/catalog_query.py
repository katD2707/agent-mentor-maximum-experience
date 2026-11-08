"""Catalog query (hs-03): filters with live facet counts, sort, paging, autocomplete and "did you mean".

Pure functions over `CatalogEntry` lists. Relevance for a text query comes from `CourseSearch` (hybrid embeddings plus
lexical, see search.py) and from a plain accent-insensitive match on title, subject and teacher, so a half-typed word
or a teacher name finds courses even when the embedding router is down.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from mentor_schemas.course import CatalogEntry

from mentor_gateway.content.search import fold

PAGE_SIZE = 10
MAX_PAGE_SIZE = 50
BANDS = ["g1_5", "g6_9", "g10_12", "uni"]
LEVELS = ["basic", "intermediate", "advanced"]
DURATIONS = ["short", "medium", "long"]  # under 1 h, 1 to 3 h, over 3 h (from est_minutes)
MEDIA = ["video", "reading", "quiz", "interactive", "audio"]
STATUSES = ["live", "coming_soon"]
LANGS = ["vi", "en"]
FACET_KEYS = ["band", "subject", "language", "level", "duration", "media", "status", "teacher"]
SORTS = ["rel", "new", "pop", "dur"]


def duration_bucket(minutes: int) -> str:
    return "short" if minutes < 60 else "medium" if minutes <= 180 else "long"


def values(e: CatalogEntry, key: str) -> list[str]:
    if key == "band":
        return [e.age_band]
    if key == "subject":
        return [e.subject]
    if key == "language":
        return [e.language]
    if key == "level":
        return [e.level] if e.level else []
    if key == "duration":
        return [duration_bucket(e.est_minutes)]
    if key == "media":
        return list(e.media)
    if key == "status":
        return [e.status]
    return [e.teacher_name]  # teacher


@dataclass
class Query:
    q: str = ""
    filters: dict[str, set[str]] = field(default_factory=dict)  # facet key -> accepted values
    sort: str = "rel"
    dir: str = "asc"  # only used by sort=dur
    page: int = 1
    page_size: int = PAGE_SIZE


def name_text(e: CatalogEntry) -> str:
    return fold(f"{e.title} {e.subject} {e.teacher_name} {'english' if e.language == 'en' else 'tieng viet'}")


def name_tokens(q: str) -> list[str]:
    return [t for t in fold(q).split() if t]


def name_match(e: CatalogEntry, toks: list[str]) -> bool:
    text = name_text(e)
    return bool(toks) and all(t in text for t in toks)


def passes_filters(e: CatalogEntry, filters: dict[str, set[str]], skip: str | None = None) -> bool:
    for k, accepted in filters.items():
        if k == skip or not accepted:
            continue
        if not any(v in accepted for v in values(e, k)):
            return False
    return True


def facets(entries: list[CatalogEntry], filters: dict[str, set[str]], matched: set[str] | None) -> dict[str, list[dict]]:
    """Counts per facet value among the entries that match the text query and every filter except that facet's own, so
    ticking one value never hides its siblings. Subjects and teachers are listed only with a hit or when ticked."""
    out: dict[str, list[dict]] = {}
    fixed = {"band": BANDS, "language": LANGS, "level": LEVELS, "duration": DURATIONS, "status": STATUSES, "media": MEDIA}
    for k in FACET_KEYS:
        counts: dict[str, int] = {}
        for e in entries:
            if matched is not None and e.id not in matched:
                continue
            if not passes_filters(e, filters, skip=k):
                continue
            for v in values(e, k):
                counts[v] = counts.get(v, 0) + 1
        if k in fixed:
            out[k] = [{"v": v, "n": counts.get(v, 0)} for v in fixed[k]]
        else:
            vals = {v for v, n in counts.items() if n} | set(filters.get(k, set()))
            out[k] = [{"v": v, "n": counts.get(v, 0)} for v in sorted(vals, key=lambda v: (-counts.get(v, 0), v.lower()))]
    return out


def relevance(e: CatalogEntry, toks: list[str], score: float) -> float:
    """Search score plus a bonus for a plain match on the name: starts-with beats contains beats subject/teacher only."""
    if not toks:
        return 0.0
    title = fold(e.title)
    bonus = 0.0
    if name_match(e, toks):
        bonus = 0.5 if title.startswith(toks[0]) else 0.3 if all(t in title for t in toks) else 0.15
    return score + bonus


def sort_entries(rows: list[tuple[int, CatalogEntry]], q: Query, rel: dict[str, float], students: dict[str, int]) -> list[CatalogEntry]:
    """`rows` carry their catalog position; ties always fall back to it, so the order is stable."""

    def soon(e: CatalogEntry) -> bool:
        return e.status != "live"

    def published(e: CatalogEntry) -> float:
        return (e.published_at or datetime(1970, 1, 1)).replace(tzinfo=None).timestamp()

    if q.sort == "new":
        def key(r):
            return (soon(r[1]), 0.0 if soon(r[1]) else -published(r[1]), r[0])
    elif q.sort == "pop":
        def key(r):
            return (-students.get(r[1].id, 0), r[0])
    elif q.sort == "dur":
        sign = 1 if q.dir == "asc" else -1

        def key(r):
            return (sign * r[1].est_minutes, r[0])
    else:
        def key(r):
            return (-rel.get(r[1].id, 0.0), soon(r[1]), r[0])
    return [e for _, e in sorted(rows, key=key)]


# ---------------------------------------------------------------- did you mean
def _dist(a: str, b: str) -> int:
    """Edit distance where swapping two neighbouring letters ("phna" for "phan") costs one."""
    d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        d[i][0] = i
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] != b[j - 1]))
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[len(a)][len(b)]


def vocabulary(entries: list[CatalogEntry]) -> dict[str, str]:
    """folded word -> display word (lower case, with accents) from titles, subjects and teacher names."""
    vocab: dict[str, str] = {}
    for e in entries:
        for raw in f"{e.title} {e.subject} {e.teacher_name}".split():
            word = raw.strip(":,.()").lower()
            k = fold(word)
            if len(k) > 1 and k not in vocab:
                vocab[k] = word
    return vocab


def did_you_mean(q: str, vocab: dict[str, str]) -> str | None:
    """Corrects words that are not (the start of) any known word. None when the query already reads fine."""
    out: list[str] = []
    changed = False
    words = list(vocab)
    for t in name_tokens(q):
        pre = next((w for w in words if w.startswith(t)), None)
        if pre:
            out.append(vocab[pre])
            continue
        changed = True
        best, bd = None, 2 if len(t) > 4 else 1
        for w in words:
            d = _dist(t, w)
            if d <= bd and (best is None or d < bd):
                best, bd = w, d
        out.append(vocab[best] if best else t)
    s = " ".join(out)
    return s if changed and s and fold(s) != fold(q) else None


# ---------------------------------------------------------------- autocomplete
def suggest(q: str, entries: list[CatalogEntry], vocab: dict[str, str], limit: int = 4) -> dict:
    toks = name_tokens(q)
    if not toks:
        return {"courses": [], "subjects": [], "teachers": [], "did_you_mean": None}

    def ok(s: str) -> bool:
        f = fold(s)
        return all(t in f for t in toks)

    courses = [{"id": e.id, "title": e.title} for e in entries if ok(e.title)][:limit]
    subjects: list[str] = []
    teachers: list[str] = []
    for e in entries:
        if e.subject not in subjects and ok(e.subject):
            subjects.append(e.subject)
        if e.teacher_name not in teachers and ok(e.teacher_name):
            teachers.append(e.teacher_name)
    hint = None if courses or subjects or teachers else did_you_mean(q, vocab)
    return {"courses": courses, "subjects": subjects[:3], "teachers": teachers[:3], "did_you_mean": hint}
