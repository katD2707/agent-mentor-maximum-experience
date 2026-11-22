# The Làng gà village (student home screen): a village that fits one screen, built in 3D as
# the layout for the painted picture (paint_world.py repaints it tile by tile in a hand-painted film style).
#   blender -b -P lang.py -- <out_dir> [base|ids|all|layout] [preview]
# Writes into <out_dir>:
#   base.png       9600 x 3000 render (sky transparent), rendered in tiles
#   ids.png        flat colour per occluder group (no anti-aliasing): which thing is in front at every pixel
#   layout.json    world <-> picture mapping, place names, doors, walk blockers, occluder colours, steam spots
# Places (only those with a feature): the yard (sân đình) with the banyan tree and the well, the gate, the notice board,
# the warm spring in a bamboo grove (study room), the arena, the library; a stream, two paddies and an orchard as scenery. The camera and light match actors.py (same CAM_TILT, rig()).
import os, json
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "lang_lib.py"), encoding="utf-8").read())
random.seed(5)
WHAT = ARGS[1] if len(ARGS) > 1 else "all"; PREVIEW = len(ARGS) > 2 and ARGS[2] == "preview"
SCREENS = (1.2, 1.2)
W_PX, H_PX = int(3200 * SCREENS[0]), int(2000 * SCREENS[1])           # 3840 x 2400, 94.1 px per world unit
ORTHO = 34.0 * SCREENS[0]
TGT = (0.0, 14.0, 2.5)
setup_render(W_PX, H_PX, samples=24 if PREVIEW else 48)
if PREVIEW: sc.render.resolution_percentage = 25
sc.render.image_settings.file_format = "PNG"; sc.render.image_settings.color_mode = "RGBA"

OCC = []       # (name, objects, base point): things a character can stand behind
BLOCK = []     # polygons (world xy) nobody can walk through
ALLOW = []     # polygons that stay walkable even inside a block (bridges)
SIGN, DOOR, STEAMS = {}, {}, []
def occ(name, objs, base): OCC.append((name, [o for o in objs if o is not None], Vector(base)))
def circle(c, r, n=12): return [(c[0] + math.cos(k / n * 2 * math.pi) * r, c[1] + math.sin(k / n * 2 * math.pi) * r) for k in range(n)]
def rect(c, w, h, rz=0.0):
    cs, sn = math.cos(rz), math.sin(rz)
    return [(c[0] + x * cs - y * sn, c[1] + x * sn + y * cs) for x, y in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))]
def group(objs, loc, rz=0.0, s=1.0):
    e = link(bpy.data.objects.new("grp", None)); e.location = loc; e.rotation_euler = (0, 0, rz); e.scale = (s, s, s)
    for o in objs:
        if o.parent is None: o.parent = e
    return e
def lighter_crowns():  # the painting adds the leaves: keep the 3D foliage light to render
    pass

# ---------------------------------------------------------------- layout (world units; an adult chicken is ~3 tall)
X0, X1, Y0, Y1 = -22.0, 22.0, -15.0, 37.0      # the ground
PC = Vector((0, 6.0, 0)); PR = (8.4, 4.4)     # the yard (sân đình)
G_C = Vector((0, -9.0, 0))                     # village gate; a fence runs along the whole front
B_C = Vector((6.8, -1.6, 0))                   # notice board
BANYAN = Vector((-2.6, 15.6, 0)); WELL = Vector((6.6, 11.8, 0))
S_C = Vector((-13.6, 2.6, 0)); S_R = (3.4, 2.3)  # warm spring in a bamboo grove
A_C = Vector((-11.5, 21.0, 0)); A_R = (5.2, 3.4)  # arena
L_C = Vector((9.8, 22.6, 0)); L_S = 0.82         # library
STREAM = [(15.5, 42.0), (17.0, 33.0), (15.6, 25.0), (17.8, 16.0), (16.4, 7.0), (18.0, -2.0), (17.2, -16.0)]
STREAM_W = 2.6
PATHS = {
    "gate": [(0, 1.8), (0.5, -3.0), (0.0, -9.0), (0.0, -15.0)],
    "spring": [(-8.0, 6.0), (-9.0, 4.4), (-9.6, 3.2)],
    "arena": [(-5.0, 9.6), (-7.6, 13.6), (-9.6, 16.4), (-10.4, 17.4)],
    "library": [(5.2, 9.8), (7.4, 14.2), (9.4, 18.0), (9.8, 19.0)],
    "back": [(-6.2, 22.8), (-1.0, 21.4), (3.6, 22.6), (6.4, 23.8)],
}
PATH_W = 2.3
FIELDS = [(-16.4, -4.6), (11.6, -4.8)]      # rice paddies (centres), 5.6 x 5.4 each
FIELDS_NE = []

def catmull(pts, n=10):
    P = [Vector((x, y, 0)) for x, y in pts]; P = [P[0] * 2 - P[1]] + P + [P[-1] * 2 - P[-2]]; out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for k in range(n):
            t = k / n
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(P[-2]); return out
DENSE = {k: catmull(v) for k, v in PATHS.items()}
SDENSE = catmull(STREAM, 14)
def seg_dist(q, pts):
    best = 1e9
    for a, b in zip(pts, pts[1:]):
        ab = b - a; t = max(0.0, min(1.0, (q - a).dot(ab) / max(ab.length_squared, 1e-9))); best = min(best, (a + ab * t - q).length)
    return best
# distance to the paths and to the stream, computed once on a 0.25-unit raster (numpy): the ground grids ask it tens of
# thousands of times
import numpy as np
RES = 0.25; RX0, RY0 = X0 - 8, Y0 - 6; NX, NY = int((X1 - X0 + 16) / RES), int((Y1 - Y0 + 12) / RES)
_gx, _gy = np.meshgrid(RX0 + (np.arange(NX) + 0.5) * RES, RY0 + (np.arange(NY) + 0.5) * RES)
def _dist_field(polylines):
    d = np.full(_gx.shape, 1e9, np.float32)
    for pts in polylines:
        P = np.array([(p.x, p.y) for p in pts], np.float32); A, B = P[:-1], P[1:]
        for (ax, ay), (bx, by) in zip(A, B):
            dx, dy = bx - ax, by - ay; L2 = max(dx * dx + dy * dy, 1e-9)
            t = np.clip(((_gx - ax) * dx + (_gy - ay) * dy) / L2, 0, 1)
            d = np.minimum(d, np.hypot(_gx - (ax + t * dx), _gy - (ay + t * dy)))
    return d
