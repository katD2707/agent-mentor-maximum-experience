# Chibi subject chicken (Gà Toán), toon look. Modes:
#   blender -b -P chicken.py -- <out_dir> lineup   4 growth stages
#   blender -b -P chicken.py -- <out_dir> faces    4 moods (adult)
#   blender -b -P chicken.py -- <out_dir> anim     idle + jump frames (transparent), 512 px
import bpy, bmesh, math, sys, os
from mathutils import Vector, Matrix

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else ["."]
OUT = ARGS[0]; MODE = ARGS[1] if len(ARGS) > 1 else "lineup"
SUBJ = ARGS[2] if len(ARGS) > 2 else "toan"; STAGE = int(ARGS[3]) if len(ARGS) > 3 else 3
# 5th argument "costume": dress the chicken in its Gunny-style costume set (costume.py) instead of the single comb / prop / scarf
COSTUME = len(ARGS) > 4 and ARGS[4] == "costume"
# modes gian (still) / ganim (idle loop): the ANGRY state of a neglected course (angry.py)
ANGRY = MODE in ("gian", "ganim")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# subject look: body tint, comb, prop
SUBJECTS = {"toan": "#fff8e8", "van": "#f7d6b4", "anh": "#ffffff", "su": "#f6d3a8", "dia": "#fff3dc", "cd": "#f3e3cc",
            "kinhte": "#f7e2c4", "ketoan": "#fbf0dc", "daicuong": "#f5dcc0"}
# accent per subject (lit, shade, highlight): neckerchief, tail feathers, prop details
ACCENTS = {
    "toan": ("#4a86f2", "#2a56b8", "#a8c6ff"), "van": ("#a8714a", "#6a4128", "#e0b88e"), "anh": ("#25a9a3", "#13756f", "#8ae6df"),
    "li": ("#f4c21f", "#c9930a", "#ffe58a"), "hoa": ("#9b59d0", "#6d3a9c", "#d2b0f0"), "sinh": ("#3cbf6a", "#26894a", "#9be8b4"),
    "su": ("#b8452e", "#86301f", "#ec8b74"), "dia": ("#2e9bd6", "#1d6f9c", "#93d0f2"), "tin": ("#3a4a72", "#232d4a", "#8fa0cc"),
    "cn": ("#ef8a2a", "#bf6412", "#ffc48a"), "cd": ("#2f4f7a", "#1e3352", "#8aa6cc"), "khoahoc": ("#8bc34a", "#5d8f22", "#cdee9a"),
    "nghethuat": ("#e94f9a", "#b52f70", "#ffaed4"), "kynang": ("#6a5cf0", "#4639b8", "#b9b2ff"),
    "khmt": ("#19b5ea", "#0d83b0", "#8fdcf7"), "ktmt": ("#6b7885", "#434c56", "#b4bfca"), "httt": ("#2fb86a", "#1d8a4c", "#98e6b8"),
    "khdl": ("#f06292", "#c03e6e", "#ffb3cc"), "vatli": ("#f08a1c", "#bf600a", "#ffc888"), "hoahoc": ("#8e5ad6", "#62389e", "#cdb2f5"),
    "kinhte": ("#e6b422", "#b08410", "#ffe58a"), "ketoan": ("#8c7ae6", "#6252b8", "#cfc6fb"), "daicuong": ("#3a4552", "#232a33", "#8a96a5"),
}
os.makedirs(OUT, exist_ok=True)

def lin(hexs):
    h = hexs.lstrip("#"); c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(((x + 0.055) / 1.055) ** 2.4 if x > 0.04045 else x / 12.92 for x in c) + (1.0,)

# MENTOR_LIVE=1: build into a new scene of the open Blender (via MCP for Blender) and skip rendering
LIVE = os.environ.get("MENTOR_LIVE") == "1"
if LIVE:
    sc = bpy.data.scenes.new("Lang ga: " + MODE); bpy.context.window.scene = sc
else:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
    try: sc.render.engine = eng; break
    except TypeError: pass
sc.view_settings.view_transform = "Standard"
world = bpy.data.worlds.new("w"); sc.world = world; world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = lin("#cfeaf7"); world.node_tree.nodes["Background"].inputs[1].default_value = 0.35

def link(o): sc.collection.objects.link(o); return o

MATS = {}
# PAINT: soft painted shading (eased 3-tone ramp, faint brush mottling, warm rim light); False = the flat 2-tone cel look
PAINT = True
OUTLINE_K = 1.45  # outline weight, heavier to sit on painted backgrounds
SUN_E = 2.1  # key light: lower = more of each form falls into the shaded tones (rounder look)
def toon(name, lit, shade=None, hi=None, edge=0.3):
    if name in MATS: return MATS[name]
    m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree; n = nt.nodes; n.clear()
    out = n.new("ShaderNodeOutputMaterial"); dif = n.new("ShaderNodeBsdfDiffuse"); s2r = n.new("ShaderNodeShaderToRGB")
    bw = n.new("ShaderNodeRGBToBW"); ramp = n.new("ShaderNodeValToRGB"); em = n.new("ShaderNodeEmission")
    cr = ramp.color_ramp
    L = lin(lit); S = lin(shade) if shade else tuple(x * 0.62 for x in L[:3]) + (1,)
    nt.links.new(dif.outputs[0], s2r.inputs[0]); nt.links.new(s2r.outputs[0], bw.inputs[0]); nt.links.new(bw.outputs[0], ramp.inputs[0])
    if not PAINT:
        cr.interpolation = "CONSTANT"
        cr.elements[0].position = 0.0; cr.elements[0].color = S
        cr.elements[1].position = edge; cr.elements[1].color = L
        if hi: e = cr.elements.new(0.95); e.color = lin(hi)
        nt.links.new(ramp.outputs[0], em.inputs[0]); nt.links.new(em.outputs[0], out.inputs[0])
        MATS[name] = m; return m
    # painted: shadow -> a warm mid tone -> lit, eased; the highlight only at the very top
    cr.interpolation = "EASE"
    M = tuple(S[i] * 0.45 + L[i] * 0.55 for i in range(3)) + (1,)
    cr.elements[0].position = 0.08; cr.elements[0].color = S
    cr.elements[1].position = 0.5; cr.elements[1].color = L
    e = cr.elements.new(edge); e.color = M
    if hi: e = cr.elements.new(0.97); e.color = lin(hi)
    # brush mottling: a soft large noise nudges the value a few percent, like uneven paint
    tc = n.new("ShaderNodeTexCoord"); nz = n.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 7.0; nz.inputs["Detail"].default_value = 3.0
    nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
    nr = n.new("ShaderNodeMapRange"); nr.inputs[3].default_value = 0.94; nr.inputs[4].default_value = 1.05
    nt.links.new(nz.outputs["Fac"], nr.inputs[0])
    mul = n.new("ShaderNodeMixRGB"); mul.blend_type = "MULTIPLY"; mul.inputs[0].default_value = 1.0
    nt.links.new(ramp.outputs[0], mul.inputs[1]); nt.links.new(nr.outputs[0], mul.inputs[2])
    # rim light: a warm glow along the silhouette, stronger on the lit side
    lw = n.new("ShaderNodeLayerWeight"); lw.inputs[0].default_value = 0.12
    rr = n.new("ShaderNodeValToRGB"); rr.color_ramp.interpolation = "EASE"
    rr.color_ramp.elements[0].position = 0.8; rr.color_ramp.elements[0].color = (0, 0, 0, 1)
    rr.color_ramp.elements[1].position = 0.95; rr.color_ramp.elements[1].color = lin("#fff0c8")
    nt.links.new(lw.outputs["Facing"], rr.inputs[0])
    lit_mask = n.new("ShaderNodeMath"); lit_mask.operation = "MULTIPLY"; lit_mask.inputs[1].default_value = 0.55
    nt.links.new(bw.outputs[0], lit_mask.inputs[0])
    rimf = n.new("ShaderNodeMixRGB"); rimf.blend_type = "MULTIPLY"; rimf.inputs[0].default_value = 1.0
    nt.links.new(rr.outputs[0], rimf.inputs[1]); nt.links.new(lit_mask.outputs[0], rimf.inputs[2])
    add = n.new("ShaderNodeMixRGB"); add.blend_type = "ADD"; add.inputs[0].default_value = 0.5
    nt.links.new(mul.outputs[0], add.inputs[1]); nt.links.new(rimf.outputs[0], add.inputs[2])
    nt.links.new(add.outputs[0], em.inputs[0]); nt.links.new(em.outputs[0], out.inputs[0])
    MATS[name] = m; return m

def flat(name, hexs):
    if name in MATS: return MATS[name]
    m = bpy.data.materials.new(name); m.use_nodes = True; n = m.node_tree.nodes; n.clear()
    out = n.new("ShaderNodeOutputMaterial"); em = n.new("ShaderNodeEmission"); em.inputs[0].default_value = lin(hexs)
    m.node_tree.links.new(em.outputs[0], out.inputs[0]); MATS[name] = m; return m

def outline_mat():
    m = flat("outline", "#3a2418"); m.use_backface_culling = True; return m

def finish(o, mat, outline=0.018, subsurf=1):
    o.data.materials.append(mat)
    for p in o.data.polygons: p.use_smooth = True
    if subsurf:
        s = o.modifiers.new("sub", "SUBSURF"); s.levels = subsurf; s.render_levels = subsurf
    if outline:
        o.data.materials.append(outline_mat())
        so = o.modifiers.new("ol", "SOLIDIFY"); so.thickness = outline * OUTLINE_K; so.offset = 1; so.use_flip_normals = True
        so.material_offset = 1; so.use_rim = False
    return o

def mesh_obj(name, bm):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free(); return link(bpy.data.objects.new(name, me))

def ball(name, loc, size, mat, rot=(0, 0, 0), outline=0.022, seg=32):
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=seg // 2, radius=1.0)
    o = mesh_obj(name, bm); o.location = loc; o.scale = size; o.rotation_euler = rot
    return finish(o, mat, outline / max(size))

def rbox(name, loc, size, mat, outline=0.02, rot=(0, 0, 0)):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    o = mesh_obj(name, bm); o.location = loc; o.scale = size; o.rotation_euler = rot
    bv = o.modifiers.new("bev", "BEVEL"); bv.width = 0.18; bv.segments = 3
    return finish(o, mat, outline / max(size), subsurf=2)

def cone(name, loc, r, depth, mat, rot, outline=0.014):
    bm = bmesh.new(); bmesh.ops.create_cone(bm, cap_ends=True, segments=24, radius1=r, radius2=0.0, depth=depth)
    o = mesh_obj(name, bm); o.location = loc; o.rotation_euler = rot
    return finish(o, mat, outline, subsurf=1)

def cyl(name, loc, r, depth, mat, outline=0.012):
    bm = bmesh.new(); bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=r, radius2=r, depth=depth)
    o = mesh_obj(name, bm); o.location = loc
    return finish(o, mat, outline, subsurf=0)

def torus(name, loc, R, r, mat, rot, scale=(1, 1, 1), outline=0, half=False):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, major_segments=40, minor_segments=10)
    t = bpy.context.active_object; t.name = name
    if half:
        bm = bmesh.new(); bm.from_mesh(t.data)
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.y < -R * 0.05], context="VERTS"); bm.to_mesh(t.data); bm.free()
    t.location = loc; t.rotation_euler = rot; t.scale = scale
    return finish(t, mat, outline, subsurf=0)

def face_rot(d): return (-math.atan2(d.z, math.hypot(d.x, d.y)), 0, math.atan2(d.x, -d.y))

def set_square(name, s, mat):
    bm = bmesh.new(); a, b = 1.0 * s, 1.45 * s
    outer = [Vector((0, 0, 0)), Vector((a, 0, 0)), Vector((0, 0, b))]
    r = (a + b - math.hypot(a, b)) / 2; inc = Vector((r, 0, r))
    O = [bm.verts.new(v) for v in outer]; I = [bm.verts.new(inc + (v - inc) * 0.42) for v in outer]
    for k in range(3):
        j = (k + 1) % 3; bm.faces.new((O[k], O[j], I[j], I[k]))
    o = mesh_obj(name, bm)
    sol = o.modifiers.new("th", "SOLIDIFY"); sol.thickness = 0.08; sol.offset = 0
    bv = o.modifiers.new("bev", "BEVEL"); bv.width = 0.025; bv.segments = 2
    o.data.materials.append(mat); o.data.materials.append(outline_mat())
    so = o.modifiers.new("ol", "SOLIDIFY"); so.thickness = 0.025; so.offset = 1; so.use_flip_normals = True; so.material_offset = 1; so.use_rim = False
    return o

