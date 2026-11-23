# The student's chibi character v3 (boy "nam" / girl "nu" x stage tieuhoc / thcs / thpt / daihoc): anime-chibi game sprite style.
# One face language for all (big glossy eyes, small nose, blush), sculpted hair made of tapered curved clumps with a
# base-to-tip gradient and pale highlight streaks, sturdy stance. Same painted/toon material kit as kid2.py (lang_lib.py).
#   blender -b -P kid3.py -- <out_dir> still  nam-tieuhoc,nu-daihoc,...     512 px transparent stills (one Blender run)
#   blender -b -P kid3.py -- <out_dir> lineup nam                            the four stages on one common scale
#   actors3.py renders the sprite sheets with build_kid3() from here.
# Build from another script (lang_lib.py must already be loaded):
#   _k = open("kid3.py", encoding="utf-8").read(); exec(_k[_k.index("\n# ==== KID3 BUILDER"):_k.index("\n# ==== KID3 MAIN")])
#   K = build_kid3("nam", "daihoc")   K.g root, K.up upper-body pivot (rotate about hip via K.rot_up), K.hp head pivot (rest at K.hc),
#   K.arms / K.elbows / K.legs {-1,1: pivot} swing about X, K.tails [(pivot, sx)] hair that sways, K.eyes (blink), K.leg_len, K.top height
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
_ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if "lang_lib_loaded" not in globals():
    _OUT = _ARGV[0] if _ARGV else "."
    sys.argv = [sys.argv[0], "--", _OUT]
    exec(open(os.path.join(HERE, "lang_lib.py"), encoding="utf-8").read())
    lang_lib_loaded = True

# ==== KID3 BUILDER
import random, types
from mathutils import Matrix
_k2 = open(os.path.join(HERE, "kid2.py"), encoding="utf-8").read()
exec(_k2[_k2.index("\n# ==== KID2 BUILDER"):_k2.index("def build_kid2")])   # V, ptube, ell, rbox2, kp, vgrad, softdisc, fin, poly2d, hs/hn/tframe ...
STAGES = ["tieuhoc", "thcs", "thpt", "daihoc"]
SPEC = {
    "tieuhoc": dict(H=2.28, hr=(0.64, 0.58, 0.585), jaw=0.16, shw=0.285, tl=0.44, U=0.19, F=0.2, legr=0.092, hand=0.84, shoe=1.12, fl=1.26),
    "thcs":    dict(H=2.52, hr=(0.62, 0.565, 0.57), jaw=0.20, shw=0.32, tl=0.54, U=0.24, F=0.25, legr=0.098, hand=0.92, shoe=1.16, fl=1.32),
    "thpt":    dict(H=2.72, hr=(0.60, 0.55, 0.555), jaw=0.23, shw=0.37, tl=0.62, U=0.28, F=0.29, legr=0.106, hand=1.0, shoe=1.2, fl=1.37),
    "daihoc":  dict(H=2.90, hr=(0.60, 0.55, 0.55), jaw=0.26, shw=0.41, tl=0.68, U=0.31, F=0.32, legr=0.116, hand=1.06, shoe=1.25, fl=1.4),
}
JAW = 0.2
def hdeform(u):
    f = sstep(-0.05, -1.15, u.z); sx = 1 - JAW * f; sy = 1 - 0.14 * f
    return V(u.x * HR[0] * sx, u.y * HR[1] * sy, u.z * HR[2])
def _bez(p0, c, p1, t): return p0 * (1 - t) ** 2 + c * (2 * (1 - t) * t) + p1 * t * t

