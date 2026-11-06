"""Accounts, `Me`, onboarding state and the per-user routines view."""

import logging
from datetime import datetime
from typing import Literal

import yaml
from mentor_schemas import Profile, RoutinesFile, WorkspacePaths
from pydantic import BaseModel
from sqlalchemy import select

from mentor_gateway.db import Database, User, UserOnboarding, UserUiState
from mentor_gateway.mirror import Mirror
from mentor_gateway.parent import ParentChannel
from mentor_gateway.provisioning import default_routines
from mentor_gateway.security import new_id, random_code
from mentor_gateway.settings import Clock, Settings

log = logging.getLogger(__name__)

OnboardingState = Literal["needs_role", "needs_parent", "active"]


TOUR_STEPS = ("welcome", "ask", "practice", "time")
MAX_TIPS = 50


class TourState(BaseModel):
    """First-run tour progress (CONTRACTS 12). `tour_step` = where to resume; null when not started or finished."""

    tour_step: Literal["welcome", "ask", "practice", "time"] | None = None
    tour_completed_at: datetime | None = None
    tour_skipped_at: datetime | None = None
    tips_seen: list[str] = []


class Me(BaseModel):
    user_id: str
    email: str
    role: Literal["thpt", "ncs"] | None
    display_name: str
    language: Literal["vi", "en"]
    onboarding_state: OnboardingState
    inbound_email_address: str | None
    # when the learner closed the first-login setup guide; null = show it on the next visit
    setup_guide_dismissed_at: datetime | None = None
    tour: TourState = TourState()


class UserService:
    def __init__(self, db: Database, mirror: Mirror, parent: ParentChannel, settings: Settings, clock: Clock) -> None:
        self.db = db
        self.mirror = mirror
        self.parent = parent
        self.settings = settings
        self.clock = clock

    def get(self, user_id: str) -> User | None:
        with self.db.session() as s:
            return s.get(User, user_id)

    def get_or_create(self, email: str) -> User:
        email = email.strip().lower()
        with self.db.session() as s:
            user = s.scalars(select(User).where(User.email == email)).first()
            if user is None:
                user = User(id=new_id("u"), email=email, display_name=email.split("@")[0], language="vi",
                            created_at=self.clock())
                s.add(user)
            return user

    def all_provisioned(self) -> list[User]:
        with self.db.session() as s:
            return list(s.scalars(select(User).where(User.provisioned_at.is_not(None))))

    def update(self, user_id: str, **fields: object) -> User:
        with self.db.session() as s:
            user = s.get(User, user_id)
            if user is None:
                raise KeyError(user_id)
            for k, v in fields.items():
                setattr(user, k, v)
            return user

    def ensure_inbound_code(self, user_id: str) -> str:
        with self.db.session() as s:
            user = s.get(User, user_id)
            if user.inbound_code is None:
                while True:
                    code = random_code(10)
                    if s.scalars(select(User).where(User.inbound_code == code)).first() is None:
                        break
                user.inbound_code = code
            return user.inbound_code

    def user_id_for_inbound_address(self, address: str) -> str | None:
        """UserDirectory for the email ingest library."""
        addr = address.strip().strip("<>").lower()
        if "@" not in addr:
            return None
        local, domain = addr.rsplit("@", 1)
        if domain != self.settings.inbound_email_domain.lower():
            return None
        with self.db.session() as s:
            user = s.scalars(select(User).where(User.inbound_code == local)).first()
            return user.id if user else None

    def profile(self, user: User) -> Profile | None:
        return Profile(user.role) if user.role else None

    def onboarding_state(self, user: User) -> OnboardingState:
        if not user.role or user.provisioned_at is None:
            return "needs_role"
        if user.role == Profile.THPT.value and not self.parent.is_verified(user.id):
            return "needs_parent"
        return "active"

    def me(self, user: User) -> Me:
        return Me(
            user_id=user.id,
            email=user.email,
            role=user.role,
            display_name=user.display_name,
            language=user.language if user.language in ("vi", "en") else "vi",
            onboarding_state=self.onboarding_state(user),
            inbound_email_address=(
                f"{user.inbound_code}@{self.settings.inbound_email_domain}" if user.inbound_code else None
            ),
            setup_guide_dismissed_at=self.setup_guide_dismissed_at(user.id),
            tour=self.tour(user.id),
        )

    @staticmethod
    def _tour_of(row: UserOnboarding | None) -> TourState:
        if row is None:
            return TourState()
        step = row.tour_step if row.tour_step in TOUR_STEPS else None
        return TourState(tour_step=step, tour_completed_at=row.tour_completed_at, tour_skipped_at=row.tour_skipped_at,
                         tips_seen=[t for t in (row.tips_seen or []) if isinstance(t, str)])

    def tour(self, user_id: str) -> TourState:
        with self.db.session() as s:
            return self._tour_of(s.get(UserOnboarding, user_id))

    def update_tour(self, user_id: str, *, step: str | None = None, complete: bool = False, skip: bool = False,
                    restart: bool = False, tip: str | None = None) -> TourState:
        """Applies one change. restart clears completed/skipped and goes back to the welcome step (tips stay seen);
        complete/skip end the tour (first time is kept); step sets where to resume; tip marks one tip as seen."""
        with self.db.session() as s:
            row = s.get(UserOnboarding, user_id)
            if row is None:
                row = UserOnboarding(user_id=user_id, tips_seen=[])
                s.add(row)
            now = self.clock()
            if restart:
                row.tour_completed_at = None
                row.tour_skipped_at = None
                row.tour_step = "welcome"
            if step is not None:
                row.tour_step = step
            if complete:
                row.tour_step = None
                row.tour_completed_at = row.tour_completed_at or now
            if skip:
                row.tour_step = None
                row.tour_skipped_at = row.tour_skipped_at or now
            if tip is not None:
                seen = list(row.tips_seen or [])
                if tip not in seen and len(seen) < MAX_TIPS:
                    row.tips_seen = [*seen, tip]  # reassign: JSON columns do not track in-place changes
            s.flush()
            return self._tour_of(row)

    def setup_guide_dismissed_at(self, user_id: str) -> datetime | None:
        with self.db.session() as s:
            row = s.get(UserUiState, user_id)
            return row.setup_guide_dismissed_at if row else None

    def set_setup_guide_dismissed(self, user_id: str, dismissed: bool) -> datetime | None:
        """Records (or clears, to show the guide again) when the learner closed the setup guide."""
        with self.db.session() as s:
            row = s.get(UserUiState, user_id)
            if row is None:
                row = UserUiState(user_id=user_id)
                s.add(row)
            if not dismissed:
                row.setup_guide_dismissed_at = None
            elif row.setup_guide_dismissed_at is None:  # keep the first dismissal time
                row.setup_guide_dismissed_at = self.clock()
            return row.setup_guide_dismissed_at

    def routines(self, user: User) -> RoutinesFile:
        text = self.mirror.read_text(user.id, WorkspacePaths.ROUTINES)
        if text is not None:
            try:
                return RoutinesFile.parse_yaml(text)
            except (ValueError, yaml.YAMLError):
                log.warning("routines.yaml of %s is invalid; using defaults", user.id)
        return default_routines(self.profile(user) or Profile.NCS)
