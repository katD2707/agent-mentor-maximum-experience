"""`/api/research` (CONTRACTS section 15): Nghiên cứu for students of the `uni` band.

Auth on every route: 401 `unauthorized`, 403 `role_mismatch` for a teacher, 403 `not_university` for a student whose derived
band is not `uni` (checked per request, so a band change applies at once). Errors are `{"error": code}`.
"""

import json
from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from mentor_schemas.research import (
    ActionItemPatch,
    AddPaperRequest,
    AgendaInput,
    AskInput,
    Experiment,
    ExperimentInput,
    ExperimentList,
    ExperimentPatch,
    JobStarted,
    Meeting,
    MeetingInput,
    MeetingPatch,
    Milestone,
    MilestoneInput,
    MilestonePatch,
    NotesInput,
    PaperDetail,
    PaperFeedback,
    PaperNote,
    PaperQA,
    ReadingEntry,
    ReadingList,
    RelatedPapers,
    ResearchJob,
    ResearchOverview,
    ResearchProfile,
    ResearchProfileInput,
    ReviewRequest,
    SearchDepth,
    SearchResponse,
    SourceKeyInput,
    SourceKeysStatus,
    StatusInput,
    SuggestionList,
    SummaryInput,
)
from pydantic import ValidationError

from mentor_gateway.api.ask import MAX_AUDIO_BYTES, _audio_format
from mentor_gateway.api.deps import student_user
from mentor_gateway.db import User
from mentor_gateway.research.base import ModelUnavailable, fail
from mentor_gateway.research.service import ResearchService

router = APIRouter(prefix="/research", tags=["research"])


def uni_user(user: User = Depends(student_user)) -> User:
    if user.age_band != "uni":
        raise HTTPException(403, {"error": "not_university"})
    return user


def research(request: Request) -> ResearchService:
    return request.app.state.research


def _detail(exc: ValidationError) -> HTTPException:
    return HTTPException(422, json.loads(exc.json(include_url=False)))


Svc = Depends(research)
Uni = Depends(uni_user)

# ---- overview, profile, keys ---------------------------------------------------------------------------------------


@router.get("", response_model=ResearchOverview)
async def overview(user: User = Uni, svc: ResearchService = Svc) -> ResearchOverview:
    return await svc.overview(user)


@router.get("/profile", response_model=ResearchProfile)
async def get_profile(user: User = Uni, svc: ResearchService = Svc) -> ResearchProfile:
    return svc.profile_view(user.id)


@router.put("/profile", response_model=ResearchProfile)
async def put_profile(body: dict[str, Any] = Body(...), user: User = Uni, svc: ResearchService = Svc) -> ResearchProfile:
    try:
        inp = ResearchProfileInput.model_validate(body)
    except ValidationError as exc:
        locs = {e["loc"][0] for e in exc.errors() if e["loc"]}
        if "title" in locs:
            raise fail(422, "empty_title") from None
        if "keywords" in locs:
            raise fail(422, "bad_keywords") from None
        raise _detail(exc) from None
    return await svc.put_profile(user, inp)


@router.get("/source-keys", response_model=SourceKeysStatus)
async def get_keys(user: User = Uni, svc: ResearchService = Svc) -> SourceKeysStatus:
    return svc.keys_status(user.id)


def _source(source: str) -> str:
    if source not in ("asta", "s2"):
        raise fail(404, "unknown_source")
    return source


@router.put("/source-keys/{source}", response_model=SourceKeysStatus)
async def put_key(body: SourceKeyInput, user: User = Uni, svc: ResearchService = Svc, source: str = Depends(_source)) -> SourceKeysStatus:
    return await svc.put_key(user, source, body.key)  # `_source` runs before the body is validated: unknown -> 404


@router.delete("/source-keys/{source}", response_model=SourceKeysStatus)
async def delete_key(source: str, user: User = Uni, svc: ResearchService = Svc) -> SourceKeysStatus:
    return svc.delete_key(user, _source(source))


# ---- search, related ------------------------------------------------------------------------------------------------


@router.get("/search", response_model=SearchResponse)
async def search(q: str = Query("", max_length=300), year_min: int | None = Query(None, ge=1900, le=2100), pdf: bool = False,
                 page: int = Query(1, ge=1, le=50), depth: SearchDepth | None = None,
                 user: User = Uni, svc: ResearchService = Svc) -> SearchResponse:
    return await svc.search(user, q, year_min, pdf, page, depth)


@router.get("/papers/{paper_id}/related", response_model=RelatedPapers)
async def related(paper_id: str, user: User = Uni, svc: ResearchService = Svc) -> RelatedPapers:
    return await svc.related(user, paper_id)


# ---- jobs -----------------------------------------------------------------------------------------------------------