class Chicken:
    """Group empty g; head pivot hp (head + face move together); named parts for animation."""
    def __init__(self, x, stage=3, moods=("neutral",), turn=-20, subject="toan"):
        self.parts = {}; self.moods = {}
        g = self.g = link(bpy.data.objects.new(f"ga{stage}_{x}", None)); g.location = (x, 0, 0)
        chick = stage == 1; s = self.s = {1: 0.72, 2: 0.86, 3: 1.0, 4: 1.06}[stage]
        DRESSED = COSTUME and subject in __import__("costume").SPEC
        sj = "_dressed" if DRESSED else subject  # costume mode: the old per-subject headwear / props below are replaced by costume.py
        body = toon("body_%s" % ("chick" if chick else subject), "#ffd23a" if chick else SUBJECTS.get(subject, "#fff8e8"), "#e8841a" if chick else "#d89058", "#fff6c8" if chick else "#ffffff")
        wingm = toon("wing%d" % (1 if chick else 2), "#ffbf2a" if chick else "#ffd49a", "#d0700f" if chick else "#c97a36")
        red = toon("comb", "#ff3d3d", "#c22a2a", "#ff8a8a"); orange = toon("beak", "#ffb21f", "#e07a10", "#ffe08a")
        blue = toon("blue", "#3f7df0", "#2a56b8", "#9cc0ff"); pink = flat("blush", "#ffa3b5")
        gold = toon("gold", "#ffcf3d", "#d99a16", "#fff1a8"); ink = toon("eye", "#2a1a14", "#1a100c"); white = flat("white", "#ffffff")
        bodyh = body
        if DRESSED and not chick:  # a hat covers the lit top of the head: lift the lit tones so the head stays as bright cream as the old adult
            bodyh = toon("body_head_" + subject, SUBJECTS.get(subject, "#fff8e8"), "#e9c9a0", "#ffffff")
            for nd in bodyh.node_tree.nodes:
                if nd.type == "VALTORGB" and len(nd.color_ramp.elements) >= 4:
                    e = nd.color_ramp.elements; e[0].position = 0.03; e[1].position = 0.1; e[2].position = 0.24
        if chick:
            rh = 0.98 * s; hc = Vector((0, 0, 1.0 * s)); bc = hc; rb = rh
        else:
            rb = 0.74 * s; rh = 0.8 * s; bc = Vector((0, 0.04, 0.82 * s)); hc = Vector((0, -0.06, 1.86 * s))
        hp = self.hp = link(bpy.data.objects.new("headpivot", None)); hp.parent = g; hp.location = hc if not chick else Vector((0, 0, 0.3 * s))
        self.bc, self.hc, self.rh, self.rb = bc, hc, rh, rb
        def add(o, key=None):
            o.parent = g
            if key: self.parts.setdefault(key, []).append(o)
            return o
        def addh(o, key=None):  # on the head: position relative to the head pivot
            o.parent = hp; o.location = o.location - hp.location
            if key: self.parts.setdefault(key, []).append(o)
            return o
        self.add, self.addh = add, addh
        if chick: addh(ball("body", hc, (rh, rh * 0.96, rh * 0.94), body))
        else:
            add(ball("body", bc, (rb, rb * 0.95, rb * 1.02), body), "body")
            bellym = toon("belly_%s" % subject, "#fffdf8", "#ecc79a", "#ffffff")
            db = Vector((0, -1, -0.12)).normalized()
            add(ball("belly", bc + db * rb * 0.9, (rb * 0.6, 0.08 * s, rb * 0.66), bellym, rot=face_rot(db), outline=0))
            addh(ball("head", hc, (rh, rh * 0.95, rh * 0.93), bodyh))
        er = (0.25 if chick else 0.21) * s
        for mood in moods:
            objs = []
            for sx in (-1, 1):
                d = Vector((0.34 * sx, -0.92, -0.02)).normalized(); p = hc + d * rh * 0.97; fwd = d * er * 0.42
                if mood == "happy":
                    objs.append(addh(torus("eye", p, er * 0.85, er * 0.2, ink, (math.radians(90), 0, math.atan2(d.x, -d.y)), half=True)))
                else:
                    k = {"surprised": 1.18, "sad": 0.95}.get(mood, 1.0); sq = {"sad": 0.78, "angry": 0.62}.get(mood, 1)
                    # a painted eye in layers: dark rim, amber iris, pupil, two highlights, an upper lash line
                    iris = toon("iris", "#b0662a", "#6e3a17", "#e6a35c"); pupil = flat("pupil", "#1c100b")
                    objs.append(addh(ball("eye", p, (er * 0.92 * k, er * 0.5, er * 1.15 * k * sq), ink, rot=face_rot(d), outline=0)))
                    objs.append(addh(ball("iris", p + d * er * 0.4 + Vector((0, 0, -0.1 * er)), (er * 0.7 * k, er * 0.12, er * 0.82 * k * sq), iris, rot=face_rot(d), outline=0)))
                    objs.append(addh(ball("pupil", p + d * er * 0.5 + Vector((0, 0, -0.08 * er)), (er * 0.4 * k, er * 0.08, er * 0.5 * k * sq), pupil, rot=face_rot(d), outline=0)))
                    objs.append(addh(ball("hl", p + d * er * 0.62 + Vector((-0.32 * er, 0, 0.45 * er)), (er * 0.3 * k, er * 0.08, er * 0.3 * k), white, outline=0)))
                    objs.append(addh(ball("hl2", p + d * er * 0.62 + Vector((0.3 * er, 0, -0.42 * er)), (er * 0.14 * k, er * 0.06, er * 0.14 * k), white, outline=0)))
                    objs.append(addh(torus("lash", p + d * er * 0.42 + Vector((0, 0, 0.04 * er)), er * 0.98 * k, er * 0.13, ink, (math.radians(90), 0, math.atan2(d.x, -d.y)), (1, 1, 1.15 * sq), half=True)))
                    if mood == "sad":  # brows slanting down at the outer end
                        b = rbox("brow", p + Vector((0, -0.05, er * 1.45)), (er * 0.9, 0.04, 0.05), ink, outline=0)
                        b.rotation_euler = (0, sx * 0.4, math.atan2(d.x, -d.y)); objs.append(addh(b))
                    if mood == "angry":  # deep frowning brows, the inner ends pulled down
                        b = rbox("brow", p + Vector((0, -0.07, er * 1.0)), (er * 1.3, 0.07, 0.11), ink, outline=0)
                        b.rotation_euler = (0, -sx * 0.62, math.atan2(d.x, -d.y)); objs.append(addh(b))
            self.moods[mood] = objs
        bk = hc + Vector((0, -rh * 0.97, -0.18 * s))
        addh(cone("beak_up", bk, 0.2 * s, 0.36 * s, orange, (math.radians(94), 0, 0)))
        self.beak_lo = addh(cone("beak_lo", bk + Vector((0, 0.04, -0.11 * s)), 0.12 * s, 0.2 * s, orange, (math.radians(110), 0, 0)))
        for sx in (-1, 1):
            d = Vector((0.62 * sx, -0.74, -0.2)).normalized()
            addh(ball("blush", hc + d * rh * 0.99, (0.15 * s, 0.04 * s, 0.09 * s), pink, rot=face_rot(d), outline=0))
        # feather tufts: a few at the back of the head, and fluffy cheeks
        for dx, tilt in ((-0.16, -0.35), (0.0, 0.0), (0.16, 0.35)):
            addh(cone("tuft", hc + Vector((dx * s, rh * 0.62, rh * 0.62)), 0.09 * s, 0.32 * s, body, (math.radians(-35), tilt, 0), outline=0.012))
        for sx in (-1, 1):
            for dz, ang in ((-0.18, 1.35), (-0.36, 1.75)):
                addh(cone("cheek", hc + Vector((sx * rh * 1.02, -0.06, dz * rh)), 0.09 * s, 0.3 * s, body, (0, sx * ang, 0), outline=0.012))
        pc = {1: 0.55, 2: 0.78, 3: 1.0, 4: 1.12}[stage]; top = hc + Vector((0, 0.02, rh * 0.93 + 0.2 * pc))
        comb = {"toan": "plus", "li": "bolt", "sinh": "leaf", "khoahoc": "leaf", "khmt": "braces",
                "su": None, "nghethuat": None, "daicuong": None}.get(subject, "classic")
        if DRESSED: comb = None
        if comb == "plus":
            addh(rbox("plus_h", top, (0.46 * pc, 0.16 * pc, 0.16 * pc), red)); addh(rbox("plus_v", top, (0.16 * pc, 0.16 * pc, 0.46 * pc), red))
        elif comb == "classic":  # a real chicken comb: three bumps, the middle one tallest
            for dx, dz, r in ((-0.19, -0.06, 0.13), (0, 0.04, 0.17), (0.19, -0.06, 0.13)):
                addh(ball("comb", top + Vector((dx * pc, 0.04, dz * pc - 0.05)), (r * pc, r * pc * 0.8, r * pc * 1.15), red))
        elif comb == "bolt":  # a lightning bolt: three slanted bars in yellow
            boltm = toon("bolt", "#ffd21f", "#d99a00", "#fff3a0")
            for dx, dz, rz in ((0.05, 0.22, -0.5), (-0.03, 0.02, 0.5), (0.05, -0.18, -0.5)):
                addh(rbox("bolt", top + Vector((dx * pc, 0.02, dz * pc)), (0.12 * pc, 0.12 * pc, 0.3 * pc), boltm, rot=(0, rz, 0)))
        elif comb == "leaf":  # a sprout: two leaves on a short stem
            leafm = toon("leafc", "#4cc65e", "#2f8f3f", "#a8ec9e")
            addh(cyl("stem", top + Vector((0, 0.02, -0.02 * pc)), 0.04 * pc, 0.3 * pc, leafm))
            for sx in (-1, 1):
                addh(ball("leaf", top + Vector((sx * 0.17 * pc, 0.02, 0.17 * pc)), (0.2 * pc, 0.07 * pc, 0.1 * pc), leafm, rot=(0, -sx * 0.5, 0)))
        elif comb == "braces":  # "{ }" in red letters
            cu = bpy.data.curves.new("braces", "FONT"); cu.body = "{ }"; cu.align_x = "CENTER"; cu.align_y = "CENTER"; cu.size = 0.62 * pc; cu.extrude = 0.05 * pc
            cu.materials.append(red); t = link(bpy.data.objects.new("braces", cu)); t.location = top + Vector((0, 0.0, 0.05 * pc)); t.rotation_euler = (math.radians(90), 0, 0); addh(t)
        # headwear
        if sj == "su":  # a bronze helmet with a red crest
            bronze = toon("bronze", "#d9a441", "#a0701c", "#ffe08a"); crest = toon("crest", "#d93a2a", "#a02418", "#ff8a7a")
            # a cap on the crown, rim above the eyes; the chick's head is its whole body, so its cap is relatively smaller
            f = 0.78 if chick else 1.0; z0 = rh * (0.52 if chick else 0.36)
            addh(ball("helmet", hc + Vector((0, 0.02, z0 + rh * 0.3 * f)), (rh * 0.9 * f, rh * 0.88 * f, rh * 0.46 * f), bronze))
            addh(torus("brim", hc + Vector((0, 0.02, z0)), rh * 0.84 * f, 0.055 * s, bronze, (0, 0, 0), (1, 0.98, 1), outline=0.012))
            addh(ball("crest", hc + Vector((0, 0.05, z0 + rh * 0.82 * f)), (0.08 * s, rh * 0.72 * f, 0.28 * s * f), crest))
        if sj == "nghethuat":  # a tilted beret
            beret = toon("beret", "#e94f9a", "#b52f70", "#ffaed4")
            addh(ball("beret", hc + Vector((0.1 * s, 0, rh * 0.92)), (rh * 0.82, rh * 0.78, rh * 0.24), beret, rot=(0, 0.25, 0)))
            addh(cyl("beretstem", hc + Vector((0.12 * s, 0, rh * 1.17)), 0.04 * s, 0.1 * s, beret))
        if sj == "daicuong":  # a mortarboard with a gold tassel
            capm = toon("capm", "#2d3540", "#1a1f26", "#5c6878"); goldt = toon("gold", "#ffcf3d", "#d99a16", "#fff1a8")
            addh(cyl("capbase", hc + Vector((0, 0, rh * 0.82)), rh * 0.55, 0.22 * s, capm))
            addh(rbox("capboard", hc + Vector((0, 0, rh * 0.96)), (rh * 1.5, rh * 1.5, 0.06 * s), capm, rot=(0, 0, math.radians(45))))
            addh(cyl("tassel", hc + Vector((rh * 0.62, -rh * 0.2, rh * 0.82)), 0.025 * s, 0.32 * s, goldt))
            addh(ball("tasselend", hc + Vector((rh * 0.62, -rh * 0.2, rh * 0.62)), (0.06 * s, 0.06 * s, 0.09 * s), goldt))
        if sj == "tin":  # pixel shades over the eyes
            shade_m = toon("shades", "#1f2430", "#10131a", "#4a5468")
            for sx in (-1, 1):
                d = Vector((0.34 * sx, -0.92, -0.02)).normalized(); p = hc + d * rh * 1.02
                addh(rbox("shade", p, (0.36 * s, 0.05 * s, 0.2 * s), shade_m, rot=(0, 0, math.atan2(d.x, -d.y))))
            addh(rbox("bridge", hc + Vector((0, -rh * 1.0, 0.03 * s)), (0.18 * s, 0.04 * s, 0.05 * s), shade_m))
        if sj == "hoahoc":  # lab goggles
            gog = toon("goggle", "#8e5ad6", "#62389e", "#cdb2f5")
            for sx in (-1, 1):
                d = Vector((0.34 * sx, -0.92, -0.02)).normalized()
                addh(torus("goggle", hc + d * rh * 1.04, 0.27 * s, 0.06 * s, gog, (math.radians(90), 0, math.atan2(d.x, -d.y)), outline=0.012))
            addh(torus("strap", hc + Vector((0, 0, -0.02 * s)), rh * 1.0, 0.04 * s, gog, (0, 0, 0), (1, 1, 0.5)))
        for sx in (-1, 1):
            w = ball("wing", Vector((0, 0, 0)), (0.16 * s, 0.38 * s, 0.5 * s), wingm)
            piv = link(bpy.data.objects.new("wingpivot", None)); piv.parent = g
            piv.location = bc + Vector((sx * rb * 0.9, 0.06, 0.32 * s)); piv.rotation_euler = (0.3, -sx * 0.3, 0)
            w.parent = piv; w.location = (sx * 0.05 * s, 0, -0.36 * s); self.parts.setdefault("wings", []).append((piv, sx))
            tipm = toon("wtip%d" % (1 if chick else 2), "#f5b52e" if chick else "#e9cfa6", "#d98d22" if chick else "#c99c66")
            # a second, shorter layer of feathers behind, then the tips: the wing reads as layered feathers
            w2 = ball("wing2", Vector((0, 0, 0)), (0.13 * s, 0.32 * s, 0.4 * s), tipm, outline=0.014); w2.parent = piv
            w2.location = (sx * 0.02 * s, 0.14 * s, -0.5 * s); w2.rotation_euler = (-0.35, 0, 0)
            for dy, dz in ((-0.16, -0.72), (0.0, -0.8), (0.16, -0.72), (0.3, -0.62)):
                f_ = ball("feather", Vector((0, 0, 0)), (0.07 * s, 0.09 * s, 0.17 * s), tipm, outline=0.014); f_.parent = piv
                f_.location = (sx * 0.06 * s, dy * s, dz * s); f_.rotation_euler = (-dy * 2.2, 0, 0)
        for sx in (-1, 1):  # each foot (leg + toes) hangs on a pivot inside the body, so it can swing for a walk
            fp = link(bpy.data.objects.new("footpivot", None)); fp.parent = g; fp.location = Vector((0.26 * sx * s, -0.02, 0.22 * s))
            self.parts.setdefault("feet", []).append((fp, sx))
            def onfoot(o): o.parent = fp; o.location = o.location - fp.location; return o
            if not chick: onfoot(cyl("leg", Vector((0.26 * sx * s, -0.02, 0.12 * s)), 0.055 * s, 0.24 * s, orange))
            for a in (-0.55, 0.0, 0.55):  # three toes
                d_ = Vector((math.sin(a), -math.cos(a), 0))
                onfoot(ball("toe", Vector((0.27 * sx * s, -0.04 * s, 0.05 * s)) + d_ * 0.13 * s, (0.06 * s, 0.17 * s, 0.055 * s), orange, rot=(0, 0, -a), outline=0.014))
        # the subject's colour: tail feathers and a neckerchief (the master keeps a gold scarf)
        acc = toon("acc_" + subject, *ACCENTS.get(subject, ACCENTS["toan"]))
        if stage >= 3:
            for j, a in enumerate((-0.9, -0.45, 0, 0.45, 0.9)):
                tall = 0.66 - abs(a) * 0.12
                add(ball("tail", bc + Vector((a * 0.42 * s, rb * 0.9, 0.62 * s + (0.6 - abs(a) * 0.3) * 0.25 * s)), (0.14 * s, 0.15 * s, tall * s),
                         (acc if j % 2 else wingm) if stage < 4 else (gold if j % 2 else wingm), rot=(-0.75, a * 0.85, 0)))
        if stage in (2, 3) and not DRESSED:
            add(torus("scarf", Vector((0, -0.04, 1.3 * s)), 0.64 * s, 0.13 * s, acc, (0, 0, 0), (1, 0.92, 0.7), outline=0.012))
            knot = cone("knot", Vector((0, 0, 0)), 0.2 * s, 0.32 * s, acc, (math.radians(180), 0, 0))
            knot.location = Vector((0.12 * s, -0.66 * s, 1.12 * s)); knot.scale = (1.2, 0.45, 1.1); add(knot)
        # where hand-held props go: the chick has no separate body, so hold them low on its round front
        pb, pr = (bc, rb) if not chick else (hc + Vector((0, 0, -0.22 * rh)), rb * 1.22)
        if subject == "toan" and not DRESSED:
            sq = set_square("eke", 0.62 * s * {1: 0.72, 2: 0.85}.get(stage, 1.0), blue)
            sq.location = pb + Vector((pr * 0.72, -pr * 1.02, -0.38 * s)); sq.rotation_euler = (0, math.radians(-8), math.radians(18)); add(sq)
        if sj == "van":  # a calligraphy brush held upright, ink tip down
            from mathutils import Euler
            k = {1: 0.68, 2: 0.82}.get(stage, 1.0); L = 1.05 * s * k
            wood = toon("wood", "#c98a45", "#93592a", "#ecb878"); inkm = toon("inktip", "#2b2320", "#151110"); band = toon("band", "#c0392b", "#8e2a20")
            rot = Euler((0.1, math.radians(-20), 0)); ax = rot.to_matrix() @ Vector((0, 0, 1))
            base = pb + Vector((pr * 0.82, -pr * 0.98, 0.08 * s))
            h = cyl("brush", Vector((0, 0, 0)), 0.075 * s * k, L, wood); h.location = base; h.rotation_euler = rot; add(h)
            b_ = cyl("band", Vector((0, 0, 0)), 0.085 * s * k, 0.08 * s * k, band); b_.location = base - ax * (L * 0.5 - 0.04 * s * k); b_.rotation_euler = rot; add(b_)
            tip = cone("tip", Vector((0, 0, 0)), 0.11 * s * k, 0.34 * s * k, inkm, (0, 0, 0)); tip.location = base - ax * (L * 0.5 + 0.17 * s * k)
            tip.rotation_euler = (Euler((math.pi, 0, 0)).to_matrix() @ Matrix.Identity(3)).to_euler() if False else (rot.x + math.pi, -rot.y, rot.z); add(tip)
        if sj == "anh":  # a speech bubble saying "Hi!"
            k = {1: 0.78, 2: 0.82}.get(stage, 1.0)
            bub = rbox("bubble", bc + Vector((rb * 1.25, -0.2, 1.62 * s)), (0.82 * s * k, 0.12 * s, 0.56 * s * k), white); add(bub)
            add(cone("bubtail", bub.location + Vector((-0.26 * s * k, 0, -0.34 * s * k)), 0.1 * s, 0.24 * s, white, (0, math.radians(150), 0)))
            cu = bpy.data.curves.new("hi", "FONT"); cu.body = "Hi!"; cu.align_x = "CENTER"; cu.align_y = "CENTER"; cu.size = 0.36 * s * k; cu.extrude = 0.015
            cu.materials.append(toon("hitext", "#d93a3a", "#a62a2a"))
            t = link(bpy.data.objects.new("hi", cu)); t.location = bub.location + Vector((0, -0.075 * s, -0.02)); t.rotation_euler = (math.radians(90), 0, 0); add(t)
        # hand-held props of the other subjects, held in front of the right wing
        u = 1.3 * s * {1: 0.72, 2: 0.85}.get(stage, 1.0); H = pb + Vector((pr * 0.8, -pr * 1.05, -0.12 * s))
        glass = toon("glassp", "#d6f1ff", "#a3d3ec", "#ffffff"); metal = toon("metal", "#dfe4ea", "#9aa3ad", "#ffffff")
        darkp = toon("darkp", "#3b3f4a", "#24272e", "#6b7180"); paper = toon("paperp", "#fffaf0", "#e6d8bc", "#ffffff")
        woodp = toon("wood", "#c98a45", "#93592a", "#ecb878"); greenp = toon("greenp", "#4cc65e", "#2f8f3f", "#a8ec9e")
        P = lambda o: add(o)
        def board(w, h, mat=paper):  # a flat panel facing the viewer
            return P(rbox("board", H + Vector((0, -0.02, 0.1 * u)), (w * u, 0.05 * u, h * u), mat))
        if sj == "li":  # a horseshoe magnet: red U with silver tips
            P(torus("magnet", H + Vector((0, 0, 0.14 * u)), 0.24 * u, 0.08 * u, toon("magred", "#e0413a", "#a82a24", "#ff8f87"), (math.radians(90), 0, math.radians(180)), half=True, outline=0.014))
            for sx in (-1, 1): P(rbox("tip", H + Vector((sx * 0.24 * u, 0, -0.06 * u)), (0.17 * u, 0.17 * u, 0.12 * u), metal))
        if sj == "hoa":  # a flask with purple liquid and bubbles
            P(cone("flask", H + Vector((0, 0, 0.0)), 0.3 * u, 0.42 * u, acc, (0, 0, 0)))
            P(cyl("neck", H + Vector((0, 0, 0.27 * u)), 0.08 * u, 0.2 * u, glass))
            for k, (dx, dz) in enumerate(((0.02, 0.46), (-0.06, 0.58), (0.05, 0.7))): P(ball("bubble", H + Vector((dx * u, 0, dz * u)), (0.05 * u + k * 0.012 * u,) * 3, glass, outline=0.008))
        if sj == "sinh":  # a double helix
            for i in range(9):
                a = i * 0.75; z = -0.3 * u + i * 0.09 * u
                p1 = H + Vector((math.cos(a) * 0.17 * u, math.sin(a) * 0.17 * u, z)); p2 = H + Vector((-math.cos(a) * 0.17 * u, -math.sin(a) * 0.17 * u, z))
                P(ball("dna", p1, (0.06 * u,) * 3, acc, outline=0.008)); P(ball("dna", p2, (0.06 * u,) * 3, greenp, outline=0.008))
                rung = cyl("rung", (p1 + p2) / 2, 0.018 * u, (p1 - p2).length, paper); rung.rotation_euler = (math.radians(90), 0, a + math.radians(90)); P(rung)
        if sj == "su":  # a scroll
            sc_ = cyl("scroll", H, 0.1 * u, 0.6 * u, paper); sc_.rotation_euler = (0, math.radians(90), math.radians(12)); P(sc_)
            for e in (-1, 1):
                r_ = cyl("rodend", H + Vector((e * 0.32 * u, 0, 0)), 0.12 * u, 0.05 * u, acc); r_.rotation_euler = sc_.rotation_euler; P(r_)
        if sj == "dia":  # a globe on a stand
            P(ball("globe", H + Vector((0, 0, 0.12 * u)), (0.27 * u,) * 3, acc))
            for dx, dz, sz in ((0.08, 0.2, 0.12), (-0.1, 0.05, 0.1), (0.05, -0.02, 0.08)):
                d = Vector((dx, -0.2, dz)).normalized(); P(ball("land", H + Vector((0, 0, 0.12 * u)) + d * 0.25 * u, (sz * u, 0.03 * u, sz * 0.8 * u), greenp, rot=face_rot(d), outline=0))
            P(torus("meridian", H + Vector((0, 0.02, 0.12 * u)), 0.31 * u, 0.025 * u, metal, (math.radians(90), 0, math.radians(90)), half=True))
            P(cyl("gbase", H + Vector((0, 0, -0.2 * u)), 0.14 * u, 0.06 * u, woodp))
        if sj in ("tin", "khmt"):  # a small laptop
            P(rbox("lapbase", H + Vector((0, -0.08 * u, -0.1 * u)), (0.6 * u, 0.36 * u, 0.05 * u), metal))
            scr = rbox("lapscreen", H + Vector((0, 0.08 * u, 0.12 * u)), (0.6 * u, 0.04 * u, 0.4 * u), darkp, rot=(math.radians(-12), 0, 0)); P(scr)
            P(rbox("lapglow", H + Vector((0, 0.05 * u, 0.12 * u)), (0.48 * u, 0.02 * u, 0.3 * u), toon("screen", "#8fe3ff", "#3fa7f2", "#ffffff"), rot=(math.radians(-12), 0, 0), outline=0))
        if sj == "cn":  # a gear
            P(torus("gear", H + Vector((0, 0, 0.08 * u)), 0.2 * u, 0.08 * u, acc, (math.radians(90), 0, 0), outline=0.014))
            for i in range(8):
                a = i / 8 * 2 * math.pi
                P(rbox("tooth", H + Vector((math.cos(a) * 0.3 * u, 0, 0.08 * u + math.sin(a) * 0.3 * u)), (0.1 * u, 0.12 * u, 0.1 * u), acc, rot=(0, -a, 0)))
        if sj == "cd":  # balance scales
            P(cyl("post", H + Vector((0, 0, 0.05 * u)), 0.03 * u, 0.6 * u, woodp)); P(cyl("sbase", H + Vector((0, 0, -0.25 * u)), 0.12 * u, 0.05 * u, woodp))
            P(rbox("beam", H + Vector((0, 0, 0.34 * u)), (0.62 * u, 0.05 * u, 0.04 * u), acc))
            for sx in (-1, 1):
                P(cyl("chain", H + Vector((sx * 0.29 * u, 0, 0.22 * u)), 0.01 * u, 0.24 * u, metal))
                P(ball("pan", H + Vector((sx * 0.29 * u, 0, 0.09 * u)), (0.14 * u, 0.14 * u, 0.04 * u), toon("brass", "#e3b04b", "#a87a1e", "#ffe08a")))
        if sj == "khoahoc":  # a magnifying glass
            P(torus("lensrim", H + Vector((0, 0, 0.16 * u)), 0.18 * u, 0.04 * u, acc, (math.radians(90), 0, 0), outline=0.012))
            P(ball("lens", H + Vector((0, 0, 0.16 * u)), (0.17 * u, 0.02 * u, 0.17 * u), glass, outline=0))
            h_ = cyl("handle", H + Vector((0.14 * u, 0, -0.1 * u)), 0.04 * u, 0.32 * u, woodp); h_.rotation_euler = (0, math.radians(35), 0); P(h_)
        if sj == "nghethuat":  # a palette with paint
            P(ball("palette", H + Vector((0, 0, 0.05 * u)), (0.34 * u, 0.04 * u, 0.26 * u), toon("palw", "#e2b07a", "#b07c48", "#f8d9b0"), rot=(0, 0.2, 0)))
            for k, (dx, dz) in enumerate(((-0.16, 0.12), (0.0, 0.17), (0.15, 0.1), (0.12, -0.08))):
                P(ball("paint", H + Vector((dx * u, -0.05 * u, 0.05 * u + dz * u)), (0.06 * u, 0.02 * u, 0.05 * u), (acc, toon("p2", "#3fa7f2", "#2a77b0"), toon("p3", "#ffd23a", "#d9a20a"), greenp)[k], outline=0))
        if sj == "kynang":  # an hourglass
            for sz in (-1, 1):
                c_ = cone("hg", H + Vector((0, 0, sz * 0.13 * u + 0.08 * u)), 0.16 * u, 0.26 * u, glass, (math.radians(0 if sz > 0 else 180), 0, 0)); P(c_)
                P(cyl("hgcap", H + Vector((0, 0, sz * 0.28 * u + 0.08 * u)), 0.2 * u, 0.05 * u, woodp))
            P(cone("sand", H + Vector((0, -0.01, -0.1 * u)), 0.12 * u, 0.12 * u, toon("sand", "#f2c25a", "#c9952a"), (0, 0, 0), outline=0))
        if sj == "ktmt":  # a chip with pins
            P(rbox("chip", H + Vector((0, 0, 0.08 * u)), (0.42 * u, 0.08 * u, 0.42 * u), darkp))
            P(rbox("die", H + Vector((0, -0.05 * u, 0.08 * u)), (0.18 * u, 0.02 * u, 0.18 * u), toon("diegold", "#f3c548", "#c99a20"), outline=0))
            for i in range(4):
                for sx in (-1, 1): P(rbox("pin", H + Vector((sx * 0.25 * u, 0, 0.08 * u + (-0.15 + i * 0.1) * u)), (0.08 * u, 0.04 * u, 0.03 * u), metal, outline=0.008))
        if sj == "httt":  # a database: stacked disks
            for i in range(3):
                P(cyl("dbdisk", H + Vector((0, 0, -0.12 * u + i * 0.15 * u)), 0.22 * u, 0.11 * u, acc))
                P(torus("dbband", H + Vector((0, 0, -0.06 * u + i * 0.15 * u)), 0.22 * u, 0.012 * u, darkp, (0, 0, 0), outline=0))
        if sj == "khdl":  # a bar chart board
            board(0.6, 0.5)
            for i, h in enumerate((0.16, 0.26, 0.38)):
                P(rbox("bar", H + Vector(((-0.17 + i * 0.17) * u, -0.06 * u, -0.1 * u + h * u / 2)), (0.11 * u, 0.04 * u, h * u), (acc, toon("bar2", "#3fa7f2", "#2a77b0"), greenp)[i], outline=0.008))
        if sj == "vatli":  # an atom: nucleus, three orbits and electrons
            P(ball("nucleus", H + Vector((0, 0, 0.1 * u)), (0.08 * u,) * 3, acc))
            for k, rz in enumerate((0, 60, -60)):
                P(torus("orbit", H + Vector((0, 0, 0.1 * u)), 0.26 * u, 0.012 * u, toon("orbit", "#3fa7f2", "#2a77b0"), (math.radians(90), math.radians(rz), 0), (1, 0.42, 1), outline=0))
                a = math.radians(rz + 90); P(ball("electron", H + Vector((math.cos(a) * 0.26 * u * 0.7, -0.02, 0.1 * u + math.sin(a) * 0.26 * u * 0.42)), (0.04 * u,) * 3, darkp, outline=0))
        if sj == "hoahoc":  # a test tube with liquid
            t_ = cyl("tube", H + Vector((0, 0, 0.08 * u)), 0.07 * u, 0.55 * u, glass); t_.rotation_euler = (0, math.radians(-15), 0); P(t_)
            l_ = cyl("tubeliq", H + Vector((0.03 * u, 0, -0.04 * u)), 0.078 * u, 0.28 * u, acc); l_.rotation_euler = t_.rotation_euler; P(l_)
        if sj == "kinhte":  # supply and demand board
            board(0.6, 0.5)
            for rz, m in ((0.6, toon("supply", "#3fa7f2", "#2a77b0")), (-0.6, toon("demand", "#e0413a", "#a82a24"))):
                P(rbox("curve", H + Vector((0, -0.06 * u, 0.1 * u)), (0.46 * u, 0.03 * u, 0.035 * u), m, rot=(0, rz, 0), outline=0))
        if sj == "ketoan":  # a calculator
            P(rbox("calc", H + Vector((0, 0, 0.08 * u)), (0.34 * u, 0.07 * u, 0.48 * u), acc))
            P(rbox("calcscreen", H + Vector((0, -0.04 * u, 0.24 * u)), (0.26 * u, 0.02 * u, 0.1 * u), toon("lcd", "#cfe8c0", "#9fbf8f"), outline=0))
            for i in range(3):
                for j in range(3): P(rbox("key", H + Vector(((-0.09 + i * 0.09) * u, -0.04 * u, (0.1 - j * 0.09) * u)), (0.06 * u, 0.02 * u, 0.055 * u), paper, outline=0.006))
        if sj == "daicuong":  # a book
            P(rbox("book", H + Vector((0, 0, 0.06 * u)), (0.44 * u, 0.12 * u, 0.56 * u), acc))
            P(rbox("pages", H + Vector((0.03 * u, 0, 0.06 * u)), (0.42 * u, 0.1 * u, 0.52 * u), paper, outline=0))
            P(rbox("title", H + Vector((0, -0.065 * u, 0.16 * u)), (0.26 * u, 0.01 * u, 0.08 * u), toon("goldt", "#f3c548", "#c99a20"), outline=0))
        if stage == 4 and not DRESSED:
            frame = flat("frame", "#3a2418")
            for sx in (-1, 1):
                d = Vector((0.34 * sx, -0.92, -0.02)).normalized()
                addh(torus("glass", hc + d * rh * 1.04, 0.27 * s, 0.03 * s, frame, (math.radians(90), 0, math.atan2(d.x, -d.y))))
            add(torus("scarf", Vector((0, -0.04, 1.3 * s)), 0.56 * s, 0.14 * s, gold, (0, 0, 0), (1, 0.95, 0.75), outline=0.012))
        if DRESSED:
            import types, costume
            self.kit = costume.dress(self, types.SimpleNamespace(**globals()), subject, stage)
        if ANGRY:
            import types, angry
            angry.apply(self, types.SimpleNamespace(**globals()), subject, stage)
        g.rotation_euler = (0, 0, math.radians(turn))
        self.show(moods[0])

    def show(self, mood, frame=None):
        for m, objs in self.moods.items():
            for o in objs:
                o.hide_render = m != mood
                if frame is not None: o.keyframe_insert("hide_render", frame=frame)