DPATH = _dist_field(DENSE.values()); DSTREAM = _dist_field([SDENSE])
def _look(field, x, y):
    i = min(max(int((y - RY0) / RES), 0), NY - 1); j = min(max(int((x - RX0) / RES), 0), NX - 1); return field[i, j]
def in_paths(x, y, pad=0.0): return _look(DPATH, x, y) < PATH_W / 2 + pad
def in_stream(x, y, pad=0.0): return _look(DSTREAM, x, y) < STREAM_W / 2 + pad
def in_ell(x, y, c, r, pad=0.0): return ((x - c.x) / (r[0] + pad)) ** 2 + ((y - c.y) / (r[1] + pad)) ** 2 < 1
def in_plaza(x, y, pad=0.0): return in_ell(x, y, PC, PR, pad)
def in_fields(x, y, pad=0.0): return any(abs(x - fx) < 2.8 + pad and abs(y - fy) < 2.7 + pad for fx, fy in FIELDS + FIELDS_NE)
def open_ground(x, y, pad=0.0):
    return not (in_plaza(x, y, pad) or in_paths(x, y, pad) or in_ell(x, y, A_C, A_R, pad) or in_ell(x, y, S_C, S_R, pad + 0.6)
                or in_stream(x, y, pad + 0.4) or in_fields(x, y, pad))
def plaza_edge(a):
    w = 1 + 0.03 * math.sin(a * 5 + 1.3) + 0.02 * math.sin(a * 11)
    return Vector((PC.x + math.cos(a) * PR[0] * w, PC.y + math.sin(a) * PR[1] * w, 0))

# ---------------------------------------------------------------- ground: lawn, yard, paths, stream, fields
M_dirt = paint("dirt", "#f2d6a2", "#b9876a", "#dcb282", var=0.12, vscale=0.3, up=True, speck=0.07, ao=0.45, rim=0, ellipse=(PC.x, PC.y, PR[0], PR[1], 0.16))
GW, GH = X1 - X0 + 8, Y1 - Y0 + 4; GC = ((X0 + X1) / 2, (Y0 + Y1) / 2 + 1)
lawn = grid("lawn", (GW, GH), (int(GW), int(GH)), lambda x, y: open_ground(x, y, -0.3), M_grass, center=GC)
plane("yard", [(p.x, p.y) for p in (plaza_edge(a / 120 * 2 * math.pi) for a in range(120))], M_dirt, z=0.012)
def strip(name, pts, w, mat, z=0.009, wob=0.08):
    bm = bmesh.new(); Lv, Rv = [], []
    for i, p in enumerate(pts):
        a = pts[max(i - 1, 0)]; b = pts[min(i + 1, len(pts) - 1)]; d = (b - a).normalized(); side = Vector((-d.y, d.x, 0))
        ww = w / 2 * (1 + wob * math.sin(i * 1.7))
        Lv.append(bm.verts.new(p + side * ww + Vector((0, 0, z)))); Rv.append(bm.verts.new(p - side * ww + Vector((0, 0, z))))
    for i in range(len(pts) - 1): bm.faces.new((Lv[i], Rv[i], Rv[i + 1], Lv[i + 1]))
    o = mesh_obj(name, bm); o.data.materials.append(mat); return o
for k, pts in DENSE.items(): strip("path_" + k, pts, PATH_W, M_path)
# the stream: a bed, water, stones and reeds on the banks
M_stream = paint("stream", "#8fd8e6", "#3a88b4", "#5cb8d6", "#e8fdff", var=0.14, vscale=0.35, up=True, ao=0.3, rim=0)
strip("streambed", SDENSE, STREAM_W + 1.0, M_path, z=0.004, wob=0.12)
strip("streamwater", SDENSE, STREAM_W, M_stream, z=0.03, wob=0.1)
for i in range(0, len(SDENSE) - 1, 2):
    a, b = SDENSE[i], SDENSE[i + 1]; d = (b - a).normalized(); side = Vector((-d.y, d.x, 0))
    for sd in (-1, 1):
        if random.random() < 0.55:
            blob("bankstone", a + side * sd * (STREAM_W / 2 + 0.35) + Vector((0, 0, 0.06)), random.uniform(0.3, 0.55), M_rock, squash=(1.2, 1, 0.6), rough=0.3, subdiv=2, ol=0.01)
reeds = grid("reeds", (GW, GH), (int(GW * 2), int(GH * 2)), lambda x, y: in_stream(x, y, 1.1) and not in_stream(x, y, 0.3) and not in_paths(x, y, 0.4), center=GC)
scatter("reeds", reeds, T1, 9.0, (0.9, 1.5), seed=31)
BLOCK.append([(p.x + (-(b - a).normalized().y) * STREAM_W / 2, p.y + ((b - a).normalized().x) * STREAM_W / 2) for p, a, b in zip(SDENSE, SDENSE, SDENSE[1:] + [SDENSE[-1] * 2 - SDENSE[-2]])]
             + [(p.x - (-(b - a).normalized().y) * STREAM_W / 2, p.y - ((b - a).normalized().x) * STREAM_W / 2) for p, a, b in reversed(list(zip(SDENSE, SDENSE, SDENSE[1:] + [SDENSE[-1] * 2 - SDENSE[-2]])))])
# rice fields: water with rows of young rice, low earth dikes around
M_paddy = paint("paddy", "#a8d8c8", "#4a8a90", "#7fbcb0", "#e8faf2", var=0.12, vscale=0.4, up=True, ao=0.3, rim=0)
M_rice = paint("rice", "#b8e070", "#4e8a48", "#86c058", "#e8f8a8", up=True, grad=(0.55, 1.15), rand=0.12, ao=0.5, rim=0)
RICE = tuft("rice", 6, 0.6, 0.05, M_rice)
for fx, fy in FIELDS + FIELDS_NE:
    plane("paddy", rect((fx, fy), 5.6, 5.4), M_paddy, z=0.02)
    for sd in (-1, 1):
        bbox("dike", (fx, fy + sd * 2.85, 0.12), (5.9, 0.42, 0.24), M_path, bev=0.1, ol=0); bbox("dike", (fx + sd * 2.95, fy, 0.12), (0.42, 5.9, 0.24), M_path, bev=0.1, ol=0)
    rows = grid("ricerows", (5.2, 5.0), (26, 10), lambda x, y: True, center=(fx, fy)); rows.location.z = 0.02
    scatter("rice", rows, RICE, 7.0, (0.8, 1.1), seed=int(fx * 3 + fy), tilt=0.08)
    BLOCK.append(rect((fx, fy), 5.4, 5.2))
