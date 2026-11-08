"""Gateway settings, read from the environment (CONTRACTS.md section 8)."""

import os
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


def _repo_root() -> Path:
    # services/gateway/src/mentor_gateway/settings.py -> repo root is 4 levels up from the package dir
    return Path(__file__).resolve().parents[4]


# Always allowed (CONTRACTS section 8): the Vite dev server and the Tauri webviews (desktop/mobile).
BUILTIN_ORIGINS = (
    "http://localhost:5173",
    "tauri://localhost",
    "http://tauri.localhost",
    "https://tauri.localhost",
)


class Settings(BaseModel):
    # Safe default: an unset MENTOR_ENV means prod (no dev accounts, MENTOR_MASTER_KEY required).
    # Development sets MENTOR_ENV=dev explicitly.
    env: Literal["dev", "test", "prod"] = "prod"
    data_dir: Path = Path("var")
    database_url: str | None = None  # default: sqlite:///$MENTOR_DATA_DIR/ops.db; Postgres URLs work too
    content_dir: Path = _repo_root() / "mentor-content"

    model_router_url: str | None = None  # LiteLLM router (course search embeddings); unset = lexical search only
    model_router_key: str | None = None  # MODEL_ROUTER_KEY, or MODEL_ROUTER_MASTER_KEY in dev
    media_token_minutes: int = 240  # lifetime of the `?t=` token for <video>/<img>/<audio> on content routes

    public_base_url: str = "http://localhost:8000"  # where the gateway is reachable
    web_origin: str = "http://localhost:5173"  # web app origin (added to CORS)
    extra_origins: str = ""  # comma-separated additional CORS origins
    session_days: int = 365  # login tokens are long-lived; the app only logs out from the settings popover
    mobile_token_minutes: int = 15  # phone-upload link lifetime
    seed_dev_accounts: bool | None = None  # hocsinh/giaovien (123456); default: on when MENTOR_ENV=dev

    # Web Push (VAPID). Push is off unless all three are set; generate the pair once (infra/README "Web Push").
    vapid_public_key: str | None = None  # urlsafe base64 (no padding) of the uncompressed P-256 point, 87 chars
    vapid_private_key: str | None = None  # urlsafe base64 (no padding) of the raw 32-byte private scalar
    vapid_subject: str | None = None  # "mailto:ops@example.com" or an https URL (push services contact it)

    # Teacher authoring (CONTRACTS "Teacher authoring"): the course builder runs as subprocesses, never in this process.
    builder_workers: int = 1  # BUILDER_WORKERS: stages running at once (one per course)
    builder_python: str | None = None  # BUILDER_PYTHON: interpreter that has mentor_course_builder (default: this one)
    builder_job_timeout_s: int = 3600  # BUILDER_JOB_TIMEOUT_S
    builder_media_kinds: str = "tts,video,diagram,illustration,picture,cover"  # BUILDER_MEDIA_KINDS: media stage kinds
    builder_deeptutor: bool = False  # BUILDER_DEEPTUTOR=1: DeepTutor knowledge base for quizzes (needs uvx)
    builder_chat_wait_s: float = 20.0  # BUILDER_CHAT_WAIT_S: POST /chat waits this long for the agent's reply

    released_app_version: str = "0.1.0"  # RELEASED_APP_VERSION: newest app students can have; the review screen warns above it

    background_tasks: bool = True  # scheduler loop
    scheduler_interval_seconds: float = 30.0

    backup_dir: Path | None = None  # encrypted snapshots; default $MENTOR_DATA_DIR/backups
    backup_enabled: bool | None = None  # daily scheduler job; default on except MENTOR_ENV=test
    backup_hour_utc: int = 19  # run once a day at/after this UTC hour (19 = 02:00 Asia/Ho_Chi_Minh)
    backup_keep_daily: int = 14
    backup_keep_weekly: int = 8

    @property
    def builder_dir(self) -> Path:
        return self.data_dir / "builder"

    @property
    def courses_dir(self) -> Path:
        return self.content_dir / "courses"

    @property
    def backups_dir(self) -> Path:
        return self.backup_dir or self.data_dir / "backups"

    @property
    def backups_scheduled(self) -> bool:
        return self.backup_enabled if self.backup_enabled is not None else self.env != "test"

    @property
    def seed_dev(self) -> bool:
        return self.seed_dev_accounts if self.seed_dev_accounts is not None else self.env == "dev"

    @property
    def push_enabled(self) -> bool:
        return bool(self.vapid_public_key and self.vapid_private_key and self.vapid_subject)

    @property
    def ops_db_url(self) -> str:
        return self.database_url or f"sqlite:///{(self.data_dir / 'ops.db').as_posix()}"

    @property
    def web_url(self) -> str:
        return self.web_origin.rstrip("/")

    @property
    def allowed_origins(self) -> list[str]:
        extra = [o.strip().rstrip("/") for o in self.extra_origins.split(",") if o.strip()]
        return list(dict.fromkeys([*BUILTIN_ORIGINS, self.web_url, *extra]))

    @property
    def mirrors_dir(self) -> Path:
        return self.data_dir / "mirrors"

    @property
    def workspaces_dir(self) -> Path:
        return self.data_dir / "workspaces"

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "Settings":
        e = os.environ if environ is None else environ
        mapping = {
            "env": "MENTOR_ENV",
            "data_dir": "MENTOR_DATA_DIR",
            "database_url": "MENTOR_DATABASE_URL",
            "content_dir": "MENTOR_CONTENT_DIR",
            "model_router_url": "MODEL_ROUTER_URL",
            "model_router_key": "MODEL_ROUTER_KEY",
            "media_token_minutes": "MEDIA_TOKEN_MINUTES",
            "public_base_url": "PUBLIC_BASE_URL",
            "web_origin": "WEB_ORIGIN",
            "extra_origins": "CORS_ORIGINS",
            "seed_dev_accounts": "SEED_DEV_ACCOUNTS",
            "vapid_public_key": "VAPID_PUBLIC_KEY",
            "vapid_private_key": "VAPID_PRIVATE_KEY",
            "vapid_subject": "VAPID_SUBJECT",
            "builder_workers": "BUILDER_WORKERS",
            "builder_python": "BUILDER_PYTHON",
            "builder_job_timeout_s": "BUILDER_JOB_TIMEOUT_S",
            "builder_media_kinds": "BUILDER_MEDIA_KINDS",
            "builder_deeptutor": "BUILDER_DEEPTUTOR",
            "builder_chat_wait_s": "BUILDER_CHAT_WAIT_S",
            "released_app_version": "RELEASED_APP_VERSION",
            "background_tasks": "GATEWAY_BACKGROUND_TASKS",
            "scheduler_interval_seconds": "SCHEDULER_INTERVAL_SECONDS",
            "backup_dir": "MENTOR_BACKUP_DIR",
            "backup_enabled": "BACKUP_ENABLED",
            "backup_hour_utc": "BACKUP_HOUR_UTC",
            "backup_keep_daily": "BACKUP_KEEP_DAILY",
            "backup_keep_weekly": "BACKUP_KEEP_WEEKLY",
        }
        values = {field: e[var] for field, var in mapping.items() if e.get(var) not in (None, "")}
        if "model_router_key" not in values and e.get("MODEL_ROUTER_MASTER_KEY"):
            values["model_router_key"] = e["MODEL_ROUTER_MASTER_KEY"]
        if "web_origin" not in values and e.get("WEB_BASE_URL"):  # older name
            values["web_origin"] = e["WEB_BASE_URL"]
        if values.get("model_router_url"):  # "localhost" costs 2-3 s per new connection on Windows (IPv6 first)
            values["model_router_url"] = re.sub(r"//localhost(?=[:/]|$)", "//127.0.0.1", values["model_router_url"])
        return cls.model_validate(values)
