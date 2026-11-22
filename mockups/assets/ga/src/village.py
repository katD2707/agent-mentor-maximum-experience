# "Làng gà" background: a yard in the middle, the arena, the library, the market and the warm pond around it.
#   blender -b -P village.py -- <out_dir>      -> lang.png (1600 x 1000)
import bpy, bmesh, math, os, sys, random
from mathutils import Vector
HERE = os.path.dirname(os.path.abspath(__file__))
_src = open(os.path.join(HERE, "chicken.py"), encoding="utf-8").read()
exec(_src[:_src.index("class Chicken")])
random.seed(7)

grass = toon("grass", "#a9dc86", "#8cc86a"); dirt = toon("dirt", "#efd6a8", "#d9b882", "#f8e8c8")
leaf = toon("leaf", "#6cc070", "#4c9a54", "#98dc8e"); blossom = toon("blossom", "#ffb7d0", "#f08cb0", "#ffd6e4")
trunk = toon("trunk", "#9a6a44", "#714a2e"); wood = toon("wood", "#c98a45", "#93592a", "#ecb878")
stone = toon("stone", "#c9c7cf", "#9f9caa", "#e6e4ec"); water = toon("water", "#5fcbe8", "#43a9cc", "#b8ecfa")
wall = toon("wall", "#fff3dc", "#e3cfa8"); roof_b = toon("roofb", "#5b8fe0", "#3e68b0", "#8ab2f0"); roof_r = toon("roofr", "#ef6a5a", "#c24b3e", "#ff9d8f")
canvas_w = toon("canvasw", "#ffffff", "#e3e3ea"); flagc = [toon("f1", "#ff6b6b", "#c94b4b"), toon("f2", "#ffd34d", "#d9a21f"), toon("f3", "#5bc0eb", "#3a93bb")]
flower = [flat("fl1", "#ff8fb1"), flat("fl2", "#ffe066"), flat("fl3", "#ffffff"), flat("fl4", "#b48cff")]

def box(name, loc, size, mat, rot=(0, 0, 0), bevel=0.06, outline=0.03):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    o = mesh_obj(name, bm); o.location = loc; o.scale = size; o.rotation_euler = rot
    if bevel:
        bv = o.modifiers.new("bev", "BEVEL"); bv.width = bevel / max(size); bv.segments = 2; bv.affect = "EDGES"
    return finish(o, mat, outline / max(size), subsurf=0)

def prism_roof(loc, w, d, h, mat):
    bm = bmesh.new()
    # gable facing the viewer: the ridge runs front to back, the front triangle is a wall
    v = [bm.verts.new(p) for p in ((-w, -d, 0), (w, -d, 0), (w, d, 0), (-w, d, 0), (0, -d, h), (0, d, h))]
    for f in ((0, 4, 5, 3), (1, 2, 5, 4), (2, 3, 5)): bm.faces.new([v[i] for i in f])
    o = mesh_obj("roof", bm); o.location = loc
    finish(o, mat, 0.03, subsurf=0)
    bm = bmesh.new(); t = [bm.verts.new(p) for p in ((-w * 0.86, 0, 0.02), (w * 0.86, 0, 0.02), (0, 0, h * 0.84))]; bm.faces.new(t)
    gab = mesh_obj("gable", bm); gab.location = loc + Vector((0, -d + 0.15, 0)); gab.data.materials.append(wall); gab.data.materials.append(outline_mat())
    sol = gab.modifiers.new("th", "SOLIDIFY"); sol.thickness = 0.05
    ball("gwin", loc + Vector((0, -d + 0.1, h * 0.36)), (0.28, 0.04, 0.28), water, outline=0.015)
    return o

# ground + paths
bm = bmesh.new(); bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=40); gp = mesh_obj("ground", bm); gp.data.materials.append(grass)
ball("plaza", (0, 1.2, 0.0), (6.4, 3.6, 0.04), dirt, outline=0)
for t in range(14):  # path from the bottom edge to the plaza
    y = -9 + t * 0.75; x = 0.9 * math.sin(t * 0.45)
    ball("path", (x, y, 0.0), (1.25, 0.75, 0.035), dirt, outline=0)
