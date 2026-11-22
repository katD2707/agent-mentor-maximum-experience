# Paints the village render (lang.py: base.png, ids.png, layout.json) in a hand-painted animated-film style with
# FLUX.2 [klein] 4B (Apache 2.0) on Cloudflare Workers AI, tile by tile at full resolution, then cuts the occluders out of
# the painted picture and writes what the page loads (assets/ga/lang/).
#   python paint_world.py <env_file> <render_dir> <out_dir> [--only-pack]
# Tiles are 1024 px with 128 px of overlap; each painted tile is kept in <render_dir>/painted/ so a rerun only pays for
# missing tiles. Colour: every painted tile is moved by one shared transform (painted look) applied to its own render
# statistics, so neighbours match; overlaps are cross-faded.
import base64, json, os, sys, time, urllib.request, urllib.error
import numpy as np
from PIL import Image, ImageFilter

env, rdir, out = sys.argv[1:4]; ONLY_PACK = "--only-pack" in sys.argv
T, STRIDE = 1024, 896
SKY = np.array([207, 232, 245], np.float32)
PROMPT = ("Repaint this exact picture as a hand-painted background from a classic Japanese hand-drawn animated film: soft gouache "
          "and watercolour brushwork, lush detailed greenery with individual painted leaves and grass, warm gentle afternoon light, "
          "rich but natural colours, painted soft shadows. Keep exactly the same layout: every object in the same place, shape, size "
          "and colour, including small ones (posts, lanterns, baskets, targets, stones, flowers); the same camera. No outlines, no text, "
          "no people, no animals. ")
SKY_LINE = "The plain light blue band at the very top is the sky: keep it plain."
GROUND_LINE = ("There is no sky anywhere in this picture: it is all ground seen from above at an angle. Large pale flat areas are a "
               "sandy village yard and dirt paths: paint them as warm packed earth, never as sky or clouds.")

Image.MAX_IMAGE_PIXELS = None
base = np.asarray(Image.open(os.path.join(rdir, "base.png")).convert("RGBA")).astype(np.float32)
H, W = base.shape[:2]; alpha = base[..., 3] / 255.0
xs = list(range(0, W - T, STRIDE)) + [W - T]; ys = list(range(0, H - T, STRIDE)) + [H - T]
pdir = os.path.join(rdir, "painted"); os.makedirs(pdir, exist_ok=True)

def cf():
    keys = {}
    for line in open(env, encoding="utf-8-sig"):
        if "=" in line and line.strip().startswith("CLOUDFLARE_"):
            k, v = line.split("=", 1); keys[k.strip()] = v.strip()
    tok = keys["CLOUDFLARE_AI_TOKEN"]
    for t in (tok, keys.get("CLOUDFLARE_WORKERS_TOKEN")):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request("https://api.cloudflare.com/client/v4/accounts", headers={"Authorization": "Bearer " + t}), timeout=60))["result"]
            if r: return tok, r[0]["id"]
        except Exception: pass
    sys.exit("cannot find the Cloudflare account id")

def paint_tile(tok, acc, png_bytes, seed=3, sky=False):
    bnd = "----pw7"
    f = lambda n, v: (f"--{bnd}\r\nContent-Disposition: form-data; name=\"{n}\"\r\n\r\n{v}\r\n").encode()
    body = (f("prompt", PROMPT + (SKY_LINE if sky else GROUND_LINE)) + f("width", str(T)) + f("height", str(T)) + f("seed", str(seed))
            + f"--{bnd}\r\nContent-Disposition: form-data; name=\"input_image_0\"; filename=\"t.png\"\r\nContent-Type: image/png\r\n\r\n".encode()
            + png_bytes + f"\r\n--{bnd}--\r\n".encode())
    req = urllib.request.Request(f"https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/@cf/black-forest-labs/flux-2-klein-4b", data=body,
                                 method="POST", headers={"Authorization": "Bearer " + tok, "Content-Type": f"multipart/form-data; boundary={bnd}"})
    for attempt in range(3):
        try:
            raw = urllib.request.urlopen(req, timeout=300).read()
            if raw[:3] != b"\xff\xd8\xff" and raw[:4] != b"\x89PNG": raw = base64.b64decode(json.loads(raw)["result"]["image"])
            return raw
        except urllib.error.HTTPError as e:
            msg = e.read().decode()[:300]
            if e.code == 429 or "quota" in msg.lower() or "neurons" in msg.lower(): sys.exit(f"QUOTA: {e.code} {msg}")
            print("retry", e.code, msg); time.sleep(5)
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:   # dropped connection: wait and try again
            print("retry", e); time.sleep(8)
    sys.exit("tile failed")

