# Hand-painted surface textures for the Làng gà look, made with FLUX.2 [klein] 4B (Apache 2.0) on Cloudflare Workers AI.
# Each texture becomes a detail map (tex/<name>-d.png): its broad colour removed, only the painted strokes, cracks,
# grain and moss kept around mid grey, so the materials keep their own palette and light and gain painted detail.
#   python gen_tex.py <env_file> [name ...]        (no names: all)
import base64, json, os, subprocess, sys, urllib.request, urllib.error
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "tex"); os.makedirs(OUT, exist_ok=True)
STYLE = ("hand-painted stylized texture for a cozy 2D casual game, painterly brush strokes, rich small details, "
         "flat even lighting with no cast shadows, seamless tileable, fills the whole frame, no text, no border")
TEX = {
    "grass": "top-down view of lush grass ground: clumps of short grass blades, little clover leaves, tiny flowers, a few bare spots",
    "dirt": "top-down view of a packed dirt yard: small pebbles, hairline cracks, footprints worn smooth, darker damp patches",
    "stone": "front view of an old wall of irregular rounded stones with moss and grass in the gaps",
    "wood": "front view of weathered vertical wooden planks: visible grain, knots, nail holes, chipped worn edges",
    "leaves": "dense canopy of stylized round tree leaves in overlapping clusters, light and shadow between clusters",
    "bark": "front view of stylized tree bark: vertical grooves, small moss patches",
    "plaster": "front view of an old lime plaster wall: soft blotches, small cracks, a few chipped spots",
    "roof": "front view of rows of overlapping clay roof tiles, slightly uneven, chipped corners, faint moss",
    "knit": "close-up of chunky hand-knitted wool fabric: neat rows of V-shaped knit stitches, soft yarn fuzz, cozy",
    "wool": "close-up of fine woven wool cloth with a subtle diagonal twill weave, soft fibers, tiny slubs, even tone",
    "brocade": "close-up of ornate woven brocade fabric with a repeating geometric pattern of small diamonds, triangles and circles, raised embroidered thread",
    "leather": "close-up of smooth worn leather with fine grain, subtle creases, tiny stitched seam",
}
env = sys.argv[1]; names = sys.argv[2:] or list(TEX)
keys = {}
for line in open(env, encoding="utf-8-sig"):
    if "=" in line and line.strip().startswith("CLOUDFLARE_"):
        k, v = line.split("=", 1); keys[k.strip()] = v.strip()
tok = keys.get("CLOUDFLARE_AI_TOKEN") or sys.exit("no CLOUDFLARE_AI_TOKEN")
acc = None
for t in (tok, keys.get("CLOUDFLARE_WORKERS_TOKEN")):
    if not t: continue
    try:
        req = urllib.request.Request("https://api.cloudflare.com/client/v4/accounts", headers={"Authorization": "Bearer " + t})
        r = json.load(urllib.request.urlopen(req, timeout=60))["result"]
        if r: acc = r[0]["id"]; break
    except urllib.error.HTTPError:
        pass
acc or sys.exit("cannot find the Cloudflare account id")
bnd = "----mentortex7"
def field(n, v): return (f"--{bnd}\r\nContent-Disposition: form-data; name=\"{n}\"\r\n\r\n{v}\r\n").encode()
for name in names:
    raw_path = os.path.join(OUT, name + ".jpg")
    if not os.path.exists(raw_path):
        body = field("prompt", TEX[name] + ". " + STYLE) + field("width", "1024") + field("height", "1024") + field("seed", "11") + f"--{bnd}--\r\n".encode()
        req = urllib.request.Request(f"https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/@cf/black-forest-labs/flux-2-klein-4b", data=body,
                                     method="POST", headers={"Authorization": "Bearer " + tok, "Content-Type": f"multipart/form-data; boundary={bnd}"})
        try:
            raw = urllib.request.urlopen(req, timeout=300).read()
        except urllib.error.HTTPError as e:
            print(name, "HTTP", e.code, e.read().decode()[:300]); continue
        if raw[:3] != b"\xff\xd8\xff" and raw[:4] != b"\x89PNG":
            j = json.loads(raw); r = j.get("result", j); raw = base64.b64decode(r["image"])
        tmp = raw_path + ".in"; open(tmp, "wb").write(raw)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-q:v", "3", raw_path], check=True); os.remove(tmp)
        print("made", name)
    # seamless: mirror into a 2x2 tile, then the detail map = picture minus its heavy blur (+ mid grey)
    det = os.path.join(OUT, name + "-d.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw_path, "-filter_complex",
                    "[0]scale=512:512,split=2[a][b];[b]hflip[c];[a][c]hstack,split=2[t][u];[u]vflip[v];[t][v]vstack,format=gbrp,split[x][y];"
                    "[y]gblur=sigma=48[bl];[x][bl]blend=all_mode=grainextract,format=rgb24", det], check=True)
    print("detail", name)
