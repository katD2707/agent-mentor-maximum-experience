# The student's chibi character v2 (boy "nam" / girl "nu"): a more detailed, more lifelike teen proportion (~2.6 heads),
# painted look of lang_lib.py (real sun + AO -> tone bands). Vietnamese school uniform, backpack, sneakers.
#   blender -b -P kid2.py -- <out_dir> <nam|nu> [still|turn|small]        stills for review (512 px, transparent)
#   actors2.py renders the sprite sheets with build_kid2() from here.
# Build from another script (lang_lib.py must already be loaded):
#   _k = open("kid2.py", encoding="utf-8").read(); exec(_k[_k.index("\n# ==== KID2 BUILDER"):_k.index("\n# ==== KID2 MAIN")])
#   K = build_kid2("nam")     K.g root (face looks -Y), K.hp head pivot (rest at K.hc), K.arms / K.legs {-1,1: pivot} swing about X,
#   K.tails [(pivot, sx)] ponytail (girl), K.eyes pivots to squash in Z for a blink, K.base their rest scales, K.leg_len hip to sole.
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
_ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if "lang_lib_loaded" not in globals():
    _OUT = _ARGV[0] if _ARGV else "."
    sys.argv = [sys.argv[0], "--", _OUT]
    exec(open(os.path.join(HERE, "lang_lib.py"), encoding="utf-8").read())
    lang_lib_loaded = True
import random, types
from mathutils import Matrix

# ==== KID2 BUILDER
import random, types
from mathutils import Matrix
TEXDIR = os.environ.get("KID2_TEX", os.path.join(os.path.dirname(HERE), "hoc-sinh-moi", "tex"))
HC = Vector((0, 0, 2.08)); HR = (0.50, 0.47, 0.50)
HIP = 0.93
def V(x, y, z): return Vector((x, y, z))
def sstep(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a))); return t * t * (3 - 2 * t)
def lerp(a, b, t): return a + (b - a) * t

def kp(name, lit, shade, mid=None, hi=None, **kw):
    kw.setdefault("ao", 0.45)
    m = paint(name, lit, shade, mid=mid, hi=hi, **kw)
    for nd in m.node_tree.nodes:
        if nd.type == "AMBIENT_OCCLUSION": nd.inputs["Distance"].default_value = 0.28
        if nd.type == "MAP_RANGE" and abs(nd.inputs[4].default_value - 0.07) < 1e-6: nd.inputs[3].default_value = -0.022; nd.inputs[4].default_value = 0.022
    return m

def vgrad(name, stops, z0, z1):
    m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree; n = nt.nodes; n.clear(); Lk = nt.links.new
    tc = n.new("ShaderNodeTexCoord"); sp = n.new("ShaderNodeSeparateXYZ"); mr = n.new("ShaderNodeMapRange"); ra = n.new("ShaderNodeValToRGB")
    em = n.new("ShaderNodeEmission"); out = n.new("ShaderNodeOutputMaterial")
    Lk(tc.outputs["Object"], sp.inputs[0]); Lk(sp.outputs[2], mr.inputs[0])
    mr.inputs[1].default_value = z0; mr.inputs[2].default_value = z1; mr.inputs[3].default_value = 0.0; mr.inputs[4].default_value = 1.0
    Lk(mr.outputs[0], ra.inputs[0]); cr = ra.color_ramp; cr.elements[0].position = stops[0][0]; cr.elements[0].color = lin(stops[0][1])
    cr.elements[1].position = stops[-1][0]; cr.elements[1].color = lin(stops[-1][1])
    for p, c in stops[1:-1]:
        e = cr.elements.new(p); e.color = lin(c)
    Lk(ra.outputs[0], em.inputs[0]); Lk(em.outputs[0], out.inputs[0]); return m

def softdisc(name, hexs, a):
    """A blended soft round blotch (blush): colour hexs, centre opacity a, fading to nothing at the rim of its bounding box."""
    m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree; n = nt.nodes; n.clear(); Lk = nt.links.new
    try: m.surface_render_method = "BLENDED"
    except Exception: pass
    tc = n.new("ShaderNodeTexCoord"); sb = n.new("ShaderNodeVectorMath"); sb.operation = "SUBTRACT"; sb.inputs[1].default_value = (0.5, 0.5, 0.5)
    ln = n.new("ShaderNodeVectorMath"); ln.operation = "LENGTH"; ra = n.new("ShaderNodeMapRange")
    ra.inputs[1].default_value = 0.0; ra.inputs[2].default_value = 0.5; ra.inputs[3].default_value = a; ra.inputs[4].default_value = 0.0; ra.clamp = True
    tr = n.new("ShaderNodeBsdfTransparent"); em = n.new("ShaderNodeEmission"); em.inputs[0].default_value = lin(hexs)
    mx = n.new("ShaderNodeMixShader"); out = n.new("ShaderNodeOutputMaterial")
    Lk(tc.outputs["Generated"], sb.inputs[0]); Lk(sb.outputs[0], ln.inputs[0]); Lk(ln.outputs["Value"], ra.inputs[0]); Lk(ra.outputs[0], mx.inputs[0])
    Lk(tr.outputs[0], mx.inputs[1]); Lk(em.outputs[0], mx.inputs[2]); Lk(mx.outputs[0], out.inputs[0]); return m

_DEF = [None]
def attach(o, par, off=None):
    if par is None: par = _DEF[0]
    if par is not None:
        o.parent = par
        if off is not None: o.location = o.location - off
    return o

def fin(o, mat, ol=0.0, sub=0, thick=0.0):
    o.data.materials.append(mat)
    for p in o.data.polygons: p.use_smooth = True
    if thick:
        s = o.modifiers.new("thk", "SOLIDIFY"); s.thickness = thick; s.offset = 0
    if sub:
        s = o.modifiers.new("sub", "SUBSURF"); s.levels = sub; s.render_levels = sub
    if ol: outline(o, ol)
    return o