# ---------------------------------------------------------------- paint the tiles (cached), check each, repaint the bad ones
def fake_sky(p, ty, tx):
    """Share of the tile painted sky-blue where the render is neither sky nor water: the model took a pale yard for sky."""
    b = base[ty:ty + T, tx:tx + T]; a = b[..., 3] > 128
    blue_b = (b[..., 2] > b[..., 0] + 25) & (b[..., 2] > b[..., 1] - 5)
    blue_p = (p[..., 2] > p[..., 0] + 25) & (p[..., 2] > p[..., 1] - 5)
    m = a & ~blue_b
    return float((blue_p & m).sum()) / max(m.sum(), 1)
import io
tiles = []
if not ONLY_PACK: tok, acc = cf()
for ty in ys:
    for tx in xs:
        a = alpha[ty:ty + T, tx:tx + T]
        if a.max() < 0.02: continue                         # sky only: nothing to paint
        fn = os.path.join(pdir, f"t_{ty}_{tx}.png"); tiles.append((ty, tx, fn))
        if ONLY_PACK: continue
        sky = (a < 0.5).mean() > 0.01
        for attempt in range(4):
            if os.path.exists(fn):
                if sky: break   # near the real sky the blue test would misfire
                bad = fake_sky(np.asarray(Image.open(fn)).astype(np.float32), ty, tx)
                if bad < 0.025: break
                print("repaint", ty, tx, "fake sky", round(bad, 3), flush=True)
            rgb = base[ty:ty + T, tx:tx + T, :3] * a[..., None] + SKY * (1 - a[..., None])
            bio = io.BytesIO(); Image.fromarray(rgb.astype(np.uint8)).save(bio, "PNG")
            raw = paint_tile(tok, acc, bio.getvalue(), seed=3 + attempt * 17, sky=sky)   # the old tile stays until this succeeds
            Image.open(io.BytesIO(raw)).convert("RGB").resize((T, T), Image.LANCZOS).save(fn); print("painted", ty, tx, flush=True)
# ---------------------------------------------------------------- one colour transform for all tiles, then cross-fade
stats = []
for ty, tx, fn in tiles:
    if not os.path.exists(fn): print("missing (render shows through):", fn); stats.append(None); continue
    p = np.asarray(Image.open(fn)).astype(np.float32); m = alpha[ty:ty + T, tx:tx + T] > 0.5
    if m.sum() < 500: stats.append(None); continue
    b = base[ty:ty + T, tx:tx + T, :3][m]; q = p[m]
    stats.append((b.mean(0), b.std(0) + 1e-3, q.mean(0), q.std(0) + 1e-3))
ok = [s for s in stats if s is not None]
g_shift = np.mean([s[2] - s[0] for s in ok], 0); g_scale = np.mean([s[3] / s[1] for s in ok], 0)
# stitch: in each overlap, cut along the seam where the two paintings agree best (image quilting), soften it a little
canvas = base[..., :3].copy(); filled = np.zeros((H, W), bool)
def seam_cols(E):   # E: rows x cols cost; the cheapest top-to-bottom path, one column per row
    C = E.copy(); n, m = C.shape
    for r in range(1, n):
        left = np.r_[np.inf, C[r - 1, :-1]]; right = np.r_[C[r - 1, 1:], np.inf]
        C[r] += np.minimum(np.minimum(left, C[r - 1]), right)
    path = np.zeros(n, int); path[-1] = int(np.argmin(C[-1]))
    for r in range(n - 2, -1, -1):
        c = path[r + 1]; lo, hi = max(c - 1, 0), min(c + 2, m); path[r] = lo + int(np.argmin(C[r, lo:hi]))
    return path
