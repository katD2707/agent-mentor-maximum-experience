"""Accounts (seeded, no sign-up), the user view and the per-user routines view."""

import logging
from datetime import datetime
from typing import Literal

import yaml
from mentor_schemas import Profile, RoutinesFile, WorkspacePaths
from pydantic import BaseModel
from sqlalchemy import func, select

from mentor_gateway.age import school_year_start
from mentor_gateway.db import Database, User
from mentor_gateway.mirror import Mirror
from mentor_gateway.provisioning import default_routines
from mentor_gateway.security import hash_password, new_id
from mentor_gateway.settings import Clock, Settings

log = logging.getLogger(__name__)

Role = Literal["student", "teacher"]
AgeBand = Literal["g1_5", "g6_9", "g10_12", "uni"]
Language = Literal["vi", "en"]
Theme = Literal["light", "dark", "system"]


class UserView(BaseModel):
    """`user` in the API (CONTRACTS section 4)."""

    id: str
    role: Role
    username: str
    display_name: str
    age_band: AgeBand | None  # derived from birth_year, recomputed per request
    birth_year: int | None
    language: Language | None
    theme: Theme
    quiet_until: datetime | None
    avatar: Literal["nam", "nu"] | None = None  # Làng gà: chosen at first run
    # Hub accounts only (CONTRACTS-HUB section 3). Left unset (so absent from the JSON) while the hub is off; with the hub on
    # `teacher_status` is null for students, else chua_nop|cho_duyet|tu_choi|da_duyet|xac_minh for teachers.
    email: str | None = None
    teacher_status: str | None = None


# Accounts created on startup in dev (infra/README, docs/demo-accounts.md). Passwords are for local use only.
DEV_ACCOUNTS = (
    {"username": "hocsinh", "password": "123456", "role": "student", "display_name": "Lan", "birth_year": 2010},
    {"username": "giaovien", "password": "123456", "role": "teacher", "display_name": "Thầy Minh"},
)


class UserService:
    def __init__(self, db: Database, mirror: Mirror, settings: Settings, clock: Clock) -> None:
        self.db = db
        self.mirror = mirror
        self.settings = settings
        self.clock = clock

    def get(self, user_id: str) -> User | None:
        with self.db.session() as s:
            return s.get(User, user_id)

    def by_username(self, username: str) -> User | None:
        with self.db.session() as s:
            return s.scalars(select(User).where(User.username == username.strip().lower())).first()

    def create(self, *, username: str, password: str, role: Role, display_name: str,
               birth_year: int | None = None, language: str | None = None) -> User:
        with self.db.session() as s:
            user = User(id=new_id("u"), role=role, username=username.strip().lower(),
                        password_hash=hash_password(password), display_name=display_name, birth_year=birth_year,
                        language=language, theme="system", created_at=self.clock())
            s.add(user)
            return user

    def seed_dev_accounts(self) -> list[str]:
        """Create the missing dev accounts; existing ones are left alone. Returns the usernames created."""
        created = []
        for acc in DEV_ACCOUNTS:
            if self.by_username(acc["username"]) is None:
                self.create(**acc)
                created.append(acc["username"])
        return created

    def all_provisioned(self) -> list[User]:
        with self.db.session() as s:
            return list(s.scalars(select(User).where(User.provisioned_at.is_not(None))))

    def by_login(self, login: str) -> User | None:
        """A user by username, or by the email on record (hub accounts)."""
        login = login.strip().lower()
        user = self.by_username(login)
        if user is None and "@" in login:
            with self.db.session() as s:
                user = s.scalars(select(User).where(func.lower(User.email) == login)).first()
        return user

    def birth_year_for_grade(self, grade: str | None) -> int | None:
        """Hub `grade` ("1".."12" or "dh") -> the birth year that `age.grade_for` maps back to that grade; `dh` = 20 years old."""
        if not grade:
            return None
        year = school_year_start(self.clock().date())
        if grade == "dh":
            return year - 20
        try:
            n = int(grade)
        except ValueError:
            return None
        return year - 5 - n if 1 <= n <= 12 else None

    def mirror_hub(self, account: dict, token: str | None, password: str | None) -> User:
        """Create or update the local row of a hub account (found by hub id, else by username: that adopts a legacy local
        account). `password` refreshes the offline login hash; the hub token is kept when none is given."""
        username = str(account["username"]).strip().lower()
        fields: dict = {
            "hub_id": account["id"], "role": account.get("role") or "student", "email": account.get("email"),
            "teacher_status": account.get("teacher_status"), "reject_reason": account.get("reject_reason"),
        }
        if token:
            fields["hub_token"] = token
        if account.get("display_name"):
            fields["display_name"] = account["display_name"]
        with self.db.session() as s:
            user = s.scalars(select(User).where(User.hub_id == account["id"])).first() or s.scalars(
                select(User).where(User.username == username)).first()
            if user is None:
                user = User(id=new_id("u"), username=username, password_hash=hash_password(password or new_id("x")),
                            display_name=account.get("display_name") or username, theme="system", language="vi",
                            created_at=self.clock(), role=fields["role"])
                s.add(user)
            elif password:
                user.password_hash = hash_password(password)
            for k, v in fields.items():
                setattr(user, k, v)
            user.username = username
            if user.birth_year is None:
                user.birth_year = self.birth_year_for_grade(account.get("grade"))
            s.flush()
            s.expunge(user)
            return user

    def update(self, user_id: str, **fields: object) -> User:
        with self.db.session() as s:
            user = s.get(User, user_id)
            if user is None:
                raise KeyError(user_id)
            for k, v in fields.items():
                setattr(user, k, v)
            return user

    @staticmethod
    def profile(user: User) -> Profile:
        return Profile.TEACHER if user.role == "teacher" else Profile.STUDENT

    @staticmethod
    def is_active(user: User) -> bool:
        """Students with a workspace take part in jobs, routines and notifications."""
        return user.role == "student" and user.provisioned_at is not None

    def view(self, user: User) -> UserView:
        extra = {"email": user.email, "teacher_status": user.teacher_status} if self.settings.hub_on else {}
        return UserView(
            **extra,
            id=user.id, role=user.role, username=user.username, display_name=user.display_name,
            age_band=user.age_band, birth_year=user.birth_year,
            language=user.language if user.language in ("vi", "en") else None,
            theme=user.theme if user.theme in ("light", "dark", "system") else "system",
            quiet_until=user.quiet_until, avatar=user.avatar if user.avatar in ("nam", "nu") else None,
        )

    def quiet_active(self, user_id: str, now: datetime | None = None) -> bool:
        """True while the learner asked for silence (`PUT /api/me/quiet`): nothing is delivered, jobs still run."""
        now = now or self.clock()
        with self.db.session() as s:
            row = s.get(User, user_id)
            return row is not None and row.quiet_until is not None and row.quiet_until > now

    def routines(self, user: User) -> RoutinesFile:
        text = self.mirror.read_text(user.id, WorkspacePaths.ROUTINES)
        if text is not None:
            try:
                return RoutinesFile.parse_yaml(text)
            except (ValueError, yaml.YAMLError):
                log.warning("routines.yaml of %s is invalid; using defaults", user.id)
        return default_routines()