def ell(name, c, r, mat, rot=(0, 0, 0), ol=0.0, seg=24, sub=0, par=None, off=None):
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=max(6, seg // 2), radius=1.0)
    for v in bm.verts: v.co = Vector((v.co.x * r[0], v.co.y * r[1], v.co.z * r[2]))
    o = mesh_obj(name, bm); o.location = c; o.rotation_euler = rot
    fin(o, mat, ol, sub); return attach(o, par, off)

def rbox2(name, c, size, mat, bev=0.04, ol=0.0, rot=(0, 0, 0), sub=1, par=None, off=None, seg=3):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts: v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
    o = mesh_obj(name, bm); o.location = c; o.rotation_euler = rot
    b = o.modifiers.new("bev", "BEVEL"); b.width = bev; b.segments = seg; b.limit_method = "NONE"
    fin(o, mat, ol, sub); return attach(o, par, off)

def ptube(name, pts, rad, mat, ol=0.0, sides=8, flat=1.0, ref=None, cap=(0.7, 0.7), sub=0, bm=None, closed=False, par=None, off=None):
    """A tube along a polyline. rad: float, (r0, r1) or f(t); flat: width factor along the side vector (s = tangent x ref)."""
    n = len(pts); own = bm is None
    if own: bm = bmesh.new()
    uvl = bm.loops.layers.uv.verify()
    if callable(rad): rf = rad
    elif isinstance(rad, (tuple, list)): rf = lambda t, a=rad: a[0] + (a[1] - a[0]) * t
    else: rf = lambda t, a=rad: a
    rings = []
    for i, p in enumerate(pts):
        t = (pts[(i + 1) % n] - pts[i - 1]) if closed else (pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)])
        t = t.normalized(); rv = ref(i, p) if callable(ref) else (ref if ref is not None else V(0, 0, 1))
        s = t.cross(rv)
        if s.length < 1e-4: s = t.cross(V(1, 0, 0))
        s = s.normalized(); u = s.cross(t).normalized(); r = rf(i / (n - 1) if n > 1 else 0.0)
        rings.append([bm.verts.new(p + (s * (math.cos(a) * flat) + u * math.sin(a)) * r) for a in (2 * math.pi * k / sides for k in range(sides))])
    for i in range(n if closed else n - 1):
        A, B = rings[i], rings[(i + 1) % n]; v0, v1 = i / max(n - 1, 1), (i + 1) / max(n - 1, 1)
        for k in range(sides):
            try: f = bm.faces.new((A[k], A[(k + 1) % sides], B[(k + 1) % sides], B[k]))
            except ValueError: continue
            for lp, uv in zip(f.loops, ((k / sides, v0), ((k + 1) / sides, v0), ((k + 1) / sides, v1), (k / sides, v1))): lp[uvl].uv = uv
    if not closed:
        for end, c in ((0, cap[0]), (1, cap[1])):
            if not c: continue
            ring = rings[0] if end == 0 else rings[-1]; p = pts[0] if end == 0 else pts[-1]
            d = (pts[0] - pts[1]) if end == 0 else (pts[-1] - pts[-2]); d = d.normalized()
            pole = bm.verts.new(p + d * rf(0.0 if end == 0 else 1.0) * c * 0.5 if False else p + d * max(rf(0.0 if end == 0 else 1.0), 0.004) * c)
            for k in range(sides):
                try: bm.faces.new((pole, ring[(k + 1) % sides], ring[k]))
                except ValueError: pass
    if not own: return None
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    o = mesh_obj(name, bm); fin(o, mat, ol, sub); return attach(o, par, off)

def poly2d(name, pts2, mat, pv, out=0.004, th=0.006, R=0.45):
    """A flat polygon in the local (x right, z up) plane of a face pivot, bent a little to follow the head (R)."""
    bm = bmesh.new(); vs = [bm.verts.new(V(x, -out + x * x / (2 * R), z)) for x, z in pts2]
    f = bm.faces.new(vs)
    if f.normal.y > 0: f.normal_flip()
    o = mesh_obj(name, bm); o.data.materials.append(mat)
    s = o.modifiers.new("thk", "SOLIDIFY"); s.thickness = th; s.offset = 0
    o.parent = pv; return o

# ---- the head surface
def hdeform(u):
    f = sstep(-0.05, -1.15, u.z); sx = 1 - 0.22 * f; sy = 1 - 0.12 * f
    return V(u.x * HR[0] * sx, u.y * HR[1] * sy, u.z * HR[2])
def hdir(az, el):
    a, e = math.radians(az), math.radians(el); return V(math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))
def hs(az, el, k=1.0): return HC + hdeform(hdir(az, el)) * k
def hn(az, el):
    d = 0.6; pa = hs(az + d, el) - hs(az - d, el); pe = hs(az, el + d) - hs(az, el - d)
    n = pa.cross(pe).normalized()
    return n if n.dot(hs(az, el) - HC) > 0 else -n
def tframe(az, el):
    """Euler for a pivot on the face: local X right, local Y into the head, local Z up (out = -Y)."""
    n = hn(az, el); right = V(0, 0, 1).cross(n).normalized(); up = n.cross(right)
    return Matrix((right, -n, up)).transposed().to_euler()