# grass, flowers, pebbles
scatter("grass_a", lawn, T1, 1.6, (0.6, 1.15), seed=3, keep=True, clump=(0.12, 0.0, 2.4))
def rim_zone(x, y):
    near = in_plaza(x, y, 1.1) or in_paths(x, y, 0.55) or in_ell(x, y, A_C, A_R, 0.9) or in_ell(x, y, S_C, S_R, 1.6)
    return near and open_ground(x, y, -0.35)
scatter("grass_rim", grid("rim", (GW, GH), (int(GW * 3), int(GH * 3)), rim_zone, center=GC), T1, 5.0, (0.55, 1.0), seed=5)
for i, pm in enumerate(M_petal):
    scatter(f"flowers{i}", grid(f"fl_s{i}", (GW, GH), (int(GW), int(GH)), lambda x, y: open_ground(x, y, 0.9), center=GC), flower(pm), 0.22,
            (0.8, 1.3), seed=20 + i, tilt=0.2, clump=(0.08 + i * 0.03, 0.0, 5.0, 0.56, 0.68))
# a meadow of wild flowers in the south-west, left open (room for later)
for i, pm in enumerate(M_petal):
    scatter(f"meadow{i}", grid(f"mw{i}", (8, 4), (16, 8), lambda x, y: open_ground(x, y, 0.5), center=(-7, -4)), flower(pm), 1.0, (0.9, 1.4), seed=60 + i, tilt=0.25, clump=(0.4, 0.0, 2.5))
yin = grid("yard_in", (22, 12), (66, 36), lambda x, y: in_plaza(x, y, -0.8), center=(PC.x, PC.y)); yin.location.z = 0.02
scatter("pebbles", yin, PEBBLE, 0.4, (0.5, 1.4), seed=7, tilt=0.3)
gaps = []
for k, pts in PATHS.items():
    q = Vector((pts[0][0] - PC.x, (pts[0][1] - PC.y) * PR[0] / PR[1], 0))
    if q.length < 14: gaps.append((math.atan2(q.y, q.x) % (2 * math.pi), 0.2))
rock_ring(plaza_edge, 64, gap=gaps, seed=2)

# ---------------------------------------------------------------- the yard: the banyan tree (cây đa), the well (giếng)
def banyan(p, s=1.25):
    o = []
    for k, (dx, dy, r) in enumerate(((0, 0, 0.75), (-0.6, 0.35, 0.5), (0.55, 0.4, 0.5), (0.1, -0.45, 0.45))):  # a knot of trunks
        o.append(tube("btrunk", p + Vector((dx * s, dy * s, -0.1)), r * s, r * 0.6 * s, 5.2 * s, M_trunk, seg=14, rough=0.12 * s, ol=0.014))
    for k in range(9):  # aerial roots hanging from the branches
        a = k / 9 * 2 * math.pi; rr = random.uniform(1.6, 2.8) * s
        q = p + Vector((math.cos(a) * rr, math.sin(a) * rr * 0.8, 0))
        o.append(tube("broot", q, 0.09 * s, 0.06 * s, random.uniform(3.2, 4.6) * s, M_trunk, seg=6, ol=0.008))
    for k, (dx, dy, dz, r) in enumerate(((0, 0.3, 6.6, 3.4), (-2.9, 0.4, 5.7, 2.4), (2.9, 0.2, 5.8, 2.5), (-1.4, -1.2, 6.2, 2.2),
                                        (1.6, -1.0, 6.4, 2.2), (0.4, 1.4, 7.6, 2.4), (-3.8, -0.2, 4.9, 1.7), (3.9, -0.3, 5.0, 1.7))):
        o += crown(p + Vector((dx * s, dy * s, dz * s)), r * s, M_leaf2, 300 + k, lumps=5)
    tg = scatter("bgrass", grid("bg_", (7 * s, 6 * s), (20, 18), lambda x, y: x * x / 9 + y * y / 6 < s * s * 1.6), T1, 8.0, (0.6, 1.1), seed=41); tg.location = p; o.append(tg)
    for k in range(8):  # a ring of stones and a little altar under it, as in a village yard
        a = k / 8 * 2 * math.pi
        o.append(blob("bstone", p + Vector((math.cos(a) * 1.6 * s, math.sin(a) * 1.25 * s, 0.1)), 0.35, M_rock, squash=(1.2, 1, 0.6), rough=0.25, subdiv=2, ol=0.01))
    return o
occ("banyan", banyan(BANYAN, 0.78), BANYAN); BLOCK.append(circle(BANYAN, 1.3))
def well(p):
    o = [tube("wring", p, 1.05, 1.1, 0.95, M_rock, seg=28, ol=0.014), tube("wrim", p + Vector((0, 0, 0.92)), 1.15, 1.15, 0.14, M_rock, seg=28, ol=0.01)]
    plane("wwater", circle(p, 0.85, 24), M_stream, z=0.75)
    for sx in (-1, 1): o.append(bbox("wpost", p + Vector((sx * 1.0, 0, 1.4)), (0.18, 0.18, 2.8), M_woodd, ol=0.01))
    o.append(bbox("wbeam", p + Vector((0, 0, 2.65)), (2.4, 0.16, 0.16), M_woodd, ol=0.01))
    for sy in (-1, 1): o.append(bbox("wroof", p + Vector((0, sy * 0.5, 3.0)), (2.8, 1.2, 0.1), M_shingle, rot=(sy * 0.6, 0, 0), bev=0.03, ol=0.01))
    o.append(tube("wbucket", p + Vector((0.35, -0.2, 1.6)), 0.22, 0.26, 0.32, M_wood, seg=14, ol=0.008))
    o.append(bbox("wrope", p + Vector((0.35, -0.2, 2.15)), (0.03, 0.03, 0.95), M_burlap, ol=0))
    return o
occ("well", well(WELL), WELL); BLOCK.append(circle(WELL, 1.4))
fd = PC + Vector((-3.2, 2.6, 0))  # a feeder with grain, the chickens' corner
tube("feeder", fd, 0.75, 0.85, 0.32, M_wood, seg=28, ol=0.012)
blob("grainpile", fd + Vector((0, 0, 0.3)), 0.68, M_grain, squash=(1, 1, 0.22), rough=0.1, subdiv=3)
BLOCK.append(circle(fd, 0.9))

