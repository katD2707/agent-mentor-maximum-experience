"""Command line: `uv run --package mentor-evals mentor-evals <command>`.

  list                                   list scenarios (filters below apply)
  validate                               load every persona/scenario and validate all checks
  run [--model scripted|router] [--judge none|claude] [--suite S ...] [--scenario ID ...] [--tag T ...]
      [--concurrency N] [--out DIR] [--clean-workspaces]

`--model scripted` (default) replays the scripted steps in the scenario files: an offline, CI-safe smoke of
the runner, harness plumbing and graders. `--model router` drives the real models through the LiteLLM router
(MODEL_ROUTER_URL, MODEL_ROUTER_KEY). `--judge claude` grades `judge` checks with Claude (ANTHROPIC_API_KEY).
Results: `evals/runs/<run_id>/results.jsonl`, `summary.md`, and the scenario workspaces.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

from mentor_harness.config import now_local

from mentor_evals.graders import validate_check
from mentor_evals.report import summary_markdown, write_jsonl
from mentor_evals.runner import ScenarioRunner
from mentor_evals.spec import EVALS_DIR, Scenario, all_checks, load_personas, load_scenarios, select

RUNS_DIR = EVALS_DIR / "runs"


def _load(args: argparse.Namespace) -> tuple[dict[str, Any], list[Scenario]]:
    today = now_local().date()
    personas = load_personas(today)
    scenarios = load_scenarios(today, personas)
    for s in scenarios:
        for where, spec in all_checks(s):
            try:
                validate_check(spec)
            except (ValueError, KeyError) as exc:
                raise SystemExit(f"{s.path} {where}: {exc}") from exc
    chosen = select(scenarios, suites=args.suite, ids=args.scenario, tags=args.tag)
    return personas, chosen


def _add_filters(p: argparse.ArgumentParser) -> None:
    p.add_argument("--suite", action="append", help="suite name (repeatable)")
    p.add_argument("--scenario", action="append", help="scenario id, * wildcard allowed (repeatable)")
    p.add_argument("--tag", action="append", help="scenario tag, e.g. smoke (repeatable)")


async def _run(args: argparse.Namespace) -> int:
    personas, scenarios = _load(args)
    if not scenarios:
        print("no scenarios selected", file=sys.stderr)
        return 2
    run_id = time.strftime("%Y%m%d-%H%M%S") + f"-{args.model}-{args.judge}"
    out = Path(args.out) if args.out else RUNS_DIR / run_id
    out.mkdir(parents=True, exist_ok=True)

    judge = None
    if args.judge == "claude":
        from mentor_evals.judge import ClaudeJudge

        judge = ClaudeJudge(effort=args.judge_effort)
    router = None
    if args.model == "router":
        from mentor_evals.models import router_model_from_env

        router = router_model_from_env()

    runner = ScenarioRunner(
        model_mode=args.model,
        workspaces_dir=out / "workspaces",
        judge=judge,
        router_model=router,
        keep_workspaces=not args.clean_workspaces,
    )
    sem = asyncio.Semaphore(max(1, args.concurrency))
    started = time.perf_counter()

    async def one(s: Scenario) -> dict[str, Any]:
        async with sem:
            res = await runner.run(s, personas[s.persona])
        row = res.to_dict(run_id, args.judge)
        status = "PASS" if row["passed"] else "FAIL"
        print(f"{status:4} {s.suite:9} {s.id} ({row['duration_s']}s)", flush=True)
        return row

    try:
        rows = await asyncio.gather(*(one(s) for s in scenarios))
    finally:
        if router is not None:
            await router.aclose()
        if judge is not None:
            await judge.aclose()
    meta: dict[str, Any] = {
        "run_id": run_id,
        "model": args.model,
        "judge": args.judge,
        "duration_s": time.perf_counter() - started,
    }
    if args.model == "scripted":
        meta["note"] = "scripted = replayed ideal-mentor steps: checks plumbing and graders, not model quality."
    if judge is not None:
        meta["judge_usage"] = {"calls": judge.calls, "input_tokens": judge.input_tokens,
                               "output_tokens": judge.output_tokens}  # fmt: skip
    write_jsonl(out / "results.jsonl", rows)
    summary = summary_markdown(rows, meta)
    (out / "summary.md").write_text(summary, encoding="utf-8", newline="\n")
    (out / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n{sum(r['passed'] for r in rows)}/{len(rows)} passed · {out.as_posix()}/summary.md")
    return 0 if all(r["passed"] for r in rows) else 1


def main(argv: list[str] | None = None) -> None:
    for stream in (sys.stdout, sys.stderr):  # Vietnamese output on Windows consoles
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="mentor-evals", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("list", "validate"):
        _add_filters(sub.add_parser(name))
    run = sub.add_parser("run")
    _add_filters(run)
    run.add_argument("--model", choices=["scripted", "router"], default="scripted")
    run.add_argument("--judge", choices=["none", "claude"], default="none")
    run.add_argument("--judge-effort", choices=["low", "medium", "high", "xhigh", "max"], default="medium")
    run.add_argument("--concurrency", type=int, default=1)
    run.add_argument("--out", help="output directory (default evals/runs/<run_id>)")
    run.add_argument("--clean-workspaces", action="store_true", help="delete workspaces of passing scenarios")
    args = parser.parse_args(argv)

    if args.command == "run":
        raise SystemExit(asyncio.run(_run(args)))
    _, scenarios = _load(args)
    if args.command == "validate":
        print(f"ok: {len(scenarios)} scenarios")
        return
    for s in scenarios:
        print(f"{s.suite:9} {s.id:40} {s.persona:18} {','.join(s.tags)}")


if __name__ == "__main__":
    main()
