"""Course content store (layout in mentor_schemas.course). The course builder (P3) and the API both go through here.

    <root>/catalog.json                  published courses only, latest version of each (regenerated on publish)
    <root>/<course_id>/course.json       CourseMeta
    <root>/<course_id>/<cover>           cover image (CourseMeta.cover)
    <root>/<course_id>/v<N>/pack.json    CoursePack
    <root>/<course_id>/v<N>/assets/...   files referenced by the pack
    <root>/<course_id>/v<N>/sources/...  server-only teacher material (never served)

Writes are atomic (temp file + os.replace). A published version is immutable: `write_pack` and `set_status` refuse it
and `publish` is not repeatable. The directory name is the course id.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import threading
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from mentor_schemas.course import (
    AssetRef,
    AudioBlock,
    Catalog,
    CatalogEntry,
    CourseMeta,
    CoursePack,
    QuizBlock,
    TextBlock,
    VersionInfo,
    VideoBlock,
)


class ContentError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class NotFound(ContentError):
    pass


class Immutable(ContentError):
    pass


class ComingSoon(ContentError):
    """The course is a placeholder (CourseMeta.status "coming_soon"): overview only, no pack, no enrollment."""

    def __init__(self, message: str = "this course is coming soon") -> None:
        super().__init__("coming_soon", message)


AssetSource = bytes | Path  # bytes, or a file to copy


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _json_bytes(model) -> bytes:
    return (model.model_dump_json(indent=2) + "\n").encode("utf-8")


def asset_ref_for(path: str, source: AssetSource, mime: str | None = None) -> AssetRef:
    """AssetRef for a file about to be passed to `write_pack` (helper for builders and seed scripts)."""
    data = source if isinstance(source, bytes) else Path(source).read_bytes()
    guessed = {".vtt": "text/vtt", ".webp": "image/webp"}.get(Path(path).suffix.lower()) or mimetypes.guess_type(path)[0]
    return AssetRef(path=path, mime=mime or guessed or "application/octet-stream", sha256=sha256_bytes(data),
                    bytes=len(data))


def derive_media(pack: CoursePack) -> list[str]:
    has = dict.fromkeys(("video", "reading", "audio", "quiz", "interactive"), False)
    for ch in pack.chapters:
        for ls in ch.lessons:
            for b in ls.blocks:
                if isinstance(b, VideoBlock):
                    has["video"] = True
                elif isinstance(b, TextBlock):
                    has["reading"] = True
                elif isinstance(b, AudioBlock):
                    has["audio"] = True
                elif isinstance(b, QuizBlock):
                    has["quiz"] = True
                    if any(q.type in ("TAP_COUNT", "PICTURE_CHOICE") for q in b.items):
                        has["interactive"] = True
    return [k for k, v in has.items() if v]


def block_ids(pack: CoursePack) -> list[str]:
    return [b.id for ch in pack.chapters for ls in ch.lessons for b in ls.blocks]


class ContentStore:
    def __init__(self, root: Path, clock=None) -> None:
        self.root = Path(root)
        self.clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.RLock()

    # ------------------------------------------------------------ paths
    def course_dir(self, course_id: str) -> Path:
        # ids come from URLs: reject anything that is not a plain directory name
        if not course_id or "/" in course_id or "\\" in course_id or course_id.startswith(".") or ".." in course_id:
            raise NotFound("course_not_found")
        p = self.root / course_id
        if not (p / "course.json").is_file():
            raise NotFound("course_not_found")
        return p

    def version_dir(self, course_id: str, version: int) -> Path:
        return self.course_dir(course_id) / f"v{int(version)}"

    def pack_path(self, course_id: str, version: int) -> Path:
        return self.version_dir(course_id, version) / "pack.json"

    @property
    def catalog_path(self) -> Path:
        return self.root / "catalog.json"

    # ------------------------------------------------------------ read
    def list_course_ids(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return [d.name for d in sorted(self.root.iterdir())
                if d.is_dir() and not d.name.startswith(".") and (d / "course.json").is_file()]

    def load_meta(self, course_id: str) -> CourseMeta:
        return CourseMeta.model_validate_json((self.course_dir(course_id) / "course.json").read_text("utf-8"))

    def list_courses(self) -> list[CourseMeta]:
        return [self.load_meta(i) for i in self.list_course_ids()]

    @staticmethod
    def version_info(meta: CourseMeta, version: int) -> VersionInfo:
        for v in meta.versions:
            if v.version == version:
                return v
        raise NotFound("version_not_found")

    def load_pack(self, course_id: str, version: int) -> CoursePack:
        return CoursePack.model_validate_json(self.pack_bytes_raw(course_id, version))

    def pack_bytes_raw(self, course_id: str, version: int) -> bytes:
        p = self.pack_path(course_id, version)
        if not p.is_file():
            raise NotFound("pack_not_found")
        return p.read_bytes()

    def asset_path(self, course_id: str, version: int, rel: str) -> Path:
        base = (self.version_dir(course_id, version) / "assets").resolve()
        target = (base / rel).resolve()
        if base not in target.parents or not target.is_file():
            raise NotFound("asset_not_found")
        return target

    def cover_path(self, course_id: str) -> Path:
        meta = self.load_meta(course_id)
        d = self.course_dir(course_id).resolve()
        target = (d / meta.cover).resolve()
        if d not in target.parents or not target.is_file():
            raise NotFound("cover_not_found")
        return target

    def load_catalog(self) -> Catalog:
        return Catalog.model_validate_json(self.catalog_bytes())

    def catalog_bytes(self) -> bytes:
        if not self.catalog_path.is_file():
            self.regenerate_catalog()
        return self.catalog_path.read_bytes()

    # ------------------------------------------------------------ write
    def _save_meta(self, meta: CourseMeta) -> None:
        atomic_write(self.course_dir(meta.id) / "course.json", _json_bytes(meta))

    def create_draft(self, meta: CourseMeta, note: str | None = None) -> int:
        """New course: writes course.json (version history reset) and returns 1. Existing course: refreshes the
        descriptive fields from `meta` (never the version history) and returns the next version number (a new draft)."""
        with self._lock:
            d = self.root / meta.id
            if (d / "course.json").is_file():
                cur = self.load_meta(meta.id)
                version = max((v.version for v in cur.versions), default=0) + 1
                new = meta.model_copy(update={"versions": list(cur.versions), "latest_published": cur.latest_published,
                                              "lessons_count": cur.lessons_count, "est_minutes": cur.est_minutes,
                                              "media": cur.media, "level": cur.level})
            else:
                version = 1
                new = meta.model_copy(update={"versions": [], "latest_published": None})
            new.versions.append(VersionInfo(version=version, status="draft", created_at=self.clock(), note=note))
            atomic_write(d / "course.json", _json_bytes(new))
            (d / f"v{version}" / "assets").mkdir(parents=True, exist_ok=True)
            return version

    def refresh_meta(self, meta: CourseMeta) -> None:
        """Rebuilding an unpublished draft: refresh the descriptive fields (title, subject, description, ...) from `meta`,
        keeping the version history, counters and `media` as they are."""
        with self._lock:
            cur = self.load_meta(meta.id)
            new = meta.model_copy(update={"versions": list(cur.versions), "latest_published": cur.latest_published,
                                          "lessons_count": cur.lessons_count, "est_minutes": cur.est_minutes,
                                          "media": cur.media, "level": cur.level})
            self._save_meta(new)

    def set_level(self, course_id: str, version: int, *, suggested: str | None = None,
                  confirmed: str | None = None, inherit: bool = False) -> VersionInfo:
        """Course difficulty of a draft version. `suggested` is the builder's guess (it never overwrites a confirmed
        level); `confirmed` is the teacher's choice. `inherit` copies both from the latest published version (a new
        draft of a published course starts with the level students already see). A published version is frozen."""
        with self._lock:
            meta = self.load_meta(course_id)
            info = self.version_info(meta, version)
            if info.status == "published":
                raise Immutable("version_published", f"{course_id} v{version} is published")
            if inherit and meta.latest_published is not None:
                src = self.version_info(meta, meta.latest_published)
                info.level_suggested = src.level_suggested
                info.level_confirmed = src.level_confirmed or meta.level
            if suggested is not None:
                info.level_suggested = suggested  # type: ignore[assignment]
            if confirmed is not None:
                info.level_confirmed = confirmed  # type: ignore[assignment]
            self._save_meta(meta)
            return info

    def set_status(self, course_id: str, version: int, status: str) -> None:
        """draft <-> review. `published` is only reachable through `publish`."""
        if status not in ("draft", "review"):
            raise ContentError("bad_status")
        with self._lock:
            meta = self.load_meta(course_id)
            info = self.version_info(meta, version)
            if info.status == "published":
                raise Immutable("version_published")
            info.status = status  # type: ignore[assignment]
            self._save_meta(meta)

    def write_pack(self, course_id: str, version: int, pack: CoursePack,
                   assets: Mapping[str, AssetSource] | None = None) -> None:
        """Writes pack.json and `assets` (path relative to assets/ -> bytes or a file to copy). Refuses a published
        version. May be called repeatedly while the version is a draft; asset files are added or replaced."""
        with self._lock:
            meta = self.load_meta(course_id)
            if self.version_info(meta, version).status == "published":
                raise Immutable("version_published", f"{course_id} v{version} is published")
            pack = CoursePack.model_validate(pack.model_dump())  # re-validate
            if pack.course_id != course_id or pack.version != version:
                raise ContentError("pack_mismatch", "pack.course_id/version differ from the target")
            base = (self.version_dir(course_id, version) / "assets").resolve()
            for rel, src in (assets or {}).items():
                target = (base / rel).resolve()
                if base not in target.parents:
                    raise ContentError("bad_asset_path", rel)
                atomic_write(target, src if isinstance(src, bytes) else Path(src).read_bytes())
            atomic_write(self.pack_path(course_id, version), _json_bytes(pack))

    def _verify_assets(self, course_id: str, version: int, pack: CoursePack) -> int:
        sizes: dict[str, int] = {}
        for ref in pack.assets():
            p = self.asset_path(course_id, version, ref.path)
            if p.stat().st_size != ref.bytes or sha256_file(p) != ref.sha256:
                raise ContentError("asset_mismatch", f"{ref.path}: size or sha256 differs from the pack")
            sizes[ref.path] = ref.bytes
        return sum(sizes.values())

    def publish(self, course_id: str, version: int, note: str | None = None) -> VersionInfo:
        """Validates pack + assets (existence, size, sha256, cover), freezes the version (pack_sha256, pack_bytes =
        pack.json + assets, published_at), refreshes course.json and regenerates catalog.json."""
        with self._lock:
            meta = self.load_meta(course_id)
            info = self.version_info(meta, version)
            if info.status == "published":
                raise Immutable("version_published")
            pack = self.load_pack(course_id, version)
            if pack.course_id != course_id or pack.version != version:
                raise ContentError("pack_mismatch")
            asset_bytes = self._verify_assets(course_id, version, pack)
            self.cover_path(course_id)  # must exist
            raw = self.pack_bytes_raw(course_id, version)
            info.status = "published"
            info.published_at = self.clock()
            info.pack_sha256 = sha256_bytes(raw)
            info.pack_bytes = len(raw) + asset_bytes
            if note is not None:
                info.note = note
            if meta.latest_published is None or version >= meta.latest_published:
                meta.latest_published = version
                meta.lessons_count = sum(len(c.lessons) for c in pack.chapters)
                meta.est_minutes = sum(ls.est_minutes for c in pack.chapters for ls in c.lessons)
                meta.media = derive_media(pack)  # type: ignore[assignment]
                meta.age_band = pack.age_band
                meta.language = pack.language
                meta.level = info.level_confirmed or meta.level
            self._save_meta(meta)
            self.regenerate_catalog()
            return info

    def regenerate_catalog(self) -> Catalog:
        with self._lock:
            entries: list[CatalogEntry] = []
            soon: list[CatalogEntry] = []
            for cid in self.list_course_ids():
                meta = self.load_meta(cid)
                if meta.status == "coming_soon":
                    try:
                        cover_sha = sha256_file(self.cover_path(cid))
                    except NotFound:
                        continue
                    soon.append(CatalogEntry(
                        id=meta.id, title=meta.title, subject=meta.subject, age_band=meta.age_band,
                        language=meta.language, teacher_name=meta.teacher_name, description_short=meta.description_short,
                        outcomes=meta.outcomes, cover_sha256=cover_sha, media=meta.media,
                        lessons_count=sum(len(c.lessons) for c in meta.outline),
                        est_minutes=sum(ls.est_minutes for c in meta.outline for ls in c.lessons), status="coming_soon",
                        level=meta.level))
                    continue
                if meta.latest_published is None:
                    continue
                info = self.version_info(meta, meta.latest_published)
                try:
                    cover_sha = sha256_file(self.cover_path(cid))
                except NotFound:
                    continue
                entries.append(CatalogEntry(
                    id=meta.id, title=meta.title, subject=meta.subject, age_band=meta.age_band, language=meta.language,
                    teacher_name=meta.teacher_name, description_short=meta.description_short, outcomes=meta.outcomes,
                    cover_sha256=cover_sha, media=meta.media, lessons_count=meta.lessons_count,
                    est_minutes=meta.est_minutes, level=meta.level, version=info.version, pack_sha256=info.pack_sha256 or "",
                    pack_bytes=info.pack_bytes or 0, published_at=info.published_at or self.clock()))
            cat = Catalog(generated_at=self.clock(), courses=entries + soon)
            atomic_write(self.catalog_path, _json_bytes(cat))
            return cat
