"""/me, onboarding, parent link, settings and account deletion."""

import asyncio
import logging
from typing import Literal

from croniter import croniter
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from mentor_schemas import JobKind, ProactivityLevel, Profile, Routine, RoutinesFile, WorkspacePaths
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import delete

from mentor_gateway.api.deps import COOKIE_NAME, current_user, get_gw, provisioned_user
from mentor_gateway.context import Gateway
from mentor_gateway.db import (
    ChatSession,
    Conversation,
    JobRow,
    NotificationActionRow,
    NotificationMeta,
    NotificationRow,
    NudgeHold,
    OutboxSeen,
    PushSubscription,
    RoutineSchedule,
    SentReport,
    UploadToken,
    User,
    UserOnboarding,
    UserUiState,
    WebSession,
)
from mentor_gateway.parent import AlreadyVerifiedError
from mentor_gateway.provisioning import provision_workspace
from mentor_gateway.routine_policy import routine_violation
from mentor_gateway.users import Me, TourState

log = logging.getLogger(__name__)
router = APIRouter(tags=["account"])


@router.get("/me", response_model=Me)
def get_me(user: User = Depends(current_user), gw: Gateway = Depends(get_gw)) -> Me:
    return gw.users.me(user)


class OnboardingBody(BaseModel):
    role: Literal["thpt", "ncs"]
    display_name: str
    language: Literal["vi", "en"] = "vi"


@router.post("/onboarding", response_model=Me)
async def onboarding(body: OnboardingBody, user: User = Depends(current_user), gw: Gateway = Depends(get_gw)) -> Me:
    name = body.display_name.strip()[:200] or user.display_name
    if user.provisioned_at is not None:
        if user.role != body.role:
            raise HTTPException(409, "role cannot be changed after onboarding")
        user = gw.users.update(user.id, display_name=name, language=body.language)
        return gw.users.me(user)
    profile = Profile(body.role)
    warnings = await asyncio.to_thread(
        provision_workspace, gw.settings.content_dir, gw.sync, user.id, profile, name, body.language
    )
    for w in warnings:
        log.warning("provisioning %s: %s", user.id, w)
    gw.users.ensure_inbound_code(user.id)
    user = gw.users.update(user.id, role=profile.value, display_name=name, language=body.language,
                           provisioned_at=gw.clock())
    return gw.users.me(user)


# ---- first-run tour ------------------------------------------------------------------------------


class TourBody(BaseModel):
    """One change per request; send only the fields you need."""

    step: Literal["welcome", "ask", "practice", "time"] | None = None
    complete: bool = False
    skip: bool = False
    restart: bool = False  # replay from Settings
    tip: str | None = Field(default=None, pattern=r"^[a-z0-9_-]{1,40}$")

    @model_validator(mode="after")
    def _something(self) -> "TourBody":
        if self.step is None and self.tip is None and not (self.complete or self.skip or self.restart):
            raise ValueError("nothing to update")
        return self


@router.get("/onboarding", response_model=TourState)
def get_tour(user: User = Depends(provisioned_user), gw: Gateway = Depends(get_gw)) -> TourState:
    return gw.users.tour(user.id)


@router.put("/onboarding", response_model=TourState)
def put_tour(body: TourBody, user: User = Depends(provisioned_user), gw: Gateway = Depends(get_gw)) -> TourState:
    return gw.users.update_tour(user.id, step=body.step, complete=body.complete, skip=body.skip,
                                restart=body.restart, tip=body.tip)


# ---- parent link ---------------------------------------------------------------------------------


@router.post("/parent-link")
async def start_parent_link(user: User = Depends(provisioned_user), gw: Gateway = Depends(get_gw)) -> dict:
    if user.role != Profile.THPT.value:
        raise HTTPException(400, "parent link is only for THPT learners")
    try:
        link = await gw.parent.start_link(user.id)
    except AlreadyVerifiedError as exc:
        raise HTTPException(409, "parent already verified") from exc
    return {
        "link_code": link.link_code,
        "expires_at": link.code_expires_at.isoformat(),
        "bot_name": gw.settings.zalo_bot_name,
        "bot_url": gw.settings.zalo_bot_url or None,
        "dev_verify": gw.settings.env == "dev",  # web shows a skip button that calls /dev/parent-link/verify
    }


@router.get("/parent-link")
def get_parent_link(user: User = Depends(current_user), gw: Gateway = Depends(get_gw)) -> dict:
    link = gw.parent.get_link(user.id)
    if link is None or link.status == "revoked":
        return {"status": "none"}
    out: dict = {"status": link.status}
    if link.status in ("pending", "awaiting_consent"):
        out["expires_at"] = link.code_expires_at.isoformat()
    return out


@router.post("/dev/parent-link/verify", include_in_schema=False)
def dev_verify_parent(user: User = Depends(provisioned_user), gw: Gateway = Depends(get_gw)) -> dict:
    """MENTOR_ENV=dev only: pretend the parent consented on Zalo."""
    if gw.settings.env != "dev":
        raise HTTPException(404)
    gw.parent.dev_verify(user.id)
    return {"status": "verified"}


# ---- settings ------------------------------------------------------------------------------------

