"""Where pictures can come from besides code-drawn SVG: image-generation APIs and reusable web images.

Two kinds of provider, both returning raw image bytes plus provenance:
  generated  `generate(prompt, w, h, seed) -> Fetched`   (self-hosted/OpenAI-compatible API, Cloudflare Workers AI FLUX,
             Gemini image, Pollinations (key), Hugging Face FLUX Space (no key, shared quota))
  web        `search(query, limit) -> [Candidate]` then `download(candidate) -> bytes`   (Openverse, Wikimedia Commons,
             Pexels, Pixabay). Only licences in IMAGE_WEB_LICENSES (default cc0, pdm, by, by-sa) are returned and the
             author / licence / source URL travel with the picture so the app can show a credit.

Configuration is read from the environment, then from `.env.dev.local` (same lookup as llm.py). Keys are never logged:
every error message is scrubbed of the secrets it could contain. Network failures raise ProviderError; a provider that
says "no quota" / "unauthorised" is switched off for the rest of the process (see `trip`).
See services/course-builder/README-images.md for the variable list.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from urllib.parse import quote

import httpx

from mentor_course_builder.llm import _find_env_file, _read_env_file

log = logging.getLogger("mentor_course_builder")

ENV_KEYS = {
    "IMAGE_SOURCES", "IMAGE_API_BASE", "IMAGE_API_KEY", "IMAGE_API_MODEL", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN",
    "IMAGE_CF_MODEL", "GEMINI_API_KEY", "IMAGE_GEMINI_MODEL", "IMAGE_GEMINI_ENABLE", "POLLINATIONS_API_KEY",
    "IMAGE_POLLINATIONS_ANON", "HF_SPACE_URL", "HF_TOKEN", "PEXELS_API_KEY", "PIXABAY_API_KEY", "IMAGE_WEB_LICENSES",
    "IMAGE_MIN_SCORE", "IMAGE_MAX_CRITIQUES", "IMAGE_GEN_TRIES", "IMAGE_WEB_CANDIDATES", "IMAGE_MAX_BYTES",
    "IMAGE_HTTP_TIMEOUT", "IMAGE_USER_AGENT",
}
_file_cache: dict[str, str] | None = None


def cfg(name: str, default: str = "") -> str:
    """Environment first, then .env.dev.local; empty string when unset."""
    global _file_cache
    v = os.environ.get(name)
    if v is not None:
        return v.strip()
    if name not in ENV_KEYS:
        return default
    if _file_cache is None:
        f = _find_env_file()
        try:
            _file_cache = _read_env_file(f, ENV_KEYS) if f and f.is_file() else {}
        except OSError:
            _file_cache = {}
    return _file_cache.get(name, default).strip()


def _secrets() -> list[str]:
    names = ("IMAGE_API_KEY", "CLOUDFLARE_API_TOKEN", "GEMINI_API_KEY", "POLLINATIONS_API_KEY", "HF_TOKEN",
             "PEXELS_API_KEY", "PIXABAY_API_KEY")
    return [s for s in (cfg(n) for n in names) if len(s) >= 8]


def scrub(text: str) -> str:
    for s in _secrets():
        text = text.replace(s, "***")
    return text


class ProviderError(Exception):
    """A source failed (network, quota, bad payload). The message never contains a key."""

    def __init__(self, msg: str, *, fatal: bool = False):
        super().__init__(scrub(msg))
        self.fatal = fatal  # True: do not try this provider again in this process (no quota / bad key)


@dataclass
class Fetched:
    data: bytes
    provider: str
    kind: str  # "generated" | "web"
    model: str = ""
    attribution: dict | None = None  # web: {title, author, license, license_url, source_url, provider}


@dataclass
class Candidate:
    provider: str
    url: str
    title: str = ""
    author: str = ""
    license: str = ""  # normalised: cc0 | pdm | by | by-sa | provider-specific token
    license_url: str = ""
    source_url: str = ""
    width: int = 0
    height: int = 0

    def attribution(self) -> dict:
        return {"provider": self.provider, "title": self.title, "author": self.author, "license": self.license,
                "license_url": self.license_url, "source_url": self.source_url}


# ------------------------------------------------------------------------------------------------ circuit breaker

_tripped: dict[str, float] = {}


def trip(name: str, seconds: float = 900.0) -> None:
    _tripped[name] = time.monotonic() + seconds


def is_tripped(name: str) -> bool:
    return _tripped.get(name, 0.0) > time.monotonic()


def reset_trips() -> None:
    _tripped.clear()


# ------------------------------------------------------------------------------------------------ http helpers

MAX_DOWNLOAD = 12_000_000


def user_agent() -> str:
    return cfg("IMAGE_USER_AGENT") or "mentor-course-builder/0.1 (+https://mentor.example/contact; set IMAGE_USER_AGENT to your contact) httpx"


def make_http() -> httpx.Client:
    t = float(cfg("IMAGE_HTTP_TIMEOUT") or 60)
    return httpx.Client(timeout=httpx.Timeout(t, connect=15.0), headers={"User-Agent": user_agent()}, follow_redirects=True)


def _check(r: httpx.Response, name: str) -> None:
    if r.status_code in (401, 403):
        raise ProviderError(f"{name}: not authorised (HTTP {r.status_code})", fatal=True)
    if r.status_code == 402:
        raise ProviderError(f"{name}: payment required / quota used up", fatal=True)
    if r.status_code == 429:
        raise ProviderError(f"{name}: rate limited (HTTP 429)", fatal=r.headers.get("retry-after", "0").isdigit()
                            and int(r.headers.get("retry-after", "0")) > 120)
    if r.status_code >= 400:
        raise ProviderError(f"{name}: HTTP {r.status_code} {r.text[:160]!r}")


def _guard(name: str, fn):
    try:
        return fn()
    except ProviderError:
        raise
    except httpx.HTTPError as exc:
        raise ProviderError(f"{name}: network error {type(exc).__name__}") from None
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise ProviderError(f"{name}: unexpected response ({type(exc).__name__})") from None


def download(http: httpx.Client, url: str, name: str, *, headers: dict | None = None) -> bytes:
    if not url.lower().startswith("https://"):
        raise ProviderError(f"{name}: refusing non-https image url")
    buf = bytearray()

    def run():
        with http.stream("GET", url, headers=headers or {}) as r:
            _check(r, name)
            ct = r.headers.get("content-type", "").split(";")[0].strip().lower()
            if ct and not ct.startswith("image/") and ct != "application/octet-stream":
                raise ProviderError(f"{name}: not an image ({ct})")
            for chunk in r.iter_bytes():
                buf.extend(chunk)
                if len(buf) > MAX_DOWNLOAD:
                    raise ProviderError(f"{name}: image larger than {MAX_DOWNLOAD // 1_000_000} MB")
        return bytes(buf)

    return _guard(name, run)


def _seed(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:7], 16)


# ------------------------------------------------------------------------------------------------ generators

class Generator:
    name = ""
    kind = "generated"

    def available(self) -> bool:
        return False

    def generate(self, http: httpx.Client, prompt: str, w: int, h: int, seed: int) -> Fetched:
        raise NotImplementedError


class OpenAICompatGenerator(Generator):
    """Any OpenAI-style /images/generations endpoint: a self-hosted server (ComfyUI/SD.Next/LocalAI wrappers), Together,
    Pollinations `/v1/images/generations`, OpenAI itself. IMAGE_API_BASE includes the version prefix, e.g. https://x/v1."""

    name = "openai"

    def available(self) -> bool:
        return bool(cfg("IMAGE_API_BASE"))

    def generate(self, http, prompt, w, h, seed):
        base = cfg("IMAGE_API_BASE").rstrip("/")
        model = cfg("IMAGE_API_MODEL")
        key = cfg("IMAGE_API_KEY")
        body: dict = {"prompt": prompt, "n": 1, "size": f"{w}x{h}", "response_format": "b64_json"}
        if model:
            body["model"] = model

        def run():
            r = http.post(f"{base}/images/generations", json=body, headers={"Authorization": f"Bearer {key}"} if key else {})
            _check(r, self.name)
            item = r.json()["data"][0]
            if item.get("b64_json"):
                return Fetched(base64.b64decode(item["b64_json"]), self.name, "generated", model or "default")
            return Fetched(download(http, item["url"], self.name), self.name, "generated", model or "default")

        return _guard(self.name, run)


