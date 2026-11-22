# The "Chợ gà" HUD icon of the village: a little market stall with a striped awning and a straw nest of chicks on the
# counter, in the painted look of lang_lib.py, on a transparent background.
#   blender -b -P icon_cho.py -- <out.png> [size]
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ICON_OUT = os.path.abspath(ARGV[0] if ARGV else "cho.png"); SIZE = int(ARGV[1]) if len(ARGV) > 1 else 640
sys.argv = [sys.argv[0], "--", os.path.dirname(ICON_OUT)]
exec(open(os.path.join(HERE, "lang_lib.py"), encoding="utf-8").read())
random.seed(5)
setup_render(SIZE, SIZE, 64)
sc.render.film_transparent = True
sc.render.image_settings.file_format = "PNG"; sc.render.image_settings.color_mode = "RGBA"
rig()

def grp(objs, loc, rz=0.0, s=1.0):
    e = link(bpy.data.objects.new("grp", None)); e.location = loc; e.rotation_euler = (0, 0, rz); e.scale = (s, s, s)
    for o in objs:
        if o.parent is None: o.parent = e
    return e

M_egg = paint("egg", "#fff6e6", "#c9a88e", "#f1dcc4", "#ffffff", ao=0.35, rand=0.06)
M_egg2 = paint("egg2", "#f7d9b4", "#b68564", "#e6bf94", "#fff0dc", ao=0.35, rand=0.06)
M_straw = paint("straw", "#ffe08a", "#b07a32", "#e2b452", "#fff4c0", grain=0.2, rand=0.08)

o = []
W, D = 3.6, 1.5
o.append(bbox("counter", Vector((0, 0, 0.55)), (W, D, 1.1), M_wood, ol=0.02))
for i in range(8): o.append(bbox("plank", Vector((-W / 2 + 0.24 + i * 0.446, -D / 2 - 0.05, 0.55)), (0.4, 0.08, 1.02), M_wall, bev=0.025, ol=0.01))
o.append(bbox("top", Vector((0, -0.05, 1.14)), (W + 0.3, D + 0.3, 0.12), M_woodd, ol=0.014))
for sx in (-1, 1):
    for sy in (-1, 1): o.append(tube("post", Vector((sx * (W / 2 - 0.08), sy * (D / 2 - 0.08), 0)), 0.11, 0.1, 4.55 if sy > 0 else 3.92, M_woodd, ol=0.016))
cloth = (M_cloth[0], M_cloth[1])
N = 7
for k in range(N):
    x = -W / 2 - 0.15 + (k + 0.5) * (W + 0.3) / N
    o.append(bbox("awn", Vector((x, -0.12, 4.32)), ((W + 0.3) / N + 0.01, D + 1.1, 0.07), cloth[k % 2], rot=(0.32, 0, 0), bev=0.02, ol=0.01))
    o.append(blob("scal", Vector((x, -1.33, 3.8)), (W + 0.3) / N * 0.55, cloth[k % 2], squash=(0.95, 0.14, 0.62), rough=0, subdiv=2, ol=0.01))
# the straw nest on the counter
nest = Vector((-0.45, -0.15, 1.2))
o.append(tube("nest", nest, 0.92, 1.02, 0.34, M_straw, seg=28, ol=0.016, rough=0.05))
for j in range(22):
    a = j / 22 * 2 * math.pi
    o.append(blob("tw", nest + Vector((math.cos(a) * 0.96, math.sin(a) * 0.96, 0.32)), 0.14, M_straw, squash=(1.25, 0.85, 0.8), rough=0.12, subdiv=2))
# a basket of eggs on the right
eb = Vector((1.15, -0.05, 1.2))
o.append(tube("ebask", eb, 0.5, 0.58, 0.3, M_bale, seg=22, ol=0.014))
for j, (dx, dy, m) in enumerate(((0, 0, M_egg), (0.24, 0.1, M_egg2), (-0.22, 0.12, M_egg), (0.05, -0.24, M_egg2), (-0.1, 0.32, M_egg2))):
    o.append(blob("egg", eb + Vector((dx, dy, 0.42)), 0.17, m, squash=(0.82, 0.82, 1.05), rough=0, subdiv=3, ol=0.01))
# sacks by the stall
root = grp(o, Vector((0, 0, 0)), rz=-0.38)

# three chicks in the nest, happy, turned a little each way
chicks = []
for (dx, dy, turn, sc_, dz) in ((-0.52, 0.3, 12, 0.68, 0.32), (0.52, 0.3, -12, 0.68, 0.32), (0.0, -0.3, 0, 0.82, 0.0)):
    C = Chicken(0, 1, ("neutral", "happy"), turn=turn, subject="ga"); C.show("happy")
    C.g.scale = (sc_, sc_, sc_); C.g.location = nest + Vector((dx, dy, 0.22 + dz)); C.g.parent = root
    chicks.append(C)

camera(5.9, Vector((0.05, 0.0, 2.45)), (SIZE, SIZE))
grade(bloom=False)
sc.render.filepath = ICON_OUT
bpy.ops.render.render(write_still=True)
print("ICON", ICON_OUT)
