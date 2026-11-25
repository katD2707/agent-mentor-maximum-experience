"""Entry point of the self-contained desktop package: the gateway as a sidecar of the Mentor app.

The Tauri shell starts this (frozen with PyInstaller as `mentor-gateway.exe`) with:

    MENTOR_PORT        port to listen on (127.0.0.1 only); 0 or unset = pick a free one and print it
    MENTOR_DATA_DIR    where the database, learner workspaces and the content folder live (the app's own data dir)
    MENTOR_PARENT_PID  optional: exit when this process (the app) is gone, so a crashed app never leaves a gateway behind

and gets standalone defaults: MENTOR_ENV=standalone (no dev accounts, local sign-up on, file mirror instead of git,
no scheduled backups), the content folder at `<data dir>/content`, and no model router (AI features need a key the
user enters; everything else works without one). Run from source with `python -m mentor_gateway.standalone`.

Course content (`seed_content`): the folder is filled from the small sample set bundled with the package so the app is
never empty. The remote course store (MENTOR_REMOTE_CATALOG_URL, built elsewhere) fills `<content>/courses` itself;
when it is configured only the base files (AGENTS.md, skills, curricula, question bank, papers, templates) are seeded.
"""

import contextlib
import logging
import logging.handlers
import os
import shutil
import socket
import sys
import threading
import time
from pathlib import Path

log = logging.getLogger("mentor_gateway.standalone")

BASE_ITEMS = ("AGENTS.md", "exam-profiles.json", "skills", "curricula", "workspace-templates", "bank", "papers")
MARKER = ".sample-version"


def bundled_sample_dir() -> Path | None:
    """The sample content next to this program: PyInstaller's data folder when frozen, else MENTOR_SAMPLE_CONTENT_DIR."""
    env = os.environ.get("MENTOR_SAMPLE_CONTENT_DIR")
    if env:
        return Path(env)
    root = getattr(sys, "_MEIPASS", None)
    if root and (Path(root) / "sample-content").is_dir():
        return Path(root) / "sample-content"
    return None


def has_courses(content_dir: Path) -> bool:
    courses = content_dir / "courses"
    return courses.is_dir() and any((d / "course.json").is_file() for d in courses.iterdir() if d.is_dir())


def seed_content(content_dir: Path, sample: Path | None, *, remote_catalog: bool) -> list[str]:
    """Fill `content_dir` from the bundled sample. Returns what was copied (for the log and the tests).

    - base files: copied when missing, and refreshed whenever the bundled sample has a different version stamp
      (a new app version ships newer skills and question banks); learner data never lives here;
    - courses: the sample courses and their catalog are copied only while there are no courses at all and no
      remote catalog is configured (a course list the user already has is never touched).
    """
    done: list[str] = []
    content_dir.mkdir(parents=True, exist_ok=True)
    if sample is None or not sample.is_dir():
        log.warning("no bundled sample content: the content folder stays as it is (%s)", content_dir)
        return done
    stamp = (sample / MARKER).read_text(encoding="utf-8").strip() if (sample / MARKER).is_file() else ""
    have = (content_dir / MARKER).read_text(encoding="utf-8").strip() if (content_dir / MARKER).is_file() else None
    refresh = have != stamp
    for name in BASE_ITEMS:
        src, dst = sample / name, content_dir / name
        if not src.exists() or (dst.exists() and not refresh):
            continue
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
        done.append(name)
    if not remote_catalog and not has_courses(content_dir) and (sample / "courses").is_dir():
        shutil.copytree(sample / "courses", content_dir / "courses", dirs_exist_ok=True)
        done.append("courses")
    (content_dir / MARKER).write_text(stamp, encoding="utf-8")
    return done


DEFAULT_HUB_URL = "https://hub.mentor-hoc.workers.dev"  # central accounts + teacher approval (CONTRACTS-HUB.md)
DEFAULT_REMOTE_CATALOG = "1AreHj5AxvmCmvHeyDHjJpIUXNWxCWHg1"  # Drive file id of catalog.json (public, anyone with the link)


def apply_defaults(environ: dict[str, str], port: int) -> Path:
    """Standalone defaults, set only when not already given. Returns the data dir."""
    environ.setdefault("MENTOR_ENV", "standalone")
    data_dir = Path(environ.get("MENTOR_DATA_DIR") or (Path.home() / "MentorData"))
    environ["MENTOR_DATA_DIR"] = str(data_dir)
    environ.setdefault("MENTOR_CONTENT_DIR", str(data_dir / "content"))
    # the public course catalog on the owner's Google Drive (content/drive.py push-all); an empty value turns it off
    environ.setdefault("MENTOR_REMOTE_CATALOG_URL", DEFAULT_REMOTE_CATALOG)
    environ.setdefault("MENTOR_HUB_URL", DEFAULT_HUB_URL)  # an empty value turns the hub off (local accounts only)
    environ.setdefault("PUBLIC_BASE_URL", f"http://127.0.0.1:{port}")
    # one local machine, nothing to route: AI goes through the user's own key, not a model router
    for var in ("MODEL_ROUTER_URL", "MODEL_ROUTER_KEY", "MODEL_ROUTER_MASTER_KEY"):
        environ.pop(var, None)
    return data_dir


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _setup_logging(data_dir: Path) -> None:
    logs = data_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        logging.handlers.RotatingFileHandler(logs / "gateway.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    ]
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler(sys.stderr))
    logging.basicConfig(level=logging.INFO, handlers=handlers, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _process_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes

        SYNCHRONIZE, WAIT_TIMEOUT = 0x00100000, 0x102
        h = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if not h:
            return False
        try:
            return ctypes.windll.kernel32.WaitForSingleObject(h, 0) == WAIT_TIMEOUT
        finally:
            ctypes.windll.kernel32.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _exit_with_parent(pid: int) -> None:
    def watch() -> None:
        while _process_alive(pid):
            time.sleep(2)
        log.info("the Mentor app (pid %s) is gone: stopping the gateway", pid)
        os._exit(0)

    threading.Thread(target=watch, daemon=True, name="parent-watch").start()


def main() -> None:
    port = int(os.environ.get("MENTOR_PORT") or 0) or free_port()
    data_dir = apply_defaults(os.environ, port)
    data_dir.mkdir(parents=True, exist_ok=True)
    _setup_logging(data_dir)

    import uvicorn

    from mentor_gateway.app import create_app
    from mentor_gateway.settings import Settings

    settings = Settings.from_env()
    seeded = seed_content(settings.content_dir, bundled_sample_dir(), remote_catalog=bool(settings.remote_catalog_url))
    log.info("standalone gateway: data %s, content %s, seeded %s", settings.data_dir, settings.content_dir, seeded or "nothing")
    if pid := os.environ.get("MENTOR_PARENT_PID"):
        with contextlib.suppress(ValueError):
            _exit_with_parent(int(pid))
    uvicorn.run(create_app(settings), host="127.0.0.1", port=port, log_level="info", log_config=None)


if __name__ == "__main__":
    main()
