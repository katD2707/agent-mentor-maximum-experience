# 8-direction sprite sheets of the village actors, in the look of lang_lib.py (same sun, fill light and camera tilt).
#   blender -b -P actors.py -- [--only toan,nam] [--anim walk] [--dir s,e] [--force] [--frame 416] [--samples 48]
# Renders every missing <actor>-<anim>-<dir>.webp (a horizontal strip of frames, 12 fps) into assets/ga/lang/actors/ and
# rewrites actors.json. Existing sheets are skipped unless --force. One Blender process per actor, run one after the other.
#   --style flat   flat cel shading + warm outline (default: the painted toon look of chicken.py)
#   --list     only print the jobs         --json   only rewrite actors.json      --outdir <dir>  write elsewhere
# Every frame is a square of FRAME px; the actor stands on the origin, which sits at pixel FEET in every frame, drawn at
# PX_PER_UNIT (the village picture: 3200 px for 34 world units), so the HTML can place a frame by its feet anchor.
import sys, os, math, json, subprocess, shutil
ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
def opt(name, default=None):
    return ARGV[ARGV.index(name) + 1] if name in ARGV and ARGV.index(name) + 1 < len(ARGV) else default
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = opt("--outdir") or os.path.join(os.path.dirname(HERE), "lang", "actors")
PX_PER_UNIT = 94.1
FRAME = int(opt("--frame", 416))
FEET = (FRAME // 2, int(round(FRAME * 0.89)))      # the origin's pixel in every frame
FPS = 12
DIRS = ["s", "se", "e", "ne", "n", "nw", "w", "sw"]            # screen directions the actor faces
YAW = {"s": 0, "se": 45, "e": 90, "ne": 135, "n": 180, "nw": 225, "w": 270, "sw": 315}   # about Z, from facing the camera
CHICKEN_ANIMS = {"idle": (16, True, DIRS), "walk": (12, True, DIRS), "peck": (16, False, DIRS), "jump": (24, False, ["s"])}
KID_ANIMS = {"idle": (16, True, DIRS), "walk": (12, True, DIRS), "wave": (24, False, ["s"])}
ACTORS = {"toan": ("chicken", 3), "van": ("chicken", 2), "anh": ("chicken", 2), "nam": ("kid", 1.3), "nu": ("kid", 1.3)}
CHICKEN_S = {2: 0.86, 3: 1.0}
STRIDE_A = 0.2   # a foot travels from +A to -A (times the actor's scale) under the body during one step

def stride_of(actor):  # world units the actor must advance per walk cycle (2 steps) for the planted foot not to slide
    kind, v = ACTORS[actor]
    return round(4 * STRIDE_A * (CHICKEN_S[v] if kind == "chicken" else 1.3), 3)

def write_json():
    os.makedirs(OUT_DIR, exist_ok=True)
    data = {"pxPerUnit": PX_PER_UNIT, "frame": [FRAME, FRAME], "feet": list(FEET), "fps": FPS, "dirs": DIRS, "actors": {}}
    for a, (kind, _) in ACTORS.items():
        anims = {}
        for name, (n, loop, dirs) in (CHICKEN_ANIMS if kind == "chicken" else KID_ANIMS).items():
            have = [d for d in dirs if os.path.exists(os.path.join(OUT_DIR, f"{a}-{name}-{d}.webp"))]
            if not have: continue
            anims[name] = {"frames": n, "fps": FPS, "loop": loop, "dirs": have}
            if name == "walk": anims[name]["stride"] = stride_of(a)
        data["actors"][a] = {"anims": anims}
    with open(os.path.join(OUT_DIR, "actors.json"), "w", encoding="utf-8") as f: json.dump(data, f, indent=1)

if "--json" in ARGV:
    write_json(); sys.exit(0)

only = opt("--only"); only = [x for x in only.split(",")] if only else list(ACTORS)
sel_anim = opt("--anim"); sel_anim = sel_anim.split(",") if sel_anim else None
sel_dir = opt("--dir"); sel_dir = sel_dir.split(",") if sel_dir else None
FORCE = "--force" in ARGV

def jobs(actor):
    kind = ACTORS[actor][0]; out = []
    for name, (n, loop, dirs) in (CHICKEN_ANIMS if kind == "chicken" else KID_ANIMS).items():
        if sel_anim and name not in sel_anim: continue
        for d in dirs:
            if sel_dir and d not in sel_dir: continue
            path = os.path.join(OUT_DIR, f"{actor}-{name}-{d}.webp")
            if FORCE or not os.path.exists(path): out.append((name, d, n, path))
    return out

if not opt("--actor"):  # orchestrator: one Blender process per actor, then actors.json
    import bpy
    os.makedirs(OUT_DIR, exist_ok=True)
    for a in only:
        todo = jobs(a)
        print(f"{a}: {len(todo)} sheets to render", flush=True)
        if "--list" in ARGV or not todo: continue
        ARGV_CHILD = [x for k, x in enumerate(ARGV) if x != "--only" and (k == 0 or ARGV[k - 1] != "--only")]
        cmd = [bpy.app.binary_path, "-b", "-P", os.path.abspath(__file__), "--", "--actor", a] + ARGV_CHILD
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        tail = [l for l in r.stdout.splitlines() if "Error" in l or "Traceback" in l or "SHEET" in l]
        print("\n".join(tail[-40:]), flush=True)
        if r.returncode: print("FAILED", a, flush=True)
        write_json()
    write_json(); sys.exit(0)

# ----------------------------------------------------------------------------------------------------- one actor
ACTOR = opt("--actor"); KIND, VAL = ACTORS[ACTOR]
TMP = os.path.join(os.environ.get("TEMP", "."), f"actors-{ACTOR}-{os.getpid()}")
sys.argv = [sys.argv[0], "--", TMP]   # chicken.py reads <out_dir> mode subject stage from argv; keep it out of our options
exec(open(os.path.join(HERE, "lang_lib.py"), encoding="utf-8").read())
_k = open(os.path.join(HERE, "kid.py"), encoding="utf-8").read()
exec(_k[_k.index("\ndef build_kid"):_k.index("\nK = build_kid")])
STYLE = opt("--style", "paint")
if STYLE == "flat":  # flat cel look for a hand-painted background: 2-3 tones, no rim light, no highlight band, warm soft outline
    PAINT = False; OUTLINE_K = 1.0
    def outline_mat():
        m = flat("outline", "#8a5a40"); m.use_backface_culling = True; return m
SAMPLES = int(opt("--samples", 48))
setup_render(FRAME, FRAME, SAMPLES)
sc.render.film_transparent = True
sc.render.image_settings.file_format = "PNG"; sc.render.image_settings.color_mode = "RGBA"
rig()
ortho = FRAME / PX_PER_UNIT
cam_up = Vector((0, math.sin(math.radians(90 - CAM_TILT)) * 0 + math.cos(math.radians(90 - CAM_TILT)), math.sin(math.radians(90 - CAM_TILT))))
camera(ortho, cam_up * ((FEET[1] - FRAME / 2) / PX_PER_UNIT), (FRAME, FRAME))

yawroot = link(bpy.data.objects.new("yaw", None))
def lerp_keys(keys, f):
    """keys: [(frame, value or tuple)]; piecewise linear."""
    if f <= keys[0][0]: return keys[0][1]
    for (f0, v0), (f1, v1) in zip(keys, keys[1:]):
        if f <= f1:
            u = (f - f0) / (f1 - f0)
            return tuple(a + (b - a) * u for a, b in zip(v0, v1)) if isinstance(v0, tuple) else v0 + (v1 - v0) * u
    return keys[-1][1]

def gait(p):
    """Foot phase p (0..1): returns (u, lift): u = +1 forward .. -1 back; planted (u falls linearly) for half the cycle."""
    p %= 1.0
    if p < 0.5: return 1 - 4 * p, 0.0
    q = (p - 0.5) * 2; e = q * q * (3 - 2 * q)
    return -1 + 2 * e, math.sin(math.pi * q)

if KIND == "chicken":
    stage = VAL; s = CHICKEN_S[stage]
    C = Chicken(0, stage, ("neutral", "happy"), turn=0, subject=ACTOR)
    g, hp = C.g, C.hp; g.parent = yawroot
    hp0 = hp.location.copy(); beak0 = C.beak_lo.rotation_euler.copy()
    wings = C.parts["wings"]; feet = C.parts["feet"]; foot0 = {sx: fp.location.copy() for fp, sx in feet}
    blinkers = list(C.moods["neutral"]); base = {o.name: tuple(o.scale) for o in blinkers}
    def pose(z=0.0, sc_=(1, 1, 1), rot=(0, 0, 0), head=(0, 0, 0), hoff=(0, 0, 0), wing=(0.3, 0.3), foot=None, mood="neutral", blink=1.0, beak=0.0, x=0.0):
        g.location = (x, 0, z); g.scale = sc_; g.rotation_euler = rot
        hp.rotation_euler = head; hp.location = hp0 + Vector(hoff)
        for piv, sx in wings: piv.rotation_euler = (0.3, -sx * wing[0 if sx < 0 else 1], 0)
        for fp, sx in feet:
            rx, dy, dz = foot[sx] if foot else (0, 0, 0)
            fp.rotation_euler = (rx, 0, 0); fp.location = foot0[sx] + Vector((0, dy, dz))
        C.show(mood); C.beak_lo.rotation_euler = (beak0.x + beak, beak0.y, beak0.z)
        for o in blinkers:
            sx_, sy_, sz_ = base[o.name]; o.scale = (sx_, sy_, sz_ * blink)
    def frame_pose(anim, i, n):
        t = 2 * math.pi * i / n
        if anim == "idle":
            bl = {10: 0.55, 11: 0.12, 12: 0.55}.get(i, 1.0)
            k = 0.015 * math.sin(t)
            pose(z=0.03 * (1 - math.cos(t)) / 2, sc_=(1 + k, 1 + k, 1 - 0.02 * math.sin(t)), head=(0, 0.07 * math.sin(t), 0),
                 hoff=(0, -0.03 * s * math.sin(2 * t), 0.03 * s * math.sin(2 * t - 1)), wing=(0.3 + 0.06 * math.sin(2 * t), 0.3 + 0.06 * math.sin(2 * t)), blink=bl)
        elif anim == "walk":
            p = i / n; A = STRIDE_A * s; foot = {}
            for fp, sx in feet:
                u, lift = gait(p + (0.5 if sx > 0 else 0.0))
                th = -0.5 * u  # tilt about the hip: forward is -Y, so negative
                foot[sx] = (th, -0.5 * A * u, 0.1 * s * lift - 0.17 * s * (1 - math.cos(th)))
            bob = abs(math.sin(math.pi * p * 2))
            fl = 0.3 + 0.25 * (0.5 + 0.5 * math.sin(t * 2))
            pose(z=0.06 * s * bob, rot=(0.04 * math.sin(t * 2 - 1.2), 0.11 * math.sin(t), 0.07 * math.sin(t)),
                 head=(0.05 * math.sin(t * 2), -0.1 * math.sin(t), 0), hoff=(0, -0.08 * s * math.sin(t * 2 + 0.4), 0.02 * s * math.sin(t * 4)),
                 wing=(fl, fl + 0.05), foot=foot)
        elif anim == "peck":
            D = [(0, 0), (1, -0.15), (2, -0.22), (3, 0.9), (4, 1.0), (5, 0.35), (6, -0.1), (7, 0.05), (8, -0.15), (9, 0.9), (10, 1.0), (11, 0.35), (12, -0.05), (13, 0.02), (15, 0)]
            d = lerp_keys(D, i)
            dd = max(d, 0)
            pose(z=0.0, rot=(0.18 * d, 0, 0), head=(0.22 * d, 0, 0), hoff=(0, -0.5 * s * dd + 0.05 * min(d, 0), -0.5 * s * dd + 0.04 * min(d, 0)),
                 wing=(0.3 + 0.15 * dd, 0.3 + 0.15 * dd), beak=0.4 if 0.55 < d < 0.95 else 0)
        elif anim == "jump":
            f = 25 + i
            J = [(25, (0, 1, 1, 1)), (27, (0, 1.12, 1.12, 0.82)), (29, (0.35, 0.92, 0.92, 1.14)), (32, (0.85, 0.97, 0.97, 1.04)),
                 (35, (0.95, 1, 1, 1)), (38, (0.7, 1, 1, 1)), (41, (0.1, 0.95, 0.95, 1.08)), (43, (0, 1.14, 1.14, 0.84)), (46, (0, 0.98, 0.98, 1.03)), (48, (0, 1, 1, 1))]
            z, sx_, sy_, sz_ = lerp_keys(J, f); up = 29 <= f <= 41
            flap = (0.3 + (1.1 if f % 2 == 0 else 0.5)) if up else 0.3
            pose(z=z, sc_=(sx_, sy_, sz_), head=(math.radians(-8) if up else 0, 0, 0), wing=(flap, flap), mood="happy" if 27 <= f <= 45 else "neutral")
    FACE_SCALE = 1.0
else:
    K = build_kid("nu" if ACTOR == "nu" else "nam")
    kg, khp = K.g, K.hp; kg.parent = yawroot; yawroot.scale = (VAL,) * 3
    arms, legs = K.arms, K.legs; leg0 = {sx: legs[sx].location.copy() for sx in (-1, 1)}
    def kpose(z=0.0, sc_=(1, 1, 1), rot=(0, 0, 0), head=(0, 0, 0), arm=None, leg=None, tails=0.0, blink=1.0, hoff=(0, 0, 0)):
        kg.location = (0, 0, z); kg.scale = sc_; kg.rotation_euler = rot
        khp.rotation_euler = head; khp.location = Vector((0, 0, 1.78)) + Vector(hoff)
        for sx in (-1, 1):
            ax, ay = arm[sx] if arm else (0.0, -sx * 0.25)
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
            kpose(sc_=(1 + 0.012 * math.sin(t),) * 2 + (1 - 0.016 * math.sin(t),), head=(0, 0.06 * math.sin(t), 0),
                  arm={sx: (0.08 * math.sin(t + sx), -sx * 0.25) for sx in (-1, 1)}, tails=0.05 * math.sin(t - 0.8), blink=bl)
        elif anim == "walk":
            p = i / n; L = 0.46; leg = {}; arm = {}; uu = {}
            for sx in (-1, 1):
                u, lift = gait(p + (0.5 if sx > 0 else 0.0)); uu[sx] = u
                th = -math.asin(STRIDE_A / L) * u
                leg[sx] = (th, 0.07 * lift - L * (1 - math.cos(th)))
            for sx in (-1, 1): arm[sx] = (-0.7 * uu[-sx], -sx * 0.22)
            bob = abs(math.sin(math.pi * 2 * p))
            kpose(z=0.05 * bob, rot=(0.05, 0, 0.04 * math.sin(t)), head=(-0.04, 0.05 * math.sin(t), 0), hoff=(0, 0, 0.02 * math.sin(t * 2)),
                  arm=arm, leg=leg, tails=0.18 * math.sin(t * 2 - 1.3), sc_=(1, 1, 1 - 0.015 * math.sin(t * 2)))
        elif anim == "wave":
            u = i / (n - 1); up = min(1, u * 5, (1 - u) * 5)
            wave = math.sin(u * 2 * math.pi * 3) * 0.35 * up
            arm = {1: (0, -0.25 - 2.35 * up + wave), -1: (0, 0.25)}
            kpose(z=0.06 * abs(math.sin(u * math.pi * 2)) * up, head=(0, -0.08 * up, 0), arm=arm, tails=0.9 * math.sin(u * 12) * up * 0.05)

EQ = "eq=saturation=1.2:contrast=1.04"
os.makedirs(OUT_DIR, exist_ok=True)
for name, d, n, path in jobs(ACTOR):
    yawroot.rotation_euler = (0, 0, math.radians(YAW[d]))
    fd = os.path.join(TMP, f"{name}-{d}"); os.makedirs(fd, exist_ok=True)
    for i in range(n):
        frame_pose(name, i, n)
        sc.render.filepath = os.path.join(fd, f"f_{i + 1:03d}.png"); bpy.ops.render.render(write_still=True)
    tmpout = path + ".tmp.webp"
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", os.path.join(fd, "f_%03d.png"), "-vf", f"{EQ},tile={n}x1",
                        "-frames:v", "1", "-c:v", "libwebp", "-quality", "85", "-compression_level", "6", "-pix_fmt", "yuva420p", tmpout],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if r.returncode: print("Error ffmpeg", r.stdout); sys.exit(1)
    os.replace(tmpout, path); shutil.rmtree(fd, ignore_errors=True)
    print("SHEET", os.path.basename(path), os.path.getsize(path), flush=True)
shutil.rmtree(TMP, ignore_errors=True)