def camera(scale, z=7.0, x=0.0, res=(1800, 760)):
    sc.render.resolution_x, sc.render.resolution_y = res
    if os.environ.get("MENTOR_FAST"):
        sc.render.resolution_percentage = int(os.environ.get("MENTOR_PCT", "50"))
        try: sc.eevee.taa_render_samples = 6
        except Exception: pass
    sun = bpy.data.lights.new("sun", "SUN"); sun.energy = SUN_E; sun.use_shadow = False; so = link(bpy.data.objects.new("sun", sun))
    so.rotation_euler = (math.radians(55), math.radians(-40), math.radians(-55))
    cam = bpy.data.cameras.new("cam"); cam.type = "ORTHO"; cam.ortho_scale = scale
    co = link(bpy.data.objects.new("cam", cam)); co.location = (x, -20, z); co.rotation_euler = (math.radians(74), 0, 0); sc.camera = co

def ground(xs, sizes):
    grass = toon("grass", "#9fd67a", "#86c265")
    bm = bmesh.new(); bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30); gp = mesh_obj("ground", bm); gp.data.materials.append(grass)
    for x, (a, b) in zip(xs, sizes): ball("shadow", (x, 0.1, 0.002), (a, b, 0.001), flat("shadow", "#7fb85c"), outline=0)

