"""Fetch one public web page as text, or download one PDF as bytes, for the harness tool web_fetch (both profiles).

Sandboxes have no internet, so the gateway fetches on their behalf. The URL comes from the model (often from a
web_search result or a link the learner pasted), so this is an SSRF surface. Defences, all in `WebFetchService`:

- only `http`/`https`, only ports 80 and 443, no `user:pass@` in the URL;
- hostnames: refuse `localhost`, single-label names (docker services such as `gateway`, `model-router`), internal
  suffixes (`.local`, `.internal`, `.lan`, ...) and the gateway's own hosts (`blocked_hosts`, from settings);
- DNS is resolved here; every returned address must be public (`ip_allowed`: no private, loopback, link-local
  incl. 169.254.169.254, CGNAT, multicast, reserved, unspecified; IPv4-mapped / 6to4 / Teredo / NAT64 forms are
  checked on the embedded IPv4). The connection then goes to the vetted IP itself (`https://<ip>/...` with the
  `Host` header and TLS SNI + certificate check on the real hostname), so a second DNS answer cannot swap it
  (no DNS rebinding);
- redirects are followed by hand, at most `MAX_REDIRECTS`, each hop re-validated from scratch;
- no cookies, no auth, no env proxies / .netrc (the transport is used directly, without an httpx client);
- 15 s for the whole fetch, at most `MAX_BODY_BYTES` read (raw and decompressed), only HTML, plain text and JSON.
  A PDF answers 415 `pdf` on the page path;
- PDFs go through `download_pdf` (POST /internal/web/download): same URL, DNS, redirect and transport rules, 60 s,
  at most `max_pdf_bytes` (WEB_FETCH_PDF_MAX_MB, raw and decompressed; over the cap = refused, never truncated),
  and the body must carry the `%PDF-` magic in its first 1024 bytes whatever the content type says. The gateway
  never parses the PDF: it holds the keys and the Docker socket, so the bytes go to the learner's sandbox, which
  saves and parses them.

Privacy: the URL path and query may carry personal data, so nothing here logs URLs (the transport is used without
an httpx client, whose INFO log line would contain the URL); the endpoint audits only the host and the status.
"""

import asyncio
import codecs
import contextlib
import ipaddress
import json
import re
import socket
import unicodedata
import zlib
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from mentor_gateway.websearch import clean_text

TIMEOUT_S = 15.0
MAX_REDIRECTS = 5
MAX_BODY_BYTES = 2_000_000
MAX_PDF_BYTES = 30_000_000  # default of WEB_FETCH_PDF_MAX_MB (MB = 10^6 bytes)
PDF_MAX_MB_LIMIT = 200
PDF_TIMEOUT_S = 60.0
PDF_MAGIC = b"%PDF-"
PDF_MAGIC_WINDOW = 1024  # readers accept the header anywhere in the first 1 KB
MAX_TEXT_CHARS = 20_000
MAX_URL_CHARS = 2000
TITLE_CHARS = 300
ALLOWED_PORTS = frozenset({80, 443})
HTML_TYPES = frozenset({"text/html", "application/xhtml+xml"})
TEXT_TYPES = frozenset({"text/plain", "application/json"})
PDF_TYPES = frozenset({"application/pdf", "application/x-pdf"})
PAGE_ACCEPT = "text/html,application/xhtml+xml,text/plain;q=0.9,application/json;q=0.8"
PDF_ACCEPT = "application/pdf,*/*;q=0.5"
USER_AGENT = "mentor-gateway/0.1 (reads one page for an AI mentoring app)"
BLOCKED_HOSTS = frozenset({"localhost", "metadata", "instance-data", "metadata.google.internal"})
BLOCKED_SUFFIXES = (".localhost", ".local", ".localdomain", ".internal", ".intranet", ".lan", ".home", ".corp",
                    ".private", ".home.arpa", ".arpa", ".test", ".invalid", ".onion")
_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2066-\u2069]")

Resolver = Callable[[str, int], Awaitable[list[str]]]


