"""Upload side of the Drive course store (owner's machine only).

Layout on the owner's Google Drive (scope drive.file: the app only ever sees files it created itself):

    Mentor courses/catalog.json                 public catalog (CatalogEntry list + "remote": drive ids per course)
    Mentor courses/<course_id>/pack-v<N>.zip    pack.json + assets/ of the latest published version
    Mentor courses/<course_id>/course.json
    Mentor courses/<course_id>/cover.<ext>

Every file is "anyone with the link: reader". Uploads are idempotent: a file carries its sha256 in `appProperties`
and is not sent again when it matches. Plain HTTPS through httpx, no Google client library.

    python -m mentor_gateway.content.drive login | push-all | status
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import io
import json
import logging
import os
import secrets
import threading
import time
import urllib.parse
import webbrowser
import zipfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import httpx

from mentor_schemas.course import CatalogEntry

from mentor_gateway.content.store import ContentStore, NotFound, atomic_write, derive_media, sha256_bytes, sha256_file
from mentor_gateway.langga.subjects import chicken_of_entry
from mentor_gateway.settings import Settings

log = logging.getLogger(__name__)

SCOPE = "https://www.googleapis.com/auth/drive.file"
API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3"
ROOT_FOLDER = "Mentor courses"
FOLDER_MIME = "application/vnd.google-apps.folder"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
USERCONTENT = "https://drive.usercontent.google.com/download"  # public download of a file shared with "anyone with the link"


class DriveError(Exception):
    pass


class NotLoggedIn(DriveError):
    pass


# ---------------------------------------------------------------- OAuth (installed app, loopback + PKCE)
def _client_config(path: Path) -> dict:
    if not path.is_file():
        raise NotLoggedIn(f"Chưa có file OAuth client: {path}")
    raw = json.loads(path.read_text("utf-8"))
    cfg = raw.get("installed") or raw.get("web") or raw
    if not cfg.get("client_id"):
        raise DriveError("OAuth client file has no client_id")
    return cfg


def login(settings: Settings, *, open_browser: Callable[[str], object] = webbrowser.open, timeout_s: int = 300,
          out: Callable[[str], None] = print) -> None:
    """Browser consent once; saves the refresh token to settings.drive_token_file (never printed)."""
    cfg = _client_config(settings.drive_client_file)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    got: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query))
            if q.get("state") == state and q.get("code"):
                got["code"] = q["code"]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<p>Xong. Quay lại cửa sổ dòng lệnh nhé.</p>".encode())

        def log_message(self, *a):  # silence
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    server.timeout = 1
    redirect = f"http://127.0.0.1:{server.server_port}"
    url = GOOGLE_AUTH_URI + "?" + urllib.parse.urlencode({
        "client_id": cfg["client_id"], "redirect_uri": redirect, "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent", "state": state, "code_challenge": challenge,
        "code_challenge_method": "S256"})
    out("Đang mở trình duyệt để đăng nhập Google. Nếu không tự mở, dán địa chỉ này vào trình duyệt:\n" + url)
    open_browser(url)
    deadline = time.monotonic() + timeout_s
    while "code" not in got and time.monotonic() < deadline:
        server.handle_request()
    server.server_close()
    if "code" not in got:
        raise DriveError("Hết thời gian chờ đăng nhập")
    data = {"client_id": cfg["client_id"], "code": got["code"], "code_verifier": verifier,
            "grant_type": "authorization_code", "redirect_uri": redirect}
    if cfg.get("client_secret"):
        data["client_secret"] = cfg["client_secret"]
    r = httpx.post(cfg.get("token_uri") or GOOGLE_TOKEN_URI, data=data, timeout=30)
    if r.status_code != 200 or not r.json().get("refresh_token"):
        raise DriveError(f"Google từ chối đăng nhập (HTTP {r.status_code})")
    tok = settings.drive_token_file
    atomic_write(tok, json.dumps({"refresh_token": r.json()["refresh_token"]}).encode())
    try:
        os.chmod(tok, 0o600)
    except OSError:
        pass
    out("Đã đăng nhập. Token lưu ở máy này, không đưa vào git.")


class DriveClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings
        self.http = httpx.Client(timeout=120, transport=transport)
        self._access: tuple[str, float] | None = None

    def _token(self) -> str:
        if self._access and self._access[1] > time.monotonic() + 60:
            return self._access[0]
        cfg = _client_config(self.settings.drive_client_file)
        tf = self.settings.drive_token_file
        if not tf.is_file():
            raise NotLoggedIn("Chưa đăng nhập Google: chạy `python -m mentor_gateway.content.drive login`")
        refresh = json.loads(tf.read_text("utf-8")).get("refresh_token")
        data = {"client_id": cfg["client_id"], "refresh_token": refresh, "grant_type": "refresh_token"}
        if cfg.get("client_secret"):
            data["client_secret"] = cfg["client_secret"]
        r = self.http.post(cfg.get("token_uri") or GOOGLE_TOKEN_URI, data=data)
        if r.status_code != 200:
            raise DriveError(f"Không làm mới được token Google (HTTP {r.status_code}); chạy lại `login`")
        j = r.json()
        self._access = (j["access_token"], time.monotonic() + int(j.get("expires_in", 3600)))
        return self._access[0]

    def _req(self, method: str, url: str, **kw) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._token()}", **kw.pop("headers", {})}
        r = self.http.request(method, url, headers=headers, **kw)
        if r.status_code in (429, 500, 502, 503, 504):
            raise DriveError(f"Drive tạm thời lỗi (HTTP {r.status_code})")
        if r.status_code >= 400:
            raise DriveError(f"Drive từ chối {method} (HTTP {r.status_code})")
        return r

    # ------------------------------------------------------------ files
    def find(self, name: str, parent: str | None = None, folder: bool = False) -> dict | None:
        q = [f"name = '{name.replace(chr(39), chr(92) + chr(39))}'", "trashed = false"]
        if parent:
            q.append(f"'{parent}' in parents")
        q.append(f"mimeType {'=' if folder else '!='} '{FOLDER_MIME}'")
        r = self._req("GET", f"{API}/files", params={"q": " and ".join(q), "spaces": "drive", "pageSize": 10,
                                                    "fields": "files(id,name,appProperties)"})
        files = r.json().get("files", [])
        return files[0] if files else None

    def ensure_folder(self, name: str, parent: str | None = None) -> str:
        hit = self.find(name, parent, folder=True)
        if hit:
            return hit["id"]
        body = {"name": name, "mimeType": FOLDER_MIME, **({"parents": [parent]} if parent else {})}
        r = self._req("POST", f"{API}/files", json=body, params={"fields": "id"})
        return r.json()["id"]

    def _send(self, file_id: str | None, meta: dict, data: bytes, mime: str) -> str:
        url = f"{UPLOAD}/files" + (f"/{file_id}" if file_id else "")
        r = self._req("PATCH" if file_id else "POST", url, params={"uploadType": "resumable", "fields": "id"}, json=meta,
                      headers={"X-Upload-Content-Type": mime, "X-Upload-Content-Length": str(len(data))})
        loc = r.headers.get("Location")
        if not loc:
            raise DriveError("Drive không trả địa chỉ upload")
        r = self._req("PUT", loc, content=data, headers={"Content-Type": mime})
        return r.json()["id"]

    def make_public(self, file_id: str) -> None:
        self._req("POST", f"{API}/files/{file_id}/permissions", json={"role": "reader", "type": "anyone"})

    def upload(self, name: str, data: bytes, mime: str, parent: str, sha: str | None = None) -> tuple[str, bool]:
        """Create or update `name` under `parent`; (file id, uploaded). Unchanged content (same sha256) is not resent."""
        sha = sha or sha256_bytes(data)
        existing = self.find(name, parent)
        if existing and (existing.get("appProperties") or {}).get("sha256") == sha:
            return existing["id"], False
        meta: dict = {"name": name, "appProperties": {"sha256": sha}}
        if not existing:
            meta["parents"] = [parent]
        fid = self._send(existing["id"] if existing else None, meta, data, mime)
        self.make_public(fid)
        return fid, True


# ---------------------------------------------------------------- pushing courses
def pack_zip(store: ContentStore, course_id: str, version: int) -> bytes:
    """pack.json + assets/ of one version (never sources/), with fixed timestamps so equal content gives equal bytes."""
    base = store.version_dir(course_id, version)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        files = [base / "pack.json", *sorted(p for p in (base / "assets").rglob("*") if p.is_file())]
        for p in files:
            arc = p.relative_to(base).as_posix()
            zi = zipfile.ZipInfo(arc, date_time=(2020, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED if arc.endswith(".json") else zipfile.ZIP_STORED
            z.writestr(zi, p.read_bytes())
    return buf.getvalue()


def build_submission(store: ContentStore, course_id: str, version: int, now: datetime) -> dict:
    """Everything the hub's `/api/courses/submit` needs for one version, without publishing it locally: the catalog `entry`
    and `meta` (course.json) as they will look once published, the pack zip with its sha256, and the cover."""
    meta = store.load_meta(course_id)
    info = store.version_info(meta, version)
    pack = store.load_pack(course_id, version)
    asset_bytes = store._verify_assets(course_id, version, pack)  # noqa: SLF001 - same checks as publish
    raw = store.pack_bytes_raw(course_id, version)
    cover = store.cover_path(course_id)
    m = meta.model_copy(deep=True)
    vi = store.version_info(m, version)
    vi.status = "published"
    vi.published_at = info.published_at or now
    vi.pack_sha256 = sha256_bytes(raw)
    vi.pack_bytes = len(raw) + asset_bytes
    if m.latest_published is None or version >= m.latest_published:  # what ContentStore.publish does to course.json
        m.latest_published = version
        m.lessons_count = sum(len(c.lessons) for c in pack.chapters)
        m.est_minutes = sum(ls.est_minutes for c in pack.chapters for ls in c.lessons)
        m.media = derive_media(pack)  # type: ignore[assignment]
        labels = vi.labels or {}
        m.age_band = labels.get("band") or pack.age_band
        m.language = labels.get("language") or pack.language
        if labels.get("goals") is not None:
            m.outcomes = list(labels["goals"])
        if labels.get("topics") is not None:
            m.topics = list(labels["topics"])
        m.level = vi.level_confirmed or m.level
        m.chicken = labels.get("chicken") or m.chicken
        m.grade = labels.get("grade") or m.grade
    entry = CatalogEntry(
        id=m.id, title=m.title, subject=m.subject, age_band=m.age_band, language=m.language, teacher_name=m.teacher_name,
        description_short=m.description_short, outcomes=m.outcomes, cover_sha256=sha256_file(cover), media=m.media,
        lessons_count=m.lessons_count, est_minutes=m.est_minutes, level=m.level, chicken=chicken_of_entry(m),
        topics=m.topics, version=version, pack_sha256=vi.pack_sha256 or "", pack_bytes=vi.pack_bytes or 0,
        published_at=vi.published_at)
    z = pack_zip(store, course_id, version)
    return {"title": m.title, "entry": entry.model_dump(mode="json"), "meta": json.loads(m.model_dump_json()),
            "zip": z, "zip_sha256": sha256_bytes(z), "cover": cover.read_bytes(), "cover_name": "cover" + cover.suffix.lower()}


class DrivePublisher:
    """Pushes courses and keeps the public catalog. State (Drive ids) lives next to the token, so a second machine
    simply rebuilds it: files are found by name and compared by sha256."""

    def __init__(self, store: ContentStore, settings: Settings, client: DriveClient | None = None) -> None:
        self.store = store
        self.settings = settings
        self.client = client or DriveClient(settings)
        self.index_path = settings.drive_token_file.with_name("drive-index.json")
        self._lock = threading.RLock()
        self._root: str | None = None

    # -- index
    def _load(self) -> dict:
        try:
            return json.loads(self.index_path.read_text("utf-8"))
        except (OSError, ValueError):
            return {"catalog_id": None, "courses": {}}

    def _save(self, idx: dict) -> None:
        atomic_write(self.index_path, json.dumps(idx, indent=1).encode())

    def _root_id(self) -> str:
        if not self._root:
            self._root = self.client.ensure_folder(ROOT_FOLDER)
        return self._root

    # -- one course
    def push_course(self, course_id: str) -> dict:
        """Uploads pack zip, course.json and cover when they changed; returns {"uploaded": [...]}"""
        with self._lock:
            c = self.client
            meta = self.store.load_meta(course_id)
            folder = c.ensure_folder(course_id, self._root_id())
            idx = self._load()
            prev = idx["courses"].get(course_id, {})
            uploaded: list[str] = []
            entry: dict = {"version": 0, "pack_id": None, "zip_sha256": "", "zip_bytes": 0}
            if meta.status != "coming_soon":
                if meta.latest_published is None:
                    raise NotFound("course_not_published")
                v = meta.latest_published
                z = pack_zip(self.store, course_id, v)
                zsha = sha256_bytes(z)
                name = f"pack-v{v}.zip"
                same = prev.get("version") == v and prev.get("zip_sha256") == zsha and prev.get("pack_id")
                pid, up = (prev["pack_id"], False) if same else c.upload(name, z, "application/zip", folder, zsha)
                if up:
                    uploaded.append(name)
                entry.update(version=v, pack_id=pid, zip_sha256=zsha, zip_bytes=len(z))
            meta_json = (self.store.course_dir(course_id) / "course.json").read_bytes()
            mid, up = c.upload("course.json", meta_json, "application/json", folder)
            if up:
                uploaded.append("course.json")
            cover = self.store.cover_path(course_id)
            cbytes = cover.read_bytes()
            cname = "cover" + cover.suffix.lower()
            cid_, up = c.upload(cname, cbytes, "application/octet-stream", folder)
            if up:
                uploaded.append(cname)
            entry.update(meta_id=mid, cover_id=cid_, cover_name=cname)
            idx["courses"][course_id] = entry
            self._save(idx)
            return {"uploaded": uploaded}

    def _published_catalog(self, idx: dict) -> dict:
        """The current public catalog.json (what the apps download), or {} when it does not exist yet or cannot be read.
        Courses published through the hub live only here, so `push_catalog` must merge with it."""
        fid = idx.get("catalog_id")
        if not fid:
            try:
                hit = self.client.find("catalog.json", self._root_id())
            except (DriveError, httpx.HTTPError):
                return {}
            fid = hit["id"] if hit else None
        if not fid:
            return {}
        try:
            r = self.client.http.get(USERCONTENT, params={"id": fid, "export": "download", "confirm": "t"},
                                     follow_redirects=True)
            doc = r.json() if r.status_code == 200 else {}
        except (httpx.HTTPError, ValueError):
            return {}
        return doc if isinstance(doc, dict) else {}

    def push_catalog(self) -> str:
        """Writes catalog.json (published courses that are on Drive) and returns its Drive file id.

        Entries (and `remote` records) of course ids that are not in the local store, i.e. teacher courses published
        through the hub, are kept from the current public catalog."""
        with self._lock:
            idx = self._load()
            cat = self.store.regenerate_catalog()
            remote: dict[str, dict] = {}
            entries = []
            for e in cat.courses:
                r = idx["courses"].get(e.id)
                if not r or (e.status == "live" and r.get("version") != e.version):
                    continue  # not (yet) on Drive: apps must not see a course they cannot download
                entries.append(e)
                meta = json.loads((self.store.course_dir(e.id) / "course.json").read_text("utf-8"))
                remote[e.id] = {**{k: r[k] for k in ("pack_id", "zip_sha256", "zip_bytes", "cover_id", "cover_name")}, "meta": meta}
            doc = {**cat.model_copy(update={"courses": entries}).model_dump(mode="json"), "remote": remote}
            local_ids = set(self.store.list_course_ids())
            current = self._published_catalog(idx)
            foreign = [c for c in current.get("courses", []) if isinstance(c, dict) and c.get("id") not in local_ids]
            if foreign:
                doc["courses"] = [*doc["courses"], *foreign]
                for c in foreign:
                    rec = (current.get("remote") or {}).get(c["id"])
                    if rec is not None:
                        doc["remote"][c["id"]] = rec
            data = (json.dumps(doc, ensure_ascii=False, separators=(",", ":"))).encode("utf-8")
            sha = sha256_bytes(json.dumps({**doc, "generated_at": ""}, ensure_ascii=False, sort_keys=True).encode("utf-8"))
            if idx.get("catalog_id") and idx.get("catalog_sha") == sha:
                return idx["catalog_id"]
            fid, _ = self.client.upload("catalog.json", data, "application/json", self._root_id(), sha)
            idx.update(catalog_id=fid, catalog_sha=sha)
            self._save(idx)
            return fid

    def push_all(self, out: Callable[[str], None] = print) -> str:
        ids = [cid for cid in self.store.list_course_ids() if self._pushable(cid)]
        for i, cid in enumerate(ids, 1):
            res = self.push_course(cid)
            out(f"[{i}/{len(ids)}] {cid}: " + (", ".join(res["uploaded"]) if res["uploaded"] else "không đổi"))
        fid = self.push_catalog()
        out(f"Catalog công khai: https://drive.usercontent.google.com/download?id={fid}&export=download&confirm=t")
        out(f"MENTOR_REMOTE_CATALOG_URL={fid}")
        return fid

    def _pushable(self, cid: str) -> bool:
        m = self.store.load_meta(cid)
        return m.status == "coming_soon" or m.latest_published is not None

    def status(self) -> dict:
        idx = self._load()
        ids = [c for c in self.store.list_course_ids() if self._pushable(c)]
        behind = []
        for cid in ids:
            r = idx["courses"].get(cid)
            m = self.store.load_meta(cid)
            if not r or (m.status != "coming_soon" and r.get("version") != m.latest_published):
                behind.append(cid)
        return {"catalog_id": idx.get("catalog_id"), "local": len(ids), "on_drive": len(idx["courses"]), "not_synced": behind}


# ---------------------------------------------------------------- background upload on publish
class DriveSync:
    """Called by ContentStore after publish / label changes. One worker thread; never blocks the caller.
    Retries with backoff; a course that keeps failing is listed in `failed` (the teacher UI shows "chưa đồng bộ")."""

    ATTEMPTS = 6

    def __init__(self, publisher: DrivePublisher, sleep: Callable[[float], None] = time.sleep, base_delay: float = 5.0) -> None:
        self.pub = publisher
        self._sleep = sleep
        self.base_delay = base_delay
        self.failed: dict[str, str] = {}
        self.pending: set[str] = set()
        self._cv = threading.Condition()
        self._busy = False
        self._thread: threading.Thread | None = None

    def notify(self, course_id: str) -> None:
        with self._cv:
            self.pending.add(course_id)
            if not self._thread or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="drive-sync", daemon=True)
                self._thread.start()
            self._cv.notify_all()

    def unsynced(self, course_id: str) -> bool:
        return course_id in self.failed

    def wait_idle(self, timeout: float = 10.0) -> bool:
        end = time.monotonic() + timeout
        with self._cv:
            while self.pending or self._busy:
                left = end - time.monotonic()
                if left <= 0:
                    return False
                self._cv.wait(left)
        return True

    def _retry(self, fn: Callable[[], object]) -> str | None:
        err = ""
        for n in range(self.ATTEMPTS):
            try:
                fn()
                return None
            except NotLoggedIn as e:
                return str(e)
            except Exception as e:  # noqa: BLE001
                err = type(e).__name__
                log.warning("drive upload failed (attempt %d): %s", n + 1, err)
                self._sleep(self.base_delay * 2 ** n)
        return err

    def _run(self) -> None:
        while True:
            with self._cv:
                if not self.pending:
                    self._busy = False
                    self._cv.notify_all()
                    return
                batch, self.pending = sorted(self.pending), set()
                self._busy = True
            ok = False
            for cid in batch:
                err = self._retry(lambda cid=cid: self.pub.push_course(cid))
                if err:
                    self.failed[cid] = err
                else:
                    self.failed.pop(cid, None)
                    ok = True
            if ok:
                err = self._retry(self.pub.push_catalog)
                if err:
                    for cid in batch:
                        self.failed.setdefault(cid, err)


# ---------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="python -m mentor_gateway.content.drive")
    ap.add_argument("cmd", choices=["login", "push-all", "status"])
    args = ap.parse_args(argv)
    settings = Settings.from_env()
    try:
        if args.cmd == "login":
            login(settings)
            return 0
        pub = DrivePublisher(ContentStore(settings.courses_dir), settings)
        if args.cmd == "push-all":
            pub.push_all()
        else:
            s = pub.status()
            print(f"Khóa trên máy: {s['local']}, đã lên Drive: {s['on_drive']}, chưa đồng bộ: {len(s['not_synced'])}")
            for cid in s["not_synced"]:
                print("  chưa đồng bộ:", cid)
            print("Catalog:", s["catalog_id"] or "(chưa có, chạy push-all)")
        return 0
    except DriveError as e:
        print("Lỗi:", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