if MODE == "lineup":
    xs = [-6.3 + i * 4.2 for i in range(4)]
    for x, st in zip(xs, (1, 2, 3, 4)): Chicken(x, st)
    ground(xs, [(0.75, 0.48)] + [(0.95, 0.6)] * 3); camera(17.5, 7.4)
    sc.render.filepath = os.path.join(OUT, "lineup.png"); (None if LIVE else bpy.ops.render.render(write_still=True))
elif MODE == "clineup":  # the four costume stages side by side (SUBJ)
    xs = [-6.3 + i * 4.2 for i in range(4)]
    for x, st in zip(xs, (1, 2, 3, 4)): Chicken(x, st, subject=SUBJ)
    ground(xs, [(0.75, 0.48)] + [(0.95, 0.6)] * 3); camera(17.5, 7.6)
    sc.render.filepath = os.path.join(OUT, "lineup.png"); (None if LIVE else bpy.ops.render.render(write_still=True))
elif MODE == "still":  # one transparent still of STAGE in the idle pose, same framing as the animation frames
    sc.render.film_transparent = True
    c = Chicken(0, STAGE, ("neutral",), subject=SUBJ)
    for piv, sx in c.parts["wings"]: piv.rotation_euler = (0.3, -sx * 0.3, 0)
    camera(5.9, 7.75, 0, (512, 512))
    sc.render.filepath = os.path.join(OUT, "still.png"); (None if LIVE else bpy.ops.render.render(write_still=True))
