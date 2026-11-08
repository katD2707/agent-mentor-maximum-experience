"""BuilderService: per-course builder state, a one-job-per-course stage queue and the teacher-facing status.

The builder (docling, torch, long model calls) never runs in this process. Every stage is a subprocess
(`python -m mentor_course_builder.cli job <kind> --dir <builder dir> ...`) that reads and writes JSON under
`<MENTOR_DATA_DIR>/builder/<course_id>/`; this service only keeps `state.json` (chat, jobs, comments) next to it.
A restart resets `running` jobs to `queued` and the stage runs again (stages are idempotent), so the teacher can close
the app, or the server can restart, at any point.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import unicodedata
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from mentor_schemas.course import CalloutBlock, ImageBlock, QuizBlock, TextBlock, VideoBlock
from sqlalchemy import func, select

from mentor_gateway.content.service import ContentService
from mentor_gateway.content.store import ContentError, Immutable, NotFound, atomic_write, sha256_file
from mentor_gateway.content.tables import Enrollment
from mentor_gateway.db import Database, User
from mentor_gateway.notifications import Nudge
from mentor_gateway.security import new_id
from mentor_gateway.settings import Clock, Settings, _repo_root

log = logging.getLogger(__name__)

ACTIVE = ("queued", "running")
REVISE_KINDS = ("revise_text", "revise_media", "revise_all", "outline_chat")


class Forbidden(ContentError):
    pass


class Busy(ContentError):
    pass


@dataclass
class StageJob:
    id: str
    kind: str
    course_id: str
    base: Path
    args_file: Path
    result_file: Path
    log_file: Path
    timeout_s: int


class StageRunner(Protocol):
    """Runs one stage to completion and returns its exit code (0 = ok). Tests replace it with a fake."""

    async def __call__(self, job: StageJob) -> int: ...


class SubprocessRunner:
    def __init__(self, python: str | None = None, cwd: Path | None = None) -> None:
        self.python = python or sys.executable
        self.cwd = cwd
        self._procs: set[subprocess.Popen] = set()

    @staticmethod
    def argv(python: str, job: StageJob) -> list[str]:
        return [python, "-m", "mentor_course_builder.cli", "job", job.kind, "--dir", str(job.base),
                "--args", str(job.args_file), "--result", str(job.result_file)]

    def _run(self, job: StageJob) -> int:
        job.log_file.parent.mkdir(parents=True, exist_ok=True)
        env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
        with job.log_file.open("ab") as log_f:
            proc = subprocess.Popen(self.argv(self.python, job), cwd=self.cwd, env=env, stdout=log_f,
                                    stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
            self._procs.add(proc)
            try:
                return proc.wait(timeout=job.timeout_s)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                return 124
            finally:
                self._procs.discard(proc)

    async def __call__(self, job: StageJob) -> int:
        return await asyncio.to_thread(self._run, job)

    def terminate_all(self) -> None:
        for p in list(self._procs):
            try:
                p.kill()
            except OSError:
                pass


class EventBus:
    """Teacher events for SSE: a small replay buffer plus live subscriber queues."""

    def __init__(self) -> None:
        self._seq = 0
        self._buf: deque[tuple[int, str, dict]] = deque(maxlen=300)
        self._subs: set[asyncio.Queue] = set()

    def publish(self, teacher_id: str, data: dict) -> None:
        self._seq += 1
        item = (self._seq, teacher_id, data)
        self._buf.append(item)
        for q in list(self._subs):
            q.put_nowait(item)

    def subscribe(self, teacher_id: str, after: int | None = None) -> tuple[asyncio.Queue, list[tuple[int, dict]]]:
        q: asyncio.Queue = asyncio.Queue()
        replay = [(i, d) for i, t, d in self._buf if t == teacher_id and after is not None and i > after]
        self._subs.add(q)
        return q, replay

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)


def slugify(text: str, cap: int = 32) -> str:
    """ASCII, lowercase, hyphens; Vietnamese diacritics removed (đ -> d). Empty when nothing usable is left."""
    t = unicodedata.normalize("NFD", (text or "").replace("đ", "d").replace("Đ", "D"))
    t = "".join(ch for ch in t if not unicodedata.combining(ch)).lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:cap].strip("-")


def _iso(dt: datetime) -> str:
    return dt.isoformat()


class BuilderService:
    def __init__(self, settings: Settings, content: ContentService, db: Database, clock: Clock, hub: Any,
                 runner: StageRunner | None = None) -> None:
        self.settings = settings
        self.content = content
        self.db = db
        self.clock = clock
        self.hub = hub
        self.base = settings.builder_dir
        root = _repo_root()  # the builder finds .env.dev.local by walking up from its cwd
        self.runner: StageRunner = runner or SubprocessRunner(settings.builder_python, root if root.is_dir() else None)
        self.bus = EventBus()
        self._states: dict[str, dict] = {}
        self._lock = threading.RLock()
        self._running: set[str] = set()
        self._tasks: set[asyncio.Task] = set()
        self._waiters: dict[str, asyncio.Event] = {}
        self._started = False

    # ------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        """Load every course's state; jobs that were running when the process stopped run again."""
        self.base.mkdir(parents=True, exist_ok=True)
        with self._lock:
            for d in sorted(self.base.iterdir()):
                f = d / "state.json"
                if d.is_dir() and f.is_file():
                    try:
                        st = json.loads(f.read_text("utf-8"))
                    except ValueError:
                        log.warning("unreadable builder state %s", f)
                        continue
                    for j in st["jobs"]:
                        if j["status"] == "running":
                            j["status"] = "queued"
                    for c in st["comments"]:
                        if c["status"] == "applying":
                            c["status"] = "open"
                    self._states[st["course_id"]] = st
        self._started = True
        self.kick()

    async def stop(self) -> None:
        self._started = False
        term = getattr(self.runner, "terminate_all", None)
        if term:
            term()
        for t in list(self._tasks):
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    # ------------------------------------------------------------ state
    def course_dir(self, cid: str) -> Path:
        return self.base / cid

    def _save(self, st: dict) -> None:
        st["updated_at"] = _iso(self.clock())
        atomic_write(self.course_dir(st["course_id"]) / "state.json",
                     json.dumps(st, ensure_ascii=False, indent=1).encode("utf-8"))

    def new_course_id(self, hint: str | None) -> str:
        """A readable id from `hint` (the title when known); -2, -3, ... on collision. Never reused or renamed."""
        base = slugify(hint or "") or "khoa-hoc"
        taken = lambda c: c in self._states or (self.base / c).exists() or self._store_meta(c) is not None  # noqa: E731
        cid, n = base, 2
        while taken(cid):
            cid, n = f"{base}-{n}", n + 1
        return cid

    def create(self, teacher: User, note: str | None, title_hint: str | None = None) -> dict:
        cid = self.new_course_id(title_hint)
        now = _iso(self.clock())
        st = {"course_id": cid, "teacher_id": teacher.id, "teacher_name": teacher.display_name or "Giáo viên",
              "note": (note or "").strip() or None, "created_at": now, "updated_at": now, "outline_edited": False,
              "chat": [], "jobs": [], "comments": []}
        with self._lock:
            self._states[cid] = st
            self._save(st)
        return st

    def _store_meta(self, cid: str):
        try:
            return self.content.store.load_meta(cid)
        except NotFound:
            return None

    def owned(self, user: User, cid: str) -> dict:
        """The builder state of one of the teacher's own courses (created on demand for a store course they own)."""
        with self._lock:
            st = self._states.get(cid)
            if st is not None:
                if st["teacher_id"] != user.id:
                    raise Forbidden("not_owner")
                return st
            meta = self._store_meta(cid) if cid and "/" not in cid and "\\" not in cid and not cid.startswith(".") else None
            if meta is None:
                raise NotFound("course_not_found")
            if meta.teacher_id not in (user.id, user.username):
                raise Forbidden("not_owner")
            st = {"course_id": cid, "teacher_id": user.id, "teacher_name": user.display_name or meta.teacher_name,
                  "note": None, "created_at": _iso(self.clock()), "updated_at": _iso(self.clock()),
                  "outline_edited": True, "chat": [], "jobs": [], "comments": []}
            self._states[cid] = st
            self._save(st)
            return st

    def list_for(self, user: User) -> list[dict]:
        with self._lock:
            ids = [c for c, st in self._states.items() if st["teacher_id"] == user.id]
        for meta in self.content.store.list_courses():  # store courses seeded without a builder state
            if meta.id not in self._states and meta.teacher_id in (user.id, user.username):
                ids.append(meta.id)
        out = []
        for cid in ids:
            try:
                out.append(self.view(self.owned(user, cid)))
            except ContentError:
                continue
        return sorted(out, key=lambda v: v["updated_at"], reverse=True)

    # ------------------------------------------------------------ chat
    def say(self, st: dict, role: str, kind: str, vi: str | None = None, en: str | None = None) -> dict:
        m = {"id": f"m{len(st['chat']) + 1}", "role": role, "kind": kind, "text": vi, "text_en": en or vi,
             "created_at": _iso(self.clock())}
        st["chat"].append(m)
        return m

    # ------------------------------------------------------------ jobs
    def active_jobs(self, st: dict) -> list[dict]:
        return [j for j in st["jobs"] if j["status"] in ACTIVE]

    def enqueue(self, st: dict, kind: str, args: dict, *, comment_id: str | None = None, kick: bool = True) -> dict:
        job = {"id": new_id("bj"), "kind": kind, "args": args, "status": "queued", "created_at": _iso(self.clock()),
               "started_at": None, "finished_at": None, "error": None, "result": None, "comment_id": comment_id}
        with self._lock:
            st["jobs"].append(job)
            st["jobs"] = [j for j in st["jobs"] if j["status"] in ACTIVE][:] + \
                [j for j in st["jobs"] if j["status"] not in ACTIVE][-40:]
            self._save(st)
        self.emit(st)
        if kick:
            self.kick()
        return job

    def kick(self) -> None:
        """Start queued jobs while there is capacity (BUILDER_WORKERS) and the course has no running job."""
        if not self._started:
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        while len(self._tasks) < max(1, self.settings.builder_workers):
            pick = None
            with self._lock:
                for st in sorted(self._states.values(), key=lambda s: s["created_at"]):
                    if st["course_id"] in self._running:
                        continue
                    nxt = next((j for j in st["jobs"] if j["status"] == "queued"), None)
                    if nxt is not None:
                        pick = (st, nxt)
                        break
            if pick is None:
                return
            st, job = pick
            self._running.add(st["course_id"])
            job["status"] = "running"
            job["started_at"] = _iso(self.clock())
            for c in st["comments"]:
                if c["id"] == job.get("comment_id"):
                    c["status"], c["updated_at"] = "applying", _iso(self.clock())
            self._save(st)
            self._waiters.setdefault(job["id"], asyncio.Event())
            t = asyncio.create_task(self._execute(st, job))
            self._tasks.add(t)
            t.add_done_callback(self._task_done)
            self.emit(st)

    def _task_done(self, t: "asyncio.Task") -> None:
        # the finished task still counted as running when _execute called kick(): start the next queued job now
        self._tasks.discard(t)
        if self._started:
            self.kick()

    async def wait(self, job_id: str, timeout: float) -> bool:
        ev = self._waiters.get(job_id)
        if ev is None:
            return True
        try:
            await asyncio.wait_for(ev.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def _execute(self, st: dict, job: dict) -> None:
        cid = st["course_id"]
        base = self.course_dir(cid)
        jdir = base / "jobs"
        jdir.mkdir(parents=True, exist_ok=True)
        args_f, res_f = jdir / f"{job['id']}.args.json", jdir / f"{job['id']}.result.json"
        args_f.write_text(json.dumps(job["args"], ensure_ascii=False), encoding="utf-8")
        res_f.unlink(missing_ok=True)
        sj = StageJob(job["id"], job["kind"], cid, base, args_f, res_f, jdir / f"{job['id']}.log",
                      self.settings.builder_job_timeout_s)
        try:
            rc = await self.runner(sj)
        except asyncio.CancelledError:
            raise  # shutdown: the job stays `running` and is queued again at the next start
        except Exception as exc:  # noqa: BLE001
            log.exception("stage %s failed to run", job["kind"])
            rc, err = -1, f"{type(exc).__name__}: {exc}"
        else:
            err = None
        try:
            result = json.loads(res_f.read_text("utf-8")) if res_f.is_file() else {}
        except ValueError:
            result = {}
        ok = rc == 0 and result.get("ok", True) is not False
        if not ok:
            err = err or result.get("error") or f"stage exited with code {rc}"
        with self._lock:
            job["status"] = "done" if ok else "failed"
            job["finished_at"] = _iso(self.clock())
            job["error"] = None if ok else str(err)[:600]
            job["result"] = {k: v for k, v in result.items() if k not in ("notes",)} if ok else None
            self._running.discard(cid)
            try:
                notify = self._on_finished(st, job, result, ok, str(err or ""))
            except Exception:  # noqa: BLE001
                log.exception("finishing job %s", job["id"])
                notify = None
            self._save(st)
        self.emit(st)
        if notify:  # the desktop app toasts it (notifications.py)
            try:
                await self.hub.notify(st["teacher_id"], notify, Nudge(text=notify, title="Mentor", source="builder"))
            except Exception:  # noqa: BLE001
                log.warning("builder notification failed", exc_info=True)
        ev = self._waiters.pop(job["id"], None)
        if ev:
            ev.set()
        self.kick()

    # ------------------------------------------------------------ finish handlers
    def title_of(self, st: dict) -> str:
        o = self.outline(st["course_id"])
        if o:
            return o.get("title") or "Khóa học"
        meta = self._store_meta(st["course_id"])
        return meta.title if meta else "Khóa học mới"

    def _on_finished(self, st: dict, job: dict, result: dict, ok: bool, err: str) -> str | None:
        kind, cid = job["kind"], st["course_id"]
        title = self.title_of(st)
        notify: str | None = None
        if kind == "intake":
            if not ok and st.get("intake_retries", 0) < 2 and job.get("args"):
                # model gateways flake (bad JSON, 502/524): stages are idempotent, so read the material again (twice at most)
                st["intake_retries"] = st.get("intake_retries", 0) + 1
                self.say(st, "agent", "notice", "Mình gặp lỗi khi đọc, đang đọc lại.", "Hit an error while reading, trying again.")
                self.enqueue(st, "intake", job["args"], kick=False)
            elif not ok:
                self.say(st, "agent", "notice", f"Chưa đọc được tài liệu: {err[:200]}", f"Could not read the material: {err[:200]}")
                notify = "Không đọc được tài liệu vừa gửi."
            else:
                retake = self.retake(cid)
                if retake:
                    self.say(st, "agent", "retake", f"Có {len(retake)} trang chưa đọc được. Bạn chụp lại giúp mình nhé.",
                             f"{len(retake)} pages could not be read. Please retake them.")
                o = self.outline(cid)
                if o:
                    n_l = sum(len(c["lessons"]) for c in o["chapters"])
                    self.say(st, "agent", "outline", f"Đây là cấu trúc đề xuất: {len(o['chapters'])} chương, {n_l} bài.",
                             f"Proposed outline: {len(o['chapters'])} chapters, {n_l} lessons.")
                notify = f"Đã đọc xong tài liệu «{title}»." + (f" Cần chụp lại {len(retake)} trang." if retake
                                                              else " Mời bạn xem cấu trúc.")
        elif kind == "outline_chat":
            if ok:
                st["outline_edited"] = True
                self.say(st, "agent", "outline", result.get("message_vi"), result.get("message_en"))
            else:
                self.say(st, "agent", "notice", f"Chưa sửa được cấu trúc: {err[:200]}", f"Could not edit the outline: {err[:200]}")
        elif kind == "build":
            if ok:
                self._archive_comments(st)
                self.say(st, "agent", "build", result.get("message_vi"), result.get("message_en"))
                if result.get("blocked"):  # hard errors left after the refine gate: tell the teacher, publishing is blocked
                    notify = f"Khóa «{title}» đã soạn xong nhưng còn lỗi cần xử lý trước khi xuất bản."
                else:
                    notify = f"Khóa «{title}» đã soạn xong, mời bạn duyệt."
            else:
                self.say(st, "agent", "notice", f"Soạn khóa chưa xong: {err[:200]}", f"The build did not finish: {err[:200]}")
                notify = f"Soạn khóa «{title}» chưa xong."
        else:  # revise_*
            cm = next((c for c in st["comments"] if c["id"] == job.get("comment_id")), None)
            if cm is not None:
                cm["status"] = "applied" if ok else "failed"
                cm["note"] = (result.get("note") or None) if ok else err[:300]
                cm["updated_at"] = _iso(self.clock())
            if ok:
                self.say(st, "agent", "notice", result.get("message_vi"), result.get("message_en"))
                notify = f"Đã sửa «{title}» theo nhận xét của bạn."
            else:
                self.say(st, "agent", "notice", f"Chưa sửa được: {err[:200]}", f"Could not apply it: {err[:200]}")
                notify = f"Chưa sửa được nhận xét ở «{title}»."
        return notify

    # ------------------------------------------------------------ read model
    def _json(self, cid: str, rel: str, default: Any = None) -> Any:
        f = self.course_dir(cid) / rel
        try:
            return json.loads(f.read_text("utf-8")) if f.is_file() else default
        except ValueError:
            return default

    def outline(self, cid: str) -> dict | None:
        return self._json(cid, "outline.json")

    def retake(self, cid: str) -> list[dict]:
        out = []
        pages = {(Path(p["source_file"]).name, p["index"]): p for m in self._json(cid, "intake/pages.json", [])
                 for p in m.get("pages", [])}
        for c in self._json(cid, "intake/checks.json", []):
            if c.get("ok", True):
                continue
            name = Path(str(c["source_file"]).replace("\\", "/")).name
            ref = f"{name}#{c['page']}"
            has_img = bool(pages.get((name, c["page"]), {}).get("image_path"))
            from urllib.parse import quote

            out.append({"ref": ref, "source_file": name, "page": c["page"], "reasons": c.get("reasons", []),
                        "message_vi": c.get("message_vi", ""), "message_en": c.get("message_en", ""),
                        "thumb_url": f"/api/teacher/courses/{cid}/thumb?ref={quote(ref)}" if has_img else None})
        return out

    def page_image(self, cid: str, ref: str) -> Path | None:
        name, _, idx = ref.rpartition("#")
        for m in self._json(cid, "intake/pages.json", []):
            for p in m.get("pages", []):
                if Path(p["source_file"].replace("\\", "/")).name == name and str(p["index"]) == idx and p.get("image_path"):
                    f = Path(p["image_path"])
                    base = self.course_dir(cid).resolve()
                    if f.is_file() and base in f.resolve().parents:
                        return f
        return None

    def build_lessons(self, cid: str) -> list[dict]:
        prog = self._json(cid, "build/progress.json")
        if prog:
            return [{"id": ls["id"], "title": ls["title"], "state": ls["state"],
                     **({"note": ls["note"]} if ls.get("note") else {})} for ls in prog["lessons"]]
        o = self.outline(cid)
        return [{"id": ls["id"], "title": ls["title"], "state": "waiting"}
                for ch in (o or {"chapters": []})["chapters"] for ls in ch["lessons"]]

    def verify_report(self, cid: str) -> dict | None:
        """The build's verify-and-refine report of the latest unpublished version ({blocked, hard, soft, fixed, ...})."""
        versions, _, _ = self.versions(cid)
        open_v = [v["version"] for v in versions if v["status"] != "published"]
        return self._json(cid, f"versions/{max(open_v)}/verify.json") if open_v else None

    def publish_blockers(self, cid: str, version: int) -> list[dict]:
        """Hard problems of a version, checked now (static checks of mentor_course_builder.refine plus the build's
        independent-solve verdicts that still apply). Publishing is refused while this list is not empty."""
        from mentor_course_builder import refine
        from mentor_course_builder.outline import CourseOutline

        o = self.outline(cid)
        try:
            outline = CourseOutline.model_validate(o) if o else None
        except Exception:  # noqa: BLE001 - a hand-edited outline file must not make publishing impossible
            outline = None
        stored = (self._json(cid, f"versions/{version}/verify.json", {}) or {}).get("hard")
        return [i.as_dict() for i in refine.check_store_version(self.content.store, cid, version, outline, stored)]

    def student_counts(self, cid: str) -> dict[int, int]:
        with self.db.session() as s:
            rows = s.execute(select(Enrollment.version, func.count()).where(Enrollment.course_id == cid)
                             .group_by(Enrollment.version)).all()
        return {int(v): int(n) for v, n in rows}

    def level_state(self, cid: str) -> dict:
        """Course level as the teacher sees it: `level` is what students see (latest published), `level_suggested` and
        `level_confirmed` belong to the working version (the open draft, else the latest published one)."""
        meta = self._store_meta(cid)
        if meta is None or not meta.versions:
            return {"level": None, "level_suggested": None, "level_confirmed": None}
        open_v = [v for v in meta.versions if v.status != "published"]
        work = max(open_v, key=lambda v: v.version) if open_v else max(meta.versions, key=lambda v: v.version)
        confirmed = work.level_confirmed or (meta.level if work.status == "published" else None)
        return {"level": meta.level, "level_suggested": work.level_suggested, "level_confirmed": confirmed}

    def set_level(self, st: dict, version: int, level: str) -> dict:
        """Teacher confirms or changes the level. On a draft it is stored on that version. On a published version a
        different level goes the new-version way: it lands in the open draft (created from the published one when there
        is none), and students see it when that version is published. Returns {version, new_version, ...level_state}."""
        cid = st["course_id"]
        store = self.content.store
        meta = store.load_meta(cid)
        info = store.version_info(meta, version)
        created = False
        if info.status == "published":
            if level == (info.level_confirmed or meta.level):
                return {"version": version, "new_version": False, **self.level_state(cid)}
            open_v = [v.version for v in meta.versions if v.status != "published"]
            if open_v:
                version = max(open_v)
            else:
                if self.active_jobs(st):
                    raise Busy("busy", "the agent is working on this course")
                version = self.new_version_from_published(st)
                created = True
        store.set_level(cid, version, confirmed=level)
        self._save(st)
        self.emit(st)
        return {"version": version, "new_version": created, **self.level_state(cid)}

    def versions(self, cid: str) -> tuple[list[dict], int | None, int]:
        meta = self._store_meta(cid)
        if meta is None:
            return [], None, 0
        counts = self.student_counts(cid)
        vs = [{"version": v.version, "status": v.status, "students": counts.get(v.version, 0),
               "level_suggested": v.level_suggested, "level_confirmed": v.level_confirmed} for v in meta.versions]
        return vs, meta.latest_published, max((v.version for v in meta.versions), default=0)

    @staticmethod
    def _line(status: str, n_retake: int, build: dict | None, published: int | None, students: int,
              draft: int | None) -> tuple[str, str]:
        return {
            "reading": ("Đang đọc tài liệu", "Reading your material"),
            "needs_retake": (f"Cần chụp lại {n_retake} trang", f"{n_retake} pages need a retake"),
            "outline_ready": ("Cần bạn xem cấu trúc", "Review the outline"),
            "building": (f"Đang soạn ({build['done']}/{build['total']} bài)" if build else "Đang soạn",
                         f"Building ({build['done']}/{build['total']} lessons)" if build else "Building"),
            "review": ("Chờ duyệt", "Waiting for your review"),
            "published": (f"Đã xuất bản (bản {published}, {students} học sinh)",
                          f"Published (v{published}, {students} students)"),
            "revising": (f"Đang sửa bản {draft}", f"Editing v{draft}"),
        }[status]

    def status_of(self, st: dict) -> dict:
        cid = st["course_id"]
        kinds = {j["kind"] for j in self.active_jobs(st)}
        versions, published, latest = self.versions(cid)
        unpublished = [v["version"] for v in versions if v["status"] != "published"]
        retake = self.retake(cid)
        lessons = self.build_lessons(cid)
        build = {"done": sum(1 for ls in lessons if ls["state"] == "done"), "total": len(lessons)}
        if "build" in kinds:
            status = "building"
        elif kinds & {"revise_text", "revise_media", "revise_all"}:
            status = "revising"
        elif kinds & {"intake", "outline_chat"}:
            status = "reading"
        elif unpublished:
            status = "revising" if published else "review"
        elif published:
            status = "published"
        elif retake:
            status = "needs_retake"
        elif self.outline(cid):
            status = "outline_ready"
        else:
            status = "reading"
        students = next((v["students"] for v in versions if v["version"] == published), 0)
        vi, en = self._line(status, len(retake), build, published, students, max(unpublished, default=None))
        return {"status": status, "status_line_vi": vi, "status_line_en": en, "build": build if status == "building" else None,
                "versions": versions, "latest_published": published, "latest_version": latest, "retake": retake,
                "lessons": lessons}

    def cover_sha(self, cid: str) -> str | None:
        try:
            return sha256_file(self.content.store.cover_path(cid))
        except ContentError:
            return None

    def view(self, st: dict) -> dict:
        cid = st["course_id"]
        s = self.status_of(st)
        out = {"id": cid, "title": self.title_of(st), "status": s["status"], "status_line_vi": s["status_line_vi"],
               "status_line_en": s["status_line_en"], "cover_sha256": self.cover_sha(cid), "updated_at": st["updated_at"],
               "latest_version": s["latest_version"], "versions": s["versions"], **self.level_state(cid)}
        if s["build"]:
            out["build"] = s["build"]
        return out

    def detail(self, st: dict) -> dict:
        cid = st["course_id"]
        s = self.status_of(st)
        o = self.outline(cid)
        meta = self._store_meta(cid)
        course = {"id": cid, "title": self.title_of(st), "teacher_note": st.get("note"),
                  "subject": (o or {}).get("subject") or (meta.subject if meta else None),
                  "age_band": (o or {}).get("age_band") or (meta.age_band if meta else None),
                  "language": (o or {}).get("language") or (meta.language if meta else None),
                  "description_short": (o or {}).get("description_short") or (meta.description_short if meta else ""),
                  "outcomes": (o or {}).get("outcomes") or (meta.outcomes if meta else []),
                  "cover_sha256": self.cover_sha(cid), "latest_published": s["latest_published"],
                  "latest_version": s["latest_version"], "versions": s["versions"], "created_at": st["created_at"],
                  **self.level_state(cid)}
        return {"course": course, "status": s["status"], "status_line_vi": s["status_line_vi"],
                "status_line_en": s["status_line_en"], "outline": o, "retake": s["retake"],
                "build": {"lessons": s["lessons"]}, "verify": self.verify_report(cid), "chat": st["chat"],
                "updated_at": st["updated_at"], "released_app_version": self.settings.released_app_version}

    def emit(self, st: dict) -> None:
        """SSE: tell the teacher's open apps that this course changed."""
        try:
            v = self.view(st)
        except Exception:  # noqa: BLE001
            log.warning("cannot build the event for %s", st["course_id"], exc_info=True)
            return
        self.bus.publish(st["teacher_id"], {"type": "course", "course_id": st["course_id"], **{
            k: v[k] for k in ("status", "status_line_vi", "status_line_en", "updated_at", "title")},
            **({"build": v["build"]} if "build" in v else {})})

    # ------------------------------------------------------------ comments and versions
    def _archive_comments(self, st: dict) -> None:
        """A rebuild rewrites the open draft in place, so the comments left on its previous content no longer
        apply: mark them `stale` (kept, never deleted; the list endpoint hides them unless asked)."""
        meta = self._store_meta(st["course_id"])
        open_v = {v.version for v in meta.versions if v.status != "published"} if meta else set()
        for c in st["comments"]:
            if c["version"] in open_v:
                c["stale"] = True

    # ---- (comments and versions)
    def new_version_from_published(self, st: dict) -> int:
        """Draft v+1 copied from the latest published version (pack, assets, editable media sources)."""
        cid = st["course_id"]
        store = self.content.store
        meta = store.load_meta(cid)
        pub = meta.latest_published
        if pub is None:
            raise ContentError("nothing_published")
        open_v = [v.version for v in meta.versions if v.status != "published"]
        if open_v:
            raise Busy("draft_exists", f"version {max(open_v)} is still a draft")
        with self._lock:
            version = store.create_draft(meta, note=f"edit of v{pub}")
            pack = store.load_pack(cid, pub)
            src = store.version_dir(cid, pub) / "assets"
            assets = {a.path: src / a.path for a in pack.assets()}
            store.write_pack(cid, version, pack.model_copy(update={"version": version}), assets)
            store.set_level(cid, version, inherit=True)  # students keep seeing the same level until the teacher changes it
            old, new = self.course_dir(cid) / "versions" / str(pub), self.course_dir(cid) / "versions" / str(version)
            if (old / "media.json").is_file():
                new.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(old / "media.json", new / "media.json")
                if (old / "media").is_dir():
                    shutil.copytree(old / "media", new / "media", dirs_exist_ok=True)
            self.say(st, "agent", "notice", f"Đã tạo bản {version} để sửa. Học sinh đang học vẫn giữ bản {pub}.",
                     f"Created v{version} for editing. Students keep v{pub}.")
            self._save(st)
        self.emit(st)
        return version

    def add_comment(self, st: dict, version: int, block_id: str, anchor: dict, body: str) -> tuple[dict, dict]:
        cid = st["course_id"]
        store = self.content.store
        info = store.version_info(store.load_meta(cid), version)
        if info.status == "published":
            raise Immutable("version_published", "comments apply to a draft: create a new version first")
        pack = store.load_pack(cid, version)
        block = next((b for ch in pack.chapters for ls in ch.lessons for b in ls.blocks if b.id == block_id), None)
        if block is None:
            raise ContentError("unknown_block", block_id)
        ok = {"text": (TextBlock, CalloutBlock, QuizBlock), "time": (VideoBlock,), "point": (ImageBlock,)}[anchor["kind"]]
        if not isinstance(block, ok):
            raise ContentError("anchor_mismatch", f"a {anchor['kind']} anchor does not fit a {block.kind} block")
        now = _iso(self.clock())
        c = {"id": new_id("cm"), "version": version, "block_id": block_id, "anchor": anchor, "body": body,
             "status": "open", "note": None, "created_at": now, "updated_at": now}
        args = {"course_id": cid, "version": version, "store": str(self.content.store.root), "block_id": block_id,
                "anchor": anchor, "comment": body, "teacher_id": st["teacher_id"]}
        with self._lock:
            st["comments"].append(c)
            snapshot = dict(c)
            job = self.enqueue(st, "revise_text" if anchor["kind"] == "text" else "revise_media", args,
                               comment_id=c["id"], kick=False)
            self._save(st)
        return snapshot, job

    # ------------------------------------------------------------ job arguments
    def intake_args(self, st: dict, batch: str, names: list[str], replace: list[str]) -> dict:
        return {"course_id": st["course_id"], "batch": batch, "files": names, "replace": replace, "note": st.get("note"),
                "outline_edited": bool(st.get("outline_edited")), "workers": 3}

    def build_args(self, st: dict) -> dict:
        return {"course_id": st["course_id"], "store": str(self.content.store.root), "teacher_id": st["teacher_id"],
                "teacher_name": st["teacher_name"], "deeptutor": self.settings.builder_deeptutor,
                "media_kinds": [k.strip() for k in self.settings.builder_media_kinds.split(",") if k.strip()],
                "workers": 2, "media_workers": 2}

    def reset_progress(self, st: dict) -> None:
        o = self.outline(st["course_id"]) or {"chapters": []}
        atomic_write(self.course_dir(st["course_id"]) / "build" / "progress.json", json.dumps(
            {"stage": "queued", "cover": "waiting", "lessons": [
                {"id": ls["id"], "title": ls["title"], "state": "waiting"} for ch in o["chapters"] for ls in ch["lessons"]]},
            ensure_ascii=False).encode("utf-8"))
