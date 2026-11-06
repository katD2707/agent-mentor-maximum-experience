"""Create a learner's workspace from mentor-content (CONTRACTS.md section 1).

Copies `workspace-templates/<profile>/` to the root, `AGENTS.md`, `skills/{core,<profile>}/` to
`.mentor/skills/`, `curricula/` to `.mentor/curricula/` (THPT), then `git init` and a first commit
authored `system <system@local>`, pushed to a new mirror. Missing content is logged and skipped so
the gateway still works while mentor-content is being written.

`refresh_content` brings an existing workspace's platform-managed files (AGENTS.md, `.mentor/skills/`,
`.mentor/curricula/`) up to the current mentor-content in one mirror commit; learner files are never touched.
"""

import hashlib
import logging
import shutil
from pathlib import Path

from mentor_schemas import Profile, Routine, RoutinesFile, WorkspacePaths

from mentor_gateway.mirror import Mirror, WorkspaceSync, _rmtree

log = logging.getLogger(__name__)

_TEXT_SUFFIXES = {".md", ".yaml", ".yml", ".txt"}


def default_routines(profile: Profile) -> RoutinesFile:
    routines = [
        Routine(id="nightly_reflection", cron="30 23 * * *", job_kind="nightly_reflection", user_editable=False),
        Routine(id="evening_review", cron="0 20 * * *", job_kind="routine",
                prompt="Nhắc nhẹ việc ôn tập hôm nay nếu có mục đến hạn."),
    ]
    if profile is Profile.THPT:
        routines.append(Routine(id="parent_report", cron="0 19 1,15 * *", job_kind="parent_report", user_editable=False))
    else:
        routines.append(Routine(id="literature_watch", cron="0 8 * * 1", job_kind="literature_watch"))
    return RoutinesFile(routines=routines)


def _copy_tree(src: Path, dst: Path, what: str, warnings: list[str]) -> None:
    if not src.is_dir():
        warnings.append(f"missing {what}: {src}")
        log.warning("provisioning: missing %s at %s", what, src)
        return
    shutil.copytree(src, dst, dirs_exist_ok=True)


def _fill_placeholders(root: Path, values: dict[str, str]) -> None:
    for f in root.rglob("*"):
        if not f.is_file() or f.suffix not in _TEXT_SUFFIXES or ".git" in f.parts:
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        new = text
        for key, value in values.items():
            new = new.replace("{{" + key + "}}", value)
        if new != text:
            f.write_text(new, encoding="utf-8", newline="\n")


def provision_workspace(
    content_dir: Path,
    sync: WorkspaceSync,
    user_id: str,
    profile: Profile,
    display_name: str,
    language: str,
) -> list[str]:
    """Build and commit the workspace; returns warnings about missing content."""
    warnings: list[str] = []
    wd = sync.path(user_id)
    if wd.exists():
        _rmtree(wd)
    wd.mkdir(parents=True)

    _copy_tree(content_dir / "workspace-templates" / profile.value, wd, f"workspace template '{profile.value}'", warnings)
    agents = content_dir / "AGENTS.md"
    if agents.is_file():
        shutil.copy2(agents, wd / WorkspacePaths.AGENTS_MD)
    else:
        warnings.append(f"missing AGENTS.md: {agents}")
        log.warning("provisioning: missing %s", agents)
    for group in ("core", profile.value):
        _copy_tree(content_dir / "skills" / group, wd / WorkspacePaths.SKILLS_DIR / group, f"skills '{group}'", warnings)
    if profile is Profile.THPT:
        _copy_tree(content_dir / "curricula", wd / WorkspacePaths.CURRICULA_DIR, "curricula", warnings)

    routines = wd / WorkspacePaths.ROUTINES
    if not routines.is_file():
        warnings.append("template has no routines.yaml; wrote defaults")
        routines.write_text(default_routines(profile).to_yaml(), encoding="utf-8", newline="\n")
    for d in (WorkspacePaths.INBOX_DIR, WorkspacePaths.MENTOR_DIR):
        (wd / d).mkdir(parents=True, exist_ok=True)
    activity = wd / WorkspacePaths.ACTIVITY
    if not activity.exists():
        activity.write_text("", encoding="utf-8")
    keep = wd / WorkspacePaths.INBOX_DIR / ".gitkeep"
    if not any((wd / WorkspacePaths.INBOX_DIR).iterdir()):
        keep.write_text("", encoding="utf-8")

    _fill_placeholders(wd, {"display_name": display_name, "language": language, "profile": profile.value})
    sync.init_from_dir(user_id)
    return warnings


def _platform_files(content_dir: Path, profile: Profile) -> dict[str, bytes]:
    """Workspace path -> bytes of every platform-managed file mentor-content has for this profile."""
    files: dict[str, bytes] = {}
    agents = content_dir / "AGENTS.md"
    if agents.is_file():
        files[WorkspacePaths.AGENTS_MD] = agents.read_bytes()
    trees = [(content_dir / "skills" / g, f"{WorkspacePaths.SKILLS_DIR}/{g}") for g in ("core", profile.value)]
    if profile is Profile.THPT:
        trees.append((content_dir / "curricula", WorkspacePaths.CURRICULA_DIR))
    for src, dst in trees:
        for f in sorted(src.rglob("*")) if src.is_dir() else []:
            if f.is_file() and "__pycache__" not in f.parts:
                files[f"{dst}/{f.relative_to(src).as_posix()}"] = f.read_bytes()
    return files


def _blob_sha(data: bytes) -> str:
    """The id git gives these bytes as a blob, to compare with `ls-tree` without reading the mirror."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest()


def refresh_content(content_dir: Path, mirror: Mirror, user_id: str, profile: Profile) -> list[str]:
    """Commit changed/new/removed platform files to the learner's mirror; returns the changed paths.

    Runs while the learner may be online: it is an ordinary `system` commit on `main`, the same path a web
    edit takes, so the working copy picks it up on its next pull. A skill or curriculum dropped from
    mentor-content is deleted; nothing outside AGENTS.md / `.mentor/skills/` / `.mentor/curricula/` is read.
    """
    if not (content_dir / "AGENTS.md").is_file():
        raise FileNotFoundError(f"no AGENTS.md in {content_dir}; refusing to refresh from incomplete content")
    wanted = _platform_files(content_dir, profile)
    managed = (WorkspacePaths.SKILLS_DIR + "/", WorkspacePaths.CURRICULA_DIR + "/")
    present = {e.path: e.sha for e in mirror.ls_tree(user_id)
               if e.type == "file" and (e.path == WorkspacePaths.AGENTS_MD or e.path.startswith(managed))}
    changes: dict[str, bytes | None] = {
        path: data for path, data in wanted.items() if present.get(path) != _blob_sha(data)
    }
    changes.update({path: None for path in present if path not in wanted})
    if changes:
        mirror.commit_files(user_id, changes, author="system", message="Cập nhật nội dung nền tảng (AGENTS.md, skills)")
    return sorted(changes)