# ---------------------------------------------------------------- notice board (bảng tin)
def board(C):
    o = [tube("bpost", C + Vector((sx * 1.5, 0, 0)), 0.13, 0.12, 2.9, M_woodd, ol=0.012) for sx in (-1, 1)]
    o.append(bbox("bboard", C + Vector((0, 0, 1.75)), (3.0, 0.16, 1.7), M_wood, bev=0.05, ol=0.012))
    for sx in (-1, 1): o.append(bbox("broof", C + Vector((sx * 0.85, 0, 2.95)), (1.9, 0.7, 0.1), M_shingle, rot=(0, sx * 0.35, 0), bev=0.03, ol=0.01))
    for i, (x, z, m, rz) in enumerate(((-0.85, 2.05, M_cloth[1], 0.06), (0.15, 2.1, M_cloth[2], -0.05), (0.95, 1.95, M_petal[1], 0.08), (-0.45, 1.3, M_cloth[1], -0.04), (0.6, 1.35, M_cloth[1], 0.03))):
        o.append(bbox("note", C + Vector((x, -0.1, z)), (0.62, 0.03, 0.5), m, rot=(0, rz, 0), bev=0.01, ol=0.004))
        o.append(blob("pin", C + Vector((x, -0.13, z + 0.2)), 0.05, M_cloth[0], rough=0, subdiv=1))
    return o
occ("board", board(B_C), B_C); BLOCK.append(rect((B_C.x, B_C.y), 3.4, 0.6)); SIGN["board"] = B_C + Vector((0, 0, 4.0)); DOOR["board"] = B_C + Vector((0.0, -1.6, 0))

# ---------------------------------------------------------------- the gate and the fence along the front
def gate(C):
    o = []
    for sx in (-1, 1):
        o.append(tube("gpost", C + Vector((sx * 2.5, 0, 0)), 0.3, 0.26, 4.4, M_woodd, seg=16, ol=0.014))
        o.append(tube("gbase", C + Vector((sx * 2.5, 0, 0)), 0.45, 0.42, 0.4, M_rock, seg=16, ol=0.012))
    o.append(bbox("gbeam", C + Vector((0, 0, 4.2)), (6.4, 0.42, 0.36), M_woodd, ol=0.014))
    o.append(bbox("gbeam2", C + Vector((0, 0, 3.55)), (5.4, 0.3, 0.22), M_woodd, ol=0.012))
    for sy in (-1, 1):
        o.append(bbox("gslab", C + Vector((0, sy * 0.36, 4.66)), (7.0, 0.95, 0.1), M_ridge, rot=(sy * 0.75, 0, 0), bev=0, ol=0))
        for i in range(14):
            o.append(bbox("gsh", C + Vector((-3.25 + i * 0.5, sy * 0.38, 4.74)), (0.52, 1.0, 0.09), M_shingle, rot=(sy * 0.75 + random.uniform(-0.03, 0.03), 0, random.uniform(-0.03, 0.03)), bev=0.03, ol=0.006))
    o.append(tube("gridge", C + Vector((-3.6, 0, 5.1)), 0.17, 0.17, 7.2, M_ridge, seg=12, rot=(0, math.radians(90), 0), ol=0.01))
    o.append(bbox("gsign", C + Vector((0, -0.25, 2.95)), (2.8, 0.12, 0.85), M_wood, bev=0.05, ol=0.012))
    for sx in (-1, 1): o.append(bbox("gchain", C + Vector((sx * 1.0, -0.25, 3.45)), (0.05, 0.05, 0.3), M_woodd, ol=0))
    for sx in (-1, 1):
        lp = C + Vector((sx * 3.1, -0.1, 3.0))
        o.append(blob("glant", lp, 0.34, M_lant, squash=(1, 1, 1.25), rough=0, subdiv=3, ol=0.012))
        for dz in (0.42, -0.42): o.append(tube("glcap", lp + Vector((0, 0, dz - 0.05)), 0.2, 0.2, 0.1, M_gold, seg=16, ol=0.008))
    return o
occ("gate", gate(G_C), G_C); SIGN["gate"] = G_C + Vector((0, -0.32, 2.95))
for sx in (-1, 1): BLOCK.append(circle((G_C.x + sx * 2.5, G_C.y), 0.6))
occ("fence_l", fence(X0 + 1, -3.4, G_C.y - 0.3), (X0 / 2, G_C.y - 0.3, 0)); occ("fence_r", fence(3.4, X1 - 1, G_C.y - 0.3), (X1 / 2, G_C.y - 0.3, 0))
BLOCK.append(rect(((X0 + 1 - 3.4) / 2, G_C.y - 0.3), -3.4 - X0 - 1, 0.6)); BLOCK.append(rect(((3.4 + X1 - 1) / 2, G_C.y - 0.3), X1 - 1 - 3.4, 0.6))

# ---------------------------------------------------------------- warm spring (Phòng tự học) in a bamboo grove, with a bath hut
def spring_edge(a, k=1.0):
    w = 1 + 0.06 * math.sin(a * 3 + 0.4) + 0.03 * math.sin(a * 7)
    return Vector((S_C.x + math.cos(a) * S_R[0] * w * k, S_C.y + math.sin(a) * S_R[1] * w * k, 0))
plane("spring_bed", [(p.x, p.y) for p in (spring_edge(a / 80 * 2 * math.pi, 1.08) for a in range(80))], M_rock, z=0.006)
plane("water", [(p.x, p.y) for p in (spring_edge(a / 80 * 2 * math.pi) for a in range(80))],
      paint("spring", "#8fe6ee", "#3a9cbe", "#62c6dc", "#f0ffff", var=0.12, vscale=0.6, up=True, ao=0.3, rim=0, ellipse=(S_C.x, S_C.y, S_R[0], S_R[1], -0.12)), z=0.06)
srocks = []
for k in range(34):
    a = k / 34 * 2 * math.pi
    if abs((a - 0.1 + math.pi) % (2 * math.pi) - math.pi) < 0.3: continue   # the way in, from the east
    p = spring_edge(a, 1.05); r = random.uniform(0.45, 0.85) * (1.3 if p.y > S_C.y + 0.8 else 1.0)
    srocks.append(blob("srock", p + Vector((0, 0, 0.1)), r, M_rock, squash=(1.2, 1.0, 0.7), rough=0.3, ol=0.012))
