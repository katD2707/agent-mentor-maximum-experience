"""`mcb intake <files...> --out <dir>`, `mcb outline <intake-dir>`, `mcb build <intake-dir> --outline <json> --out <dir>`."""

import argparse
import logging
import sys
from pathlib import Path

from mentor_course_builder.intake import IntakeOptions, intake, write_outputs
from mentor_course_builder.llm import ModelClient, ModelError


def _client() -> ModelClient | None:
    try:
        return ModelClient.from_env()
    except ModelError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None


def _job(args) -> int:
    import json
    import traceback

    from mentor_course_builder.workflow import JobError, _write_json, run_job

    def factory() -> ModelClient | None:
        try:
            return ModelClient.from_env()
        except ModelError as exc:
            print(f"warning: {exc}", file=sys.stderr)
            return None

    try:
        result = run_job(args.kind, Path(args.dir), json.loads(Path(args.args).read_text("utf-8")), factory)
        _write_json(Path(args.result), result)
        return 0
    except JobError as exc:
        err = str(exc)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        err = f"{type(exc).__name__}: {str(exc)[:300]}"
    _write_json(Path(args.result), {"ok": False, "error": err})
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mcb")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("intake", help="split teacher files into pages, check quality, extract text")
    p.add_argument("files", nargs="+")
    p.add_argument("--out", required=True, help="output directory")
    p.add_argument("--no-model", action="store_true", help="deterministic checks only (no OCR, no transcription)")
    p.add_argument("--keyframe-every", type=float, default=30.0, help="video: max seconds between keyframes")
    p.add_argument("--workers", type=int, default=3)

    o = sub.add_parser("outline", help="propose the course outline (chapters -> lessons) from an intake directory")
    o.add_argument("intake_dir")
    o.add_argument("--note", default=None, help="teacher's note, e.g. 'Cho lớp 11A2'")
    o.add_argument("--out", default=None, help="outline.json path (default <intake_dir>/outline.json)")
    o.add_argument("--instruction", default=None, help="free-text edit to apply to an existing outline (--from)")
    o.add_argument("--from", dest="src", default=None, help="existing outline.json to revise with --instruction")

    b = sub.add_parser("build", help="write lessons, quizzes, humanize, verify, assemble a draft course")
    b.add_argument("intake_dir")
    b.add_argument("--outline", required=True, help="outline.json")
    b.add_argument("--out", required=True, help="output directory (pack.json, course.json, report.json, ...)")
    b.add_argument("--store", default=None, help="courses root of the gateway ContentStore: also write a review version")
    b.add_argument("--lessons", default=None, help="comma-separated lesson ids (default: all)")
    b.add_argument("--no-deeptutor", action="store_true", help="own prompts only (no DeepTutor sidecar)")
    b.add_argument("--quiz-items", type=int, default=None)
    b.add_argument("--workers", type=int, default=2)
    j = sub.add_parser("job", help="teacher-flow stage run by the gateway (workflow.py): state is JSON under --dir")
    j.add_argument("kind")
    j.add_argument("--dir", required=True, help="builder directory of the course")
    j.add_argument("--args", required=True, help="JSON file with the stage arguments")
    j.add_argument("--result", required=True, help="JSON file to write the stage result to")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    if args.cmd == "job":
        return _job(args)
    if args.cmd == "intake":
        client = None
        if not args.no_model:
            client = _client()
            if client is None:
                return 2
        opts = IntakeOptions(keyframe_every_s=args.keyframe_every, workers=args.workers, ocr=client is not None)
        result = intake(args.files, args.out, client=client, options=opts)
        write_outputs(result, args.out)
        print(result.summary())
        return 0 if not result.retake else 1

    from mentor_course_builder.gen import load_intake
    from mentor_course_builder.outline import CourseOutline, build_outline, outline_to_json, revise_outline

    client = _client()
    if client is None:
        return 2
    if args.cmd == "outline":
        out = Path(args.out or Path(args.intake_dir) / "outline.json")
        if args.instruction:
            cur = CourseOutline.model_validate_json(Path(args.src or out).read_text("utf-8"))
            new, note = revise_outline(cur, args.instruction, client)
            print(note)
        else:
            new = build_outline(load_intake(args.intake_dir), client, teacher_note=args.note)
        out.write_text(outline_to_json(new), encoding="utf-8")
        print(new.listing())
        print(f"-> {out}")
        return 0

    from mentor_course_builder.assemble import write_to_dir, write_to_store
    from mentor_course_builder.deeptutor import DeepTutor
    from mentor_course_builder.pipeline import build_course, save_build

    outline = CourseOutline.model_validate_json(Path(args.outline).read_text("utf-8"))
    dt = None if args.no_deeptutor else DeepTutor.from_env()
    res = build_course(load_intake(args.intake_dir), outline, client, dt=dt,
                       only_lessons=args.lessons.split(",") if args.lessons else None, quiz_items=args.quiz_items,
                       workers=args.workers, log_fn=print)
    out = Path(args.out)
    write_to_dir(res.assembled, out)
    save_build(res, out)
    for n in res.notes + res.assembled.notes:
        print("note:", n)
    if args.store:
        extra = [d.lesson.id for d in res.drafts if not d.grounded]
        note = "draft by course-builder" + (f"; written from general knowledge: {', '.join(extra)}" if extra else "")
        v = write_to_store(res.assembled, Path(args.store), note=note)
        print(f"store: {outline.course_id} v{v} (review)")
    print(f"-> {out}")
    return 0 if all(r.error is None for r in res.reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