def build_kid3(kind="nam", stage="daihoc"):
    global HC, HR, JAW
    girl = kind == "nu"; si = STAGES.index(stage); S = SPEC[stage]; PFX = f"{kind}{stage}_"
    rnd = random.Random(7 + si * 13 + (101 if girl else 0))
    HR = S["hr"]; JAW = S["jaw"]; H = S["H"]; HC = V(0, 0, H - HR[2])
    chin = H - 2 * HR[2]
    shw = S["shw"] * (0.9 if girl else 1.0); legr = S["legr"] * (0.93 if girl else 1.0); FL = S["fl"]
    zs = chin - 0.04; HZ = zs - S["tl"]; U, Fa = S["U"], S["F"]; hsc = S["hand"]; armr = legr * 0.82
    def mk(name, *a, **kw): return kp(PFX + name, *a, **kw)
    def mt(name, *a, **kw): return toon(PFX + name, *a, **kw)
    def mf(name, h): return flat(PFX + name, h)
    K = types.SimpleNamespace(arms={}, elbows={}, legs={}, tails=[], eyes=[], base={}, parts={}, hc=HC.copy(), leg_len=HZ - 0.03, HZ=HZ, top=H, shw=shw)
    g = K.g = link(bpy.data.objects.new("kid", None))
    up = K.up = link(bpy.data.objects.new("up", None)); up.parent = g; _DEF[0] = up
    hp = K.hp = link(bpy.data.objects.new("head", None)); hp.parent = up; hp.location = HC
    def rot_up(eul, pivot=None):
        pv = pivot if pivot is not None else V(0, 0, HZ)
        up.rotation_euler = eul; up.location = pv - up.rotation_euler.to_matrix() @ pv
    K.rot_up = rot_up
    # ------------------------------------------------------------------ materials
    skin = mt("skin", "#ffd8bb", "#e78f80", "#fff0e0", edge=0.34)
    white = lambda n, **kw: mk(n, "#ffffff", "#a9b9e8", mid="#e3e9fb", hi="#ffffff", tex=("cotton", 3.2, 0.25), rim=0.6, **kw)
    shirt = white("shirt")
    navy = mk("navy", "#3a5db3", "#141f4d", mid="#294591", hi="#7d9be0", tex=("twill", 3.0, 0.3))
    navy2 = mk("navy2", "#2e4686", "#0f1938", mid="#1b2a5c", hi="#4a66a8")
    red = mk("red", "#f24a40", "#a31f28", mid="#d33534", hi="#ffa08e", ao=0.3)
    gold = mk("gold", "#ffd860", "#b8801c", mid="#e6ac38", hi="#fff4b0", ao=0.2)
    metal = mk("metal", "#f4f0e6", "#8d8aa0", mid="#c9c6d4", hi="#ffffff", ao=0.2)
    _sp = {("nam", "tieuhoc"): "#2a5cb4", ("nam", "thcs"): "#b8581c", ("nam", "thpt"): "#2a3550", ("nam", "daihoc"): "#2f3744", ("nu", "tieuhoc"): "#c0507a", ("nu", "thcs"): "#5e4cb8", ("nu", "thpt"): "#8a5a30", ("nu", "daihoc"): "#a8946e"}[(kind, stage)]
    strap = mk("strap", _sp, darker(_sp, 0.5), mid=darker(_sp, 0.78), hi="#ffffff", ao=0.3)
    sole = mk("sole", "#fffaf0", "#c9c2d8", mid="#ece6dc", hi="#ffffff", ao=0.3)
    shoe = mk("shoe", "#ffffff", "#b9c3e2", mid="#e4e9f6", hi="#ffffff", tex=("cotton", 3.5, 0.2))
    lace = mk("lace", "#fdfbff", "#aeb6d8", ao=0.0)
    lineb = mf("brow", "#3a2621"); lidm = mf("lid", "#241210"); lipm = mf("lip", "#a8453b"); crease = mf("crease", "#c78367"); whitef = mf("whitef", "#ffffff")
    # hair colours: the same student keeps a dark-brown family and gains colour with age
    HC_ = {("nam", "tieuhoc"): ("#483a58", "#171220", "#312840", "#b3a6e0"), ("nam", "thcs"): ("#4b3a50", "#181220", "#33283e", "#b8a8da"),
           ("nam", "thpt"): ("#4a3430", "#1c1214", "#352323", "#c9a28c"), ("nam", "daihoc"): ("#5b3d35", "#1f1214", "#40292a", "#e9b88e"),
           ("nu", "tieuhoc"): ("#55405a", "#1c1228", "#3a2b48", "#d0a8c8"), ("nu", "thcs"): ("#5a4056", "#1e1424", "#3e2c44", "#d4aac0"),
           ("nu", "thpt"): ("#47302d", "#1b1216", "#33232a", "#cfa7a8"), ("nu", "daihoc"): ("#5e3433", "#241218", "#43272c", "#f0a392")}[(kind, stage)]
    hair = mk("hair", HC_[0], HC_[1], mid=HC_[2], hi=HC_[3], grad=(0.78, 1.18), rim=0.7, ao=0.35)
    hairbase = mk("hairbase", HC_[1], darker(HC_[1], 0.7), mid=HC_[1], ao=0.5, rim=0.0)
    tipc = ("#d9a066", "#8a5430", "#bb7e4a", "#ffe0b4") if (not girl) else ("#f4a69a", "#a64a5c", "#d8707a", "#ffe0d8")
    hairtip = mk("hairtip", tipc[0], tipc[1], mid=tipc[2], hi=tipc[3], grad=(0.82, 1.2), rim=0.7, ao=0.35)
    hairhi = flat(PFX + "hairhi", HC_[3])
    # ------------------------------------------------------------------ head
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=56, v_segments=32, radius=1.0)
    for v in bm.verts: v.co = HC + hdeform(v.co.normalized())
    ho = mesh_obj("head", bm); fin(ho, skin, 0.017); attach(ho, hp, HC)
    ef = HR[0] / 0.5 * 0.92
    for sx in (-1, 1):
        c = hs(sx * 96, -6, 0.995)
        ell("ear", c, (0.04 * ef, 0.075 * ef, 0.095 * ef), skin, rot=(0, 0, sx * 0.25), ol=0.01, par=hp, off=HC)
        ell("earin", c + V(-sx * 0.012, -0.018, 0.0), (0.022 * ef, 0.04 * ef, 0.06 * ef), mk("earin", "#eaa18f", "#b86f62", ao=0.0), rot=(0, 0, sx * 0.25), par=hp, off=HC)
    ptube("neck", [V(0, 0.01, zs - 0.12), V(0, 0.0, chin + 0.16)], (0.125, 0.13), skin, ol=0.012, sides=14, cap=(0.0, 0.0))
    # ------------------------------------------------------------------ face (one language for the whole set)
    def facepivot(name, az, el, k=0.985):
        pv = link(bpy.data.objects.new(name, None)); pv.parent = hp; pv.location = hs(az, el, k) - HC; pv.rotation_euler = tframe(az, el); return pv
    EW, EH = [(0.158, 0.19), (0.152, 0.182), (0.146, 0.172), (0.142, 0.164)][si]
    if girl: EW *= 1.03; EH *= 1.05
    EAZ, EEL = 27, [-9, -8, -7, -6][si]
    iris_m = vgrad(PFX + "iris", [(0.0, "#28120b"), (0.34, "#5a3014"), (0.75, "#b66f2c"), (1.0, "#ffc46a")], -EH * 0.9, EH * 0.9)
    scl_m = vgrad(PFX + "sclera", [(0.0, "#e9dcdf"), (0.35, "#fffaf6"), (1.0, "#ffffff")], -EH, EH)
    limb = mf("limbus", "#1a0b06"); pupil = mf("pupil", "#0b0504")
    for sx in (-1, 1):
        pv = facepivot("eye", sx * EAZ, EEL); K.eyes.append(pv)
        def E(nm, c, r, m, rot=(0, 0, 0), seg=24):
            o = ell(nm, c, r, m, rot=rot, seg=seg); o.parent = pv; return o
        E("sclera", V(0, -0.004, 0), (EW, 0.012, EH), scl_m)
        ix = -sx * 0.006
        E("limbus", V(ix, -0.012, -0.006), (EW * 0.9, 0.01, EH * 0.93), limb)
        E("iris", V(ix, -0.017, -0.01), (EW * 0.8, 0.008, EH * 0.84), iris_m)
        E("pupil", V(ix, -0.021, -0.004), (EW * 0.4, 0.006, EH * 0.43), pupil)
        E("hl", V(ix - EW * 0.3, -0.027, EH * 0.36), (EW * 0.27, 0.005, EH * 0.27), whitef)
        E("hl2", V(ix + EW * 0.3, -0.027, -EH * 0.38), (EW * 0.13, 0.005, EH * 0.12), whitef)
        E("hl3", V(ix + EW * 0.1, -0.027, EH * 0.58), (EW * 0.08, 0.005, EH * 0.07), whitef)
        arc = []
        for th in range(176, 2, -12):
            a = math.radians(th); arc.append(V(sx * EW * 1.03 * math.cos(a), -0.02, EH * 1.0 * math.sin(a) - 0.004))
        arc.append(arc[-1] + V(sx * (0.035 if not girl else 0.052), 0.0, 0.016 if not girl else 0.026))
        lw = 0.02 if not girl else 0.024
        lw *= (1.0 + 0.1 * si)
        ptube("lid", arc, lambda t, lw=lw: lw * (0.35 + 0.8 * math.sin(math.pi * min(1.0, t * 0.95 + 0.05)) ** 0.7) * (1 - 0.7 * max(0, t - 0.85) / 0.15), lidm, sides=6, flat=1.0, ref=V(0, 1, 0), cap=(0.8, 0.5), par=pv)
        if girl:
            for dl, dz in ((0.0, 0.0), (0.024, 0.026), (0.046, 0.0)):
                ptube("lash", [arc[-3] + V(0, 0, dz * 0.2), arc[-2] + V(sx * dl, 0, 0.014 + dz), arc[-1] + V(sx * (0.03 + dl), 0, 0.03 + dz)], (0.0075, 0.0015), lidm, sides=4, ref=V(0, 1, 0), cap=(0, 0.6), par=pv)
        ptube("crease", [V(sx * EW * 0.8 * math.cos(math.radians(t_)), -0.012, EH * 1.2 * math.sin(math.radians(t_)) + 0.014) for t_ in range(150, 40, -22)], 0.005, crease, sides=4, ref=V(0, 1, 0), par=pv)
        ptube("lowlid", [V(sx * EW * math.cos(math.radians(t_)), -0.014, -EH * 0.95 * math.sin(math.radians(t_)) - 0.004) for t_ in range(200, 340, 20)], 0.004, crease, sides=4, ref=V(0, 1, 0), par=pv)
        bp = facepivot("brow", sx * 26, 20)
        bw_ = 0.13 if not girl else 0.115; tilt = [0.004, -0.006, -0.012, -0.018][si]
        bpts = [V(sx * (-0.02 + bw_ * t_), -0.012, 0.022 * math.sin(math.pi * (0.1 + t_ * 0.8)) + tilt * t_ + (0.012 * t_ if not girl else 0.005 * t_)) for t_ in (0, 0.2, 0.4, 0.6, 0.8, 1.0)]
        bth = (0.014 if not girl else 0.009) * (1.0 + 0.1 * si)
        ptube("brow", bpts, lambda t, b=bth: b * (0.55 + 0.6 * math.sin(math.pi * (0.15 + 0.7 * t))), lineb, sides=6, flat=1.0, ref=V(0, 1, 0), cap=(0.8, 0.8), par=bp)
        cp = facepivot("cheek", sx * 42, -26, 0.995)
        bl = ell("blush", V(0, -0.002, 0), (0.1, 0.004, 0.06), softdisc(PFX + "blush", "#ff7a90", 0.66 - 0.06 * si)); bl.parent = cp
        for hx in (-0.03, 0.0, 0.03):
            ptube("hatch", [V(hx - 0.009, -0.006, -0.014), V(hx + 0.009, -0.006, 0.016)], 0.003, mf("hatch", "#e8788a"), sides=4, ref=V(0, 1, 0), cap=(0.5, 0.5), par=cp)
    npv = facepivot("nose", 0, -24, 0.99)
    ell("nose", V(0, -0.012, 0), (0.03, 0.022, 0.025), skin, ol=0.006, par=npv).parent = npv
    ell("nosehl", V(-0.009, -0.032, -0.004), (0.009, 0.004, 0.007), whitef, par=npv).parent = npv
    ptube("nosesh", [V(-0.03, -0.008, -0.03), V(0, -0.012, -0.034), V(0.03, -0.008, -0.03)], 0.004, crease, sides=4, ref=V(0, 1, 0), par=npv)
    mpv = facepivot("mouth", 0, -46, 0.97)
    w = [0.1, 0.092, 0.085, 0.078][si]; d = [0.074, 0.066, 0.05, 0.036][si] * (0.92 if girl else 1.0)
    xs = [w * math.cos(math.pi * i / 16) for i in range(17)]
    top = [(x, 0.016 * (x / w) ** 2) for x in xs[::-1]]
    bot = [(x, 0.016 * (x / w) ** 2 - d * math.sqrt(max(0, 1 - (x / w) ** 2))) for x in xs]
    cav = top + bot[1:-1]
    poly2d("mouthcav", cav, mf("cav", "#7a2a2c"), mpv, out=0.014, th=0.008, R=0.56)
    poly2d("tongue", [(x * 0.6, -d * 0.5 + 0.016 * (x / w) ** 2) for x in xs[:9]] + [(x * 0.6, -d * 0.45 - d * 0.3 * math.sqrt(max(0, 1 - (x / w) ** 2))) for x in xs[9:]], mf("tongue", "#f27c86"), mpv, out=0.018, R=0.56)
    poly2d("teeth", [(-w * 0.86, 0.0118), (w * 0.86, 0.0118), (w * 0.8, -0.003 - d * 0.1), (-w * 0.8, -0.003 - d * 0.1)], whitef, mpv, out=0.0185, R=0.56)
    ptube("lipline", [V(x, -0.02, z_) for x, z_ in cav + [cav[0]]], 0.005, lipm, sides=4, ref=V(0, 1, 0), cap=(0.6, 0.6), par=mpv)
    for sx in (-1, 1):
        ptube("dimple", [V(sx * (w + 0.012), -0.006, 0.026), V(sx * (w + 0.024), -0.006, 0.014), V(sx * (w + 0.02), -0.006, 0.0)], 0.003, crease, sides=4, ref=V(0, 1, 0), par=mpv)
    # ------------------------------------------------------------------ hair kit
    HB = bmesh.new(); HT = bmesh.new(); HH = bmesh.new()
    def prof(t): return min(1.0, 0.5 + t * 3.0) * (1 - t) ** 0.72
    def prof2(t): return min(1.0, 0.55 + t * 4.0) * (1 - t ** 3.0) ** 0.7
    def strand(B, az0, el0, az1, el1, k0, k1, wd, bulge=0.05, n=8, flat=2.4, flick=0.0, bendaz=0.0, hi=0.0, pf=None):
        pts = []
        for i in range(n):
            t = i / (n - 1)
            az = lerp(az0, az1, t) + bendaz * math.sin(math.pi * t); el = lerp(el0, el1, t)
            pts.append(hs(az, el, lerp(k0, k1, t) + bulge * math.sin(math.pi * t) + flick * t ** 3))
        pf = pf or prof
        ptube("s", pts, lambda t: wd * pf(t), None, sides=6, flat=flat, ref=lambda i, p: (p - HC).normalized(), cap=(0.35, 0.55), bm=B)
        if hi:   # a pale streak on the lit side of the lock
            q = []
            for i in range(6):
                t = lerp(0.16, 0.7, i / 5); az = lerp(az0, az1, t) + bendaz * math.sin(math.pi * t); el = lerp(el0, el1, t)
                q.append(hs(az - 3.5, el + 2.5, lerp(k0, k1, t) + bulge * math.sin(math.pi * t) + flick * t ** 3 + wd * 0.5))
            ptube("hs", q, lambda t: wd * hi * math.sin(math.pi * (0.08 + 0.84 * t)) ** 0.8, None, sides=4, flat=2.0, ref=lambda i, p: (p - HC).normalized(), cap=(0.4, 0.4), bm=HH)
    def lockto(B, root, end, wd, bow=0.1, dropc=0.0, n=9, flat=2.2, hi=0.0, wob=0.0, ph=0.0, pf=None):
        """A lock from a surface point (az, el, k) to an absolute point: a quadratic curve bowed outwards from the head."""
        p0 = hs(*root); out = (p0 - HC).normalized(); c = (p0 + end) * 0.5 + out * bow + V(0, 0, -dropc)
        pts = []
        for i in range(n):
            t = i / (n - 1); p = _bez(p0, c, end, t)
            if wob: p = p + V(math.cos(math.radians(root[0])), math.sin(math.radians(root[0])), 0) * wob * math.sin(t * 5.5 + ph) * t
            pts.append(p)
        ptube("l", pts, lambda t: wd * (pf or prof2)(t), None, sides=6, flat=flat, ref=lambda i, p: V(out.x, out.y, 0) if abs(out.z) < 0.9 else V(0, -1, 0), cap=(0.35, 0.55), bm=B)
        if hi:
            ptube("lh", [p + (V(-out.y, out.x, 0) * -0.02) + out * (wd * 0.55) for p in pts[1:7]], lambda t: wd * hi * math.sin(math.pi * (0.1 + 0.8 * t)), None, sides=4, flat=2.0, ref=V(0, 0, 1), cap=(0.4, 0.4), bm=HH)
    def hang(B, az, el0, el1, drop, wd, k=1.12, flare=0.0, wave=0.0, ph=0.0, n=11, flat=2.2, hi=0.0, curl=0.0):
        """A lock down the back/side of the head from latitude el0 to el1, then falling `drop` with a flare and a wave."""
        pts = []; m = 5
        for i in range(m):
            t = i / (m - 1); pts.append(hs(az, lerp(el0, el1, t), k))
        base = pts[-1]; ox, oy = math.sin(math.radians(az)), -math.cos(math.radians(az)); px, py = math.cos(math.radians(az)), math.sin(math.radians(az))
        for j in range(1, n + 1):
            t = j / n
            pts.append(base + V(ox * flare * t ** 1.4 + px * wave * math.sin(t * 5.2 + ph) * t + ox * curl * t ** 3, oy * flare * t ** 1.4 + py * wave * math.sin(t * 5.2 + ph) * t + oy * curl * t ** 3, -drop * t))
        tot = len(pts)
        ptube("h", pts, lambda t: wd * min(1.0, 0.7 + t * 3.0) * (1 - max(0.0, (t - 0.55) / 0.45) ** 1.6) ** 0.7, None, sides=6, flat=flat, ref=lambda i, p: V(ox, oy, 0) if i > 3 else (p - HC).normalized(), cap=(0.35, 0.5), bm=B)
        if hi:
            q = [p + V(px * -0.022, py * -0.022, 0) + V(ox, oy, 0) * wd * 0.6 for p in pts[3:tot - 4]]
            ptube("hh", q, lambda t: wd * hi * math.sin(math.pi * (0.1 + 0.8 * t)) ** 0.8, None, sides=4, flat=2.0, ref=V(ox, oy, 0), cap=(0.4, 0.4), bm=HH)
    def hl_line(tab, az):
        az = abs(az) % 360; az = 360 - az if az > 180 else az
        for (a0, e0), (a1, e1) in zip(tab, tab[1:]):
            if az <= a1: return lerp(e0, e1, (az - a0) / (a1 - a0))
        return tab[-1][1]
    def cap(tab, vol=1.08):
        b = bmesh.new(); bmesh.ops.create_uvsphere(b, u_segments=44, v_segments=26, radius=1.0)
        for v in b.verts: u = v.co.normalized(); v.co = HC + hdeform(u) * vol + V(0, 0.012, 0.014)
        dead = []
        for f in b.faces:
            c = f.calc_center_median() - HC; az = math.degrees(math.atan2(c.x, -c.y)); el = math.degrees(math.asin(max(-1, min(1, c.z / c.length))))
            if el < hl_line(tab, az): dead.append(f)
        bmesh.ops.delete(b, geom=dead, context="FACES")
        for e in [e for e in b.edges if not e.link_faces]: b.edges.remove(e)
        for v in [v for v in b.verts if not v.link_faces]: b.verts.remove(v)
        o = mesh_obj("haircap", b); fin(o, hairbase, 0.013); attach(o, hp, HC)
    def radial(tab, layers, drift=12, tipfun=None, flick=0.05, hib=0.034, Bt=None, tipevery=0):
        for li, (cnt, k, up_, wd, fl) in enumerate(layers):
            for i in range(cnt):
                azn = (360.0 * i / cnt + rnd.uniform(-5, 5) + (8 if li % 2 else 0) + 180) % 360 - 180
                tip = hl_line(tab, azn) + up_ + rnd.uniform(-4, 4)
                if abs(azn) < 112:
                    tip = max(tip, hl_line(tab, azn) + 4)
                    if abs(azn) < 70: tip = max(tip, 44 if li else 40)   # leave the forehead to the fringe
                if tipfun: tip = tipfun(azn, tip, li)
                if tip > 68: continue
                B = Bt if (Bt is not None and tipevery and (i + li) % tipevery == 0) else HB
                strand(B, azn + rnd.uniform(-4, 4), 84, azn + (drift if azn > 0 else -drift * 0.8) + rnd.uniform(-5, 5), tip, k, k - 0.015, wd * rnd.uniform(0.92, 1.12), bulge=0.05, n=9, flat=fl, flick=flick, bendaz=rnd.uniform(-5, 5), hi=hib if li >= 1 else 0)
    def finish_hair(parent=None, off=None):
        for B, m, olw in ((HB, hair, 0.009), (HT, hairtip, 0.009), (HH, hairhi, 0)):
            if not B.verts: B.free(); continue
            bmesh.ops.recalc_face_normals(B, faces=B.faces[:])
            o = mesh_obj("hair", B); fin(o, m, olw); attach(o, parent or hp, HC if off is None else off); o.visible_shadow = False
    def crown_spikes(n, el0, el1, kout, wd, front=60, hi=0.05, B=None, up=0.0, tipB=None, tipn=0):
        """Bold clumps radiating round the crown and the back: the anime silhouette."""
        for j in range(n):
            az = -180 + j * (360.0 / n) + rnd.uniform(-5, 5)
            if abs(az) < front: continue
            Bj = tipB if (tipB is not None and tipn and j % tipn == 0) else (B or HB)
            strand(Bj, az, el0 + rnd.uniform(-4, 4), az * 1.03, el1 + rnd.uniform(-8, 6), 1.12, kout + rnd.uniform(-0.04, 0.06), wd * rnd.uniform(0.9, 1.1), bulge=0.04, n=7, flat=2.2, flick=0.1 + up, hi=hi, pf=prof)
    # ------------------------------------------------------------------ hair styles
    TAB_B = ((0, 24), (28, 24), (58, 21), (80, 19), (104, 14), (124, 0), (150, -30), (180, -34))
    FR = (-70, -52, -35, -18, 0, 18, 35, 52, 70)
    if not girl:
        if stage == "tieuhoc":
            cap(TAB_B, 1.10)
            radial(TAB_B, ((14, 1.10, 0, 0.13, 2.6), (10, 1.15, 22, 0.14, 2.5), (6, 1.19, 42, 0.13, 2.3)), flick=0.16, hib=0.05)
            for j in range(10):   # bold spikes radiating round the crown: the silhouette
                az = -180 + j * 36 + rnd.uniform(-5, 5)
                if abs(az) < 60: continue
                strand(HB, az, 52, az * 1.04, 20 + rnd.uniform(-8, 6), 1.12, 1.42, 0.13, bulge=0.04, n=7, flat=2.4, flick=0.1, hi=0.05, pf=prof)
            for i, az in enumerate(FR):   # chunky spiky fringe, tips pointing down and out
                sw = -12 if az < -10 else (14 if az > 4 else 4)
                te = 21 + 7 * math.exp(-((az + 12) / 24) ** 2) + rnd.uniform(-2.5, 2.5)
                strand(HB, az * 0.8, 72, az * 0.97 + sw, te, 1.15, 1.12, rnd.uniform(0.115, 0.135), bulge=0.05, n=8, flat=2.6, flick=0.05, bendaz=(-3 if az < 0 else 3), hi=0.035, pf=prof)
            for az, el0, el1, kk, wd in ((-20, 60, 86, 1.36, 0.075), (12, 62, 88, 1.42, 0.08), (-48, 56, 80, 1.3, 0.07)):   # ahoge tufts
                strand(HB, az, el0, az * 0.5, el1, 1.12, kk, wd, bulge=0.0, n=6, flat=2.2, flick=0.0, bendaz=8, pf=prof)
            for sx in (-1, 1):
                strand(HB, sx * 78, 38, sx * 92, 2, 1.13, 1.12, 0.09, bulge=0.04, n=6, hi=0.03)
                strand(HB, sx * 100, 20, sx * 120, -12, 1.12, 1.14, 0.085, bulge=0.03, n=6, flick=0.08)
            for az in range(-160, 161, 32):
                if abs(az) > 108: strand(HB, az, -4, az + rnd.uniform(-6, 6), -36, 1.08, 1.16, 0.075, bulge=0.02, n=5, flick=0.08)
        elif stage == "thcs":
            cap(TAB_B, 1.10)
            radial(TAB_B, ((14, 1.10, 0, 0.13, 2.6), (10, 1.15, 22, 0.14, 2.5), (7, 1.2, 42, 0.13, 2.3)), flick=0.14, hib=0.05)
            crown_spikes(10, 54, 22, 1.38, 0.13)
            for i, az in enumerate(FR):   # side-swept fringe, longer on the left, a few points
                sw = -22 if az < -6 else 16
                te = 18 + 14 * math.exp(-((az + 10) / 26) ** 2) + rnd.uniform(-3, 3)
                strand(HB, az * 0.78, 74, az * 0.98 + sw, te, 1.16, 1.11, rnd.uniform(0.11, 0.13), bulge=0.055, n=8, flat=2.6, flick=0.07, bendaz=(-4 if az < 0 else 4), hi=0.035)
            for az, el1, kk in ((-30, 36, 1.28), (4, 34, 1.3), (38, 32, 1.26)):   # bolder outer bangs
                strand(HB, az * 0.7, 76, az + (-18 if az < 0 else 14), el1 - 10, 1.18, 1.14, 0.12, bulge=0.06, n=8, flat=2.5, flick=0.08, hi=0.04)
            for az, el0, el1, kk, wd in ((-18, 58, 84, 1.38, 0.085), (16, 60, 86, 1.4, 0.085), (-54, 54, 78, 1.3, 0.075), (50, 56, 80, 1.3, 0.075)):
                strand(HB, az, el0, az * 0.55, el1, 1.12, kk, wd, bulge=0.0, n=6, flat=2.2, bendaz=8)
            for sx in (-1, 1):
                strand(HB, sx * 76, 40, sx * 92, 4, 1.13, 1.1, 0.095, bulge=0.04, n=6, hi=0.03)
                strand(HB, sx * 100, 22, sx * 122, -14, 1.12, 1.15, 0.09, bulge=0.03, n=6, flick=0.1)
            for az in range(-160, 161, 28):
                if abs(az) > 108: strand(HB, az, -4, az + rnd.uniform(-6, 6), -38, 1.08, 1.17, 0.08, bulge=0.02, n=5, flick=0.1)
        elif stage == "thpt":
            tab = ((0, 28), (28, 28), (58, 26), (80, 24), (104, 14), (124, 0), (150, -26), (180, -30))
            cap(tab, 1.11)
            radial(tab, ((14, 1.11, 0, 0.13, 2.6), (10, 1.16, 24, 0.14, 2.5), (7, 1.21, 44, 0.13, 2.3)), flick=0.16, tipevery=0, hib=0.05)
            crown_spikes(11, 58, 30, 1.46, 0.135, up=0.08)
            for i, az in enumerate(FR):   # textured, lifted fringe: points sweep up and forward
                te = 36 + 16 * math.exp(-((az + 6) / 28) ** 2) + rnd.uniform(-3, 3)
                strand(HB, az * 0.78, 70, az * 0.95 + (-14 if az < 0 else 18), te, 1.17, 1.27, rnd.uniform(0.115, 0.14), bulge=0.06, n=8, flat=2.6, flick=0.16, bendaz=(-4 if az < 0 else 4), hi=0.04)
            for az, el0, el1, kk, wd in ((-26, 54, 78, 1.42, 0.095), (10, 56, 82, 1.46, 0.1), (-58, 52, 74, 1.34, 0.085), (44, 52, 76, 1.36, 0.085), (-5, 40, 66, 1.38, 0.09)):
                strand(HB, az, el0, az * 0.6, el1, 1.13, kk, wd, bulge=0.0, n=6, flat=2.2, flick=0.05, bendaz=8)
            for sx in (-1, 1):
                strand(HB, sx * 78, 44, sx * 92, 12, 1.13, 1.1, 0.09, bulge=0.04, n=6, hi=0.03)
                strand(HB, sx * 100, 22, sx * 122, -10, 1.12, 1.15, 0.085, bulge=0.03, n=6, flick=0.1)
            for az in range(-160, 161, 28):
                if abs(az) > 108: strand(HB, az, -2, az + rnd.uniform(-6, 6), -34, 1.08, 1.17, 0.08, bulge=0.02, n=5, flick=0.12)
        else:   # daihoc: big swept quiff, bold spikes, caramel tips, long face-framing locks
            tab = ((0, 28), (28, 28), (58, 26), (80, 24), (104, 12), (124, -4), (150, -26), (180, -30))
            cap(tab, 1.13)
            radial(tab, ((15, 1.12, 0, 0.14, 2.6), (11, 1.18, 24, 0.15, 2.5), (8, 1.23, 44, 0.14, 2.3)), flick=0.18, hib=0.05)
            crown_spikes(12, 60, 36, 1.55, 0.145, up=0.14, tipB=HT, tipn=4)
            for i, az in enumerate(FR):   # swept-back pompadour: long strong strands lifting to the crown
                te = 40 + 22 * math.exp(-((az + 8) / 30) ** 2) + rnd.uniform(-3, 3)
                B = HT if i in (2, 6) else HB
                strand(B, az * 0.75, 66, az * 0.9 + (-16 if az < 0 else 20), te, 1.18, 1.36, rnd.uniform(0.125, 0.15), bulge=0.075, n=9, flat=2.1, flick=0.2, bendaz=(-5 if az < 0 else 5), hi=0.045)
            for az, el0, el1, kk, wd, B in ((-30, 48, 76, 1.5, 0.105, HB), (6, 52, 82, 1.56, 0.115, HB), (-60, 46, 70, 1.4, 0.095, HB), (42, 48, 74, 1.44, 0.1, HB), (-8, 34, 60, 1.46, 0.105, HB), (28, 30, 58, 1.4, 0.09, HB)):
                strand(B, az, el0, az * 0.6, el1, 1.14, kk, wd, bulge=0.0, n=7, flat=2.3, flick=0.08, bendaz=10, hi=0.04)
            for sx in (-1, 1):
                lockto(HB, (sx * 62, 40, 1.16), hs(sx * 62, -22, 1.16) + V(sx * 0.02, -0.04, -0.02), 0.085, bow=0.06, hi=0.03)    # face-framing locks
                strand(HB, sx * 100, 24, sx * 122, -10, 1.12, 1.17, 0.095, bulge=0.03, n=6, flick=0.12)
            for az in range(-160, 161, 24):
                if abs(az) > 104: strand(HT if az % 48 == 0 else HB, az, 0, az + rnd.uniform(-6, 6), -32, 1.08, 1.2, 0.09, bulge=0.02, n=5, flick=0.16)
        finish_hair()
    else:
        if stage == "tieuhoc":
            tab = ((0, 24), (28, 24), (58, 22), (80, 20), (104, 8), (124, -10), (150, -34), (180, -38))
            cap(tab, 1.10)
            radial(tab, ((15, 1.10, 0, 0.115, 2.6), (10, 1.15, 22, 0.12, 2.4), (6, 1.19, 40, 0.11, 2.2)), flick=0.03, hib=0.03)
            for i, az in enumerate((-66, -48, -32, -16, 0, 16, 32, 48, 66)):   # straight blunt bangs
                te = 25 + 3 * math.cos(math.radians(az * 1.4)) + rnd.uniform(-1.5, 1.5)
                strand(HB, az * 0.8, 72, az * 1.0, te, 1.15, 1.12, rnd.uniform(0.11, 0.125), bulge=0.05, n=8, flat=2.8, flick=0.0, hi=0.035, pf=prof2)
            for az, el0, el1, kk, wd in ((-16, 62, 84, 1.3, 0.05), (10, 64, 86, 1.34, 0.05)):
                strand(HB, az, el0, az * 0.5, el1, 1.12, kk, wd, bulge=0.0, n=5, flat=1.6, bendaz=6)
            for sx in (-1, 1):   # two pigtails on pivots, red ties
                tie = hs(sx * 84, 34, 1.16)
                pv = link(bpy.data.objects.new("tail", None)); pv.parent = hp; pv.location = tie - HC; K.tails.append((pv, sx))
                TB = bmesh.new(); TH = bmesh.new()
                for j in range(7):
                    a = 2 * math.pi * j / 7; ox, oy = math.cos(a) * 0.1, math.sin(a) * 0.08
                    Lh = rnd.uniform(0.62, 0.78)
                    pts = [V(sx * (0.0 + 0.18 * t ** 1.4) + ox * lerp(1, 0.55, t), oy * 0.5 + 0.03 * math.sin(t * 4), 0.02 - Lh * t) for t in (0, 0.1, 0.25, 0.42, 0.6, 0.78, 1.0)]
                    pts = [p + V(sx * 0.07 * math.sin(math.pi * 0.7 * (1 - p.z / (0.02 - Lh)) if False else 0), 0, 0) for p in pts]
                    ptube("tl", pts, lambda t: 0.09 * min(1, 0.7 + t * 2) * (1 - t ** 2.4) ** 0.62, None, sides=6, flat=1.7, ref=V(ox, oy, 0.001), cap=(0.35, 0.5), bm=TB)
                    if j % 2 == 0: ptube("th", [p + V(0, -0.014, 0) for p in pts[1:5]], lambda t: 0.02 * math.sin(math.pi * (0.1 + 0.8 * t)), None, sides=4, flat=2.0, ref=V(0, 1, 0), cap=(0.3, 0.3), bm=TH)
                for B, m, olw in ((TB, hair, 0.009), (TH, hairhi, 0)):
                    bmesh.ops.recalc_face_normals(B, faces=B.faces[:]); o = mesh_obj("tail", B); fin(o, m, olw); o.parent = pv; o.visible_shadow = False
                o = ptube("tie", [V(0.09 * math.cos(a), 0.075 * math.sin(a), 0.03) for a in [2 * math.pi * i / 16 for i in range(16)]], 0.036, red, ol=0.009, sides=8, closed=True, sub=1); o.parent = pv
                for q in (-1, 1):
                    ell("bowl", V(0.0, -0.07, 0.07) + V(q * 0.05, 0, 0), (0.05, 0.025, 0.04), red, ol=0.006, par=hp).parent = pv
        elif stage == "thcs":
            tab = ((0, 24), (28, 24), (58, 22), (80, 18), (104, 4), (124, -16), (150, -40), (180, -46))
            cap(tab, 1.11)
            radial(tab, ((16, 1.11, 0, 0.12, 2.6), (11, 1.16, 22, 0.125, 2.4), (7, 1.2, 40, 0.115, 2.2)), flick=0.0, hib=0.034)
            for i, az in enumerate(FR):   # side-parted bangs swept to the right
                sw = -16 if az < -4 else 10
                te = 22 + 12 * math.exp(-((az + 14) / 30) ** 2) + rnd.uniform(-2, 2)
                strand(HB, az * 0.78, 74, az * 0.98 + sw, te, 1.16, 1.12, rnd.uniform(0.115, 0.135), bulge=0.055, n=8, flat=2.7, flick=0.0, bendaz=(-4 if az < 0 else 4), hi=0.04, pf=prof2)
            for sx in (-1, 1):   # a bob: locks end at the jaw, flicking out
                for j, (az0, wd) in enumerate(((sx * 74, 0.12), (sx * 96, 0.125), (sx * 120, 0.12), (sx * 146, 0.115))):
                    hang(HB, az0, 40 if j == 0 else 30, -30, 0.18 + 0.05 * j, wd, k=1.12 + 0.02 * j, flare=0.1, curl=0.1, hi=0.035)
            for j in range(9):
                hang(HB, 108 + j * 18 + rnd.uniform(-3, 3), 66, -34, 0.22, 0.13, k=1.14, flare=0.1, curl=0.1)
            ell("clip", hs(-70, 34, 1.2), (0.065, 0.02, 0.04), gold, ol=0.006, rot=(0, 0, 0.5), par=hp, off=HC)
            ell("clipin", hs(-70, 34, 1.2) + V(0, -0.018, 0), (0.035, 0.012, 0.022), red, par=hp, off=HC)
        elif stage == "thpt":
            tab = ((0, 26), (28, 26), (58, 24), (80, 20), (104, 2), (124, -20), (150, -44), (180, -50))
            cap(tab, 1.11)
            radial(tab, ((16, 1.11, 0, 0.12, 2.6), (11, 1.16, 22, 0.125, 2.4), (7, 1.2, 40, 0.115, 2.2)), flick=0.0, hib=0.034)
            for i, az in enumerate((-72, -54, -38, -22, -8, 8, 22, 38, 54, 72)):   # centre-parted bangs falling to the sides
                sw = -22 if az < 0 else 22
                te = 14 + 14 * math.exp(-((abs(az) - 3) / 36) ** 2) * 0 + 12 * (1 - abs(az) / 80) + rnd.uniform(-2, 2)
                strand(HB, az * 0.7, 76, az * 1.0 + sw, te, 1.17, 1.11, rnd.uniform(0.115, 0.135), bulge=0.06, n=9, flat=2.7, flick=0.02, bendaz=(-3 if az < 0 else 3), hi=0.04, pf=prof2)
            # long straight back hair on a swaying pivot
            tie = hs(180, 6, 1.12)
            pv = link(bpy.data.objects.new("tail", None)); pv.parent = hp; pv.location = tie - HC; K.tails.append((pv, 1))
            BH = bmesh.new(); BHH = bmesh.new()
            for j in range(13):
                az = 118 + j * (124.0 / 12) + rnd.uniform(-3, 3)
                hang(BH, az, 60, -34, 0.92 + rnd.uniform(-0.1, 0.1), 0.125, k=1.15 + 0.02 * (j % 3), flare=0.08, wave=0.015, ph=j, hi=0.03 if j % 3 == 0 else 0)
            for B, m, olw in ((HB, hair, 0.009),):
                pass
            # the back hair joins HB parts built so far? keep separate so it can sway
            for B in (BH,):
                bmesh.ops.recalc_face_normals(B, faces=B.faces[:]); o = mesh_obj("backhair", B); fin(o, hair, 0.009); attach(o, pv, tie); o.visible_shadow = False
            for sx in (-1, 1):   # front locks falling over the shoulders
                for j, (az0, wd, ex, ey, ez) in enumerate(((sx * 68, 0.1, sx * 0.34, -0.1, 1.0), (sx * 80, 0.095, sx * 0.4, -0.04, 0.9))):
                    lockto(HB, (az0, 30, 1.14), V(ex, ey, zs - 0.26 - 0.1 * j), wd, bow=0.1, dropc=0.15, wob=0.01, ph=j, hi=0.03)
            ell("clip", hs(60, 38, 1.2), (0.06, 0.02, 0.035), whitef, ol=0.006, rot=(0, 0, -0.4), par=hp, off=HC)
        else:   # daihoc: long, wavy, voluminous, rose-copper highlights and ombre ends; curtain bangs, a lock over the shoulder
            tab = ((0, 30), (28, 30), (58, 28), (80, 20), (104, 0), (124, -24), (150, -48), (180, -54))
            cap(tab, 1.14)
            radial(tab, ((18, 1.13, 0, 0.13, 2.6), (13, 1.19, 24, 0.135, 2.4), (9, 1.24, 44, 0.125, 2.2)), flick=0.04, hib=0.04, Bt=HT, tipevery=5)
            for i, az in enumerate((-74, -56, -40, -24, -8, 8, 24, 40, 56, 74)):   # curtain bangs parted in the middle, swept apart
                sw = -26 if az < 0 else 26
                te = 12 + 18 * (1 - abs(az) / 80) + rnd.uniform(-2, 2)
                B = HT if i in (1, 8) else HB
                strand(B, az * 0.7, 78, az * 1.0 + sw, te, 1.18, 1.14, rnd.uniform(0.125, 0.15), bulge=0.07, n=9, flat=2.8, flick=0.05, bendaz=(-4 if az < 0 else 4), hi=0.045, pf=prof2)
            for az, el0, el1, kk, wd in ((-20, 58, 82, 1.34, 0.075), (14, 60, 84, 1.36, 0.075)):
                strand(HB, az, el0, az * 0.5, el1, 1.13, kk, wd, bulge=0.0, n=6, flat=1.8, bendaz=8)
            tie = hs(180, 6, 1.12)
            pv = link(bpy.data.objects.new("tail", None)); pv.parent = hp; pv.location = tie - HC; K.tails.append((pv, 1))
            BH = bmesh.new(); BT = bmesh.new(); BHH = bmesh.new()
            for j in range(15):
                az = 112 + j * (136.0 / 14) + rnd.uniform(-3, 3)
                hang(BT if j % 4 == 1 else BH, az, 60, -34, 1.0 + rnd.uniform(-0.12, 0.12), 0.14, k=1.17 + 0.02 * (j % 3), flare=0.14, wave=0.07, ph=j * 0.9, curl=0.12, hi=0.03 if j % 3 == 0 else 0)
            for B, m, olw in ((BH, hair, 0.009), (BT, hairtip, 0.009)):
                bmesh.ops.recalc_face_normals(B, faces=B.faces[:]); o = mesh_obj("backhair", B); fin(o, m, olw); attach(o, pv, tie); o.visible_shadow = False
            for sx in (-1, 1):
                for j, (az0, wd) in enumerate(((sx * 66, 0.11), (sx * 80, 0.1))):
                    end = V(sx * (0.40 + 0.02 * j), -0.14 + 0.05 * j, zs - 0.28 - 0.12 * j)
                    lockto(HT if j == 1 else HB, (az0, 32, 1.15), end, wd, bow=0.12, dropc=0.2, wob=0.05, ph=j * 2 + sx, hi=0.035)
            ell("clip", hs(-62, 40, 1.22), (0.07, 0.02, 0.04), mk("clippink", "#ff8aa8", "#b4466e", mid="#df678a", hi="#ffc4d4", ao=0.0), ol=0.006, rot=(0, 0, 0.5), par=hp, off=HC)
        finish_hair()
    # ------------------------------------------------------------------ torso
    z0t, z1t = HZ - 0.03, zs + 0.03; dc = shw / FL
    PR = [(0.0, 1.0 if si == 0 else 0.94), (0.3, 1.0 if si == 0 else (0.86 if girl else 0.92)), (0.72, 1.0), (1.0, 0.8)]
    def tprof(t):
        for (a0, v0), (a1, v1) in zip(PR, PR[1:]):
            if t <= a1: return lerp(v0, v1, (t - a0) / (a1 - a0))
        return PR[-1][1]
    def tdep(z): return dc * tprof(max(0.0, min(1.0, (z - z0t) / (z1t - z0t))))
    def tfront(x, z):
        dd = tdep(z); q = 1 - (x / (FL * dd)) ** 2
        return -dd * math.sqrt(max(q, 0.0)) - 0.004
    outfit = {("nam", "daihoc"): "bomber", ("nu", "daihoc"): "cardigan", ("nu", "thpt"): "aodai"}.get((kind, stage), "school")
    top_m = {"bomber": mk("bomber", "#34a58f", "#0f4a52", mid="#1f7c76", hi="#9ff0dc", rim=0.6, tex=("twill", 2.6, 0.25)),
             "cardigan": mk("cardi", "#c4aef4", "#6c58b8", mid="#9b85dc", hi="#efe2ff", rim=0.6, tex=("cotton", 2.4, 0.3)),
             "aodai": mk("aodai", "#ffffff", "#aeb4ec", mid="#e6e8fb", hi="#ffffff", rim=0.6, tex=("cotton", 3.0, 0.2))}.get(outfit, shirt)
    tee = mk("tee", "#ffffff", "#aebce8", mid="#e6ebfa", hi="#ffffff", rim=0.5)
    ptube("torso", [V(0, 0.005, lerp(z0t, z1t, i / 6)) for i in range(7)], lambda t: tdep(lerp(z0t, z1t, t)), top_m, ol=0.014, sides=26, flat=FL, ref=V(0, 1, 0), cap=(0.0, 0.0), sub=1)
    for sx in (-1, 1):
        ell("shoulder", V(sx * (shw - 0.015), 0.0, zs - 0.045), (armr * 1.3, armr * 1.35, armr * 1.3), top_m, ol=0.012)
    # ---- collar / neckline
    def ring(rx, ry, z, rad, mat, ol=0.008, n=22, y0=0.0, sub=1, sides=8):
        return ptube("ring", [V(rx * math.cos(a), ry * math.sin(a) + y0, z) for a in [2 * math.pi * i / n for i in range(n)]], rad, mat, ol=ol, sides=sides, ref=V(0, 0, 1), closed=True, sub=sub)
    if outfit == "school":
        for sx in (-1, 1):
            pts = [V(sx * 0.03, -0.185, zs + 0.0), V(sx * 0.12, -0.19, zs - 0.005), V(sx * 0.21, -0.14, zs - 0.0), V(sx * 0.25, -0.07, zs + 0.01)]
            pts2 = [V(sx * 0.04, -0.215, zs - 0.1), V(sx * 0.15, -0.22, zs - 0.095), V(sx * 0.24, -0.155, zs - 0.06), V(sx * 0.27, -0.08, zs - 0.03)]
            bmc = bmesh.new(); a_ = [bmc.verts.new(p) for p in pts]; b_ = [bmc.verts.new(p) for p in pts2]
            for i in range(3): bmc.faces.new((a_[i], a_[i + 1], b_[i + 1], b_[i]))
            bmesh.ops.recalc_face_normals(bmc, faces=bmc.faces[:]); o = mesh_obj("collar", bmc); fin(o, shirt, 0.01, 1, thick=0.026)
        ring(0.17, 0.16, zs + 0.01, 0.034, shirt, y0=0.0)
        if stage in ("tieuhoc", "thcs"):   # khan quang do: band, knot, two tails
            ring(0.2, 0.18, zs - 0.03, 0.04, red, ol=0.01)
            ell("knot", V(0, -0.22, zs - 0.07), (0.068, 0.055, 0.055), red, ol=0.008, sub=1)
            for sx, rot_ in ((-1, 0.28), (1, -0.3)):
                tl_ = 0.3 if stage == "tieuhoc" else 0.4
                bmc = bmesh.new(); vs = [bmc.verts.new(p) for p in (V(sx * 0.02, -0.24, zs - 0.07), V(sx * 0.11, -0.23, zs - 0.08), V(sx * 0.15, -0.255, zs - 0.07 - tl_), V(sx * 0.03, -0.275, zs - 0.07 - tl_ * 0.9))]
                bmc.faces.new(vs); bmesh.ops.subdivide_edges(bmc, edges=bmc.edges[:], cuts=3, use_grid_fill=True)
                bmesh.ops.recalc_face_normals(bmc, faces=bmc.faces[:]); o = mesh_obj("scarftail", bmc); fin(o, red, 0.009, 1, thick=0.02)
        else:   # open collar, Doan badge on the chest pocket
            ring(0.12, 0.11, zs - 0.04, 0.0, shirt) if False else None
        px, pz = shw * 0.4, zs - 0.34 * (S["tl"] / 0.5)
        pw, ph = 0.09 + 0.01 * si, 0.1 + 0.01 * si
        if not (girl and stage != "tieuhoc") or True:
            rbox2("pocket", V(px, tfront(px, pz) - 0.006, pz), (pw * 2, 0.014, ph * 2), shirt, bev=0.007, ol=0.006, sub=0, seg=2)
            bgz = V(px, tfront(px, pz) - 0.022, pz + 0.012)
            ell("badge", bgz, (0.052, 0.009, 0.06), mk("badge", "#e84b43", "#9c2428", mid="#cf3a36", hi="#ff9b8c", ao=0.0), ol=0.006)
            ell("badgering", bgz + V(0, -0.006, 0), (0.038, 0.005, 0.044), gold)
            ell("badgein", bgz + V(0, -0.011, 0), (0.028, 0.004, 0.032), mk("badgein", "#2d62c9", "#183a82", ao=0.0, rim=0.0) if stage in ("tieuhoc", "thcs") else mk("badgered", "#e8362d", "#9c2428", ao=0.0, rim=0.0))
            star = bmesh.new(); sv = []
            for i in range(10):
                a = math.pi / 2 + i * math.pi / 5; r_ = 0.022 if i % 2 == 0 else 0.009; sv.append(star.verts.new(V(px + r_ * math.cos(a), bgz.y - 0.014, bgz.z + 0.0 + r_ * math.sin(a))))
            f_ = star.faces.new(sv)
            if f_.normal.y > 0: f_.normal_flip()
            o = mesh_obj("star", star); o.data.materials.append(gold); o.modifiers.new("t", "SOLIDIFY").thickness = 0.004
        for z in (zs - 0.1, zs - 0.28 * (S["tl"] / 0.5), zs - 0.44 * (S["tl"] / 0.5)):
            ell("button", V(0.0, tfront(0, z) - 0.008, z), (0.014, 0.006, 0.014), mk("btn", "#ffffff", "#9aa3c8", ao=0.0), ol=0.004)
        ptube("placket", [V(0.0, tfront(0, z) - 0.003, z) for z in (zs - 0.05, zs - 0.3, HZ + 0.05)], 0.0045, mk("plk", "#e8ecf8", "#a8b3d6", ao=0.0), sides=4, ref=V(1, 0, 0))
    elif outfit == "bomber":
        ring(0.17, 0.15, zs + 0.015, 0.045, mk("rib", "#1d6a66", "#0b3036", mid="#154d4e", hi="#6fd0c0", ao=0.3), ol=0.01, sides=8)
        ring(0.15, 0.13, zs + 0.03, 0.026, tee, ol=0.007, sides=8)
        ptube("zip", [V(0.0, tfront(0, z) - 0.006, z) for z in (zs - 0.02, zs - 0.25, HZ + 0.12)], 0.007, metal, sides=5, ref=V(1, 0, 0))
        ell("zippull", V(0.0, tfront(0, zs - 0.07) - 0.014, zs - 0.09), (0.014, 0.008, 0.032), gold, ol=0.004)
        rib = mk("rib2", "#1d6a66", "#0b3036", mid="#154d4e", hi="#6fd0c0", ao=0.3)
        ring(shw * 0.92, dc * 0.88, HZ - 0.015, 0.05, rib, ol=0.01, n=30, y0=0.005)
        for sx in (-1, 1):   # chest patch + pocket flap
            pass
        px, pz = shw * 0.42, zs - 0.26
        ell("patch", V(px, tfront(px, pz) - 0.012, pz), (0.058, 0.008, 0.058), mk("patch", "#ff8a2a", "#b04a10", mid="#e06a1c", hi="#ffd0a0", ao=0.0), ol=0.006)
        ell("patchin", V(px, tfront(px, pz) - 0.019, pz), (0.03, 0.005, 0.03), whitef)
        for sx in (-1, 1):
            rbox2("flap", V(sx * shw * 0.55, tfront(sx * shw * 0.55, HZ + 0.12) - 0.01, HZ + 0.13), (0.15, 0.014, 0.04), top_m, bev=0.008, ol=0.005, sub=0, rot=(0, 0, sx * 0.22), seg=2)
    elif outfit == "cardigan":
        ring(0.16, 0.15, zs + 0.015, 0.032, tee, ol=0.008)
        # open front: white tee strip between two soft knit edges
        sx_ = shw * 0.16
        pts = [V(0, tfront(0, z) - 0.004, z) for z in (zs - 0.02, zs - 0.15, zs - 0.3, HZ + 0.02)]
        ptube("teestrip", pts, lambda t: 0.105 - 0.03 * t, tee, ol=0.0, sides=12, flat=1.0, ref=V(1, 0, 0), cap=(0.4, 0.5))
        for sx in (-1, 1):
            ptube("cardiedge", [V(sx * (0.12 - 0.015 * t), tfront(sx * 0.12, z) - 0.01, z) for t, z in zip((0, 0.33, 0.66, 1.0), (zs - 0.02, zs - 0.15, zs - 0.3, HZ + 0.02))], 0.03, top_m, ol=0.01, sides=8, ref=V(1, 0, 0), cap=(0.5, 0.5), sub=1)
            for j, zb in enumerate((zs - 0.12, zs - 0.26)):
                pass
        for zb in (zs - 0.14, zs - 0.28):
            ell("cbtn", V(0.0, tfront(0, zb) - 0.03, zb), (0.017, 0.007, 0.017), mk("cbtn", "#fff4ea", "#c8a8a0", ao=0.0), ol=0.004) if False else None
        ring(shw * 0.95, dc * 0.9, HZ - 0.005, 0.042, mk("cardihem", "#b8a0ee", "#5e4aa6", mid="#8c76d4", hi="#e8dcff", ao=0.3), ol=0.01, n=30, y0=0.005)
    elif outfit == "aodai":
        ring(0.14, 0.13, zs + 0.03, 0.05, top_m, ol=0.01, sides=8)   # mandarin stand collar
        ptube("collarbutt", [V(0.0, -0.13, zs + 0.0), V(0.07, -0.12, zs - 0.02)], 0.018, top_m, ol=0.006, sides=6)
        # diagonal fastening from the collar over the right shoulder to the waist under the arm, with small buttons
        dpts = [V(sx_ * 1.0, 0, 0) for sx_ in (0,)]
        diag = [V(-0.03 + 0.0, tfront(0.0, zs - 0.01) - 0.005, zs - 0.01)]
        for t in (0.25, 0.5, 0.75, 1.0):
            x = lerp(0.0, -shw * 0.88, t) * -1 * -1; z = lerp(zs - 0.01, HZ + 0.1, t)
            x = lerp(0.04, shw * 0.9, t) * (-1)   # runs to the wearer's right side (-x)
            diag.append(V(x, tfront(x, z) - 0.005, z))
        ptube("diag", diag, 0.0055, mk("seam", "#cfd4f3", "#8e95d6", ao=0.0), sides=4, ref=V(0, 1, 0))
        for p in diag[1:]:
            ell("abtn", p + V(0, -0.008, 0), (0.014, 0.007, 0.014), gold, ol=0.003)
        for sx in (-1, 1):   # raglan seams
            ptube("raglan", [V(sx * 0.08, tfront(sx * 0.08, zs - 0.01) - 0.004, zs - 0.01), V(sx * shw * 0.8, tfront(sx * shw * 0.8, zs - 0.12) - 0.004, zs - 0.14)], 0.004, mk("seam", "#cfd4f3", "#8e95d6", ao=0.0), sides=4, ref=V(0, 1, 0))
    # waist fabric folds for plain shirts
    if outfit in ("school", "bomber"):
        def fold(zz0, zz1, x0, x1, wd=0.011):
            pts = []
            for i in range(7):
                t = i / 6; x = lerp(x0, x1, t); z = lerp(zz0, zz1, t); pts.append(V(x, tfront(x, z) - 0.002, z))
            ptube("fold", pts, lambda t: wd * math.sin(math.pi * (0.05 + 0.9 * t)) ** 0.6, top_m, sides=6, ref=V(0, 1, 0), cap=(0.4, 0.4))
        for zz0, zz1, x0, x1 in ((HZ + 0.1, HZ + 0.13, -shw * 0.75, -shw * 0.1), (HZ + 0.08, HZ + 0.11, shw * 0.1, shw * 0.78), (HZ + 0.2, HZ + 0.17, -shw * 0.8, -shw * 0.4)):
            fold(zz0, zz1, x0, x1)
    # ------------------------------------------------------------------ lower body
    hipx = shw * 0.43
    jean = mk("jean", "#5b86d2", "#243a7e", mid="#3c5fb0", hi="#b6cdf6", tex=("twill", 3.0, 0.3))
    skirt_m = {"tieuhoc": navy, "thcs": navy, "daihoc": mk("skirt", "#5b86d2", "#243a7e", mid="#3c5fb0", hi="#b6cdf6", tex=("twill", 3.0, 0.3))}.get(stage, navy)
    pantsw = mk("pantsw", "#ffffff", "#aeb4ec", mid="#e6e8fb", hi="#ffffff", tex=("cotton", 3.0, 0.2), rim=0.5)
    hipw, hipd = shw * 0.95, dc * 0.92
    if not girl:
        pm = jean if stage == "daihoc" else navy
        ell("hips", V(0, 0.01, HZ + 0.015), (hipw * 1.02, hipd * 1.08, 0.15 + 0.01 * si), pm, ol=0.014, sub=1)
        if stage != "tieuhoc":
            ring(hipw * 0.96, hipd * 0.98, HZ + 0.09, 0.022, mk("belt", "#5a3f30", "#2c1c14", mid="#43301f", hi="#9a7458", ao=0.2), ol=0.006, n=34, y0=0.01, sub=0, sides=6)
            rbox2("buckle", V(0, hipd * 1.0 + 0.0, HZ + 0.09), (0.07, 0.014, 0.05), metal, bev=0.008, ol=0.005, sub=0, seg=2)
            for ax in (-0.17, 0.17): rbox2("loop", V(ax, -hipd * 0.985 + 0.0, HZ + 0.09), (0.016, 0.014, 0.065), mk("belt", "#5a3f30", "#2c1c14"), bev=0.004, sub=0, seg=1)
    else:
        if outfit != "aodai":
            slen = {"tieuhoc": 0.3, "thcs": 0.4, "daihoc": 0.36}[stage]
            N = 22 if stage != "daihoc" else 30; M = 144; rows = 12; z0, z1 = HZ + 0.06, HZ + 0.06 - slen
            rx0, ry0 = hipw * 0.92, hipd * 1.0; rx1, ry1 = hipw * 1.4, hipd * 1.5
            bmk = bmesh.new(); grid = []
            for j in range(rows + 1):
                t = j / rows; z = lerp(z0, z1, t); rx = lerp(rx0, rx1, t ** 0.8); ry = lerp(ry0, ry1, t ** 0.8); amp = lerp(0.006, 0.07, t)
                row = []
                for i in range(M):
                    th = 2 * math.pi * i / M; pl = abs(math.sin(N * th / 2)); k = 1 + amp * (pl - 0.5) * 2
                    row.append(bmk.verts.new(V(rx * k * math.cos(th), ry * k * math.sin(th) + 0.01, z)))
                grid.append(row)
            for j in range(rows):
                for i in range(M): bmk.faces.new((grid[j][i], grid[j][(i + 1) % M], grid[j + 1][(i + 1) % M], grid[j + 1][i]))
            bmesh.ops.recalc_face_normals(bmk, faces=bmk.faces[:]); o = mesh_obj("skirt", bmk); fin(o, skirt_m, 0.012, 0, thick=0.014)
            ring(hipw * 0.93, hipd * 1.0, HZ + 0.07, 0.026, navy2 if stage != "daihoc" else mk("waistb", "#3c5fb0", "#16265c", mid="#294a96", hi="#7a9be0"), ol=0.008, n=34, y0=0.01, sub=0, sides=6)
            ell("hipsg", V(0, 0.01, HZ + 0.03), (hipw * 0.9, hipd * 0.98, 0.13), skirt_m)
        else:
            ell("hipsg", V(0, 0.01, HZ + 0.03), (hipw * 0.9, hipd * 0.98, 0.13), pantsw)
            hem = 0.36
            for front in (True, False):
                rows, cols = 12, 9; bmk = bmesh.new(); grid = []
                for j in range(rows + 1):
                    t = j / rows; z = lerp(HZ + 0.13, hem, t); row = []
                    ex = lerp(hipw * 0.92, hipw * 1.5, t ** 0.9); ey = lerp(hipd * 1.0, hipd * 1.5, t ** 0.9) + 0.012
                    for i in range(cols):
                        u = lerp(-0.64, 0.64, i / (cols - 1)); x = ex * math.sin(u * math.pi * 0.5 * 1.08)
                        yy = ey * math.cos(u * math.pi * 0.5 * 1.08)
                        zz = z - 0.045 * (1 - u * u) * t ** 1.5
                        row.append(bmk.verts.new(V(x, (-yy if front else yy) + 0.01, zz)))
                    grid.append(row)
                for j in range(rows):
                    for i in range(cols - 1):
                        bmk.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]) if front else (grid[j][i + 1], grid[j][i], grid[j + 1][i], grid[j + 1][i + 1]))
                bmesh.ops.recalc_face_normals(bmk, faces=bmk.faces[:]); o = mesh_obj("aopanel", bmk); fin(o, top_m, 0.012, 1, thick=0.016)
                ptube("panelfold", [V(0, (-1 if front else 1) * (hipd * 1.2) + 0.01, z_) for z_ in (HZ + 0.1, HZ - 0.15, hem + 0.1)], 0.01, top_m, sides=6, ref=V(1, 0, 0), cap=(0.4, 0.4))
                ptube("hemtrim", [V(hipw * 1.5 * math.sin(u_ * math.pi * 0.5 * 1.08), (-1 if front else 1) * (hipd * 1.5 + 0.014) * math.cos(u_ * math.pi * 0.5 * 1.08) + 0.01, hem - 0.045 * (1 - u_ * u_) + 0.012) for u_ in [(-0.64 + 1.28 * q / 8) for q in range(9)]], 0.013, mk("trim", "#8fb4f0", "#3f62b4", mid="#6b90d8", hi="#d6e6ff", ao=0.0), sides=4, ref=V(0, 0, 1), cap=(0.4, 0.4))
            ring(hipw * 0.9, hipd * 0.98, HZ + 0.1, 0.014, mk("sash", "#cfd4f3", "#8e95d6", ao=0.0), ol=0.0, n=34, y0=0.01, sub=0, sides=4)
    # legs (pivot at the hip), then sneakers
    leg_h = HZ - 0.1
    for sx in (-1, 1):
        lg = link(bpy.data.objects.new("leg", None)); lg.parent = g; lg.location = (sx * hipx, 0.01, HZ); K.legs[sx] = lg
        def Lp(o): o.parent = lg; return o
        if (not girl and stage == "tieuhoc"):   # shorts, bare legs and socks
            ptube("trouser", [V(0, 0, -0.02), V(0, 0, -0.18), V(0, -0.004, -0.3)], (legr * 1.5, legr * 1.4), navy, ol=0.014, sides=16, ref=V(1, 0, 0), cap=(0.0, 0.0), sub=1, par=lg)
            ptube("hem", [V(legr * 1.4 * math.cos(a), legr * 1.4 * math.sin(a), -0.3) for a in [2 * math.pi * i / 20 for i in range(20)]], 0.014, navy2, ol=0.006, sides=6, ref=V(0, 0, 1), closed=True, par=lg)
            legbare = -0.28
        elif not girl:
            pm = jean if stage == "daihoc" else navy
            ptube("trouser", [V(0, 0, -0.02), V(0, 0, leg_h * 0.35), V(0, -0.008, leg_h * 0.7), V(0, 0, leg_h - 0.02)] if False else [V(0, 0, -0.02), V(0, 0, -leg_h * 0.35), V(0, -0.008, -leg_h * 0.7), V(0, 0, -leg_h + 0.06)],
                  (legr * 1.35, legr * (1.2 if stage != "thpt" else 1.1)), pm, ol=0.014, sides=16, ref=V(1, 0, 0), cap=(0.0, 0.0), sub=1, par=lg)
            ptube("crease", [V(0, -legr * 1.3, -0.12), V(0, -legr * 1.25, -leg_h * 0.5), V(0, -legr * 1.1, -leg_h + 0.1)], 0.006, mk("crs", "#6a94da", "#27396f", ao=0.0), sides=4, ref=V(1, 0, 0), par=lg) if stage != "daihoc" else None
            cuff = mk("cuff", "#8eb2ea", "#3552a0", mid="#5f86d0", hi="#d0e0fc", ao=0.2) if stage == "daihoc" else navy2
            ptube("hem", [V(legr * 1.2 * math.cos(a), legr * 1.2 * math.sin(a), -leg_h + 0.07) for a in [2 * math.pi * i / 20 for i in range(20)]], 0.02 if stage == "daihoc" else 0.014, cuff, ol=0.006, sides=6, ref=V(0, 0, 1), closed=True, par=lg)
            for zz, ln in ((-leg_h * 0.5, 0.08), (-leg_h * 0.78, 0.06)):
                ptube("wr", [V(-ln, -legr * 1.3, zz + 0.01), V(0, -legr * 1.35, zz), V(ln, -legr * 1.3, zz + 0.012)], 0.007, pm, sides=4, ref=V(0, 1, 0), par=lg)
            legbare = None
        elif outfit == "aodai":
            ptube("pant", [V(0, 0, -0.1), V(0, 0, -leg_h * 0.5), V(0, 0, -leg_h + 0.08)], lambda t: lerp(legr * 1.2, legr * 1.75, t ** 1.5), pantsw, ol=0.013, sides=14, ref=V(1, 0, 0), cap=(0.0, 0.0), sub=1, par=lg)
            legbare = None
        else:
            legbare = -(0.06 + (0.3 if stage == "tieuhoc" else 0.4 if stage == "thcs" else 0.36)) * 0.9
        if legbare is not None:
            ptube("legskin", [V(0, 0, legbare), V(0, -0.004, legbare - (leg_h + legbare) * 0.45), V(0, 0.0, -leg_h * 0.88), V(0, 0, -leg_h + 0.04)], lambda t: lerp(legr * 0.96, legr * 0.72, t) + 0.005 * math.sin(math.pi * min(1, t * 1.6)) ** 2, skin, ol=0.012, sides=12, ref=V(1, 0, 0), cap=(0.0, 0.0), sub=1, par=lg)
            sock_h = 0.16 if stage != "daihoc" else 0.1
            ptube("sock", [V(0, 0, -leg_h + 0.02 + sock_h), V(0, 0, -leg_h + 0.03)], legr * 0.78, shirt, ol=0.01, sides=12, ref=V(1, 0, 0), cap=(0.0, 0.0), par=lg)
            ptube("sockcuff", [V(legr * 0.8 * math.cos(a), legr * 0.8 * math.sin(a), -leg_h + 0.03 + sock_h) for a in [2 * math.pi * i / 16 for i in range(16)]], 0.014, mk("scuff", "#eef0fa", "#aab5da", ao=0.0), ol=0.005, sides=6, ref=V(0, 0, 1), closed=True, par=lg)
        # sneaker
        yaw = sx * 0.12; ssc = S["shoe"]
        grp = link(bpy.data.objects.new("shoe", None)); grp.parent = lg; grp.location = (0, 0, -HZ); grp.rotation_euler = (0, 0, yaw); grp.scale = (ssc, ssc, ssc)
        accent = {"daihoc": ("#ff8a2a" if not girl else "#a58bf0"), "thpt": "#4a66a8", "thcs": "#e84b43", "tieuhoc": "#f06f95" if girl else "#4a66a8"}[stage]
        acc = mk("acc", accent, darker(accent, 0.55), mid=darker(accent, 0.8), hi="#ffffff", ao=0.2)
        up_pts = [V(0, 0.09, 0.105), V(0, 0.035, 0.115), V(0, -0.06, 0.095), V(0, -0.15, 0.072), V(0, -0.2, 0.056)]
        ptube("upper", up_pts, lambda t: lerp(0.082, 0.045, t ** 1.4), shoe, ol=0.012, sides=14, flat=1.12, ref=V(1, 0, 0), cap=(0.5, 0.5), sub=1, par=grp)
        ell("toecap", V(0, -0.19, 0.052), (0.066, 0.062, 0.046), sole, ol=0.008, par=grp, sub=1)
        rbox2("sole", V(0, -0.045, 0.018), (0.14, 0.38, 0.034), sole, bev=0.018, ol=0.01, sub=1, par=grp)
        ptube("scollar", [V(0.056 * math.cos(a), 0.07 + 0.058 * math.sin(a), 0.128) for a in [2 * math.pi * i / 18 for i in range(18)]], 0.016, shoe, ol=0.007, sides=6, ref=V(0, 0, 1), closed=True, par=grp)
        ell("tongue", V(0, -0.012, 0.128), (0.036, 0.05, 0.016), shoe, rot=(-0.35, 0, 0), ol=0.005, par=grp)
        for i, y in enumerate((-0.0, -0.045, -0.09, -0.13)):
            ptube("lace", [V(-0.044, y + 0.012, 0.118 - i * 0.011), V(0, y - 0.004, 0.126 - i * 0.012), V(0.044, y + 0.012, 0.118 - i * 0.011)], 0.0075, lace, sides=5, ref=V(0, 1, 0), ol=0.003, par=grp)
        for sx2 in (-1, 1):
            ptube("stripe", [V(sx2 * 0.068, 0.07, 0.07), V(sx2 * 0.07, -0.01, 0.075), V(sx2 * 0.062, -0.1, 0.06), V(sx2 * 0.045, -0.15, 0.05)], 0.012, acc, sides=5, ref=V(0, 0, 1), par=grp)
    # ------------------------------------------------------------------ arms: shoulder pivot, elbow pivot, hand
    long_sleeve = outfit in ("bomber", "cardigan", "aodai")
    slv_r = armr * (1.55 if outfit == "bomber" else 1.3 if outfit != "school" else 1.42)
    rib_c = mk("rib3", "#1d6a66", "#0b3036", mid="#154d4e", hi="#6fd0c0", ao=0.3) if outfit == "bomber" else top_m
    for sx in (-1, 1):
        a = link(bpy.data.objects.new("arm", None)); a.parent = up; a.location = (sx * shw, 0.0, zs - 0.07); a.rotation_euler = (0, -sx * 0.13, 0); K.arms[sx] = a
        el = link(bpy.data.objects.new("elbow", None)); el.parent = a; el.location = (0, 0, -U); K.elbows[sx] = el
        sl_u = 1.0 if long_sleeve else 0.82
        ptube("usleeve", [V(0, 0, 0.05), V(0, 0, -U * 0.5), V(0, 0, -U * sl_u)], (slv_r * 1.02, slv_r), top_m, ol=0.012, sides=14, ref=V(1, 0, 0), cap=(0.0, 0.0), sub=1, par=a)
        if not long_sleeve:
            ptube("usleevehem", [V(slv_r * math.cos(q), slv_r * math.sin(q), -U * sl_u) for q in [2 * math.pi * i / 16 for i in range(16)]], 0.014, mk("hem", "#ffffff", "#aab6dc", ao=0.2), ol=0.006, sides=6, ref=V(0, 0, 1), closed=True, par=a)
            ptube("uarm", [V(0, 0, -U * sl_u + 0.02), V(0, 0, -U - 0.02)], (armr * 0.98, armr * 0.9), skin, ol=0.011, sides=10, ref=V(1, 0, 0), cap=(0.0, 0.0), par=a)
        ell("elbowball", V(0, 0, 0), (armr * 0.98, armr * 0.98, armr * 0.98), top_m if long_sleeve else skin, ol=0.01, par=el, sub=0).location = V(0, 0, 0)
        if long_sleeve:
            ptube("fsleeve", [V(0, 0, 0.0), V(0, -0.004, -Fa * 0.5), V(0, -0.0, -Fa + 0.02)], (slv_r * 0.98, armr * (1.12 if outfit == "bomber" else 1.0)), top_m, ol=0.012, sides=14, ref=V(1, 0, 0), cap=(0.0, 0.0), sub=1, par=el)
            cr_ = armr * (1.12 if outfit == "bomber" else 1.0)
            ptube("fcuff", [V(cr_ * 1.0 * math.cos(q), cr_ * math.sin(q), -Fa + 0.02) for q in [2 * math.pi * i / 16 for i in range(16)]], 0.02 if outfit == "bomber" else 0.012, rib_c, ol=0.006, sides=6, ref=V(0, 0, 1), closed=True, par=el)
            ptube("farm", [V(0, 0, -Fa + 0.02), V(0, -0.0, -Fa - 0.03)], armr * 0.8, skin, ol=0.01, sides=10, ref=V(1, 0, 0), cap=(0.0, 0.0), par=el)
        else:
            ptube("farm", [V(0, 0, 0.0), V(0, -0.004, -Fa * 0.5), V(0, 0, -Fa - 0.03)], (armr * 0.95, armr * 0.78), skin, ol=0.011, sides=10, ref=V(1, 0, 0), cap=(0.0, 0.0), sub=1, par=el)
        hd = link(bpy.data.objects.new("hand", None)); hd.parent = el; hd.location = (0, 0, -Fa - 0.02); hd.rotation_euler = (-0.18, 0, -sx * 0.1)
        hs_ = hsc
        ell("palm", V(0, -0.004, -0.04 * hs_), (0.064 * hs_, 0.038 * hs_, 0.072 * hs_), skin, ol=0.009, par=hd, sub=1).parent = hd
        for fi, fx in enumerate((-0.036, -0.012, 0.012, 0.036)):
            ln = (0.062, 0.078, 0.072, 0.056)[fi] * hs_; cr = 0.02 * hs_; fx *= hs_
            pts = [V(fx, 0.0, -0.09 * hs_), V(fx * 1.05, -cr * 0.4, -0.09 * hs_ - ln * 0.5), V(fx * 1.08, -cr * 1.5, -0.09 * hs_ - ln * 0.95), V(fx * 1.08, -cr * 2.6, -0.09 * hs_ - ln * 1.1)]
            ptube("finger", pts, (0.02 * hs_, 0.014 * hs_), skin, ol=0.006, sides=6, ref=V(1, 0, 0), cap=(0.0, 0.8), par=hd)
        tx = -sx * 0.055 * hs_
        ptube("thumb", [V(tx * 0.8, -0.02 * hs_, -0.02 * hs_), V(tx * 1.05, -0.04 * hs_, -0.055 * hs_), V(tx * 1.0, -0.05 * hs_, -0.09 * hs_)], (0.023 * hs_, 0.017 * hs_), skin, ol=0.006, sides=6, ref=V(0, 1, 0), cap=(0.0, 0.8), par=hd)
    # watch (dai hoc boy) / bracelet (girl)
    if stage == "daihoc":
        for sx in (1,):
            ptube("watch", [V(armr * 0.84 * math.cos(q), armr * 0.84 * math.sin(q), -Fa + 0.0) for q in [2 * math.pi * i / 14 for i in range(14)]], 0.016, mk("watchb", "#2f3744", "#121720", mid="#1d2430", hi="#7d8ba0", ao=0.2) if not girl else gold, ol=0.005, sides=6, ref=V(0, 0, 1), closed=True, par=K.elbows[sx])
    # ------------------------------------------------------------------ bags
    bagpal = {("nam", "tieuhoc"): ("#3f8be6", "#1c4c9c", "#2f6ccb", "#8ec2ff"), ("nam", "thcs"): ("#e8873a", "#a24a12", "#cf6a22", "#ffc89a"), ("nam", "thpt"): ("#3b4a6b", "#1a2338", "#2a3752", "#8da0c8"),
              ("nam", "daihoc"): ("#4a5568", "#1a202b", "#323b4a", "#9fb0c8"), ("nu", "tieuhoc"): ("#f58aa8", "#b4466e", "#df678a", "#ffc4d4"), ("nu", "thcs"): ("#8e7bf0", "#4c3ea8", "#6f5ccf", "#cfc4ff"),
              ("nu", "thpt"): ("#c98a52", "#6a3f1c", "#a8683a", "#f0c8a0"), ("nu", "daihoc"): ("#f3e6cf", "#a8946e", "#d9c7a4", "#ffffff")}[(kind, stage)]
    bag = mk("bag", bagpal[0], bagpal[1], mid=bagpal[2], hi=bagpal[3], rim=0.5, tex=("cotton", 2.4, 0.2))
    zk = types.SimpleNamespace()
    def backpack(bw, bh, bd, cz, one=False, big=True):
        by = dc * 0.95 + bd * 0.5 - 0.02; xoff = shw * 0.18 if one else 0.0
        rot = (0, 0.1 if one else 0.0, 0)
        rbox2("bag", V(xoff, by, cz), (bw, bd, bh), bag, bev=0.07, ol=0.014, sub=1, rot=rot)
        rbox2("bagpocket", V(xoff, by + bd * 0.5, cz - bh * 0.18), (bw * 0.72, bd * 0.36, bh * 0.5), bag, bev=0.04, ol=0.01, sub=1, rot=rot)
        rbox2("baglid", V(xoff, by + bd * 0.32, cz + bh * 0.32), (bw * 0.9, bd * 0.4, bh * 0.22), bag, bev=0.04, ol=0.01, sub=1, rot=rot)
        ptube("zip", [V(xoff - bw * 0.28, by + bd * 0.72, cz - bh * 0.05), V(xoff, by + bd * 0.74, cz - bh * 0.04), V(xoff + bw * 0.28, by + bd * 0.72, cz - bh * 0.05)], 0.008, metal, sides=5, ref=V(0, 1, 0))
        ell("zippull", V(xoff + bw * 0.28, by + bd * 0.76, cz - bh * 0.08), (0.012, 0.008, 0.026), gold, ol=0.004)
        ptube("handle", [V(xoff - 0.09, by, cz + bh * 0.5), V(xoff - 0.07, by, cz + bh * 0.5 + 0.08), V(xoff + 0.07, by, cz + bh * 0.5 + 0.08), V(xoff + 0.09, by, cz + bh * 0.5)], 0.016, strap, ol=0.006, sides=6, ref=V(0, 1, 0))
        for sx in ((1,) if one else (-1, 1)):
            sxo = sx * shw * 0.5
            sp = [V(sxo, by - 0.02, cz + bh * 0.42), V(sxo, 0.1, zs + 0.01), V(sxo * 1.0, -0.04, zs + 0.012), V(sxo * 1.06, tfront(sxo * 1.06, zs - 0.1) - 0.018, zs - 0.1), V(sx * shw * 0.82, tfront(sx * shw * 0.82, zs - 0.26) - 0.016, zs - 0.26),
                  V(sx * (shw + 0.02), -0.04, zs - 0.4), V(sx * (shw + 0.01), 0.1, zs - 0.5), V(sx * bw * 0.4, by - 0.06, cz - bh * 0.36)]
            ptube("strap", sp, 0.028, strap, ol=0.008, sides=8, flat=2.6, ref=lambda i, p, sx=sx: V(sx * 0.4, 0.0, 0.0) if i > 4 else V(0, 0, 1) if i < 3 else V(0, 1, 0), cap=(0.5, 0.5), sub=1)
        if stage in ("tieuhoc", "thcs"):
            for sx in (-1, 1): ell("bottle", V(sx * (bw * 0.5 + 0.0), by, cz - bh * 0.35), (0.07, 0.07, 0.17), bag, ol=0.01, sub=1)
    if outfit == "bomber":   # laptop backpack, slim, two straps, orange zip + keychain
        backpack(shw * 1.4, 0.8, 0.22, zs - 0.38)
        by_ = dc * 0.95 + 0.22 - 0.02
        ptube("lapzip", [V(-shw * 0.5, by_ + 0.13, zs - 0.22), V(0, by_ + 0.14, zs - 0.2), V(shw * 0.5, by_ + 0.13, zs - 0.22)], 0.012, mk("oz", "#ff8a2a", "#b04a10", ao=0.0), sides=5, ref=V(0, 1, 0))
    elif outfit == "cardigan":   # canvas tote on the right hip, strap over the shoulder
        tx = -(shw + 0.18); tz = HZ - 0.02
        rbox2("tote", V(tx, 0.02, tz), (0.42, 0.14, 0.44), bag, bev=0.04, ol=0.012, sub=1, rot=(0, -0.06, 0))
        ell("totelogo", V(tx, -0.056, tz + 0.02), (0.1, 0.008, 0.1), mk("totec", "#a58bf0", "#5e4aa6", mid="#7f66d8", hi="#d9ccff", ao=0.0), ol=0.005, rot=(0, 0, 0))
        ptube("totestrap", [V(tx - 0.12, 0.02, tz + 0.22), V(tx - 0.12, 0.0, tz + 0.5), V(-(shw * 0.6), 0.0, zs + 0.0), V(-shw * 0.55, 0.12, zs - 0.0), V(tx + 0.12, 0.02, tz + 0.5), V(tx + 0.12, 0.02, tz + 0.22)], 0.022, mk("strapc", "#e0cfa8", "#8a7550", mid="#bfae88", hi="#ffffff", ao=0.2), ol=0.006, sides=6, flat=2.2, ref=V(0, 1, 0), cap=(0.4, 0.4)) if False else None
        for sx2 in (-1, 1):
            ptube("tohandle", [V(tx + sx2 * 0.12, 0.02, tz + 0.2), V(tx + sx2 * 0.09, 0.02, tz + 0.46), V(tx + sx2 * 0.02 - 0.02, 0.02, tz + 0.5)], 0.016, mk("strapc", "#e0cfa8", "#8a7550", mid="#bfae88", hi="#ffffff", ao=0.2), ol=0.005, sides=6, ref=V(0, 1, 0), cap=(0.4, 0.4))
    elif outfit == "aodai":
        pass   # no bag with the ao dai
    elif kind == "nam" and stage == "thpt":
        backpack(shw * 1.35, 0.72, 0.26, zs - 0.34, one=True)
    elif stage == "tieuhoc":
        backpack(shw * 2.35, 0.8, 0.4, zs - 0.38)
    else:
        backpack(shw * 1.7, 0.74, 0.28, zs - 0.34)
    if outfit == "bomber":   # headphones round the neck
        hpm = mk("hph", "#f4f0ea", "#9d9aae", mid="#cfcad8", hi="#ffffff", ao=0.2)
        ptube("hpband", [V(0.19 * math.sin(math.radians(a)), 0.17 * math.cos(math.radians(a)) * 0.97 + 0.0, zs + 0.07 - 0.04 * (1 - abs(a) / 180) * 0) for a in range(-150, 151, 15)], 0.017, hpm, ol=0.006, sides=6, ref=V(0, 0, 1), cap=(0.5, 0.5))
        for sx in (-1, 1):
            ell("cup", V(sx * 0.2, -0.0, zs + 0.0), (0.05, 0.075, 0.075), mk("cup", "#ff8a2a", "#b04a10", mid="#e06a1c", hi="#ffd0a0", ao=0.2), ol=0.007, sub=1)
    K.base = {o.name: tuple(o.scale) for o in K.eyes}
    K.top = H + 0.25
    return K

