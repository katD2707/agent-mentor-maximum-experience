# Tripo API (v3): picture -> textured 3D character -> rig check -> auto-rig -> preset animations. Key is read from
# .env.dev.local (TRIPO_API_KEY=...) like meshy3d.py and never printed.
#   python tripo3d.py <env_file> <out_dir> balance
#   python tripo3d.py <env_file> <out_dir> create <image.png>     upload + image-to-model, waits, downloads model.glb
#   python tripo3d.py <env_file> <out_dir> rig                    rig-check + auto-rig (biped, v3.0 rig), downloads rigged.glb
#   python tripo3d.py <env_file> <out_dir> animate walk idle ...  retarget presets (preset:<name>), downloads anim-<name>.glb
# Task ids are kept in <out_dir>/tripo.json so every step resumes; results are downloaded as soon as a task succeeds
# (Tripo URLs expire).
import json, os, sys, time, urllib.error, urllib.request, uuid

API = "https://openapi.tripo3d.ai/v3"
env_file, out, cmd, *rest = sys.argv[1:]
os.makedirs(out, exist_ok=True)
state_file = os.path.join(out, "tripo.json")
state = json.load(open(state_file, encoding="utf-8")) if os.path.exists(state_file) else {}


def save():
    json.dump(state, open(state_file, "w", encoding="utf-8"), indent=1)


def key():
    for line in open(env_file, encoding="utf-8"):
        k, _, v = line.strip().partition("=")
        if k == "TRIPO_API_KEY" and v.strip():
            return v.strip().strip('"').strip("'")
    sys.exit("TRIPO_API_KEY is missing in " + env_file)


KEY = key()


def call(method, path, body=None, raw=None, ctype="application/json"):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(API + path, method=method, data=data,
                                 headers={"Authorization": "Bearer " + KEY, "Content-Type": ctype})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} on {method} {path}: {e.read().decode(errors='replace')[:500]}")
    if d.get("code") != 0:
        sys.exit(f"API error on {path}: {json.dumps(d)[:500]}")
    return d["data"]


def wait(tid):
    while True:
        t = call("GET", f"/tasks/{tid}")
        print(f"{t.get('type')} {t.get('status')} {t.get('progress', '')}%", flush=True)
        if t["status"] == "success":
            print("credits", t.get("credits_consumed"))
            return t
        if t["status"] in ("failed", "cancelled", "banned", "expired"):
            sys.exit(f"task {t['status']}: {json.dumps(t)[:400]}")
        time.sleep(5)


def fetch(url, name):
    if url:
        urllib.request.urlretrieve(url, os.path.join(out, name))
        print("saved", name)


def upload(path):
    b = uuid.uuid4().hex
    body = (f"--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{os.path.basename(path)}\"\r\n"
            f"Content-Type: image/png\r\n\r\n").encode() + open(path, "rb").read() + f"\r\n--{b}--\r\n".encode()
    return call("POST", "/files", raw=body, ctype="multipart/form-data; boundary=" + b)["file_token"]


if cmd == "balance":
    print(call("GET", "/account/balance"))
elif cmd == "create":
    if "model" not in state:
        tok = upload(rest[0])
        # No cartoon "style" option exists in the v3 API; texture_alignment=original_image keeps the picture's colours.
        state["model"] = call("POST", "/generation/image-to-model", {
            "input": tok, "model": "v3.1-20260211", "texture": True, "pbr": False, "texture_quality": "detailed",
            "texture_alignment": "original_image", "orientation": "align_image", "face_limit": 30000,
            "enable_image_autofix": False})["task_id"]
        save()
    t = wait(state["model"])
    o = t["output"]
    fetch(o.get("model_url") or o.get("pbr_model"), "model.glb")
    fetch(o.get("rendered_image_url"), "preview.webp")
elif cmd == "rig":
    if "check" not in state:
        state["check"] = call("POST", "/animations/rig-check", {"input": state["model"]})["task_id"]
        save()
    c = wait(state["check"])["output"]
    print("riggable", c.get("riggable"), c.get("rig_type"))
    if not c.get("riggable"):
        sys.exit("not riggable")
    if "rig" not in state:
        state["rig"] = call("POST", "/animations/rig", {"input": state["model"], "model": "v3.0-20260909",
                                                        "rig_type": "biped", "spec": "tripo", "out_format": "glb"})["task_id"]
        save()
    fetch(wait(state["rig"])["output"].get("model_url"), "rigged.glb")
elif cmd == "animate":
    for n in rest:
        tag = "anim-" + n
        if tag not in state:
            state[tag] = call("POST", "/animations/retarget", {"input": state["rig"], "animation": "preset:" + n,
                                                               "out_format": "glb", "animate_in_place": True})["task_id"]
            save()
        fetch(wait(state[tag])["output"].get("model_url"), tag + ".glb")
else:
    sys.exit("commands: balance | create <image> | rig | animate <name>...")