for k in range(40):  # a ring of flat stones around the plaza
    a = k / 40 * 2 * math.pi
    if -1.95 < a - 1.5 * math.pi < 0.25: continue  # gap where the path comes in
    ball("rim", (math.cos(a) * 6.45, 1.2 + math.sin(a) * 3.65, 0.06), (0.34, 0.24, 0.1), stone, outline=0.012)
bush = toon("bush", "#5fb768", "#438f4c", "#8fd78f")
for (x, y) in ((-5.2, 6.4), (5.4, 6.2), (-7.0, 0.8), (7.2, 3.2), (-2.6, -4.8), (3.0, -4.6), (-11.4, -2.0), (11.6, 2.0), (-6.4, -9.0), (6.8, -9.2)):
    for dx, r in ((-0.35, 0.5), (0.3, 0.6), (0.0, 0.45)):
        ball("bush", (x + dx, y, 0.35), (r, r * 0.85, r * 0.75), bush)

# arena (top-left): a low round wall with flags
ar = Vector((-8.2, 7.4, 0))
bpy.ops.mesh.primitive_torus_add(major_radius=2.6, minor_radius=0.35, major_segments=48, minor_segments=12)
t = bpy.context.active_object; t.location = ar + Vector((0, 0, 0.35)); t.scale = (1, 0.8, 1.2); finish(t, roof_r, 0.03, subsurf=0)
ball("arenafloor", ar + Vector((0, 0, 0.05)), (2.3, 1.85, 0.05), dirt, outline=0)
for k in range(4):
    a = k / 4 * 2 * math.pi + 0.4; p = ar + Vector((math.cos(a) * 2.6, math.sin(a) * 2.1, 0))
    cyl("pole", p + Vector((0, 0, 1.2)), 0.06, 2.4, wood)
    bm = bmesh.new(); v = [bm.verts.new(q) for q in ((0, 0, 0), (0.9, 0, -0.25), (0, 0, -0.5))]; bm.faces.new(v)
    f = mesh_obj("flag", bm); f.location = p + Vector((0.05, 0, 2.35)); f.data.materials.append(flagc[k % 3])
    sol = f.modifiers.new("th", "SOLIDIFY"); sol.thickness = 0.04

# library (top-right): a house with a blue roof and a round window
lb = Vector((8.0, 7.6, 0))
box("libwall", lb + Vector((0, 0, 1.4)), (3.9, 2.8, 2.8), wall)
prism_roof(lb + Vector((0, 0, 2.8)), 2.25, 1.65, 1.6, roof_b)
box("door", lb + Vector((0, -1.42, 0.75)), (0.8, 0.08, 1.3), wood, bevel=0.04)
ball("window", lb + Vector((-1.2, -1.42, 1.6)), (0.34, 0.05, 0.34), water, outline=0.02)
ball("window2", lb + Vector((1.2, -1.42, 1.6)), (0.34, 0.05, 0.34), water, outline=0.02)
for k in range(3):  # a stack of books by the door
    box("book", lb + Vector((1.7 + 0.02 * k, -2.1, 0.12 + 0.2 * k)), (0.42 - 0.05 * k, 0.3, 0.09), flagc[k], bevel=0.02, outline=0.015)

# market (right): a stall with a striped awning and crates
mk = Vector((10.0, -0.4, 0))
box("counter", mk + Vector((0, 0, 0.7)), (4.0, 1.4, 1.4), wood)
for sx in (-1, 1): cyl("post", mk + Vector((sx * 2.0, 0.5, 1.7)), 0.1, 3.0, wood)
for k in range(8):
    box("awning", mk + Vector((-2.1 + k * 0.6, -0.35, 3.05)), (0.62, 2.2, 0.08), canvas_w if k % 2 else roof_r, rot=(0.12, 0, 0), bevel=0.02, outline=0.015)