# ==== KID3 MAIN
if _ARGV and len(_ARGV) >= 3 and "kid3_main" not in globals():
    kid3_main = True
    OUTD = _ARGV[0]; MODE = _ARGV[1]; WHAT = _ARGV[2]
    os.makedirs(OUTD, exist_ok=True)
    SAMPLES = int(os.environ.get("KID3_SAMPLES", 64)); RES = int(os.environ.get("KID3_RES", 512))
    sc.render.film_transparent = True
    sc.render.image_settings.file_format = "PNG"; sc.render.image_settings.color_mode = "RGBA"
    rig(); bpy.data.lights['sun'].angle = math.radians(1.0); setup_render(RES, RES, SAMPLES)
    KEEP = set(o.name for o in bpy.data.objects)
    def clear():
        for o in list(bpy.data.objects):
            if o.name not in KEEP: bpy.data.objects.remove(o)
        for me in list(bpy.data.meshes):
            if me.users == 0: bpy.data.meshes.remove(me)
    # arm poses: (shoulder x, shoulder y(out), elbow x(forward bend), elbow y(inward)) for the arm at +x ("L") and -x ("R")
    POSES = {
        ("nam", "tieuhoc"): ((-0.1, -0.30, -0.5, 0.75), (-0.1, 0.30, -0.5, -0.75)),    # both hands gripping the backpack straps
        ("nu", "tieuhoc"):  ((-0.1, -0.30, -0.5, 0.75), (-0.1, 0.30, -0.5, -0.75)),
        ("nam", "thcs"):    ((0.0, -0.2, -0.2, 0.2), (-0.15, 0.1, -1.3, -0.3)),        # one hand on the strap
        ("nu", "thcs"):     ((0.0, -0.2, -0.2, 0.2), (-0.15, 0.1, -1.3, -0.3)),
        ("nam", "thpt"):    ((0.1, -0.15, -0.2, 0.25), (-0.2, 0.1, -1.5, -0.4)),       # thumb hooked on the one strap
        ("nu", "thpt"):     ((-0.35, 0.0, -0.9, 0.5), (-0.35, 0.0, -0.9, -0.5)),       # hands clasped in front
        ("nam", "daihoc"):  ((0.05, -0.22, -0.15, 0.55), (-0.3, 0.05, -1.55, -0.3)),    # hand in pocket, other on the strap
        ("nu", "daihoc"):   ((0.0, -0.55, -0.25, 1.2), (-0.1, 0.1, -0.25, 0.0)),        # hand on hip, the other loose
    }
    def pose_still(K, kind, stage):
        """Sturdy stance: feet apart, weight on one leg, hips and shoulders tilted, head turned back to the viewer."""
        si = STAGES.index(stage)
        K.g.rotation_euler = (0, 0, math.radians(-26))
        K.rot_up((0, 0.06 + 0.012 * si, 0.05))
        K.hp.rotation_euler = (-0.1, 0.0, 0.12)
        K.legs[1].rotation_euler = (0.0, -0.15, 0); K.legs[-1].rotation_euler = (-0.1, 0.18, 0)
        for sx, (ax, ay, ex, ey) in zip((1, -1), POSES[(kind, stage)]):
            K.arms[sx].rotation_euler = (ax, ay, 0); K.elbows[sx].rotation_euler = (ex, ey, 0)
    def cam_for(ortho, zc, tilt):
        global CAM_TILT
        CAM_TILT = tilt
        for o in list(bpy.data.objects):
            if o.name == "cam": bpy.data.objects.remove(o)
        camera(ortho, V(0, 0, zc), (RES, RES))
    if MODE == "still":
        for cid in WHAT.split(","):
            kind, stage = cid.split("-")
            K = build_kid3(kind, stage); pose_still(K, kind, stage)
            cam_for((K.top + 0.1) / 0.82, K.top / 2 + 0.02, 12)
            sc.render.filepath = os.path.join(OUTD, f"{kind}-{stage}.png"); bpy.ops.render.render(write_still=True)
            print("RENDERED", cid, flush=True); clear()
    elif MODE == "lineup":
        for stage in STAGES:
            K = build_kid3(WHAT, stage); pose_still(K, WHAT, stage)
            cam_for(3.9, 1.6, 12)
            sc.render.filepath = os.path.join(OUTD, f"lu-{WHAT}-{stage}.png"); bpy.ops.render.render(write_still=True)
            print("RENDERED", WHAT, stage, flush=True); clear()