class SettingsBody(BaseModel):
    proactivity: ProactivityLevel
    quiet_hours: tuple[str, str]
    language: Literal["vi", "en"]
    routines: list[Routine]

    @field_validator("quiet_hours")
    @classmethod
    def _hhmm(cls, v: tuple[str, str]) -> tuple[str, str]:
        for x in v:
            h, _, m = x.partition(":")
            if not (h.isdigit() and m.isdigit() and 0 <= int(h) < 24 and 0 <= int(m) < 60):
                raise ValueError("quiet_hours must be HH:MM")
        return v

    @field_validator("routines")
    @classmethod
    def _routines(cls, v: list[Routine]) -> list[Routine]:
        for r in v:
            JobKind(r.job_kind)
            if not croniter.is_valid(r.cron):
                raise ValueError(f"invalid cron for {r.id}: {r.cron}")
        return v


def _routine_key(r: Routine) -> tuple:
    return (r.enabled, r.cron.strip(), r.job_kind, r.prompt or None)


def _settings_view(gw: Gateway, user: User) -> dict:
    rf = gw.users.routines(user)
    return {
        "proactivity": rf.proactivity.value,
        "quiet_hours": list(rf.quiet_hours),
        "language": user.language,
        "routines": [r.model_dump(mode="json") for r in rf.routines],
    }


@router.get("/settings")
def get_settings(user: User = Depends(provisioned_user), gw: Gateway = Depends(get_gw)) -> dict:
    return _settings_view(gw, user)


@router.put("/settings")
async def put_settings(body: SettingsBody, user: User = Depends(provisioned_user),
                       gw: Gateway = Depends(get_gw)) -> dict:
    current = gw.users.routines(user)
    locked = {r.id: r for r in current.routines if not r.user_editable}
    sent = {r.id: r for r in body.routines}
    for rid, r in locked.items():
        # platform routines (nightly_reflection, parent_report) may be echoed back but not changed or removed
        if rid not in sent or _routine_key(sent[rid]) != _routine_key(r):
            raise HTTPException(422, f"routine '{rid}' cannot be changed")
    routines = [r.model_copy(update={"user_editable": True}) for r in body.routines if r.id not in locked]
    if len({r.id for r in body.routines}) != len(body.routines):
        raise HTTPException(422, "duplicate routine id")
    previous = {r.id: _routine_key(r) for r in current.routines}
    for r in routines:
        # new or changed learner routines: no platform job kinds, at most hourly (unchanged ones are echoed back)
        if previous.get(r.id) != _routine_key(r) and (why := routine_violation(r, from_user=True)):
            raise HTTPException(422, why)
    merged = [locked[rid] for rid in locked] + routines
    rf = RoutinesFile(timezone=current.timezone, proactivity=body.proactivity, quiet_hours=body.quiet_hours,
                      routines=merged)
    base = await asyncio.to_thread(gw.mirror.blob_sha, user.id, WorkspacePaths.ROUTINES)
    await asyncio.to_thread(
        gw.mirror.commit_files, user.id, {WorkspacePaths.ROUTINES: rf.to_yaml().encode("utf-8")},
        author="user", message="Cập nhật cài đặt", expected={WorkspacePaths.ROUTINES: base},
    )
    user = gw.users.update(user.id, language=body.language)
    return _settings_view(gw, user)


class SetupGuideBody(BaseModel):
    dismissed: bool


@router.put("/settings/setup-guide")
def put_setup_guide(body: SetupGuideBody, user: User = Depends(provisioned_user),
                    gw: Gateway = Depends(get_gw)) -> dict:
    """First-login setup guide: closed (stays closed on every device) or reset (shown again on the next visit)."""
    at = gw.users.set_setup_guide_dismissed(user.id, body.dismissed)
    return {"setup_guide_dismissed_at": at.isoformat() if at else None}


# ---- account deletion ----------------------------------------------------------------------------


@router.delete("/account")
async def delete_account(user: User = Depends(current_user), gw: Gateway = Depends(get_gw)) -> JSONResponse:
    uid = user.id
    try:
        await gw.orchestrator.stop(uid)
    except Exception:
        log.exception("stopping sandbox of %s", uid)
    await asyncio.to_thread(gw.sync.delete, uid)
    await asyncio.to_thread(gw.mirror.delete, uid)
    gw.parent.store.delete_student(uid)
    try:
        await gw.gcal.disconnect(uid)  # revoke Google Calendar access at Google, forget the tokens
    except Exception:
        log.exception("revoking google calendar of %s", uid)
    if gw.backups is not None:
        # crypto-shred: drop the data key (every copy of the user's snapshots becomes unreadable), delete local
        # snapshot files, scrub the user from local ops.db snapshots. Before the row deletes so a failure is retryable.
        await asyncio.to_thread(gw.backups.forget_user, uid)
    with gw.db.session() as s:
        for model, col in (
            (WebSession, WebSession.user_id), (ChatSession, ChatSession.user_id), (Conversation, Conversation.user_id), (JobRow, JobRow.user_id),
            (RoutineSchedule, RoutineSchedule.user_id), (NotificationMeta, NotificationMeta.user_id),
            (NotificationActionRow, NotificationActionRow.user_id), (NotificationRow, NotificationRow.user_id),
            (PushSubscription, PushSubscription.user_id), (NudgeHold, NudgeHold.user_id),
            (OutboxSeen, OutboxSeen.user_id), (UploadToken, UploadToken.user_id), (SentReport, SentReport.user_id),
            (UserUiState, UserUiState.user_id), (UserOnboarding, UserOnboarding.user_id),
        ):
            s.execute(delete(model).where(col == uid))
        if gw.practice is not None:
            gw.practice.forget(s, uid)
        s.execute(delete(User).where(User.id == uid))
    # audit_log rows (consent, crisis alerts) are kept: minimal content, needed as legal record (plan 8.3).
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp
