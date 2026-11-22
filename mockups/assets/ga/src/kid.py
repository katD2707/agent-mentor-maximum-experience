# The student's chibi character, boy or girl, same toon look as the chickens.
#   blender -b -P kid.py -- <out_dir> <nam|nu>      idle (1-24) + wave (25-48) frames, 512 px, transparent
# Build the model from another script without rendering (chicken.py's toon helpers must already be defined,
# e.g. via lang_lib.py):
#   _k = open("kid.py", encoding="utf-8").read(); exec(_k[_k.index("\ndef build_kid"):_k.index("\nK = build_kid")])
#   K = build_kid("nam")      # or "nu"
# K.g root empty (rotate Z to turn the kid; face looks -Y, towards the camera), K.hp head pivot, K.arms / K.legs
# {-1: pivot, 1: pivot} swing about local X (arms: Y is the sideways splay), K.tails pigtail pivots (girl),
# K.eyes the objects to squash for a blink, K.base their rest scales.
import bpy, math, os, sys, types
from mathutils import Vector, Matrix
HERE = os.path.dirname(os.path.abspath(__file__))
if "toon" not in globals():
    _src = open(os.path.join(HERE, "chicken.py"), encoding="utf-8").read()
    exec(_src[:_src.index("class Chicken")])  # scene setup + toon helpers (ball, rbox, cone, cyl, torus, toon, flat...)

KIND = ARGS[1] if len(ARGS) > 1 else "nam"
def build_kid(kind="nam"):
    import types
    girl = kind == "nu"
    skin = toon("skin", "#ffe2cc", "#f0b99a", "#fff3ea"); hair = toon("hair", "#5a3828", "#33200f", "#8a5c42")
    hair2 = toon("hair2", "#7a5139", "#46291a", "#b4805e")  # lighter locks in front, for depth between the layers
    shirt = toon("shirt", "#ffffff", "#d3d9ea", "#ffffff"); navy = toon("navy", "#34508f", "#20346a", "#5c7cc0")
    shoe = toon("shoe", "#6a4430", "#3a271d", "#9a6a4c"); sole = toon("sole", "#fff6e8", "#d8c8b0", "#ffffff")
    ink = toon("eye", "#2a1a14", "#1a100c"); white = flat("white", "#ffffff")
    pink = flat("blush", "#ffa3b5"); red = toon("red", "#e8413c", "#b02c28", "#ff8a85"); mouthm = flat("mouth", "#b2493c")
    shine = flat("hshine", "#b88462")
    K = types.SimpleNamespace(arms={}, legs={}, tails=[], eyes=[], base={}, parts={})
    g = K.g = link(bpy.data.objects.new("kid", None))
    hp = K.hp = link(bpy.data.objects.new("head", None)); hp.parent = g; hc = Vector((0, 0, 1.78)); hp.location = hc
    def add(o, par=None):
        par = par or g; o.parent = par
        if par is hp: o.location = o.location - hc
        return o
    R = 0.86; HR = (R, R * 0.92, R * 0.9)
    def S(az, el, k=1.0):  # a point on (k times) the head's surface; az 0 = front, + to the right; el up
        a, e = math.radians(az), math.radians(el)
        return hc + Vector((HR[0] * math.cos(e) * math.sin(a), -HR[1] * math.cos(e) * math.cos(a), HR[2] * math.sin(e))) * k
    def lock(a, b, r, mat, bulge=0.04, ol=0.014, par=None, name="lock", bend=0.0, p=0.9):
        """A teardrop lock of hair: round and thick at a, drawn out to a point at b, bowed outward from the head by
        `bulge`, its tip bent sideways by `bend` (in units of its radius)."""
        d = b - a; L = d.length; out = (((a + b) / 2) - hc).normalized() * bulge
        bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=14, v_segments=12, radius=1.0)
        for v in bm.verts:  # a lathe: round at the base, widest near a third of the way, drawn out to a point
            x, y, z = v.co; rho = math.hypot(x, y); tt = (z + 1) / 2
            w = r * math.sin(math.pi * tt ** 0.55) ** p
            ux, uy = (x / rho, y / rho) if rho > 1e-6 else (0.0, 0.0)
            v.co = Vector((ux * w + bend * r * tt * tt * 2.5, uy * w * 0.85, tt * L))
        o = mesh_obj(name, bm); o.location = a + out; o.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
        finish(o, mat, ol, subsurf=0)
        return add(o, par or hp)
    add(ball("head", hc, HR, skin), hp)
    for sx in (-1, 1):
        add(ball("ear", hc + Vector((sx * R * 0.94, 0.06, -0.1)), (0.1, 0.13, 0.16), skin), hp)
    # ---- hair: a scalp cap, then layers of locks over it like shingles (back and sides), side locks, crown tufts,
    # a fringe of distinct strands, and a pale streak on the strands that face the light
    hairhi = toon("hairhi", "#a87a5e", "#8a5c42", "#c89a7c")
    add(ball("haircap", hc + Vector((0, 0.15, 0.15)), (R * 1.02, R * 0.98, R * 0.88), hair), hp)
    add(ball("hairback", hc + Vector((0, 0.42, -0.1 if not girl else -0.2)), (0.76, 0.44, 0.58 if not girl else 0.66), hair), hp)
    CC, CR = hc + Vector((0, 0.15, 0.15)), (R * 1.02, R * 0.98, R * 0.88)
    def SC(az, el, k=1.0):  # a point on the hair cap
        a, e = math.radians(az), math.radians(el)
        return CC + Vector((CR[0] * math.cos(e) * math.sin(a), -CR[1] * math.cos(e) * math.cos(a), CR[2] * math.sin(e))) * k
    rows = (62, 22, -10) if not girl else (62, 22, -12, -44)
    for ri, e0 in enumerate(rows):
        for ai, a in enumerate(range(54 + (12 if ri % 2 else 0), 306, 24)):
            if e0 < 30 and (a < 112 or a > 248): continue  # leave the cheeks and ears clear
            j = math.sin(a * 0.37 + ri * 1.9)
            r_ = 0.2 if e0 > 0 else 0.18
            a_, b_ = SC(a, e0 + 34, 0.9), SC(a + 8 * j, e0 - 44 + 5 * j, 1.1)
            lock(a_, b_, r_, hair2 if (ai + ri) % 2 else hair, 0.1, name="layer", bend=0.5 * j)
            if a > 230 and e0 > 30: lock(a_ + (b_ - a_) * 0.1, a_ + (b_ - a_) * 0.6, r_ * 0.4, hairhi, 0.1, ol=0, name="streak")    # side locks in front of the ears, a longer pair for the girl
    for sx in (-1, 1):
        lock(S(sx * 72, 44, 1.07), S(sx * 86, 8 if not girl else -26, 1.03), 0.15, hair2, 0.05, name="side")
        lock(S(sx * 66, 40, 1.1), S(sx * 78, 22 if not girl else -6, 1.06), 0.12, hair, 0.06, name="side2")
    # crown: hair tufts out of a whorl, leaning back a little
    if not girl:
        for az, el, ln, rr, tilt in ((-34, 76, 0.34, 0.17, -0.4), (0, 82, 0.46, 0.19, 0.0), (32, 76, 0.36, 0.17, 0.4), (150, 70, 0.3, 0.15, 0.2), (-140, 66, 0.28, 0.14, -0.2)):
            a = S(az, el, 1.1); out = (a - hc).normalized(); b = a + out * ln + Vector((tilt * 0.4, 0.14, 0))
            lock(a, b, rr, hair2 if az in (0, 150) else hair, 0.0, name="tuft")
    else:
        for az, el, ln, rr, tilt in ((-30, 78, 0.3, 0.15, -0.5), (32, 76, 0.26, 0.14, 0.5)):
            a = S(az, el, 1.1); out = (a - hc).normalized(); b = a + out * ln + Vector((tilt * 0.3, 0.1, 0))
            lock(a, b, rr, hair, 0.0, name="tuft")
        a = S(4, 80, 1.1); lock(a, a + Vector((0.1, -0.04, 0.34)), 0.07, hair2, 0.0, ol=0.012, name="ahoge", bend=2.0)  # a curl standing up
    # fringe: distinct strands over the forehead, parted a little left of centre, sweeping out to both sides
    FR = (-62, -46, -30, -15, 0, 14, 30, 46, 62)
    tips = (30, 32, 34, 36, 34, 36, 33, 31, 29)
    for i, (az, te) in enumerate(zip(FR, tips)):
        sw = -10 if az < -10 else (12 if az > 4 else 2)
        a_, b_ = S(az * 0.8, 68, 1.12), S(az * 0.98 + sw, te, 1.06); r_ = 0.145 + (0.02 if i % 2 else 0)
        lock(a_, b_, r_, hair2 if i % 2 else hair, 0.05, name="fringe")
        if az < 20:  # the light comes from the left, so those strands carry a streak
            lock(a_ + (b_ - a_) * 0.1, a_ + (b_ - a_) * 0.62, r_ * 0.5, hairhi, 0.09, ol=0, name="streak")
    for az, te, rr in ((-20, 28, 0.17), (22, 26, 0.16)):  # two bolder locks in front
        a_, b_ = S(az * 0.7, 66, 1.14), S(az + (-6 if az < 0 else 8), te, 1.1)
        lock(a_, b_, rr, hair2, 0.07, ol=0.016, name="bang")
        if az < 0: lock(a_ + (b_ - a_) * 0.1, a_ + (b_ - a_) * 0.6, rr * 0.5, hairhi, 0.12, ol=0, name="streak")
    if girl:
        for sx in (-1, 1):  # pigtails with volume: fat droplets of hair on a pivot at a red tie
            tie = S(sx * 108, 30, 1.04) + Vector((0, 0.12, 0))
            pv = link(bpy.data.objects.new("tail", None)); pv.parent = hp; pv.location = tie - hc; K.tails.append((pv, sx))
            def tl(a, b, r, mat, bend=0.0):
                o = lock(tie + Vector(a), tie + Vector(b), r, mat, 0.0, ol=0.016, par=hp, name="tail", bend=bend, p=0.6)
                o.parent = pv; o.location = o.location - pv.location - hc + hc  # (add() already made it head-relative)
                return o
            tl((sx * 0.06, 0.04, -0.3), (sx * 0.3, 0.1, -1.12), 0.3, hair, bend=0.4 * sx)
            tl((-sx * 0.02, -0.12, -0.24), (sx * 0.1, -0.1, -0.98), 0.2, hair2, bend=0.5)
            tl((sx * 0.16, 0.1, -0.24), (sx * 0.5, 0.16, -0.9), 0.17, hair, bend=-0.5)
            tl((sx * 0.0, -0.1, -0.34), (sx * 0.14, -0.08, -0.84), 0.075, hairhi, bend=0.0)
            o = ball("tie", Vector((0, 0, 0.0)), (0.14, 0.14, 0.11), red); o.parent = pv
            o = ball("tiebow", Vector((sx * 0.12, -0.08, 0.05)), (0.12, 0.045, 0.07), red, rot=(0, sx * 0.6, 0)); o.parent = pv
            o = ball("tiebow2", Vector((sx * 0.02, -0.08, 0.14)), (0.08, 0.045, 0.11), red, rot=(0, sx * -0.5, 0)); o.parent = pv
    # ---- face
    for sx in (-1, 1):
        d = Vector((0.33 * sx, -0.93, -0.12)).normalized(); p = hc + d * R * 0.9; er = 0.17
        iris = toon("kiris", "#7a4a2a", "#4a2a16", "#b98352"); pupil = flat("kpupil", "#1c100b")
        for nm, o in (("eye", ball("eye", p, (er * 0.85, er * 0.45, er * 1.2), ink, rot=face_rot(d), outline=0)),
                      ("iris", ball("iris", p + d * er * 0.36 + Vector((0, 0, -0.1 * er)), (er * 0.66, er * 0.12, er * 0.86), iris, rot=face_rot(d), outline=0)),
                      ("pupil", ball("pupil", p + d * er * 0.46 + Vector((0, 0, -0.08 * er)), (er * 0.36, er * 0.08, er * 0.5), pupil, rot=face_rot(d), outline=0)),
                      ("hl", ball("hl", p + d * er * 0.58 + Vector((-0.3 * er, 0, 0.45 * er)), (er * 0.3, er * 0.08, er * 0.3), white, outline=0)),
                      ("hl2", ball("hl2", p + d * er * 0.58 + Vector((0.28 * er, 0, -0.42 * er)), (er * 0.13, er * 0.06, er * 0.13), white, outline=0))):
            add(o, hp); K.eyes.append(o)
        add(torus("lash", p + d * er * 0.38 + Vector((0, 0, 0.05 * er)), er * 0.95, er * 0.12, ink, (math.radians(90), 0, math.atan2(d.x, -d.y)), (1, 1, 1.2), half=True), hp)
        # brows: short tilted dashes
        bd = Vector((0.36 * sx, -0.9, 0.3)).normalized()
        add(ball("brow", hc + bd * R * 0.92, (0.08, 0.025, 0.022), hair, rot=(0, -sx * 0.25, math.atan2(bd.x, -bd.y)), outline=0), hp)
        d2 = Vector((0.55 * sx, -0.8, -0.32)).normalized()
        add(ball("blush", hc + d2 * R * 0.9, (0.13, 0.04, 0.07), pink, rot=face_rot(d2), outline=0), hp)
    add(torus("smile", hc + Vector((0, -R * 0.86, -0.36)), 0.08, 0.022, mouthm, (math.radians(-90), 0, 0), half=True), hp)
    K.base = {o.name: tuple(o.scale) for o in K.eyes}
    # ---- body: a neck, a tapered shirt, the red scarf, trousers or a skirt
    add(cyl("neck", Vector((0, 0, 1.03)), 0.15, 0.14, skin))
    add(ball("chest", Vector((0, 0.02, 0.86)), (0.44, 0.35, 0.34), shirt))
    add(ball("waist", Vector((0, 0.02, 0.64)), (0.37, 0.3, 0.25), shirt))
    add(torus("scarfring", Vector((0, -0.03, 1.0)), 0.3, 0.09, red, (0, 0, 0), (1, 0.95, 0.6), outline=0.012))
    sk = add(cone("scarf", Vector((0, -0.31, 0.85)), 0.15, 0.3, red, (math.radians(180), 0, 0))); sk.scale = (1.0, 0.4, 1.0)
    for sx in (-1, 1):  # shirt collar points
        add(cone("collar", Vector((sx * 0.17, -0.27, 0.97)), 0.1, 0.19, shirt, (math.radians(150), sx * 0.6, 0)))
    if not girl:
        add(ball("trousers", Vector((0, 0.02, 0.47)), (0.42, 0.34, 0.2), navy))
        add(torus("belt", Vector((0, 0.02, 0.58)), 0.36, 0.035, shoe, (0, 0, 0), (1, 0.82, 1), outline=0.01))
        legm, lr, lp = navy, 0.1, 0.4
    else:
        bm = bmesh.new(); bmesh.ops.create_cone(bm, cap_ends=True, segments=28, radius1=0.5, radius2=0.3, depth=0.36)
        sk = add(finish(mesh_obj("skirt", bm), navy, 0.02, 1)); sk.location = (0, 0.02, 0.46)
        legm, lr, lp = skin, 0.075, 0.4
    for sx in (-1, 1):
        a = link(bpy.data.objects.new("arm", None)); a.parent = g; a.location = (sx * 0.42, 0.0, 0.98); a.rotation_euler = (0, -sx * 0.25, 0)
        for o, loc in ((ball("arm", Vector((0, 0, 0)), (0.12, 0.12, 0.3), shirt), (0, 0, -0.24)),
                       (ball("hand", Vector((0, 0, 0)), (0.11, 0.11, 0.11), skin), (0, 0, -0.52)),
                       (ball("cuff", Vector((0, 0, 0)), (0.13, 0.13, 0.06), shirt), (0, 0, -0.43))):
            o.parent = a; o.location = loc
        K.arms[sx] = a
        l = link(bpy.data.objects.new("leg", None)); l.parent = g; l.location = (sx * 0.17, 0.02, 0.46)
        for o, loc in ((cyl("leg", Vector((0, 0, 0)), lr, lp, legm), (0, 0, -0.22)),
                       (ball("shoe", Vector((0, 0, 0)), (0.135, 0.21, 0.1), shoe), (0.01 * sx, -0.06, -0.37)),
                       (ball("sole", Vector((0, 0, 0)), (0.14, 0.22, 0.04), sole), (0.01 * sx, -0.06, -0.43))):
            o.parent = l; o.location = loc
        if girl:
            o = cyl("sock", Vector((0, 0, 0)), 0.085, 0.14, shirt); o.parent = l; o.location = (0, 0, -0.32)
        else:
            o = torus("cuff", Vector((0, 0, 0)), 0.095, 0.03, navy, (0, 0, 0), outline=0.008); o.parent = l; o.location = (0, 0, -0.33)
        K.legs[sx] = l
    return K
