"""Thin wrapper around the git CLI used by the mirror and the workspace sync.

Git runs isolated from the operator's global/system config so hooks, templates,
signing or autocrlf settings on the host never change what lands in a workspace.
"""

import os
import subprocess
import threading
import time
from collections import defaultdict
from pathlib import Path

AUTHORS = {
    "mentor": ("mentor", "mentor@local"),
    "user": ("user", "user@local"),
    "system": ("system", "system@local"),
}

# Passed as GIT_CONFIG_* env vars (not `-c`) so child processes such as receive-pack on push inherit them.
_BASE_CONFIG = {
    "core.autocrlf": "false",
    "core.safecrlf": "false",
    "core.longpaths": "true",  # Windows: data dirs can be deep
    "core.quotepath": "false",
    "commit.gpgsign": "false",
    "safe.directory": "*",
    "init.defaultBranch": "main",
}


# Windows only: another process (IDE git integration, antivirus) can hold a file in a freshly created repo for a
# moment, so git fails to rename config.lock / index.lock into place. Retrying a few times clears it.
_LOCK_RETRIES = 5 if os.name == "nt" else 0


def _transient_lock_error(stderr: bytes) -> bool:
    s = stderr.decode("utf-8", "replace")
    return "Permission denied" in s and (".lock" in s or "could not write config file" in s)


class GitError(RuntimeError):
    def __init__(self, args: list[str], code: int, stderr: str) -> None:
        super().__init__(f"git {' '.join(args)} failed ({code}): {stderr.strip()}")
        self.code = code
        self.stderr = stderr


def git_env(author: str | None = None, extra: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
            "GIT_CONFIG_COUNT": str(len(_BASE_CONFIG)),
        }
    )
    for i, (key, value) in enumerate(_BASE_CONFIG.items()):
        env[f"GIT_CONFIG_KEY_{i}"] = key
        env[f"GIT_CONFIG_VALUE_{i}"] = value
    name, email = AUTHORS[author or "system"]
    env.update(
        {
            "GIT_AUTHOR_NAME": name,
            "GIT_AUTHOR_EMAIL": email,
            "GIT_COMMITTER_NAME": name,
            "GIT_COMMITTER_EMAIL": email,
        }
    )
    if extra:
        env.update(extra)
    return env


def run_git(
    args: list[str],
    *,
    cwd: Path | None = None,
    git_dir: Path | None = None,
    author: str | None = None,
    input: bytes | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    cmd = ["git"]
    if git_dir is not None:
        cmd += ["--git-dir", str(git_dir)]
    cmd += args
    for attempt in range(_LOCK_RETRIES + 1):
        proc = subprocess.run(cmd, check=False, cwd=cwd, input=input, capture_output=True, env=git_env(author, env))
        if proc.returncode == 0 or not _transient_lock_error(proc.stderr) or attempt == _LOCK_RETRIES:
            break
        time.sleep(0.1 * (attempt + 1))
    if check and proc.returncode != 0:
        raise GitError(args, proc.returncode, proc.stderr.decode("utf-8", "replace"))
    return proc


def out(proc: subprocess.CompletedProcess[bytes]) -> str:
    return proc.stdout.decode("utf-8", "replace").strip()


class UserLocks:
    """One re-entrant lock per user, shared by the mirror and the workspace sync."""

    def __init__(self) -> None:
        self._locks: dict[str, threading.RLock] = defaultdict(threading.RLock)
        self._guard = threading.Lock()

    def get(self, user_id: str) -> threading.RLock:
        with self._guard:
            return self._locks[user_id]