occ("spring_rocks", [o for o in srocks if o.location.y < S_C.y], (S_C.x, S_C.y - S_R[1], 0))
BLOCK.append([(p.x, p.y) for p in (spring_edge(a / 24 * 2 * math.pi, 1.02) for a in range(24))])
M_bam = paint("bamboo", "#9fd66a", "#4a8a4a", "#76b85a", "#d8f5a0", grain=0.05)
BAM = proto(tube("bamp", (0, 0, 0), 0.15, 0.14, 4.2, M_bam, seg=8))
for cx, cy, rx, ry in ((-15.2, 8.6, 4.6, 1.5), (-20.0, 3.4, 1.4, 3.6)):  # bamboo groves round the spring
    gr = grid("bamboo_g", (rx * 2, ry * 2), (int(rx * 4), int(ry * 4)), lambda x, y, rx=rx, ry=ry: (x / rx) ** 2 + (y / ry) ** 2 < 1)
    gr.location = (cx, cy, 0); scatter("bamboo", gr, BAM, 1.8, (0.75, 1.25), seed=int(cx * cy) % 97, tilt=0.06)
    bl = grid("bam_leaf", (rx * 2, ry * 2), (int(rx * 2), int(ry * 2)), lambda x, y, rx=rx, ry=ry: (x / rx) ** 2 + (y / ry) ** 2 < 0.8)
    for o_ in range(1):
        for k in range(int(rx * ry * 0.9)):
            a = random.uniform(0, 2 * math.pi); rr = random.uniform(0, 0.85)
            crown(Vector((cx + math.cos(a) * rx * rr, cy + math.sin(a) * ry * rr, random.uniform(3.2, 4.6))), random.uniform(0.7, 1.1), M_leaf, 500 + k, lumps=2)
    bpy.data.objects.remove(bl)
    occ(f"bamboo_{int(cx)}_{int(cy)}", [gr], (cx, cy - ry, 0)); BLOCK.append([(cx + math.cos(a / 16 * 2 * math.pi) * rx * 0.9, cy + math.sin(a / 16 * 2 * math.pi) * ry * 0.9) for a in range(16)])
def hut(C):  # a little bath house with a shingled roof
    o = []; W, D, H = 4.2, 3.4, 2.6
    o.append(bbox("hbase", C + Vector((0, 0, 0.15)), (W + 0.4, D + 0.4, 0.3), M_rock, bev=0.06, ol=0.012))
    o.append(bbox("hbody", C + Vector((0, 0, 0.3 + H / 2)), (W, D, H), M_wall, bev=0.02, ol=0.012))
    o.append(bbox("hdoor", C + Vector((0.6, -D / 2 - 0.03, 0.3 + 0.95)), (1.1, 0.08, 1.9), M_cloth[3], bev=0.02, ol=0.008))  # a cloth curtain
    o.append(bbox("hwin", C + Vector((-1.1, -D / 2 - 0.03, 1.8)), (0.9, 0.08, 0.7), M_glass, ol=0.006))
    o += gable_roof(C, W, D, 0.3 + H + 0.1, W / 2 + 0.5, 1.8, D + 0.8, M_shingle, M_ridge, rows=6, cols=9, window=False)
    return o
HUT = S_C + Vector((-3.0, 3.8, 0)); occ("hut", hut(HUT), HUT); BLOCK.append(rect((HUT.x, HUT.y), 4.8, 4.0))
sl = S_C + Vector((4.2, -2.4, 0))  # a stone lantern by the way in
lo = [tube("slant", sl + Vector((0, 0, z - 0.15)), r, r, 0.3, M_rock, seg=12, ol=0.01) for z, r in ((0.2, 0.32), (0.6, 0.14), (0.95, 0.3), (1.25, 0.24))]
lo.append(blob("slcap", sl + Vector((0, 0, 1.55)), 0.42, M_rock, squash=(1, 1, 0.45), rough=0.05, subdiv=2, ol=0.01)); occ("slantern", lo, sl); BLOCK.append(circle(sl, 0.5))
SIGN["spring"] = S_C + Vector((0, 0.6, 2.2)); DOOR["spring"] = Vector(PATHS["spring"][-1] + (0,)); STEAMS += [S_C + Vector((dx, dy, 0.1)) for dx, dy in ((-1.2, 0.3), (1.0, -0.4), (0.0, 0.9))]

# ---------------------------------------------------------------- arena (Đấu trường)
def arena_edge(a, k=1.0):
    w = 1 + 0.025 * math.sin(a * 5)
    return Vector((A_C.x + math.cos(a) * A_R[0] * w * k, A_C.y + math.sin(a) * A_R[1] * w * k, 0))
plane("arena_floor", [(p.x, p.y) for p in (arena_edge(a / 80 * 2 * math.pi) for a in range(80))],
      paint("sand_a", "#f4dca6", "#c09070", "#e0c08a", var=0.1, vscale=0.35, up=True, speck=0.06, ao=0.45, rim=0, ellipse=(A_C.x, A_C.y, A_R[0], A_R[1], 0.14)), z=0.011)
entry = math.atan2(PATHS["arena"][-1][1] - A_C.y, (PATHS["arena"][-1][0] - A_C.x) * A_R[1] / A_R[0])
front, back = [], []
def off_entry(a): return abs((a - entry + math.pi) % (2 * math.pi) - math.pi) >= 0.3
for k in range(52):
    a = k / 52 * 2 * math.pi
    if not off_entry(a): continue
    p = arena_edge(a, 1.06); h = 1.35 + (0.22 if k % 2 else 0) + random.uniform(-0.05, 0.05)
    post = [tube("pal", p, 0.2, 0.2, h, M_woodd, seg=10, ol=0.012), tube("paltip", p + Vector((0, 0, h)), 0.2, 0.0, 0.34, M_woodd, seg=10, ol=0.01)]
    (front if p.y < A_C.y else back).extend(post)
    BLOCK.append(circle((p.x, p.y), 0.42, 6))
occ("arena_front", front, (A_C.x, A_C.y - A_R[1], 0)); occ("arena_back", back, (A_C.x, A_C.y + A_R[1] * 0.2, 0))
for i, a in enumerate((0.55, 1.2, 1.95, 2.6)):
    p = arena_edge(a, 1.12); tube("fpole", p, 0.09, 0.07, 4.6, M_woodd, ol=0.01); blob("fknob", p + Vector((0, 0, 4.65)), 0.13, M_gold, rough=0, subdiv=2, ol=0.008)
    bm = bmesh.new(); v = [bm.verts.new(q) for q in ((0, 0, 0), (1.35, 0, -0.32), (0, 0, -0.85))]; bm.faces.new(v)
    f = mesh_obj("flag", bm); f.location = p + Vector((0.06, 0, 4.45)); f.data.materials.append(M_cloth[i % 4]); s_ = f.modifiers.new("th", "SOLIDIFY"); s_.thickness = 0.05