class WebFetchError(Exception):
    """`status` = HTTP status the endpoint returns; `reason` = machine-readable cause for the harness."""

    def __init__(self, status: int, message: str, reason: str = "upstream", upstream_status: int | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.reason = reason
        self.upstream_status = upstream_status


def _blocked(message: str) -> WebFetchError:
    return WebFetchError(400, message, "blocked_url")


def _is_pdf() -> WebFetchError:
    return WebFetchError(415, "the URL is a PDF; download it with POST /internal/web/download", "pdf")


def _not_pdf() -> WebFetchError:
    return WebFetchError(415, "the response is not a PDF (no %PDF- header)", "not_pdf")


def has_pdf_magic(head: bytes) -> bool:
    return PDF_MAGIC in head[:PDF_MAGIC_WINDOW]


# ---- address and URL checks ---------------------------------------------------------------------


def ip_allowed(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True only for a globally routable unicast address (embedded IPv4 in v6 forms is checked too)."""
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.scope_id:
            return False
        embedded = ip.ipv4_mapped if ip.ipv4_mapped is not None else ip.sixtofour
        if embedded is None and ip.teredo is not None:
            embedded = ip.teredo[1]  # (server, client): the client address is the one reached
        if embedded is None and ip in _NAT64:
            embedded = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        if embedded is not None and not ip_allowed(embedded):
            return False
    return bool(
        ip.is_global
        and not ip.is_private
        and not ip.is_loopback
        and not ip.is_link_local
        and not ip.is_multicast
        and not ip.is_reserved
        and not ip.is_unspecified
    )


def _parse_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


@dataclass(frozen=True)
class Target:
    url: str  # normalized URL with the real hostname (what the learner sees and cites)
    scheme: str
    host: str  # lowercase ASCII (IDNA) hostname or IP literal, no brackets
    port: int
    path: str  # path + "?query", never empty


def host_of(url: str) -> str:
    """Hostname for the audit log / messages; never the path or query."""
    try:
        return (urlsplit(url).hostname or "?")[:253]
    except ValueError:
        return "?"


def parse_target(url: str, blocked_hosts: Iterable[str] = ()) -> Target:
    """Validate scheme, port, credentials and hostname (no DNS yet)."""
    url = (url or "").strip()
    if not url or len(url) > MAX_URL_CHARS or _CONTROL.search(url) or any(c.isspace() for c in url):
        raise WebFetchError(400, "invalid URL", "bad_url")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise WebFetchError(400, "invalid URL", "bad_url") from exc
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise _blocked("only http and https URLs can be fetched")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise _blocked("URLs with credentials are not fetched")
    port = port if port is not None else (443 if scheme == "https" else 80)
    if port not in ALLOWED_PORTS:
        raise _blocked("only ports 80 and 443 are allowed")
    host = (parts.hostname or "").rstrip(".")
    if not host:
        raise WebFetchError(400, "URL has no host", "bad_url")
    if _parse_ip(host) is None:
        try:
            host = host.encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise WebFetchError(400, "invalid hostname", "bad_url") from exc
        blocked = {h.lower().rstrip(".") for h in blocked_hosts if h}
        if (host in BLOCKED_HOSTS or host in blocked or "." not in host or host.endswith(BLOCKED_SUFFIXES)
                or not re.fullmatch(r"[a-z0-9.-]+", host)):
            raise _blocked(f"host {host} is internal or not allowed")
    netloc = f"[{host}]" if ":" in host else host
    if port != (443 if scheme == "https" else 80):
        netloc += f":{port}"
    path = parts.path or "/"
    if parts.query:
        path += f"?{parts.query}"
    return Target(urlunsplit((scheme, netloc, parts.path or "/", parts.query, "")), scheme, host, port, path)


async def system_resolver(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM,
                                                         proto=socket.IPPROTO_TCP)
    return [str(info[4][0]) for info in infos]


# ---- text extraction ----------------------------------------------------------------------------

SKIP_TAGS = frozenset({"script", "style", "noscript", "template", "svg", "math", "nav", "footer", "iframe",
                       "object", "canvas", "select", "head"})
BLOCK_TAGS = frozenset({"p", "div", "section", "article", "main", "header", "aside", "ul", "ol", "dl", "dt", "dd",
                        "table", "tr", "blockquote", "pre", "figure", "figcaption", "form", "fieldset", "address",
                        "details", "summary", "caption", "hr", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li"})


class _TextExtractor(HTMLParser):
    """Readable text: drops script/style/nav/footer/..., keeps link text, one line per block element."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self._skip: list[str] = []
        self._in_title = False
        self._title_done = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":  # the document title only: not a second one, not <svg><title>
            self._in_title = not self._title_done and set(self._skip) <= {"head"}
            return
        if tag in SKIP_TAGS:
            self._skip.append(tag)
            return
        if self._skip:
            return
        if tag in BLOCK_TAGS:
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("- ")
        elif tag in ("h1", "h2", "h3"):
            self.parts.append("#" * int(tag[1]) + " ")
        elif tag in ("td", "th"):
            self.parts.append(" | ")
        elif tag == "img":
            alt = dict(attrs).get("alt")
            if alt:
                self.parts.append(f" {alt} ")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in SKIP_TAGS:  # <br/>, <img/>; a self-closed skip tag must not open a skip region
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._title_done = self._title_done or self._in_title
            self._in_title = False
            return
        if self._skip:
            if tag in self._skip:
                while self._skip and self._skip.pop() != tag:
                    pass
            return
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        elif not self._skip:
            self.parts.append(data)


def _collapse(text: str) -> str:
    text = _CONTROL.sub("", unicodedata.normalize("NFC", text))
    lines = []
    for raw in text.split("\n"):
        line = " ".join(raw.split())
        line = re.sub(r"^\| ", "", line).removesuffix(" |")
        if not line:
            continue  # compact: no blank lines, except one before each heading
        if line.startswith("#") and lines:
            lines.append("")
        lines.append(line)
    return "\n".join(lines).strip()


def html_to_text(markup: str) -> tuple[str, str]:
    """`(title, text)` from an HTML document."""
    parser = _TextExtractor()
    with contextlib.suppress(AssertionError, ValueError):  # rare html.parser errors: keep what was extracted
        parser.feed(markup)
        parser.close()
    return clean_text("".join(parser.title_parts), TITLE_CHARS), _collapse("".join(parser.parts))


_META_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?\s*([A-Za-z0-9_.:-]+)""", re.IGNORECASE)


def _charset(content_type_header: str, body: bytes, is_html: bool) -> str:
    candidates = []
    if m := re.search(r"charset\s*=\s*\"?([A-Za-z0-9_.:-]+)", content_type_header, re.IGNORECASE):
        candidates.append(m.group(1))
    if is_html and (m := _META_CHARSET.search(body[:4096])):
        candidates.append(m.group(1).decode("ascii", "ignore"))
    for name in candidates:
        try:
            return codecs.lookup(name).name
        except LookupError:
            continue
    return "utf-8"


# ---- the service --------------------------------------------------------------------------------


class _Decoder:
    """Bounded Content-Encoding decoding (gzip/deflate); a compression bomb stops at the size cap."""

    def __init__(self, encoding: str) -> None:
        encoding = encoding.strip().lower()
        if encoding in ("", "identity"):
            self._z = None
        elif encoding in ("gzip", "x-gzip"):
            self._z = zlib.decompressobj(16 + zlib.MAX_WBITS)
        elif encoding == "deflate":
            self._z = zlib.decompressobj()
        else:
            raise WebFetchError(502, f"unsupported content encoding {encoding[:20]}", "upstream")

    def feed(self, chunk: bytes, room: int) -> bytes:
        if self._z is None:
            return chunk
        try:
            return self._z.decompress(chunk, max(room, 1))
        except zlib.error as exc:
            raise WebFetchError(502, "corrupt compressed response", "upstream") from exc


class WebFetchService:
    def __init__(
        self,
        *,
        enabled: bool = True,
        blocked_hosts: Iterable[str] = (),
        resolver: Resolver = system_resolver,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_s: float = TIMEOUT_S,
        max_body_bytes: int = MAX_BODY_BYTES,
        max_text_chars: int = MAX_TEXT_CHARS,
        max_pdf_bytes: int = MAX_PDF_BYTES,
        pdf_timeout_s: float = PDF_TIMEOUT_S,
    ) -> None:
        self.enabled = enabled
        self.blocked_hosts = frozenset(h.lower().rstrip(".") for h in blocked_hosts if h)
        self.resolver = resolver
        self.transport = transport  # tests: httpx.MockTransport; None = a fresh AsyncHTTPTransport per fetch
        self.timeout_s = timeout_s
        self.max_body_bytes = max_body_bytes
        self.max_text_chars = max_text_chars
        self.max_pdf_bytes = max_pdf_bytes
        self.pdf_timeout_s = pdf_timeout_s

    @classmethod
    def from_settings(cls, settings: Any) -> "WebFetchService":
        urls = [settings.public_base_url, settings.web_origin, settings.sandbox_gateway_url, settings.model_router_url,
                settings.searxng_url, *(settings.extra_origins or "").split(",")]
        hosts = {host_of(u) for u in urls if u and u.strip()} - {"?"}
        if settings.inbound_email_domain:
            hosts.add(settings.inbound_email_domain)
        pdf_mb = min(max(int(getattr(settings, "web_fetch_pdf_max_mb", 30) or 30), 1), PDF_MAX_MB_LIMIT)
        return cls(enabled=settings.web_fetch_enabled, blocked_hosts=hosts, max_pdf_bytes=pdf_mb * 1_000_000)

    async def fetch(self, url: str) -> dict[str, Any]:
        """`{url, final_url, title, text, truncated, content_type}`; raises `WebFetchError` (415 `pdf` for a PDF)."""
        return await self._run(url, self._read, PAGE_ACCEPT, self.timeout_s)

    async def download_pdf(self, url: str) -> dict[str, Any]:
        """`{url, final_url, data: bytes}` of a PDF (bytes only, never parsed here); raises `WebFetchError`."""
        return await self._run(url, self._read_pdf, PDF_ACCEPT, self.pdf_timeout_s)

    async def _run(self, url: str, reader: "Reader", accept: str, timeout_s: float) -> dict[str, Any]:
        if not self.enabled:
            raise WebFetchError(503, "web fetch is disabled on this gateway (WEB_FETCH_ENABLED=false)", "disabled")
        target = parse_target(url, self.blocked_hosts)
        try:
            async with asyncio.timeout(timeout_s):
                return await self._fetch(target, reader, accept)
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise WebFetchError(504, f"{target.host} timed out", "timeout") from exc

    async def _vetted_ip(self, target: Target) -> str:
        if (literal := _parse_ip(target.host)) is not None:
            if not ip_allowed(literal):
                raise _blocked("the address is private or reserved")
            return str(literal)
        try:
            addresses = await self.resolver(target.host, target.port)
        except (OSError, UnicodeError) as exc:
            raise WebFetchError(502, f"could not resolve {target.host}", "dns") from exc
        ips = []
        for raw in addresses:
            ip = _parse_ip(str(raw).split("%", 1)[0])
            if ip is None or not ip_allowed(ip) or "%" in str(raw):
                raise _blocked(f"{target.host} resolves to a private or reserved address")
            ips.append(ip)
        if not ips:
            raise WebFetchError(502, f"could not resolve {target.host}", "dns")
        # every answer was vetted; prefer IPv4 (sandbox hosts / docker often lack IPv6 routes)
        return str(next((ip for ip in ips if ip.version == 4), ips[0]))

    async def _fetch(self, target: Target, reader: "Reader", accept: str) -> dict[str, Any]:
        requested = target.url
        for hop in range(MAX_REDIRECTS + 1):
            ip = await self._vetted_ip(target)
            transport = self.transport or httpx.AsyncHTTPTransport(retries=0)
            try:
                resp = await self._send(transport, target, ip, accept)
                try:
                    if resp.status_code in (301, 302, 303, 307, 308):
                        location = resp.headers.get("location", "").strip()
                        if not location:
                            raise WebFetchError(502, f"{target.host} sent a redirect without Location",
                                                upstream_status=resp.status_code)
                        if hop == MAX_REDIRECTS:
                            raise WebFetchError(502, f"more than {MAX_REDIRECTS} redirects", "too_many_redirects")
                        target = parse_target(urljoin(target.url, location), self.blocked_hosts)
                        continue
                    if resp.status_code != 200:
                        raise WebFetchError(502, f"{target.host} returned HTTP {resp.status_code}", "http_error",
                                            upstream_status=resp.status_code)
                    return await reader(resp, requested, target)
                finally:
                    await resp.aclose()
            except httpx.TimeoutException:
                raise
            except httpx.HTTPError as exc:
                if "CERTIFICATE" in str(exc).upper():
                    raise WebFetchError(502, f"{target.host}: TLS certificate check failed", "tls") from exc
                raise WebFetchError(502, f"{target.host} unreachable: {exc.__class__.__name__}") from exc
            finally:
                if self.transport is None:
                    await transport.aclose()
        raise AssertionError("unreachable")  # pragma: no cover

    async def _send(self, transport: httpx.AsyncBaseTransport, target: Target, ip: str,
                    accept: str = PAGE_ACCEPT) -> httpx.Response:
        ip_host = f"[{ip}]" if ":" in ip else ip
        default_port = 443 if target.scheme == "https" else 80
        host_header = target.host if target.port == default_port else f"{target.host}:{target.port}"
        if ":" in target.host:  # IPv6 literal
            host_header = f"[{target.host}]" + ("" if target.port == default_port else f":{target.port}")
        request = httpx.Request(
            "GET",
            f"{target.scheme}://{ip_host}:{target.port}{target.path}",
            headers={
                "Host": host_header,
                "User-Agent": USER_AGENT,
                "Accept": accept,
                "Accept-Language": "vi,en;q=0.8",
                "Accept-Encoding": "gzip, deflate",
            },
            extensions={
                "timeout": {"connect": self.timeout_s, "read": self.timeout_s, "write": self.timeout_s,
                            "pool": self.timeout_s},
                # TLS: SNI and certificate verification use the real hostname, the TCP connection the vetted IP
                **({"sni_hostname": target.host} if target.scheme == "https" and _parse_ip(target.host) is None
                   else {}),
            },
        )
        return await transport.handle_async_request(request)

    async def _read_body(self, resp: httpx.Response, cap: int, *, too_large: str | None = None,
                         require_magic: bool = False) -> tuple[bytes, bool]:
        """`(body, truncated)`: at most `cap` bytes, raw and decoded. With `too_large` set, going over the cap raises
        413 `too_large` instead of truncating. `require_magic` raises 415 `not_pdf` as soon as the first
        `PDF_MAGIC_WINDOW` bytes lack the PDF header (an HTML page is not downloaded in full)."""
        decoder = _Decoder(resp.headers.get("content-encoding", ""))
        chunks, size, raw_size, checked = [], 0, 0, not require_magic
        async for chunk in resp.stream:  # raw bytes; works for streamed and pre-read (test) responses
            raw_size += len(chunk)
            data = decoder.feed(chunk, cap - size + 1)
            size += len(data)
            chunks.append(data)
            if not checked and size >= PDF_MAGIC_WINDOW:
                checked = True
                if not has_pdf_magic(b"".join(chunks)):
                    raise _not_pdf()
            if size > cap or raw_size > cap:
                if too_large is not None:
                    raise WebFetchError(413, too_large, "too_large")
                return b"".join(chunks)[:cap], True
        return b"".join(chunks), False

    async def _read(self, resp: httpx.Response, requested: str, target: Target) -> dict[str, Any]:
        header = resp.headers.get("content-type", "")
        mime = header.split(";", 1)[0].strip().lower()
        if mime in PDF_TYPES:
            raise _is_pdf()
        if mime not in HTML_TYPES and mime not in TEXT_TYPES:
            # application/octet-stream, no type, a .pdf path...: a PDF only if the bytes say so
            head, _ = await self._read_body(resp, PDF_MAGIC_WINDOW)
            if has_pdf_magic(head):
                raise _is_pdf()
            raise WebFetchError(415, f"unsupported content type {mime[:60] or '(none)'}; only HTML, plain text and "
                                "JSON pages (and PDFs)", "unsupported_type")
        body, truncated = await self._read_body(resp, self.max_body_bytes)
        if body.startswith(PDF_MAGIC):  # a PDF served as text
            raise _is_pdf()
        text = body.decode(_charset(header, body, mime in HTML_TYPES), errors="replace")
        if mime in HTML_TYPES:
            title, text = html_to_text(text)
        else:
            title = ""
            if mime == "application/json":
                try:
                    text = json.dumps(json.loads(text), ensure_ascii=False, indent=1)
                except ValueError:
                    pass
            text = _collapse(text)
        if len(text) > self.max_text_chars:
            text, truncated = text[: self.max_text_chars].rstrip() + "…", True
        return {"url": requested, "final_url": target.url, "title": title, "text": text, "truncated": truncated,
                "content_type": mime}

    async def _read_pdf(self, resp: httpx.Response, requested: str, target: Target) -> dict[str, Any]:
        mime = resp.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if mime in HTML_TYPES:  # a landing page, not the file; any other type is checked by the magic bytes
            raise WebFetchError(415, f"not a PDF ({mime})", "not_pdf")
        cap = self.max_pdf_bytes
        too_large = f"the PDF is larger than {cap // 1_000_000} MB (WEB_FETCH_PDF_MAX_MB)"
        declared = resp.headers.get("content-length", "").strip()
        if declared.isdigit() and int(declared) > cap:
            raise WebFetchError(413, too_large, "too_large")
        body, _ = await self._read_body(resp, cap, too_large=too_large, require_magic=True)
        if not has_pdf_magic(body):  # shorter than PDF_MAGIC_WINDOW
            raise _not_pdf()
        return {"url": requested, "final_url": target.url, "data": body}


Reader = Callable[[httpx.Response, str, Target], Awaitable[dict[str, Any]]]
