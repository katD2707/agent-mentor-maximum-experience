"""FastAPI app: `uvicorn mentor_gateway.app:app --port 8000`.

`app` is built lazily from the environment on first access so importing this module has no side
effects; tests call `create_app(settings, ...)` directly.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from mentor_gateway.api import account, ai_key, ask, auth, courses, goals, guide, nudges, plan, teacher, workspace
from mentor_gateway.api import research as research_api
from mentor_gateway.api import practice as practice_api
from mentor_gateway.content.service import ContentService
from mentor_gateway.content.store import ContentError
from mentor_gateway import userai
from mentor_gateway.context import build_gateway
from mentor_gateway.hub import HubError
from mentor_gateway.jobs import JobExecutor
from mentor_gateway.langga import api as langga_api
from mentor_gateway.langga.chat import ChatService
from mentor_gateway.langga.focus import FocusService
from mentor_gateway.langga.hooks import make_progress_hook
from mentor_gateway.langga.resolve import ChickenResolver
from mentor_gateway.langga.service import LanggaService
from mentor_gateway.practice import PracticeError
from mentor_gateway.teacher import steps as teacher_steps
from mentor_gateway.research.service import ResearchService
from mentor_gateway.settings import Clock, Settings, utc_now
from mentor_gateway.teacher import BuilderService
from mentor_gateway.teacher.service import Busy, Forbidden

log = logging.getLogger(__name__)


def _warm_search(content) -> None:
    try:
        content.search_courses("khởi động", None)
    except Exception:  # noqa: BLE001 - only a warm-up
        pass


def create_app(settings: Settings | None = None, *, clock: Clock = utc_now,
               executor: JobExecutor | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    gw = build_gateway(settings, clock=clock, executor=executor)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        tasks: list[asyncio.Task] = []
        await app.state.builder.start()  # resumes stages that were running when the gateway last stopped
        if app.state.content.remote is not None and settings.env != "test":  # installed app: the courses come from Drive
            tasks.append(asyncio.create_task(app.state.content.remote.run_forever()))
        if settings.background_tasks:
            tasks.append(asyncio.create_task(gw.scheduler.run_forever()))
            if settings.model_router_url:  # embed new course documents now, so the first Ask search is not the slow one
                tasks.append(asyncio.create_task(asyncio.to_thread(_warm_search, app.state.content)))
        try:
            yield
        finally:
            gw.scheduler.stop()
            await app.state.builder.stop()
            tasks += list(app.state.research.tasks)  # running research jobs end with the app
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await gw.runner.drain()
            gw.db.dispose()

    app = FastAPI(title="mentor-gateway", lifespan=lifespan)
    app.state.gw = gw
    app.state.content = ContentService(settings, gw.db, gw.box, clock)
    app.state.builder = BuilderService(settings, app.state.content, gw.db, clock, gw.hub)  # /api/teacher stages
    if gw.ai_store is not None and hasattr(app.state.builder.runner, "extra_env"):  # the course builder gets the user's key too
        app.state.builder.runner.extra_env = lambda: userai.builder_env(gw.ai_store)
    if gw.ai is not None:  # direct mode: the one client also serves course-search embeddings (lexical until a key is saved)
        app.state.content.search.embedder = gw.ai
    gw.planner.content = gw.practice.content = app.state.content  # course quiz items for Luyện tập
    gw.practice.planner = gw.planner
    gw.practice.course_tests = lambda cid: teacher_steps.course_tests(app.state.builder, cid)
    resolver = ChickenResolver(app.state.content)  # Làng gà: course -> chicken
    gw.practice.resolver = resolver
    app.state.content.progress_hook = make_progress_hook(gw.db, gw.xp, resolver)
    app.state.langga = LanggaService(gw.db, clock, gw.xp, app.state.content, gw.planner, gw.practice, resolver, gw.practice.papers)
    app.state.focus = FocusService(gw.db, clock, gw.xp, app.state.langga)
    app.state.chat = ChatService(gw.db, clock, app.state.langga)
    app.state.chicken_resolver = resolver
    app.state.research = ResearchService(gw, app.state.content, ask.build_llm(gw))  # /api/research (uni band)
    gw.scheduler.research = app.state.research.tick  # Monday discovery, agenda drafts
    app.add_exception_handler(ContentError, lambda _req, exc: courses.content_error_response(exc))
    app.add_exception_handler(Forbidden, lambda _req, exc: JSONResponse({"error": exc.code, "detail": str(exc)}, 403))
    app.add_exception_handler(Busy, lambda _req, exc: JSONResponse({"error": exc.code, "detail": str(exc)}, 409))
    app.add_exception_handler(HubError, lambda _req, exc: JSONResponse({"error": exc.code}, exc.status))  # hub answers pass through
    app.add_exception_handler(PracticeError, lambda _req, exc: practice_api.error_response(exc))

    @app.exception_handler(HTTPException)
    async def _http_error(request: Request, exc: HTTPException) -> Any:
        """`HTTPException(detail={"error": code})` goes out as `{"error": code}` (CONTRACTS section 4)."""
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(exc.detail, status_code=exc.status_code, headers=exc.headers)
        return await http_exception_handler(request, exc)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        # dev only: a build previewed on any other localhost port (vite preview, a second dev server) can log in too
        allow_origin_regex=r"^http://(localhost|127\.0\.0\.1)(:\d+)?$" if settings.env == "dev" else None,
        allow_credentials=False,  # bearer tokens, no cookies
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Accept", "Authorization", "If-None-Match", "Range"],
        expose_headers=["ETag", "Content-Range", "Accept-Ranges", "Content-Length"],  # the app reads ETag (catalog revalidation)
    )

    api = APIRouter(prefix="/api")
    api.include_router(auth.router)
    api.include_router(account.router)
    api.include_router(workspace.router)
    api.include_router(practice_api.router)  # /api/practice
    api.include_router(nudges.router)  # /api/notifications, /api/engagement, /api/push/*
    api.include_router(courses.router)  # /api/catalog, /api/courses, /api/enrollments, /api/search
    api.include_router(plan.router)  # /api/events, /api/today, /api/plan/week, /api/reminders
    api.include_router(goals.router)  # /api/goals
    api.include_router(ai_key.router)  # /api/ai-key (the user's own AI key, direct mode)
    api.include_router(ask.router)  # /api/ask (SSE Q&A)
    api.include_router(guide.router)  # /api/guide (guide chicken)
    api.include_router(teacher.router)  # /api/teacher (course authoring)
    api.include_router(research_api.router)  # /api/research (Nghiên cứu, uni band)
    api.include_router(langga_api.router)  # Làng gà: /api/village, /market, /chickens, /xp, /arena, /focus, /chat
    app.include_router(api)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    return app


_app: FastAPI | None = None


def __getattr__(name: str) -> Any:
    global _app
    if name == "app":
        if _app is None:
            logging.basicConfig(level=logging.INFO)
            _app = create_app()
        return _app
    raise AttributeError(name)