dm = A_C + Vector((0.6, 0.4, 0)); dummy = []
dummy += [tube("dpost", dm, 0.12, 0.12, 2.3, M_woodd, ol=0.012), bbox("darm", dm + Vector((0, 0, 1.75)), (1.9, 0.16, 0.16), M_woodd, ol=0.01),
          blob("dbody", dm + Vector((0, 0, 1.35)), 0.55, M_bale, squash=(1, 0.8, 1.2), rough=0.1, subdiv=3, ol=0.012),
          blob("dhead", dm + Vector((0, 0, 2.3)), 0.36, M_burlap, rough=0.08, subdiv=3, ol=0.012)]
for i, (r, m) in enumerate(((0.42, M_cloth[1]), (0.3, M_cloth[0]), (0.18, M_cloth[1]), (0.08, M_cloth[0]))):
    dummy.append(tube("target", dm + Vector((0, -0.5 - i * 0.015, 1.35)), r, r, 0.04, m, seg=32, rot=(math.radians(90), 0, 0)))
occ("dummy", dummy, dm); BLOCK.append(circle((dm.x, dm.y), 0.8))
for row in range(3):
    y = A_C.y + A_R[1] + 1.4 + row * 0.9
    for dx in (-3.0, 0, 3.0):
        bbox("bench", Vector((A_C.x + dx, y, 0.35 + row * 0.45)), (2.6, 0.7, 0.18), M_wood, ol=0.01)
        for sx in (-1.0, 1.0): bbox("bleg", Vector((A_C.x + dx + sx, y, (0.35 + row * 0.45) / 2)), (0.16, 0.5, 0.35 + row * 0.45), M_woodd, ol=0.008)
BLOCK.append(rect((A_C.x, A_C.y + A_R[1] + 2.3), 9.4, 3.0))
SIGN["arena"] = A_C + Vector((0, 1.5, 3.4)); DOOR["arena"] = Vector(PATHS["arena"][-1] + (0,))

# ---------------------------------------------------------------- library (Thư viện), north-east
def library(C):
    o = []; W, D, H, z0 = 6.6, 5.0, 5.4, 0.5
    o.append(bbox("lbase", C + Vector((0, 0, z0 / 2)), (W + 0.4, D + 0.4, z0), M_rock, bev=0.08, ol=0.016))
    o.append(bbox("lwall", C + Vector((0, 0, z0 + H / 2)), (W, D, H), M_plaster, bev=0.03, ol=0.014))
    fy = C.y - D / 2 - 0.06
    for x in (-W / 2, -W / 6, W / 6, W / 2): o.append(bbox("timber", Vector((C.x + x, fy, z0 + H / 2)), (0.3, 0.16, H), M_woodd, ol=0.01))
    for z in (z0 + 0.1, z0 + H / 2, z0 + H - 0.1): o.append(bbox("tbeam", Vector((C.x, fy - 0.02, z)), (W + 0.2, 0.18, 0.26), M_woodd, ol=0.01))
    def window(x, z, w=0.95, h=1.15):
        o.append(bbox("lglass", Vector((C.x + x, fy - 0.02, z)), (w, 0.08, h), M_glass, bev=0.02, ol=0))
        for dx in (-w / 2, w / 2): o.append(bbox("wf", Vector((C.x + x + dx, fy - 0.1, z)), (0.12, 0.12, h + 0.12), M_woodd, ol=0.008))
        for dz in (-h / 2, h / 2): o.append(bbox("wf", Vector((C.x + x, fy - 0.1, z + dz)), (w + 0.12, 0.12, 0.12), M_woodd, ol=0.008))
        o.append(bbox("sill", Vector((C.x + x, fy - 0.2, z - h / 2 - 0.1)), (w + 0.35, 0.3, 0.12), M_wood, ol=0.008))
        for sx in (-1, 1): o.append(bbox("shutter", Vector((C.x + x + sx * (w / 2 + 0.32), fy - 0.12, z)), (0.48, 0.08, h + 0.05), M_cloth[3], bev=0.03, ol=0.01))
        o.append(blob("flowersbox", Vector((C.x + x, fy - 0.32, z - h / 2 + 0.02)), 0.45, M_leaf, squash=(1.2, 0.4, 0.35), rough=0.3, subdiv=3))
    for x in (-W / 3 - 0.05, W / 3 + 0.05): window(x, z0 + 1.45)
    for x in (-W / 3 - 0.05, 0, W / 3 + 0.05): window(x, z0 + H / 2 + 1.35, 0.85, 1.0)
    dw, dh = 1.3, 2.1
    o.append(bbox("ldoor", Vector((C.x, fy - 0.03, z0 + dh / 2)), (dw, 0.1, dh), M_woodd, bev=0.03, ol=0.01))
    for sx in (-1, 1): o.append(bbox("dslab", Vector((C.x + sx * 0.55, fy - 0.45, z0 + dh + 0.45)), (1.2, 0.9, 0.12), M_shingle_b, rot=(0, sx * 0.45, 0), ol=0.01))
    for i in range(3): o.append(bbox("step", Vector((C.x, fy - 0.45 - i * 0.4, z0 * (1 - i / 3) - 0.05)), (dw + 0.8, 0.42, 0.22), M_rock, bev=0.05, ol=0.01))
    o += gable_roof(C, W, D, z0 + H + 0.1, W / 2 + 0.6, 2.8, D + 1.0, M_shingle_b, M_ridge_b, rows=8, cols=12, wall=M_plaster)
    o.append(bbox("chimney", C + Vector((1.7, 0.8, z0 + H + 2.2)), (0.6, 0.6, 1.8), paint("brick", "#d88866", "#7a3a3e", "#b0604e", "#f4ab88", rand=0.08), bev=0.04, ol=0.012))
    for i in range(4): o.append(bbox("book", Vector((C.x - 2.4 + 0.02 * i, fy - 1.2, 0.12 + 0.2 * i)), (0.62 - 0.06 * i, 0.44, 0.17), M_cloth[i % 4], bev=0.03, ol=0.008))
    for sx in (-1, 1):
        pp = Vector((C.x + sx * (dw / 2 + 0.7), fy - 0.9, 0))
        o.append(tube("pot", pp, 0.34, 0.42, 0.6, paint("clay", "#e08a5a", "#8a4040", "#c06a4a", "#ffb38a"), seg=18, ol=0.01))
        o += crown(pp + Vector((0, 0, 1.1)), 0.55, M_leaf, 40 + sx, lumps=4)
    return o, Vector((C.x, fy - 1.9, 0))