for (ty, tx, fn), s in zip(tiles, stats):
    if not os.path.exists(fn): continue
    p = np.asarray(Image.open(fn)).astype(np.float32)
    if s is not None:  # this tile's painted stats -> its render stats moved by the shared transform (gain clamped)
        bm, bs, pm, ps = s; gain = np.clip(bs * g_scale / ps, 0.75, 1.35); p = (p - pm) * gain + (bm + g_shift)
    mask = np.ones((T, T), np.float32); f = filled[ty:ty + T, tx:tx + T]; cur = canvas[ty:ty + T, tx:tx + T]
    ovm = f & (alpha[ty:ty + T, tx:tx + T] > 0.5)
    if ovm.sum() > 2000:  # nudge this tile's colour towards what is already laid down in the overlap, within a small
        # range: the tile stays anchored to the render-based transform, so corrections can't add up across the picture
        mp, sp_ = p[ovm].mean(0), p[ovm].std(0) + 1e-3; mc, sc_ = cur[ovm].mean(0), cur[ovm].std(0) + 1e-3
        p = (p - mp) * np.clip(sc_ / sp_, 0.92, 1.08) + mp + np.clip(mc - mp, -10, 10)
    E = ((p - cur) ** 2).sum(2)
    lw = int(f[:, :T // 2].all(0).sum()) if f[:, 0].any() else 0         # overlap with the tile on the left
    if lw > 4:
        cols = seam_cols(E[:, :lw])
        for r in range(T): mask[r, :cols[r]] = 0
    th_ = int(f[:T // 2, :].all(1).sum()) if f[0, :].any() else 0       # overlap with the tile above
    if th_ > 4:
        rows_ = seam_cols(E[:th_, :].T)
        for c in range(T): mask[:rows_[c], c] = 0
    mask = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(5))).astype(np.float32) / 255
    mask = np.where(f, mask, 1.0)[..., None]
    canvas[ty:ty + T, tx:tx + T] = cur * (1 - mask) + p * mask; filled[ty:ty + T, tx:tx + T] = True
painted = canvas
# a tile that could not be painted yet (quota): fill what no painted tile covers with a mirror of the painted strip next
# to it, row by row, so no raw render shows (the next run with quota paints it properly)
for ty, tx, fn in tiles:
    if os.path.exists(fn): continue
    f = filled[ty:ty + T, tx:tx + T]
    for r in range(T):
        miss = np.nonzero(~f[r])[0]
        if not len(miss): continue
        x0 = tx + miss[0]; n = len(miss); src = np.clip(x0 - 1 - np.arange(n), 0, W - 1)
        painted[ty + r, x0:x0 + n] = painted[ty + r, src]
painted = np.clip(painted, 0, 255)
rgba = np.dstack([painted, alpha * 255]).astype(np.uint8)
os.makedirs(out, exist_ok=True); Image.fromarray(rgba).save(os.path.join(rdir, "painted.png"))

# ---------------------------------------------------------------- the picture in display tiles (lazy loading, small files)
for f in os.listdir(out):
    if f.startswith("bg_") and f.endswith(".webp"): os.remove(os.path.join(out, f))
BC, BR = 4, 2; tw, th = W // BC, H // BR; bgt = []
for r in range(BR):
    for c in range(BC):
        Image.fromarray(rgba[r * th:(r + 1) * th, c * tw:(c + 1) * tw]).save(os.path.join(out, f"bg_{r}_{c}.webp"), "WEBP", quality=88, method=5)
        bgt.append({"file": f"bg_{r}_{c}.webp", "box": [c / BC, r / BR, (c + 1) / BC, (r + 1) / BR]})

# ---------------------------------------------------------------- occluders: cut from the painted picture by the id pass
lay = json.load(open(os.path.join(rdir, "layout.json"), encoding="utf-8"))
ids = np.asarray(Image.open(os.path.join(rdir, "ids.png")).convert("RGBA"))
idmap = np.where((ids[..., 1] > 200) & (ids[..., 3] > 128), ids[..., 0].astype(np.int32), 0)
odir = os.path.join(out, "occ"); os.makedirs(odir, exist_ok=True)
for f in os.listdir(odir): os.remove(os.path.join(odir, f))
occ_out = []
for o in lay.get("occ", []):
    m = idmap == o["id"]
    if m.sum() < 40: continue
    yy, xx = np.nonzero(m); y0, y1, x0, x1 = max(yy.min() - 3, 0), min(yy.max() + 4, H), max(xx.min() - 3, 0), min(xx.max() + 4, W)
    mk = Image.fromarray((m[y0:y1, x0:x1] * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.9))   # soft edge
    a = (np.asarray(mk).astype(np.float32) / 255.0) * alpha[y0:y1, x0:x1]
    cut = np.dstack([painted[y0:y1, x0:x1], a * 255]).astype(np.uint8)
    Image.fromarray(cut).save(os.path.join(odir, o["name"] + ".webp"), "WEBP", quality=88, method=5)
    occ_out.append({"name": o["name"], "box": [x0 / W, y0 / H, x1 / W, y1 / H], "base": o["base"]})
lay["occ"] = occ_out; lay["bg"] = bgt
with open(os.path.join(out, "layout.js"), "w", encoding="utf-8") as f: f.write("window.LANG_LAYOUT = " + json.dumps(lay) + ";\n")
aj = os.path.join(out, "actors", "actors.json")
if os.path.exists(aj):
    with open(os.path.join(out, "actors.js"), "w", encoding="utf-8") as f: f.write("window.LANG_ACTORS = " + open(aj, encoding="utf-8").read() + ";\n")
print("done", len(tiles), "tiles,", len(occ_out), "occluders")