for k, dx in enumerate((-2.6, -2.0)):
    box("crate", mk + Vector((dx - 0.4, -0.6, 0.35)), (0.7, 0.7, 0.7), wood, bevel=0.03)
for k in range(6): ball("corn", mk + Vector((-1.5 + k * 0.6, -0.1, 1.48)), (0.26, 0.26, 0.18), flagc[1], outline=0.015)

# warm pond (bottom-left): the study room, rocks around the water
pd = Vector((-8.6, -2.6, 0))
ball("pond", pd + Vector((0, 0, 0.03)), (3.0, 2.0, 0.06), water, outline=0)
for k in range(16):
    a = k / 16 * 2 * math.pi; r = 1 + random.uniform(-0.05, 0.08)
    ball("rock", pd + Vector((math.cos(a) * 3.0 * r, math.sin(a) * 2.0 * r, 0.12)), (random.uniform(0.32, 0.5), random.uniform(0.28, 0.4), random.uniform(0.2, 0.3)), stone)

# trees, blossoms, fence, flowers
tshadow = flat("tshadow", "#8fc66d")
def tree(p, pink=False, s=1.0):
    ball("tshadow", p + Vector((0.3 * s, 0.2 * s, 0.01)), (1.1 * s, 0.75 * s, 0.01), tshadow, outline=0)
    cyl("trunk", p + Vector((0, 0, 0.7 * s)), 0.16 * s, 1.4 * s, trunk)
    m = blossom if pink else leaf
    for dx, dy, dz, r in ((0, 0, 1.9, 0.95), (-0.55, 0.1, 1.55, 0.7), (0.6, 0.05, 1.6, 0.72), (0.1, 0.2, 2.45, 0.6)):
        ball("crown", p + Vector((dx * s, dy * s, dz * s)), (r * s, r * s * 0.9, r * s * 0.85), m)
for p, pink, s in (((-12.6, 3.0, 0), True, 1.2), ((-3.8, 10.4, 0), False, 1.1), ((3.4, 10.6, 0), True, 1.0), ((12.8, 4.2, 0), False, 1.15),
                   ((-12.0, -7.0, 0), False, 1.0), ((12.4, -6.2, 0), True, 1.1), ((-4.6, -8.6, 0), True, 0.8), ((5.0, -8.2, 0), False, 0.85),
                   ((0.0, 11.2, 0), False, 1.2), ((-13.5, 9.5, 0), False, 1.3), ((14.0, 10.0, 0), True, 1.2)):
    tree(Vector(p), pink, s)
for k in range(13):  # fence along the bottom
    x = -12 + k * 2.0
    if abs(x) < 1.6: continue
    cyl("fpost", Vector((x, -10.6, 0.45)), 0.1, 0.9, wood)
    if k < 12 and abs(x + 1.0) > 1.6: box("rail", Vector((x + 1.0, -10.6, 0.6)), (1.0, 0.06, 0.06), wood, bevel=0.02, outline=0.015)
for k in range(70):
    x, y = random.uniform(-14, 14), random.uniform(-10, 11)
    if abs(x) < 7 and -2.6 < y < 5: continue
    ball("flower", (x, y, 0.05), (0.09, 0.09, 0.05), random.choice(flower), outline=0)

# the chickens' coops along the back of the yard: small houses with red roofs and a round door
coopw = toon("coopw", "#e7b06c", "#b7773d", "#f6d29a"); dark = flat("coopdoor", "#5a3420"); straw = toon("straw", "#f3d77a", "#d2b04a")
for k, x in enumerate((-2.6, 0.2, 3.0)):
    c = Vector((x, 6.1 + (0.25 if k == 1 else 0), 0))
    box("coop", c + Vector((0, 0, 0.55)), (1.5, 1.2, 1.1), coopw)
    prism_roof(c + Vector((0, 0, 1.1)), 0.95, 0.75, 0.85, roof_r)
    ball("door", c + Vector((0, -0.61, 0.42)), (0.3, 0.04, 0.34), dark, outline=0)
    box("ramp", c + Vector((0, -0.95, 0.1)), (0.5, 0.7, 0.06), coopw, rot=(0.25, 0, 0), bevel=0.02, outline=0.015)
    for dx in (-0.55, 0.5): ball("straw", c + Vector((dx, -0.75, 0.06)), (0.28, 0.2, 0.08), straw, outline=0.012)

