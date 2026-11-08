"""Text-to-speech for the media stage (REQUIREMENTS-PLAN §12 Q9: the cheapest option).

Chain per clip: Edge voice (retry) -> the other Edge voice -> Gemini TTS (free tier: 3 requests/minute, so calls go
through a rate-limited queue that also honours "retry in Ns"). Output is always MP3 (ffmpeg transcode) and cached by
hash(text, voice, rate, lang) so re-running a course costs nothing.

Licences: `edge-tts` is LGPL-3.0; it is only imported as an unmodified library (no copy or patch of its code), which
LGPL allows. It talks to Microsoft's Edge read-aloud endpoint, which has no SLA: hence the Gemini fallback.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import logging
import os
import re
import threading
import time
import wave
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import httpx

from mentor_course_builder.llm import _find_env_file, _read_env_file
from mentor_course_builder.media import MediaError, _run, require_ffmpeg

log = logging.getLogger("mentor_course_builder")

# (language, gender) -> Edge voice
EDGE_VOICES: dict[tuple[str, str], str] = {
    ("vi", "female"): "vi-VN-HoaiMyNeural",
    ("vi", "male"): "vi-VN-NamMinhNeural",
    ("en", "female"): "en-US-AriaNeural",
    ("en", "male"): "en-US-GuyNeural",
}
GEMINI_TTS_MODEL = "gemini-3.8-flash-lite-tts"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
GEMINI_VOICE = {"female": "Kore", "male": "Charon"}
RATE_SLOW, RATE_NORMAL = "-15%", "+0%"


class TtsError(Exception):
    pass


class RateLimited(TtsError):
    def __init__(self, msg: str, retry_after_s: float) -> None:
        super().__init__(msg)
        self.retry_after_s = retry_after_s


_SPOKEN = {
    "vi": {"+": " cộng ", "-": " trừ ", "=": " bằng ", "*": " nhân ", "/": " chia ", "<": " nhỏ hơn ", ">": " lớn hơn ",
           "\\pi": " pi ", "\\times": " nhân ", "\\cdot": " nhân ", "\\div": " chia ", "\\leq": " nhỏ hơn hoặc bằng ",
           "\\geq": " lớn hơn hoặc bằng ", "\\neq": " khác ", "\\approx": " xấp xỉ ", "^2": " bình phương ",
           "^3": " lập phương "},
    "en": {"+": " plus ", "-": " minus ", "=": " equals ", "*": " times ", "/": " over ", "<": " is less than ",
           ">": " is greater than ", "\\pi": " pi ", "\\times": " times ", "\\cdot": " times ", "\\div": " divided by ",
           "\\leq": " is at most ", "\\geq": " is at least ", "\\neq": " is not equal to ", "\\approx": " is about ",
           "^2": " squared ", "^3": " cubed "}}


def speakable(text: str, lang: str = "vi") -> str:
    """Read-aloud text from lesson Markdown: no `**`, `#`, bullets or `$`, and simple formulas spoken as words.

    Edge's voice returns no audio for a text that is only symbols, and reads "dollar x caret two" for raw LaTeX; both
    used to push clips to the slow Gemini fallback. Commands it cannot say are dropped, never read out.
    """
    words = _SPOKEN.get(lang, _SPOKEN["en"])
    over, root, power = (("chia", "căn bậc hai của", "mũ") if lang == "vi" else ("over", "square root of", "to the power"))

    def math(m: re.Match) -> str:
        t = (m.group(1) if m.group(1) is not None else m.group(2)) or ""
        t = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", lambda x: f" {x.group(1)} {over} {x.group(2)} ", t)
        t = re.sub(r"\\sqrt\{([^{}]*)\}", lambda x: f" {root} {x.group(1)} ", t)
        t = re.sub(r"\^\{?(\d+)\}?", lambda x: words.get("^" + x.group(1), f" {power} {x.group(1)} "), t)
        for k in sorted((k for k in words if k.startswith("\\")), key=len, reverse=True):
            t = t.replace(k, words[k])
        for k, v in words.items():
            if not k.startswith(("\\", "^")):
                t = t.replace(k, v)
        t = re.sub(r"\\[A-Za-z]+", " ", t)
        return " " + re.sub(r"[{}_\\]", " ", t) + " "

    t = re.sub(r"\$\$(.+?)\$\$|\$([^$\n]+)\$", math, text, flags=re.S)
    t = re.sub(r"```.*?```", " ", t, flags=re.S)
    t = re.sub(r"^\s{0,3}(?:#{1,6}|[-*+]|\d+[.)])\s+", "", t, flags=re.M)
    t = re.sub(r"\*\*|__|`|~~", "", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"(?<!\w)[*_](?=\S)|(?<=\S)[*_](?!\w)", "", t)
    return " ".join(t.split())



def rate_for(age_band: str, rate: str | None) -> str:
    """Spec rate ("slow"|"normal") or, by default, slow for grades 1-5."""
    if rate in ("slow", "normal"):
        return RATE_SLOW if rate == "slow" else RATE_NORMAL
    if rate and re.fullmatch(r"[+-]\d+%", rate):
        return rate
    return RATE_SLOW if age_band == "g1_5" else RATE_NORMAL


def pcm_to_wav(pcm: bytes, sample_rate: int = 24000, channels: int = 1, width: int = 2) -> bytes:
    """Wrap raw 16-bit mono PCM (what Gemini TTS returns) as WAV. Bytes that are already RIFF pass through."""
    if pcm[:4] == b"RIFF":
        return pcm
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


def find_audio_b64(obj: Any) -> tuple[bytes, str] | None:
    """Locate base64 audio anywhere in a Gemini response. Returns (bytes, mime or "")."""
    best: tuple[bytes, str] | None = None
    stack: list[Any] = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            mime = str(cur.get("mime_type") or cur.get("mimeType") or "")
            for k, v in cur.items():
                if isinstance(v, str) and len(v) > 400 and k in ("data", "audio", "inline_data", "bytes", "content"):
                    try:
                        raw = base64.b64decode(v, validate=False)
                    except Exception:
                        continue
                    if best is None or len(raw) > len(best[0]):
                        best = (raw, mime)
                elif isinstance(v, (dict, list)):
                    stack.append(v)
        elif isinstance(cur, list):
            stack.extend(cur)
    return best


def parse_retry_after(text: str, default: float = 25.0) -> float:
    m = re.search(r"retry in ([0-9.]+)\s*s", text, re.I) or re.search(r'"retryDelay"\s*:\s*"([0-9.]+)s"', text)
    return float(m.group(1)) + 1.0 if m else default


class RateLimiter:
    """At most `per_minute` calls per rolling minute; thread-safe. Clock and sleep are injectable for tests."""

    def __init__(self, per_minute: int = 3, *, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.per_minute, self._clock, self._sleep = per_minute, clock, sleep
        self._stamps: list[float] = []
        self._lock = threading.Lock()
        self._blocked_until = 0.0

    def penalise(self, seconds: float) -> None:
        """A 429 said "retry in Ns": nothing goes out before then."""
        with self._lock:
            self._blocked_until = max(self._blocked_until, self._clock() + seconds)

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = self._clock()
                self._stamps = [t for t in self._stamps if now - t < 60.0]
                wait = max(self._blocked_until - now, 0.0)
                if len(self._stamps) >= self.per_minute:
                    wait = max(wait, 60.0 - (now - self._stamps[0]) + 0.05)
                if wait <= 0:
                    self._stamps.append(now)
                    return
            self._sleep(wait)


class TtsProvider(ABC):
    name: str

    @abstractmethod
    def synthesize(self, text: str, *, lang: str, gender: str, voice: str, rate: str) -> tuple[bytes, str]:
        """Return (audio bytes, extension without dot: "mp3" or "wav"). Raise TtsError on failure."""


class EdgeTtsProvider(TtsProvider):
    name = "edge-tts"

    def __init__(self, timeout_s: float = 40.0) -> None:
        self.timeout_s = timeout_s

    def synthesize(self, text: str, *, lang: str, gender: str, voice: str, rate: str) -> tuple[bytes, str]:
        try:
            import edge_tts
        except ImportError as exc:  # pragma: no cover
            raise TtsError("edge-tts is not installed") from exc

        async def go() -> bytes:
            comm = edge_tts.Communicate(text, voice, rate=rate)
            out = bytearray()
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    out += chunk["data"]
            return bytes(out)

        try:
            data = asyncio.run(asyncio.wait_for(go(), self.timeout_s))
        except Exception as exc:
            raise TtsError(f"edge-tts {voice}: {exc.__class__.__name__}: {str(exc)[:120]}") from exc
        if len(data) < 500:
            raise TtsError(f"edge-tts {voice}: empty audio")
        return data, "mp3"


def _gemini_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        f = _find_env_file()
        if f and f.is_file():
            key = _read_env_file(f, {"GEMINI_API_KEY"}).get("GEMINI_API_KEY", "")
    return key


class GeminiTtsProvider(TtsProvider):
    name = "gemini-tts"

    def __init__(self, api_key: str | None = None, *, limiter: RateLimiter | None = None,
                 transport: httpx.BaseTransport | None = None, max_wait_s: float = 120.0, attempts: int = 4) -> None:
        self._key = api_key
        self.limiter = limiter or RateLimiter(3)
        self._transport = transport
        self.max_wait_s = max_wait_s
        self.attempts = attempts

    def synthesize(self, text: str, *, lang: str, gender: str, voice: str, rate: str) -> tuple[bytes, str]:
        key = self._key or _gemini_key()
        if not key:
            raise TtsError("GEMINI_API_KEY not set (env or .env.dev.local)")
        slow = rate.startswith("-")
        style = ("Speak slowly, warmly and clearly, like a kind primary-school teacher"
                 if slow else "Speak clearly and calmly, like a friendly teacher")
        lang_name = "Vietnamese" if lang == "vi" else "English"
        body = {
            "model": GEMINI_TTS_MODEL,
            "input": [{"type": "user_input", "content": [{
                "type": "text", "text": text,
                "annotations": [{"type": "speech_metadata", "style": f"{style}, in {lang_name}"}]}]}],
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": [{"voice": GEMINI_VOICE.get(gender, "Kore")}]},
        }
        last = "unknown"
        with httpx.Client(timeout=httpx.Timeout(90.0, connect=15.0), transport=self._transport) as http:
            for _ in range(self.attempts):
                self.limiter.acquire()
                try:
                    r = http.post(GEMINI_URL, json=body, headers={"x-goog-api-key": key})
                except httpx.HTTPError as exc:
                    last = f"gemini-tts unreachable: {exc.__class__.__name__}"
                    continue
                if r.status_code == 429:
                    wait = parse_retry_after(r.text)
                    last = f"gemini-tts rate limited (retry in {wait:.0f}s)"
                    if wait > self.max_wait_s:
                        raise RateLimited(last, wait)
                    self.limiter.penalise(wait)
                    continue
                if r.status_code != 200:
                    last = f"gemini-tts HTTP {r.status_code}: {r.text[:120]}"
                    if r.status_code < 500:
                        break
                    continue
                found = find_audio_b64(r.json())
                if not found:
                    last = "gemini-tts: no audio in response"
                    continue
                raw, mime = found
                if raw[:4] == b"RIFF":
                    return raw, "wav"
                if raw[:3] == b"ID3" or raw[:2] == b"\xff\xfb":
                    return raw, "mp3"
                m = re.search(r"rate=(\d+)", mime)
                return pcm_to_wav(raw, int(m.group(1)) if m else 24000), "wav"
        raise TtsError(last)


@dataclass
class TtsClip:
    path: Path
    duration_s: float
    voice: str
    provider: str
    cached: bool = False
    notes: list[str] = field(default_factory=list)


def default_cache_dir() -> Path:
    base = os.environ.get("MENTOR_MEDIA_CACHE")
    if base:
        return Path(base)
    root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.cache")
    return Path(root) / "mentor-course-builder" / "cache"


def audio_duration(path: Path) -> float:
    r = _run([require_ffmpeg(), "-i", str(path)], timeout=60)
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", r.stderr)
    if not m:
        raise MediaError(f"cannot read duration of {path.name}")
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def to_mp3(data: bytes, ext: str, dest: Path, bitrate: str = "48k") -> None:
    """Transcode to mono MP3 (small packs). Voice does not need more than 48 kbit/s."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = dest.with_suffix(f".src.{ext}")
    src.write_bytes(data)
    try:
        r = _run([require_ffmpeg(), "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", "24000",
                  "-b:a", bitrate, str(dest)], timeout=120)
        if r.returncode != 0 or not dest.is_file():
            raise MediaError(f"ffmpeg mp3 transcode failed: {r.stderr.strip()[-200:]}")
    finally:
        src.unlink(missing_ok=True)