class CloudflareGenerator(Generator):
    """Workers AI FLUX.1 schnell (Apache-2.0 weights). Free: 10,000 neurons/day, no card; needs an account id + API token."""

    name = "cloudflare"

    def available(self) -> bool:
        return bool(cfg("CLOUDFLARE_ACCOUNT_ID") and cfg("CLOUDFLARE_API_TOKEN"))

    def generate(self, http, prompt, w, h, seed):
        model = cfg("IMAGE_CF_MODEL") or "@cf/black-forest-labs/flux-1-schnell"
        url = f"https://api.cloudflare.com/client/v4/accounts/{cfg('CLOUDFLARE_ACCOUNT_ID')}/ai/run/{model}"

        def run():
            r = http.post(url, json={"prompt": prompt[:2000], "steps": 6, "seed": seed},
                          headers={"Authorization": f"Bearer {cfg('CLOUDFLARE_API_TOKEN')}"})
            _check(r, self.name)
            if r.headers.get("content-type", "").startswith("image/"):
                return Fetched(r.content, self.name, "generated", model)
            b64 = r.json()["result"]["image"]
            return Fetched(base64.b64decode(b64), self.name, "generated", model)

        return _guard(self.name, run)


class GeminiGenerator(Generator):
    """Gemini image models. NOT free: on a free-tier key the quota for image models is 0 (verified Nov 2026), so it is only
    in the automatic chain when IMAGE_GEMINI_ENABLE=1 (a billed key)."""

    name = "gemini"

    def available(self) -> bool:
        return bool(cfg("GEMINI_API_KEY")) and (cfg("IMAGE_GEMINI_ENABLE") == "1" or "gemini" in _explicit())

    def generate(self, http, prompt, w, h, seed):
        model = cfg("IMAGE_GEMINI_MODEL") or "gemini-2.5-flash-image"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

        def run():
            r = http.post(url, headers={"x-goog-api-key": cfg("GEMINI_API_KEY")},
                          json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseModalities": ["IMAGE"]}})
            if r.status_code == 429:
                raise ProviderError("gemini: quota exceeded (image models have no free tier)", fatal=True)
            _check(r, self.name)
            for cand in r.json().get("candidates", []):
                for part in cand.get("content", {}).get("parts", []):
                    d = part.get("inlineData") or part.get("inline_data")
                    if d and d.get("data"):
                        return Fetched(base64.b64decode(d["data"]), self.name, "generated", model)
            raise ProviderError("gemini: reply had no image (blocked or text-only)")

        return _guard(self.name, run)


class PollinationsGenerator(Generator):
    """Pollinations. With POLLINATIONS_API_KEY (free key from enter.pollinations.ai) uses gen.pollinations.ai. Without a
    key the legacy anonymous endpoint answers 402 often, falls back to a small model and stamps a logo, so it is used only
    when IMAGE_POLLINATIONS_ANON=1."""

    name = "pollinations"

    def available(self) -> bool:
        return bool(cfg("POLLINATIONS_API_KEY")) or cfg("IMAGE_POLLINATIONS_ANON") == "1"

    def generate(self, http, prompt, w, h, seed):
        key = cfg("POLLINATIONS_API_KEY")
        q = f"width={w}&height={h}&seed={seed}&nologo=true"
        if key:
            url, headers = f"https://gen.pollinations.ai/image/{quote(prompt[:1500])}?{q}", {"Authorization": f"Bearer {key}"}
        else:
            url, headers = f"https://image.pollinations.ai/prompt/{quote(prompt[:1500])}?{q}&model=flux", {}

        def run():
            r = http.get(url, headers=headers)
            _check(r, self.name)
            if not r.headers.get("content-type", "").startswith("image/"):
                raise ProviderError("pollinations: reply is not an image")
            return Fetched(r.content, self.name, "generated", "pollinations" + ("" if key else "-anon"))

        return _guard(self.name, run)


class HFSpaceGenerator(Generator):
    """The public FLUX.1-schnell Space on Hugging Face (Apache-2.0 model) through its Gradio API. No key; it runs on a
    shared ZeroGPU quota (a few images per IP, more with HF_TOKEN of a free account), so it is a best-effort source."""

    name = "hf_space"

    def available(self) -> bool:
        return True

    def generate(self, http, prompt, w, h, seed):
        base = (cfg("HF_SPACE_URL") or "https://black-forest-labs-flux-1-schnell.hf.space").rstrip("/") + "/gradio_api"
        headers = {"Authorization": f"Bearer {cfg('HF_TOKEN')}"} if cfg("HF_TOKEN") else {}
        w, h = (min(2048, max(256, round(v / 32) * 32)) for v in (w, h))

        def run():
            r = http.post(f"{base}/call/infer", json={"data": [prompt, seed % 2_147_483_647, False, w, h, 4]}, headers=headers)
            _check(r, self.name)
            eid = r.json()["event_id"]
            event, data = "", ""
            with http.stream("GET", f"{base}/call/infer/{eid}", headers=headers) as s:
                _check(s, self.name)
                for line in s.iter_lines():
                    if line.startswith("event:"):
                        event = line[6:].strip()
                    elif line.startswith("data:"):
                        data = line[5:].strip()
                        if event in ("complete", "error"):
                            break
            if event != "complete":
                raise ProviderError("hf_space: generation failed (shared GPU quota is probably used up)", fatal=True)
            url = json.loads(data)[0]["url"]
            if not url.startswith(base.split("/gradio_api")[0]):
                raise ProviderError("hf_space: unexpected file host")
            return Fetched(download(http, url, self.name), self.name, "generated", "FLUX.1-schnell (HF Space)")

        return _guard(self.name, run)


# ------------------------------------------------------------------------------------------------ web search

def allowed_licenses() -> set[str]:
    return {x.strip().lower() for x in (cfg("IMAGE_WEB_LICENSES") or "cc0,pdm,by,by-sa").split(",") if x.strip()}


def normalise_license(text: str) -> str:
    """'CC BY-SA 4.0' -> 'by-sa', 'Public domain' -> 'pdm', 'CC0' -> 'cc0'; '' when unknown."""
    t = text.lower().replace("_", "-")
    if "cc0" in t or "cc-zero" in t or "public domain dedication" in t:
        return "cc0"
    if "public domain" in t or t.strip() in ("pd", "pdm") or "pd-" in t:
        return "pdm"
    m = re.search(r"\bcc[- ]by(?:[- ](sa|nc|nd|nc-sa|nc-nd))?\b", t)
    if m:
        return "by" + (f"-{m.group(1)}" if m.group(1) else "")
    return ""


def strip_html(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()[:200]


class WebSource:
    name = ""
    kind = "web"

    def available(self) -> bool:
        return True

    def search(self, http: httpx.Client, query: str, limit: int) -> list[Candidate]:
        raise NotImplementedError

    def fetch(self, http: httpx.Client, c: Candidate) -> bytes:
        return download(http, c.url, self.name)


class OpenverseSource(WebSource):
    """api.openverse.org: CC/public-domain images from Flickr, Wikimedia, etc. Anonymous: 20/min, 200/day."""

    name = "openverse"

    def search(self, http, query, limit):
        lic = ",".join(sorted(allowed_licenses() & {"cc0", "pdm", "by", "by-sa"})) or "cc0,pdm"

        def run():
            r = http.get("https://api.openverse.org/v1/images/", params={"q": query, "license": lic, "mature": "false",
                                                                          "page_size": min(20, limit * 3), "extension": "jpg,png"})
            _check(r, self.name)
            out = []
            for it in r.json().get("results", []):
                token = it.get("license", "")
                if token in ("cc0", "pdm", "by", "by-sa"):
                    out.append(Candidate(self.name, it["url"], it.get("title") or "", it.get("creator") or "", token,
                                         it.get("license_url") or "", it.get("foreign_landing_url") or "",
                                         it.get("width") or 0, it.get("height") or 0))
            return out

        return _guard(self.name, run)


class WikimediaSource(WebSource):
    """commons.wikimedia.org API: licence and author come from extmetadata. No key; be polite (User-Agent)."""

    name = "wikimedia"

    def search(self, http, query, limit):
        def run():
            r = http.get("https://commons.wikimedia.org/w/api.php", params={
                "action": "query", "generator": "search", "gsrnamespace": 6, "gsrsearch": f"filetype:bitmap {query}",
                "gsrlimit": min(30, limit * 4), "prop": "imageinfo", "iiprop": "url|extmetadata|size|mime",
                "iiurlwidth": 1280, "format": "json"})
            _check(r, self.name)
            out = []
            for p in (r.json().get("query", {}).get("pages") or {}).values():
                info = (p.get("imageinfo") or [{}])[0]
                meta = info.get("extmetadata") or {}
                if info.get("mime") not in ("image/jpeg", "image/png", "image/webp"):
                    continue
                tok = normalise_license((meta.get("LicenseShortName") or {}).get("value", ""))
                if not tok:
                    continue
                out.append(Candidate(self.name, info.get("thumburl") or info.get("url", ""), strip_html(p.get("title", "")),
                                     strip_html((meta.get("Artist") or {}).get("value", "")), tok,
                                     (meta.get("LicenseUrl") or {}).get("value", ""), info.get("descriptionurl", ""),
                                     info.get("thumbwidth") or info.get("width") or 0, info.get("thumbheight") or info.get("height") or 0))
            return out

        return _guard(self.name, run)


class PexelsSource(WebSource):
    """Pexels API: free key (200/h, 20k/month). Pexels licence: free to use, no attribution legally required, the API terms
    ask for a visible credit to Pexels and the photographer, which the metadata supports."""

    name = "pexels"

    def available(self):
        return bool(cfg("PEXELS_API_KEY"))

    def search(self, http, query, limit):
        def run():
            r = http.get("https://api.pexels.com/v1/search", params={"query": query, "per_page": min(20, limit * 2)},
                         headers={"Authorization": cfg("PEXELS_API_KEY")})
            _check(r, self.name)
            return [Candidate(self.name, p["src"]["large"], p.get("alt") or "", p.get("photographer") or "", "pexels",
                              "https://www.pexels.com/license/", p.get("url", ""), p.get("width") or 0, p.get("height") or 0)
                    for p in r.json().get("photos", [])]

        return _guard(self.name, run)


class PixabaySource(WebSource):
    """Pixabay API: free key (100 req/min). Pixabay Content Licence: free for commercial use, no attribution needed; images
    must be downloaded (no hotlinking), which is what we do."""

    name = "pixabay"

    def available(self):
        return bool(cfg("PIXABAY_API_KEY"))

    def search(self, http, query, limit):
        def run():
            r = http.get("https://pixabay.com/api/", params={"key": cfg("PIXABAY_API_KEY"), "q": query, "safesearch": "true",
                                                              "image_type": "illustration", "per_page": max(3, min(20, limit * 2))})
            _check(r, self.name)
            return [Candidate(self.name, h["largeImageURL"], h.get("tags") or "", h.get("user") or "", "pixabay",
                              "https://pixabay.com/service/license-summary/", h.get("pageURL", ""),
                              h.get("imageWidth") or 0, h.get("imageHeight") or 0) for h in r.json().get("hits", [])]

        return _guard(self.name, run)


# ------------------------------------------------------------------------------------------------ registry

GENERATORS: dict[str, Generator] = {g.name: g for g in (OpenAICompatGenerator(), CloudflareGenerator(), GeminiGenerator(),
                                                         PollinationsGenerator(), HFSpaceGenerator())}
WEB_SOURCES: dict[str, WebSource] = {s.name: s for s in (PexelsSource(), PixabaySource(), OpenverseSource(), WikimediaSource())}
DEFAULT_GEN_ORDER = ["openai", "cloudflare", "gemini", "pollinations", "hf_space"]
DEFAULT_WEB_ORDER = ["pixabay", "pexels", "openverse", "wikimedia"]


def _explicit() -> list[str]:
    raw = cfg("IMAGE_SOURCES").lower()
    if raw in ("", "auto"):
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def source_order(restrict: str | None = None) -> list[str]:
    """Ordered source ids to try after the accuracy check; "code" means code-drawn SVG and is always last unless listed.

    IMAGE_SOURCES: "auto" (default: every configured generator, then every available web source, then code),
    "code"/"svg"/"none" (never leave code-drawn), or a comma list such as "cloudflare,openverse,code".
    `restrict` ("gen" | "web" | "code") comes from MediaRequest.spec["source"] and narrows the list.
    """
    raw = cfg("IMAGE_SOURCES").lower()
    if raw in ("code", "svg", "none", "off"):
        return ["code"]
    ids = _explicit() or DEFAULT_GEN_ORDER + DEFAULT_WEB_ORDER
    ids = [i for i in ids if i in GENERATORS or i in WEB_SOURCES or i == "code"]
    if "code" not in ids:
        ids.append("code")
    if restrict == "code":
        return ["code"]
    if restrict == "gen":
        ids = [i for i in ids if i in GENERATORS or i == "code"]
    elif restrict == "web":
        ids = [i for i in ids if i in WEB_SOURCES or i == "code"]
    out = []
    for i in ids:
        if i == "code":
            out.append(i)
        elif i in GENERATORS and GENERATORS[i].available() and not is_tripped(i):
            out.append(i)
        elif i in WEB_SOURCES and WEB_SOURCES[i].available() and not is_tripped(i):
            out.append(i)
    return out
