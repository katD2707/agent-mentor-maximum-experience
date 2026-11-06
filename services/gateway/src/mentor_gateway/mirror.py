"""Per-user workspace mirror (plan section 5.4) and the sandbox-side working copy sync.

- The mirror is a bare git repo at `$MENTOR_DATA_DIR/mirrors/<user_id>.git`, branch `main`.
  The web viewer reads only from it, so reads work while the sandbox sleeps.
- User edits from the web are committed straight into the mirror with git plumbing
  (author `user <user@local>`), guarded by the blob sha the client last saw.
- The working copy the sandbox mounts lives at `$MENTOR_DATA_DIR/workspaces/<user_id>/`.
  Before a turn/job it merges the mirror with a user-wins policy; after it, it pushes.
"""

import io
import logging
import os
import shutil
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath

from mentor_gateway.gitrepo import GitError, UserLocks, out, run_git

log = logging.getLogger(__name__)

BRANCH = "main"
REF = f"refs/heads/{BRANCH}"


class StaleBaseError(Exception):
    """The file changed in the mirror since the client read it (HTTP 409)."""

    def __init__(self, path: str, current_sha: str | None) -> None:
        super().__init__(f"{path} changed (current sha {current_sha})")
        self.path = path
        self.current_sha = current_sha


@dataclass
class TreeEntry:
    path: str
    type: str  # file | dir
    size: int
    sha: str


@dataclass
class Commit:
    sha: str
    author: str
    ts: datetime
    message: str


def normalize_path(path: str) -> str:
    """Workspace-relative POSIX path; raises ValueError on absolute paths or `..`."""
    p = PurePosixPath(path.replace("\\", "/").strip())
    if not path or p.is_absolute() or ".." in p.parts or str(p) in ("", "."):
        raise ValueError(f"invalid workspace path: {path!r}")
    if p.parts[0] == ".git":
        raise ValueError(f"invalid workspace path: {path!r}")
    return p.as_posix()


def _rmtree(path: Path) -> None:
    def onerror(func, p, _exc):  # git objects are read-only on Windows
        os.chmod(p, stat.S_IWRITE)
        func(p)

    if path.exists():
        shutil.rmtree(path, onerror=onerror)