elif MODE == "trio":  # the three subjects side by side (STAGE)
    xs = [-4.2, 0, 4.2]
    for x, sj in zip(xs, ("toan", "van", "anh")): Chicken(x, STAGE, subject=sj)
    ground(xs, [(0.95, 0.6)] * 3); camera(13.5, 7.4, 0, (1400, 760))
    sc.render.filepath = os.path.join(OUT, "trio.png"); (None if LIVE else bpy.ops.render.render(write_still=True))
elif MODE == "row":  # preview: several subjects side by side (SUBJ = comma list), stage STAGE
    subs = SUBJ.split(","); xs = [(i - (len(subs) - 1) / 2) * 4.2 for i in range(len(subs))]
    for x, sj in zip(xs, subs): Chicken(x, STAGE, subject=sj)
    ground(xs, [(0.95, 0.6)] * len(subs)); camera(4.2 * len(subs) + 1, 7.4, 0, (int(330 * len(subs)), 760))
    sc.render.filepath = os.path.join(OUT, "row.png"); (None if LIVE else bpy.ops.render.render(write_still=True))
elif MODE == "faces":
    xs = [-6.3 + i * 4.2 for i in range(4)]
    for x, m in zip(xs, ("neutral", "happy", "surprised", "sad")):
        c = Chicken(x, 3, (m,))
        if m == "surprised": c.beak_lo.rotation_euler.x = math.radians(135)
        if m == "sad": c.hp.rotation_euler = (math.radians(-10), 0, 0)
    ground(xs, [(0.95, 0.6)] * 4); camera(17.5, 7.4)
    sc.render.filepath = os.path.join(OUT, "faces.png"); (None if LIVE else bpy.ops.render.render(write_still=True))