K = build_kid(KIND); g, hp, arms, eyes, base = K.g, K.hp, [(K.arms[s], s) for s in (-1, 1)], K.eyes, K.base
g.rotation_euler = (0, 0, math.radians(-12))

# idle: breathe, sway the head, blink; arms swing a little
sc.render.film_transparent = True; sc.render.fps = 12
def key(o, path, f, v): setattr(o, path, v); o.keyframe_insert(path, frame=f)
for f in range(1, 25):
    t = (f - 1) / 24 * 2 * math.pi
    key(g, "scale", f, (1 + 0.012 * math.sin(t), 1 + 0.012 * math.sin(t), 1 - 0.016 * math.sin(t)))
    key(hp, "rotation_euler", f, (0, 0.06 * math.sin(t), 0))
    for piv, sx in arms: key(piv, "rotation_euler", f, (0.08 * math.sin(t + sx), -sx * 0.25, 0))
    for piv, sx in K.tails: key(piv, "rotation_euler", f, (0, 0, 0.05 * math.sin(t - 0.8) * sx))
for o in eyes:
    for f, k in ((14, 1.0), (15, 0.12), (16, 0.12), (17, 1.0)):
        x, y, z = base[o.name]; o.scale = (x, y, z * k); o.keyframe_insert("scale", frame=f)
