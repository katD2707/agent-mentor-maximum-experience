"""Drive the harness in-process through a scenario and grade it.

Per scenario: fresh provisioned workspace -> for each session a new `Harness` (a fresh sandbox process, so
only workspace files carry memory across sessions) -> turns via `Harness.run_turn`, jobs via
`Harness.run_job` -> checks after each turn/job and at the end.
"""

from __future__ import annotations

import asyncio
import shutil
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mentor_harness.agent import Harness
from mentor_harness.config import Settings, now_local
from mentor_harness.scripts import run_mentor_script
from mentor_harness.workspace import ensure_git_safe_directory
from mentor_schemas import JobRequest, SandboxEvent, TurnRequest

from mentor_evals.graders import CheckContext, CheckResult, JudgeFn, TurnRecord, run_check
from mentor_evals.models import EvalScriptedModel, RecordingModel
from mentor_evals.spec import CheckSpec, Persona, Scenario, Session
from mentor_evals.workspace import MEMORY_DIRS, WELLBEING_PATH, provision, snapshot, wellbeing_series


@dataclass
class ScenarioResult:
    scenario: Scenario
    persona: Persona
    model_mode: str
    checks: list[CheckResult] = field(default_factory=list)
    turns: list[TurnRecord] = field(default_factory=list)
    error: str | None = None
    duration_s: float = 0.0
    workspace: str = ""
    usage: dict[str, int] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.error is None and not any(c.failed and c.severity == "critical" for c in self.checks)

    @property
    def crisis_alerted(self) -> bool:
        return any(o.get("kind") == "crisis_alert" for t in self.turns for o in t.outbox)

    def to_dict(self, run_id: str, judge_mode: str) -> dict[str, Any]:
        s = self.scenario
        return {
            "run_id": run_id,
            "scenario": s.id,
            "suite": s.suite,
            "persona": self.persona.id,
            "profile": self.persona.profile.value,
            "tags": s.tags,
            "crisis": s.crisis,
            "model": self.model_mode,
            "judge": judge_mode,
            "passed": self.passed,
            "crisis_alerted": self.crisis_alerted,
            "error": self.error,
            "duration_s": round(self.duration_s, 2),
            "usage": self.usage,
            "checks": [c.to_dict() for c in self.checks],
            "turns": [t.to_dict() for t in self.turns],
            "workspace": self.workspace,
        }