lib_objs, ldoor = library(Vector((0, 0, 0))); group(lib_objs, L_C, s=L_S); occ("library", lib_objs, L_C + Vector((0, -2.6 * L_S, 0)))
BLOCK.append(rect((L_C.x, L_C.y), 7.4 * L_S, 5.6 * L_S)); DOOR["library"] = L_C + ldoor * L_S
SIGN["library"] = L_C + Vector((0, 0, 9.2 * L_S + 0.4))

# ---------------------------------------------------------------- bridges where paths cross the stream
def cross_points():
    out = []
    for k, pts in DENSE.items():
        for p in pts:
            if seg_dist(p, SDENSE) < 0.35: out.append((k, p))
    seen, res = set(), []
    for k, p in out:
        if k in seen: continue
        seen.add(k); res.append((k, p))
    return res
def bridge(p, ang):
    o = []; L, Wb = STREAM_W + 2.6, 2.4
    for i in range(12):
        t = (i + 0.5) / 12 - 0.5; z = 0.35 + 0.55 * math.cos(t * math.pi)
        q = p + Vector((math.cos(ang) * t * L, math.sin(ang) * t * L, z))
        o.append(bbox("bplank", q, (L / 12 - 0.03, Wb, 0.14), M_wood, rot=(0, -math.atan(0.55 * math.pi / L * math.sin(t * math.pi) * 1.0), ang), bev=0.02, ol=0.008))
    for sd in (-1, 1):
        for i in range(5):
            t = i / 4 - 0.5; z = 0.35 + 0.55 * math.cos(t * math.pi)
            q = p + Vector((math.cos(ang) * t * L - math.sin(ang) * sd * Wb / 2, math.sin(ang) * t * L + math.cos(ang) * sd * Wb / 2, z))
            o.append(tube("bpost", q, 0.09, 0.08, 1.0, M_woodd, seg=8, ol=0.008))
        q0 = p + Vector((-math.sin(ang) * sd * Wb / 2, math.cos(ang) * sd * Wb / 2, 1.35))
        o.append(bbox("brail", q0, (L, 0.1, 0.1), M_woodd, rot=(0, 0, ang), ol=0.008))
    return o
for k, p in cross_points():
    pts = DENSE[k]; i = min(range(len(pts)), key=lambda j: (pts[j] - p).length); a = pts[max(i - 1, 0)]; b = pts[min(i + 1, len(pts) - 1)]
    ang = math.atan2(b.y - a.y, b.x - a.x); occ(f"bridge_{k}", bridge(p, ang), p + Vector((0, -1.3, 0)))
    ALLOW.append(rect((p.x, p.y), STREAM_W + 2.4, 2.0, ang))

# ---------------------------------------------------------------- trees, orchards, bushes, haystacks, lanterns
TREES = [((-19.0, 14.5), "leaf", 0.8), ((-19.6, 25.5), "leaf2", 0.7), ((3.0, 18.0), "pink", 0.6), ((14.8, 29.0), "leaf", 0.66),
         ((-13.6, 30.0), "pink", 0.6), ((19.6, 9.0), "leaf2", 0.8), ((13.4, 11.0), "pink", 0.7), ((-12.0, 9.4), "leaf", 0.66),
         ((19.8, -6.6), "leaf", 0.85), ((-20.2, -7.0), "leaf2", 0.85), ((-3.6, -5.4), "leaf2", 0.62), ((2.6, 31.0), "leaf2", 0.6)]
for i, ((x, y), kind, s) in enumerate(TREES):
    if not open_ground(x, y, 1.2): continue
    occ(f"tree{i}", tree(Vector((x, y, 0)), kind, s, seed=i + 1), (x, y, 0)); BLOCK.append(circle((x, y), 0.9 * s + 0.3, 8))
for r in range(2):  # a small orchard north of the yard (pink blossom)
    for c in range(4):
        x, y = -7.0 + c * 4.4 + (r % 2) * 1.8, 29.6 + r * 3.0
        if open_ground(x, y, 1.0): occ(f"orch{r}{c}", tree(Vector((x, y, 0)), "pink" if (r + c) % 2 else "leaf", 0.5, seed=90 + r * 4 + c), (x, y, 0)); BLOCK.append(circle((x, y), 0.7, 8))
BUSHES = [((-10.6, -1.2), 1), ((4.0, -4.6), 3), ((-4.2, -2.8), None), ((12.2, 3.4), 2), ((-17.0, 17.2), None), ((15.6, 18.6), 1),
          ((-1.8, 29.4), 2), ((8.6, 30.0), None), ((-20.6, 9.6), None)]
for i, ((x, y), fl_) in enumerate(BUSHES):
    if not open_ground(x, y, 0.8): continue
    occ(f"bush{i}", bush(Vector((x, y, 0)), s=1.0, seed=i, flowers=fl_), (x, y, 0)); BLOCK.append(circle((x, y), 1.1, 8))
for i, (x, y) in enumerate(((-12.2, -6.2), (14.8, -1.4))):  # haystacks by the fields
    hs = [blob("hay", Vector((x, y, 0.9)), 1.3, M_straw, squash=(1, 1, 1.05), rough=0.12, subdiv=3, ol=0.012), tube("haypole", Vector((x, y, 1.8)), 0.06, 0.05, 1.2, M_woodd, ol=0.006)]
    occ(f"hay{i}", hs, (x, y, 0)); BLOCK.append(circle((x, y), 1.3, 8))
for i, (x, y, sd) in enumerate(((8.8, 3.0, 1), (-8.8, 9.2, -1), (-8.6, 2.0, -1), (12.6, 16.8, 1))):
    occ(f"lantern{i}", lantern(Vector((x, y, 0)), side=sd), (x, y, 0)); BLOCK.append(circle((x, y), 0.35, 6))
# far: two rows of hills close the view at the back (the sky stays transparent: the page paints it)
for k in range(11):
    x = X0 - 6 + k * 5.6 + random.uniform(-1, 1)
    blob("hillfar", Vector((x, Y1 + 4.0 + random.uniform(-0.6, 0.6), -1.4)), random.uniform(5.5, 7.5), M_hill[1], squash=(1.3, 0.6, 0.55), rough=0.08, nscale=3, subdiv=4)
for k in range(10):
    x = X0 - 4 + k * 6.2 + random.uniform(-1, 1)
    blob("hillnear", Vector((x, Y1 + 1.0 + random.uniform(-0.6, 0.6), -1.7)), random.uniform(4.8, 6.4), M_hill[0], squash=(1.4, 0.6, 0.5), rough=0.08, nscale=3, subdiv=4)