class TtsService:
    EDGE_CONCURRENCY = 4  # more simultaneous Edge sockets gets the endpoint to refuse some of them

    def __init__(self, providers: list[TtsProvider] | None = None, *, cache_dir: Path | None = None,
                 edge_retries: int = 3, sleep: Callable[[float], None] = time.sleep) -> None:
        self.edge = providers[0] if providers else EdgeTtsProvider()
        self.fallback = providers[1] if providers and len(providers) > 1 else (None if providers else GeminiTtsProvider())
        self.cache_dir = cache_dir or default_cache_dir()
        self.edge_retries = edge_retries
        self._sleep = sleep
        self._edge_slots = threading.BoundedSemaphore(self.EDGE_CONCURRENCY)
        self._edge_streak = 0  # clips in a row whose Edge attempts all failed

    @staticmethod
    def cache_key(text: str, voice: str, rate: str, lang: str) -> str:
        return hashlib.sha256(f"{lang}|{voice}|{rate}|{text}".encode()).hexdigest()[:32]

    def synthesize(self, text: str, *, lang: str, age_band: str, rate: str | None = None, gender: str = "female",
                   dest: Path | None = None) -> TtsClip:
        text = speakable(text, lang)
        if not re.search(r"\w", text):
            raise TtsError("empty text")
        rate_s = rate_for(age_band, rate)
        voice = EDGE_VOICES[(lang, gender)]
        other_gender = "male" if gender == "female" else "female"
        key = self.cache_key(text, voice, rate_s, lang)
        cached = self.cache_dir / "tts" / f"{key}.mp3"
        if cached.is_file():
            clip = TtsClip(cached, audio_duration(cached), voice, "cache", True, [f"tts: cache hit {voice}"])
        else:
            clip = self._generate(text, lang, gender, other_gender, voice, rate_s, cached)
        if dest:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(clip.path.read_bytes())
            clip.path = dest
        return clip

    def _generate(self, text: str, lang: str, gender: str, other: str, voice: str, rate: str, out: Path) -> TtsClip:
        notes: list[str] = []
        attempts: list[tuple[TtsProvider, str, str]] = []
        # Edge is flaky per voice and per moment (P0: a voice failed 5/5 on one sentence), so: the same voice with
        # growing pauses, then the other voice. While Edge is clearly down (3 clips in a row failed everywhere) a clip
        # gets one try per voice instead of the full ladder, so a dead endpoint costs seconds, not minutes.
        tries = 1 + (self.edge_retries if self._edge_streak < 3 else 0)
        attempts += [(self.edge, gender, voice)] * tries
        attempts.append((self.edge, other, EDGE_VOICES[(lang, other)]))
        for n, (prov, g, v) in enumerate(attempts):
            try:
                with self._edge_slots:
                    data, ext = prov.synthesize(text, lang=lang, gender=g, voice=v, rate=rate)
                to_mp3(data, ext, out)
                notes.append(f"tts: {prov.name} {v}")
                self._edge_streak = 0
                return TtsClip(out, audio_duration(out), v, prov.name, False, notes)
            except (TtsError, MediaError) as exc:
                notes.append(str(exc))
                log.warning("tts attempt failed: %s", exc)
                self._sleep(min(1.0 * 2 ** min(n, 3), 8.0) + (hash((text, n)) % 7) / 10)  # 1,2,4,8 s + jitter
        self._edge_streak += 1
        if self.fallback:
            try:
                data, ext = self.fallback.synthesize(text, lang=lang, gender=gender, voice=GEMINI_VOICE[gender], rate=rate)
                to_mp3(data, ext, out)
                notes.append(f"tts: {self.fallback.name} {GEMINI_VOICE[gender]} (fallback)")
                return TtsClip(out, audio_duration(out), GEMINI_VOICE[gender], self.fallback.name, False, notes)
            except (TtsError, MediaError) as exc:
                notes.append(str(exc))
        raise TtsError("all TTS providers failed: " + " | ".join(notes[-4:]))