def build_kid2(kind="nam"):
    girl = kind == "nu"; rnd = random.Random(11 if girl else 5)
    K = types.SimpleNamespace(arms={}, legs={}, tails=[], eyes=[], base={}, parts={}, hc=HC.copy(), leg_len=HIP - 0.03)
    g = K.g = link(bpy.data.objects.new("kid", None)); _DEF[0] = g
    hp = K.hp = link(bpy.data.objects.new("head", None)); hp.parent = g; hp.location = HC
    # ---- materials: warm light, cool shade, painted tone bands
    skin = toon("k_skin", "#fddcc2", "#d98c78", "#fff1e6", edge=0.34)
    hairc = ("#4a342d", "#2a1b20", "#2b1d1e", "#8a6452") if not girl else ("#503329", "#2e1c20", "#30201f", "#926a55")
    hair = toon("k_hair", hairc[0], hairc[1], hairc[3], edge=0.3)
    hairhi = toon("k_hairhi", "#a07d68", "#6a4c40", "#e8c8ac", edge=0.3)
    shirt = kp("k_shirt", "#fffdf9", "#b3bfe4", mid="#e6ebf9", hi="#ffffff", tex=("cotton", 3.2, 0.25), rim=0.6)
    navy = kp("k_navy", "#35508f", "#16214a", mid="#263c78", hi="#6580bd", tex=("twill", 3.0, 0.3))
    navy2 = kp("k_navy2", "#2e4686", "#101a3c", mid="#1b2a5c", hi="#4a66a8")
    red = kp("k_red", "#ec4c46", "#a02226", mid="#cf3837", hi="#ff9f90", ao=0.3)
    metal = kp("k_metal", "#f4f0e6", "#8d8aa0", mid="#c9c6d4", hi="#ffffff", ao=0.2)
    shoe = kp("k_shoe", "#ffffff", "#b9c3e2", mid="#e4e9f6", hi="#ffffff", tex=("cotton", 3.5, 0.2))
    sole = kp("k_sole", "#fffaf0", "#c9c2d8", mid="#ece6dc", hi="#ffffff", ao=0.3)
    accent = navy2 if not girl else kp("k_acc", "#f06f95", "#b03a64", mid="#d85580", hi="#ffb0c8")
    bagc = ("#3f8be6", "#1c4c9c", "#2f6ccb", "#8ec2ff") if not girl else ("#f58aa8", "#b4466e", "#df678a", "#ffc4d4")
    bag = kp("k_bag", bagc[0], bagc[1], mid=bagc[2], hi=bagc[3], rim=0.5)
    strap = kp("k_strap", "#454f60", "#1e2430", mid="#323b4a", hi="#8693a8", ao=0.3)
    gold = kp("k_gold", "#ffd860", "#b8801c", mid="#e6ac38", hi="#fff4b0", ao=0.2)
    lineb = flat("k_brow", "#3a2621"); lidm = flat("k_lid", "#2a1713"); lipm = flat("k_lip", "#a8453b"); crease = flat("k_crease", "#c78367")
    # ---------------------------------------------------------------- head
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=56, v_segments=32, radius=1.0)
    for v in bm.verts: v.co = HC + hdeform(v.co.normalized())
    ho = mesh_obj("head", bm); fin(ho, skin, 0.016); attach(ho, hp, HC)
    for sx in (-1, 1):  # ears: shell + shaded inner
        c = hs(sx * 96, -3, 0.995)
        ell("ear", c, (0.04, 0.075, 0.095), skin, rot=(0, 0, sx * 0.25), ol=0.01, par=hp, off=HC)
        ell("earin", c + V(-sx * 0.012, -0.018, 0.0), (0.022, 0.04, 0.06), kp("k_earin", "#e8a58f", "#b86f62", ao=0.0), rot=(0, 0, sx * 0.25), par=hp, off=HC)
    ptube("neck", [V(0, 0.01, 1.47), V(0, 0.0, 1.62)], (0.115, 0.12), skin, ol=0.012, sides=14, cap=(0.0, 0.0))
    # ---------------------------------------------------------------- face
    def facepivot(name, az, el, k=0.985):
        pv = link(bpy.data.objects.new(name, None)); pv.parent = hp; pv.location = hs(az, el, k) - HC; pv.rotation_euler = tframe(az, el); return pv
    iris_m = vgrad("k_iris", [(0.0, "#2b160d"), (0.38, "#5a3419"), (0.78, "#a8672f"), (1.0, "#e0a05a")], -0.1, 0.1)
    scl_m = vgrad("k_sclera", [(0.0, "#eadfe0"), (0.35, "#fffaf6"), (1.0, "#ffffff")], -0.13, 0.13)
    limb = flat("k_limbus", "#1d0e08"); pupil = flat("k_pupil", "#0d0605"); white = flat("k_white", "#ffffff")
    for sx in (-1, 1):
        pv = facepivot("eye", sx * 25, -3); K.eyes.append(pv); K.base[pv.name] = tuple(pv.scale)
        EW, EH = (0.108, 0.128) if not girl else (0.112, 0.138)
        def E(nm, c, r, m, rot=(0, 0, 0), seg=24):
            o = ell(nm, c, r, m, rot=rot, seg=seg); o.parent = pv; return o
        E("sclera", V(0, -0.004, 0), (EW, 0.012, EH), scl_m)
        ix = -sx * 0.006
        E("limbus", V(ix, -0.012, -0.008), (0.094, 0.01, 0.12), limb)
        E("iris", V(ix, -0.017, -0.012), (0.082, 0.008, 0.108), iris_m)
        E("pupil", V(ix, -0.021, -0.006), (0.041, 0.006, 0.056), pupil)
        E("hl", V(ix - 0.03, -0.026, 0.045), (0.027, 0.005, 0.034), white)
        E("hl2", V(ix + 0.03, -0.026, -0.05), (0.013, 0.005, 0.015), white)
        E("hl3", V(ix + 0.012, -0.026, 0.07), (0.008, 0.005, 0.009), white)
        # upper lid: a heavy dark arc that flicks out past the outer corner; a lid crease above
        arc = []
        for th in range(172, 4, -14):
            a = math.radians(th); arc.append(V(sx * EW * 1.02 * math.cos(a), -0.02, EH * 0.98 * math.sin(a) - 0.004))
        arc.append(arc[-1] + V(sx * (0.03 if not girl else 0.045), 0.0, 0.012 if not girl else 0.02))
        lw = 0.017 if not girl else 0.021
        ptube("lid", arc, lambda t, lw=lw: lw * (0.35 + 0.8 * math.sin(math.pi * min(1.0, t * 0.95 + 0.05)) ** 0.7) * (1 - 0.7 * max(0, t - 0.85) / 0.15), lidm, sides=6, flat=1.0, ref=V(0, 1, 0), cap=(0.8, 0.5), par=pv)
        if girl:
            for dl, dz in ((0.0, 0.0), (0.02, 0.02)):
                ptube("lash", [arc[-3] + V(0, 0, dz * 0.2), arc[-2] + V(sx * dl, 0, 0.012 + dz), arc[-1] + V(sx * (0.025 + dl), 0, 0.026 + dz)], (0.006, 0.0015), lidm, sides=4, ref=V(0, 1, 0), cap=(0, 0.6), par=pv)
        ptube("crease", [V(sx * EW * 0.8 * math.cos(math.radians(t_)), -0.012, EH * 1.18 * math.sin(math.radians(t_)) + 0.012) for t_ in range(150, 40, -22)], 0.0045, crease, sides=4, ref=V(0, 1, 0), par=pv)
        ptube("lowlid", [V(sx * EW * math.cos(math.radians(t_)), -0.014, -EH * 0.95 * math.sin(math.radians(t_)) - 0.004) for t_ in range(200, 340, 20)], 0.0035, crease, sides=4, ref=V(0, 1, 0), par=pv)
        # brow
        bp = facepivot("brow", sx * 25, 17)
        bw, tilt = (0.115, -0.012) if not girl else (0.105, -0.004)
        bpts = [V(sx * (-0.02 + bw * t_), -0.012, 0.02 * math.sin(math.pi * (0.1 + t_ * 0.8)) + sx * 0 + tilt * t_ * 1.0 + (0.012 * t_ if not girl else 0.004 * t_)) for t_ in (0, 0.2, 0.4, 0.6, 0.8, 1.0)]
        ptube("brow", bpts, lambda t, g_=girl: (0.012 if not g_ else 0.008) * (0.55 + 0.6 * math.sin(math.pi * (0.15 + 0.7 * t))) , lineb, sides=6, flat=1.0, ref=V(0, 1, 0), cap=(0.8, 0.8), par=bp)
        # cheek blush
        cp = facepivot("cheek", sx * 40, -22, 0.995)
        bl = ell("blush", V(0, -0.002, 0), (0.085, 0.004, 0.055), softdisc("k_blush", "#ff7f93", 0.62)); bl.parent = cp
        for hx in (-0.025, 0.0, 0.025):
            ptube("hatch", [V(hx - 0.008, -0.006, -0.012), V(hx + 0.008, -0.006, 0.014)], 0.0028, flat("k_hatch", "#e8788a"), sides=4, ref=V(0, 1, 0), cap=(0.5, 0.5), par=cp)
    # nose: a small soft bump with a highlight, shadow below
    npv = facepivot("nose", 0, -21, 0.99)
    ell("nose", V(0, -0.012, 0), (0.026, 0.02, 0.022), skin, ol=0.006, par=npv) ; npv.children[-1].parent = npv
    ell("nosehl", V(-0.008, -0.03, -0.004), (0.008, 0.004, 0.006), white, par=npv).parent = npv
    ptube("nosesh", [V(-0.026, -0.008, -0.026), V(0, -0.012, -0.03), V(0.026, -0.008, -0.026)], 0.0035, crease, sides=4, ref=V(0, 1, 0), par=npv)
    # mouth: a small open smile with teeth and tongue, lip line, corner dimples
    mpv = facepivot("mouth", 0, -42, 0.97)
    w = 0.085; d = 0.06 if not girl else 0.054
    xs = [w * math.cos(math.pi * i / 16) for i in range(17)]
    top = [(-x, 0.012 * (x / w) ** 2 * 1.0 + 0.004) for x in xs[::-1]]       # left to right along the upper edge
    top = [(x, 0.016 * (x / w) ** 2) for x, _ in top]
    bot = [(x, 0.016 * (x / w) ** 2 - d * math.sqrt(max(0, 1 - (x / w) ** 2))) for x in xs]  # right to left
    cav = top + bot[1:-1]
    poly2d("mouthcav", cav, flat("k_cav", "#7a2a2c"), mpv, out=0.006, th=0.008)
    poly2d("tongue", [(x * 0.6, -d * 0.45 + 0.016 * (x / w) ** 2 + (-d * 0.5) * math.sqrt(max(0, 1 - (x / w) ** 2)) * 0.0 + 0.0) for x in xs[:9]] + [(x * 0.6, -d * 0.45 - d * 0.5 * math.sqrt(max(0, 1 - (x / w * 0.6 / 0.6) ** 2)) * 0.6) for x in xs[9:]], flat("k_tongue", "#f27c86"), mpv, out=0.009)
    poly2d("teeth", [(x * 0.92, 0.016 * (x / w) ** 2 * 0.0 + 0.012 * (x / w) ** 2 * 0.0 - 0.0) for x in (-w * 0.9, w * 0.9)] + [(w * 0.88, -0.014), (-w * 0.88, -0.014)] if False else [(-w * 0.86, 0.016 * 0.74 - 0.0), (w * 0.86, 0.016 * 0.74 - 0.0), (w * 0.8, -0.013 + 0.01), (-w * 0.8, -0.013 + 0.01)], white, mpv, out=0.0095)
    outl = [V(x, -0.006, z) for x, z in cav + [cav[0]]]
    ptube("lipline", [q - V(0, 0.003, 0) for q in outl], 0.0046, lipm, sides=4, ref=V(0, 1, 0), cap=(0.6, 0.6), par=mpv)
    for sx in (-1, 1):
        ptube("dimple", [V(sx * (w + 0.012), -0.006, 0.026), V(sx * (w + 0.022), -0.006, 0.014), V(sx * (w + 0.018), -0.006, 0.002)], 0.003, crease, sides=4, ref=V(0, 1, 0), par=mpv)
    # ---------------------------------------------------------------- hair
    def hl_line(az, girl_=girl):
        tab = ((0, 22), (28, 22), (58, 20), (80, 19), (104, 17), (124, 4), (150, -30 if not girl_ else -44), (180, -34 if not girl_ else -52))
        az = abs(az) % 360; az = 360 - az if az > 180 else az
        for (a0, e0), (a1, e1) in zip(tab, tab[1:]):
            if az <= a1: return lerp(e0, e1, (az - a0) / (a1 - a0))
        return tab[-1][1]
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=44, v_segments=26, radius=1.0)
    for v in bm.verts:
        u = v.co.normalized(); v.co = HC + hdeform(u) * 1.075 + V(0, 0.012, 0.012)
    dead = []
    for f in bm.faces:
        c = f.calc_center_median() - HC; az = math.degrees(math.atan2(c.x, -c.y)); el = math.degrees(math.asin(max(-1, min(1, c.z / c.length))))
        if el < hl_line(az): dead.append(f)
    bmesh.ops.delete(bm, geom=dead, context="FACES")
    for e in [e for e in bm.edges if not e.link_faces]: bm.edges.remove(e)
    for v in [v for v in bm.verts if not v.link_faces]: bm.verts.remove(v)
    hc_o = mesh_obj("haircap", bm); fin(hc_o, hair, 0.012); attach(hc_o, hp, HC)
    HB = bmesh.new(); HH = bmesh.new()   # locks (dark / pale streaks), joined so each is one mesh
    def prof(t): return min(1.0, 0.55 + t * 3.0) * (1 - t ** 2.2) ** 0.8
    def strand(B, az0, el0, az1, el1, k0, k1, w, bulge=0.035, n=7, flat=2.2, flick=0.0, bendaz=0.0):
        pts = []
        for i in range(n):
            t = i / (n - 1)
            az = lerp(az0, az1, t) + bendaz * math.sin(math.pi * t); el = lerp(el0, el1, t)
            pts.append(hs(az, el, lerp(k0, k1, t) + bulge * math.sin(math.pi * t) + flick * t ** 3))
        ptube("s", pts, lambda t: w * prof(t), None, sides=6, flat=flat, ref=lambda i, p: (p - HC).normalized(), cap=(0.35, 0.5), bm=B)
    def streak(az0, el0, az1, el1, k, w, t0=0.12, t1=0.62, bulge=0.035):
        pts = []
        for i in range(6):
            t = lerp(t0, t1, i / 5); pts.append(hs(lerp(az0, az1, t), lerp(el0, el1, t), k + 0.012 + bulge * math.sin(math.pi * t)))
        ptube("hs", pts, lambda t: w * math.sin(math.pi * (0.1 + 0.8 * t)), None, sides=4, flat=2.0, ref=lambda i, p: (p - HC).normalized(), cap=(0.4, 0.4), bm=HH)
    # radial locks from the crown whorl, in layers: the lowest lies under, the top layers over it (long, narrow locks)
    for li, (cnt, k, up_, w, fl) in enumerate(((28, 1.075, 0, 0.062, 2.5), (24, 1.105, 20, 0.07, 2.5), (18, 1.135, 40, 0.075, 2.4), (12, 1.16, 58, 0.07, 2.2))):
        for i in range(cnt):
            azn = (360.0 * i / cnt + rnd.uniform(-5, 5) + (7 if li % 2 else 0) + 180) % 360 - 180
            drift = 14 if azn > 0 else 10
            fr = abs(azn) < 112
            tip = (hl_line(azn) + up_ + rnd.uniform(-4, 4)) if fr else (-31 + up_ * 0.8 + rnd.uniform(-5, 5) if not girl else -40 + up_ + rnd.uniform(-5, 5))
            if fr: tip = max(tip, hl_line(azn) + 4)
            if fr and abs(azn) < 70: tip = max(tip, 42 if li else 38)   # keep the forehead for the fringe
            if tip > 66: continue
            if girl and not fr and li == 0:
                strand(HB, azn, 84, 160 + (azn - 160 if azn > 0 else azn + 360 - 160) * 0.18, 34, k - 0.02, 1.13, w, bulge=0.04, n=9, flat=fl)
                continue
            strand(HB, azn + rnd.uniform(-4, 4), 84, azn + drift + rnd.uniform(-5, 5), tip, k, k - 0.015, w * rnd.uniform(0.9, 1.15), bulge=0.045, n=9, flat=fl, bendaz=rnd.uniform(-5, 5))
            if li >= 1 and -100 < azn < 40 and i % 2 == 0: streak(azn, 84, azn + drift, tip, k, 0.026, 0.18, 0.7, 0.045)
    if not girl:   # short textured crown tufts and nape spikes
        for az, el, ln, w in ((-35, 74, 12, .05), (-5, 80, 14, .055), (30, 76, 13, .05), (150, 66, 10, .045), (-140, 62, 10, .045), (175, 52, 12, .05), (95, 70, 10, .045), (-100, 68, 10, .045)):
            strand(HB, az, el, az + (10 if az > 0 else -10), el - ln, 1.12, 1.2, w * 1.5, bulge=0.03, n=5, flick=0.1, flat=2.4)
        for az in range(-150, 151, 28):
            if abs(az) < 100: continue
            strand(HB, az, -6, az + rnd.uniform(-6, 6), -30, 1.06, 1.1, 0.048, bulge=0.02, n=5, flick=0.03)
    # sides in front of the ears, sideburns
    for sx in (-1, 1):
        if not girl:
            strand(HB, sx * 80, 30, sx * 90, 4, 1.1, 1.08, 0.05, bulge=0.03, n=5)
            strand(HB, sx * 70, 44, sx * 84, 14, 1.12, 1.1, 0.045, bulge=0.03, n=5)
        else:   # long side locks framing the face down to the shoulder
            strand(HB, sx * 76, 34, sx * 86, -34, 1.1, 1.12, 0.062, bulge=0.05, n=9, flat=2.4)
            strand(HB, sx * 66, 44, sx * 80, -26, 1.13, 1.14, 0.05, bulge=0.05, n=9, flat=2.4)
            strand(HB, sx * 84, 20, sx * 94, -40, 1.08, 1.09, 0.05, bulge=0.04, n=9, flat=2.4)
            streak(sx * 76, 30, sx * 86, -28, 1.1, 0.02, 0.1, 0.7, 0.05)
    # fringe: distinct strands over the forehead, parted a little left of centre, sweeping to both sides
    FR = (-68, -50, -33, -16, 0, 16, 33, 50, 68)
    for i, az in enumerate(FR):
        sw = -14 if az < -12 else (16 if az > 2 else 3)
        te = (24 if not girl else 22) + 12 * math.exp(-((az + 8) / 26) ** 2) + rnd.uniform(-3, 3); rt = 70
        w = rnd.uniform(0.085, 0.1)
        strand(HB, az * 0.8, rt, az * 0.97 + sw, te, 1.13, 1.085, w, bulge=0.045, n=8, flat=2.6, bendaz=(-3 if az < 0 else 3))
        if az < 25: streak(az * 0.8, rt, az * 0.97 + sw, te, 1.11, 0.03, 0.1, 0.6)
    for az, te in ((-24, 30), (16, 28), (-46, 33), (36, 30)):   # outer layer of bolder bangs
        strand(HB, az * 0.7, 74, az + (-8 if az < 0 else 10), te, 1.16, 1.12, 0.09, bulge=0.05, n=8, flat=2.5)
        if az < 0: streak(az * 0.7, 74, az + (-8 if az < 0 else 10), te, 1.14, 0.026, 0.1, 0.55)
    if girl: strand(HB, 3, 84, 12, 52, 1.13, 1.2, 0.03, bulge=0.0, n=5, flick=0.1, flat=1.4)   # a single flyaway
    for B, m, olw in ((HB, hair, 0.008), (HH, hairhi, 0)):
        bmesh.ops.recalc_face_normals(B, faces=B.faces[:])
        o = mesh_obj("hairlocks", B); fin(o, m, olw); attach(o, hp, HC); o.visible_shadow = False
    if girl:   # high ponytail on a pivot at a red scrunchie
        tie = hs(168, 36, 1.12)
        pv = link(bpy.data.objects.new("tail", None)); pv.parent = hp; pv.location = tie - HC; K.tails.append((pv, 1))
        pv.rotation_euler = (0, 0, 0)
        TB = bmesh.new(); TH = bmesh.new()
        for i in range(9):
            a = 2 * math.pi * i / 9; ox, oy = math.cos(a) * 0.1, math.sin(a) * 0.07
            L = rnd.uniform(0.8, 1.0)
            pts = [V(ox * lerp(1, 0.75, t) + 0.02 * t * t, oy * 0.4 + 0.12 * math.sin(t * 2.6) + 0.04 * t, 0.04 - L * t) for t in (0, 0.12, 0.3, 0.5, 0.7, 0.86, 1.0)]
            ptube("tl", pts, lambda t: 0.075 * (min(1, 0.7 + t * 2)) * (1 - t ** 2.6) ** 0.6, None, sides=6, flat=1.8, ref=lambda i, p: V(ox, oy, 0) + V(0, 0.001, 0), cap=(0.35, 0.5), bm=TB)
            if i % 2 == 0: ptube("th", [p + V(0, -0.012, 0) for p in pts[1:5]], lambda t: 0.018 * math.sin(math.pi * (0.1 + 0.8 * t)), None, sides=4, flat=2.0, ref=V(0, 1, 0), cap=(0.3, 0.3), bm=TH)
        for B, m, olw in ((TB, hair, 0.008), (TH, hairhi, 0)):
            bmesh.ops.recalc_face_normals(B, faces=B.faces[:]); o = mesh_obj("tail", B); fin(o, m, olw); o.parent = pv; o.visible_shadow = False
        o = ptube("scrunch", [V(0.075 * math.cos(a), 0.06 * math.sin(a), 0.02) for a in [2 * math.pi * i / 16 for i in range(16)]], 0.034, red, ol=0.008, sides=8, closed=True, sub=1); o.parent = pv
    # ---------------------------------------------------------------- torso: shirt, collar, scarf, pocket + badge, buttons
    TZ = [(0.96, 0.168), (1.06, 0.162), (1.2, 0.185), (1.33, 0.2), (1.44, 0.172), (1.52, 0.115)]
    def tdepth(z):
        for (z0, d0), (z1, d1) in zip(TZ, TZ[1:]):
            if z <= z1: return lerp(d0, d1, (z - z0) / (z1 - z0))
        return TZ[-1][1]
    FL = 1.4 if not girl else 1.32
    def tfront(x, z):  # y of the shirt's front surface
        d = tdepth(z); q = 1 - (x / (FL * d)) ** 2
        return -d * math.sqrt(max(q, 0.0)) - 0.004
    ptube("shirt", [V(0, 0.005, z) for z, _ in TZ], lambda t: tdepth(lerp(0.96, 1.52, t)), shirt, ol=0.014, sides=24, flat=FL, ref=V(0, 1, 0), cap=(0.0, 0.0), sub=1)
    for sx in (-1, 1):
        ell("shoulder", V(sx * 0.315, 0.0, 1.425), (0.085, 0.095, 0.09), shirt, ol=0.012, par=g)
    # collar: a stand around the neck and two points lying open in front
    ptube("collarband", [V(0.16 * math.sin(a), 0.14 * math.cos(a) + 0.0, 1.55) for a in [math.radians(x) for x in range(-130, 131, 20)]], 0.03, shirt, ol=0.008, sides=8, flat=1.8, ref=V(0, 0, 1), cap=(0.5, 0.5), sub=1) if False else None
    ptube("collarb", [V(0.155 * math.sin(math.radians(a)), 0.16 * math.cos(math.radians(a)) * 0.9 - 0.0, 1.56) for a in range(-160, 161, 20)], 0.032, shirt, ol=0.008, sides=8, flat=1.0, ref=V(0, 0, 1), cap=(0.5, 0.5), sub=1)
    for sx in (-1, 1):
        pts = [V(sx * 0.03, -0.165, 1.56), V(sx * 0.11, -0.17, 1.55), V(sx * 0.2, -0.12, 1.54), V(sx * 0.23, -0.06, 1.545)]
        pts2 = [V(sx * 0.04, -0.195, 1.47), V(sx * 0.13, -0.2, 1.47), V(sx * 0.22, -0.135, 1.5), V(sx * 0.25, -0.07, 1.525)]
        bmc = bmesh.new(); a_ = [bmc.verts.new(p) for p in pts]; b_ = [bmc.verts.new(p) for p in pts2]
        for i in range(3): bmc.faces.new((a_[i], a_[i + 1], b_[i + 1], b_[i]))
        bmesh.ops.recalc_face_normals(bmc, faces=bmc.faces[:]); o = mesh_obj("collar", bmc); fin(o, shirt, 0.01, 1, thick=0.022); o.parent = g
    # red scarf: knot + two tails, a band at the neck
    ptube("scarfband", [V(0.19 * math.sin(math.radians(a)), 0.17 * math.cos(math.radians(a)) * 0.97, 1.5) for a in range(-180, 180, 20)], 0.036, red, ol=0.01, sides=8, flat=1.0, ref=V(0, 0, 1), closed=True, sub=1)
    ell("knot", V(0, -0.2, 1.46), (0.06, 0.05, 0.05), red, ol=0.008, par=g, sub=1)
    for sx, rot_ in ((-1, 0.28), (1, -0.3)):
        bmc = bmesh.new(); vs = [bmc.verts.new(p) for p in (V(sx * 0.02, -0.215, 1.46), V(sx * 0.095, -0.205, 1.45), V(sx * 0.2, -0.205, 1.2) if False else V(sx * 0.12, -0.22, 1.2), V(sx * 0.03, -0.24, 1.24))]
        bmc.faces.new(vs); bmesh.ops.subdivide_edges(bmc, edges=bmc.edges[:], cuts=3, use_grid_fill=True)
        bmesh.ops.recalc_face_normals(bmc, faces=bmc.faces[:]); o = mesh_obj("scarftail", bmc); fin(o, red, 0.009, 1, thick=0.018); o.parent = g
    # pocket on the wearer's left chest (+x) with a school badge, stitching
    px, pz = 0.115, 1.27
    pw, ph = 0.1, 0.105
    rbox2("pocket", V(px, tfront(px, pz) - 0.006, pz), (pw * 2, 0.014, ph * 2), shirt, bev=0.007, ol=0.006, sub=0, par=g, seg=2)
    ptube("stitch", [V(px - pw * 0.88, tfront(px, pz) - 0.016, pz + ph * 0.8), V(px - pw * 0.88, tfront(px, pz) - 0.016, pz - ph * 0.7), V(px, tfront(px, pz) - 0.016, pz - ph * 0.92), V(px + pw * 0.88, tfront(px, pz) - 0.016, pz - ph * 0.7), V(px + pw * 0.88, tfront(px, pz) - 0.016, pz + ph * 0.8)], 0.0032, flat("k_stitch", "#a8b3d6"), sides=4, ref=V(0, 1, 0), par=g)
    bgz = V(px, tfront(px, pz) - 0.022, pz + 0.01)
    ell("badge", bgz, (0.052, 0.009, 0.06), kp("k_badge", "#e84b43", "#9c2428", mid="#cf3a36", hi="#ff9b8c", ao=0.0), ol=0.006, par=g)
    ell("badgering", bgz + V(0, -0.006, 0), (0.038, 0.005, 0.044), gold, par=g)
    ell("badgein", bgz + V(0, -0.011, 0), (0.028, 0.004, 0.032), kp("k_badgein", "#2d62c9", "#183a82", ao=0.0, rim=0.0), par=g)
    star = bmesh.new(); sv = []
    for i in range(10):
        a = math.pi / 2 + i * math.pi / 5; r_ = 0.022 if i % 2 == 0 else 0.009; sv.append(star.verts.new(V(px + r_ * math.cos(a), bgz.y - 0.014, bgz.z + r_ * math.sin(a))))
    f_ = star.faces.new(sv)
    if f_.normal.y > 0: f_.normal_flip()
    o = mesh_obj("star", star); o.data.materials.append(gold); o.modifiers.new("t", "SOLIDIFY").thickness = 0.004; o.parent = g
    for z in (1.4, 1.2, 1.05):   # button placket + buttons
        ell("button", V(0.0, tfront(0, z) - 0.008, z), (0.014, 0.006, 0.014), kp("k_btn", "#ffffff", "#9aa3c8", ao=0.0), ol=0.004, par=g)
    ptube("placket", [V(0.0, tfront(0, z) - 0.003, z) for z in (1.48, 1.3, 1.1, 0.99)], 0.0045, kp("k_plk", "#e8ecf8", "#a8b3d6", ao=0.0), sides=4, ref=V(1, 0, 0), par=g)
    # fabric folds: waist bunching and chest pulls (soft ridges that catch light and AO)
    def fold(z0, z1, x0, x1, w=0.011, lift=0.0):
        pts = []
        for i in range(7):
            t = i / 6; x = lerp(x0, x1, t); z = lerp(z0, z1, t) + lift * math.sin(math.pi * t); pts.append(V(x, tfront(x, z) - 0.002, z))
        ptube("fold", pts, lambda t: w * math.sin(math.pi * (0.05 + 0.9 * t)) ** 0.6, shirt, sides=6, flat=1.0, ref=V(0, 1, 0), cap=(0.4, 0.4), par=g)
    for z0, z1, x0, x1 in ((1.09, 1.12, -0.24, -0.04), (1.07, 1.1, 0.03, 0.25), (1.13, 1.12, -0.2, 0.0), (1.22, 1.17, -0.27, -0.12), (1.2, 1.15, 0.2, 0.28)):
        fold(z0, z1, x0, x1)
    # ---------------------------------------------------------------- lower body
    if not girl:
        ell("hips", V(0, 0.01, HIP + 0.02), (0.275, 0.2, 0.155), navy, ol=0.014, par=g, sub=1)
        ptube("belt", [V(0.255 * math.cos(a), 0.18 * math.sin(a) + 0.01, 1.0) for a in [2 * math.pi * i / 36 for i in range(36)]], 0.024, kp("k_belt", "#5a3f30", "#2c1c14", mid="#43301f", hi="#9a7458", ao=0.2), ol=0.006, sides=6, flat=1.0, ref=V(0, 0, 1), closed=True)
        rbox2("buckle", V(0, -0.19, 1.0), (0.07, 0.014, 0.05), metal, bev=0.008, ol=0.005, sub=0, par=g, seg=2)
        for ax in (-0.17, -0.09, 0.09, 0.17):
            rbox2("loop", V(ax, tfront(ax, 1.0) - 0.012 + 0.012, 1.0), (0.016, 0.014, 0.07), kp("k_belt", "#5a3f30", "#2c1c14"), bev=0.004, sub=0, par=g, seg=1)
    else:
        N = 24; M = 144; rows = 12; z0, z1 = 1.04, 0.70
        bmk = bmesh.new(); grid = []
        for j in range(rows + 1):
            t = j / rows; z = lerp(z0, z1, t); rx = lerp(0.255, 0.40, t ** 0.8); ry = lerp(0.19, 0.31, t ** 0.8); amp = lerp(0.006, 0.075, t)
            row = []
            for i in range(M):
                th = 2 * math.pi * i / M; pl = abs(math.sin(N * th / 2)); k = 1 + amp * (pl - 0.5) * 2
                row.append(bmk.verts.new(V(rx * k * math.cos(th), ry * k * math.sin(th) + 0.01, z)))
            grid.append(row)
        for j in range(rows):
            for i in range(M): bmk.faces.new((grid[j][i], grid[j][(i + 1) % M], grid[j + 1][(i + 1) % M], grid[j + 1][i]))
        bmesh.ops.recalc_face_normals(bmk, faces=bmk.faces[:]); o = mesh_obj("skirt", bmk); fin(o, navy, 0.012, 0, thick=0.014); o.parent = g
        ptube("waistband", [V(0.262 * math.cos(a), 0.195 * math.sin(a) + 0.01, 1.04) for a in [2 * math.pi * i / 36 for i in range(36)]], 0.026, navy2, ol=0.008, sides=6, flat=1.0, ref=V(0, 0, 1), closed=True)
        ptube("hemline", [V(0.405 * math.cos(a) * 1.0, 0.315 * math.sin(a) + 0.01, 0.705) for a in [2 * math.pi * i / 72 for i in range(72)]], 0.012, navy2, sides=4, flat=1.0, ref=V(0, 0, 1), closed=True)
        ell("hipsg", V(0, 0.01, HIP + 0.06), (0.24, 0.18, 0.13), navy, par=g)
    # legs (pivot at the hip, geometry hangs down): trouser or skin + sock, then the sneaker
    for sx in (-1, 1):
        lg = link(bpy.data.objects.new("leg", None)); lg.parent = g; lg.location = (sx * 0.135, 0.01, HIP); K.legs[sx] = lg
        def Lp(o): o.parent = lg; return o
        if not girl:
            ptube("trouser", [V(0, 0, -0.02), V(0, 0, -0.3), V(0, -0.008, -0.55), V(0, -0.0, -0.72)], (0.135, 0.108), navy, ol=0.014, sides=16, flat=1.0, ref=V(1, 0, 0), cap=(0.0, 0.0), sub=1, par=lg)
            ptube("crease", [V(0, -0.118, -0.12), V(0, -0.113, -0.45), V(0, -0.1, -0.76)], 0.006, kp("k_crs", "#5272bb", "#27396f", ao=0.0), sides=4, ref=V(1, 0, 0), par=lg)
            ptube("hem", [V(0.112 * math.cos(a), 0.105 * math.sin(a), -0.715) for a in [2 * math.pi * i / 20 for i in range(20)]], 0.018, navy2, ol=0.006, sides=6, ref=V(0, 0, 1), closed=True, par=lg)
            for zz, ln in ((-0.46, 0.07), (-0.62, 0.06)):   # knee and ankle wrinkles
                ptube("wr", [V(-ln, -0.112, zz + 0.01), V(0, -0.118, zz), V(ln, -0.112, zz + 0.012)], 0.007, navy, sides=4, ref=V(0, 1, 0), par=lg)
        else:
            ptube("legskin", [V(0, 0, -0.18), V(0, -0.005, -0.42), V(0, 0.0, -0.62), V(0, 0, -0.82)], lambda t: lerp(0.08, 0.057, t) + 0.006 * math.sin(math.pi * min(1, t * 1.6)) ** 2, skin, ol=0.012, sides=12, ref=V(1, 0, 0), cap=(0.0, 0.0), sub=1, par=lg)
            ell("knee", V(0, -0.045, -0.43), (0.05, 0.03, 0.045), skin, par=lg, sub=0)
            ptube("sock", [V(0, 0, -0.64), V(0, 0, -0.76)], 0.058, shirt, ol=0.01, sides=12, ref=V(1, 0, 0), cap=(0.0, 0.0), par=lg)
            ptube("sockcuff", [V(0.062 * math.cos(a), 0.062 * math.sin(a), -0.645) for a in [2 * math.pi * i / 16 for i in range(16)]], 0.014, kp("k_scuff", "#eef0fa", "#aab5da", ao=0.0), ol=0.005, sides=6, ref=V(0, 0, 1), closed=True, par=lg)
        # sneaker: upper along heel to toe, rubber toe cap and sole, laces, tongue, accent stripe, collar
        so = -HIP + 0.0; yaw = sx * 0.1
        grp = link(bpy.data.objects.new("shoe", None)); grp.parent = lg; grp.location = (0, 0, so); grp.rotation_euler = (0, 0, yaw); grp.scale = (1.2, 1.2, 1.2)
        up_pts = [V(0, 0.09, 0.105), V(0, 0.035, 0.115), V(0, -0.06, 0.095), V(0, -0.15, 0.072), V(0, -0.2, 0.056)]
        ptube("upper", up_pts, lambda t: lerp(0.082, 0.045, t ** 1.4), shoe, ol=0.012, sides=14, flat=1.12, ref=V(1, 0, 0), cap=(0.5, 0.5), sub=1, par=grp)
        ell("toecap", V(0, -0.19, 0.052), (0.066, 0.062, 0.046), sole, ol=0.008, par=grp, sub=1)
        rbox2("sole", V(0, -0.045, 0.018), (0.14, 0.38, 0.034), sole, bev=0.018, ol=0.01, sub=1, par=grp)
        ptube("tread", [V(0.0, -0.045 + y, 0.0) for y in (-0.19, 0.19)], 0.0, sole, sides=3, cap=(0, 0), par=grp) if False else None
        ptube("collar", [V(0.056 * math.cos(a) * 1.0, 0.07 + 0.058 * math.sin(a), 0.128) for a in [2 * math.pi * i / 18 for i in range(18)]], 0.016, shoe, ol=0.007, sides=6, ref=V(0, 0, 1), closed=True, par=grp)
        ell("tongue", V(0, -0.012, 0.128), (0.036, 0.05, 0.016), shoe, rot=(-0.35, 0, 0), ol=0.005, par=grp)
        for i, y in enumerate((-0.0, -0.045, -0.09, -0.13)):
            ptube("lace", [V(-0.044, y + 0.012, 0.118 - i * 0.011), V(0, y - 0.004, 0.126 - i * 0.012), V(0.044, y + 0.012, 0.118 - i * 0.011)], 0.0075, kp("k_lace", "#fdfbff", "#aeb6d8", ao=0.0), sides=5, ref=V(0, 1, 0), ol=0.003, par=grp)
        ptube("bow", [V(-0.03, 0.03, 0.15), V(0, 0.026, 0.14), V(0.03, 0.03, 0.15)], 0.009, kp("k_lace", "#fdfbff", "#aeb6d8", ao=0.0), sides=5, ref=V(0, 1, 0), ol=0.003, par=grp)
        for sx2 in (-1, 1):
            ptube("stripe", [V(sx2 * 0.068, 0.07, 0.07), V(sx2 * 0.07, -0.01, 0.075), V(sx2 * 0.062, -0.1, 0.06), V(sx2 * 0.045, -0.15, 0.05)], 0.011, accent, sides=5, ref=V(0, 0, 1), par=grp)
    # ---------------------------------------------------------------- arms: sleeve, skin, hand with fingers (pivot at the shoulder)
    for sx in (-1, 1):
        a = link(bpy.data.objects.new("arm", None)); a.parent = g; a.location = (sx * 0.35, 0.0, 1.43); a.rotation_euler = (0, -sx * 0.14, 0); K.arms[sx] = a
        def Ap(o): o.parent = a; return o
        ptube("sleeve", [V(0, 0, 0.04), V(0, 0, -0.1), V(0, -0.005, -0.215)], (0.098, 0.09), shirt, ol=0.012, sides=14, ref=V(1, 0, 0), cap=(0.0, 0.0), sub=1, par=a)
        ptube("sleevehem", [V(0.096 * math.cos(q), 0.096 * math.sin(q), -0.215) for q in [2 * math.pi * i / 16 for i in range(16)]], 0.014, kp("k_hem", "#ffffff", "#aab6dc", ao=0.2), ol=0.006, sides=6, ref=V(0, 0, 1), closed=True, par=a)
        ptube("sleevefold", [V(-0.06 + 0.12 * t * (-1 if sx < 0 else 1) * 0, -0.098 + 0.0, -0.1 + 0.04 * t) for t in (0, 0.5, 1)], 0.007, shirt, sides=4, ref=V(0, 1, 0), par=a)
        arm_pts = [V(0, 0, -0.2), V(0, -0.012, -0.3), V(0, -0.04, -0.4), V(0, -0.09, -0.5), V(0, -0.115, -0.56)]
        ptube("arm", arm_pts, lambda t: lerp(0.078, 0.056, t) + 0.004 * math.sin(math.pi * t), skin, ol=0.011, sides=10, ref=V(1, 0, 0), cap=(0.0, 0.0), sub=1, par=a)
        hd = link(bpy.data.objects.new("hand", None)); hd.parent = a; hd.location = (0, -0.115, -0.56); hd.rotation_euler = (-0.35, 0, -sx * 0.12)
        ell("palm", V(0, -0.004, -0.04), (0.064, 0.036, 0.072), skin, ol=0.009, par=hd, sub=1)
        for fi, fx in enumerate((-0.036, -0.012, 0.012, 0.036)):
            ln = (0.062, 0.078, 0.072, 0.056)[fi]; cr = 0.02
            pts = [V(fx, 0.0, -0.09), V(fx * 1.05, -cr * 0.4, -0.09 - ln * 0.5), V(fx * 1.08, -cr * 1.5, -0.09 - ln * 0.95), V(fx * 1.08, -cr * 2.6, -0.09 - ln * 1.1)]
            ptube("finger", pts, (0.02, 0.014), skin, ol=0.006, sides=6, ref=V(1, 0, 0), cap=(0.0, 0.8), par=hd)
        tx = -sx * 0.055
        ptube("thumb", [V(tx * 0.8, -0.02, -0.02), V(tx * 1.05, -0.04, -0.055), V(tx * 1.0, -0.05, -0.09)], (0.023, 0.017), skin, ol=0.006, sides=6, ref=V(0, 1, 0), cap=(0.0, 0.8), par=hd)
    # ---------------------------------------------------------------- backpack with straps (rigid on the torso)
    by = 0.335
    bagb = rbox2("bag", V(0, by, 1.17), (0.56, 0.27, 0.62), bag, bev=0.07, ol=0.014, sub=1, par=g)
    rbox2("bagpocket", V(0, by + 0.15, 1.02), (0.4, 0.1, 0.34), bag, bev=0.04, ol=0.01, sub=1, par=g)
    rbox2("baglid", V(0, by + 0.1, 1.38), (0.5, 0.12, 0.14), bag, bev=0.04, ol=0.01, sub=1, par=g)
    ptube("zip", [V(-0.17, by + 0.205, 1.17), V(0.0, by + 0.208, 1.18), V(0.17, by + 0.205, 1.17)], 0.008, metal, sides=5, ref=V(0, 1, 0), par=g)
    ell("zippull", V(0.17, by + 0.215, 1.15), (0.012, 0.008, 0.026), gold, ol=0.004, par=g)
    ptube("handle", [V(-0.09, by, 1.5), V(-0.07, by, 1.58), V(0.07, by, 1.58), V(0.09, by, 1.5)], 0.016, strap, ol=0.006, sides=6, ref=V(0, 1, 0), par=g)
    for sx in (-1, 1):
        ell("bottle", V(sx * 0.3, by + 0.0, 0.98), (0.07, 0.07, 0.17), bag, ol=0.01, par=g, sub=1)
        sp = [V(sx * 0.2, by - 0.02, 1.46), V(sx * 0.2, 0.12, 1.545), V(sx * 0.2, -0.04, 1.545), V(sx * 0.215, -0.14, 1.47), V(sx * 0.225, tfront(sx * 0.225, 1.3) - 0.02, 1.3),
              V(sx * 0.3, -0.09, 1.1), V(sx * 0.31, 0.12, 0.99), V(sx * 0.22, by - 0.1, 0.9)]
        ptube("strap", sp, 0.026, strap, ol=0.008, sides=8, flat=2.6, ref=lambda i, p: V(sx * 0.4, 0.0, 0.0) if i > 4 else V(0, 0, 1) if i < 3 else V(0, 1, 0), cap=(0.5, 0.5), sub=1, par=g)
        rbox2("slider", V(sx * 0.31, 0.0, 1.06), (0.05, 0.02, 0.035), metal, bev=0.006, ol=0.004, sub=0, par=g, seg=1)
    K.base = {o.name: tuple(o.scale) for o in K.eyes}
    return K

