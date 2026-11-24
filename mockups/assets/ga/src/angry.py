# The ANGRY (gian) state of a Lang ga chicken: a neglected course. Used by chicken.py modes `gian` (still) and `ganim` (idle loop).
# Cute, not scary: arms crossed, deep frowning brows, narrowed eyes, a pouting frown, red cheeks, a red anger-vein mark beside the head
# and a few small stylised flames above it.
import bpy, bmesh, math
from mathutils import Vector


def V(x, y, z): return Vector((x, y, z))


def flat(H, name, pts, mat, depth=0.06, ol=0.03, bev=0.0):
    """an extruded outline in the xz plane (faces the viewer at -y), unit size, placed by the caller"""
    bm = bmesh.new(); vs = [bm.verts.new(V(x, 0, z)) for x, z in pts]; bm.faces.new(vs)
    o = H.mesh_obj(name, bm)
    so = o.modifiers.new("th", "SOLIDIFY"); so.thickness = depth; so.offset = 0
    if bev: bv = o.modifiers.new("bev", "BEVEL"); bv.width = bev; bv.segments = 2
    return H.finish(o, mat, ol, subsurf=0)


def flame_pts(k=1.0, bend=0.22, n=18):
    right, left = [], []
    for i in range(n + 1):
        t = i / n; z = -0.9 + 2.1 * t; w = 0.62 * (math.sin(math.pi * t ** 0.72) ** 0.95) * (1 - 0.22 * t); cx = bend * math.sin(3.0 * t) * t
        right.append((cx + w * k, z)); left.append((cx - w * k, z))
    return right + left[::-1][1:]


def vein_pieces(a=0.56, ri=0.22, ro=0.62, n=8):
    """the four curved wedges of the anger mark (a cross with a gap in the middle)"""
    out = []
    for cx, cz, a0 in ((a, a, 180), (-a, a, 270), (a, -a, 90), (-a, -a, 0)):
        pts = [(cx + math.cos(math.radians(a0 + 90 * i / n)) * ro, cz + math.sin(math.radians(a0 + 90 * i / n)) * ro) for i in range(n + 1)]
        pts += [(cx + math.cos(math.radians(a0 + 90 - 90 * i / n)) * ri, cz + math.sin(math.radians(a0 + 90 - 90 * i / n)) * ri) for i in range(n + 1)]
        out.append(pts)
    return out