# the village gate where the path comes in
gate_w = 1.6
for sx in (-1, 1): cyl("gatepost", Vector((sx * gate_w, -10.6, 1.4)), 0.16, 2.8, wood)
box("gatebeam", Vector((0, -10.6, 2.75)), (2 * gate_w + 0.8, 0.3, 0.3), roof_r, bevel=0.05)
box("gatesign", Vector((0, -10.75, 2.2)), (1.9, 0.12, 0.62), coopw, bevel=0.05)

# flower beds by the plaza and tufts of grass
for (x, y) in ((-4.6, -6.4), (5.8, -3.0), (-6.6, 3.6), (6.8, 4.4)):
    ball("bed", (x, y, 0.06), (1.0, 0.55, 0.12), dirt, outline=0.012)
    for k in range(7):
        a = k / 7 * 2 * math.pi
        ball("bloom", (x + math.cos(a) * 0.55, y + math.sin(a) * 0.28, 0.22), (0.14, 0.14, 0.12), flower[k % 4], outline=0.01)
tuft = toon("tuft", "#7cc65f", "#5aa548")
for k in range(45):
    x, y = random.uniform(-14, 14), random.uniform(-10, 11)
    if abs(x) < 7 and -2.8 < y < 5.2: continue
    for j in range(3): cone("tuft", Vector((x + j * 0.12, y, 0.12)), 0.06, 0.28, tuft, (random.uniform(-0.3, 0.3), random.uniform(-0.3, 0.3), 0), outline=0.008)

# --- depth and life (painted pass) ---
# far away: sky, a few clouds, two rows of hills; they fill the top band of the picture
skym = flat("sky", "#bfe3f5"); cloud = toon("cloud", "#ffffff", "#e3eef6")
bm = bmesh.new(); bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=40); sky = mesh_obj("skyplane", bm)
sky.location = (0, 19.5, 6); sky.rotation_euler = (math.radians(90), 0, 0); sky.data.materials.append(skym)
for x, z, sc_ in ((-11, 4.6, 1.3), (-2, 5.4, 1.0), (8, 4.9, 1.2), (15, 5.6, 0.9)):
    for dx, dz, r in ((0, 0, 1.0), (1.1, -0.15, 0.8), (-1.0, -0.2, 0.75), (0.4, 0.45, 0.7)):
        ball("cloud", (x + dx * sc_, 19.2, z + dz * sc_), (r * sc_ * 1.3, 0.2, r * sc_ * 0.75), cloud, outline=0.02)
far = toon("hillfar", "#9fcfa8", "#86b896"); near = toon("hillnear", "#88c46b", "#6eab58", "#a6d98a")
for k in range(9):
    ball("hill", (-18 + k * 4.6, 17.5, 0.2), (3.6, 1.2, 2.2 + (k % 3) * 0.5), far, outline=0.02)
for k in range(8):
    ball("hill", (-16 + k * 4.8, 15.8, 0.1), (3.2, 1.2, 1.4 + ((k + 1) % 3) * 0.35), near, outline=0.02)
# grass patches in two tones so the lawn is not one flat green
g_dark = flat("gdark", "#98d27a"); g_light = flat("glight", "#b6e396")
for k in range(36):
    x, y = random.uniform(-15, 15), random.uniform(-10.5, 13)
    if abs(x) < 7 and -2.8 < y < 5.2: continue
    ball("patch", (x, y, 0.004), (random.uniform(0.8, 1.8), random.uniform(0.4, 0.9), 0.002), random.choice((g_dark, g_light)), outline=0)
# stepping stones along the path
pstone = toon("pstone", "#e3d3b4", "#c4b08c", "#f3e8d2")
for t in range(11):
    y = -9.2 + t * 0.8; x = 0.9 * math.sin((t + 0.3) * 0.45) + random.uniform(-0.25, 0.25)
    ball("pstone", (x, y, 0.05), (0.32, 0.22, 0.05), pstone, outline=0.012)
