"""Composition root: builds every gateway component from Settings. Stored on `app.state.gw`."""

from dataclasses import dataclass

from mentor_gateway import age
from mentor_gateway.audit import AuditLog
from mentor_gateway.backup import BackupService
from mentor_gateway.content import tables as _content_tables  # noqa: F401  (registers enrollments before create_all)
from mentor_gateway.crypto import SecretBox, load_master_key
from mentor_gateway.planner import tables as _planner_tables  # noqa: F401  (registers study_goals before create_all)
from mentor_gateway.research import tables as _research_tables  # noqa: F401  (registers the Nghiên cứu tables before create_all)
from mentor_gateway.db import Database
from mentor_gateway.engagement import EngagementService
from mentor_gateway.gitrepo import UserLocks
from mentor_gateway.jobs import JobExecutor, JobRunner, JobStore
from mentor_gateway.mirror import Mirror, WorkspaceSync
from mentor_gateway.notifications import NotificationHub
from mentor_gateway.nudges import NudgeService
from mentor_gateway.outbox import OutboxDispatcher
from mentor_gateway.planner import PlannerService
from mentor_gateway.planner.llm import RouterPlannerLLM
from mentor_gateway.practice import Bank as PracticeBank  # also registers the practice tables before create_all
from mentor_gateway.practice import PracticeService
from mentor_gateway.push import PushService
from mentor_gateway.scheduler import Scheduler
from mentor_gateway.settings import Clock, Settings, utc_now
from mentor_gateway.users import UserService


@dataclass
class Gateway:
    settings: Settings
    clock: Clock
    db: Database
    box: SecretBox  # master-key AEAD for secrets at rest
    mirror: Mirror
    sync: WorkspaceSync
    users: UserService
    hub: NotificationHub
    dispatcher: OutboxDispatcher
    jobs: JobStore
    runner: JobRunner
    scheduler: Scheduler
    backups: BackupService  # encrypted snapshots + crypto-shredding
    push: PushService  # Web Push (VAPID); `enabled` only when configured
    nudges: NudgeService  # notification actions + proactive routines
    practice: PracticeService  # /api/practice engine
    engagement: EngagementService  # GET /api/engagement
    audit: AuditLog
    planner: PlannerService | None = None  # behaviour events, study profile, planner agent, goals, reminders


def build_gateway(settings: Settings, *, clock: Clock = utc_now, executor: JobExecutor | None = None) -> Gateway:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    box = SecretBox(load_master_key(settings.env, settings.data_dir))
    db = Database(settings.ops_db_url)
    db.create_all()
    locks = UserLocks()
    mirror = Mirror(settings.mirrors_dir, locks)
    sync = WorkspaceSync(settings.workspaces_dir, mirror, locks)
    users = UserService(db, mirror, settings, clock)
    age.set_today_provider(clock)
    if settings.seed_dev:
        users.seed_dev_accounts()

    def routines_for(user_id: str):
        user = users.get(user_id)
        if user is None:
            from mentor_schemas import RoutinesFile

            return RoutinesFile()
        return users.routines(user)

    push = PushService(db, box, settings, clock)
    hub = NotificationHub(db, clock, routines_for, push=push, quiet_active=users.quiet_active)
    dispatcher = OutboxDispatcher(db, hub, clock, routines_for)
    jobs = JobStore(db, clock)
    runner = JobRunner(jobs, users, dispatcher, sync.path, clock, executor=executor)
    scheduler = Scheduler(db, users, runner, hub, clock, settings.scheduler_interval_seconds)
    backups = BackupService(settings, db, box, mirror, clock)
    scheduler.backups = backups if settings.backups_scheduled else None
    audit = AuditLog(db, clock)
    nudges = NudgeService(db, hub, jobs, users, mirror, clock, audit.record, runner.run_due)
    runner.nudges = nudges
    practice = PracticeService(db, mirror, PracticeBank(settings.content_dir), clock)
    scheduler.practice_sweep = practice.sweep
    llm = RouterPlannerLLM(settings.model_router_url, settings.model_router_key) if settings.model_router_url else None
    planner = PlannerService(db, users, hub, push, clock, practice, llm)
    scheduler.planner = planner.tick
    return Gateway(settings, clock, db, box, mirror, sync, users, hub, dispatcher, jobs, runner, scheduler, backups,
                   push, nudges, practice, EngagementService(db, mirror, clock), audit, planner)