def apply(ch, H, subject, stage):
    s = ch.s; chick = stage == 1; hc, rh, bc, rb = ch.hc, ch.rh, ch.bc, ch.rb
    kit = getattr(ch, "kit", None)
    ch.fx = []  # (object, kind, base scale) for the idle animation
    ink = H.toon("eye", "#2a1a14", "#1a100c")
    # ---- red cheeks (instead of the soft pink ones) and a pouting frown either side of the beak --------------------------------------------
    red = H.flat("redcheek", "#ff3b3b")
    for sx in (-1, 1):
        d = Vector((0.62 * sx, -0.74, -0.2)).normalized()
        ch.addh(H.ball("redblush", hc + d * rh * 1.0, (0.2 * s, 0.05 * s, 0.13 * s), red, rot=H.face_rot(d), outline=0))
        for j in (-1, 0, 1):  # little hatch marks on the cheek, anime style
            ch.addh(H.rbox("hatch", hc + d * rh * 1.02 + V(sx * (0.02 + j * 0.06) * s, -0.02 * s, 0.0), (0.012 * s, 0.02 * s, 0.1 * s), H.flat("hatchc", "#c2181f"), rot=(0, 0.6 * sx, 0), outline=0))
    Rx, Ry, Rz = rh, rh * 0.95, rh * 0.93
    def onhead(x, z):  # a point on the face surface (front), x / z offsets from the head centre
        v = max(0.05, 1 - (x / Rx) ** 2 - (z / Rz) ** 2); return hc + V(x, -Ry * math.sqrt(v) * 1.01, z)
    for sx in (-1, 1):
        pts = [onhead(sx * 0.2 * s, -0.36 * s), onhead(sx * 0.34 * s, -0.40 * s), onhead(sx * 0.46 * s, -0.50 * s)]
        ch.addh(H.cone.__call__ if False else ch.kit.tube("frown", pts, 0.03 * s, ink, outline=0.0, sides=5)) if kit else None
    # ---- crossed wings -----------------------------------------------------------------------------------------------------------------------
    for piv, sx in ch.parts["wings"]:
        w = piv.children[0]; w.scale = (0.24 * s, 0.34 * s, 0.5 * s)
        w.location = (0, 0, -0.36 * s)
        yfront = bc.y - rb * 0.95 * (1.12 if not chick else 1.04) - 0.06 * s
        front = 0.0 if sx > 0 else 0.1 * s  # the right wing lies over the left one
        piv.location = V(sx * rb * 0.62, yfront + front, bc.z - 0.0 * s)
        piv.rotation_euler = (math.radians(-12), sx * 1.32, math.radians(sx * 8))
    # ---- flames above the head ----------------------------------------------------------------------------------------------------------------
    top = getattr(kit, "hat_top", hc.z + rh)
    top = getattr(top, "z", top)  # some hats store a Vector
    fo = H.toon("flame_o", "#ff5a1a", "#d62a08", "#ffa040"); fy = H.toon("flame_y", "#ffd23a", "#f09a10", "#fff0a0")
    room = 4.55 - top
    sizes = [(0.0, 1.0), (-0.62, 0.7), (0.62, 0.72)]
    fs = 0.5 * s
    if room > 0.95 * s:
        base = [(0.0, top + 0.28 * s, 1.0), (-0.62 * s, top + 0.1 * s, 0.68), (0.62 * s, top + 0.1 * s, 0.72)]
    else:  # a tall hat: the flames burn on both sides of it, over the shoulders of the head
        zz = hc.z + rh * 0.95
        base = [(-0.98 * rh, zz + 0.05 * s, 0.8), (0.98 * rh, zz + 0.05 * s, 0.8), (-1.28 * rh, zz - 0.35 * s, 0.55)]
        base = base[:3]
    for i, (x, z, k) in enumerate(base):
        fl = flame_pts(); o = flat(H, "flame", fl, fo, depth=0.1, ol=0.03)
        o.scale = (fs * k, fs * k, fs * k); o.location = V(hc.x + x, hc.y - 0.12 * s, z + fs * k * 0.9); o.rotation_euler = (0, 0, math.radians((i - 1) * 6 if i else 0))
        ch.addh(o); ch.fx.append((o, "flame%d" % i, o.scale[:]))
        inner = flat(H, "flamein", flame_pts(0.62, 0.15), fy, depth=0.1, ol=0.0)
        inner.scale = (fs * k * 0.72, fs * k * 0.72, fs * k * 0.72); inner.location = V(hc.x + x, hc.y - 0.2 * s, z + fs * k * 0.72)
        ch.addh(inner); ch.fx.append((inner, "flame%d" % i, inner.scale[:]))
    # ---- the anger vein mark beside the head ---------------------------------------------------------------------------------------------------
    vm = H.toon("vein", "#ee1f2b", "#b00d18", "#ff7a80")
    vs = 0.5 * s; vp = V(hc.x + rh * 1.78, hc.y - 0.35 * s, hc.z + rh * 0.55)
    root = H.link(bpy.data.objects.new("vein", None)); root.location = vp; root.rotation_euler = (0, 0, 0)
    for pts in vein_pieces():
        o = flat(H, "veinp", pts, vm, depth=0.16, ol=0.035); o.parent = root
    root.scale = (vs, vs, vs); root.rotation_euler = (0, math.radians(-12), 0)
    root.parent = ch.hp; root.location = vp - ch.hp.location; ch.fx.append((root, "vein", root.scale[:]))
    # ---- feet planted: a slightly wider stance ------------------------------------------------------------------------------------------------
    for fp, sx in ch.parts["feet"]: fp.location.x += sx * 0.04 * s