elif MODE == "icon":  # head and shoulders, happy, for the app icon (transparent, 1024 px)
    sc.render.film_transparent = True
    c = Chicken(0, STAGE, ("happy",), subject=SUBJ, turn=-8)
    for piv, sx in c.parts["wings"]: piv.rotation_euler = (0.3, -sx * 1.0, 0)
    camera(2.6, 7.55, 0, (1024, 1024))
    sc.render.filepath = os.path.join(OUT, f"icon-{SUBJ}.png"); (None if LIVE else bpy.ops.render.render(write_still=True))
elif MODE in ("happy", "sad", "surprised"):  # one transparent still, same framing as the animation frames
    sc.render.film_transparent = True
    c = Chicken(0, STAGE, (MODE,), subject=SUBJ)
    if MODE == "surprised": c.beak_lo.rotation_euler.x = math.radians(135)
    if MODE == "sad": c.hp.rotation_euler = (math.radians(-10), 0, 0)
    if MODE == "happy":
        for piv, sx in c.parts["wings"]: piv.rotation_euler = (0.3, -sx * 1.0, 0)
    camera(5.9, 7.75, 0, (512, 512))
    sc.render.filepath = os.path.join(OUT, f"{SUBJ}-{ {'happy': 'vui', 'sad': 'buon', 'surprised': 'ngac'}[MODE] }.png"); (None if LIVE else bpy.ops.render.render(write_still=True))
