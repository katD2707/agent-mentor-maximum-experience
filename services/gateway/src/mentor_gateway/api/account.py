"""`/api/me`: the user, profile settings and "quiet until" (CONTRACTS section 4)."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from mentor_gateway.api.deps import current_user, get_gw
from mentor_gateway.context import Gateway
from mentor_gateway.db import User
from mentor_gateway.age import BIRTH_YEAR_MAX, BIRTH_YEAR_MIN
from mentor_gateway.users import Language, Theme, UserView

router = APIRouter(tags=["account"])


@router.get("/me", response_model=UserView)
def get_me(user: User = Depends(current_user), gw: Gateway = Depends(get_gw)) -> UserView:
    return gw.users.view(user)


class MePatch(BaseModel):
    """Only the fields present are changed. `language` may be set back to null. `birth_year` is set once (first
    run); the age band is derived from it, so there is no `age_band` here."""

    birth_year: int | None = Field(default=None, ge=BIRTH_YEAR_MIN, le=BIRTH_YEAR_MAX)
    language: Language | None = None
    theme: Theme | None = None
    display_name: str | None = Field(default=None, max_length=200)

    @field_validator("display_name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("display_name must not be empty")
        return v


@router.patch("/me", response_model=UserView)
def patch_me(body: MePatch, user: User = Depends(current_user), gw: Gateway = Depends(get_gw)) -> UserView:
    fields = {k: getattr(body, k) for k in body.model_fields_set}
    if fields.get("theme") is None:  # theme is never null
        fields.pop("theme", None)
    if fields.get("display_name") is None:
        fields.pop("display_name", None)
    if "birth_year" in fields:
        if fields["birth_year"] is None:
            raise HTTPException(422, {"error": "bad_request"})
        if user.birth_year is not None:  # students cannot change it; an operator can (cli set-birth-year)
            raise HTTPException(409, {"error": "birth_year_locked"})
    return gw.users.view(gw.users.update(user.id, **fields)) if fields else gw.users.view(user)


class QuietBody(BaseModel):
    until: datetime | None

    @field_validator("until")
    @classmethod
    def _utc(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        return v.replace(tzinfo=UTC) if v.tzinfo is None else v.astimezone(UTC)


@router.put("/me/quiet")
def put_quiet(body: QuietBody, user: User = Depends(current_user), gw: Gateway = Depends(get_gw)) -> dict:
    """`until` in the future = no notifications until then; null clears it. Echoes the stored value (UTC, `Z`)."""
    gw.users.update(user.id, quiet_until=body.until)
    return {"until": body.until.isoformat().replace("+00:00", "Z") if body.until else None}
