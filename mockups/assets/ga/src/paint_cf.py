# Repaint a rendered picture as a soft painted illustration with Cloudflare Workers AI (free daily allowance),
# Stable Diffusion 1.5 img2img (CreativeML OpenRAIL-M). Low strength keeps the layout.
# python paint_cf.py <env_file> <in.png 1024x640> <out.png> <strength> [seed]
import base64, json, sys, urllib.request, urllib.error

env, src, dst, strength = sys.argv[1:5]
seed = int(sys.argv[5]) if len(sys.argv) > 5 else 7
keys = {}
for line in open(env, encoding="utf-8-sig"):
    if "=" in line and line.strip().startswith("CLOUDFLARE_"):
        k, v = line.split("=", 1); keys[k.strip()] = v.strip()
tok = keys.get("CLOUDFLARE_AI_TOKEN")
if not tok:
    sys.exit("no CLOUDFLARE_AI_TOKEN")

def call(url, body=None, token=None):
    h = {"Authorization": "Bearer " + (token or tok), "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers=h,
                                 method="POST" if body is not None else "GET")
    return urllib.request.urlopen(req, timeout=180)

# the AI token may only run models; the account id comes from whichever token can list accounts
acc = None
for t in (tok, keys.get("CLOUDFLARE_WORKERS_TOKEN")):
    if not t: continue
    try:
        r = json.load(call("https://api.cloudflare.com/client/v4/accounts", token=t))["result"]
        if r: acc = r[0]["id"]; break
    except urllib.error.HTTPError:
        pass
if not acc:
    sys.exit("cannot find the Cloudflare account id")
import os
STYLES = {
    "paint": "a soft hand-painted 2D illustration for a cute casual mobile game: painterly brushwork, gouache texture, warm afternoon sunlight, soft painted shadows, gentle colour variation in the grass and dirt",
    "game": "bright, clean, hand-painted 2D background art for a cheerful casual mobile game: vivid saturated colours, crisp clean shapes with soft painted shading, glossy highlights, sunny daylight, lush detailed grass and blossoms, polished and cute",
}
STYLE = STYLES[os.environ.get("PAINT_STYLE", "paint")]
PROMPT = ("Repaint this exact picture as " + STYLE + ". Keep exactly the same layout, every object in the same place and size, the same camera angle, and the "
          "empty dirt yard in the middle. No text, no people, no animals.")
# FLUX.2 [klein] on Workers AI takes multipart form data with reference images; strength is not used (the prompt
# asks to keep the layout); 'model' is the 4th argument
model = strength if strength.startswith("@cf/") else "@cf/black-forest-labs/flux-2-klein-4b"
bnd = "----mentorpaint7"
def field(name, value):
    return (f"--{bnd}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n").encode()
img = open(src, "rb").read()
payload = (field("prompt", PROMPT) + field("width", "1024") + field("height", "640") + field("seed", str(seed)) +
           f"--{bnd}\r\nContent-Disposition: form-data; name=\"input_image_0\"; filename=\"in.png\"\r\nContent-Type: image/png\r\n\r\n".encode()
           + img + f"\r\n--{bnd}--\r\n".encode())
req = urllib.request.Request(f"https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/{model}", data=payload, method="POST",
                             headers={"Authorization": "Bearer " + tok, "Content-Type": f"multipart/form-data; boundary={bnd}"})
try:
    raw = urllib.request.urlopen(req, timeout=300).read()
except urllib.error.HTTPError as e:
    sys.exit(f"HTTP {e.code}: {e.read().decode()[:500]}")
if raw[:4] == b"\x89PNG" or raw[:3] == b"\xff\xd8\xff":
    data = raw
else:
    j = json.loads(raw); r = j.get("result", j)
    b64 = r.get("image") if isinstance(r, dict) else None
    if not b64:
        sys.exit("no image: " + raw[:400].decode(errors="replace"))
    data = base64.b64decode(b64)
open(dst, "wb").write(data)
print("saved", dst, len(data))
