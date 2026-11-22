# Hero frame of the Làng gà look: one corner of the village (a coop, trees, the yard, Gà Toán and the student) at the
# final pixel density. A quick test scene for lang_lib.py (the shared look); the village itself is lang.py.
#   blender -b -P lang_hero.py -- <out_dir>          -> hero.png (1600 x 1000)
import os
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "lang_lib.py"), encoding="utf-8").read())
random.seed(11)
setup_render(1600, 1000)

YARD_C = Vector((1.8, -1.2, 0)); YARD_R = (8.6, 4.7)
def in_yard(x, y, pad=0.0):
    return ((x - YARD_C.x) / (YARD_R[0] + pad)) ** 2 + ((y - YARD_C.y) / (YARD_R[1] + pad)) ** 2 < 1
def yard_edge(a):
    w = 1 + 0.035 * math.sin(a * 5 + 1.3) + 0.02 * math.sin(a * 11)
    return Vector((YARD_C.x + math.cos(a) * YARD_R[0] * w, YARD_C.y + math.sin(a) * YARD_R[1] * w, 0))
def path_x(y): return 1.6 + 0.6 * math.sin(y * 0.35)
def in_path(x, y, pad=0.0): return -16 < y < YARD_C.y - YARD_R[1] + 0.8 and abs(x - path_x(y)) < 1.15 + 0.12 * math.sin(y * 1.7) + pad
M_dirt = paint("dirt", "#f2d6a2", "#b9876a", "#dcb282", var=0.12, vscale=0.3, up=True, speck=0.07, ao=0.45, rim=0,
               ellipse=(YARD_C.x, YARD_C.y, YARD_R[0], YARD_R[1], 0.16))

lawn = grid("lawn", 70, 140, lambda x, y: not in_yard(x, y, -0.25) and not in_path(x, y, -0.2), M_grass)
plane("yard", [(p.x, p.y) for p in (yard_edge(a / 96 * 2 * math.pi) for a in range(96))], M_dirt, z=0.012)
ys = [YARD_C.y - YARD_R[1] + 0.9 - k * 0.5 for k in range(26)]
plane("path", [(path_x(y) + 1.15 + 0.12 * math.sin(y * 1.7), y) for y in ys] + [(path_x(y) - 1.15 - 0.12 * math.sin(y * 1.7), y) for y in ys][::-1], M_path, z=0.008)
for k in range(14):
    p = yard_edge(random.uniform(0, 2 * math.pi))
    blob("wear", (p.x, p.y, -0.02), random.uniform(0.5, 0.9), M_dirt, squash=(1.4, 1, 0.04), rough=0, subdiv=2)
scatter("grass_a", lawn, T1, 4.0, (0.6, 1.15), seed=3, keep=True, clump=(0.22, 0.0, 2.2))
def rim_zone(x, y):
    return (in_yard(x, y, 1.1) and not in_yard(x, y, -0.4)) or (in_path(x, y, 0.5) and not in_path(x, y, -0.35) and not in_yard(x, y, -0.4))
scatter("grass_rim", grid("rim", 40, 160, rim_zone), T1, 7.0, (0.55, 1.0), seed=5)
scatter("grass_rim2", grid("rim2", 40, 160, rim_zone), T2, 5.0, (0.5, 0.9), seed=6)
for i, pm in enumerate(M_petal):
    scatter(f"flowers{i}", grid(f"fl_s{i}", 70, 70, lambda x, y: not in_yard(x, y, 0.8)), flower(pm), 0.3, (0.8, 1.3), seed=20 + i, tilt=0.2,
            clump=(0.2 + i * 0.05, 0.0, 4.0, 0.56, 0.68))
yard_in = grid("yard_in", 30, 60, lambda x, y: in_yard(x, y, -0.8)); yard_in.location.z = 0.02
scatter("pebbles", yard_in, PEBBLE, 0.55, (0.5, 1.4), seed=7, tilt=0.3)
scatter("yard_tufts", grid("yt", 30, 60, lambda x, y: in_yard(x, y, -1.0)), T2, 0.18, (0.4, 0.8), seed=13, clump=(0.3, 0, 3, 0.5, 0.62))
rock_ring(yard_edge, 46, gap=[(1.5 * math.pi, 0.22)], seed=2)

C = Vector((-4.6, 4.3, 0)); coop(C)
fd = C + Vector((3.9, -3.0, 0))
tube("feeder", fd, 0.75, 0.85, 0.32, M_wood, seg=28, ol=0.012)
blob("grainpile", fd + Vector((0, 0, 0.3)), 0.68, M_grain, squash=(1, 1, 0.22), rough=0.1, subdiv=3)
hb = C + Vector((-2.4, -3.3, 0))
bbox("bale", hb + Vector((0, 0, 0.6)), (1.9, 1.3, 1.2), M_bale, bev=0.16, seg=3, ol=0.014)
bst = grid("bale_top", 1.7, 8, lambda x, y: True); bst.location = hb + Vector((0, 0, 1.2))
scatter("bale_tufts", bst, STRAW, 18, (0.5, 1.0), seed=8, tilt=0.4)
for dx in (-0.45, 0.45): bbox("twine", hb + Vector((dx, 0, 0.6)), (0.07, 1.34, 1.24), M_woodd, bev=0.03, ol=0)
blob("sack", hb + Vector((-1.6, -0.6, 0.55)), 0.62, M_burlap, squash=(0.9, 0.8, 1.05), rough=0.18, subdiv=3, ol=0.012)

for i, (p, kind, s) in enumerate([(Vector((-0.4, 7.8, 0)), "leaf", 0.72), (Vector((8.4, 6.6, 0)), "pink", 0.74), (Vector((-10.2, 8.6, 0)), "leaf", 0.8)]):
    tree(p, kind, s, seed=i)
for i, p in enumerate([Vector((4.8, 4.6, 0)), Vector((-9.4, -1.4, 0)), Vector((10.8, -3.6, 0))]):
    bush(p, seed=i, flowers=1 if i == 0 else None)
fence(-12.0, -3.0, -7.8); fence(5.6, 13.5, -7.8)
lantern(Vector((8.0, -3.4, 0)))

ga = Chicken(0, 3, ("neutral",), turn=-18, subject="toan"); ga.g.location = (-0.4, -1.9, 0)
_k = open(os.path.join(HERE, "kid.py"), encoding="utf-8").read()
exec(_k[_k.index("KIND ="):_k.index("# idle")])
g.location = (3.4, -0.4, 0); g.scale = (1.3, 1.3, 1.3)

rig(); camera(19, (0.6, 2.2, 2.6), (1600, 1000)); grade(89, 104, 0.1)
sc.render.filepath = os.path.join(OUT, "hero.png")
if not LIVE: bpy.ops.render.render(write_still=True)
print("RENDERED hero")
