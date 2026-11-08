"""Paper text for questions: PDF -> text (pypdf, the library the sandbox `pdf_extract` script also uses), section-aware
passages, and a small lexical retriever. The text of one paper is cached on disk under the learner's own folder
(`<data_dir>/research/<user_id>/<paper_id>.txt`); it is the learner's own knowledge base and goes with the account.
"""

from __future__ import annotations

import io
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from mentor_gateway.planner.text import tokens

log = logging.getLogger(__name__)

MAX_PDF_BYTES = 25_000_000
MAX_PAGES = 80
CHUNK_CHARS = 1100
_NUM_HEADING = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,2})\.?\s+([A-Z][A-Za-z0-9 ,:&\-/()]{2,70})$")
_NAMED_HEADING = re.compile(r"^(Abstract|Introduction|Related Work|Background|Methods?|Methodology|Approach|Experiments?|"
                            r"Experimental Setup|Results|Discussion|Limitations|Conclusions?|Acknowledg\w+|References|Appendix\b.*)$",
                            re.IGNORECASE)


@dataclass
class Passage:
    section: str  # "" when unknown
    text: str
    url: str | None = None
    origin: str = "fulltext"  # fulltext | asta | abstract


def extract_pdf_text(data: bytes) -> str:
    """Text of a PDF ("" for an image-only scan: there is nothing to read without OCR)."""
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages[:MAX_PAGES]:
            try:
                pages.append(page.extract_text() or "")
            except Exception:  # noqa: BLE001 - one broken page must not lose the paper
                pages.append("")
    except (PyPdfError, ValueError, OSError, KeyError) as exc:
        log.warning("pdf unreadable: %s", exc.__class__.__name__)
        return ""
    text = "\n".join(pages)
    text = re.sub(r"-\n(?=[a-z])", "", text)  # hyphenated line breaks
    return re.sub(r"[ \t]+", " ", text).strip()


def section_label(number: str | None, title: str, lang: str) -> str:
    if number:
        return f"{'Section' if lang == 'en' else 'Mục'} {number}, {title}"
    return title


def split_passages(text: str, lang: str = "vi") -> list[Passage]:
    """Section-aware chunks of about 1100 characters, each labelled with the heading it sits under."""
    out: list[Passage] = []
    section = ""
    buf: list[str] = []

    def flush() -> None:
        body = " ".join(buf).strip()
        buf.clear()
        while body:
            if len(body) <= CHUNK_CHARS * 1.3:
                out.append(Passage(section, body))
                break
            cut = body.rfind(". ", int(CHUNK_CHARS * 0.6), CHUNK_CHARS + 200)
            cut = cut + 1 if cut > 0 else CHUNK_CHARS
            out.append(Passage(section, body[:cut].strip()))
            body = body[cut:].strip()

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _NUM_HEADING.match(line)
        if m and len(line) < 80:
            flush()
            section = section_label(m.group(1), m.group(2).strip(), lang)
            continue
        if _NAMED_HEADING.match(line):
            flush()
            section = line.strip().title() if line.islower() or line.isupper() else line.strip()
            continue
        buf.append(line)
        if sum(len(b) for b in buf) > CHUNK_CHARS * 2:
            flush()
    flush()
    return [p for p in out if len(p.text) > 40]


def top_passages(passages: list[Passage], question: str, k: int = 8) -> list[Passage]:
    """Lexical ranking (overlap weighted by rarity). A question in another language than the paper shares few words with
    it: when nothing overlaps, passages spread evenly through the paper are returned instead of nothing."""
    q = tokens(question)
    if not passages:
        return []
    if q:
        docs = [Counter(w for w in re.findall(r"[a-z0-9]+", _flat(p.text)) if len(w) >= 3) for p in passages]
        df = Counter(w for d in docs for w in d)
        n = len(docs)
        scored = []
        for i, d in enumerate(docs):
            s = sum((1 + math.log(d[w])) * math.log(1 + n / df[w]) for w in q if w in d)
            if s > 0:
                scored.append((s, i))
        if scored:
            scored.sort(key=lambda t: (-t[0], t[1]))
            keep = sorted(i for _, i in scored[:k])
            return [passages[i] for i in keep]
    step = max(1, len(passages) // k)
    return passages[::step][:k]


def _flat(text: str) -> str:
    from mentor_gateway.planner.text import unaccent

    return unaccent(text)


def norm(text: str) -> str:
    return " ".join(_flat(text).split())


def quote_in(quote: str, passage_text: str) -> bool:
    """A cited quote must be text of the passage (case, accents and spacing ignored), so a paraphrase cannot pose as a citation."""
    q = norm(quote).strip(" .…\"'")
    return len(q) >= 12 and q in norm(passage_text)


class TextCache:
    """`<root>/<user_id>/<paper_id>.txt`."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, user_id: str, paper_id: str) -> Path:
        return self.root / user_id / f"{paper_id}.txt"

    def write(self, user_id: str, paper_id: str, text: str) -> None:
        p = self.path(user_id, paper_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def read(self, user_id: str, paper_id: str) -> str | None:
        p = self.path(user_id, paper_id)
        return p.read_text(encoding="utf-8") if p.is_file() else None