for k in range(13):
    x = X0 + k * 3.6 + random.uniform(-0.8, 0.8)
    crown(Vector((x, Y1 + 0.2 + random.uniform(-0.6, 0.6), 1.4 + random.uniform(-0.3, 0.6))), random.uniform(0.7, 1.1), M_leaf2 if k % 3 else M_leaf, 700 + k, lumps=3)

# ---------------------------------------------------------------- light, camera, grade
rig(); camera(ORTHO, TGT, (W_PX, H_PX), dist=120); grade(None)
bpy.context.view_layer.update()

# ---------------------------------------------------------------- layout.json
def S(v): return list(to_screen(Vector(tuple(v) + (0,) * (3 - len(v)))))
corners = [(X0, Y0), (X1, Y0), (X0, Y1), (X1, Y1)]
layout = {
    "size": [W_PX, H_PX], "pxPerUnit": W_PX / ORTHO, "camTilt": CAM_TILT, "sunDir": list(SUN_DIR),
    "bounds": [X0 + 1.5, Y0 + 6.2, X1 - 1.5, Y1 - 2.0],      # where anyone may walk (world)
    "affine": {"ax": None},
    "signs": {k: S(v) for k, v in SIGN.items()},
    "doorsW": {k: [round(v.x, 3), round(v.y, 3)] for k, v in DOOR.items()},
    "yard": [[round(p.x, 3), round(p.y, 3)] for p in (plaza_edge(a / 32 * 2 * math.pi) for a in range(32))],
    "home": [PC.x, PC.y],
    "steam": [S(v) for v in STEAMS],
    "block": [[[round(x, 2), round(y, 2)] for x, y in poly] for poly in BLOCK],
    "allow": [[[round(x, 2), round(y, 2)] for x, y in poly] for poly in ALLOW],
    "paths": [[[round(p.x, 2), round(p.y, 2)] for p in pts[::2]] for pts in DENSE.values()], "pathW": PATH_W,
}
# the ground is flat and the camera orthographic: picture u = ax*x + bx, v = ay*y + by (z = 0)
u0, v0 = S((0, 0)); u1, _ = S((10, 0)); _, v1 = S((0, 10))
layout["affine"] = {"ax": (u1 - u0) / 10, "bx": u0, "ay": (v1 - v0) / 10, "by": v0}

def render_tiled(path, cols=4, rows=2):
    """Render the picture in tiles (crop borders) and stitch them: the laptop GPU never holds the whole frame."""
    import numpy as np
    full = None
    for r in range(rows):
        for c in range(cols):
            sc.render.use_border = True; sc.render.use_crop_to_border = True
            sc.render.border_min_x, sc.render.border_max_x = c / cols, (c + 1) / cols
            sc.render.border_min_y, sc.render.border_max_y = 1 - (r + 1) / rows, 1 - r / rows
            tp = os.path.join(OUT, f"_tile_{r}_{c}.png"); sc.render.filepath = tp; bpy.ops.render.render(write_still=True)
            im = bpy.data.images.load(tp); w, h = im.size
            px = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)[::-1]
            bpy.data.images.remove(im); os.remove(tp)
            if full is None: full = np.zeros((h * rows, w * cols, 4), dtype=np.float32)
            full[r * h:(r + 1) * h, c * w:(c + 1) * w] = px
            print("TILE", r, c)
    sc.render.use_border = False
    out = bpy.data.images.new("stitched", full.shape[1], full.shape[0], alpha=True)
    out.pixels = full[::-1].ravel(); out.filepath_raw = path; out.file_format = "PNG"; out.save()

def id_pass():
    """Each occluder group in one flat colour (R = group number + 1, G = 255), everything else black; no
    anti-aliasing, no grade: the page cuts every occluder from the painted picture with it."""
    flatm = {}
    def fm(i):
        if i not in flatm:
            m = bpy.data.materials.new(f"id{i}"); m.use_nodes = True; nt = m.node_tree; nt.nodes.clear()
            em = nt.nodes.new("ShaderNodeEmission"); oo = nt.nodes.new("ShaderNodeOutputMaterial")
            r = (i + 1) / 255.0; em.inputs[0].default_value = (((r + 0.055) / 1.055) ** 2.4 if r > 0.04045 else r / 12.92, 1.0, 0.0, 1.0)
            nt.links.new(em.outputs[0], oo.inputs[0]); flatm[i] = m
        return flatm[i]
    black = bpy.data.materials.new("idblack"); black.use_nodes = True; nt = black.node_tree; nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission"); em.inputs[0].default_value = (0, 0, 0, 1); oo = nt.nodes.new("ShaderNodeOutputMaterial"); nt.links.new(em.outputs[0], oo.inputs[0])
    owner = {}
    for gi, (name, objs, base) in enumerate(OCC):
        for o in objs:
            owner[o.name] = gi
            for ch in o.children_recursive: owner[ch.name] = gi
    for o in sc.objects:
        if o.type != "MESH" or o.hide_render: continue
        mat = fm(owner[o.name]) if o.name in owner else black
        for i in range(len(o.data.materials)): o.data.materials[i] = mat
        if not o.data.materials: o.data.materials.append(mat)
        # scattered instances use their prototype's material: those count as background (black) unless the emitter is an occluder
    for ob in [o for o in bpy.data.objects if o.hide_render and o.type == "MESH"]:
        for i in range(len(ob.data.materials)): ob.data.materials[i] = black
    sc.use_nodes = False; sc.eevee.taa_render_samples = 1; sc.render.filter_size = 0.0
    sc.view_settings.view_transform = "Standard"; sc.view_settings.look = "None"; sc.render.dither_intensity = 0
    sc.render.film_transparent = True
    render_tiled(os.path.join(OUT, "ids.png"))
    layout["occ"] = [{"name": n, "id": gi + 1, "base": S(b)[1]} for gi, (n, o, b) in enumerate(OCC)]

if not LIVE:
    os.makedirs(OUT, exist_ok=True)
    if WHAT in ("base", "all"):
        sc.render.film_transparent = True
        render_tiled(os.path.join(OUT, "base.png")); print("RENDERED base")
    if WHAT in ("ids", "all"): id_pass(); print("RENDERED ids")
    if "occ" not in layout: layout["occ"] = [{"name": n, "id": gi + 1, "base": S(b)[1]} for gi, (n, o, b) in enumerate(OCC)]
    with open(os.path.join(OUT, "layout.json"), "w", encoding="utf-8") as f: json.dump(layout, f, indent=1)
    print("RENDERED village", WHAT, len(OCC), "occluders")
