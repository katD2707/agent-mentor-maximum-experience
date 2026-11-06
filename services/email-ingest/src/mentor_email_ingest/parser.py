"""Parse a raw RFC 5322 message into plain text and attachments, with the stdlib only.

- Headers are decoded by `email.policy.default` (RFC 2047 encoded words, RFC 2231 filenames).
- Text parts are decoded by their declared charset with fallbacks (utf-8, windows-1258) and NFC-normalised,
  because Vietnamese mail is often mislabelled or uses windows-1258 combining tone marks.
- HTML-only mail is converted to text with `html.parser`.
- A forwarded message attached as message/rfc822 is inlined into the text; its attachments are kept.
"""

import codecs
import re
import unicodedata
from datetime import datetime
from email import policy
from email.errors import MessageError
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses
from html.parser import HTMLParser

from pydantic import BaseModel

MAX_NESTING = 3
# What policy.default may raise on a malformed header; such headers are treated as absent.
_HEADER_ERRORS = (MessageError, ValueError, TypeError, IndexError, AttributeError)


class ParsedEmail(BaseModel):
    from_addr: str  # addr-spec, e.g. "gvhd@hust.edu.vn"
    from_name: str = ""
    to_addrs: list[str]  # To + Cc addr-specs
    delivered_to: list[str] = []  # Delivered-To / X-Original-To / Envelope-To, set by the receiving MTA
    subject: str
    date: datetime | None
    text: str
    attachments: list[tuple[str, str, bytes]] = []  # (filename as sent, mime type, content)
    message_id: str | None = None


# ---- HTML -> text -------------------------------------------------------------------------------

_PARAGRAPH_TAGS = {
    "p", "table", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "section", "article",
    "header", "footer", "pre", "hr", "dl",
}  # fmt: skip
_LINE_TAGS = {"div", "li", "tr", "dt", "dd"}
_SKIP_TAGS = {"script", "style", "head", "title", "noscript", "template"}
_WS = re.compile(r"\s+")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._newlines = 2  # trailing newlines already emitted; start as if after a paragraph
        self._skip = 0
        self._pre = 0
        self._href: str | None = None
        self._link_text: list[str] = []

    def _break(self, n: int) -> None:
        """Ensure the output ends with at least n newlines (block boundaries collapse)."""
        if self._newlines < n:
            self.parts.append("\n" * (n - self._newlines))
            self._newlines = n

    def _block(self, tag: str) -> None:
        if tag in _PARAGRAPH_TAGS:
            self._break(2)
        elif tag in _LINE_TAGS:
            self._break(1)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag == "pre":
            self._pre += 1
        if tag == "br":
            self.parts.append("\n")
            self._newlines += 1
            return
        self._block(tag)
        if tag == "li":
            self.parts.append("- ")
        elif tag in ("td", "th"):
            self.parts.append(" ")
        elif tag == "a":
            self._href = dict(attrs).get("href")
            self._link_text = []

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in ("br", "hr"):
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        elif tag == "pre":
            self._pre = max(0, self._pre - 1)
        if tag == "a" and self._href:
            text = "".join(self._link_text).strip()
            if self._href.startswith(("http://", "https://")) and self._href != text:
                self.parts.append(f" ({self._href})")
            self._href = None
        self._block(tag)

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if not self._pre:
            data = _WS.sub(" ", data)  # source line breaks inside HTML text are not line breaks
        self.parts.append(data)
        if data.strip():
            self._newlines = 0
        if self._href is not None:
            self._link_text.append(data)


def html_to_text(html: str) -> str:
    extractor = _TextExtractor()
    extractor.feed(html)
    extractor.close()
    lines = [" ".join(line.split()) for line in "".join(extractor.parts).split("\n")]
    out: list[str] = []
    for line in lines:
        if line or (out and out[-1]):
            out.append(line)
    return "\n".join(out).strip()


# ---- decoding -----------------------------------------------------------------------------------


def _known(charset: str) -> bool:
    try:
        codecs.lookup(charset)
    except LookupError:
        return False
    return True


