# Meshy API: picture -> textured 3D character (A-pose) -> auto-rig (+ walk/run) -> extra animations. Same idea as
# paint_cf.py: the key is read from .env.dev.local (MESHY_API_KEY=msy_...) and never printed.
#   python meshy3d.py <env_file> <out_dir> create <image.png>      image-to-3D (~30 credits), waits, downloads GLB/FBX
#   python meshy3d.py <env_file> <out_dir> rig                     auto-rig the model of out_dir (5 credits), downloads
#   python meshy3d.py <env_file> <out_dir> library <search>        list animations (free), e.g. idle / wave / walk
#   python meshy3d.py <env_file> <out_dir> animate <id> [<id>...]  apply animations to the rig (3 credits each)
# Task ids are kept in <out_dir>/meshy.json so every step can be resumed; Meshy deletes API assets after 3 days, so
# everything is downloaded as soon as a task succeeds.
import base64, json, os, sys, time, urllib.error, urllib.parse, urllib.request

API = "https://api.meshy.ai/openapi/v1"
env_file, out, cmd, *rest = sys.argv[1:]
os.makedirs(out, exist_ok=True)
state_file = os.path.join(out, "meshy.json")
state = json.load(open(state_file, encoding="utf-8")) if os.path.exists(state_file) else {}


def save():
    json.dump(state, open(state_file, "w", encoding="utf-8"), indent=1)


def key():
    for line in open(env_file, encoding="utf-8"):
        k, _, v = line.strip().partition("=")
        if k == "MESHY_API_KEY" and v.strip():
            return v.strip()
    sys.exit("MESHY_API_KEY is missing in " + env_file)


KEY = key()


def call(method, path, body=None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:  # the body explains (402 = needs a paid plan, 400 = bad field)
        sys.exit(f"HTTP {e.code} on {method} {path}: {e.read().decode(errors='replace')[:400]}")


def wait(kind, tid):
    while True:
        t = call("GET", f"/{kind}/{tid}")
        print(f"{kind} {t.get('status')} {t.get('progress', '')}%", flush=True)
        if t["status"] == "SUCCEEDED":
            return t
        if t["status"] in ("FAILED", "CANCELED"):
            sys.exit(f"{kind} {t['status']}: {t.get('task_error')}")
        time.sleep(10)


def fetch(url, name):
    if url:
        urllib.request.urlretrieve(url, os.path.join(out, name))
        print("saved", name)


if cmd == "create":
    img = rest[0]
    uri = "data:image/png;base64," + base64.b64encode(open(img, "rb").read()).decode()
    if "model" not in state:
        state["model"] = call("POST", "/image-to-3d", {
            "image_url": uri, "ai_model": "latest", "should_texture": True, "should_remesh": True,
            "topology": "triangle", "target_polycount": 30000, "pose_mode": "a-pose", "target_formats": ["glb", "fbx"]})["result"]
        save()
    t = wait("image-to-3d", state["model"])
    print("credits", t.get("consumed_credits"))
    fetch(t["model_urls"].get("glb"), "model.glb")
    fetch(t["model_urls"].get("fbx"), "model.fbx")
    fetch((t.get("texture_urls") or [{}])[0].get("base_color"), "base_color.png")
    fetch(t.get("thumbnail_url"), "thumbnail.png")
elif cmd == "rig":
    if "rig" not in state:
        state["rig"] = call("POST", "/rigging", {"input_task_id": state["model"], "animation_type": "biped",
                                                 "height_meters": 1.6})["result"]
        save()
    r = wait("rigging", state["rig"])["result"]
    fetch(r.get("rigged_character_glb_url"), "rigged.glb")
    fetch(r.get("rigged_character_fbx_url"), "rigged.fbx")
    b = r.get("basic_animations") or {}
    fetch(b.get("walking_glb_url"), "walk.glb")
    fetch(b.get("running_glb_url"), "run.glb")
elif cmd == "library":
    q = urllib.parse.quote(rest[0]) if rest else ""
    d = call("GET", f"/animations/library?search={q}")
    items = d.get("result", d.get("items", [])) if isinstance(d, dict) else d  # list, or wrapped in an object
    for a in items:
        print(a.get("action_id"), a.get("rig_type"), a.get("category"), "|", a.get("name"))
elif cmd == "animate":
    ids = [int(x) for x in rest]
    tag = "anim-" + "-".join(map(str, ids))
    if tag not in state:
        state[tag] = call("POST", "/animations", {"rig_task_id": state["rig"], "action_ids": ids,
                                                  "post_process": {"operation_type": "change_fps", "fps": 24}})["result"]
        save()
    r = wait("animations", state[tag])["result"]
    fetch(r.get("animation_glb_url"), tag + ".glb")
    fetch(r.get("processed_animation_fps_fbx_url") or r.get("animation_fbx_url"), tag + ".fbx")
else:
    sys.exit("commands: create <image> | rig | library <search> | animate <id>...")
