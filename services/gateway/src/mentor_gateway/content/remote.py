"""Download side of the Drive course store (every installed app).

`MENTOR_REMOTE_CATALOG_URL` (a public Drive URL or file id) names the catalog. The local gateway

  * syncs it into the content dir on start and then periodically (ETag / If-None-Match, so a check is cheap),
    writing catalog.json and a course.json per course (the Drive catalog carries each course's meta);
  * downloads a course's pack zip the first time the course is opened, verifies sha256 and every asset,
    and installs it as <course>/v<N>/ exactly like a locally built pack;
  * lets cached courses keep working offline; an uncached one raises NeedsNetwork (HTTP 503 `needs_network`).
"""

from __future__ import annotations

import asyncio
import html
import io
import json
import logging
import re
import shutil
import threading
import zipfile

import httpx
from mentor_schemas.course import Catalog, CoursePack

from mentor_gateway.content.store import ContentError, ContentStore, NotFound, atomic_write, sha256_bytes, sha256_file
from mentor_gateway.settings import Settings

log = logging.getLogger(__name__)

USERCONTENT = "https://drive.usercontent.google.com/download"


class NeedsNetwork(ContentError):
    def __init__(self, message: str = "needs network to download this course the first time") -> None:
        super().__init__("needs_network", message)


class BadDownload(ContentError):
    def __init__(self, message: str) -> None:
        super().__init__("download_corrupt", message)


def drive_id(value: str) -> str:
    """A Drive file id from an id, a /file/d/<id>/ link, or any link with ?id=<id>."""
    v = value.strip()
    m = re.search(r"/d/([A-Za-z0-9_-]{10,})", v) or re.search(r"[?&]id=([A-Za-z0-9_-]{10,})", v)
    return m.group(1) if m else v


