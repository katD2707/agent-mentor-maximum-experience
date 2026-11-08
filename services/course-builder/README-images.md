# Picture sources (covers, illustrations, object pictures)

`illustrate.make_image` asks `picture_chain.try_raster_sources` first. Order of decision:

1. **Code-drawn SVG stays first where accuracy matters**: `diagram`, any request with `spec.math`, a `picture` with
   `spec.count`, and covers/illustrations whose subject is physics or statistics. No raster source runs for these
   (override per request with `spec["source"] = "gen" | "web" | "auto"`; force SVG with `"code"`).
2. Otherwise: **image-generation API** (first configured one that works) -> **web image search** (licence-filtered) ->
   **code-drawn SVG** as the last resort.
3. Every candidate is scored by the vision model (`mentor-vision`) against what the lesson needs (objects and counts,
   nothing scary or wrong, age fit, no text/watermark). Below `IMAGE_MIN_SCORE` the generator is retried once with the
   defects in the prompt, then the next source runs. A web image that the critic did not approve is never used.
4. The winner is stored as WebP (`<= IMAGE_MAX_BYTES`, sha256 in `MediaResult.meta` and `sources/<id>/image.json`).
   Web images carry `meta.attribution = {provider, title, author, license, license_url, source_url}` so the app can show
   a credit.
5. Revise with a point comment (`MediaRequest.revise` with `x`,`y`): a raster picture is regenerated with the teacher's
   comment (and "top/middle/bottom, left/centre/right") added to the prompt. SVG pictures are edited as before.

Any failure (no key, no network, quota, bad file) is logged into `MediaResult.notes` and the chain moves on; the worst
case is the old code-drawn SVG. A provider that answers "no quota"/401/402 is skipped for the rest of the process.

## Environment variables (process env, else `.env.dev.local`)

| Variable | Meaning |
| --- | --- |
| `IMAGE_SOURCES` | `auto` (default) = every configured generator, then every available web source, then code. `code`/`svg`/`off` = never leave code-drawn. Or a list, e.g. `cloudflare,openverse,code` (ids below; sources after `code` are never reached; `code,...` = SVG only). |
| `IMAGE_API_BASE`, `IMAGE_API_KEY`, `IMAGE_API_MODEL` | Self-hosted or any OpenAI-compatible `/images/generations` (base includes `/v1`). Source id `openai`. |
| `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `IMAGE_CF_MODEL` | Workers AI, default `@cf/black-forest-labs/flux-1-schnell`. Source id `cloudflare`. Free 10,000 neurons/day, no card. |
| `GEMINI_API_KEY`, `IMAGE_GEMINI_ENABLE=1`, `IMAGE_GEMINI_MODEL` | Gemini image (default `gemini-2.5-flash-image`). Billed key only: free-tier quota is 0. Source id `gemini`. |
| `POLLINATIONS_API_KEY` (or `IMAGE_POLLINATIONS_ANON=1`) | Pollinations. Anonymous mode is unreliable and watermarked; off by default. Source id `pollinations`. |
| `HF_SPACE_URL`, `HF_TOKEN` | Keyless FLUX.1-schnell Hugging Face Space (default URL built in; shared GPU quota; `HF_TOKEN` of a free account raises it). Source id `hf_space`. |
| `PEXELS_API_KEY`, `PIXABAY_API_KEY` | Stock photo APIs (free keys). Ids `pexels`, `pixabay`. |
| (none) | `openverse` and `wikimedia` need no key. |
| `IMAGE_WEB_LICENSES` | Allowed licences for Openverse/Wikimedia, default `cc0,pdm,by,by-sa` (NC/ND are never used). |
| `IMAGE_MIN_SCORE` (7), `IMAGE_MAX_CRITIQUES` (6 per picture), `IMAGE_GEN_TRIES` (2 per generator), `IMAGE_WEB_CANDIDATES` (4 per web source) | Review thresholds and budgets. |
| `IMAGE_MAX_BYTES` (400000), `IMAGE_HTTP_TIMEOUT` (60), `IMAGE_USER_AGENT` | Stored size cap, HTTP timeout, User-Agent. Wikimedia answers 403 to anonymous User-Agents: set `IMAGE_USER_AGENT` to `name/version (https://your-site; contact-email)`. |

Unit tests pin `IMAGE_SOURCES=code` (see `tests/conftest.py`), so nothing reaches the network. Live test:
`MENTOR_LIVE_BUILDER=1 pytest -m live tests/test_picture_chain.py`.
