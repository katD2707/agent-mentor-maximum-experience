"""Plain-text helpers for Zalo: markdown -> plain text and splitting at the 2,000-char limit.

Zalo's sendMessage takes 1 to 2,000 characters. Style offsets in its API are UTF-16 code units, so we
count length the same way (characters outside the BMP, e.g. emoji, count as 2). Vietnamese text is
all BMP, so for normal reports this is the same as len().
"""

import re

MAX_MESSAGE_CHARS = 2000

_FENCE = re.compile(r"^\s*(```|~~~)")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
_HR = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
_BULLET = re.compile(r"^(\s*)[-*+]\s+")
_QUOTE = re.compile(r"^\s{0,3}>\s?")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+[^)]*)?\)")
_BOLD = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
_ITALIC_STAR = re.compile(r"(?<![\w*])\*(?=\S)(.+?)(?<=\S)\*(?![\w*])")
_ITALIC_UNDERSCORE = re.compile(r"(?<![\w_])_(?=\S)(.+?)(?<=\S)_(?![\w_])")
_STRIKE = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~")
_CODE = re.compile(r"`([^`]+)`")
_HTML_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
_MANY_BLANKS = re.compile(r"\n{3,}")


def utf16_len(text: str) -> int:
    """Length in UTF-16 code units, the unit Zalo uses for message limits and style offsets."""
    return len(text.encode("utf-16-le")) // 2


def _inline(text: str) -> str:
    text = _IMAGE.sub(r"\1", text)
    text = _LINK.sub(lambda m: m.group(1) if m.group(1) == m.group(2) else f"{m.group(1)} ({m.group(2)})", text)
    text = _CODE.sub(r"\1", text)
    text = _BOLD.sub(r"\2", text)
    text = _ITALIC_STAR.sub(r"\1", text)
    text = _ITALIC_UNDERSCORE.sub(r"\1", text)
    text = _STRIKE.sub(r"\1", text)
    return _HTML_TAG.sub("", text)


def markdown_to_plain(markdown: str) -> str:
    """Render markdown as readable plain text for a Zalo chat bubble.

    Headings lose their `#`, emphasis markers are dropped, bullets become `•`, links become
    `text (url)`, table rows become cells joined by ` | `, fenced code keeps its content.
    """
    out: list[str] = []
    in_fence = False
    for line in markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            out.append(line.rstrip())
            continue
        if _HR.match(line) or _TABLE_SEP.match(line) and "-" in line and "|" in line:
            out.append("")
            continue
        heading = _HEADING.match(line)
        if heading:
            out.append(_inline(heading.group(1)))
            continue
        line = _QUOTE.sub("", line)
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|") and len(stripped) > 1:
            cells = [_inline(c.strip()) for c in stripped[1:-1].split("|")]
            out.append(" | ".join(c for c in cells if c))
            continue
        line = _BULLET.sub(lambda m: f"{m.group(1)}• ", line)
        out.append(_inline(line).rstrip())
    return _MANY_BLANKS.sub("\n\n", "\n".join(out)).strip()


def _max_prefix(text: str, limit: int) -> int:
    """Largest index i such that text[:i] fits in `limit` UTF-16 units."""
    units = 0
    for i, ch in enumerate(text):
        units += 2 if ord(ch) > 0xFFFF else 1
        if units > limit:
            return i
    return len(text)


def _cut_point(text: str, limit: int) -> int:
    hard = _max_prefix(text, limit)
    window = text[:hard]
    floor = hard // 3  # do not produce tiny chunks just to honour a boundary
    for sep in ("\n\n", "\n", ". ", " "):
        idx = window.rfind(sep)
        if idx >= floor and idx > 0:
            return idx + len(sep)
    return max(hard, 1)


def split_text(text: str, limit: int = MAX_MESSAGE_CHARS) -> list[str]:
    """Split text into chunks of at most `limit` UTF-16 units.

    Prefers paragraph breaks, then line breaks, then sentence ends, then spaces; only cuts inside a
    word when a single word is longer than the limit. Empty input gives an empty list.
    """
    if limit < 1:
        raise ValueError("limit must be positive")
    text = text.strip()
    chunks: list[str] = []
    while text and utf16_len(text) > limit:
        cut = _cut_point(text, limit)
        head, text = text[:cut].rstrip(), text[cut:].lstrip()
        if head:
            chunks.append(head)
    if text:
        chunks.append(text)
    return chunks