@router.post("/review", status_code=202, response_model=JobStarted)
async def start_review(body: ReviewRequest, user: User = Uni, svc: ResearchService = Svc) -> JobStarted:
    return svc.start_review(user, body)


@router.get("/jobs/{job_id}", response_model=ResearchJob)
async def get_job(job_id: str, user: User = Uni, svc: ResearchService = Svc) -> ResearchJob:
    return svc.job_view(user.id, job_id)


@router.post("/discovery", status_code=202, response_model=JobStarted)
async def start_discovery(user: User = Uni, svc: ResearchService = Svc) -> JobStarted:
    return svc.start_discovery(user, manual=True)  # type: ignore[return-value]


@router.get("/suggestions", response_model=SuggestionList)
async def suggestions(user: User = Uni, svc: ResearchService = Svc) -> SuggestionList:
    return svc.suggestion_list(user.id)


@router.post("/suggestions/{sid}/accept", status_code=201, response_model=ReadingEntry)
async def accept_suggestion(sid: str, user: User = Uni, svc: ResearchService = Svc) -> ReadingEntry:
    return svc.accept_suggestion(user, sid)


@router.post("/suggestions/{sid}/dismiss", status_code=204)
async def dismiss_suggestion(sid: str, user: User = Uni, svc: ResearchService = Svc) -> Response:
    svc.dismiss_suggestion(user, sid)
    return Response(status_code=204)


# ---- reading list and the reader ------------------------------------------------------------------------------------


@router.get("/reading-list", response_model=ReadingList)
async def reading_list(user: User = Uni, svc: ResearchService = Svc) -> ReadingList:
    return svc.reading_list(user.id)


@router.post("/reading-list", response_model=ReadingEntry, status_code=201)
async def add_paper(body: AddPaperRequest, response: Response, user: User = Uni, svc: ResearchService = Svc) -> ReadingEntry:
    entry, created = await svc.add_paper(user, body)
    if not created:
        response.status_code = 200
    return entry


@router.delete("/reading-list/{paper_id}", status_code=204)
async def remove_paper(paper_id: str, user: User = Uni, svc: ResearchService = Svc) -> Response:
    svc.remove_paper(user, paper_id)
    return Response(status_code=204)


@router.put("/papers/{paper_id}/status", response_model=ReadingEntry)
async def set_status(paper_id: str, body: StatusInput, user: User = Uni, svc: ResearchService = Svc) -> ReadingEntry:
    return svc.set_status(user, paper_id, body.status)


@router.get("/papers/{paper_id}", response_model=PaperDetail)
async def paper_detail(paper_id: str, user: User = Uni, svc: ResearchService = Svc) -> PaperDetail:
    return svc.paper_detail(user, paper_id)


@router.put("/papers/{paper_id}/summary", response_model=PaperNote)
async def put_summary(paper_id: str, body: SummaryInput, user: User = Uni, svc: ResearchService = Svc) -> PaperNote:
    return svc.put_summary(user, paper_id, body.text)


@router.post("/papers/{paper_id}/feedback", response_model=PaperFeedback)
async def feedback(paper_id: str, user: User = Uni, svc: ResearchService = Svc) -> PaperFeedback:
    return await svc.feedback(user, paper_id)


@router.get("/papers/{paper_id}/qa", response_model=list[PaperQA])
async def qa_thread(paper_id: str, user: User = Uni, svc: ResearchService = Svc) -> list[PaperQA]:
    return svc.qa_list(user, paper_id)