elif MODE == "gian":  # the angry state, one transparent still, same framing as the others
    sc.render.film_transparent = True
    c = Chicken(0, STAGE, ("angry",), subject=SUBJ)
    camera(5.9, 7.75, 0, (512, 512))
    sc.render.filepath = os.path.join(OUT, "gian.png"); (None if LIVE else bpy.ops.render.render(write_still=True))
elif MODE == "ganim":  # the angry idle loop: a little huff and a stomp, 24 frames at 12 fps
    sc.render.film_transparent = True; sc.render.fps = 12
    c = Chicken(0, STAGE, ("angry",), subject=SUBJ); g, hp = c.g, c.hp
    feet = c.parts["feet"]; fz = [fp.location.z for fp, _ in feet]
    for f in list(range(1, 25)) + [25]:
        t = ((f - 1) % 24) / 24 * 2 * math.pi
        # stomp: the left foot hits at frame 7, the right at 19; the body drops a little on each hit
        def lift(f0): d = abs(((f - f0 + 12) % 24) - 12); return max(0.0, 1 - d / 3.0)
        for i, (fp, sx) in enumerate(feet):
            fp.location.z = fz[i] + 0.16 * c.s * lift(4 if sx < 0 else 16); fp.keyframe_insert("location", frame=f)
        hit = max(lift(7) if True else 0, 0) * 0 + max(0.0, 1 - abs(((f - 7 + 12) % 24) - 12) / 2.0) + max(0.0, 1 - abs(((f - 19 + 12) % 24) - 12) / 2.0)
        g.location = (0, 0, -0.045 * hit); g.keyframe_insert("location", frame=f)
        g.scale = (1 + 0.05 * hit, 1 + 0.05 * hit, 1 - 0.05 * hit); g.keyframe_insert("scale", frame=f)
        hp.rotation_euler = (0.04 * math.sin(t * 4) , 0.03 * math.sin(t * 4 + 1), 0.05 * math.sin(t * 4)); hp.keyframe_insert("rotation_euler", frame=f)
        for o, kind, base in c.fx:
            if kind.startswith("flame"):
                ph = int(kind[5:]) * 2.1; fl = 1 + 0.2 * math.sin(t * 4 + ph) + 0.08 * math.sin(t * 8 + ph)
                o.scale = (base[0] * (1 - 0.07 * math.sin(t * 4 + ph)), base[1], base[2] * fl)
            else:
                o.scale = tuple(b * (1 + 0.22 * hit * 0.5 + 0.1 * (0.5 + 0.5 * math.sin(t * 4))) for b in base)
            o.keyframe_insert("scale", frame=f)
    camera(5.9, 7.75, 0, (512, 512))
    sc.frame_start, sc.frame_end = 1, 24
    sc.render.filepath = os.path.join(OUT, "f_"); (None if LIVE else bpy.ops.render.render(animation=True))
else:  # anim: idle (1-24) and jump (25-48) for one adult, transparent frames
    sc.render.film_transparent = True; sc.render.fps = 12
    c = Chicken(0, STAGE, ("neutral", "happy"), subject=SUBJ); g, hp = c.g, c.hp
    blinks = [o for o in c.moods["neutral"]]
    def key(obj, path, f, val):
        setattr(obj, path, val); obj.keyframe_insert(path, frame=f)
    # idle: breathe, sway the head, small wing flutter, blink at frame 17-19
    for f in range(1, 25):
        t = (f - 1) / 24 * 2 * math.pi
        key(g, "location", f, (0, 0, 0.03 * (1 - math.cos(t)) / 2))
        key(g, "scale", f, (1 + 0.015 * math.sin(t), 1 + 0.015 * math.sin(t), 1 - 0.02 * math.sin(t)))
        key(hp, "rotation_euler", f, (0, 0.07 * math.sin(t), 0))
        for piv, sx in c.parts["wings"]: key(piv, "rotation_euler", f, (0.3, -sx * (0.3 + 0.06 * math.sin(t * 2)), 0))
        c.show("neutral", f)
        for o in blinks:
            o.scale.z = o.scale.z if not hasattr(o, "_z") else o._z
    base = {o.name: tuple(o.scale) for o in blinks}
    for o in blinks:
        for f, k in ((16, 1.0), (17, 0.12), (18, 0.12), (19, 1.0)):
            sx_, sy_, sz_ = base[o.name]; o.scale = (sx_, sy_, sz_ * k); o.keyframe_insert("scale", frame=f)
    # jump: crouch, take off with flapping wings and a happy face, land with a squash
    J = [(25, 0, (1, 1, 1)), (27, 0, (1.12, 1.12, 0.82)), (29, 0.35, (0.92, 0.92, 1.14)), (32, 0.85, (0.97, 0.97, 1.04)),
         (35, 0.95, (1, 1, 1)), (38, 0.7, (1, 1, 1)), (41, 0.1, (0.95, 0.95, 1.08)), (43, 0, (1.14, 1.14, 0.84)), (46, 0, (0.98, 0.98, 1.03)), (48, 0, (1, 1, 1))]
    for f, z, sc_ in J:
        key(g, "location", f, (0, 0, z)); key(g, "scale", f, sc_)
    for f in range(25, 49):
        up = 29 <= f <= 41
        for piv, sx in c.parts["wings"]:
            flap = (0.3 + (1.1 if (f % 2 == 0) else 0.5)) if up else 0.3
            key(piv, "rotation_euler", f, (0.3, -sx * flap, 0))
        key(hp, "rotation_euler", f, (math.radians(-8) if up else 0, 0, 0))
        c.show("happy" if 27 <= f <= 45 else "neutral", f)
    for o in blinks:
        sx_, sy_, sz_ = base[o.name]; o.scale = (sx_, sy_, sz_); o.keyframe_insert("scale", frame=25)
    for a in bpy.data.actions:
        for fc in getattr(a, "fcurves", []):
            for kp in fc.keyframe_points: kp.interpolation = "LINEAR" if fc.data_path != "hide_render" else "CONSTANT"
    camera(5.9, 7.75, 0, (512, 512))
    sc.frame_start, sc.frame_end = 1, 48
    sc.render.filepath = os.path.join(OUT, "f_"); (None if LIVE else bpy.ops.render.render(animation=True))
print("RENDERED", MODE, sc.render.engine)