# ==== KID2 MAIN
if __name__ == "__main__" or True:
    if _ARGV and len(_ARGV) >= 2 and "kid2_main" not in globals():
        kid2_main = True
        KIND = _ARGV[1]; MODE = _ARGV[2] if len(_ARGV) > 2 else "still"; OUTD = _ARGV[0]
        os.makedirs(OUTD, exist_ok=True)
        K = build_kid2(KIND)
        sc.render.film_transparent = True
        sc.render.image_settings.file_format = "PNG"; sc.render.image_settings.color_mode = "RGBA"
        rig(); bpy.data.lights['sun'].angle = math.radians(1.0); setup_render(512, 512, int(os.environ.get("KID2_SAMPLES", 64)))
        cam = bpy.data.cameras.new("cam"); cam.type = "ORTHO"; cam.ortho_scale = 3.42; cam.clip_end = 400
        co = link(bpy.data.objects.new("cam", cam)); co.location = (0, -20, 7.05); co.rotation_euler = (math.radians(74), 0, 0); sc.camera = co
        sc.render.resolution_x = sc.render.resolution_y = 512; sc.render.resolution_percentage = int(os.environ.get("KID2_PCT", 100))
        if MODE == "still":
            K.g.rotation_euler = (0, 0, math.radians(-12))
            for sx in (-1, 1): K.arms[sx].rotation_euler = (0, -sx * 0.14, 0)
            sc.render.filepath = os.path.join(OUTD, f"{KIND}-still.png"); bpy.ops.render.render(write_still=True)
        elif MODE == "turn":
            for nm, yaw in (("s", 0), ("e", 90), ("n", 180), ("se", 45)):
                K.g.rotation_euler = (0, 0, math.radians(yaw))
                sc.render.filepath = os.path.join(OUTD, f"{KIND}-turn-{nm}.png"); bpy.ops.render.render(write_still=True)
        print("RENDERED kid2", KIND, MODE)
