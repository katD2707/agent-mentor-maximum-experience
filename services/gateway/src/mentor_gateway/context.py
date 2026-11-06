"""Composition root: builds every gateway component from Settings. Stored on `app.state.gw`."""

from dataclasses import dataclass, field
from typing import Any

from mentor_gateway.backup import BackupService
from mentor_gateway.crypto import SecretBox, load_master_key
from mentor_gateway.db import Database
from mentor_gateway.email_ingest import build_inbound_handler
from mentor_gateway.engagement import EngagementService
from mentor_gateway.gcal import GoogleCalendar  # also registers its tables before create_all
from mentor_gateway.gitrepo import UserLocks
from mentor_gateway.jobs import JobRunner, JobStore
from mentor_gateway.mirror import Mirror, WorkspaceSync
from mentor_gateway.notifications import NotificationHub
from mentor_gateway.nudges import NudgeService
from mentor_gateway.outbox import OutboxDispatcher
from mentor_gateway.papers import PaperService, RateLimiter
from mentor_gateway.parent import ParentChannel, SqlParentLinkStore, build_parent_channel
from mentor_gateway.practice import Bank as PracticeBank  # also registers the practice tables before create_all
from mentor_gateway.practice import PracticeService
from mentor_gateway.push import PushService
from mentor_gateway.sandbox import Orchestrator, SandboxBackend, make_backend
from mentor_gateway.sandbox.tokens import SandboxTokens
from mentor_gateway.scheduler import Scheduler
from mentor_gateway.settings import Clock, Settings, utc_now
from mentor_gateway.users import UserService
from mentor_gateway.webfetch import WebFetchService
from mentor_gateway.websearch import WebSearchService


@dataclass
class Gateway:
    settings: Settings
    clock: Clock
    db: Database
    mirror: Mirror
    sync: WorkspaceSync
    parent: ParentChannel
    users: UserService
    hub: NotificationHub
    backend: SandboxBackend
    orchestrator: Orchestrator
    dispatcher: OutboxDispatcher
    jobs: JobStore
    runner: JobRunner
    scheduler: Scheduler
    inbound: Any | None  # mentor_email_ingest.InboundHandler
    tokens: SandboxTokens = field(default_factory=SandboxTokens)  # sandbox -> gateway credentials
    papers: PaperService = field(default_factory=PaperService)
    paper_limiter: RateLimiter = field(default_factory=lambda: RateLimiter(20))
    box: SecretBox | None = None  # master-key AEAD for secrets at rest; always set by build_gateway
    gcal: GoogleCalendar | None = None  # Google Calendar (NCS); always set by build_gateway
    backups: BackupService | None = None  # encrypted snapshots + crypto-shredding; always set by build_gateway
    web: WebSearchService = field(default_factory=WebSearchService)  # web_search proxy (Tavily / SearXNG)
    web_limiter: RateLimiter = field(default_factory=lambda: RateLimiter(10))
    fetch: WebFetchService = field(default_factory=WebFetchService)  # web_fetch proxy (SSRF-checked page reader)
    fetch_limiter: RateLimiter = field(default_factory=lambda: RateLimiter(10))
    email_guard: Any | None = None  # api.email_webhook.EmailWebhookGuard (rate limit + replays), made on first use
    push: PushService | None = None  # Web Push (VAPID); always set by build_gateway, `enabled` only when configured
    nudges: NudgeService | None = None  # notification actions + proactive routines; always set by build_gateway
    practice: PracticeService | None = None  # /api/practice engine; always set by build_gateway
    engagement: EngagementService | None = None  # GET /api/engagement; always set by build_gateway


def build_gateway(
    settings: Settings,
    *,
    clock: Clock = utc_now,
    backend: SandboxBackend | None = None,
    parent: ParentChannel | None = None,
) -> Gateway:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    box = SecretBox(load_master_key(settings.env, settings.data_dir))
    db = Database(settings.ops_db_url)
    db.create_all()
    locks = UserLocks()
    mirror = Mirror(settings.mirrors_dir, locks)
    sync = WorkspaceSync(settings.workspaces_dir, mirror, locks)
    store = SqlParentLinkStore(db, clock, box)
    parent = parent or build_parent_channel(settings, store, clock)
    users = UserService(db, mirror, parent, settings, clock)

    def routines_for(user_id: str):
        user = users.get(user_id)
        if user is None:
            from mentor_schemas import RoutinesFile

            return RoutinesFile()
        return users.routines(user)

    push = PushService(db, box, settings, clock)
    hub = NotificationHub(db, clock, routines_for, push=push)
    tokens = SandboxTokens()
    backend = backend or make_backend(settings, tokens)
    tokens = getattr(backend, "tokens", tokens)  # a backend passed in (tests) may bring its own registry
    orchestrator = Orchestrator(backend, sync, clock, settings.sandbox_idle_seconds, on_status=hub.sandbox_status,
                                prewarm=settings.sandbox_prewarm)
    dispatcher = OutboxDispatcher(db, mirror, hub, parent, clock, routines_for)
    jobs = JobStore(db, clock)
    runner = JobRunner(jobs, users, orchestrator, dispatcher, sync.path, clock)
    scheduler = Scheduler(db, users, runner, hub, orchestrator, clock, settings.scheduler_interval_seconds)
    inbound = build_inbound_handler(users, mirror, jobs, settings.inbound_email_domain, clock,
                                    max_bytes=settings.inbound_email_max_bytes)
    gw = Gateway(settings, clock, db, mirror, sync, parent, users, hub, backend, orchestrator, dispatcher, jobs,
                 runner, scheduler, inbound, tokens=tokens, papers=PaperService.from_settings(settings),
                 paper_limiter=RateLimiter(settings.paper_requests_per_minute), box=box)
    gw.gcal = GoogleCalendar(db, box, settings, clock)
    gw.web = WebSearchService.from_settings(settings)
    gw.web_limiter = RateLimiter(settings.web_search_requests_per_minute)
    gw.fetch = WebFetchService.from_settings(settings)
    gw.fetch_limiter = RateLimiter(settings.web_fetch_requests_per_minute)
    gw.backups = BackupService(settings, db, box, mirror, clock)
    scheduler.backups = gw.backups if settings.backups_scheduled else None
    gw.push = push
    gw.nudges = NudgeService(db, hub, jobs, users, mirror, clock, store.record_audit, runner.run_due)
    runner.nudges = gw.nudges
    gw.engagement = EngagementService(db, mirror, clock)
    gw.practice = PracticeService(db, mirror, PracticeBank(settings.content_dir), clock)
    scheduler.practice_sweep = gw.practice.sweep
    return gw
