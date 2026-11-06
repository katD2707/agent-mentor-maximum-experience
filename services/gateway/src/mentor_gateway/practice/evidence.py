"""Writing a finished session's evidence into the learner's workspace mirror (CONTRACTS 10.2).

One mirror commit (author `system`) carries: the new `events.jsonl` lines (one `LearningEvent` per answered item and
skill id, validated with `mentor_schemas.LearningEvent`), the recomputed `learning/<subject>/skills.md` and
`review-queue.md` (bytes produced by `bkt_update`'s own code, see `mastery.py`) and one line of
`learning/<subject>/practice-log.md`, which the mentor reads.

Safety: the whole read-modify-write runs under the learner's `UserLocks` lock, which `WorkspaceSync.push` also takes,
so a sandbox push cannot land in between; `commit_files` additionally compare-and-swaps the `events.jsonl` blob and the
ref, and on a conflict (or a push from outside the lock) the whole step is redone from a fresh read. Event ids are
deterministic (`practice-<session>-<position>-<skill>`), so repeating the step never duplicates evidence.
"""

import json
import logging
from datetime import date, datetime
from pathlib import Path

from mentor_schemas import EvidenceMode, LearningEvent, WorkspacePaths
from mentor_scripts.bkt_update import SkillState

from mentor_gateway.gitrepo import GitError
from mentor_gateway.mirror import Mirror, StaleBaseError
from mentor_gateway.practice import mastery as bkt

log = logging.getLogger(__name__)

ATTEMPTS = 5


def make_events(session_id: str, subject: str, rows: list[dict], ts: datetime) -> list[LearningEvent]:
    """`rows`: {position, skill_ids, correct, hints}. Hint-free answers are `independent` (they move mastery), answers
    after a hint are `guided` (process only), exactly as `bkt_update` reads them."""
    events = []
    for r in rows:
        for sid in dict.fromkeys(r["skill_ids"]):
            events.append(LearningEvent(
                event_id=f"practice-{session_id}-{r['position']}-{sid}", ts=ts, type="practice_item", subject=subject,
                skill_ids=[sid], correct=bool(r["correct"]),
                mode=EvidenceMode.GUIDED if r["hints"] else EvidenceMode.INDEPENDENT, hint_count=int(r["hints"]),
                source_ref=f"practice:{session_id}", grader="bank"))  # type: ignore[arg-type]
    return events


def _read_text(mirror: Mirror, user_id: str, path: str) -> tuple[str, str | None]:
    got = mirror.read(user_id, path)
    return ("", None) if got is None else (got[0].decode("utf-8", "replace"), got[1])


def commit_session_evidence(
    mirror: Mirror, user_id: str, subject: str, session_id: str, events: list[LearningEvent], today: date,
    log_line: str, curriculum_file: Path | None,
) -> tuple[dict[str, SkillState], dict[str, SkillState]]:
    """Append `events`, recompute mastery and commit. Returns (states before, states after) for this subject."""
    last: Exception | None = None
    for _ in range(ATTEMPTS):
        try:
            with mirror.locks.get(user_id):
                return _attempt(mirror, user_id, subject, session_id, events, today, log_line, curriculum_file)
        except (StaleBaseError, GitError) as exc:
            last = exc
            log.info("practice evidence for %s raced with another commit; retrying", user_id)
    raise RuntimeError(f"could not commit practice evidence for {user_id}") from last


def _attempt(mirror: Mirror, user_id: str, subject: str, session_id: str, events: list[LearningEvent], today: date,
             log_line: str, curriculum_file: Path | None):
    events_path = WorkspacePaths.EVENTS
    old_text, events_sha = _read_text(mirror, user_id, events_path)
    curriculum_text = curriculum_file.read_text(encoding="utf-8") if curriculum_file and curriculum_file.exists() else \
        _read_text(mirror, user_id, f"{WorkspacePaths.CURRICULA_DIR}/{subject}.yaml")[0] or None
    before = bkt.skill_states(old_text, subject, curriculum_text)

    known = {_event_id(line) for line in old_text.splitlines()}
    fresh = [e for e in events if e.event_id not in known]
    new_text = old_text
    if fresh:
        if new_text and not new_text.endswith("\n"):
            new_text += "\n"
        new_text += "".join(e.model_dump_json() + "\n" for e in fresh)
    after, skills_md, review_md = bkt.recompute(new_text, subject, curriculum_text, today)

    base = f"{WorkspacePaths.LEARNING_DIR}/{subject}"
    log_path = f"{base}/practice-log.md"
    log_text, log_sha = _read_text(mirror, user_id, log_path)
    changes: dict[str, bytes | None] = {f"{base}/skills.md": skills_md.encode(), f"{base}/review-queue.md": review_md.encode()}
    if fresh:
        changes[events_path] = new_text.encode()
    if f"session {session_id}" not in log_text:
        if not log_text:
            log_text = f"# Nhật ký luyện tập — {subject}\n\nMỗi dòng là một buổi luyện tập hoặc thi thử đã kết thúc (tự động ghi).\n\n"
        elif not log_text.endswith("\n"):
            log_text += "\n"
        changes[log_path] = (log_text + log_line + "\n").encode()
    mirror.commit_files(user_id, changes, author="system", message=f"Luyện tập: {session_id} ({len(fresh)} bằng chứng)",
                        expected={events_path: events_sha, log_path: log_sha})
    return before, after


def _event_id(line: str) -> str | None:
    try:
        return json.loads(line).get("event_id")
    except (ValueError, AttributeError):
        return None
