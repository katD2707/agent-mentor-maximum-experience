"""Hooks around tool calls: schema validation of important files and activity summaries."""

import yaml
from mentor_schemas import RoutinesFile, WorkspacePaths
from pydantic import ValidationError


def _short_validation_error(exc: ValidationError) -> str:
    items = [f"{'.'.join(str(p) for p in e['loc']) or '(gốc)'}: {e['msg']}" for e in exc.errors()[:5]]
    return "; ".join(items)


def validate_write(rel: str, content: str) -> str | None:
    """Return a Vietnamese error if `content` is not valid for `rel`, else None."""
    if rel == WorkspacePaths.ROUTINES:
        try:
            RoutinesFile.parse_yaml(content)
        except yaml.YAMLError as exc:
            return f"routines.yaml không phải YAML hợp lệ: {exc}"
        except ValidationError as exc:
            return f"routines.yaml sai cấu trúc RoutinesFile: {_short_validation_error(exc)}"
    return None


def write_summary(rel: str, created: bool) -> str:
    return f"Mentor đã {'tạo' if created else 'cập nhật'} {rel}."


def edit_summary(rel: str) -> str:
    return f"Mentor đã sửa {rel}."


def delete_summary(rel: str) -> str:
    # Never repeat the deleted content (plan 6.3: record *that* it was deleted, not what).
    return f"Mentor đã xóa {rel}."


def move_summary(src: str, dst: str) -> str:
    return f"Mentor đã chuyển {src} sang {dst}."