class ScenarioRunner:
    def __init__(
        self,
        *,
        model_mode: str,
        workspaces_dir: Path,
        judge: JudgeFn | None = None,
        router_model: Any = None,
        keep_workspaces: bool = True,
    ) -> None:
        if model_mode not in ("scripted", "router"):
            raise ValueError("model_mode must be 'scripted' or 'router'")
        if model_mode == "router" and router_model is None:
            raise ValueError("router mode needs a router model")
        self.model_mode = model_mode
        self.workspaces_dir = workspaces_dir
        self.judge = judge
        self.router_model = router_model
        self.keep_workspaces = keep_workspaces
        ensure_git_safe_directory()

    async def run(self, scenario: Scenario, persona: Persona) -> ScenarioResult:
        result = ScenarioResult(scenario, persona, self.model_mode)
        started = time.perf_counter()
        root = self.workspaces_dir / scenario.id
        result.workspace = root.as_posix()
        scripted = EvalScriptedModel() if self.model_mode == "scripted" else None
        recorder = RecordingModel(scripted if scripted is not None else self.router_model)
        try:
            baseline = await asyncio.to_thread(self._provision, root, scenario, persona)
            for si, session in enumerate(scenario.sessions):
                await self._run_session(si, session, root, baseline, scenario, persona, recorder, scripted, result)
            ctx = CheckContext(root, baseline, result.turns, persona, scenario, "scenario", self.judge)
            for n, spec in enumerate(scenario.expect):
                result.checks.append(await run_check(spec, ctx, f"scenario.{spec.check}#{n}"))
            if scripted is not None and scripted.exhausted:
                result.checks.append(
                    CheckResult("scripted.exhausted", "no_script_exhaustion", "fail", "critical", "scenario",
                                f"{scripted.exhausted} model call(s) had no scripted step")
                )  # fmt: skip
        except Exception as exc:  # noqa: BLE001 - one broken scenario must not stop the run
            result.error = f"{exc.__class__.__name__}: {exc}"
            result.checks.append(
                CheckResult("runner", "runner", "error", "critical", "scenario", traceback.format_exc()[-1500:])
            )
        result.usage = dict(recorder.usage)
        result.duration_s = time.perf_counter() - started
        if not self.keep_workspaces and result.passed:
            shutil.rmtree(root, ignore_errors=True)
        return result

    # ---- internals ----------------------------------------------------------------------------

    def _provision(self, root: Path, scenario: Scenario, persona: Persona) -> dict[str, str]:
        seeds = {**persona.seed_files, **scenario.seed_files}
        if scenario.seed_wellbeing:
            today = now_local().date()
            seeds[WELLBEING_PATH] = wellbeing_series(today, **scenario.seed_wellbeing)
        provision(
            root,
            user_id=f"eval-{persona.id}",
            profile=persona.profile,
            display_name=persona.display_name,
            language=persona.language,
            seed_files=seeds,
        )
        return snapshot(root, (*MEMORY_DIRS, ".mentor"))

    def _harness(self, root: Path, persona: Persona, recorder: RecordingModel) -> Harness:
        settings = Settings(workspace_root=root, profile=persona.profile, user_id=f"eval-{persona.id}")
        return Harness(settings, recorder, script_runner=run_mentor_script)

    async def _run_session(
        self,
        si: int,
        session: Session,
        root: Path,
        baseline: dict[str, str],
        scenario: Scenario,
        persona: Persona,
        recorder: RecordingModel,
        scripted: EvalScriptedModel | None,
        result: ScenarioResult,
    ) -> None:
        harness = self._harness(root, persona, recorder)  # new process: no in-memory chat history
        session_id = f"eval-{scenario.id}-{session.id or si}"
        if session.job is not None:
            if scripted is not None:
                scripted.load(session.scripted)
            record = await self._run_job(harness, si, session, session_id, persona, recorder)
            result.turns.append(record)
            await self._grade(session.expect, record, root, baseline, scenario, persona, result, auto_ok=False)
            return
        for ti, turn in enumerate(session.turns):
            if scripted is not None:
                scripted.load(turn.scripted, safety_confirms=turn.scripted_safety)
            record = await self._run_turn(harness, si, ti, turn.user, session_id, persona, recorder)
            result.turns.append(record)
            await self._grade(
                turn.expect, record, root, baseline, scenario, persona, result, auto_ok=not turn.allow_error
            )

    async def _run_turn(
        self, harness: Harness, si: int, ti: int, text: str, session_id: str, persona: Persona, recorder: RecordingModel
    ) -> TurnRecord:
        record = TurnRecord("turn", si, ti, session_id, text)
        calls_before, reviews_before = len(recorder.tool_calls), len(recorder.safety_reviews)
        offered_before = len(recorder.offered)
        events: list[SandboxEvent] = []

        async def emit(event: SandboxEvent) -> None:
            events.append(event)

        started = time.perf_counter()
        req = TurnRequest(session_id=session_id, user_id=f"eval-{persona.id}", profile=persona.profile, text=text)
        await harness.run_turn(req, emit)
        record.duration_s = time.perf_counter() - started
        recorder.resolve_results()
        record.events = [e.type for e in events]
        record.reply = "".join(e.text or "" for e in events if e.type == "text_delta")
        final = next((e for e in reversed(events) if e.type in ("done", "error")), None)
        if final is None:
            record.error = "turn ended without done/error"
        else:
            record.outbox = [o.model_dump(mode="json") for o in final.outbox]
            if final.type == "error":
                record.error = final.error or "error"
        record.tool_calls = recorder.tool_calls[calls_before:]
        record.offered_tools = sorted({n for o in recorder.offered[offered_before:] for n in o.split(",") if n})
        record.safety_reviews = [
            {"alias": r.alias, "confirmed": r.confirmed} for r in recorder.safety_reviews[reviews_before:]
        ]
        return record

    async def _run_job(
        self, harness: Harness, si: int, session: Session, session_id: str, persona: Persona, recorder: RecordingModel
    ) -> TurnRecord:
        assert session.job is not None
        record = TurnRecord("job", si, 0, session_id, session.job.value)
        calls_before, reviews_before = len(recorder.tool_calls), len(recorder.safety_reviews)
        offered_before = len(recorder.offered)
        started = time.perf_counter()
        req = JobRequest(
            job_id=f"{session_id}-job",
            user_id=f"eval-{persona.id}",
            profile=persona.profile,
            kind=session.job,
            prompt=session.job_prompt,
        )
        res = await harness.run_job(req)
        record.duration_s = time.perf_counter() - started
        recorder.resolve_results()
        record.job_status, record.job_summary, record.reply = res.status, res.summary, res.summary
        record.error = res.error
        record.outbox = [o.model_dump(mode="json") for o in res.outbox]
        record.tool_calls = recorder.tool_calls[calls_before:]
        record.offered_tools = sorted({n for o in recorder.offered[offered_before:] for n in o.split(",") if n})
        record.safety_reviews = [
            {"alias": r.alias, "confirmed": r.confirmed} for r in recorder.safety_reviews[reviews_before:]
        ]
        return record

    async def _grade(
        self,
        specs: list[CheckSpec],
        record: TurnRecord,
        root: Path,
        baseline: dict[str, str],
        scenario: Scenario,
        persona: Persona,
        result: ScenarioResult,
        *,
        auto_ok: bool,
    ) -> None:
        ctx = CheckContext(root, baseline, [record], persona, scenario, record.label, self.judge)
        if auto_ok:
            result.checks.append(await run_check(CheckSpec(check="turn_ok"), ctx, f"{record.label}.turn_ok"))
        for n, spec in enumerate(specs):
            result.checks.append(await run_check(spec, ctx, f"{record.label}.{spec.check}#{n}"))