class Mirror:
    def __init__(self, root: Path, locks: UserLocks) -> None:
        self.root = root
        self.locks = locks

    def path(self, user_id: str) -> Path:
        return (self.root / f"{user_id}.git").resolve()

    def exists(self, user_id: str) -> bool:
        return (self.path(user_id) / "HEAD").exists()

    def create(self, user_id: str) -> Path:
        p = self.path(user_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        if not self.exists(user_id):
            run_git(["init", "--bare", "-q", "-b", BRANCH, str(p)])
        return p

    def delete(self, user_id: str) -> None:
        with self.locks.get(user_id):
            _rmtree(self.path(user_id))

    def head(self, user_id: str) -> str | None:
        if not self.exists(user_id):
            return None
        proc = run_git(["rev-parse", "--verify", "-q", REF], git_dir=self.path(user_id), check=False)
        return out(proc) or None

    # ---- reads -------------------------------------------------------------------------------

    def ls_tree(self, user_id: str) -> list[TreeEntry]:
        if not self.exists(user_id):
            return []
        proc = run_git(["ls-tree", "-r", "-t", "-l", "-z", REF], git_dir=self.path(user_id), check=False)
        if proc.returncode != 0:  # no commit yet
            return []
        entries: list[TreeEntry] = []
        for rec in proc.stdout.decode("utf-8", "replace").split("\0"):
            if not rec:
                continue
            meta, path = rec.split("\t", 1)
            _mode, otype, sha, size = meta.split()
            entries.append(
                TreeEntry(path=path, type="dir" if otype == "tree" else "file", size=0 if size == "-" else int(size), sha=sha)
            )
        return entries

    def blob_sha(self, user_id: str, path: str) -> str | None:
        """Blob sha of a file on `main`, or None if missing (or a directory). One git call."""
        if not self.exists(user_id):
            return None
        proc = run_git(["ls-tree", "-z", REF, "--", path], git_dir=self.path(user_id), check=False)
        for rec in proc.stdout.decode("utf-8", "replace").split("\0"):
            if not rec:
                continue
            meta, name = rec.split("\t", 1)
            _mode, otype, sha = meta.split()
            if name == path and otype == "blob":
                return sha
        return None

    def read(self, user_id: str, path: str) -> tuple[bytes, str] | None:
        sha = self.blob_sha(user_id, path)
        if sha is None:
            return None
        data = run_git(["cat-file", "blob", sha], git_dir=self.path(user_id)).stdout
        return data, sha

    def read_text(self, user_id: str, path: str) -> str | None:
        got = self.read(user_id, path)
        return None if got is None else got[0].decode("utf-8", "replace")

    def rev_before(self, user_id: str, when: datetime) -> str | None:
        """Last commit on `main` made before `when`, or None."""
        if self.head(user_id) is None:
            return None
        proc = run_git(["rev-list", "-1", f"--before={int(when.timestamp())}", REF], git_dir=self.path(user_id),
                       check=False)
        return out(proc) or None

    def read_batch(self, user_id: str, specs: list[str]) -> list[str | None]:
        """Contents of several `<rev>:<path>` specs (text) in one `git cat-file --batch`; None when missing."""
        if not specs or self.head(user_id) is None:
            return [None] * len(specs)
        data = run_git(["cat-file", "--batch"], git_dir=self.path(user_id),
                       input=("\n".join(specs) + "\n").encode("utf-8")).stdout
        results: list[str | None] = []
        pos = 0
        for _ in specs:
            nl = data.index(b"\n", pos)
            header = data[pos:nl].decode("utf-8", "replace").split()
            pos = nl + 1
            if len(header) == 3 and header[1] in ("blob", "tree", "commit", "tag"):
                size = int(header[2])
                body = data[pos:pos + size]
                pos += size + 1
                results.append(body.decode("utf-8", "replace") if header[1] == "blob" else None)
            else:  # "<spec> missing" / "ambiguous"
                results.append(None)
        return results

    def last_modified(self, user_id: str) -> dict[str, datetime]:
        """Last commit time per path (files only), from one `git log` pass."""
        if self.head(user_id) is None:
            return {}
        proc = run_git(["log", "--format=\x01%cI", "--name-only", "-z", REF], git_dir=self.path(user_id))
        result: dict[str, datetime] = {}
        current: datetime | None = None
        for token in proc.stdout.decode("utf-8", "replace").split("\0"):
            for part in token.split("\n"):
                part = part.strip()
                if not part:
                    continue
                if part.startswith("\x01"):
                    current = datetime.fromisoformat(part[1:])
                elif current is not None and part not in result:
                    result[part] = current
        return result

    def history(self, user_id: str, path: str | None = None, limit: int = 100) -> list[Commit]:
        if self.head(user_id) is None:
            return []
        args = ["log", f"-n{limit}", "--format=%H%x1f%an%x1f%aI%x1f%s%x1e", REF]
        if path:
            args += ["--", path]
        proc = run_git(args, git_dir=self.path(user_id))
        commits = []
        for rec in proc.stdout.decode("utf-8", "replace").split("\x1e"):
            rec = rec.strip()
            if not rec:
                continue
            sha, author, ts, msg = rec.split("\x1f", 3)
            commits.append(
                Commit(sha=sha, author=author if author in ("mentor", "user", "system") else "system",
                       ts=datetime.fromisoformat(ts), message=msg)
            )
        return commits

    def archive_zip(self, user_id: str) -> bytes:
        if self.head(user_id) is None:
            buf = io.BytesIO()
            zipfile.ZipFile(buf, "w").close()
            return buf.getvalue()
        return run_git(["archive", "--format=zip", REF], git_dir=self.path(user_id)).stdout

    # ---- writes ------------------------------------------------------------------------------

    def commit_files(
        self,
        user_id: str,
        changes: dict[str, bytes | None],
        *,
        author: str,
        message: str,
        expected: dict[str, str | None] | None = None,
    ) -> str:
        """Commit file writes (bytes) and deletions (None) on top of `main`.

        `expected` maps paths to the blob sha the caller last saw (None = must not exist);
        a mismatch raises StaleBaseError before anything is written.
        """
        gd = self.path(user_id)
        with self.locks.get(user_id):
            for path, base in (expected or {}).items():
                current = self.blob_sha(user_id, path)
                if (base or None) != current:
                    raise StaleBaseError(path, current)
            parent = self.head(user_id)
            fd, index_file = tempfile.mkstemp(prefix="mentor-index-")
            os.close(fd)
            os.unlink(index_file)
            env = {"GIT_INDEX_FILE": index_file}
            try:
                if parent:
                    run_git(["read-tree", parent], git_dir=gd, env=env)
                else:
                    run_git(["read-tree", "--empty"], git_dir=gd, env=env)
                info = []
                for path, data in changes.items():
                    if data is None:
                        info.append(f"0 {'0' * 40}\t{path}")  # mode 0 removes the entry
                    else:
                        blob = out(run_git(["hash-object", "-w", "--stdin"], git_dir=gd, input=data))
                        info.append(f"100644 {blob}\t{path}")
                run_git(["update-index", "--index-info"], git_dir=gd, env=env,
                        input=("\n".join(info) + "\n").encode("utf-8"))
                tree = out(run_git(["write-tree"], git_dir=gd, env=env))
            finally:
                if os.path.exists(index_file):
                    os.unlink(index_file)
            args = ["commit-tree", tree, "-m", message]
            if parent:
                args[2:2] = ["-p", parent]
            commit = out(run_git(args, git_dir=gd, author=author))
            run_git(["update-ref", REF, commit, parent or "0" * 40], git_dir=gd)
            return commit


class WorkspaceSync:
    """The working copy the sandbox mounts, synchronised with the mirror."""

    REMOTE = "mirror"

    def __init__(self, root: Path, mirror: Mirror, locks: UserLocks) -> None:
        self.root = root
        self.mirror = mirror
        self.locks = locks

    def path(self, user_id: str) -> Path:
        return (self.root / user_id).resolve()

    def exists(self, user_id: str) -> bool:
        return (self.path(user_id) / ".git").exists()

    def delete(self, user_id: str) -> None:
        with self.locks.get(user_id):
            _rmtree(self.path(user_id))

    def configure(self, user_id: str) -> None:
        wd = self.path(user_id)
        for key, value in (("core.autocrlf", "false"), ("commit.gpgsign", "false"), ("user.name", "mentor"),
                           ("user.email", "mentor@local")):
            run_git(["config", key, value], cwd=wd)

    def init_from_dir(self, user_id: str) -> None:
        """First commit of a freshly provisioned workspace, then push it to a new mirror."""
        wd = self.path(user_id)
        with self.locks.get(user_id):
            run_git(["init", "-q", "-b", BRANCH], cwd=wd)
            self.configure(user_id)
            run_git(["add", "-A"], cwd=wd)
            run_git(["commit", "-q", "--allow-empty", "-m", "Khởi tạo workspace"], cwd=wd, author="system")
            self.mirror.create(user_id)
            self._set_remote(user_id)
            run_git(["push", "-q", self.REMOTE, f"HEAD:{REF}"], cwd=wd)

    def _set_remote(self, user_id: str) -> None:
        wd = self.path(user_id)
        url = self.mirror.path(user_id).as_posix()
        proc = run_git(["remote", "get-url", self.REMOTE], cwd=wd, check=False)
        if proc.returncode != 0:
            run_git(["remote", "add", self.REMOTE, url], cwd=wd)
        elif out(proc) != url:
            run_git(["remote", "set-url", self.REMOTE, url], cwd=wd)

    def ensure_clone(self, user_id: str) -> Path:
        wd = self.path(user_id)
        with self.locks.get(user_id):
            if not self.exists(user_id):
                if not self.mirror.exists(user_id):
                    raise FileNotFoundError(f"no mirror for {user_id}")
                wd.parent.mkdir(parents=True, exist_ok=True)
                run_git(["clone", "-q", "-o", self.REMOTE, self.mirror.path(user_id).as_posix(), str(wd)])
                self.configure(user_id)
            self._set_remote(user_id)
        return wd

    def is_dirty(self, user_id: str) -> bool:
        return bool(out(run_git(["status", "--porcelain"], cwd=self.path(user_id))))

    def commit_dirty(self, user_id: str, author: str = "mentor", message: str = "Lưu thay đổi chưa commit") -> bool:
        """Safety net: the harness commits after each turn/job; anything left over is committed here."""
        wd = self.path(user_id)
        with self.locks.get(user_id):
            if not self.is_dirty(user_id):
                return False
            run_git(["add", "-A"], cwd=wd)
            run_git(["commit", "-q", "-m", message], cwd=wd, author=author)
            return True

    def pull(self, user_id: str) -> None:
        """Merge the mirror into the working copy; on conflict the mirror (web edits) wins."""
        wd = self.ensure_clone(user_id)
        with self.locks.get(user_id):
            self.commit_dirty(user_id)
            run_git(["fetch", "-q", self.REMOTE], cwd=wd)
            remote_ref = f"{self.REMOTE}/{BRANCH}"
            if run_git(["rev-parse", "--verify", "-q", remote_ref], cwd=wd, check=False).returncode != 0:
                return
            if run_git(["rev-parse", "--verify", "-q", "HEAD"], cwd=wd, check=False).returncode != 0:
                run_git(["reset", "-q", "--hard", remote_ref], cwd=wd)
                return
            merge = run_git(
                ["merge", "-q", "--no-edit", "-X", "theirs", "-m", "Đồng bộ chỉnh sửa từ web (ưu tiên người học)",
                 remote_ref],
                cwd=wd, author="system", check=False,
            )
            if merge.returncode == 0:
                return
            # -X theirs does not settle modify/delete or add/add-binary conflicts: resolve each to the mirror's side.
            unmerged = out(run_git(["diff", "--name-only", "--diff-filter=U", "-z"], cwd=wd)).split("\0")
            unmerged = [p for p in unmerged if p]
            if not unmerged:
                run_git(["merge", "--abort"], cwd=wd, check=False)
                raise GitError(["merge"], merge.returncode, merge.stderr.decode("utf-8", "replace"))
            for p in unmerged:
                in_mirror = run_git(["cat-file", "-e", f"{remote_ref}:{p}"], cwd=wd, check=False).returncode == 0
                if in_mirror:
                    run_git(["checkout", remote_ref, "--", p], cwd=wd)
                    run_git(["add", "--", p], cwd=wd)
                else:
                    run_git(["rm", "-q", "-f", "--", p], cwd=wd)
            run_git(["commit", "-q", "--no-edit"], cwd=wd, author="system")
            log.info("workspace %s: resolved %d conflict(s) in favour of web edits", user_id, len(unmerged))

    def push(self, user_id: str, attempts: int = 3) -> str | None:
        """Push the working copy to the mirror; if web edits landed meanwhile, merge them first."""
        wd = self.ensure_clone(user_id)
        with self.locks.get(user_id):
            self.commit_dirty(user_id)
            if run_git(["rev-parse", "--verify", "-q", "HEAD"], cwd=wd, check=False).returncode != 0:
                return None
            for _ in range(attempts):
                proc = run_git(["push", "-q", self.REMOTE, f"HEAD:{REF}"], cwd=wd, check=False)
                if proc.returncode == 0:
                    return self.mirror.head(user_id)
                self.pull(user_id)
            raise GitError(["push"], proc.returncode, proc.stderr.decode("utf-8", "replace"))
