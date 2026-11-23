"""A git-free workspace mirror for the standalone desktop package (student PCs have no `git`).

Same interface as `mirror.Mirror`, so practice evidence, the workspace viewer, engagement and every other reader
and writer keep working. Storage per learner, `$MENTOR_DATA_DIR/mirrors/<user_id>.fm/`:

    log.jsonl            append-only commit log, one JSON object per line (sha, parent, author, ts, message, changes)
    objects/<aa>/<sha>   file contents, named by their git blob id (so `provisioning._blob_sha` still matches)

A commit lists only what it changed (`path -> blob sha`, or `null` for a deletion); the tree at any commit is the
replay of the log up to it. That gives `history`, `rev_before` and `<rev>:<path>` reads without any git machinery.
The log is only ever appended to (flushed and fsynced), so a crash leaves at worst one torn last line, which is skipped.
"""

import hashlib
import io
import json
import logging
import os
import threading
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from mentor_gateway.gitrepo import UserLocks
from mentor_gateway.mirror import BRANCH, REF, Commit, Mirror, StaleBaseError, TreeEntry, WorkspaceSync, _rmtree

log = logging.getLogger(__name__)

AUTHORS = ("mentor", "user", "system")


def blob_sha(data: bytes) -> str:
    """The id git gives these bytes as a blob."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest()


@dataclass
class _Log:
    size: int = 0
    commits: list[dict] = field(default_factory=list)
    state: dict[str, str] = field(default_factory=dict)  # path -> blob sha at head


class FileMirror(Mirror):
    SUFFIX = ".fm"

    def __init__(self, root: Path, locks: UserLocks) -> None:
        super().__init__(root, locks)
        self._cache: dict[str, _Log] = {}
        self._guard = threading.Lock()

    # ---- layout ------------------------------------------------------------------------------

    def path(self, user_id: str) -> Path:
        return (self.root / f"{user_id}{self.SUFFIX}").resolve()

    def _log_file(self, user_id: str) -> Path:
        return self.path(user_id) / "log.jsonl"

    def _object(self, user_id: str, sha: str) -> Path:
        return self.path(user_id) / "objects" / sha[:2] / sha

    def exists(self, user_id: str) -> bool:
        return self._log_file(user_id).exists()

    def create(self, user_id: str) -> Path:
        p = self.path(user_id)
        (p / "objects").mkdir(parents=True, exist_ok=True)
        lf = self._log_file(user_id)
        if not lf.exists():
            lf.write_bytes(b"")
        return p

    def delete(self, user_id: str) -> None:
        with self.locks.get(user_id):
            _rmtree(self.path(user_id))
            with self._guard:
                self._cache.pop(user_id, None)

    # ---- the log -----------------------------------------------------------------------------

    def _load(self, user_id: str) -> _Log:
        """The parsed log, re-read only when the file grew (another process, or the first access)."""
        lf = self._log_file(user_id)
        try:
            size = lf.stat().st_size
        except FileNotFoundError:
            return _Log()
        with self._guard:
            cached = self._cache.get(user_id)
            if cached is not None and cached.size == size:
                return cached
            commits: list[dict] = []
            state: dict[str, str] = {}
            for line in lf.read_bytes().decode("utf-8", "replace").splitlines():
                try:
                    rec = json.loads(line)
                    changes = rec["changes"]
                    _ = rec["sha"]
                except (ValueError, KeyError, TypeError):
                    continue  # a torn last line
                commits.append(rec)
                for path, sha in changes.items():
                    if sha is None:
                        state.pop(path, None)
                    else:
                        state[path] = sha
            fresh = _Log(size=size, commits=commits, state=state)
            self._cache[user_id] = fresh
            return fresh

    @staticmethod
    def _state_at(log_: _Log, sha: str) -> dict[str, str] | None:
        if not log_.commits or sha in (BRANCH, REF, "HEAD"):
            return log_.state
        state: dict[str, str] = {}
        for rec in log_.commits:
            for path, b in rec["changes"].items():
                if b is None:
                    state.pop(path, None)
                else:
                    state[path] = b
            if rec["sha"] == sha:
                return state
        return None

    def _blob(self, user_id: str, sha: str) -> bytes | None:
        try:
            return self._object(user_id, sha).read_bytes()
        except FileNotFoundError:
            return None

    def head(self, user_id: str) -> str | None:
        commits = self._load(user_id).commits
        return commits[-1]["sha"] if commits else None

    # ---- reads -------------------------------------------------------------------------------

    def ls_tree(self, user_id: str) -> list[TreeEntry]:
        state = self._load(user_id).state
        entries: dict[str, TreeEntry] = {}
        for path, sha in state.items():
            try:
                size = self._object(user_id, sha).stat().st_size
            except FileNotFoundError:
                size = 0
            entries[path] = TreeEntry(path=path, type="file", size=size, sha=sha)
            for parent in list(PurePosixPath(path).parents)[:-1]:  # every folder above the file
                key = parent.as_posix()
                entries.setdefault(key, TreeEntry(path=key, type="dir", size=0, sha=""))
        return [entries[k] for k in sorted(entries)]

    def blob_sha(self, user_id: str, path: str) -> str | None:
        return self._load(user_id).state.get(path)

    def read(self, user_id: str, path: str) -> tuple[bytes, str] | None:
        sha = self.blob_sha(user_id, path)
        if sha is None:
            return None
        data = self._blob(user_id, sha)
        return None if data is None else (data, sha)

    def rev_before(self, user_id: str, when: datetime) -> str | None:
        best = None
        for rec in self._load(user_id).commits:
            if datetime.fromisoformat(rec["ts"]) <= when:
                best = rec["sha"]
        return best

    def read_batch(self, user_id: str, specs: list[str]) -> list[str | None]:
        log_ = self._load(user_id)
        if not specs or not log_.commits:
            return [None] * len(specs)
        results: list[str | None] = []
        for spec in specs:
            rev, _, path = spec.partition(":")
            state = self._state_at(log_, rev)
            sha = state.get(path) if state is not None else None
            data = self._blob(user_id, sha) if sha else None
            results.append(None if data is None else data.decode("utf-8", "replace"))
        return results

    def last_modified(self, user_id: str) -> dict[str, datetime]:
        log_ = self._load(user_id)
        result: dict[str, datetime] = {}
        for rec in log_.commits:
            ts = datetime.fromisoformat(rec["ts"])
            for path in rec["changes"]:
                if path in log_.state:
                    result[path] = ts
        return result

    def history(self, user_id: str, path: str | None = None, limit: int = 100) -> list[Commit]:
        commits = []
        for rec in reversed(self._load(user_id).commits):
            if path and not any(p == path or p.startswith(path.rstrip("/") + "/") for p in rec["changes"]):
                continue
            author = rec["author"] if rec["author"] in AUTHORS else "system"
            commits.append(Commit(sha=rec["sha"], author=author, ts=datetime.fromisoformat(rec["ts"]),
                                  message=rec["message"]))
            if len(commits) >= limit:
                break
        return commits

    def archive_zip(self, user_id: str) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for path, sha in sorted(self._load(user_id).state.items()):
                data = self._blob(user_id, sha)
                if data is not None:
                    z.writestr(path, data)
        return buf.getvalue()

    # ---- writes ------------------------------------------------------------------------------

    def _write_object(self, user_id: str, data: bytes) -> str:
        sha = blob_sha(data)
        target = self._object(user_id, sha)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(f".{sha}.{os.getpid()}.{threading.get_ident()}.tmp")
            tmp.write_bytes(data)
            os.replace(tmp, target)
        return sha

    def commit_files(
        self,
        user_id: str,
        changes: dict[str, bytes | None],
        *,
        author: str,
        message: str,
        expected: dict[str, str | None] | None = None,
    ) -> str:
        with self.locks.get(user_id):
            self.create(user_id)
            log_ = self._load(user_id)
            for path, base in (expected or {}).items():
                current = log_.state.get(path)
                if (base or None) != current:
                    raise StaleBaseError(path, current)
            parent = log_.commits[-1]["sha"] if log_.commits else None
            recorded = {path: (None if data is None else self._write_object(user_id, data))
                        for path, data in changes.items()}
            ts = datetime.now(UTC).isoformat()
            body = {"parent": parent, "author": author, "ts": ts, "message": message, "changes": recorded}
            sha = hashlib.sha1(json.dumps(body, sort_keys=True).encode("utf-8"), usedforsecurity=False).hexdigest()
            rec = {"sha": sha, **body}
            line = (json.dumps(rec, ensure_ascii=False) + "\n").encode("utf-8")
            lf = self._log_file(user_id)
            if lf.stat().st_size:
                with lf.open("rb") as f:
                    f.seek(-1, os.SEEK_END)
                    if f.read(1) != b"\n":
                        line = b"\n" + line  # a torn last line must not swallow this commit
            with lf.open("ab") as f:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())
            with self._guard:  # keep the parsed log current instead of re-reading all of it on the next access
                log_.commits.append(rec)
                for path, b in recorded.items():
                    if b is None:
                        log_.state.pop(path, None)
                    else:
                        log_.state[path] = b
                log_.size += len(line)
                self._cache[user_id] = log_
            return sha


class FileWorkspaceSync(WorkspaceSync):
    """The standalone package has no sandbox that mounts a working copy: the staged workspace folder is committed
    into the mirror once and pull/push have nothing to synchronise."""

    def __init__(self, root: Path, mirror: FileMirror, locks: UserLocks) -> None:
        super().__init__(root, mirror, locks)
        self.mirror: FileMirror = mirror

    def exists(self, user_id: str) -> bool:
        return self.path(user_id).is_dir()

    def init_from_dir(self, user_id: str) -> None:
        wd = self.path(user_id)
        files: dict[str, bytes | None] = {}
        for f in sorted(wd.rglob("*")):
            if f.is_file() and ".git" not in f.relative_to(wd).parts:
                files[f.relative_to(wd).as_posix()] = f.read_bytes()
        with self.locks.get(user_id):
            self.mirror.create(user_id)
            self.mirror.commit_files(user_id, files, author="system", message="Khởi tạo workspace")

    def configure(self, user_id: str) -> None:
        return None

    def ensure_clone(self, user_id: str) -> Path:
        return self.path(user_id)

    def is_dirty(self, user_id: str) -> bool:
        return False

    def commit_dirty(self, user_id: str, author: str = "mentor", message: str = "") -> bool:
        return False

    def pull(self, user_id: str) -> None:
        return None

    def push(self, user_id: str, attempts: int = 3) -> str | None:
        return self.mirror.head(user_id)