def sse(event: str, data: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode()


@router.post("/papers/{paper_id}/ask")
async def ask(paper_id: str, request: Request, user: User = Uni, svc: ResearchService = Svc) -> StreamingResponse:
    if svc.entry_for(user.id, paper_id) is None:
        raise fail(404, "paper_not_found")
    audio: bytes | None = None
    fmt = "wav"
    ctype = request.headers.get("content-type", "")
    if ctype.startswith(("multipart/", "application/x-www-form-urlencoded")):
        form = await request.form()
        raw: dict[str, Any] = {"text": str(form.get("text") or "x"), "lang": form.get("lang") or None}
        upload = form.get("audio")
        if upload is not None and hasattr(upload, "read"):
            audio = await upload.read(MAX_AUDIO_BYTES + 1)
            if len(audio) > MAX_AUDIO_BYTES:
                raise HTTPException(413, {"error": "file_too_large"})
            fmt = _audio_format(getattr(upload, "filename", None), getattr(upload, "content_type", None))
    else:
        try:
            raw = await request.json()
        except ValueError:
            raise HTTPException(422, {"error": "bad_request"}) from None
    try:
        body = AskInput.model_validate(raw if isinstance(raw, dict) else {})
    except ValidationError as exc:
        raise _detail(exc) from None

    async def gen() -> AsyncIterator[bytes]:
        question = body.text
        if audio is not None:
            try:
                question = (await svc.transcribe(audio, fmt))[:500]
            except ModelUnavailable:
                yield sse("error", {"code": "model_unavailable", "message": "The model is not available right now."})
                yield sse("done", {"qa_id": None})
                return
        async for event, data in svc.ask_events(user, paper_id, question, body.lang):
            yield sse(event, data)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


# ---- experiments ----------------------------------------------------------------------------------------------------


@router.get("/experiments", response_model=ExperimentList)
async def list_experiments(limit: int = Query(20, ge=1, le=50), before: str | None = None, user: User = Uni,
                           svc: ResearchService = Svc) -> ExperimentList:
    return svc.list_experiments(user.id, limit, before)


@router.post("/experiments", status_code=201, response_model=Experiment)
async def create_experiment(body: ExperimentInput, user: User = Uni, svc: ResearchService = Svc) -> Experiment:
    return await svc.create_experiment(user, body)


@router.get("/experiments/{eid}", response_model=Experiment)
async def get_experiment(eid: str, user: User = Uni, svc: ResearchService = Svc) -> Experiment:
    return svc.get_experiment(user.id, eid)


@router.patch("/experiments/{eid}", response_model=Experiment)
async def patch_experiment(eid: str, body: ExperimentPatch, user: User = Uni, svc: ResearchService = Svc) -> Experiment:
    return svc.patch_experiment(user, eid, body)


# ---- meetings -------------------------------------------------------------------------------------------------------


@router.get("/meetings", response_model=list[Meeting])
async def list_meetings(status: Literal["scheduled", "done", "all"] = "scheduled", user: User = Uni,
                        svc: ResearchService = Svc) -> list[Meeting]:
    return svc.list_meetings(user.id, status)


@router.get("/meetings/next", response_model=Meeting | None)
async def next_meeting(user: User = Uni, svc: ResearchService = Svc) -> Meeting | None:
    return svc.next_meeting(user.id)


@router.post("/meetings", status_code=201, response_model=Meeting)
async def create_meeting(body: MeetingInput, user: User = Uni, svc: ResearchService = Svc) -> Meeting:
    return await svc.create_meeting(user, body)


@router.patch("/meetings/{mid}", response_model=Meeting)
async def patch_meeting(mid: str, body: MeetingPatch, user: User = Uni, svc: ResearchService = Svc) -> Meeting:
    return svc.patch_meeting(user, mid, body)


@router.delete("/meetings/{mid}", status_code=204)
async def delete_meeting(mid: str, user: User = Uni, svc: ResearchService = Svc) -> Response:
    svc.delete_meeting(user, mid)
    return Response(status_code=204)


@router.put("/meetings/{mid}/agenda", response_model=Meeting)
async def put_agenda(mid: str, body: AgendaInput, user: User = Uni, svc: ResearchService = Svc) -> Meeting:
    return svc.put_agenda(user, mid, body)


@router.post("/meetings/{mid}/agenda/draft", response_model=Meeting)
async def draft_agenda(mid: str, user: User = Uni, svc: ResearchService = Svc) -> Meeting:
    try:
        return await svc.draft_agenda(user, mid, require_model=True)
    except ModelUnavailable:
        raise fail(503, "model_unavailable") from None


@router.put("/meetings/{mid}/notes", response_model=Meeting)
async def put_notes(mid: str, body: NotesInput, user: User = Uni, svc: ResearchService = Svc) -> Meeting:
    return await svc.put_notes(user, mid, body.notes_md)


@router.patch("/meetings/{mid}/actions/{aid}", response_model=Meeting)
async def patch_action(mid: str, aid: str, body: ActionItemPatch, user: User = Uni, svc: ResearchService = Svc) -> Meeting:
    return svc.patch_action(user, mid, aid, body)


# ---- deadlines ------------------------------------------------------------------------------------------------------


@router.get("/deadlines", response_model=list[Milestone])
async def list_deadlines(include_done: bool = False, user: User = Uni, svc: ResearchService = Svc) -> list[Milestone]:
    return svc.list_deadlines(user.id, include_done)


@router.post("/deadlines", status_code=201, response_model=Milestone)
async def create_deadline(body: MilestoneInput, user: User = Uni, svc: ResearchService = Svc) -> Milestone:
    return await svc.create_deadline(user, body)


@router.patch("/deadlines/{mid}", response_model=Milestone)
async def patch_deadline(mid: str, body: MilestonePatch, user: User = Uni, svc: ResearchService = Svc) -> Milestone:
    return svc.patch_deadline(user, mid, body)


@router.delete("/deadlines/{mid}", status_code=204)
async def delete_deadline(mid: str, user: User = Uni, svc: ResearchService = Svc) -> Response:
    svc.delete_deadline(user, mid)
    return Response(status_code=204)
