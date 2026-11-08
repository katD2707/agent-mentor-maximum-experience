"""Picture-source chain for cover / illustration / picture requests (REQUIREMENTS-PLAN: code-drawn skill -> image API -> web).

    result, notes = try_raster_sources(req, out_dir, client)      # result is None -> caller draws the SVG itself

Policy
  * diagrams, and anything where accuracy matters (physics / statistics figures, exact `math`, counted `picture`s), stay
    code-drawn: no raster source is tried unless the request says spec["source"] = "gen" | "web" | "auto".
  * otherwise sources run in the order of picture_sources.source_order(): generators, then web search, then code.
  * every candidate is scored by the vision model against the lesson (objects and counts, nothing scary or wrong, age
    fit, no text or watermark); below IMAGE_MIN_SCORE the next try / next source runs. Web images must be approved.
  * the winner is stored as WebP under the asset rules (<= IMAGE_MAX_BYTES, sha256) with provenance in
    sources/<id>/image.json and MediaResult.meta (author / licence / source URL for credit).
Everything degrades: no key, no network, no quota, no Chrome-free path -> None and the code-drawn SVG is used.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import httpx
from mentor_schemas import ModelAlias

from mentor_course_builder import picture_sources as ps
from mentor_course_builder.contracts import MediaFile, MediaRequest, MediaResult
from mentor_course_builder.jsonparse import parse_model_json
from mentor_course_builder.llm import ModelClient, ModelError, image_part
from mentor_course_builder.media import MediaError

log = logging.getLogger("mentor_course_builder")

# target canvas of the stored file, and the size asked from generators (multiples of 32)
TARGET = {"cover": (1600, 1000), "illustration": (1200, 800), "picture": (400, 400)}
GEN_SIZE = {"cover": (1024, 640), "illustration": (1024, 704), "picture": (768, 768)}
MIN_SIDE = {"cover": 500, "illustration": 500, "picture": 200}
AGE_STYLE = {
    "g1_5": "for children aged 6 to 10: big friendly shapes, bright warm colours, cute and gentle",
    "g6_9": "for pupils aged 11 to 14: clear, lively, slightly more detailed",
    "g10_12": "for teenagers: clean, clear and tasteful",
    "uni": "for adult learners: clean and neutral",
}
STYLE = ("flat vector children's picture-book illustration, simple clean shapes, soft warm colours, plain light background, "
         "no text, no letters, no numbers, no watermark, no logo")

PLAN_PROMPT = """You prepare one picture for a school lesson. Reply JSON only:
{{"prompt": "...", "query": "...", "expected": "..."}}
prompt: ONE English sentence for an image generator describing the scene concretely (subject, action, setting). Do NOT
write digits or number words, the word 'counting', or anything that would be drawn as writing: for a count, say 'a few' or
show the objects. Do not mention style.
query: 2 to 4 English keywords to find a matching free stock photo or illustration.
expected: what a reviewer must see in the picture, including exact counts or colours if the lesson depends on them.
Lesson picture request ({kind}, learner age band {age}): {description}
Course: {title}  Subject: {subject}"""

CRITIQUE_PROMPT = """You review a picture for a school lesson. Lesson need: "{expected}". Learner age band: {age}.
Check: (1) it shows what the lesson needs, with the right number of objects when a count matters; (2) nothing wrong,
scary, violent, sexual, or unsuitable for children; (3) it fits the age band in tone and detail; (4) NO visible text,
letters, digits, logos or watermarks; (5) clean composition, nothing important cut off, not blurry or distorted
(extra limbs, melted faces); {web_clause}
Reply JSON only: {{"ok": true|false, "score": 0-10, "defects": ["short fix instruction", ...]}}.
score 9-10 = perfect for the lesson, 7-8 = good, below 7 = do not use."""

WEB_CLAUSE = "(6) it is not a photo of an identifiable person or a brand, and not a screenshot, patent drawing or diagram."


@dataclass
class Verdict:
    ok: bool
    score: float
    defects: list[str]


def _int(name: str, default: int) -> int:
    try:
        return int(ps.cfg(name) or default)
    except ValueError:
        return default


def accuracy_critical(req: MediaRequest) -> bool:
    """True when a drawn-by-code figure is more trustworthy than an image model."""
    from mentor_course_builder.illustrate import SUBJECT_RECIPES, subject_recipe

    s = req.spec
    if req.kind == "diagram" or s.get("math"):
        return True
    if req.kind == "picture" and s.get("count"):
        return True
    recipe = subject_recipe(f"{s.get('subject', '')} {s.get('title', '')} {s.get('description', '')}")
    return recipe in (SUBJECT_RECIPES["physics"], SUBJECT_RECIPES["statistics"])


def plan_sources(req: MediaRequest) -> list[str]:
    """Raster sources to try for this request, in order; [] means go straight to code-drawn."""
    forced = req.spec.get("source")
    if forced == "code" or req.kind not in TARGET:
        return []
    if accuracy_critical(req) and forced not in ("gen", "web", "auto"):
        return []
    if _code_ahead(forced):
        return []
    out: list[str] = []
    for i in ps.source_order(forced if forced in ("gen", "web") else None):
        if i == "code":  # sources listed after `code` are never reached
            break
        out.append(i)
    return out


def _code_ahead(forced: str | None) -> bool:
    """IMAGE_SOURCES may list `code` first (e.g. "code,openverse"): then SVG is the first choice and rasters never run."""
    order = ps._explicit()
    return bool(order) and order[0] == "code" and forced not in ("gen", "web", "auto")


# ------------------------------------------------------------------------------------------------ planning / review

def _plan(req: MediaRequest, client: ModelClient | None) -> dict:
    s = req.spec
    desc = str(s.get("description") or s.get("idea") or s.get("title") or "")
    fallback = {"prompt": desc, "query": " ".join(desc.split()[:4]), "expected": desc}
    if client is None:
        return fallback
    try:
        raw = client.complete(ModelAlias.CHAT, [{"role": "user", "content": PLAN_PROMPT.format(
            kind=req.kind, age=req.age_band, description=desc, title=s.get("title", ""), subject=s.get("subject", ""))}],
            max_tokens=4000, temperature=0.3)
        data = parse_model_json(raw)
        return {k: str(data.get(k) or fallback[k])[:600] for k in fallback}
    except (ModelError, ValueError, KeyError, AttributeError) as exc:
        log.warning("picture plan skipped: %s", exc)
        return fallback


def build_prompt(plan: dict, req: MediaRequest, extra: str = "") -> str:
    style = AGE_STYLE.get(req.age_band, "")
    parts = [plan["prompt"].rstrip(". "), STYLE, style]
    if extra:
        parts.append(extra)
    return ". ".join(p for p in parts if p)[:1500]


def review(client: ModelClient | None, data: bytes, expected: str, age: str, *, web: bool) -> Verdict | None:
    """Vision score. None when the critic is unavailable (then web images are rejected, generated ones accepted)."""
    if client is None:
        return None
    from PIL import Image

    try:
        with Image.open(BytesIO(data)) as im:
            im = im.convert("RGB")
            im.thumbnail((800, 800))
            buf = BytesIO()
            im.save(buf, "JPEG", quality=85)
        raw = client.complete(ModelAlias.VISION, [{"role": "user", "content": [
            {"type": "text", "text": CRITIQUE_PROMPT.format(expected=expected, age=age, web_clause=WEB_CLAUSE if web else "")},
            image_part(buf.getvalue())]}], max_tokens=2000)
        d = parse_model_json(raw)
        score = float(d.get("score", 10 if d.get("ok") is True else 0))
        return Verdict(bool(d.get("ok")) and score >= _int("IMAGE_MIN_SCORE", 7), score,
                       [str(x)[:200] for x in (d.get("defects") or [])][:6])
    except (ModelError, ValueError, KeyError, TypeError, OSError) as exc:
        log.warning("picture review skipped: %s", exc)
        return None


# ------------------------------------------------------------------------------------------------ storage

def encode_webp(data: bytes, kind: str) -> tuple[bytes, int, int]:
    """Decode, fit to the target canvas, encode WebP under IMAGE_MAX_BYTES. Raises ProviderError for unusable files."""
    from PIL import Image, ImageOps

    tw, th = TARGET[kind]
    try:
        im = Image.open(BytesIO(data))
        if im.width * im.height > 60_000_000:
            raise ps.ProviderError("image has too many pixels")
        im = ImageOps.exif_transpose(im)
        im = im.convert("RGBA")
    except ps.ProviderError:
        raise
    except Exception as exc:  # corrupt / unsupported file
        raise ps.ProviderError(f"cannot decode image: {type(exc).__name__}") from None
    if min(im.size) < MIN_SIDE[kind]:
        raise ps.ProviderError(f"image too small ({im.width}x{im.height})")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    im = Image.alpha_composite(bg, im).convert("RGB")
    if kind == "picture":  # single object: whole image, centred on a square
        im.thumbnail((tw, th))
        canvas = Image.new("RGB", (tw, th), (255, 255, 255))
        canvas.paste(im, ((tw - im.width) // 2, (th - im.height) // 2))
        im = canvas
    else:
        aspect, want = im.width / im.height, tw / th
        if abs(aspect - want) / want > 0.12:  # centre-crop to the page's aspect ratio
            if aspect > want:
                nw = round(im.height * want)
                im = im.crop(((im.width - nw) // 2, 0, (im.width - nw) // 2 + nw, im.height))
            else:
                nh = round(im.width / want)
                im = im.crop((0, (im.height - nh) // 2, im.width, (im.height - nh) // 2 + nh))
        if im.width > tw:
            im = im.resize((tw, round(tw / want)) if abs(aspect - want) / want > 0.12 else (tw, round(tw / aspect)), Image.LANCZOS)
    cap = _int("IMAGE_MAX_BYTES", 400_000)
    for _ in range(4):
        for q in (84, 76, 68, 58, 48):
            out = BytesIO()
            im.save(out, "WEBP", quality=q, method=6)
            if out.tell() <= cap:
                return out.getvalue(), im.width, im.height
        im = im.resize((round(im.width * 0.8), round(im.height * 0.8)), Image.LANCZOS)
    raise ps.ProviderError(f"cannot fit the image under {cap} bytes")


def _licence_ok(c: ps.Candidate) -> bool:
    return c.license in ps.allowed_licenses() or c.license in ("pexels", "pixabay")


def _store(req: MediaRequest, out_dir: Path, webp: bytes, w: int, h: int, meta: dict, notes: list[str]) -> MediaResult:
    rel = f"images/{req.id}.webp"
    dest = out_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(webp)
    meta = {**meta, "sha256": hashlib.sha256(webp).hexdigest(), "bytes": len(webp), "width": w, "height": h}
    src = out_dir / "sources" / req.id
    src.mkdir(parents=True, exist_ok=True)
    (src / "image.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return MediaResult(id=req.id, kind=req.kind, source_dir=src, notes=notes, meta=meta,
                       files=[MediaFile(role="main", path=rel, mime="image/webp", file=dest)])


# ------------------------------------------------------------------------------------------------ the chain

def _gen_loop(gen: ps.Generator, req, plan, http, client, state, notes, extra="") -> tuple[bytes, int, int, dict] | None:
    tries = max(1, _int("IMAGE_GEN_TRIES", 2))
    w, h = GEN_SIZE[req.kind]
    feedback = ""
    for attempt in range(tries):
        if state["critiques"] >= _int("IMAGE_MAX_CRITIQUES", 6):
            notes.append("image: critique budget used up")
            return None
        prompt = build_prompt(plan, req, "; ".join(x for x in (extra, f"avoid: {feedback}" if feedback else "") if x))
        try:
            got = gen.generate(http, prompt, w, h, ps._seed(req.id, gen.name, attempt))
            webp, ow, oh = encode_webp(got.data, req.kind)
        except ps.ProviderError as exc:
            notes.append(f"image: {gen.name} failed: {exc}")
            if exc.fatal:
                ps.trip(gen.name)
            return None
        state["critiques"] += 1
        v = review(client, webp, plan["expected"], req.age_band, web=False)
        info = {"kind": "generated", "provider": gen.name, "model": got.model, "prompt": prompt, "attribution": None}
        if v is None:
            notes.append(f"image: {gen.name} accepted without review (critic unavailable)")
            return webp, ow, oh, info
        info["critique"] = {"score": v.score, "defects": v.defects}
        if v.ok:
            notes.append(f"image: {gen.name} score {v.score:g}")
            return webp, ow, oh, info
        notes.append(f"image: {gen.name} rejected (score {v.score:g}): {'; '.join(v.defects)[:200]}")
        feedback = "; ".join(v.defects)[:300]
    return None


def _web_loop(src: ps.WebSource, req, plan, http, client, state, notes) -> tuple[bytes, int, int, dict] | None:
    try:
        cands = [c for c in src.search(http, plan["query"], _int("IMAGE_WEB_CANDIDATES", 4)) if c.url and _licence_ok(c)]
    except ps.ProviderError as exc:
        notes.append(f"image: {src.name} search failed: {exc}")
        if exc.fatal:
            ps.trip(src.name)
        return None
    if not cands:
        notes.append(f"image: {src.name} found no usable picture for '{plan['query']}'")
        return None
    for c in cands[: _int("IMAGE_WEB_CANDIDATES", 4)]:
        if state["critiques"] >= _int("IMAGE_MAX_CRITIQUES", 6):
            notes.append("image: critique budget used up")
            return None
        try:
            webp, ow, oh = encode_webp(src.fetch(http, c), req.kind)
        except ps.ProviderError as exc:
            notes.append(f"image: {src.name} candidate skipped: {exc}")
            continue
        state["critiques"] += 1
        v = review(client, webp, plan["expected"], req.age_band, web=True)
        if v is not None and v.ok:
            notes.append(f"image: {src.name} '{c.title[:40]}' by {c.author[:40] or 'unknown'} ({c.license}) score {v.score:g}")
            return webp, ow, oh, {"kind": "web", "provider": src.name, "query": plan["query"], "attribution": c.attribution(),
                                  "critique": {"score": v.score, "defects": v.defects}}
        notes.append(f"image: {src.name} candidate rejected" + (f" (score {v.score:g})" if v else " (critic unavailable)"))
    return None


def try_raster_sources(req: MediaRequest, out_dir: Path, client: ModelClient | None, *, http: httpx.Client | None = None,
                       revise_extra: str = "", plan_override: dict | None = None,
                       only_generated: bool = False) -> tuple[MediaResult | None, list[str]]:
    notes: list[str] = []
    order = plan_sources(req)
    if only_generated:
        order = [i for i in order if i in ps.GENERATORS]
    if not order:
        return None, notes
    owned = http is None
    http = http or ps.make_http()
    try:
        plan = plan_override or _plan(req, client)
        plan = {**plan, "expected": plan["expected"] + (f" Also: {revise_extra}" if revise_extra else "")}
        state = {"critiques": 0}
        for sid in order:
            if ps.is_tripped(sid):
                continue
            hit = None
            if sid in ps.GENERATORS:
                hit = _gen_loop(ps.GENERATORS[sid], req, plan, http, client, state, notes, revise_extra)
            elif sid in ps.WEB_SOURCES:
                hit = _web_loop(ps.WEB_SOURCES[sid], req, plan, http, client, state, notes)
            if hit:
                webp, w, h, info = hit
                info.setdefault("plan", plan)
                notes.append(f"illustration: {info['kind']} image via {info['provider']}")
                return _store(req, out_dir, webp, w, h, info, notes), notes
        notes.append("image: no raster source produced an approved picture; code-drawn SVG used")
        return None, notes
    finally:
        if owned:
            http.close()


def _where(x: float | None, y: float | None) -> str:
    if x is None or y is None:
        return ""
    if x > 1 or y > 1:
        return ""
    col = "left" if x < 0.34 else "right" if x > 0.66 else "centre"
    row = "top" if y < 0.34 else "bottom" if y > 0.66 else "middle"
    return f" (at the {row} {col} of the picture)"


def revise_picture(req: MediaRequest, out_dir: Path, client: ModelClient | None, *, http: httpx.Client | None = None
                   ) -> MediaResult | None:
    """Teacher comment on a raster picture: regenerate with the comment added to the prompt. None when the previous
    version was not a raster (caller edits the SVG) or no generator is configured (MediaError is raised in that case)."""
    rev = req.revise or {}
    src_dir = Path(rev["source_dir"]) if rev.get("source_dir") else None
    meta_file = src_dir / "image.json" if src_dir else None
    if not meta_file or not meta_file.is_file():
        return None
    prev = json.loads(meta_file.read_text(encoding="utf-8"))
    plan = dict(prev.get("plan") or {})
    if not plan.get("prompt"):
        return None
    comment = str(rev.get("comment", "")).strip()
    extra = f"IMPORTANT change requested by the teacher{_where(rev.get('x'), rev.get('y'))}: {comment}"
    plan["expected"] = (plan.get("expected") or "") + f" Teacher's change: {comment}"
    spec_req = req.model_copy(update={"spec": {**req.spec, "source": "gen"}})
    res, notes = try_raster_sources(spec_req, out_dir, client, http=http, revise_extra=extra, plan_override=plan,
                                    only_generated=True)
    if res is None:
        raise MediaError("cannot revise a raster picture: no image generator available or approved ("
                         + "; ".join(notes)[-300:] + ")")
    res.notes.insert(0, "revised by regenerating with the teacher's comment in the prompt")
    return res
