"""Course search (REQUIREMENTS-PLAN 3.5): hybrid of embeddings (router alias `mentor-embed`) and a lexical score.

Retrieval text per course = title + subject + description_short + outcomes + lesson titles + key ideas.
Embeddings are cached on disk per `<pack_sha256>-<text hash>.json` and fetched in one batch call; the query embedding
is cached in memory. If the router is not configured or fails, search is purely lexical (diacritic-insensitive).
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import threading
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import httpx
from mentor_schemas import ModelAlias
from mentor_schemas.course import CatalogEntry, CourseMeta, CoursePack

log = logging.getLogger(__name__)

STOP = {
    "em", "muon", "hoc", "toi", "minh", "la", "va", "cua", "cac", "nhung", "co", "the", "khoa", "bai", "ve", "cho",
    "can", "tim", "mot", "nhu", "gi", "nao", "i", "want", "to", "learn", "course", "a", "an", "of", "and", "in", "on",
    "how", "what", "is", "lop", "grade", "class", "muon", "biet", "giup", "xem", "ve",
}

MIN_SCORE = 0.2      # below this a course is not a match (hybrid score 0..1)
REL_SCORE = 0.55     # ...and neither is one scoring under this share of the best match
EMBED_BATCH = 32     # texts per embedding call when filling the cache
CONFIDENT_LEX = 0.55  # a lexical hit this strong (and clearly ahead) needs no embedding call


def fold(text: str) -> str:
    """Lower-case, strip Vietnamese diacritics (d with stroke too)."""
    t = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", fold(text))


def retrieval_fields(meta: CourseMeta | CatalogEntry, pack: CoursePack | None) -> dict[str, str]:
    lesson_titles, key_ideas = [], []
    if pack:
        for ch in pack.chapters:
            lesson_titles.append(ch.title)
            for ls in ch.lessons:
                lesson_titles.append(ls.title)
                key_ideas.extend(ls.key_ideas)
    return {
        "title": meta.title,
        "subject": meta.subject,
        "desc": " ".join([meta.description_short, *meta.outcomes]),
        "lessons": " ".join(lesson_titles),
        "ideas": " ".join(key_ideas),
    }


FIELD_WEIGHT = {"title": 3.0, "subject": 2.0, "lessons": 1.5, "desc": 1.0, "ideas": 1.0}


def retrieval_text(fields: dict[str, str]) -> str:
    return "\n".join(fields[k] for k in ("title", "subject", "desc", "lessons", "ideas") if fields.get(k))


def lexical_scores(query: str, docs: dict[str, dict[str, str]]) -> dict[str, float]:
    """Score 0..1 per doc id: idf-weighted share of query tokens found (best field weight, prefix match allowed)."""
    q = [t for t in dict.fromkeys(tokens(query)) if t not in STOP] or list(dict.fromkeys(tokens(query)))
    if not q or not docs:
        return {}
    toks = {i: {f: set(tokens(v)) for f, v in fields.items()} for i, fields in docs.items()}
    n = len(docs)

    def hit(t: str, ts: set[str]) -> bool:
        return t in ts or (len(t) >= 3 and any(x.startswith(t) for x in ts))

    idf = {t: math.log(1 + n / (1 + sum(1 for d in toks.values() if any(hit(t, ts) for ts in d.values())))) for t in q}
    if any(not t.isdigit() for t in q):  # "lớp 11" must not pull in every course that mentions 11
        idf = {t: v * (0.3 if t.isdigit() else 1.0) for t, v in idf.items()}
    total = sum(idf.values()) * max(FIELD_WEIGHT.values()) or 1.0
    phrase = " ".join(q)
    out: dict[str, float] = {}
    for i, fields in docs.items():
        s = sum(idf[t] * max((FIELD_WEIGHT[f] for f, ts in toks[i].items() if hit(t, ts)), default=0.0) for t in q)
        score = s / total
        if len(q) > 1 and any(phrase in " ".join(tokens(v)) for v in fields.values()):
            score += 0.2
        if score > 0:
            out[i] = min(score, 1.0)
    return out


def cosine(a: list[float], b: list[float]) -> float:
    da = math.sqrt(sum(x * x for x in a))
    db = math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b, strict=False)) / (da * db) if da and db else 0.0


class RouterEmbedder:
    """POST {router}/v1/embeddings with the `mentor-embed` alias. `available` is False without a router URL, and for
    60 s after a failure (so a down router does not slow every search)."""

    def __init__(self, url: str | None, key: str | None, timeout: float = 6.0) -> None:
        self.url = (url or "").rstrip("/")
        self.key = key or ""
        self.timeout = timeout
        self._down_until = 0.0
        self._client: httpx.Client | None = None  # one keep-alive connection: a new one costs 20-100 ms and more

    @property
    def available(self) -> bool:
        return bool(self.url) and time.monotonic() >= self._down_until

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        if not self.available or not texts:
            return None
        try:
            if self._client is None:
                self._client = httpx.Client(timeout=self.timeout)
            r = self._client.post(f"{self.url}/v1/embeddings", json={"model": ModelAlias.EMBED.value, "input": texts},
                                  headers={"Authorization": f"Bearer {self.key}"} if self.key else {})
            r.raise_for_status()
            data = sorted(r.json()["data"], key=lambda d: d["index"])
            vecs = [d["embedding"] for d in data]
            if len(vecs) != len(texts):
                raise ValueError("embedding count mismatch")
            return vecs
        except Exception as e:  # noqa: BLE001 - any failure means "fall back to lexical"
            log.warning("embeddings unavailable (%s); lexical search only for 60 s", e)
            self._down_until = time.monotonic() + 60
            return None


@dataclass
class Doc:
    entry: CatalogEntry
    fields: dict[str, str]
    text: str
    key: str  # pack_sha256-texthash


class CourseSearch:
    def __init__(self, cache_dir: Path, embedder: RouterEmbedder | None = None) -> None:
        self.cache_dir = cache_dir
        self.embedder = embedder or RouterEmbedder(None, None)
        self._qcache: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _doc_vectors(self, docs: list[Doc]) -> dict[str, list[float]] | None:
        out: dict[str, list[float]] = {}
        missing: list[Doc] = []
        for d in docs:
            f = self.cache_dir / f"{d.key}.json"
            try:
                out[d.entry.id] = json.loads(f.read_text("utf-8"))
            except (OSError, ValueError):
                missing.append(d)
        if missing:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            for i in range(0, len(missing), EMBED_BATCH):  # batches keep each call fast; finished ones stay cached
                chunk = missing[i:i + EMBED_BATCH]
                vecs = self.embedder.embed([d.text for d in chunk])
                if vecs is None:
                    return None
                for d, v in zip(chunk, vecs, strict=True):
                    out[d.entry.id] = v
                    (self.cache_dir / f"{d.key}.json").write_text(json.dumps(v), "utf-8")
        return out

    def _query_vector(self, q: str) -> list[float] | None:
        with self._lock:
            if q in self._qcache:
                return self._qcache[q]
        vecs = self.embedder.embed([q])
        if vecs is None:
            return None
        with self._lock:
            if len(self._qcache) > 500:
                self._qcache.clear()
            self._qcache[q] = vecs[0]
        return vecs[0]

    def search(self, query: str, docs: list[Doc], *, fast: bool = False) -> tuple[list[tuple[CatalogEntry, float]], str]:
        """Returns ([(entry, score)] best first, mode "hybrid"|"lexical"). Only matching courses are returned: a score under
        MIN_SCORE or under REL_SCORE of the best one is dropped. `fast` skips the embedding call (1-2 s) when the
        lexical match is already clear and the query vector is not cached."""
        lex = lexical_scores(query, {d.entry.id: d.fields for d in docs})
        cos: dict[str, float] = {}
        mode = "lexical"
        top = sorted(lex.values(), reverse=True)[:2] + [0.0]
        skip = fast and top[0] >= CONFIDENT_LEX and top[1] <= 0.75 * top[0] and query.strip() not in self._qcache
        if self.embedder.available and docs and not skip:
            qv = self._query_vector(query.strip())
            dv = self._doc_vectors(docs) if qv is not None else None
            if qv is not None and dv is not None:
                cos = {i: cosine(qv, v) for i, v in dv.items()}
                mode = "hybrid"
        scored: list[tuple[CatalogEntry, float]] = []
        for d in docs:
            l_ = lex.get(d.entry.id, 0.0)
            if mode == "hybrid":
                c = cos.get(d.entry.id, 0.0)
                c_norm = min(max((c - 0.2) / 0.6, 0.0), 1.0)
                if l_ <= 0 and c < 0.4:
                    continue
                s = 0.55 * c_norm + 0.45 * l_
            else:
                if l_ <= 0:
                    continue
                s = l_
            scored.append((d.entry, round(s, 4)))
        scored.sort(key=lambda x: (-x[1], x[0].title))
        if scored:
            floor = max(MIN_SCORE, REL_SCORE * scored[0][1])
            scored = [x for x in scored if x[1] >= floor]
        return scored, mode


def make_key(pack_sha256: str, text: str) -> str:
    return f"{pack_sha256}-{hashlib.sha256(text.encode()).hexdigest()[:8]}"