class RemoteCourses:
    def __init__(self, settings: Settings, store: ContentStore, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings
        self.store = store
        self.catalog_id = drive_id(settings.remote_catalog_url or "")
        self.api_key = settings.drive_api_key
        self.http = httpx.Client(timeout=httpx.Timeout(60, connect=10), follow_redirects=True, transport=transport)
        self.state_path = store.root / ".remote.json"
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()
        self._verified: set[tuple[str, int]] = set()
        self.progress: dict[str, dict] = {}  # course id -> {"state": "downloading", "bytes": n, "total": n}
        self.last_sync_error: str | None = None

    # ------------------------------------------------------------ state
    def _state(self) -> dict:
        try:
            return json.loads(self.state_path.read_text("utf-8"))
        except (OSError, ValueError):
            return {"etag": None, "sha": None, "courses": {}}

    def info(self, course_id: str) -> dict | None:
        return self._state()["courses"].get(course_id)

    def _lock(self, key: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(key, threading.Lock())

    # ------------------------------------------------------------ fetching one file
    def _url(self, fid: str) -> tuple[str, dict]:
        if self.api_key:
            return f"https://www.googleapis.com/drive/v3/files/{fid}", {"alt": "media", "key": self.api_key}
        return USERCONTENT, {"id": fid, "export": "download", "confirm": "t"}

    def fetch(self, fid: str, headers: dict | None = None, on_bytes=None) -> httpx.Response | None:
        """GET a public Drive file. Handles Drive's "can't scan for viruses" HTML page by following its form
        (or `confirm=t`). Returns the response (bytes in .content); network trouble raises NeedsNetwork."""
        url, params = self._url(fid)
        try:
            r = self.http.get(url, params=params, headers=headers or {})
            for _ in range(2):
                if r.status_code == 200 and r.headers.get("content-type", "").startswith("text/html"):
                    form = self._confirm_form(r.text)
                    if not form:
                        break
                    r = self.http.get(form[0], params=form[1], headers=headers or {})
                else:
                    break
        except httpx.HTTPError as e:
            raise NeedsNetwork() from e
        if r.status_code == 304:
            return r
        if r.status_code >= 500 or r.status_code == 429:
            raise NeedsNetwork()
        if r.status_code != 200:
            raise BadDownload(f"Drive HTTP {r.status_code}")
        if r.headers.get("content-type", "").startswith("text/html"):
            raise BadDownload("Drive returned a web page instead of the file")
        return r

    @staticmethod
    def _confirm_form(page: str) -> tuple[str, dict] | None:
        m = re.search(r'<form[^>]*action="([^"]+)"', page)
        if not m:
            return None
        params = {html.unescape(k): html.unescape(v)
                  for k, v in re.findall(r'<input[^>]*type="hidden"[^>]*name="([^"]+)"[^>]*value="([^"]*)"', page)}
        params.setdefault("confirm", "t")
        return html.unescape(m.group(1)), params

    # ------------------------------------------------------------ catalog
    def sync_catalog(self) -> bool:
        """Fetch the catalog if it changed and write it into the content dir. True when something changed.
        Offline or broken: the local copy stays as it is (False)."""
        st = self._state()
        try:
            r = self.fetch(self.catalog_id, {"If-None-Match": st["etag"]} if st.get("etag") else None)
            if r is None or r.status_code == 304:
                return False
            raw = r.content
            sha = sha256_bytes(raw)
            if sha == st.get("sha"):
                self._save_etag(st, r)
                return False
            doc = json.loads(raw)
            remote = doc.pop("remote", {})
            cat = Catalog.model_validate(doc)
        except (NeedsNetwork, BadDownload, ValueError) as e:
            self.last_sync_error = type(e).__name__
            log.info("catalog sync skipped: %s", self.last_sync_error)
            return False
        self.last_sync_error = None
        courses = {}
        for e in cat.courses:
            r_ = remote.get(e.id)
            if not r_ or not isinstance(r_.get("meta"), dict):
                continue
            meta = r_["meta"]
            cdir = self.store.root / e.id
            cur = cdir / "course.json"
            data = (json.dumps(meta, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            if not cur.is_file() or cur.read_bytes() != data:
                atomic_write(cur, data)
            courses[e.id] = {k: v for k, v in r_.items() if k != "meta"}
        cat = cat.model_copy(update={"courses": [e for e in cat.courses if e.id in courses]})
        atomic_write(self.store.catalog_path, (cat.model_dump_json(indent=2) + "\n").encode("utf-8"))
        st.update(sha=sha, courses=courses)
        self._save_etag(st, r)
        return True

    def _save_etag(self, st: dict, r: httpx.Response) -> None:
        st["etag"] = r.headers.get("etag")
        atomic_write(self.state_path, json.dumps(st).encode())

    async def run_forever(self) -> None:
        while True:
            try:
                await asyncio.to_thread(self.sync_catalog)
            except Exception:
                log.exception("remote catalog sync")
            await asyncio.sleep(max(60.0, self.settings.remote_sync_minutes * 60))

    # ------------------------------------------------------------ packs
    def has_pack(self, course_id: str, version: int) -> bool:
        return self.store.pack_path(course_id, version).is_file()

    def ensure_pack(self, course_id: str, version: int) -> None:
        """Make sure pack.json and assets of this published version are on disk (downloads once)."""
        key = (course_id, version)
        if key in self._verified:
            return
        info = self.info(course_id)
        meta = self.store.load_meta(course_id)
        vi = self.store.version_info(meta, version)
        if self.has_pack(course_id, version) and (not vi.pack_sha256 or vi.pack_sha256 == sha256_file(self.store.pack_path(course_id, version))):
            self._verified.add(key)
            return
        if not info or not info.get("pack_id") or version != meta.latest_published:
            raise NotFound("pack_not_found")
        with self._lock(f"{course_id}:{version}"):
            if self.has_pack(course_id, version) and (not vi.pack_sha256 or vi.pack_sha256 == sha256_file(self.store.pack_path(course_id, version))):
                self._verified.add(key)
                return
            self.progress[course_id] = {"state": "downloading", "total": info.get("zip_bytes", 0)}
            try:
                r = self.fetch(info["pack_id"])
                data = r.content
                if sha256_bytes(data) != info["zip_sha256"]:
                    raise BadDownload("pack zip sha256 differs from the catalog")
                self._install(course_id, version, data, vi.pack_sha256)
            finally:
                self.progress.pop(course_id, None)
            self._verified.add(key)

    def _install(self, course_id: str, version: int, data: bytes, pack_sha: str | None) -> None:
        dest = self.store.course_dir(course_id) / f"v{version}"
        tmp = dest.with_name(f".dl-v{version}")
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                base = tmp.resolve()
                for zi in z.infolist():
                    target = (base / zi.filename).resolve()
                    if zi.is_dir() or base not in target.parents:
                        if zi.is_dir():
                            continue
                        raise BadDownload("unsafe path in pack zip")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(z.read(zi))
            pj = tmp / "pack.json"
            if not pj.is_file():
                raise BadDownload("pack.json missing")
            if pack_sha and sha256_file(pj) != pack_sha:
                raise BadDownload("pack.json sha256 differs from the catalog")
            pack = CoursePack.model_validate_json(pj.read_bytes())
            if pack.course_id != course_id or pack.version != version:
                raise BadDownload("pack is for another course")
            for ref in pack.assets():
                f = (tmp / "assets" / ref.path).resolve()
                if (tmp / "assets").resolve() not in f.parents or not f.is_file() or f.stat().st_size != ref.bytes \
                        or sha256_file(f) != ref.sha256:
                    raise BadDownload(f"asset {ref.path} is missing or damaged")
        except (zipfile.BadZipFile, ValueError) as e:
            shutil.rmtree(tmp, ignore_errors=True)
            raise BadDownload(str(e)) from e
        except BadDownload:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        tmp.rename(dest)

    # ------------------------------------------------------------ cover
    def ensure_cover(self, course_id: str) -> None:
        info = self.info(course_id)
        meta = self.store.load_meta(course_id)
        target = self.store.course_dir(course_id) / meta.cover
        if target.is_file() or not info or not info.get("cover_id"):
            return
        with self._lock(f"{course_id}:cover"):
            if target.is_file():
                return
            data = self.fetch(info["cover_id"]).content
            if not data:
                raise BadDownload("empty cover")
            atomic_write(target, data)
