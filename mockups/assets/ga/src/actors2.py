# 8-direction sprite sheets of the new student (kid2.py) in the exact layout of actors.py: idle 16 frames x 8 dirs, walk 12 frames x 8 dirs,
# wave 24 frames (s only), 12 fps, a horizontal strip of FRAME-px squares, the feet at pixel FEET, PX_PER_UNIT 94.1, same sun / fill / camera tilt.
#   blender -b -P actors2.py -- --outdir <dir> [--only nam,nu] [--anim idle,walk,wave] [--dir s,e] [--samples 48] [--frame 416]
# One Blender process per actor. Writes <actor>-<anim>-<dir>.webp and actors.json (same schema as lang/actors/actors.json).
import sys, os, math, json, subprocess, shutil
ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def opt(name, default=None):
    return ARGV[ARGV.index(name) + 1] if name in ARGV and ARGV.index(name) + 1 < len(ARGV) else default
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = opt("--outdir") or os.path.join(os.path.dirname(HERE), "hoc-sinh-moi", "actors")
PX_PER_UNIT = 94.1
FRAME = int(opt("--frame", 416))
FEET = (FRAME // 2, int(round(FRAME * 0.89)))
FPS = 12
DIRS = ["s", "se", "e", "ne", "n", "nw", "w", "sw"]
YAW = {"s": 0, "se": 45, "e": 90, "ne": 135, "n": 180, "nw": 225, "w": 270, "sw": 315}
KID_ANIMS = {"idle": (16, True, DIRS), "walk": (12, True, DIRS), "wave": (24, False, ["s"])}
ACTORS = {"nam": 1.37, "nu": 1.37}      # kid2 stands ~5% shorter than kid.py at the same scale; 1.37 gives the same on-map height as the old 1.3
STRIDE_A = 0.24
def stride_of(a): return round(4 * STRIDE_A * ACTORS[a], 3)
def write_json():
    os.makedirs(OUT_DIR, exist_ok=True)
    data = {"pxPerUnit": PX_PER_UNIT, "frame": [FRAME, FRAME], "feet": list(FEET), "fps": FPS, "dirs": DIRS, "actors": {}}
    for a in ACTORS:
        anims = {}
        for name, (n, loop, dirs) in KID_ANIMS.items():
            have = [d for d in dirs if os.path.exists(os.path.join(OUT_DIR, f"{a}-{name}-{d}.webp"))]
            if not have: continue
            anims[name] = {"frames": n, "fps": FPS, "loop": loop, "dirs": have}
            if name == "walk": anims[name]["stride"] = stride_of(a)
        data["actors"][a] = {"anims": anims}
    with open(os.path.join(OUT_DIR, "actors.json"), "w", encoding="utf-8") as f: json.dump(data, f, indent=1)
if "--json" in ARGV: write_json(); sys.exit(0)
only = opt("--only"); only = only.split(",") if only else list(ACTORS)
sel_anim = opt("--anim"); sel_anim = sel_anim.split(",") if sel_anim else None
sel_dir = opt("--dir"); sel_dir = sel_dir.split(",") if sel_dir else None
def jobs(actor):
    out = []
    for name, (n, loop, dirs) in KID_ANIMS.items():
        if sel_anim and name not in sel_anim: continue
        for d in dirs:
            if sel_dir and d not in sel_dir: continue
            out.append((name, d, n, os.path.join(OUT_DIR, f"{actor}-{name}-{d}.webp")))
    return out
if not opt("--actor"):
    import bpy
    os.makedirs(OUT_DIR, exist_ok=True)
    for a in only:
        todo = jobs(a); print(f"{a}: {len(todo)} sheets", flush=True)
        child = [x for k, x in enumerate(ARGV) if x != "--only" and (k == 0 or ARGV[k - 1] != "--only")]
        r = subprocess.run([bpy.app.binary_path, "-b", "-P", os.path.abspath(__file__), "--", "--actor", a] + child, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        print("\n".join([l for l in r.stdout.splitlines() if "Error" in l or "Traceback" in l or "SHEET" in l][-40:]), flush=True)
        write_json()
    sys.exit(0)
# ------------------------------------------------------------------ one actor
ACTOR = opt("--actor")
TMP = os.path.join(os.environ.get("TEMP", "."), f"actors2-{ACTOR}-{os.getpid()}")
sys.argv = [sys.argv[0], "--", TMP]
exec(open(os.path.join(HERE, "lang_lib.py"), encoding="utf-8").read())
lang_lib_loaded = True
_k = open(os.path.join(HERE, "kid2.py"), encoding="utf-8").read()
exec(_k[_k.index("\n# ==== KID2 BUILDER"):_k.index("\n# ==== KID2 MAIN")])
setup_render(FRAME, FRAME, int(opt("--samples", 48)))
sc.render.film_transparent = True
sc.render.image_settings.file_format = "PNG"; sc.render.image_settings.color_mode = "RGBA"
rig(); bpy.data.lights['sun'].angle = math.radians(1.0)
ortho = FRAME / PX_PER_UNIT
cam_up = Vector((0, math.cos(math.radians(90 - CAM_TILT)), math.sin(math.radians(90 - CAM_TILT))))
camera(ortho, cam_up * ((FEET[1] - FRAME / 2) / PX_PER_UNIT), (FRAME, FRAME))
yawroot = link(bpy.data.objects.new("yaw", None))
def gait(p):
    p %= 1.0
    if p < 0.5: return 1 - 4 * p, 0.0
    q = (p - 0.5) * 2; e = q * q * (3 - 2 * q); return -1 + 2 * e, math.sin(math.pi * q)
K = build_kid2(ACTOR); kg, khp = K.g, K.hp; kg.parent = yawroot; yawroot.scale = (ACTORS[ACTOR],) * 3
arms, legs = K.arms, K.legs; leg0 = {sx: legs[sx].location.copy() for sx in (-1, 1)}; HC0 = K.hc.copy(); SPL = 0.14
def kpose(z=0.0, sc_=(1, 1, 1), rot=(0, 0, 0), head=(0, 0, 0), arm=None, leg=None, tails=0.0, blink=1.0, hoff=(0, 0, 0)):
    kg.location = (0, 0, z); kg.scale = sc_; kg.rotation_euler = rot
    khp.rotation_euler = head; khp.location = HC0 + Vector(hoff)
    for sx in (-1, 1):
        ax, ay = arm[sx] if arm else (0.0, -sx * SPL)
        arms[sx].rotation_euler = (ax, ay, 0)
        lx, lz = leg[sx] if leg else (0.0, 0.0)
        legs[sx].rotation_euler = (lx, 0, 0); legs[sx].location = leg0[sx] + Vector((0, 0, lz))
    for pv, sx in K.tails: pv.rotation_euler = (tails * 0.4, 0, tails * sx)
    for o in K.eyes:
        x, y, zz = K.base[o.name]; o.scale = (x, y, zz * blink)
def frame_pose(anim, i, n):
    t = 2 * math.pi * i / n
    if anim == "idle":
        bl = {10: 0.55, 11: 0.12, 12: 0.55}.get(i, 1.0)
        kpose(sc_=(1 + 0.012 * math.sin(t),) * 2 + (1 - 0.016 * math.sin(t),), head=(0, 0.06 * math.sin(t), 0), hoff=(0, 0, 0.01 * math.sin(t)),
              arm={sx: (0.08 * math.sin(t + sx), -sx * SPL) for sx in (-1, 1)}, tails=0.05 * math.sin(t - 0.8), blink=bl)
    elif anim == "walk":
        p = i / n; L = K.leg_len; leg = {}; arm = {}; uu = {}
        for sx in (-1, 1):
            u, lift = gait(p + (0.5 if sx > 0 else 0.0)); uu[sx] = u
            th = -math.asin(STRIDE_A / L) * u
            leg[sx] = (th, 0.07 * lift - L * (1 - math.cos(th)))
        for sx in (-1, 1): arm[sx] = (-0.6 * uu[-sx], -sx * SPL)
        bob = abs(math.sin(math.pi * 2 * p))
        kpose(z=0.04 * bob, rot=(0.04, 0, 0.04 * math.sin(t)), head=(-0.03, 0.05 * math.sin(t), 0), hoff=(0, 0, 0.015 * math.sin(t * 2)),
              arm=arm, leg=leg, tails=0.2 * math.sin(t * 2 - 1.3), sc_=(1, 1, 1 - 0.012 * math.sin(t * 2)))
    elif anim == "wave":
        u = i / (n - 1); up = min(1, u * 5, (1 - u) * 5); wave = math.sin(u * 2 * math.pi * 3) * 0.35 * up
        kpose(z=0.06 * abs(math.sin(u * math.pi * 2)) * up, head=(0, -0.08 * up, 0), arm={1: (0, -SPL - 2.35 * up + wave), -1: (0, SPL)}, tails=0.9 * math.sin(u * 12) * up * 0.05)
EQ = "eq=saturation=1.2:contrast=1.04"
os.makedirs(OUT_DIR, exist_ok=True)
for name, d, n, path in jobs(ACTOR):
    yawroot.rotation_euler = (0, 0, math.radians(YAW[d]))
    fd = os.path.join(TMP, f"{name}-{d}"); os.makedirs(fd, exist_ok=True)
    LIM = int(opt('--limit', n))
    for i in range(min(n, LIM)):
        frame_pose(name, i, n)
        sc.render.filepath = os.path.join(fd, f"f_{i + 1:03d}.png"); bpy.ops.render.render(write_still=True)
    if LIM < n:
        for q in os.listdir(fd): shutil.copy(os.path.join(fd, q), os.path.join(OUT_DIR, f"{ACTOR}-{name}-{d}-{q}"))
        continue
    tmpout = path + ".tmp.webp"
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", os.path.join(fd, "f_%03d.png"), "-vf", f"{EQ},tile={n}x1", "-frames:v", "1",
                        "-c:v", "libwebp", "-quality", "85", "-compression_level", "6", "-pix_fmt", "yuva420p", tmpout], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if r.returncode: print("Error ffmpeg", r.stdout); sys.exit(1)
    os.replace(tmpout, path); shutil.rmtree(fd, ignore_errors=True)
    print("SHEET", os.path.basename(path), os.path.getsize(path), flush=True)
shutil.rmtree(TMP, ignore_errors=True)