# wave (frames 25-48): the right arm goes up and waves, a small hop
for f in range(25, 49):
    u = (f - 25) / 23
    up = min(1, u * 5, (1 - u) * 5)                      # raise, hold, lower
    wave = math.sin((f - 25) / 23 * 2 * math.pi * 3) * 0.35 * up
    for piv, sx in arms:
        if sx == 1: key(piv, "rotation_euler", f, (0, -0.25 - 2.35 * up + wave, 0))
        else: key(piv, "rotation_euler", f, (0, 0.25, 0))
    key(g, "location", f, (0, 0, 0.06 * abs(math.sin(u * math.pi * 2)) * up))
    key(g, "scale", f, (1, 1, 1))
    key(hp, "rotation_euler", f, (0, -0.08 * up, 0))
    for piv, sx in K.tails: key(piv, "rotation_euler", f, (0, 0, 0.05 * math.sin(u * 12) * sx * up))
    for o in eyes:
        x, y, z = base[o.name]; o.scale = (x, y, z); o.keyframe_insert("scale", frame=f)
for a in bpy.data.actions:
    for fc in getattr(a, "fcurves", []):
        for kp in fc.keyframe_points: kp.interpolation = "LINEAR"
sun = bpy.data.lights.new("sun", "SUN"); sun.energy = SUN_E; sun.use_shadow = False; so = link(bpy.data.objects.new("sun", sun))
so.rotation_euler = (math.radians(55), math.radians(-40), math.radians(-55))
cam = bpy.data.cameras.new("cam"); cam.type = "ORTHO"; cam.ortho_scale = 3.6
co = link(bpy.data.objects.new("cam", cam)); co.location = (0, -20, 7.05); co.rotation_euler = (math.radians(74), 0, 0); sc.camera = co
sc.render.resolution_x = sc.render.resolution_y = 512
sc.frame_start, sc.frame_end = 1, 48
sc.render.filepath = os.path.join(OUT, "k_"); bpy.ops.render.render(animation=True)
print("RENDERED kid", KIND)