def decode_bytes(data: bytes, charset: str | None) -> str:
    """Strict-decode with the declared charset, then utf-8, then windows-1258; last resort replaces."""
    declared = (charset or "").strip().strip('"').lower()
    candidates: list[str] = []
    if declared and declared not in ("us-ascii", "ascii") and _known(declared):
        candidates.append(declared)
    candidates += ["utf-8", "cp1258"]
    for enc in candidates:
        try:
            return unicodedata.normalize("NFC", data.decode(enc))
        except UnicodeDecodeError:
            continue
    return unicodedata.normalize("NFC", data.decode("utf-8", errors="replace"))


def _part_text(part: EmailMessage) -> str:
    payload = part.get_payload(decode=True)
    if not isinstance(payload, bytes):
        return ""
    return decode_bytes(payload, part.get_content_charset())


def _header(msg: EmailMessage, name: str) -> str:
    try:
        value = msg.get(name)
    except _HEADER_ERRORS:
        return ""
    return unicodedata.normalize("NFC", " ".join(str(value).split())) if value is not None else ""


def _addresses(msg: EmailMessage, *names: str) -> list[tuple[str, str]]:
    values: list[str] = []
    for name in names:
        try:
            values += [str(v) for v in msg.get_all(name, [])]
        except _HEADER_ERRORS:
            pass
    return [(n, a.strip().lower()) for n, a in getaddresses(values) if "@" in a]


def _date(msg: EmailMessage) -> datetime | None:
    try:
        header = msg.get("date")
        return getattr(header, "datetime", None)
    except _HEADER_ERRORS:
        return None


# ---- structure ----------------------------------------------------------------------------------


def _leaves(part: EmailMessage):
    if part.get_content_type() == "message/rfc822":
        yield part
    elif part.is_multipart():
        for sub in part.iter_parts():
            yield from _leaves(sub)
    else:
        yield part


def _parse(msg: EmailMessage, depth: int) -> ParsedEmail:
    plains: list[str] = []
    htmls: list[str] = []
    forwarded: list[str] = []
    attachments: list[tuple[str, str, bytes]] = []

    for part in _leaves(msg):
        ctype = part.get_content_type()
        disposition = part.get_content_disposition()
        filename = part.get_filename()
        if ctype == "message/rfc822" and depth < MAX_NESTING:
            inner = part.get_payload(0) if part.is_multipart() else None
            if isinstance(inner, EmailMessage):
                sub = _parse(inner, depth + 1)
                forwarded.append(
                    "---------- Thư được chuyển tiếp / Forwarded message ----------\n"
                    f"Từ / From: {sub.from_name} <{sub.from_addr}>\n"
                    f"Tiêu đề / Subject: {sub.subject}\n"
                    f"Ngày / Date: {sub.date.isoformat() if sub.date else ''}\n\n{sub.text}"
                )
                attachments += sub.attachments
                continue
        if disposition == "attachment" or filename:
            data = part.get_payload(decode=True)
            if isinstance(data, bytes):
                attachments.append((filename or "", ctype, data))
        elif ctype == "text/plain":
            plains.append(_part_text(part))
        elif ctype == "text/html":
            htmls.append(_part_text(part))

    if plains:
        text = "\n\n".join(p.strip() for p in plains if p.strip())
    else:
        text = "\n\n".join(html_to_text(h) for h in htmls)
    text = "\n\n".join(t for t in [text.strip(), *forwarded] if t)

    senders = _addresses(msg, "from")
    from_name, from_addr = senders[0] if senders else ("", "")
    return ParsedEmail(
        from_addr=from_addr,
        from_name=unicodedata.normalize("NFC", from_name),
        to_addrs=[a for _, a in _addresses(msg, "to", "cc")],
        delivered_to=[a for _, a in _addresses(msg, "delivered-to", "x-original-to", "envelope-to")],
        subject=_header(msg, "subject"),
        date=_date(msg),
        text=text.replace("\r\n", "\n"),
        attachments=attachments,
        message_id=_header(msg, "message-id") or None,
    )


def parse_message(raw: bytes) -> ParsedEmail:
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    assert isinstance(msg, EmailMessage)
    return _parse(msg, 0)