# the pond: ripples and lily pads
ripple = flat("ripple", "#bfeffa"); pad = toon("pad", "#5cb85c", "#3f8f45")
for r, dx, dy in ((0.5, -0.6, 0.2), (0.8, -0.6, 0.2), (0.4, 1.0, -0.5)):
    bpy.ops.mesh.primitive_torus_add(major_radius=r, minor_radius=0.025, major_segments=40, minor_segments=6)
    t = bpy.context.active_object; t.location = pd + Vector((dx, dy, 0.1)); t.scale = (1, 0.65, 0.3); finish(t, ripple, 0, subsurf=0)
for dx, dy, r in ((1.6, 0.7, 0.32), (1.2, 1.1, 0.24), (-1.7, -0.6, 0.3)):
    ball("lily", pd + Vector((dx, dy, 0.1)), (r, r * 0.75, 0.02), pad, outline=0.01)
ball("lotus", pd + Vector((1.5, 0.75, 0.2)), (0.13, 0.13, 0.12), blossom, outline=0.01)
# bamboo clumps at the sides
bam = toon("bamboo", "#7cc35a", "#5a9c42", "#a8dd86"); bleaf = toon("bleaf", "#6fbf5b", "#4f9a45")
for bx, by in ((-14.2, -1.5), (14.6, -2.0), (-9.8, 12.0)):
    for j in range(5):
        h = random.uniform(2.6, 3.6); x = bx + random.uniform(-0.5, 0.5); y = by + random.uniform(-0.3, 0.3)
        cyl("bamboo", Vector((x, y, h / 2)), 0.09, h, bam)
        for q in range(3):
            cone("bleaf", Vector((x + 0.25, y, h * (0.6 + q * 0.15))), 0.08, 0.55, bleaf, (0, math.radians(70 + q * 15), 0), outline=0.008)
# red lanterns on posts by the gate and the market
lant = toon("lantern", "#e8453c", "#b02e28", "#ff8a7a"); cap = toon("lcap", "#f3c548", "#c99a20")
for lx, ly in ((-2.6, -10.2), (2.6, -10.2), (7.6, -1.6)):
    cyl("lpost", Vector((lx, ly, 1.0)), 0.07, 2.0, wood)
    box("larm", Vector((lx + 0.3, ly, 1.95)), (0.6, 0.06, 0.06), wood, bevel=0.01, outline=0.012)
    ball("lantern", Vector((lx + 0.55, ly, 1.55)), (0.22, 0.22, 0.28), lant, outline=0.014)
    cyl("lcap", Vector((lx + 0.55, ly, 1.86)), 0.12, 0.06, cap); cyl("lcap", Vector((lx + 0.55, ly, 1.25)), 0.12, 0.06, cap)
# a chimney on the library
box("chimney", lb + Vector((1.2, 0.4, 3.6)), (0.42, 0.42, 1.0), toon("brick", "#c97a5a", "#9a5640"), bevel=0.03)

# light + camera: a high three-quarter view (the chickens and the kid are layered on top in HTML)
sun = bpy.data.lights.new("sun", "SUN"); sun.energy = 3.5; sun.use_shadow = False; so = link(bpy.data.objects.new("sun", sun))
so.rotation_euler = (math.radians(48), math.radians(-28), math.radians(-30))
cam = bpy.data.cameras.new("cam"); cam.type = "ORTHO"; cam.ortho_scale = 27
th = math.radians(60); fwd = Vector((0, math.sin(th), -math.cos(th))); tgt = Vector((0, 1.8, 1.0))
co = link(bpy.data.objects.new("cam", cam)); co.location = tgt - fwd * 40; co.rotation_euler = (th, 0, 0); sc.camera = co
sc.render.resolution_x, sc.render.resolution_y = 1600, 1000
sc.render.filepath = os.path.join(OUT, "lang.png"); bpy.ops.render.render(write_still=True)
print("RENDERED village")
