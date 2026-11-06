"""Gateway settings, read from the environment (CONTRACTS.md section 8)."""

import os
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


class Settings(BaseModel):
    # Safe default: an unset MENTOR_ENV means prod (no magic links in responses, no dev parent verify, no local
    # sandbox backend, MENTOR_MASTER_KEY required). Development sets MENTOR_ENV=dev explicitly.
    env: Literal["dev", "test", "prod"] = "prod"
    data_dir: Path = Path("var")
    database_url: str | None = None  # default: sqlite:///$MENTOR_DATA_DIR/ops.db; Postgres URLs work too
    content_dir: Path = _repo_root() / "mentor-content"

    public_base_url: str = "http://localhost:8000"  # where the gateway is reachable (magic links, mobile upload)
    web_origin: str = "http://localhost:3000"  # web app: CORS origin, /auth/verify redirects, phone upload page
    extra_origins: str = ""  # comma-separated additional CORS / WebSocket origins (e.g. the Tauri pop-up)
    cookie_secure: bool = False
    session_days: int = 30
    magic_link_minutes: int = 15
    login_requests_per_hour: int = 5  # per email; each request allows 5 more login-code guesses
    # Comma-separated emails and/or "@domain" entries allowed to log in; empty = anyone (open signup).
    signup_allowlist: str = ""
    mobile_token_minutes: int = 15

    smtp_host: str | None = None  # outbound mail (magic links + login codes) when env != dev
    smtp_port: int = 1025
    smtp_username: str | None = None  # SMTP AUTH (Gmail: the full address); needs STARTTLS or SSL
    smtp_password: str | None = None  # Gmail: a 16-character app password, not the account password
    smtp_starttls: bool = False  # STARTTLS after connecting (Gmail: port 587)
    smtp_ssl: bool = False  # implicit TLS from the first byte (Gmail: port 465); excludes smtp_starttls
    mail_from: str = "mentor@mentor.local"  # "Name <addr>" works; Gmail rewrites it unless addr is the account

    inbound_email_domain: str = "inbox.mentor.local"
    inbound_smtp_port: int | None = None
    inbound_smtp_host: str = "127.0.0.1"  # 0.0.0.0 inside a container  # start an in-process inbound SMTP server (aiosmtpd) on this port
    internal_token: str | None = None  # protects POST /internal/email/inbound
    # POST /webhooks/email/inbound (Cloudflare Email Worker, HMAC-signed); unset = that endpoint answers 404
    email_webhook_secret: str | None = None
    inbound_email_max_bytes: int = 25 * 1024 * 1024  # raw message cap (webhook, SMTP, internal); Cloudflare: 25 MiB
    email_webhook_per_rcpt_per_hour: int = 30  # per learner address, POST /webhooks/email/inbound

    sandbox_backend: Literal["local", "docker"] = "local"
    sandbox_idle_seconds: int = 15 * 60
    sandbox_prewarm: bool = True  # start the sandbox when the learner opens the chat (WS connect, POST /sandbox/warm)
    sandbox_image: str = "mentor-sandbox:dev"
    # `container[:alias],...` attached to each sandbox's own internal network (`self` = the gateway's container),
    # e.g. "self:gateway,mentor-dev-model-router-1:model-router". Set = one network per sandbox (recommended).
    sandbox_network_attach: str | None = None
    sandbox_docker_network: str | None = None  # legacy: ONE internal network shared by all sandboxes + the router
    sandbox_docker_user: str | None = None  # `--user` for sandbox containers; default: the gateway's uid:gid, never 0
    sandbox_tmpfs_size: str = "256m"  # the sandbox's root fs is read-only; /tmp is a tmpfs of this size
    host_data_dir: Path | None = None  # data dir as seen by the docker daemon, if the gateway runs in a container
    model_router_url: str = "http://localhost:4000"
    model_router_key: str = ""
    model_mode: Literal["router", "scripted"] = "router"
    sandbox_gateway_url: str | None = None  # gateway as seen from a sandbox; default public_base_url
    s2_api_key: str | None = None  # optional Semantic Scholar key for /internal/papers/*
    paper_requests_per_minute: int = 20  # per learner, /internal/papers/*
    asta_mcp_url: str = "https://asta-tools.allen.ai/mcp/v1"  # Ai2 Asta (MCP); "" disables, see papers.py
    asta_api_key: str | None = None  # optional; higher Asta rate limits
    asta_timeout_seconds: float = 40.0  # per Asta tool call (anonymous calls often take ~30 s)
    google_oauth_client_id: str | None = None  # Google Calendar (NCS); unset = integration unavailable
    google_oauth_client_secret: str | None = None
    calendar_requests_per_minute: int = 30  # per learner, /internal/calendar/*
    tavily_api_key: str | None = None  # web_search backend (hosted); preferred over SearXNG when both are set
    searxng_url: str | None = None  # web_search backend (self-hosted SearXNG with the JSON format enabled)
    web_search_requests_per_minute: int = 10  # per learner, /internal/web/search
    web_fetch_enabled: bool = True  # /internal/web/fetch (web_fetch tool); independent of the search backend
    web_fetch_requests_per_minute: int = 10  # per learner, /internal/web/fetch
    web_fetch_pdf_max_mb: int = 30  # /internal/web/download cap in MB (clamped to 1..200); HTML stays at 2 MB

    zalo_bot_token: str | None = None
    zalo_webhook_secret: str = "dev-secret"
    zalo_bot_name: str = "Mentor Phụ huynh"
    zalo_bot_url: str = ""  # the bot's share link from bot.zaloplatforms.com; empty hides the QR in the web app

    # Web Push (VAPID). Push is off unless all three are set; generate the pair once (infra/README "Web Push").
    vapid_public_key: str | None = None  # urlsafe base64 (no padding) of the uncompressed P-256 point, 87 chars
    vapid_private_key: str | None = None  # urlsafe base64 (no padding) of the raw 32-byte private scalar
    vapid_subject: str | None = None  # "mailto:ops@example.com" or an https URL (push services contact it)

    background_tasks: bool = True  # scheduler loop, idle reaper, inbound SMTP
    scheduler_interval_seconds: float = 30.0

    backup_dir: Path | None = None  # encrypted snapshots; default $MENTOR_DATA_DIR/backups
    backup_enabled: bool | None = None  # daily scheduler job; default on except MENTOR_ENV=test
    backup_hour_utc: int = 19  # run once a day at/after this UTC hour (19 = 02:00 Asia/Ho_Chi_Minh)
    backup_keep_daily: int = 14
    backup_keep_weekly: int = 8

    @property
    def backups_dir(self) -> Path:
        return self.backup_dir or self.data_dir / "backups"

    @property
    def backups_scheduled(self) -> bool:
        return self.backup_enabled if self.backup_enabled is not None else self.env != "test"

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
        return [self.web_url, *extra]

    @property
    def sandbox_gateway_base_url(self) -> str:
        return (self.sandbox_gateway_url or self.public_base_url).rstrip("/")

    @property
    def google_redirect_uri(self) -> str:
        return f"{self.public_base_url.rstrip('/')}/api/integrations/google-calendar/callback"

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
            "public_base_url": "PUBLIC_BASE_URL",
            "web_origin": "WEB_ORIGIN",
            "extra_origins": "CORS_ORIGINS",
            "cookie_secure": "COOKIE_SECURE",
            "signup_allowlist": "SIGNUP_ALLOWLIST",
            "smtp_host": "SMTP_HOST",
            "smtp_port": "SMTP_PORT",
            "smtp_username": "SMTP_USERNAME",
            "smtp_password": "SMTP_PASSWORD",
            "smtp_starttls": "SMTP_STARTTLS",
            "smtp_ssl": "SMTP_SSL",
            "mail_from": "MAIL_FROM",
            "inbound_email_domain": "INBOUND_EMAIL_DOMAIN",
            "inbound_smtp_port": "INBOUND_SMTP_PORT",
            "inbound_smtp_host": "INBOUND_SMTP_HOST",
            "internal_token": "GATEWAY_INTERNAL_TOKEN",
            "email_webhook_secret": "EMAIL_WEBHOOK_SECRET",
            "inbound_email_max_bytes": "INBOUND_EMAIL_MAX_BYTES",
            "email_webhook_per_rcpt_per_hour": "EMAIL_WEBHOOK_PER_RCPT_PER_HOUR",
            "sandbox_backend": "SANDBOX_BACKEND",
            "sandbox_idle_seconds": "SANDBOX_IDLE_SECONDS",
            "sandbox_prewarm": "SANDBOX_PREWARM",
            "sandbox_image": "SANDBOX_IMAGE",
            "sandbox_network_attach": "SANDBOX_NETWORK_ATTACH",
            "sandbox_docker_network": "SANDBOX_DOCKER_NETWORK",
            "sandbox_tmpfs_size": "SANDBOX_TMPFS_SIZE",
            "sandbox_docker_user": "SANDBOX_DOCKER_USER",
            "host_data_dir": "MENTOR_HOST_DATA_DIR",
            "model_router_url": "MODEL_ROUTER_URL",
            "model_router_key": "MODEL_ROUTER_KEY",
            "model_mode": "MENTOR_MODEL_MODE",
            "sandbox_gateway_url": "SANDBOX_GATEWAY_URL",
            "s2_api_key": "S2_API_KEY",
            "paper_requests_per_minute": "PAPER_REQUESTS_PER_MINUTE",
            "asta_mcp_url": "ASTA_MCP_URL",
            "asta_api_key": "ASTA_API_KEY",
            "asta_timeout_seconds": "ASTA_TIMEOUT_SECONDS",
            "google_oauth_client_id": "GOOGLE_OAUTH_CLIENT_ID",
            "google_oauth_client_secret": "GOOGLE_OAUTH_CLIENT_SECRET",
            "calendar_requests_per_minute": "CALENDAR_REQUESTS_PER_MINUTE",
            "tavily_api_key": "TAVILY_API_KEY",
            "searxng_url": "SEARXNG_URL",
            "web_search_requests_per_minute": "WEB_SEARCH_REQUESTS_PER_MINUTE",
            "web_fetch_enabled": "WEB_FETCH_ENABLED",
            "web_fetch_requests_per_minute": "WEB_FETCH_REQUESTS_PER_MINUTE",
            "web_fetch_pdf_max_mb": "WEB_FETCH_PDF_MAX_MB",
            "zalo_bot_token": "ZALO_BOT_TOKEN",
            "zalo_webhook_secret": "ZALO_WEBHOOK_SECRET",
            "zalo_bot_name": "ZALO_BOT_NAME",
            "zalo_bot_url": "ZALO_BOT_URL",
            "vapid_public_key": "VAPID_PUBLIC_KEY",
            "vapid_private_key": "VAPID_PRIVATE_KEY",
            "vapid_subject": "VAPID_SUBJECT",
            "background_tasks": "GATEWAY_BACKGROUND_TASKS",
            "scheduler_interval_seconds": "SCHEDULER_INTERVAL_SECONDS",
            "backup_dir": "MENTOR_BACKUP_DIR",
            "backup_enabled": "BACKUP_ENABLED",
            "backup_hour_utc": "BACKUP_HOUR_UTC",
            "backup_keep_daily": "BACKUP_KEEP_DAILY",
            "backup_keep_weekly": "BACKUP_KEEP_WEEKLY",
        }
        values = {field: e[var] for field, var in mapping.items() if e.get(var) not in (None, "")}
        if "web_origin" not in values and e.get("WEB_BASE_URL"):  # older name
            values["web_origin"] = e["WEB_BASE_URL"]
        return cls.model_validate(values)
