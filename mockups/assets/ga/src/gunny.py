# Gunny-style costume library for the 23 subject chickens: HATS (the silhouette), EMBLEMS (a big chest badge) and HELD items (the signature prop).
# Used by costume.py. Everything is built from chunky extruded outlines so a subject reads from its hat + badge + prop at map size.
import bpy, bmesh, math
from mathutils import Vector


def V(x, y, z): return Vector((x, y, z))


def M(k):
    """the shared colour materials of one kit (subject suffixed ones follow the spec)"""
    if getattr(k, "_M", None): return k._M
    T = k.H.toon
    d = dict(main=k.m_main, deep=k.m_deep, cream=k.m_cream, gold=k.m_gold, ink=k.m_ink, red=k.m_red, metal=k.m_metal)
    d.update(
        silver=T("g_silver", "#f2f5fb", "#8c97ad", "#ffffff"), white=T("g_white", "#ffffff", "#cfd6e6", "#ffffff"),
        black=T("g_black", "#4a4a5c", "#17181f", "#7a7c92"), wood=T("g_wood", "#d09050", "#93592a", "#f2c288"),
        green=T("g_green", "#4cc65e", "#2f8f3f", "#a8ec9e"), blue=T("g_blue", "#3f9bf2", "#2a63b0", "#b8dcff"),
        sky=T("g_sky", "#bfeaff", "#7fc4e8", "#ffffff"), yellow=T("g_yel", "#ffd93a", "#d99a00", "#fff3a0"),
        orange=T("g_ora", "#ff9a2a", "#c8620a", "#ffd08a"), pink=T("g_pink", "#ff7fb0", "#c8457f", "#ffc4dc"),
        purple=T("g_pur", "#a066e0", "#6a3aa8", "#d9b8ff"), brown=T("g_brn", "#9a6a45", "#5e3a22", "#d9b08a"),
        khaki=T("g_khk", "#d9b872", "#9a7a3a", "#f5e0a8"), bronze=T("g_brz", "#d9a441", "#8a5a14", "#ffe08a"),
        paper=T("g_pap", "#fff8e6", "#e3d2a8", "#ffffff"), lcd=T("g_lcd", "#cfeec0", "#8fc07f", "#ffffff"),
        neon=T("g_neon", "#7ff0ff", "#1fb0c9", "#e0ffff"), lime=T("g_lime", "#a6e22e", "#6a9a10", "#e0ff9a"),
        crimson=T("g_crim", "#e0413a", "#a82a24", "#ff8f87"), navy=T("g_navy", "#2f4f9a", "#1b2f66", "#8aa6e0"),
        terra=T("g_terra", "#d9794a", "#9a4a24", "#f2b08a"), teal=T("g_teal", "#25b5ae", "#13756f", "#8ae6df"),
        grey=T("g_grey", "#a9b3bf", "#5d6672", "#e0e6ee"), pcb=T("g_pcb", "#2bb673", "#15774a", "#9be8c0"),
        dark=T("g_dark", "#2c3440", "#12161c", "#5c6878"), lav=T("g_lav", "#d4cbff", "#9c8ee0", "#ffffff"),
        glass=T("g_glass", "#d6f1ff", "#9fd0ea", "#ffffff"),
    )
    k._M = d
    return d


class F:
    """flat chunky shapes facing the viewer (-y) around a centre p, in units of r"""
    def __init__(s, k, p, r, add=None):
        s.k, s.p, s.r = k, Vector(p), r; s.add = add or k.ch.add; s.m = M(k)

    def at(s, x, z, dy=0.0): return Vector((s.p.x + x * s.r, s.p.y + dy * s.r, s.p.z + z * s.r))

    def poly(s, pts, mat, dy=0.0, d=0.28, ol=0.012, bev=0.03, rot=0.0, ox=0.0, oz=0.0, sc=1.0):
        c, sn = math.cos(rot), math.sin(rot)
        loop = [s.at(ox + (x * c - z * sn) * sc, oz + (x * sn + z * c) * sc, dy) for x, z in pts]
        return s.add(s.k.poly("fp", loop, d * s.r, mat, outline=ol, bevel=bev * s.r))

    def circ(s, cx, cz, rad, mat, dy=0.0, d=0.28, n=36, sx=1.0, sz=1.0, ol=0.012, a0=0, a1=360):
        pts = [(cx + math.cos(math.radians(a)) * rad * sx, cz + math.sin(math.radians(a)) * rad * sz) for a in [a0 + (a1 - a0) * i / n for i in range(n)]]
        return s.poly(pts, mat, dy, d, ol=ol)

    def ring(s, cx, cz, rad, w, mat, dy=0.0, n=40, sx=1.0, sz=1.0):
        return s.add(s.k.tube("fr", [s.at(cx + math.cos(a) * rad * sx, cz + math.sin(a) * rad * sz, dy) for a in [i * 2 * math.pi / n for i in range(n)]], w * s.r, mat, closed=True, outline=0.008, sides=6))

    def line(s, a, b, w, mat, dy=0.0):
        return s.add(s.k.tube("fl", [s.at(a[0], a[1], dy), s.at(b[0], b[1], dy)], w * s.r, mat, outline=0.006, sides=6))

    def poly_line(s, pts, w, mat, dy=0.0, closed=False):
        return s.add(s.k.tube("fpl", [s.at(x, z, dy) for x, z in pts], w * s.r, mat, closed=closed, outline=0.006, sides=6))

    def text(s, txt, cx, cz, size, mat, dy=0.0, ext=0.06):
        cu = bpy.data.curves.new("tx", "FONT"); cu.body = txt; cu.align_x = "CENTER"; cu.align_y = "CENTER"; cu.size = size * s.r; cu.extrude = ext * s.r
        cu.materials.append(mat); t = s.k.H.link(bpy.data.objects.new("tx", cu)); t.location = s.at(cx, cz, dy); t.rotation_euler = (math.radians(90), 0, 0)
        return s.add(t)

    def ball(s, cx, cz, rad, mat, dy=0.0, sy=1.0, ol=0.01, sx=1.0, sz=1.0):
        return s.add(s.k.H.ball("fb", s.at(cx, cz, dy), (rad * s.r * sx, rad * s.r * sy, rad * s.r * sz), mat, outline=ol))

    def box(s, cx, cz, w, h, mat, dy=0.0, dep=0.2, rot=0.0, ol=0.01):
        o = s.k.H.rbox("fx", s.at(cx, cz, dy), (w * s.r, dep * s.r, h * s.r), mat, outline=ol, rot=(0, -rot, 0))
        return s.add(o)


def rect(w, h, cx=0.0, cz=0.0): return [(cx - w, cz - h), (cx + w, cz - h), (cx + w, cz + h), (cx - w, cz + h)]


def arc(rad, a0, a1, n=12, cx=0.0, cz=0.0): return [(cx + math.cos(math.radians(a0 + (a1 - a0) * i / n)) * rad, cz + math.sin(math.radians(a0 + (a1 - a0) * i / n)) * rad) for i in range(n + 1)]


BOLT = [(0.2, 1.0), (0.72, 1.0), (0.3, 0.2), (0.7, 0.2), (-0.42, -1.0), (-0.1, -0.1), (-0.62, -0.1)]


def leaf_pts(L, w): return [(0, 0), (w * 0.55, L * 0.2), (w, L * 0.5), (w * 0.62, L * 0.82), (0, L), (-w * 0.62, L * 0.82), (-w, L * 0.5), (-w * 0.55, L * 0.2)]


def flask_pts(): return [(-0.28, 1.0), (0.28, 1.0), (0.28, 0.55), (0.95, -0.85), (0.8, -1.0), (-0.8, -1.0), (-0.95, -0.85), (-0.28, 0.55)]


# ================================================================== EMBLEMS: chest badges (centre, size r) =====================================
def em_bolt(f, m, t=3):
    f.poly(BOLT, m["yellow"], d=0.34)


def em_flask(f, m, t=3):
    f.poly(flask_pts(), m["glass"], d=0.3)
    f.poly([(-0.78, -0.2), (0.78 - 0.1, -0.2 + 0.0), (0.9, -0.85), (0.78, -0.97), (-0.78, -0.97), (-0.9, -0.85)], m["lime"], dy=-0.2, d=0.2, ol=0.0)
    f.poly(rect(0.34, 0.12, 0, 1.1), m["wood"], dy=-0.1, d=0.3)
    for cx, cz, rr in ((0.1, 0.3, 0.14), (-0.12, 0.62, 0.1), (0.1, 0.82, 0.08)): f.ball(cx, cz, rr, m["white"], dy=-0.4, ol=0.006)


def em_dna(f, m, t=3):
    for ph, col in ((0, m["main"]), (math.pi, m["lime"])):
        pts = [(math.sin(z * 2.4 + ph) * 0.62, z) for z in [-1 + i * 2 / 24 for i in range(25)]]
        f.poly_line(pts, 0.14, col, dy=-0.2)
    for z in [-0.88 + i * 0.4 for i in range(5)]:
        w = math.sin(z * 2.4) * 0.62; f.line((-w, z), (w, z), 0.07, m["white"], dy=-0.1)


def em_leaf(f, m, t=3):
    f.poly(leaf_pts(2.0, 0.78), m["green"], oz=-1.0, d=0.3, rot=0.0)
    f.line((0, -0.95), (0, 0.8), 0.06, m["white"], dy=-0.2)


def em_drum(f, m, t=3):  # Dong Son bronze drum face: rings, a sun star and a bird frieze
    f.circ(0, 0, 1.0, m["bronze"], d=0.3)
    f.ring(0, 0, 0.88, 0.05, m["dark"], dy=-0.2); f.ring(0, 0, 0.62, 0.05, m["dark"], dy=-0.2)
    star = []
    for i in range(24):
        a = math.pi / 2 + i * math.pi / 12; rr = 0.52 if i % 2 == 0 else 0.26; star.append((math.cos(a) * rr, math.sin(a) * rr))
    f.poly(star, m["gold"], dy=-0.25, d=0.2)
    for i in range(12):
        a = i * math.pi / 6; f.ball(math.cos(a) * 0.75, math.sin(a) * 0.75, 0.06, m["dark"], dy=-0.25, ol=0.0)


def em_compass(f, m, t=3):  # a compass rose
    f.circ(0, 0, 1.0, m["sky"], d=0.28); f.ring(0, 0, 0.9, 0.05, m["navy"], dy=-0.2)
    f.poly([(0, 0.92), (0.2, 0.2), (0, 0), (-0.2, 0.2)], m["red"], dy=-0.25, d=0.2)
    f.poly([(0, -0.92), (0.2, -0.2), (0, 0), (-0.2, -0.2)], m["white"], dy=-0.25, d=0.2)
    f.poly([(0.92, 0), (0.2, 0.2), (0, 0), (0.2, -0.2)], m["navy"], dy=-0.25, d=0.2)
    f.poly([(-0.92, 0), (-0.2, 0.2), (0, 0), (-0.2, -0.2)], m["navy"], dy=-0.25, d=0.2)
    f.circ(0, 0, 0.1, m["gold"], dy=-0.5, d=0.2)


def em_scales(f, m, t=3):  # the scales of justice
    f.line((0, -0.95), (0, 0.75), 0.1, m["gold"], dy=-0.1); f.poly(rect(0.5, 0.1, 0, -0.95), m["gold"], dy=-0.1, d=0.3)
    f.line((-0.85, 0.62), (0.85, 0.62), 0.09, m["gold"], dy=-0.15); f.ball(0, 0.78, 0.13, m["gold"], dy=-0.2)
    for sx in (-1, 1):
        x = sx * 0.85; f.line((x, 0.62), (x - sx * 0.35, -0.12), 0.03, m["white"], dy=-0.1); f.line((x, 0.62), (x + sx * 0.35, -0.12), 0.03, m["white"], dy=-0.1)
        f.poly(arc(0.5, 180, 360, 10, x, -0.12), m["gold"], dy=-0.2, d=0.3)


def em_gear(f, m, t=3):
    pts = []
    for i in range(32):
        a = i * math.pi / 16; rr = 1.0 if (i // 2) % 2 == 0 else 0.76; pts.append((math.cos(a) * rr, math.sin(a) * rr))
    f.poly(pts, m["main"], d=0.34); f.circ(0, 0, 0.3, m["cream"], dy=-0.3, d=0.2); f.ring(0, 0, 0.55, 0.05, m["white"], dy=-0.3)


def em_atom(f, m, t=3):
    f.circ(0, 0, 1.0, m["dark"], d=0.26)
    for rz in (0, 60, -60):
        pts = [(math.cos(a) * 0.86, math.sin(a) * 0.34) for a in [i * 2 * math.pi / 28 for i in range(28)]]
        c, sn = math.cos(math.radians(rz)), math.sin(math.radians(rz))
        f.add(f.k.tube("orb", [f.at(x * c - z * sn, x * sn + z * c, -0.25) for x, z in pts], 0.06 * f.r, m["neon"], closed=True, outline=0.006, sides=6))
    f.ball(0, 0, 0.2, m["gold"], dy=-0.3)
    for a in (20, 140, 260): f.ball(math.cos(math.radians(a)) * 0.74, math.sin(math.radians(a)) * 0.34, 0.09, m["white"], dy=-0.3, ol=0.0)


def em_text(txt, size, bg, fg="neon", mid=0.0):
    def fn(f, m, t=3):
        f.circ(0, 0, 1.0, m[bg], d=0.26)
        f.text(txt, 0, mid, size, m[fg], dy=-0.25)
    return fn


def em_clock(f, m, t=3):  # hourglass
    f.poly([(-0.7, 0.9), (0.7, 0.9), (0.08, 0.0), (0.7, -0.9), (-0.7, -0.9), (-0.08, 0.0)], m["glass"], d=0.28)
    f.poly([(-0.44, -0.8), (0.44, -0.8), (0.1, -0.36), (-0.1, -0.36)], m["yellow"], dy=-0.2, d=0.2, ol=0.0)
    f.poly([(-0.5, 0.78), (0.5, 0.78), (0.08, 0.06), (-0.08, 0.06)], m["yellow"], dy=-0.2, d=0.2, ol=0.0)
    for z in (0.98, -0.98): f.poly(rect(0.86, 0.1, 0, z), m["brown"], dy=-0.1, d=0.34)


def em_chip(f, m, t=3):
    for i in range(5):
        z = -0.7 + i * 0.35
        for sx in (-1, 1): f.poly(rect(0.2, 0.07, sx * 1.0, z), m["gold"], dy=0.05, d=0.2, ol=0.006)
        f.poly(rect(0.07, 0.2, z, 1.0), m["gold"], dy=0.05, d=0.2, ol=0.006); f.poly(rect(0.07, 0.2, z, -1.0), m["gold"], dy=0.05, d=0.2, ol=0.006)
    f.poly(rect(0.8, 0.8), m["dark"], dy=-0.1, d=0.34); f.poly(rect(0.4, 0.4), m["grey"], dy=-0.3, d=0.2); f.circ(0, 0, 0.14, m["neon"], dy=-0.5, d=0.2)


def em_table(f, m, t=3):  # a data table grid
    f.poly(rect(1.0, 0.85), m["white"], d=0.3); f.poly(rect(1.0, 0.2, 0, 0.65), m["main"], dy=-0.1, d=0.3)
    for z in (0.2, -0.25, -0.7): f.line((-1.0, z), (1.0, z), 0.04, m["dark"], dy=-0.2)
    for x in (-0.33, 0.33): f.line((x, 0.85), (x, -0.85), 0.04, m["dark"], dy=-0.2)
    for x, z in ((-0.66, 0.0), (0.0, -0.45), (0.66, 0.0)): f.circ(x, z, 0.1, m["lime"], dy=-0.25, d=0.2)


def em_pie(f, m, t=3):  # pie chart
    f.circ(0, 0, 1.0, m["white"], d=0.3)
    f.poly([(0, 0)] + arc(0.94, 90, -30, 10), m["main"], dy=-0.15, d=0.26)
    f.poly([(0.0, 0.0)] + arc(0.94, -30, -150, 10), m["gold"], dy=-0.15, d=0.26)
    f.poly([(0.0, 0.0)] + arc(0.94, 90, 210, 10), m["purple"], dy=-0.15, d=0.26)
    f.poly([(0, 0)] + arc(1.12, 210, 270, 6), m["pink"], dy=-0.15, d=0.26, ox=-0.05, oz=-0.02, sc=0.88)


def em_hex(f, m, t=3):  # a benzene ring
    f.circ(0, 0, 1.0, m["white"], d=0.28)
    hexp = [(math.cos(math.radians(30 + 60 * i)) * 0.7, math.sin(math.radians(30 + 60 * i)) * 0.7) for i in range(6)]
    f.poly_line(hexp, 0.1, m["purple"], dy=-0.2, closed=True)
    f.ring(0, 0, 0.42, 0.05, m["purple"], dy=-0.2)
    for (x, z) in hexp: f.ball(x, z, 0.14, m["pink"], dy=-0.3, ol=0.008)


def em_calc(f, m, t=3):  # a calculator
    f.poly(rect(0.78, 1.0), m["main"], d=0.32, bev=0.06); f.poly(rect(0.62, 0.22, 0, 0.66), m["lcd"], dy=-0.2, d=0.2)
    f.text("8.8", 0.18, 0.64, 0.34, m["dark"], dy=-0.4, ext=0.03)
    cols = (m["white"], m["white"], m["white"], m["orange"])
    for i in range(3):
        for j in range(4): f.poly(rect(0.15, 0.1, -0.44 + j * 0.3, 0.16 - i * 0.3), cols[j] if j == 3 else m["white"], dy=-0.25, d=0.2, ol=0.006)
    f.poly(rect(0.15, 0.1, 0.46, -0.74), m["green"], dy=-0.25, d=0.2, ol=0.006)


def em_coin(f, m, t=3):
    f.circ(0, 0, 1.0, m["gold"], d=0.34); f.ring(0, 0, 0.8, 0.06, m["bronze"], dy=-0.2)
    f.text("$", 0, 0.0, 1.35, m["bronze"], dy=-0.3, ext=0.08)


def em_books(f, m, t=3):  # a stack of books
    cols = (m["main"], m["gold"], m["red"], m["green"])
    for i, (w, c) in enumerate(((0.95, cols[0]), (0.8, cols[1]), (0.88, cols[2]), (0.7, cols[3]))):
        z = -0.78 + i * 0.5; f.poly(rect(w, 0.22, 0.04 * (i % 2), z), c, dy=-0.05 * i, d=0.4)
        f.poly(rect(w * 0.9, 0.06, 0.04 * (i % 2) + 0.06, z), m["paper"], dy=-0.25 - 0.05 * i, d=0.2, ol=0.0)


def em_scroll(f, m, t=3):  # a poem scroll with a red seal
    f.poly(rect(0.7, 0.85), m["paper"], d=0.3)
    for z in (0.5, 0.25, 0.0, -0.25): f.line((-0.45, z), (0.45 - 0.08 * (z < 0.2), z), 0.045, m["dark"], dy=-0.2)
    for sz in (-1, 1): f.poly(rect(0.88, 0.13, 0, sz * 0.9), m["wood"], dy=-0.1, d=0.4)
    f.poly(rect(0.17, 0.17, 0.4, -0.55), m["crimson"], dy=-0.3, d=0.2)


def em_union(f, m, t=3):  # a Union Jack disc
    f.circ(0, 0, 1.0, m["navy"], d=0.28)
    for ang in (45, -45):
        a = math.radians(ang); f.poly(rect(1.05, 0.16), m["white"], dy=-0.12, d=0.2, rot=a, ol=0.0); f.poly(rect(1.05, 0.07), m["crimson"], dy=-0.16, d=0.2, rot=a, ol=0.0)
    f.poly(rect(1.02, 0.24), m["white"], dy=-0.22, d=0.2, ol=0.0); f.poly(rect(0.24, 1.02), m["white"], dy=-0.22, d=0.2, ol=0.0)
    f.poly(rect(1.0, 0.13), m["crimson"], dy=-0.3, d=0.2, ol=0.0); f.poly(rect(0.13, 1.0), m["crimson"], dy=-0.3, d=0.2, ol=0.0)
    f.ring(0, 0, 1.0, 0.06, m["gold"], dy=-0.2)


def em_palette(f, m, t=3):  # three paint splats
    for cx, cz, c in ((-0.45, 0.35, m["red"]), (0.45, 0.35, m["yellow"]), (0, -0.4, m["blue"])):
        pts = [(cx + math.cos(a) * (0.62 + 0.14 * math.sin(a * 5)), cz + math.sin(a) * (0.62 + 0.14 * math.sin(a * 5))) for a in [i * 2 * math.pi / 30 for i in range(30)]]
        f.poly(pts, c, dy=-0.1 * (cz < 0), d=0.3)
    f.circ(0, -0.05, 0.22, m["white"], dy=-0.3, d=0.2)


def em_flow(f, m, t=3):  # a flowchart
    f.circ(0, 0, 1.0, m["white"], d=0.26)
    f.poly(rect(0.42, 0.2, 0, 0.62), m["main"], dy=-0.15, d=0.2); f.poly([(0, 0.28), (0.42, 0), (0, -0.28), (-0.42, 0)], m["gold"], dy=-0.15, d=0.2)
    f.poly(rect(0.42, 0.2, 0, -0.62), m["main"], dy=-0.15, d=0.2); f.line((0, 0.42), (0, 0.28), 0.06, m["dark"], dy=-0.2); f.line((0, -0.28), (0, -0.42), 0.06, m["dark"], dy=-0.2)


def em_db(f, m, t=3):  # a database cylinder
    for i, z in enumerate((-0.6, 0.0, 0.6)):
        f.poly(rect(0.82, 0.34, 0, z), m["main"], dy=0.0, d=0.3, ol=0.0)
        f.circ(0, z - 0.34, 0.82, m["main"], d=0.3, sz=0.28, ol=0.0)
        f.circ(0, z + 0.34, 0.82, m["white"], dy=-0.1, d=0.3, sz=0.28)
        f.circ(-0.55, z - 0.02, 0.09, m["lime"], dy=-0.2, d=0.2, n=12, ol=0.0)
    f.line((-0.82, 0.94), (-0.82, -0.94), 0.06, m["dark"], dy=-0.05); f.line((0.82, 0.94), (0.82, -0.94), 0.06, m["dark"], dy=-0.05)


EMB = dict(
    protractor=None, bolt=em_bolt, flask=em_flask, dna=em_dna, leaf=em_leaf, drum=em_drum, compass=em_compass, scales=em_scales, gear=em_gear, atom=em_atom,
    code=em_text("</>", 0.78, "dark", "neon"), braces=em_text("{ }", 1.0, "main", "white", 0.02), formula=em_text("E=mc2", 0.52, "dark", "yellow"), h2o=em_text("H2O", 0.6, "purple", "white"),
    clock=em_clock, chip=em_chip, table=em_table, pie=em_pie, hex=em_hex, calc=em_calc, coin=em_coin, books=em_books, scroll=em_scroll, union=em_union,
    palette=em_palette, flow=em_flow, db=em_db,
)
BACK = dict(drum="bronze", compass="sky", union="navy", calc="main", hex="white", pie="white", table="white", flow="white", chip="dark", atom="dark")


SELF = ('drum', 'compass', 'union', 'atom', 'coin', 'code', 'braces', 'formula', 'h2o', 'hex', 'pie', 'flow', 'maths')


def chest(k, name, p, r, t=3, add=None):
    """a medallion: a gold ring, a backing disc and the emblem, centred at p"""
    m = M(k); fn = EMB.get(name)
    if fn is None: return
    f = F(k, p, r, add)
    if name not in SELF:
        f.circ(0, 0, 1.28, m["cream"] if name not in ("bolt", "flask", "hex") else m["dark"], dy=0.35, d=0.28, ol=0.014)
        f2 = F(k, p + V(0, -0.05 * r, 0), r * 0.84, add)
    else:
        f2 = F(k, p + V(0, -0.0, 0), r, add)
    f.ring(0, 0, 1.0 if name in SELF else 1.28, 0.1, m["gold"], dy=-0.12)
    fn(f2, m, t)


# ================================================================== HELD signature items (centre p, half-height r) =============================
def hd_brush(f, m):  # bút lông: a long calligraphy brush with a red ferrule
    k = f.k
    f.add(k.tube("hb", [f.at(-0.3, -1.1), f.at(0.16, 0.45)], 0.12 * f.r, m["wood"], outline=0.01, sides=6))
    f.add(k.tube("hb2", [f.at(0.12, 0.38), f.at(0.2, 0.55)], 0.15 * f.r, m["crimson"], outline=0.008, sides=6))
    f.add(k.tube("hbt", [f.at(0.2, 0.52), f.at(0.28, 0.9), f.at(0.33, 1.28)], lambda t: 0.2 * f.r * (1 - t * 0.92), m["ink"], outline=0.01, sides=8))
    f.add(k.tube("hbk", [f.at(-0.3, -1.1), f.at(-0.34, -1.2)], 0.15 * f.r, m["gold"], outline=0.008, sides=6))


def hd_magnet(f, m):
    pts = [(-1, 0.9), (-1, 0.0)] + arc(1.0, 180, 360, 14) + [(1, 0.9), (0.5, 0.9), (0.5, 0.0)] + arc(0.5, 360, 180, 10) + [(-0.5, 0.9)]
    f.poly(pts, m["crimson"], d=0.5, bev=0.04)
    for sx in (-1, 1): f.poly(rect(0.25, 0.2, sx * 0.75, 0.7), m["silver"], dy=-0.3, d=0.5)
    for dx in (-0.6, 0.6): f.poly([(dx - 0.08, 1.3), (dx + 0.05, 1.05), (dx, 1.4)], m["yellow"], dy=-0.2, d=0.2)


def hd_beaker(f, m):
    f.poly([(-0.6, 1.0), (0.6, 1.0), (0.6, -0.9), (-0.6, -0.9)], m["glass"], d=0.5, bev=0.05)
    f.poly(rect(0.56, 0.5, 0, -0.4), m["lime"], dy=-0.3, d=0.4, ol=0.0)
    for z in (0.6, 0.35, 0.1): f.line((0.1, z), (0.6, z), 0.05, m["dark"], dy=-0.5)
    for cx, cz, rr in ((-0.15, -0.1, 0.14), (0.15, 0.2, 0.1), (-0.2, 0.55, 0.09)): f.ball(cx, cz, rr, m["white"], dy=-0.6, ol=0.006)


def hd_magnifier(f, m):
    f.ring(-0.1, 0.35, 0.72, 0.12, m["gold"], dy=-0.2); f.circ(-0.1, 0.35, 0.68, m["sky"], dy=0.0, d=0.3)
    f.k.tube  # noqa
    f.add(f.k.tube("hmh", [f.at(0.4, -0.2), f.at(0.9, -0.95)], 0.15 * f.r, m["wood"], outline=0.01, sides=6))
    f.poly(leaf_pts(0.7, 0.2), m["green"], dy=-0.35, d=0.2, ox=-0.1, oz=0.1, rot=0.6)


def hd_scroll(f, m):
    f.poly(rect(0.8, 0.95), m["paper"], d=0.4)
    for sz in (-1, 1): f.poly(rect(0.95, 0.15, 0, sz * 1.0), m["bronze"], dy=-0.1, d=0.7); f.ball(sz * 0.0 + 0.95, sz * 1.0, 0.17, m["red"], dy=-0.1); f.ball(-0.95, sz * 1.0, 0.17, m["red"], dy=-0.1)
    for z in (0.55, 0.25, -0.05, -0.35): f.line((-0.5, z), (0.5, z), 0.06, m["dark"], dy=-0.25)
    f.poly(rect(0.15, 0.15, 0.45, -0.6), m["crimson"], dy=-0.3, d=0.2)


def hd_gavel(f, m):
    f.add(f.k.tube("hgh", [f.at(-0.7, -0.9), f.at(0.3, 0.35)], 0.15 * f.r, m["wood"], outline=0.01, sides=6))
    f.add(f.k.H.rbox("hgd", f.at(0.35, 0.55), (0.95 * f.r, 0.5 * f.r, 0.52 * f.r), m["brown"], outline=0.012, rot=(0, -0.7, 0)))
    for dd in (-0.25, 0.25): f.add(f.k.H.rbox("hgb", f.at(0.35 + dd * 0.8, 0.55 + dd * 0.7, -0.35), (0.14 * f.r, 0.52 * f.r, 0.58 * f.r), m["gold"], outline=0.008, rot=(0, -0.7, 0)))
    f.poly(rect(0.95, 0.17, 0.35, -1.1), m["brown"], d=0.5)


def hd_globe(f, m):
    f.ball(0, 0.15, 0.85, m["sky"], ol=0.014)
    for cx, cz, sx, sz in ((0.2, 0.45, 0.4, 0.3), (-0.35, 0.0, 0.3, 0.4), (0.3, -0.25, 0.28, 0.3)): f.ball(cx, cz + 0.15, 0.5, m["green"], dy=-0.62, sy=0.12, sx=sx * 1.6, sz=sz * 1.6, ol=0.0)
    f.add(f.k.tube("hgm", [f.at(0.0 + math.cos(math.radians(a)) * 0.95, 0.15 + math.sin(math.radians(a)) * 0.95, -0.2) for a in range(-80, 260, 10)], 0.06 * f.r, m["gold"], outline=0.006, sides=6))
    f.poly(rect(0.5, 0.1, 0, -1.05), m["wood"], d=0.6); f.poly([(-0.14, -0.9), (0.14, -0.9), (0.08, -0.7), (-0.08, -0.7)], m["wood"], d=0.5)


def hd_laptop(f, m):
    k = f.k; H = k.H
    f.add(H.rbox("hl1", f.at(0, 0.18, 0.1), (1.9 * f.r, 0.14 * f.r, 1.3 * f.r), m["dark"], outline=0.012, rot=(math.radians(-8), 0, 0)))
    f.add(H.rbox("hl2", f.at(0, 0.18, -0.05), (1.62 * f.r, 0.06 * f.r, 1.0 * f.r), m["black"], outline=0, rot=(math.radians(-8), 0, 0)))
    for i, w in enumerate((0.9, 0.55, 0.75, 0.4)): f.line((-0.7, 0.55 - i * 0.28), (-0.7 + w, 0.55 - i * 0.28), 0.06, m["neon"] if i % 2 == 0 else m["lime"], dy=-0.2)
    f.add(H.rbox("hl3", f.at(0, -0.85, -0.45), (2.1 * f.r, 0.9 * f.r, 0.14 * f.r), m["silver"], outline=0.012))


def hd_wrench(f, m):  # cờ lê
    f.poly([(-0.18, -1.15), (0.18, -1.15), (0.2, 0.4), (-0.2, 0.4)], m["silver"], d=0.5, bev=0.04, rot=0.0)
    head = [(-0.62, 0.35), (-0.62, 1.1), (-0.25, 1.1), (-0.25, 0.78), (0.25, 0.78), (0.25, 1.1), (0.62, 1.1), (0.62, 0.35)]
    f.poly(head, m["silver"], d=0.5, bev=0.04); f.circ(0, -1.0, 0.14, m["dark"], dy=-0.3, d=0.2)
    f.poly(rect(0.2, 0.55, 0, -0.35), m["orange"], dy=-0.3, d=0.5, bev=0.04)


def hd_micro(f, m):  # microscope
    k = f.k; H = k.H
    f.poly(rect(0.8, 0.12, 0, -1.05), m["dark"], d=0.7); f.add(k.tube("hm1", [f.at(0.4, -1.0), f.at(0.65, -0.3), f.at(0.45, 0.4)], 0.13 * f.r, m["lime"], outline=0.01, sides=8))
    f.add(k.tube("hm2", [f.at(-0.35, 1.25), f.at(0.2, 0.3)], 0.19 * f.r, m["silver"], outline=0.01, sides=8)); f.add(k.tube("hm3", [f.at(-0.42, 1.38), f.at(-0.5, 1.5)], 0.12 * f.r, m["dark"], outline=0.01, sides=8))
    f.poly(rect(0.5, 0.07, -0.2, -0.3), m["dark"], d=0.6); f.add(k.tube("hm4", [f.at(0.2, 0.3), f.at(0.5, 0.45)], 0.13 * f.r, m["lime"], outline=0.01, sides=6))
    f.ball(-0.2, -0.05, 0.16, m["neon"], dy=-0.2, ol=0.0)


def hd_paintbrush(f, m):
    f.add(f.k.tube("hp1", [f.at(-0.6, -1.15), f.at(0.2, 0.2)], 0.12 * f.r, m["pink"], outline=0.01, sides=6))
    f.add(f.k.tube("hp2", [f.at(0.15, 0.1), f.at(0.3, 0.4)], 0.16 * f.r, m["silver"], outline=0.008, sides=6))
    f.add(f.k.tube("hp3", [f.at(0.3, 0.4), f.at(0.5, 0.95), f.at(0.62, 1.3)], lambda t: 0.26 * f.r * (1 - t * 0.85), m["main"], outline=0.01, sides=8))
    f.ball(0.45, 0.8, 0.3, m["yellow"], dy=-0.3, ol=0.0)


def hd_planner(f, m):  # a clipboard checklist
    f.poly(rect(0.8, 1.05), m["brown"], d=0.5, bev=0.05); f.poly(rect(0.66, 0.9), m["paper"], dy=-0.3, d=0.3)
    f.poly(rect(0.32, 0.14, 0, 1.0), m["silver"], dy=-0.5, d=0.4)
    for i, z in enumerate((0.6, 0.15, -0.3, -0.75)):
        f.circ(-0.4, z, 0.14, m["green"] if i < 3 else m["white"], dy=-0.5, d=0.2, n=14); f.line((-0.15, z), (0.5, z), 0.07, m["dark"], dy=-0.5)
    f.poly([(-0.48, 0.62), (-0.4, 0.52), (-0.28, 0.72), (-0.4, 0.6)], m["white"], dy=-0.7, d=0.1, ol=0)


def hd_flow(f, m):
    f.poly(rect(0.95, 1.05), m["dark"], d=0.45, bev=0.05); f.poly(rect(0.85, 0.95), m["white"], dy=-0.3, d=0.3)
    f.poly(rect(0.4, 0.17, 0, 0.62), m["main"], dy=-0.5, d=0.2); f.poly([(0, 0.22), (0.4, -0.05), (0, -0.32), (-0.4, -0.05)], m["gold"], dy=-0.5, d=0.2)
    f.poly(rect(0.4, 0.17, 0, -0.65), m["main"], dy=-0.5, d=0.2); f.line((0, 0.45), (0, 0.22), 0.05, m["dark"], dy=-0.6); f.line((0, -0.32), (0, -0.48), 0.05, m["dark"], dy=-0.6)
    f.line((0.4, -0.05), (0.7, -0.05), 0.05, m["dark"], dy=-0.6); f.line((0.7, -0.05), (0.7, 0.62), 0.05, m["dark"], dy=-0.6)


def hd_pcb(f, m):  # a circuit board
    f.poly(rect(0.98, 0.8), m["pcb"], d=0.4, bev=0.04)
    f.poly(rect(0.32, 0.32, -0.3, 0.05), m["dark"], dy=-0.3, d=0.3); f.circ(0.55, -0.35, 0.18, m["gold"], dy=-0.3, d=0.2)
    for pts in (((-0.9, 0.55), (-0.4, 0.55), (-0.2, 0.3)), ((0.1, 0.05), (0.5, 0.05), (0.7, 0.5)), ((-0.9, -0.5), (-0.3, -0.5), (-0.1, -0.2))): f.poly_line(pts, 0.05, m["gold"], dy=-0.3)
    for x in (-0.55, -0.3, -0.05): f.poly(rect(0.05, 0.12, x, -0.34 + 0.0), m["silver"], dy=-0.4, d=0.1, ol=0)


def hd_tablet(f, m):  # a table on a tablet
    f.poly(rect(0.8, 1.05), m["dark"], d=0.45, bev=0.05); f.poly(rect(0.7, 0.92), m["white"], dy=-0.3, d=0.3)
    f.poly(rect(0.7, 0.14, 0, 0.78), m["main"], dy=-0.5, d=0.2)
    for z in (0.4, 0.0, -0.4, -0.8): f.line((-0.7, z), (0.7, z), 0.04, m["dark"], dy=-0.5)
    f.line((0, 0.9), (0, -0.92), 0.04, m["dark"], dy=-0.5)
    for x, z in ((-0.35, 0.2), (0.35, -0.2), (-0.35, -0.6)): f.circ(x, z, 0.1, m["lime"], dy=-0.6, d=0.2, n=14)


def hd_chart(f, m):  # a bar + trend chart board
    f.poly(rect(0.95, 0.95), m["white"], d=0.4, bev=0.04); f.ring(0, 0, 0.0, 0.0, m["dark"]) if False else None
    for i, h in enumerate((0.35, 0.65, 0.95, 1.4)): f.poly(rect(0.17, h / 2, -0.62 + i * 0.4, -0.85 + h / 2), (m["main"], m["gold"], m["main"], m["gold"])[i], dy=-0.3, d=0.3)
    f.poly_line([(-0.7, -0.2), (-0.2, 0.1), (0.2, 0.0), (0.75, 0.75)], 0.07, m["red"], dy=-0.6)
    f.poly([(0.55, 0.85), (0.95, 0.85), (0.9, 0.45)], m["red"], dy=-0.6, d=0.2, ol=0.006)


def hd_cradle(f, m):  # Newton's cradle
    f.poly(rect(1.05, 0.08, 0, 0.95), m["silver"], d=0.5)
    for sx in (-1, 1): f.poly(rect(0.07, 1.0, sx * 1.0, 0.0), m["silver"], d=0.5); f.poly(rect(0.2, 0.08, sx * 1.0, -1.0), m["dark"], d=0.7)
    for i in range(5):
        x = -0.72 + i * 0.36; ang = 0.0
        if i == 0: x -= 0.28; f.line((-0.72, 0.92), (x, -0.5), 0.02, m["silver"], dy=0.0)
        else: f.line((x, 0.92), (x, -0.55), 0.02, m["silver"], dy=0.0)
        f.ball(x, -0.55 if i else -0.45, 0.2, m["silver"] if i else m["gold"], ol=0.01)


def hd_tubes(f, m):  # a test-tube rack
    f.poly(rect(1.0, 0.14, 0, -0.9), m["wood"], d=0.7); f.poly(rect(1.0, 0.12, 0, 0.0), m["wood"], dy=0.0, d=0.5)
    for i, c in enumerate((m["lime"], m["pink"], m["neon"])):
        x = -0.62 + i * 0.62; f.poly(rect(0.2, 0.9, x, 0.1), m["glass"], d=0.3, bev=0.05)
        f.poly(rect(0.18, 0.4 + 0.1 * (i % 2), x, -0.5 + 0.1 * (i % 2)), c, dy=-0.2, d=0.2, ol=0)
        f.ball(x, 1.1, 0.0, m["white"], ol=0) if False else None


def hd_coins(f, m):  # a stack of gold coins
    k = f.k; H = k.H
    for i in range(6):
        c = f.at(0, -0.9 + i * 0.28, 0.0); H_ = H.ball("hc", c, (0.9 * f.r, 0.45 * f.r, 0.2 * f.r), m["gold"], outline=0.012)
        f.add(H_)
    f.add(H.ball("hc", f.at(0.9, -0.9 + 6 * 0.28 - 0.1, -0.5), (0.9 * f.r, 0.5 * f.r, 0.22 * f.r), m["gold"], outline=0.012, rot=(0.0, 0.0, 0.0))) if False else None
    f.text("$", 0, 0.7, 1.2, m["bronze"], dy=-0.75, ext=0.1)


def hd_ledger(f, m):  # a ledger book
    f.poly(rect(0.92, 1.05), m["green"], d=0.6, bev=0.05); f.poly(rect(0.78, 0.9, 0.06, 0.0), m["paper"], dy=-0.35, d=0.4)
    f.poly(rect(0.1, 1.05, -0.88, 0.0), m["dark"], dy=-0.1, d=0.62)
    for z in (0.6, 0.3, 0.0, -0.3, -0.6): f.line((-0.55, z), (0.7, z), 0.04, m["main"], dy=-0.6)
    f.line((0.3, 0.8), (0.3, -0.8), 0.04, m["crimson"], dy=-0.6)
    f.poly(rect(0.3, 0.17, 0.0, 0.0), m["gold"], dy=-0.8, d=0.1, ol=0.006, ox=0.1, oz=0.78)


def hd_openbook(f, m):
    f.poly([(-1.0, 0.9), (0.0, 0.7), (0.0, -0.9), (-1.0, -0.7)], m["paper"], d=0.4, bev=0.03); f.poly([(0.0, 0.7), (1.0, 0.9), (1.0, -0.7), (0.0, -0.9)], m["paper"], d=0.4, bev=0.03)
    f.poly([(-1.08, 0.98), (0.0, 0.78), (1.08, 0.98), (1.08, 0.86), (0.0, 0.66), (-1.08, 0.86)], m["main"], dy=-0.1, d=0.3, ol=0.0)
    for z in (0.35, 0.05, -0.25, -0.55):
        f.line((-0.85, z + 0.05), (-0.15, z - 0.05), 0.04, m["dark"], dy=-0.25); f.line((0.15, z - 0.05), (0.85, z + 0.05), 0.04, m["dark"], dy=-0.25)


def hd_dict(f, m):  # a dictionary
    f.poly(rect(0.8, 1.05), m["crimson"], d=0.7, bev=0.05); f.poly(rect(0.7, 0.95, 0.12, 0.0), m["paper"], dy=0.3, d=0.5, ol=0.006)
    f.poly(rect(0.12, 1.05, -0.78, 0.0), m["dark"], dy=-0.25, d=0.72); f.poly(rect(0.5, 0.33, 0.0, 0.2), m["gold"], dy=-0.5, d=0.1)
    f.text("A-Z", 0, 0.2, 0.62, m["crimson"], dy=-0.65, ext=0.05)


HELD = dict(brush=hd_brush, magnet=hd_magnet, beaker=hd_beaker, magnifier=hd_magnifier, scroll=hd_scroll, gavel=hd_gavel, globe=hd_globe, laptop=hd_laptop,
            wrench=hd_wrench, micro=hd_micro, paintbrush=hd_paintbrush, planner=hd_planner, flow=hd_flow, pcb=hd_pcb, tablet=hd_tablet, chart=hd_chart,
            cradle=hd_cradle, tubes=hd_tubes, coins=hd_coins, ledger=hd_ledger, openbook=hd_openbook, dict=hd_dict)


def held(k, name, t):
    fn = HELD.get(name)
    if fn is None: return
    s, rb, bc = k.s, k.rb, k.bc
    r = 0.64 * s * {2: 0.8, 3: 1.0, 4: 1.1}.get(t, 1.0)
    p = V(bc.x + rb * 1.08 + r * 0.78, bc.y - 0.62 * s, bc.z + 0.05 * s + r * 0.2)
    fn(F(k, p, r), M(k))


# ================================================================== HATS ======================================================================
def top_z(k): return k.hc.z + k.Rh[2]


def band(k, zu, mat, w=0.07, lift=0.03, k_=1.03):
    R = tuple(x * k_ for x in k.Rh)
    k.ch.addh(k.ring("hband", k.hc, R, zu, lift * k.s, w * k.s, mat, outline=0.012, n=56))


def dome(k, mat, zu=0.4, grow=1.06, zg=1.1, thick=0.075):
    R = (k.Rh[0] * grow, k.Rh[1] * grow, k.Rh[2] * zg)
    k.ch.addh(k.shell("dome", k.hc, R, mat, zr=(zu, 1), thick=thick * k.s, ol=0.02, seg=(56, 28)))
    return R


def hat_van(k, t):  # mũ cánh chuồn: a scholar's hat with two long wings
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    R = dome(k, m["black"], 0.38, 1.04, 1.12 if t >= 3 else 1.0); band(k, 0.38, m["gold"], 0.075, k_=1.04)
    zc = hc.z + R[2] * 0.7; L = u * {1: 1.15, 2: 0.9, 3: 1.25, 4: 1.55}[t]
    for sx in (-1, 1):
        cx = hc.x + sx * (R[0] * 0.55 + L * 0.5)
        A(H.ball("vw", V(cx, hc.y + 0.08 * s, zc), (L * 0.5, 0.24 * u, 0.065 * u), m["black"], rot=(0, -sx * 0.12, 0), outline=0.016))
        A(H.ball("vwg", V(cx - sx * L * 0.1, hc.y + 0.08 * s, zc + 0.01 * s), (L * 0.36, 0.2 * u, 0.075 * u), m["brown"], rot=(0, -sx * 0.12, 0), outline=0.0))
        A(H.ball("vwt", V(hc.x + sx * (R[0] * 0.55 + L - 0.02 * u), hc.y + 0.08 * s, zc + sx * -0.0), (0.2 * u, 0.26 * u, 0.12 * u), m["gold"], outline=0.012))
    if t >= 3:
        pts = [k.surf(hc, R, -90, z, 0.04 * s)[0] for z in [0.44 + i * 0.056 for i in range(10)]]
        A(k.tube("vst", pts, 0.04 * s, m["gold"], outline=0.008, sides=6))
        A(H.ball("vtop", V(hc.x, hc.y, hc.z + R[2] + 0.1 * s), (0.14 * s,) * 3, m["red"], outline=0.012))
    if t >= 4:
        for sx in (-1, 1): A(H.cone("vcr", V(hc.x + sx * 0.35 * u, hc.y + 0.0, hc.z + R[2] + 0.28 * s), 0.1 * s, 0.4 * s, m["gold"], (0, sx * 0.4, 0), outline=0.01))
    k.hat_top = hc.z + R[2] + 0.28 * s


def hat_su(k, t):  # a gold crown with a fan of long feathers (Lac Viet / Dong Son)
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    band(k, 0.5, m["gold"], 0.1, k_=1.04); band(k, 0.4, m["red"], 0.06, k_=1.03)
    top = V(hc.x, hc.y - 0.05 * s, hc.z + Rh[2] * 0.82)
    n = {1: 5, 2: 5, 3: 7, 4: 9}[t]; Lh = u * {1: 1.2, 2: 1.3, 3: 1.75, 4: 2.0}[t]
    for i in range(n):
        a = (i - (n - 1) / 2) / ((n - 1) / 2) * 1.0; L = Lh * (1.0 - 0.3 * abs(a)); ang = -a * 0.85
        f = F(k, top + V(math.sin(-ang) * 0.0, 0, 0), 1.0, A)
        f.poly(leaf_pts(L, 0.2 * u * (1.2 if i % 2 == 0 else 1.0)), (m["red"], m["gold"])[i % 2], rot=ang, ox=a * 0.5 * u, oz=-0.1 * u, d=0.08 * u * 0.5, bev=0.0)
    A(H.ball("sdisc", V(hc.x, hc.y - Rh[1] * 0.98, hc.z + Rh[2] * 0.5), (0.2 * u, 0.1 * u, 0.2 * u), m["bronze"], outline=0.012))
    k.hat_top = top.z + Lh * 0.9


def hat_dia(k, t):  # an explorer's pith helmet
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    R = dome(k, m["khaki"], 0.28, 1.08, 1.12)
    A(H.ball("dbrim", V(hc.x, hc.y - 0.05 * s, hc.z + Rh[2] * 0.3), (Rh[0] * 1.62, Rh[1] * 1.5, 0.08 * u), m["khaki"], rot=(0.06, 0, 0), outline=0.018))
    band(k, 0.34, m["sky"], 0.085, k_=1.08)
    A(H.ball("dknob", V(hc.x, hc.y, hc.z + R[2] + 0.04 * s), (0.12 * s,) * 3, m["brown"], outline=0.01))
    f = F(k, V(hc.x, hc.y - R[1] * 0.96, hc.z + Rh[2] * 0.5), 0.2 * u, A); em_compass(f, m)
    if t >= 3:
        for sx in (-1, 1): A(k.tube("dflag", [V(hc.x + sx * 0.5 * u, hc.y + 0.1 * s, hc.z + Rh[2] * 0.95), V(hc.x + sx * 0.7 * u, hc.y + 0.1 * s, hc.z + R[2] + 0.5 * s)], 0.025 * s, m["brown"], outline=0.0, sides=5)) if False else None
    k.hat_top = hc.z + R[2] + 0.1 * s


def hat_cd(k, t):  # a judge's white curly wig
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    R = dome(k, m["white"], -0.1, 1.12, 1.16, 0.09)
    for sx in (-1, 1):
        for i, (dz, rr) in enumerate(((0.35, 0.3), (0.0, 0.32), (-0.35, 0.28))):
            A(H.ball("curl", V(hc.x + sx * Rh[0] * 1.02, hc.y + 0.1 * s, hc.z + dz * u), (rr * u * 0.95, rr * u * 0.95, rr * u * 0.7), m["white"], outline=0.016))
    for i in range(5):
        a = math.radians(-150 + i * 30); A(H.ball("curl", V(hc.x + math.cos(a) * Rh[0] * 1.0, hc.y + math.sin(a) * Rh[1] * 1.0 - 0.03 * s, hc.z + Rh[2] * 0.62), (0.2 * u, 0.2 * u, 0.17 * u), m["white"], outline=0.014))
    if t >= 3:
        A(H.ball("curltop", V(hc.x, hc.y, hc.z + R[2] * 0.98), (0.34 * u, 0.34 * u, 0.22 * u), m["white"], outline=0.014))
    if t >= 4:
        A(k.ring("wigband", hc, tuple(x * 1.14 for x in Rh), 0.6, 0.0, 0.05 * s, m["gold"], outline=0.01, n=48))
    k.hat_top = hc.z + R[2] + 0.1 * s


def hat_tin(k, t):  # a hoodie hood with headphones
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    R = (Rh[0] * 1.14, Rh[1] * 1.14, Rh[2] * 1.18)
    A(k.shell("hood", hc, R, m["main"], zr=(-0.55, 1), back=-0.2, thick=0.08 * s, ol=0.02, seg=(56, 28)))
    for sx in (-1, 1):
        A(H.ball("cup", V(hc.x + sx * (Rh[0] * 1.1), hc.y - 0.02 * s, hc.z + 0.0), (0.2 * u, 0.32 * u, 0.34 * u), m["neon"], outline=0.016))
        A(H.ball("cup2", V(hc.x + sx * (Rh[0] * 1.2), hc.y - 0.02 * s, hc.z + 0.0), (0.1 * u, 0.24 * u, 0.26 * u), m["dark"], outline=0.012))
        A(k.tube("cord", [V(hc.x + sx * 0.2 * u, hc.y - Rh[1] * 0.96, hc.z - Rh[2] * 0.62), V(hc.x + sx * 0.22 * u, hc.y - Rh[1] * 1.0, hc.z - Rh[2] * 0.95)], 0.025 * s, m["neon"], outline=0.0, sides=5))
    arcp = [V(hc.x + math.cos(math.radians(a)) * Rh[0] * 1.22, hc.y, hc.z + math.sin(math.radians(a)) * Rh[2] * 1.26) for a in range(10, 171, 10)]
    A(k.tube("hband", arcp, 0.05 * s, m["neon"], outline=0.012, sides=6))
    if t >= 3:
        for i, (px, pz) in enumerate(((-0.35, 1.02), (0.0, 1.12), (0.35, 1.02))): A(H.rbox("pix", V(hc.x + px * u, hc.y - 0.2 * s, hc.z + pz * u * 0.95 + 0.0), (0.12 * u,) * 3, m["lime"], outline=0.008))
    k.hat_top = hc.z + R[2] + 0.15 * s


def hat_cn(k, t):  # an orange hard hat with a lamp
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    R = dome(k, m["main"], 0.3, 1.08, 1.12)
    A(H.ball("hvis", V(hc.x, hc.y - Rh[1] * 0.97, hc.z + Rh[2] * 0.34), (0.78 * u, 0.52 * u, 0.08 * u), m["main"], rot=(0.15, 0, 0), outline=0.018))
    pts = [k.surf(hc, R, -90, z, 0.04 * s)[0] for z in [0.3 + i * 0.07 for i in range(11)]] + [V(hc.x, hc.y + 0.0, hc.z + R[2] + 0.04 * s)] + [V(hc.x, hc.y + 0.5 * u + i * 0.1 * u, hc.z + R[2] * 0.92 - i * 0.12 * u) for i in range(3)]
    A(k.tube("ridge", pts, 0.1 * s, m["yellow"], outline=0.012, sides=8))
    for sx in (-1, 1): A(k.tube("ridge2", [k.surf(hc, R, -90 + sx * 22, z, 0.03 * s)[0] for z in [0.34 + i * 0.09 for i in range(7)]], 0.05 * s, m["deep"], outline=0.008, sides=6))
    A(H.ball("lamp", V(hc.x, hc.y - R[1] * 0.97, hc.z + Rh[2] * 0.7), (0.17 * u, 0.1 * u, 0.15 * u), m["white"], outline=0.012))
    A(H.ball("lamp2", V(hc.x, hc.y - R[1] * 1.02, hc.z + Rh[2] * 0.7), (0.1 * u, 0.06 * u, 0.09 * u), m["yellow"], outline=0.0))
    if t >= 3:
        f = F(k, V(hc.x, hc.y - R[1] * 0.99, hc.z + Rh[2] * 1.04), 0.2 * u, A); em_gear(f, m)
    k.hat_top = hc.z + R[2] + 0.12 * s


def hat_nghe(k, t):  # a giant paint palette tilted on the head
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    base = V(hc.x + 0.08 * u, hc.y - 0.05 * s, hc.z + Rh[2] + 0.5 * u * (1.0 if t >= 3 else 0.8))
    R = 0.95 * u * (1.0 if t >= 2 else 0.8)
    f = F(k, base, R, A)
    ang = 0.28
    outline = [(math.cos(a) * 1.0, math.sin(a) * 0.72) for a in [i * 2 * math.pi / 40 for i in range(40)]]
    outline = [(x, z) for x, z in outline if not (x > 0.35 and z < -0.35)]
    notch = [(0.25, -0.45), (0.5, -0.78 + 0.18), (0.75, -0.52)]
    f.poly(outline, m["wood"], d=0.2, rot=ang, ol=0.016)
    c, sn = math.cos(ang), math.sin(ang)
    def P2(x, z): return (x * c - z * sn, x * sn + z * c)
    x, z = P2(-0.55, -0.12); f.circ(x, z, 0.14, m["dark"], dy=-0.3, d=0.15, n=16)
    for i, (cx, cz, col) in enumerate(((-0.35, 0.38, m["red"]), (0.0, 0.5, m["yellow"]), (0.4, 0.36, m["blue"]), (0.62, 0.02, m["green"]), (-0.05, -0.12, m["white"]))):
        x, z = P2(cx, cz); f.ball(x, z, 0.19, col, dy=-0.4, sy=0.3, ol=0.01)
    if t >= 2:
        A(k.tube("brush", [V(base.x + 0.75 * u, base.y + 0.1, base.z - 0.5 * u), V(base.x + 1.05 * u, base.y + 0.1, base.z + 0.75 * u)], 0.07 * s, m["pink"], outline=0.01, sides=6))
        A(k.tube("brushtip", [V(base.x + 1.04 * u, base.y + 0.1, base.z + 0.72 * u), V(base.x + 1.1 * u, base.y + 0.1, base.z + 1.12 * u)], lambda tt: 0.12 * s * (1 - tt * 0.9), m["main"], outline=0.01, sides=8))
    k.hat_top = base.z + 0.95 * u


def hat_kynang(k, t):  # an alarm clock with two bells
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    rr = 0.78 * u * (1.0 if t >= 3 else 0.85); c = V(hc.x, hc.y, hc.z + Rh[2] + rr * 0.78)
    body = H.cyl("clk", c, rr, 0.5 * u, m["main"], outline=0.02); body.rotation_euler = (math.radians(90), 0, 0); A(body)
    face = H.cyl("clkf", c + V(0, -0.2 * u, 0), rr * 0.86, 0.1 * u, m["white"], outline=0.012); face.rotation_euler = (math.radians(90), 0, 0); A(face)
    A(H.cyl.__call__("clkr", c + V(0, -0.18 * u, 0), rr * 0.9, 0.0, m["main"], outline=0.0)) if False else None
    for i in range(12):
        a = i * math.pi / 6; ln = 0.12 if i % 3 == 0 else 0.07
        A(H.rbox("tk", c + V(math.sin(a) * rr * 0.72, -0.27 * u, math.cos(a) * rr * 0.72), (0.05 * u, 0.04 * u, ln * u), m["dark"], rot=(0, -a, 0), outline=0.0))
    A(H.rbox("hh", c + V(0.0, -0.3 * u, 0.2 * rr), (0.06 * u, 0.04 * u, 0.4 * rr), m["dark"], outline=0.0)); A(H.rbox("mh", c + V(0.2 * rr, -0.3 * u, -0.05 * rr), (0.34 * rr, 0.04 * u, 0.06 * u), m["red"], outline=0.0))
    A(H.ball("hub", c + V(0, -0.32 * u, 0), (0.07 * u,) * 3, m["dark"], outline=0.0))
    for sx in (-1, 1):
        A(H.ball("bell", c + V(sx * rr * 0.62, 0, rr * 0.86), (0.3 * u, 0.3 * u, 0.24 * u), m["gold"], rot=(0, sx * 0.35, 0), outline=0.016))
        A(H.ball("bellk", c + V(sx * rr * 0.62, 0, rr * 0.86 + 0.2 * u), (0.07 * u,) * 3, m["gold"], outline=0.008))
        A(k.tube("clegs", [c + V(sx * rr * 0.58, 0, -rr * 0.8), c + V(sx * rr * 0.75, 0, -rr * 1.0)], 0.06 * u, m["dark"], outline=0.008, sides=6))
    A(k.tube("hmr", [c + V(0, 0, rr * 0.95), c + V(0, 0, rr * 1.14)], 0.03 * u, m["dark"], outline=0.0, sides=5))
    k.hat_top = c.z + rr * 1.15


def hat_li(k, t):  # a crown of three lightning bolts
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    band(k, 0.5, m["yellow"], 0.085, k_=1.04); band(k, 0.4, m["dark"], 0.05, k_=1.04)
    base = V(hc.x, hc.y - 0.03 * s, hc.z + Rh[2] + 0.2 * u)
    big = {1: 1.15, 2: 0.9, 3: 1.2, 4: 1.45}[t] * u
    f = F(k, base + V(0, 0, big * 0.88), big, A); f.poly(BOLT, m["yellow"], d=0.28, bev=0.0)
    if t >= 2:
        for sx in (-1, 1):
            f2 = F(k, base + V(sx * 0.72 * u, 0.04, big * 0.42), big * 0.52, A); f2.poly(BOLT, m["yellow"] if t < 4 else m["orange"], d=0.28, bev=0.0, rot=-sx * 0.55)
    if t >= 3:
        for sx in (-1, 1): f3 = F(k, base + V(sx * 1.05 * u, 0.0, big * 0.1), big * 0.26, A); f3.poly(BOLT, m["white"], d=0.3, bev=0.0, rot=-sx * 0.9)
    k.hat_top = base.z + big * 1.9


def hat_hoa(k, t):  # a bubbling flask worn as a hat, safety goggles on the forehead
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    base = V(hc.x, hc.y, hc.z + Rh[2] * 0.82)
    sc = u * {1: 1.15, 2: 0.9, 3: 1.0, 4: 1.12}[t]
    prof = [(0.7 * sc, 0.0), (0.7 * sc, 0.08 * sc), (0.55 * sc, 0.4 * sc), (0.3 * sc, 0.74 * sc), (0.2 * sc, 0.9 * sc), (0.2 * sc, 1.45 * sc), (0.27 * sc, 1.55 * sc)]
    A(k.lathe("flask", base, prof, m["purple"], k=1.0))
    A(k.ring("fliq", base, (0.5 * sc, 0.5 * sc, 1.0), 0.0, 0.0, 0.01, m["lime"], n=4)) if False else None
    A(H.ball("liq", base + V(0, -0.02, 0.28 * sc), (0.52 * sc, 0.5 * sc, 0.3 * sc), m["lime"], outline=0.0))
    A(H.cyl("cork", base + V(0, 0, 1.6 * sc), 0.19 * sc, 0.14 * sc, m["wood"], outline=0.012))
    A(H.ball("hlt", base + V(-0.16 * sc, -0.28 * sc, 0.5 * sc), (0.07 * sc, 0.03 * sc, 0.3 * sc), m["white"], rot=(0, 0.45, 0), outline=0.0))
    for i, (dx, dz, rr) in enumerate(((0.05, 1.95, 0.13), (-0.14, 2.2, 0.1), (0.12, 2.45, 0.08), (-0.02, 2.65, 0.06))):
        if i < 2 + (1 if t >= 3 else 0) + (1 if t >= 4 else 0): A(H.ball("bub", base + V(dx * sc, 0, dz * sc * 0.86), (rr * sc,) * 3, m["lime"] if i % 2 == 0 else m["white"], outline=0.01))
    band(k, 0.5, m["dark"], 0.06, k_=1.04)
    for sx in (-1, 1):
        d = V(0.3 * sx, -0.94, 0.0).normalized(); c = hc + V(d.x * Rh[0], d.y * Rh[1], 0.5 * Rh[2]) * 1.04
        A(H.torus("gog", c, 0.24 * s, 0.06 * s, m["gold"], (math.radians(90), 0, math.atan2(d.x, -d.y)), outline=0.012))
        A(H.ball("lens", c + d * 0.01, (0.2 * s, 0.03 * s, 0.2 * s), m["neon"], rot=(0, 0, math.atan2(d.x, -d.y)), outline=0.0))
    k.hat_top = base.z + 2.5 * sc if t >= 3 else base.z + 1.9 * sc


def hat_sinh(k, t):  # a sprouting plant crown: big leaves on a vine headband
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    band(k, 0.5, m["brown"], 0.07, k_=1.04)
    for i in range(7 if t >= 3 else 5):
        a = math.radians(-160 + i * (140 / (6 if t >= 3 else 4)))
        p = k.surf(hc, tuple(x * 1.04 for x in Rh), -90 + (i - 3) * 22, 0.5, 0.06 * s)[0]
        A(H.ball("bl", p, (0.14 * u, 0.06 * u, 0.1 * u), m["green"], rot=(0, 0, (i - 3) * 0.4), outline=0.008))
    base = V(hc.x, hc.y - 0.02 * s, hc.z + Rh[2] * 0.9)
    A(k.tube("stem", [base, base + V(0.03 * u, 0, 0.35 * u), base + V(0.0, 0, 0.62 * u)], 0.06 * u, m["green"], outline=0.01, sides=6))
    L = u * {1: 1.15, 2: 1.05, 3: 1.5, 4: 1.75}[t]
    f = F(k, base + V(0, 0, 0.55 * u), 1.0, A)
    f.poly(leaf_pts(L, 0.45 * u), m["green"], rot=0.65, d=0.1 * u, bev=0.0, ox=0.02 * u); f.poly(leaf_pts(L, 0.45 * u), m["lime"], rot=-0.65, d=0.1 * u, bev=0.0, ox=-0.02 * u)
    if t >= 3: f.poly(leaf_pts(L * 1.12, 0.4 * u), m["green"], rot=0.0, d=0.1 * u, bev=0.0, dy=0.04 * u)
    if t >= 4:
        for sx in (-1, 1): f.poly(leaf_pts(L * 0.7, 0.3 * u), m["lime"], rot=sx * 1.25, d=0.1 * u, bev=0.0, oz=-0.1 * u)
    k.hat_top = base.z + 0.55 * u + L * 0.82


def hat_khoahoc(k, t):  # wild white mad-scientist hair, big goggles on the forehead
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    n = {1: 7, 2: 7, 3: 9, 4: 11}[t]
    for i in range(n):
        a = math.radians(-165 + i * (150 / (n - 1)))
        p = hc + V(math.cos(a) * Rh[0] * 0.85, math.sin(a) * Rh[1] * 0.7 - 0.05 * s, Rh[2] * 0.78)
        d = V(math.cos(a) * 0.9, 0, 0.7 + abs(math.sin(a)) * 0.3).normalized()
        L = 0.62 * u * (1.2 if i % 2 == 0 else 0.95) * (1.15 if t >= 3 else 1.0)
        A(H.cone("hair", p + d * L * 0.4, 0.16 * u, L, m["white"], (math.acos(max(-1, min(1, d.z))) * (1 if d.x >= 0 else -1) * 0 + 0, 0, 0) if False else (0, math.atan2(d.x, d.z), 0), outline=0.014))
    band(k, 0.55, m["lime"], 0.075, k_=1.03)
    for sx in (-1, 1):
        d = V(0.3 * sx, -0.94, 0.0).normalized(); c = hc + V(d.x * Rh[0], d.y * Rh[1], 0.6 * Rh[2]) * 1.05; yaw = math.atan2(d.x, -d.y)
        A(H.torus("gog", c, 0.3 * s, 0.075 * s, m["gold"], (math.radians(90), 0, yaw), outline=0.014))
        A(H.ball("lens", c + d * 0.01, (0.25 * s, 0.04 * s, 0.25 * s), m["neon"], rot=(0, 0, yaw), outline=0.0))
        A(H.ball("lg", c + d * 0.05 + V(-0.08 * s * sx, 0, 0.1 * s), (0.07 * s, 0.015 * s, 0.05 * s), m["white"], rot=(0, 0, yaw), outline=0.0))
    k.hat_top = hc.z + Rh[2] * 0.78 + 0.62 * u * 1.4


def hat_khmt(k, t):  # braces { } floating over a headband with binary cubes
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    band(k, 0.5, m["main"], 0.085, k_=1.04); band(k, 0.42, m["white"], 0.04, k_=1.04)
    base = V(hc.x, hc.y - 0.03 * s, hc.z + Rh[2] + 0.62 * u * (1.0 if t >= 3 else 0.82))
    sz = 1.45 * u * {1: 1.15, 2: 0.9, 3: 1.0, 4: 1.15}[t]
    for sx, ch_ in ((-1, "{"), (1, "}")):
        cu = bpy.data.curves.new("br", "FONT"); cu.body = ch_; cu.align_x = "CENTER"; cu.align_y = "CENTER"; cu.size = sz; cu.extrude = 0.14 * sz; cu.bevel_depth = 0.012 * sz
        cu.materials.append(m["main"]); o = H.link(bpy.data.objects.new("br", cu)); o.location = base + V(sx * 0.62 * u, 0, 0); o.rotation_euler = (math.radians(90), 0, 0); A(o)
    f = F(k, base, 1.0, A)
    for i, (dx, dz, c) in enumerate(((-0.12, 0.05, 0), (0.1, -0.25, 1), (0.02, 0.38, 1))):
        if i < 2 + (1 if t >= 3 else 0):
            f.text("1" if c else "0", dx * u, dz * u + 0.0, 0.55 * u, m["lime"] if c else m["neon"], ext=0.1)
    k.hat_top = base.z + sz * 0.62


def hat_ktmt(k, t):  # a silver robot helmet with an antenna and ear bolts
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    R = dome(k, m["silver"], 0.32, 1.08, 1.12)
    band(k, 0.32, m["dark"], 0.075, k_=1.08)
    f = F(k, V(hc.x, hc.y - R[1] * 0.99, hc.z + Rh[2] * 0.74), 0.46 * u, A); em_chip(f, m)
    A(k.tube("ant", [V(hc.x, hc.y, hc.z + R[2] - 0.05 * s), V(hc.x, hc.y, hc.z + R[2] + 0.55 * u)], 0.04 * u, m["dark"], outline=0.008, sides=6))
    A(H.ball("antb", V(hc.x, hc.y, hc.z + R[2] + 0.66 * u), (0.14 * u,) * 3, m["crimson"], outline=0.012))
    for sx in (-1, 1):
        A(H.ball("ear", V(hc.x + sx * Rh[0] * 1.12, hc.y - 0.02 * s, hc.z + Rh[2] * 0.3), (0.14 * u, 0.3 * u, 0.3 * u), m["gold"], outline=0.014))
        A(H.ball("ear2", V(hc.x + sx * Rh[0] * 1.2, hc.y - 0.02 * s, hc.z + Rh[2] * 0.3), (0.06 * u, 0.2 * u, 0.2 * u), m["dark"], outline=0.0))
    if t >= 3:
        for sx in (-1, 1): A(k.tube("ant2", [V(hc.x + sx * 0.42 * u, hc.y, hc.z + R[2] * 0.9), V(hc.x + sx * 0.7 * u, hc.y, hc.z + R[2] + 0.2 * u)], 0.03 * u, m["dark"], outline=0.006, sides=5)); A(H.ball("ant2b", V(hc.x + sx * 0.72 * u, hc.y, hc.z + R[2] + 0.26 * u), (0.08 * u,) * 3, m["neon"], outline=0.008))
    k.hat_top = hc.z + R[2] + 0.8 * u


def hat_httt(k, t):  # a stack of database disks with status lights
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    n = {1: 2, 2: 2, 3: 3, 4: 4}[t]; rr = 0.68 * u; h = 0.34 * u
    for i in range(n):
        z = hc.z + Rh[2] * 0.82 + h * 0.5 + i * h * 1.0
        A(H.cyl("dsk", V(hc.x, hc.y, z), rr, h * 0.95, m["main"], outline=0.02))
        A(H.torus("dskr", V(hc.x, hc.y, z + h * 0.46), rr, 0.035 * u, m["white"], (0, 0, 0), outline=0.0))
        A(H.torus("dskb", V(hc.x, hc.y, z - h * 0.46), rr, 0.035 * u, m["dark"], (0, 0, 0), outline=0.0))
        for dx in (-0.3, -0.12): A(H.ball("led", V(hc.x + dx * u * 1.1, hc.y - rr * 0.97, z + 0.02), (0.045 * u,) * 3, m["lime"] if i % 2 == 0 else m["yellow"], outline=0.0))
        A(H.rbox("slot", V(hc.x + 0.22 * u, hc.y - rr * 0.99, z), (0.34 * u, 0.04 * u, 0.06 * u), m["dark"], outline=0.0))
    k.hat_top = hc.z + Rh[2] * 0.82 + h * (n + 0.4)


def hat_khdl(k, t):  # rising bar chart with a trend arrow
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    band(k, 0.5, m["main"], 0.085, k_=1.04)
    n = {1: 3, 2: 3, 3: 4, 4: 5}[t]; w = 0.26 * u; base = hc.z + Rh[2] * 0.85
    for i in range(n):
        h = (0.5 + i * 0.4) * u * (1.0 if t >= 2 else 0.8)
        A(H.rbox("bar", V(hc.x + (i - (n - 1) / 2) * 0.5 * u, hc.y - 0.05 * s, base + h * 0.5), (w, 0.3 * u, h), (m["main"], m["gold"], m["white"], m["purple"], m["gold"])[i % 5], outline=0.016))
    pts = [V(hc.x + (i - (n - 1) / 2) * 0.5 * u, hc.y - 0.22 * u, base + (0.5 + i * 0.4) * u * (1.0 if t >= 2 else 0.8) + 0.22 * u) for i in range(n)]
    A(k.tube("trend", pts, 0.045 * u, m["red"], outline=0.008, sides=6)); A(H.cone("arw", pts[-1] + V(0.1 * u, 0, 0.1 * u), 0.12 * u, 0.3 * u, m["red"], (0, math.radians(40), 0), outline=0.008))
    k.hat_top = base + (0.5 + (n - 1) * 0.4) * u + 0.3 * u


def hat_vatli(k, t):  # an atom: a nucleus with three orbiting rings
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    band(k, 0.5, m["main"], 0.085, k_=1.04)
    c = V(hc.x, hc.y, hc.z + Rh[2] + 0.82 * u * (1.0 if t >= 3 else 0.85)); R = 0.95 * u * {1: 1.15, 2: 0.9, 3: 1.0, 4: 1.12}[t]
    for i, rz in enumerate((0, 60, -60)):
        c_, sn = math.cos(math.radians(rz)), math.sin(math.radians(rz))
        pts = [V(math.cos(a) * R, 0.0, math.sin(a) * R * 0.34) for a in [i2 * 2 * math.pi / 48 for i2 in range(48)]]
        pts = [c + V(p.x * c_ - p.z * sn, 0.0, p.x * sn + p.z * c_) for p in pts]
        A(k.tube("orbr", pts, 0.05 * u, m["neon"] if i != 1 else m["white"], closed=True, outline=0.008, sides=6))
        a = math.radians(40 + i * 130)
        A(H.ball("elec", c + V((math.cos(a) * R) * c_ - (math.sin(a) * R * 0.34) * sn, 0, (math.cos(a) * R) * sn + (math.sin(a) * R * 0.34) * c_), (0.1 * u,) * 3, m["dark"] if i else m["yellow"], outline=0.01))
    A(H.ball("nuc", c, (0.24 * u,) * 3, m["main"], outline=0.014)); A(H.ball("nuc2", c + V(0.1 * u, -0.06 * u, 0.06 * u), (0.14 * u,) * 3, m["gold"], outline=0.01))
    k.hat_top = c.z + R * 0.9


def hat_hoahoc(k, t):  # a benzene ring molecule model
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    band(k, 0.5, m["main"], 0.08, k_=1.04)
    c = V(hc.x, hc.y, hc.z + Rh[2] + 0.88 * u * (1.0 if t >= 3 else 0.85)); R = 0.72 * u * {1: 1.15, 2: 0.9, 3: 1.0, 4: 1.12}[t]
    pts = [c + V(math.cos(math.radians(90 + 60 * i)) * R, 0, math.sin(math.radians(90 + 60 * i)) * R) for i in range(6)]
    for i in range(6): A(k.tube("bnd", [pts[i], pts[(i + 1) % 6]], 0.06 * u, m["white"], outline=0.01, sides=6))
    A(k.tube("bnd2", [c + V(math.cos(a) * R * 0.55, 0.05, math.sin(a) * R * 0.55) for a in [i * 2 * math.pi / 32 for i in range(32)]], 0.03 * u, m["pink"], closed=True, outline=0.0, sides=5))
    for i, p in enumerate(pts): A(H.ball("atm", p, (0.2 * u if i % 2 == 0 else 0.16 * u,) * 3, m["main"] if i % 2 == 0 else m["pink"] if t >= 3 else m["white"], outline=0.014))
    for i in (0, 3) if t >= 3 else ():
        d = (pts[i] - c).normalized(); A(k.tube("sub", [pts[i], pts[i] + d * 0.4 * u], 0.05 * u, m["white"], outline=0.008, sides=6)); A(H.ball("subb", pts[i] + d * 0.5 * u, (0.12 * u,) * 3, m["white"], outline=0.01))
    k.hat_top = c.z + R + 0.5 * u


def hat_kinhte(k, t):  # a tall black top hat with a gold coin buckle
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    z0 = hc.z + Rh[2] * 0.58; hh = 1.05 * u * {1: 1.15, 2: 0.85, 3: 1.0, 4: 1.15}[t]
    A(H.cyl("brimt", V(hc.x, hc.y, z0), 1.05 * u, 0.09 * u, m["black"], outline=0.02))
    prof = [(0.7 * u, 0.0), (0.68 * u, hh * 0.5), (0.7 * u, hh)]
    A(k.lathe("crownt", V(hc.x, hc.y, z0), prof, m["black"], k=1.0))
    A(H.torus("bandt", V(hc.x, hc.y, z0 + hh * 0.22), 0.7 * u, 0.1 * u, m["gold"], (0, 0, 0), outline=0.012))
    f = F(k, V(hc.x, hc.y - 0.72 * u, z0 + hh * 0.22), 0.2 * u, A); em_coin(f, m)
    if t >= 3:
        for sx in (-1, 1): A(H.ball("cn", V(hc.x + sx * 0.5 * u, hc.y - 0.5 * u, z0 + hh + 0.12 * u), (0.12 * u, 0.04 * u, 0.12 * u), m["gold"], outline=0.01))
    k.hat_top = z0 + hh + 0.1 * u


def hat_ketoan(k, t):  # an accountant's green eyeshade with a pencil
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    band(k, 0.52, m["green"], 0.12, k_=1.04); band(k, 0.62, m["green"], 0.06, k_=1.02)
    A(H.ball("visor", V(hc.x, hc.y - Rh[1] * 0.92, hc.z + Rh[2] * 0.5), (0.95 * u, 0.62 * u, 0.07 * u), m["green"], rot=(0.35, 0, 0), outline=0.018))
    A(H.ball("visor2", V(hc.x, hc.y - Rh[1] * 0.92, hc.z + Rh[2] * 0.52), (0.82 * u, 0.5 * u, 0.04 * u), m["lime"], rot=(0.35, 0, 0), outline=0.0))
    top = hc + V(0, 0.0, Rh[2] * 0.96)
    if t >= 2: A(H.ball("domet", top + V(0, 0.02 * s, 0.02 * s), (Rh[0] * 0.72, Rh[1] * 0.7, 0.2 * u), m["main"], outline=0.018))
    A(k.tube("pen", [V(hc.x + 0.55 * u, hc.y + 0.05, hc.z + Rh[2] * 0.62), V(hc.x + 0.95 * u, hc.y + 0.05, hc.z + Rh[2] * 1.38)], 0.06 * u, m["yellow"], outline=0.01, sides=6))
    A(k.tube("pen2", [V(hc.x + 0.53 * u, hc.y + 0.05, hc.z + Rh[2] * 0.58), V(hc.x + 0.57 * u, hc.y + 0.05, hc.z + Rh[2] * 0.66)], 0.06 * u, m["dark"], outline=0.008, sides=6))
    A(k.tube("pen3", [V(hc.x + 0.93 * u, hc.y + 0.05, hc.z + Rh[2] * 1.34), V(hc.x + 0.97 * u, hc.y + 0.05, hc.z + Rh[2] * 1.44)], 0.06 * u, m["pink"], outline=0.008, sides=6))
    if t >= 3:
        f = F(k, V(hc.x - 0.3 * u, hc.y - 0.1 * u, hc.z + Rh[2] + 0.5 * u), 0.46 * u, A); em_calc(f, m)
        f.k.tube  # noqa
    k.hat_top = hc.z + Rh[2] + (1.0 * u if t >= 3 else 0.3 * u)


def hat_daicuong(k, t):  # a mortarboard with a long gold tassel
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    zb = hc.z + Rh[2] * 0.7
    A(H.cyl("capb", V(hc.x, hc.y, zb), 0.62 * u, 0.4 * u, m["dark"], outline=0.02))
    bd = {1: 1.35, 2: 1.45, 3: 1.6, 4: 1.75}[t] * u
    A(H.rbox("board", V(hc.x, hc.y, zb + 0.24 * u), (bd, bd, 0.08 * u), m["dark"], rot=(0, 0, math.radians(45)), outline=0.018))
    A(H.ball("bdtop", V(hc.x, hc.y, zb + 0.31 * u), (0.1 * u,) * 3, m["gold"], outline=0.01))
    e = V(hc.x + 0.45 * u, hc.y - 0.45 * u, zb + 0.28 * u)
    A(k.tube("tas", [V(hc.x, hc.y, zb + 0.3 * u), e + V(0.3 * u, -0.2 * u, 0.0), e + V(0.6 * u, -0.2 * u, -0.5 * u)], 0.035 * u, m["gold"], outline=0.006, sides=5))
    A(H.cone("tasend", e + V(0.62 * u, -0.2 * u, -0.78 * u), 0.14 * u, 0.4 * u, m["gold"], (math.pi, 0, 0), outline=0.01))
    if t >= 3:
        for i in range(4): A(H.rbox("edge", V(hc.x, hc.y, zb + 0.21 * u), (bd * 1.02, bd * 1.02, 0.03 * u), m["gold"], rot=(0, 0, math.radians(45)), outline=0.0)) if i == 0 else None
    k.hat_top = zb + 0.45 * u


def hat_anh(k, t):  # a headset and a big speech bubble
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    arcp = [V(hc.x + math.cos(math.radians(a)) * Rh[0] * 1.14, hc.y, hc.z + math.sin(math.radians(a)) * Rh[2] * 1.12) for a in range(8, 173, 8)]
    A(k.tube("hsb", arcp, 0.055 * s, m["main"], outline=0.012, sides=6))
    for sx in (-1, 1):
        A(H.ball("cup", V(hc.x + sx * Rh[0] * 1.1, hc.y - 0.02 * s, hc.z + 0.04 * s), (0.2 * u, 0.32 * u, 0.34 * u), m["main"], outline=0.016))
        A(H.ball("cup2", V(hc.x + sx * Rh[0] * 1.2, hc.y - 0.02 * s, hc.z + 0.04 * s), (0.1 * u, 0.24 * u, 0.26 * u), m["white"], outline=0.012))
    A(k.tube("mic", [V(hc.x - Rh[0] * 1.14, hc.y - 0.1 * s, hc.z - 0.1 * s), V(hc.x - 0.5 * u, hc.y - Rh[1] * 0.9, hc.z - 0.5 * u), V(hc.x - 0.18 * u, hc.y - Rh[1] * 1.0, hc.z - 0.52 * u)], 0.03 * s, m["dark"], outline=0.006, sides=5))
    A(H.ball("micb", V(hc.x - 0.16 * u, hc.y - Rh[1] * 1.02, hc.z - 0.52 * u), (0.07 * u,) * 3, m["dark"], outline=0.006))
    base = V(hc.x + 0.05 * u, hc.y - 0.08 * s, hc.z + Rh[2] + 0.62 * u * (1.0 if t >= 3 else 0.85)); w = 1.0 * u * {1: 1.15, 2: 0.9, 3: 1.0, 4: 1.1}[t]
    f = F(k, base, w, A)
    pts = rect(1.05, 0.62); f.poly(pts, m["white"], d=0.3, bev=0.12, ol=0.016)
    f.poly([(-0.55, -0.55), (-0.1, -0.55), (-0.62, -1.0)], m["white"], d=0.3, bev=0.0, ol=0.016, dy=0.02)
    f.text("Hello" if t >= 3 else "Hi!", 0, 0.0, 0.62 if t >= 3 else 0.8, m["crimson"], dy=-0.25, ext=0.06)
    k.hat_top = base.z + 0.65 * w


HATS = dict(van=hat_van, su=hat_su, dia=hat_dia, cd=hat_cd, tin=hat_tin, cn=hat_cn, nghethuat=hat_nghe, kynang=hat_kynang, li=hat_li, hoa=hat_hoa, sinh=hat_sinh,
            khoahoc=hat_khoahoc, khmt=hat_khmt, ktmt=hat_ktmt, httt=hat_httt, khdl=hat_khdl, vatli=hat_vatli, hoahoc=hat_hoahoc, kinhte=hat_kinhte, ketoan=hat_ketoan,
            daicuong=hat_daicuong, anh=hat_anh)


# ================================================================== ROUND 2: redesigns after the blind test (toan, khoahoc, cd, van, ketoan, daicuong) =====================
def sym(f, kind, cx, cz, sz, mat, dy=-0.25):
    d = 0.3
    if kind == "+":
        f.poly(rect(sz, sz * 0.27, cx, cz), mat, dy, d); f.poly(rect(sz * 0.27, sz, cx, cz), mat, dy - 0.01, d, ol=0.0)
    elif kind == "-":
        f.poly(rect(sz, sz * 0.27, cx, cz), mat, dy, d)
    elif kind == "x":
        f.poly(rect(sz, sz * 0.27, cx, cz), mat, dy, d, rot=math.pi / 4); f.poly(rect(sz, sz * 0.27, cx, cz), mat, dy - 0.01, d, rot=-math.pi / 4, ol=0.0)
    elif kind == "/":
        f.poly(rect(sz, sz * 0.24, cx, cz), mat, dy, d); f.ball(cx, cz + sz * 0.7, sz * 0.24, mat, dy=dy); f.ball(cx, cz - sz * 0.7, sz * 0.24, mat, dy=dy)
    elif kind == "pi":
        f.poly(rect(sz * 1.0, sz * 0.2, cx, cz + sz * 0.75), mat, dy, d, bev=0.0)
        f.poly(rect(sz * 0.19, sz * 0.78, cx - sz * 0.42, cz - sz * 0.05), mat, dy, d, bev=0.0)
        f.poly([(cx + sz * 0.3, cz + sz * 0.6), (cx + sz * 0.68, cz + sz * 0.6), (cx + sz * 0.66, cz - sz * 0.55), (cx + sz * 1.0, cz - sz * 0.62), (cx + sz * 0.98, cz - sz * 0.88), (cx + sz * 0.4, cz - sz * 0.86)], mat, dy, d, bev=0.0)

def em_maths(f, m, t=3):  # + - x / on a navy disc
    f.circ(0, 0, 1.0, m["navy"], d=0.28)
    for (cx, cz, k_, c) in ((-0.46, 0.46, "+", m["gold"]), (0.46, 0.46, "-", m["white"]), (-0.46, -0.46, "x", m["white"]), (0.46, -0.46, "/", m["gold"])): sym(f, k_, cx, cz, 0.3, c)


def em_ink(f, m, t=3):  # an ink splash
    pts = []
    for i in range(36):
        a = i * math.pi / 18; rr = 0.62 + (0.34 if i % 4 == 0 else 0.0) + 0.1 * math.sin(a * 3); pts.append((math.cos(a) * rr, math.sin(a) * rr))
    f.poly(pts, m["dark"], dy=-0.1, d=0.3)
    for cx, cz, rr in ((0.78, 0.5, 0.13), (-0.8, -0.35, 0.1), (0.5, -0.85, 0.09)): f.ball(cx, cz, rr, m["dark"], dy=-0.1)
    f.poly_line([(-0.4, -0.05), (-0.1, 0.2), (0.15, -0.1), (0.4, 0.15)], 0.07, m["paper"], dy=-0.4)


def em_ledger(f, m, t=3):  # a ledger page with ticked columns
    f.poly(rect(0.85, 1.0), m["paper"], d=0.3); f.poly(rect(0.85, 0.16, 0, 0.84), m["green"], dy=-0.1, d=0.3)
    for x in (-0.28, 0.28): f.line((x, 0.7), (x, -0.9), 0.04, m["dark"], dy=-0.2)
    for i, z in enumerate((0.4, 0.0, -0.4)):
        f.line((-0.85, z - 0.2), (0.85, z - 0.2), 0.035, m["dark"], dy=-0.2)
        f.poly_line([(-0.62, z), (-0.5, z - 0.12), (-0.36, z + 0.1)], 0.07, m["green"], dy=-0.35); f.line((0.0, z), (0.2, z), 0.05, m["dark"], dy=-0.3); f.line((0.4, z), (0.7, z), 0.05, m["crimson"], dy=-0.3)
    f.line((-0.8, -0.78), (0.8, -0.78), 0.04, m["crimson"], dy=-0.3); f.line((-0.8, -0.88), (0.8, -0.88), 0.04, m["crimson"], dy=-0.3)


def pi_top(k, t):  # toan: a big gold pi over the beret
    m = M(k); A = k.ch.addh; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    if t >= 4: return
    r = u * {1: 1.15, 2: 0.7, 3: 0.82}[t]
    f = F(k, V(hc.x, hc.y - 0.02 * s, hc.z + Rh[2] * 1.12 + 0.25 * u + r * 1.0), r, A)
    sym(f, "pi", 0.0, 0.0, 1.0, m["gold"], dy=0.0)
    if t >= 3:
        for sx, kd in ((-1, "+"), (1, "x")): g2 = F(k, V(hc.x + sx * 1.05 * u, hc.y - 0.02 * s, hc.z + Rh[2] * 1.0 + 0.5 * u), 0.26 * u, A); sym(g2, kd, 0, 0, 1.0, m["white"], dy=0.0)
    k.hat_top = hc.z + Rh[2] * 1.12 + 0.25 * u + r * 2.0


def hd_setsq(f, m):  # a big set square and a ruler
    f.poly(rect(0.17, 1.2, 0.95, 0.0), m["yellow"], d=0.35, rot=-0.28, ox=0.0)
    for i in range(7): f.line((0.8 + 0.0, -0.9 + i * 0.3), (0.95 + 0.0, -0.9 + i * 0.3 - 0.04), 0.03, m["dark"], dy=-0.25) if False else None
    f.poly([(-0.95, -1.0), (0.85, -1.0), (-0.95, 1.1)], m["main"], d=0.45, bev=0.0, ol=0.016)
    f.poly([(-0.68, -0.72), (0.4, -0.72), (-0.68, 0.0)], m["sky"], dy=-0.3, d=0.2, ol=0.012)
    for i in range(8): f.line((-0.95 + 0.04, -0.75 + i * 0.22), (-0.78, -0.75 + i * 0.22), 0.03, m["white"], dy=-0.3)
    f.text("90", -0.45, -0.52, 0.34, m["white"], dy=-0.4, ext=0.05)


def hd_telescope(f, m):
    k = f.k
    for (a, b) in (((-0.1, -0.15), (-0.6, -1.1)), ((0.05, -0.15), (0.05, -1.1)), ((0.2, -0.15), (0.75, -1.1))): f.line(a, b, 0.07, m["wood"], dy=0.0)
    f.add(k.tube("tele", [f.at(-0.75, 0.0, -0.1), f.at(0.8, 0.95, -0.1)], lambda tt: (0.2 + 0.14 * tt) * f.r, m["main"], outline=0.012, sides=10))
    for tt in (0.25, 0.6): f.add(k.tube("telb", [f.at(-0.75 + 1.55 * (tt - 0.04), 0.95 * (tt - 0.04), -0.1), f.at(-0.75 + 1.55 * (tt + 0.04), 0.95 * (tt + 0.04), -0.1)], (0.23 + 0.14 * tt) * f.r, m["gold"], outline=0.01, sides=10))
    f.add(k.tube("telo", [f.at(0.8, 0.95, -0.1), f.at(0.88, 1.0, -0.1)], 0.37 * f.r, m["gold"], outline=0.012, sides=10)); f.ball(0.9, 1.01, 0.2, m["neon"], dy=-0.2, ol=0.0)
    f.ball(-0.8, -0.03, 0.14, m["dark"], dy=-0.1)
    f.ball(0.0, -0.1, 0.17, m["gold"], dy=0.0)


def hd_lawbook(f, m):
    f.poly(rect(0.8, 1.05), m["crimson"], d=0.7, bev=0.05); f.poly(rect(0.7, 0.95, 0.12, 0.0), m["paper"], dy=0.3, d=0.5, ol=0.006)
    f.poly(rect(0.12, 1.05, -0.78, 0.0), m["dark"], dy=-0.25, d=0.72); f.ring(0.0, 0.4, 0.0, 0.0, m["gold"]) if False else None
    f.line((-0.55, 0.85), (0.6, 0.85), 0.05, m["gold"], dy=-0.5); f.line((-0.55, -0.85), (0.6, -0.85), 0.05, m["gold"], dy=-0.5)
    f.line((0.03, 0.3), (0.03, -0.3), 0.06, m["gold"], dy=-0.55); f.line((-0.3, 0.3), (0.36, 0.3), 0.06, m["gold"], dy=-0.55)
    for sx in (-1, 1): f.poly(arc(0.2, 180, 360, 8, 0.03 + sx * 0.33, -0.05), m["gold"], dy=-0.55, d=0.15, ol=0.0)
    f.text("LUAT", 0.05, -0.62, 0.34, m["gold"], dy=-0.6, ext=0.05)


def hd_writing(f, m):  # an open notebook with handwriting and a big brush
    f.poly([(-1.0, 0.8), (0.0, 0.65), (0.0, -0.95), (-1.0, -0.8)], m["paper"], d=0.4, bev=0.03); f.poly([(0.0, 0.65), (1.0, 0.8), (1.0, -0.8), (0.0, -0.95)], m["paper"], d=0.4, bev=0.03)
    f.line((0.0, 0.7), (0.0, -0.95), 0.05, m["brown"], dy=-0.2)
    for i, z in enumerate((0.45, 0.2, -0.05, -0.3, -0.55)):
        pts = [(-0.85 + j * 0.1, z + 0.04 * math.sin(j * 1.7 + i)) for j in range(0, 7 + (i % 2))]
        f.poly_line(pts, 0.04, m["dark"], dy=-0.25)
        pts2 = [(0.15 + j * 0.1, z - 0.02 + 0.04 * math.sin(j * 1.9 + i)) for j in range(0, 7 - (i % 3))]
        f.poly_line(pts2, 0.04, m["dark"], dy=-0.25)
    k = f.k
    f.add(k.tube("wb", [f.at(0.5, -0.5, -0.5), f.at(1.05, 0.7, -0.5)], 0.1 * f.r, m["wood"], outline=0.01, sides=6))
    f.add(k.tube("wbf", [f.at(1.02, 0.65, -0.5), f.at(1.08, 0.78, -0.5)], 0.13 * f.r, m["crimson"], outline=0.008, sides=6))
    f.add(k.tube("wbt", [f.at(1.06, 0.75, -0.5), f.at(1.18, 1.1, -0.5), f.at(1.3, 1.5, -0.5)], lambda tt: 0.17 * f.r * (1 - tt * 0.9), m["dark"], outline=0.01, sides=8))


def hd_calctape(f, m):  # a calculator with a long receipt tape spilling down
    k = f.k
    tape = [(-0.55, 0.2), (0.0, 0.2), (0.0, -1.4)] + [(0.0 - 0.0, -1.4 - 0.0)]
    zig = [(-0.62, -1.45), (-0.5, -1.25), (-0.38, -1.45), (-0.26, -1.25), (-0.14, -1.45), (-0.02, -1.25)]
    f.poly([(-0.62, 0.3), (-0.02, 0.3)] + zig[::-1] + [(-0.62, -1.3)], m["white"], dy=0.2, d=0.2, ol=0.012)
    for z in (-0.1, -0.4, -0.7, -1.0): f.line((-0.52, z), (-0.2, z), 0.035, m["dark"], dy=-0.0)
    f.poly_line([(-0.5, -0.25), (-0.4, -0.36), (-0.25, -0.18)], 0.05, m["green"], dy=-0.0); f.poly_line([(-0.5, -0.85), (-0.4, -0.96), (-0.25, -0.78)], 0.05, m["green"], dy=-0.0)
    f.line((-0.55, -1.15), (-0.08, -1.15), 0.045, m["crimson"], dy=0.0)
    f.poly(rect(0.62, 0.95, 0.35, 0.05), m["main"], dy=-0.3, d=0.4, bev=0.05); f.poly(rect(0.5, 0.2, 0.35, 0.72), m["lcd"], dy=-0.55, d=0.2)
    f.text("1,250", 0.42, 0.72, 0.3, m["dark"], dy=-0.7, ext=0.03)
    for i in range(3):
        for j in range(3): f.poly(rect(0.12, 0.1, 0.12 + j * 0.23, 0.38 - i * 0.28), m["white"] if j < 2 else m["orange"], dy=-0.6, d=0.2, ol=0.006)
    f.poly(rect(0.12, 0.1, 0.12, -0.46), m["white"], dy=-0.6, d=0.2, ol=0.006); f.poly(rect(0.35, 0.1, 0.46, -0.46), m["green"], dy=-0.6, d=0.2, ol=0.006)


def hd_bookstack(f, m):  # a tall stack of books
    cols = (m["crimson"], m["main"], m["green"], m["gold"], m["purple"])
    for i, (w, c) in enumerate(((0.95, cols[0]), (0.8, cols[1]), (0.9, cols[2]), (0.72, cols[3]), (0.8, cols[4]))):
        z = -0.85 + i * 0.42; ox = 0.06 * ((i % 2) * 2 - 1)
        f.poly(rect(w, 0.2, ox, z), c, d=0.8, bev=0.03); f.poly(rect(w * 0.92, 0.07, ox + 0.08, z - 0.02), m["paper"], dy=-0.45, d=0.4, ol=0.0)
        f.line((ox - w + 0.12, z + 0.1), (ox - w + 0.12, z - 0.1), 0.04, m["gold"], dy=-0.5)
    f.ball(0.0, 1.1, 0.14, m["gold"], dy=-0.2)


def hat_van2(k, t):  # a writer: ribbon headband with a huge quill and ink drops (no imperial elements)
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    band(k, 0.5, m["cream"], 0.09, k_=1.04); band(k, 0.42, m["main"], 0.05, k_=1.04)
    for sx in (-1, 1): A(H.ball("bow", V(hc.x - 0.62 * u + sx * 0.14 * u, hc.y - Rh[1] * 0.72, hc.z + Rh[2] * 0.52), (0.17 * u, 0.07 * u, 0.1 * u), m["main"], rot=(0, sx * 0.5, 0), outline=0.012))
    A(H.ball("bowk", V(hc.x - 0.62 * u, hc.y - Rh[1] * 0.74, hc.z + Rh[2] * 0.52), (0.07 * u,) * 3, m["deep"], outline=0.01))
    base = V(hc.x + 0.1 * u, hc.y - 0.04 * s, hc.z + Rh[2] * 0.7); L = u * {1: 1.75, 2: 1.5, 3: 1.85, 4: 2.1}[t]
    f = F(k, base, 1.0, A)
    f.poly(leaf_pts(L, 0.42 * u), m["white"], rot=-0.32, d=0.09 * u, bev=0.0, ol=0.016)
    f.poly(leaf_pts(L * 0.8, 0.2 * u), m["paper"], rot=-0.32, d=0.09 * u, bev=0.0, ol=0.0, dy=-0.05 * u)
    a = -0.32
    A(k.tube("qs", [base + V(math.sin(-a) * 0.0, -0.06 * u, 0), base + V(-math.sin(a) * L * 0.95, -0.06 * u, math.cos(a) * L * 0.95)], 0.035 * u, m["brown"], outline=0.008, sides=5))
    A(k.tube("qn", [base + V(0, -0.06 * u, 0), base + V(-0.08 * u, -0.06 * u, -0.28 * u)], lambda tt: 0.05 * u * (1 - tt * 0.8), m["dark"], outline=0.008, sides=6))
    if t >= 2:
        for dx, dz, r_ in ((-0.35, -0.2, 0.08), (-0.52, -0.5, 0.06)): A(H.ball("ink", base + V(dx * u, -0.06 * u, dz * u), (r_ * u, r_ * u * 0.5, r_ * u * 1.3), m["dark"], outline=0.0))
    k.hat_top = base.z + L * 0.95


def hat_cd2(k, t):  # a dark judge's cap carrying a big gold scales of justice
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    R = dome(k, m["dark"], 0.45, 1.05, 0.62, 0.07); band(k, 0.45, m["gold"], 0.07, k_=1.05)
    top = hc.z + R[2] * 0.97
    r = 0.6 * u * {1: 1.5, 2: 0.9, 3: 1.0, 4: 1.1}[t]
    c = V(hc.x, hc.y - 0.02 * s, top + r * 1.05)
    f = F(k, c, r, A)
    f.line((0, -1.0), (0, 0.8), 0.1, m["gold"], dy=0.0); f.poly(rect(0.4, 0.1, 0, -1.0), m["gold"], dy=0.0, d=0.5); f.ball(0, 0.95, 0.16, m["gold"], dy=0.0)
    f.line((-1.4, 0.7), (1.4, 0.7), 0.1, m["gold"], dy=-0.05)
    for sx in (-1, 1):
        x = sx * 1.4; f.line((x, 0.7), (x - 0.5, -0.2), 0.035, m["gold"], dy=-0.05); f.line((x, 0.7), (x + 0.5, -0.2), 0.035, m["gold"], dy=-0.05)
        f.poly(arc(0.62, 180, 360, 12, x, -0.2), m["gold"], dy=-0.1, d=0.5)
    k.hat_top = c.z + r * 1.9


def hat_khoahoc2(k, t):  # a ringed planet over a leafy-lime headband, with stars
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    band(k, 0.5, m["deep"], 0.085, k_=1.04); band(k, 0.42, m["white"], 0.04, k_=1.04)
    for i in range(5 if t >= 3 else 3):
        p = k.surf(hc, tuple(x * 1.04 for x in Rh), -90 + (i - 2) * 28, 0.5, 0.06 * s)[0]
        A(H.ball("bl", p, (0.13 * u, 0.06 * u, 0.09 * u), m["lime"], rot=(0, 0, (i - 2) * 0.4), outline=0.008))
    R = 0.62 * u * {1: 1.15, 2: 0.9, 3: 1.0, 4: 1.12}[t]
    c = V(hc.x, hc.y, hc.z + Rh[2] + 0.2 * u + R)
    A(H.ball("planet", c, (R,) * 3, m["lime"], outline=0.016))
    for dz, w_ in ((0.25, 0.95), (-0.2, 0.98)): A(H.ball("pband", c + V(0, -R * 0.1, dz * R), (R * w_, R * 0.9, R * 0.12), m["main"] if False else m["blue"], outline=0.0))
    th = math.radians(-22); pts = []
    for a in [i * 2 * math.pi / 56 for i in range(56)]:
        x, y = math.cos(a) * R * 1.9, math.sin(a) * R * 1.9 * 0.42
        pts.append(c + V(x * math.cos(th) - 0.0, y, -x * math.sin(th) * 0.5))
    A(k.tube("ring", pts, 0.085 * R, m["gold"], closed=True, outline=0.012, sides=6))
    A(k.tube("ring2", [c + (p - c) * 0.84 for p in pts], 0.045 * R, m["white"], closed=True, outline=0.0, sides=5))
    f = F(k, c, 1.0, A)
    star = [(math.cos(math.pi / 2 + i * math.pi / 4) * (0.5 if i % 2 == 0 else 0.13), math.sin(math.pi / 2 + i * math.pi / 4) * (0.5 if i % 2 == 0 else 0.13)) for i in range(8)]
    for sx, dz, kk in ((-1, 0.55, 1.0), (1, 0.95, 0.8), (-1, -0.35, 0.7)):
        f.poly(star, m["yellow"], dy=-0.05, d=0.15 * u, ol=0.01, sc=0.42 * u * kk * (1.6 if t >= 3 else 1.2), ox=sx * 1.5 * R * (1.0 if kk > 0.75 else 1.12), oz=dz * R)
    k.hat_top = c.z + R * 1.2


def hat_ketoan2(k, t):  # a green eyeshade, a pencil behind the ear and a rubber stamp: paperwork, not maths
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    band(k, 0.52, m["green"], 0.13, k_=1.045); band(k, 0.64, m["green"], 0.06, k_=1.02)
    A(H.ball("visor", V(hc.x, hc.y - Rh[1] * 0.92, hc.z + Rh[2] * 0.52), (1.05 * u, 0.7 * u, 0.075 * u), m["green"], rot=(0.38, 0, 0), outline=0.02))
    A(H.ball("visor2", V(hc.x, hc.y - Rh[1] * 0.93, hc.z + Rh[2] * 0.54), (0.9 * u, 0.56 * u, 0.045 * u), m["lime"], rot=(0.38, 0, 0), outline=0.0))
    for sx in (-1, 1): A(H.ball("vstrap", V(hc.x + sx * Rh[0] * 0.98, hc.y - Rh[1] * 0.3, hc.z + Rh[2] * 0.5), (0.05 * u, 0.4 * u, 0.1 * u), m["green"], outline=0.01))
    A(k.tube("pen", [V(hc.x + 0.62 * u, hc.y + 0.05, hc.z + Rh[2] * 0.5), V(hc.x + 1.15 * u, hc.y + 0.05, hc.z + Rh[2] * 1.5)], 0.075 * u, m["yellow"], outline=0.01, sides=6))
    A(k.tube("pen2", [V(hc.x + 0.59 * u, hc.y + 0.05, hc.z + Rh[2] * 0.44), V(hc.x + 0.65 * u, hc.y + 0.05, hc.z + Rh[2] * 0.56)], 0.075 * u, m["dark"], outline=0.008, sides=6))
    A(k.tube("pen3", [V(hc.x + 1.12 * u, hc.y + 0.05, hc.z + Rh[2] * 1.45), V(hc.x + 1.17 * u, hc.y + 0.05, hc.z + Rh[2] * 1.57)], 0.075 * u, m["pink"], outline=0.008, sides=6))
    if t >= 1:  # a rubber stamp perched on the head
        z0 = hc.z + Rh[2] * 0.95
        A(H.cyl("stampb", V(hc.x - 0.1 * u, hc.y, z0 + 0.12 * u), 0.5 * u * 0.62, 0.24 * u, m["crimson"], outline=0.016))
        A(H.ball("stampk", V(hc.x - 0.1 * u, hc.y, z0 + 0.42 * u), (0.2 * u, 0.2 * u, 0.2 * u), m["wood"], outline=0.014))
        A(H.rbox("stampp", V(hc.x - 0.1 * u, hc.y, z0 - 0.02 * u), (0.42 * u, 0.42 * u, 0.06 * u), m["dark"], outline=0.01))
    k.hat_top = hc.z + Rh[2] + 0.8 * u


HATS.update(van=hat_van2, cd=hat_cd2, khoahoc=hat_khoahoc2, ketoan=hat_ketoan2)
EMB.update(maths=em_maths, ink=em_ink, ledger=em_ledger)
HELD.update(setsq=hd_setsq, telescope=hd_telescope, lawbook=hd_lawbook, writing=hd_writing, calctape=hd_calctape, bookstack=hd_bookstack)


def hat_su2(k, t):  # Dong Son bronze drum-top disc worn upright as a crest, a gold band, no feather fan
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    band(k, 0.5, m["gold"], 0.1, k_=1.04); band(k, 0.4, m["red"], 0.06, k_=1.03)
    r = u * {1: 1.15, 2: 0.78, 3: 0.95, 4: 1.1}[t]
    c = V(hc.x, hc.y - 0.02 * s, hc.z + Rh[2] * 0.9 + r * 0.95)
    f = F(k, c, r, A)
    f.circ(0, 0, 1.0, m["bronze"], d=0.3, n=48); f.ring(0, 0, 1.0, 0.07, m["gold"], dy=-0.2)
    f.ring(0, 0, 0.84, 0.05, m["dark"], dy=-0.2); f.ring(0, 0, 0.58, 0.05, m["dark"], dy=-0.2)
    star = []
    for i in range(24):
        a = math.pi / 2 + i * math.pi / 12; rr = 0.5 if i % 2 == 0 else 0.24; star.append((math.cos(a) * rr, math.sin(a) * rr))
    f.poly(star, m["gold"], dy=-0.3, d=0.2)
    for i in range(16):
        a = i * math.pi / 8; f.ball(math.cos(a) * 0.72, math.sin(a) * 0.72, 0.055, m["dark"], dy=-0.3, ol=0.0)
    for sx in (-1, 1): A(H.ball("sh", V(hc.x + sx * 0.4 * r, hc.y, c.z - r * 1.0), (0.3 * r, 0.14 * r, 0.12 * r), m["bronze"], outline=0.012))
    k.hat_top = c.z + r


_hk = hat_khoahoc2
def hat_khoahoc3(k, t):
    _hk(k, t)
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    f = F(k, V(hc.x + 0.55 * u, hc.y - Rh[1] * 1.05, hc.z + Rh[2] * 0.5), 0.2 * u, A)  # a tiny beaker on the band
    f.poly([(-0.5, 1.0), (0.5, 1.0), (0.5, -0.9), (-0.5, -0.9)], m["glass"], d=0.3, bev=0.05); f.poly(rect(0.46, 0.5, 0, -0.45), m["lime"], dy=-0.2, d=0.2, ol=0.0)


HATS.update(su=hat_su2, khoahoc=hat_khoahoc3)


def hat_su3(k, t):  # a little Dong Son bronze drum (a cylinder with the patterned top facing forward) worn on a gold band
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    band(k, 0.5, m["gold"], 0.1, k_=1.04)
    r = u * {1: 1.0, 2: 0.85, 3: 0.95, 4: 1.1}[t]
    c = V(hc.x, hc.y, hc.z + Rh[2] * 0.85 + r * 0.9)
    rot = (math.radians(90), 0, 0)
    body = H.cyl("drumb", c + V(0, 0.18 * r, 0), r * 0.82, 0.9 * r, m["bronze"], outline=0.02); body.rotation_euler = rot; A(body)
    top = H.cyl("drumt", c + V(0, -0.28 * r, 0), r * 1.0, 0.34 * r, m["gold"], outline=0.02); top.rotation_euler = rot; A(top)
    for dz in (-0.5, 0.5): 
        hnd = H.ball("drumh", c + V(0.0, 0.1 * r, dz * r * 0.0), (0.001,) * 3, m["bronze"], outline=0.0); A(hnd)
    for sx in (-1, 1): A(H.ball("drumhd", c + V(sx * r * 0.86, 0.18 * r, 0.0), (0.12 * r, 0.12 * r, 0.42 * r), m["dark"], outline=0.01))
    f = F(k, c + V(0, -0.46 * r, 0), r * 0.9, A)
    f.circ(0, 0, 1.0, m["bronze"], d=0.12, n=48, ol=0.0); f.ring(0, 0, 0.93, 0.06, m["dark"], dy=-0.05); f.ring(0, 0, 0.66, 0.05, m["dark"], dy=-0.05)
    star = []
    for i in range(24):
        a = math.pi / 2 + i * math.pi / 12; rr = 0.55 if i % 2 == 0 else 0.26; star.append((math.cos(a) * rr, math.sin(a) * rr))
    f.poly(star, m["white"] if False else m["yellow"], dy=-0.12, d=0.12)
    for i in range(16):
        a = i * math.pi / 8; f.ball(math.cos(a) * 0.8, math.sin(a) * 0.8, 0.05, m["dark"], dy=-0.1, ol=0.0)
    k.hat_top = c.z + r


def _x1(base, extra):
    def fn(k, t):
        base(k, t)
        if t == 1: extra(k)
    return fn


def ex_tin(k):
    m = M(k); hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    f = F(k, V(hc.x, hc.y - 0.02 * s, hc.z + Rh[2] * 1.18 + 0.62 * u), 0.95 * u, k.ch.addh)
    f.poly(rect(1.0, 0.62), m["dark"], d=0.25, bev=0.12, ol=0.016); f.poly(rect(0.9, 0.52), m["black"], dy=-0.15, d=0.15, ol=0.0)
    f.text("</>", 0, 0.0, 0.95, m["neon"], dy=-0.3, ext=0.1); k.hat_top = hc.z + Rh[2] * 1.18 + 1.3 * u


def ex_cn(k):
    m = M(k); hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    f = F(k, V(hc.x, hc.y - 0.1 * s, hc.z + Rh[2] * 1.12 + 0.75 * u), 0.72 * u, k.ch.addh)
    pts = []
    for i in range(32):
        a = i * math.pi / 16; rr = 1.0 if (i // 2) % 2 == 0 else 0.74; pts.append((math.cos(a) * rr, math.sin(a) * rr))
    f.poly(pts, m["silver"], d=0.4, ol=0.02); f.circ(0, 0, 0.36, m["dark"], dy=-0.3, d=0.2); f.ring(0, 0, 0.6, 0.06, m["dark"], dy=-0.3)
    k.hat_top = hc.z + Rh[2] * 1.12 + 1.5 * u


def ex_li(k):
    m = M(k); A = k.ch.addh; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    base = V(hc.x, hc.y - 0.03 * s, hc.z + Rh[2] + 0.2 * u); big = 1.15 * u
    f = F(k, base + V(0, 0.08, big * 0.88), big * 1.16, A); f.poly(BOLT, m["orange"], d=0.3, bev=0.0, ol=0.02)
    g2 = F(k, base + V(0, -0.1, big * 0.88), big * 0.9, A); g2.poly(BOLT, m["yellow"], dy=-0.2, d=0.2, bev=0.0, ol=0.0)
    for sx in (-1, 1): h = F(k, base + V(sx * 0.95 * u, 0.02, big * 0.45), big * 0.5, A); h.poly(BOLT, m["yellow"], d=0.3, bev=0.0, rot=-sx * 0.5, ol=0.016)


def ex_khoahoc(k):
    m = M(k); A = k.ch.addh; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    f = F(k, V(hc.x + 0.95 * u, hc.y - 0.2 * s, hc.z + Rh[2] * 0.95), 0.42 * u, A)
    f.poly([(-0.5, 1.0), (0.5, 1.0), (0.5, -0.9), (-0.5, -0.9)], m["glass"], d=0.3, bev=0.05, ol=0.016); f.poly(rect(0.46, 0.5, 0, -0.45), m["lime"], dy=-0.2, d=0.2, ol=0.0)
    for cx, cz, rr in ((0.1, 0.2, 0.14), (-0.1, 0.55, 0.1)): f.ball(cx, cz, rr, m["white"], dy=-0.4, ol=0.006)


def ex_van(k):
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    c = V(hc.x - 0.95 * u, hc.y - 0.15 * s, hc.z + Rh[2] * 0.9)
    A(H.cyl("pot", c, 0.34 * u, 0.4 * u, m["dark"], outline=0.014)); A(H.torus("potr", c + V(0, 0, 0.2 * u), 0.3 * u, 0.06 * u, m["white"], (0, 0, 0), outline=0.008))
    A(H.ball("potink", c + V(0, 0, 0.21 * u), (0.25 * u, 0.25 * u, 0.04 * u), m["navy"], outline=0.0))


HATS.update(su=hat_su3, tin=_x1(hat_tin, ex_tin), cn=_x1(hat_cn, ex_cn), li=_x1(hat_li, ex_li), khoahoc=_x1(hat_khoahoc3, ex_khoahoc), van=_x1(hat_van2, ex_van))


# ================================================================== ROUND 4: bold small-stage signatures for the university chicks ===============================
def _sign(k, c, r, add):
    return F(k, c, r, add)


def hat_khmt_s(k, t):  # a little monitor showing a big white { }
    if t >= 3: return _hk_khmt(k, t)
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    band(k, 0.5, m["main"], 0.085, k_=1.04)
    r = u * {1: 1.0, 2: 0.9}[t]
    c = V(hc.x, hc.y - 0.02 * s, hc.z + Rh[2] * 0.95 + r * 1.15)
    f = F(k, c, r, A)
    f.poly(rect(1.05, 0.78), m["dark"], d=0.3, bev=0.12, ol=0.02); f.poly(rect(0.92, 0.65), m["navy"], dy=-0.17, d=0.15, ol=0.0)
    f.text("{ }", 0, 0.0, 1.05, m["white"], dy=-0.3, ext=0.12)
    f.poly(rect(0.12, 0.3, 0, -1.05), m["dark"], d=0.3); f.poly(rect(0.5, 0.08, 0, -1.3), m["dark"], d=0.4)
    k.hat_top = c.z + r * 0.9


def hat_httt_s(k, t):  # an emerald/grey database cylinder with three silver bands and a table sign
    if t >= 3: return _hk_httt(k, t)
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    rr = 0.78 * u * (1.1 if t == 1 else 1.0); h = 0.36 * u
    for i in range(3):
        z = hc.z + Rh[2] * 0.85 + h * 0.5 + i * h * 1.12
        A(H.cyl("dsk", V(hc.x - 0.15 * u, hc.y, z), rr, h, m["main"], outline=0.02))
        A(H.torus("dskb", V(hc.x - 0.15 * u, hc.y, z + h * 0.52), rr, 0.05 * u, m["silver"], (0, 0, 0), outline=0.0))
        A(H.ball("led", V(hc.x - 0.15 * u - 0.4 * u, hc.y - rr * 0.97, z), (0.06 * u,) * 3, m["lime"] if i != 1 else m["yellow"], outline=0.0))
        A(H.rbox("slot", V(hc.x - 0.15 * u + 0.15 * u, hc.y - rr * 0.99, z), (0.4 * u, 0.04 * u, 0.07 * u), m["dark"], outline=0.0))
    f = F(k, V(hc.x + 0.78 * u, hc.y - 0.3 * u, hc.z + Rh[2] * 1.15 + 0.5 * u), 0.5 * u, A); em_table(f, m)
    k.hat_top = hc.z + Rh[2] * 0.85 + h * 4


def hat_khdl_s(k, t):  # a flat chart board: bars, a big rising arrow and a small pie
    if t >= 3: return _hk_khdl(k, t)
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    r = u * {1: 1.05, 2: 0.95}[t]
    c = V(hc.x, hc.y - 0.02 * s, hc.z + Rh[2] * 0.95 + r * 1.05)
    f = F(k, c, r, A)
    f.poly(rect(1.1, 0.9), m["white"], d=0.22, bev=0.08, ol=0.02)
    for i, h in enumerate((0.35, 0.6, 0.9)): f.poly(rect(0.17, h / 2, -0.62 + i * 0.4, -0.75 + h / 2), (m["main"], m["gold"], m["purple"])[i], dy=-0.15, d=0.2)
    f.poly_line([(-0.85, -0.55), (-0.25, -0.05), (0.15, -0.3), (0.85, 0.55)], 0.1, m["red"], dy=-0.4)
    f.poly([(0.55, 0.8), (1.0, 0.8), (0.95, 0.35)], m["red"], dy=-0.4, d=0.2, ol=0.008)
    g = F(k, c + V(0.95 * r, -0.05, -0.45 * r), 0.42 * r, A); em_pie(g, m)
    k.hat_top = c.z + r * 0.95


def ex_kinhte(k, t):  # a big gold coin and an up-trend arrow above the top hat
    if t >= 3: return
    m = M(k); A = k.ch.addh; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    z0 = hc.z + Rh[2] * 0.58; hh = 1.05 * u * {1: 1.15, 2: 0.85}[t]
    f = F(k, V(hc.x, hc.y - 0.75 * u, z0 + hh * 0.55), 0.5 * u * (1.1 if t == 1 else 1.0), A); em_coin(f, m)
    g = F(k, V(hc.x + 0.95 * u, hc.y - 0.35 * u, z0 + hh * 1.05), 0.45 * u, A)
    g.poly_line([(-0.9, -0.7), (-0.2, -0.05), (0.2, -0.35), (0.85, 0.5)], 0.12, m["green"], dy=0.0); g.poly([(0.45, 0.85), (1.0, 0.85), (1.0, 0.3)], m["green"], d=0.2, ol=0.008)


def hat_ketoan3(k, t):  # a big calculator with "=" on the head, a red stamp and a pencil; a low green visor that doesn't hide it
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    band(k, 0.52, m["green"], 0.1, k_=1.045)
    A(H.ball("visor", V(hc.x, hc.y - Rh[1] * 0.93, hc.z + Rh[2] * 0.5), (0.9 * u, 0.5 * u, 0.06 * u), m["green"], rot=(0.38, 0, 0), outline=0.018))
    A(k.tube("pen", [V(hc.x + 0.7 * u, hc.y + 0.05, hc.z + Rh[2] * 0.4), V(hc.x + 1.15 * u, hc.y + 0.05, hc.z + Rh[2] * 1.2)], 0.07 * u, m["yellow"], outline=0.01, sides=6))
    A(k.tube("pen2", [V(hc.x + 0.68 * u, hc.y + 0.05, hc.z + Rh[2] * 0.36), V(hc.x + 0.72 * u, hc.y + 0.05, hc.z + Rh[2] * 0.44)], 0.07 * u, m["dark"], outline=0.008, sides=6))
    r = u * {1: 1.0, 2: 0.9, 3: 0.95, 4: 1.05}[t]
    c = V(hc.x - 0.05 * u, hc.y - 0.02 * s, hc.z + Rh[2] * 0.95 + r * 1.0)
    f = F(k, c, r, A); em_calc(f, m)
    f.text("=", 0.0, -0.68, 0.5, m["white"], dy=-0.5, ext=0.05) if False else None
    sc = V(hc.x - 0.9 * u, hc.y - 0.2 * s, hc.z + Rh[2] * 0.9)
    A(H.cyl("stampb", sc + V(0, 0, 0.18 * u), 0.2 * u, 0.3 * u, m["crimson"], outline=0.014)); A(H.ball("stampk", sc + V(0, 0, 0.42 * u), (0.14 * u,) * 3, m["wood"], outline=0.012))
    A(H.cyl("stampp", sc, 0.27 * u, 0.06 * u, m["dark"], outline=0.01))
    k.hat_top = c.z + r


_hk_khmt, _hk_httt, _hk_khdl = HATS["khmt"], HATS["httt"], HATS["khdl"]
_hk_kinhte = HATS["kinhte"]
HATS.update(khmt=hat_khmt_s, httt=hat_httt_s, khdl=hat_khdl_s, ketoan=hat_ketoan3, kinhte=lambda k, t: (_hk_kinhte(k, t), ex_kinhte(k, t))[0])


def hat_khoahoc4(k, t):  # Saturn-like planet (flat purple, bold tilted gold ring), big bubbling flask and a small microscope at hat level, stars
    m = M(k); A = k.ch.addh; H = k.H; hc, Rh, s, u = k.hc, k.Rh, k.s, k.rh
    band(k, 0.5, m["deep"], 0.085, k_=1.04); band(k, 0.42, m["white"], 0.04, k_=1.04)
    R = 0.62 * u * {1: 1.1, 2: 0.95, 3: 1.0, 4: 1.1}[t]
    c = V(hc.x, hc.y, hc.z + Rh[2] + 0.2 * u + R)
    A(H.ball("planet", c, (R,) * 3, m["purple"], outline=0.02))
    th = math.radians(24); ca, sa = math.cos(th), math.sin(th); pts = []; pts2 = []
    for a in [i * 2 * math.pi / 64 for i in range(64)]:
        x, z = math.cos(a) * R * 2.0, math.sin(a) * R * 0.62
        P = V(c.x + x * ca - z * sa, c.y + 0.9 * R * math.sin(a) * -1 * -1, c.z + x * sa + z * ca)
        pts.append(P); pts2.append(c + (P - c) * 0.8)
    A(k.tube("ring", pts, 0.13 * R, m["gold"], closed=True, outline=0.014, sides=6))
    A(k.tube("ring2", pts2, 0.06 * R, m["yellow"], closed=True, outline=0.0, sides=5))
    f = F(k, c, 1.0, A)
    star = [(math.cos(math.pi / 2 + i * math.pi / 4) * (0.5 if i % 2 == 0 else 0.13), math.sin(math.pi / 2 + i * math.pi / 4) * (0.5 if i % 2 == 0 else 0.13)) for i in range(8)]
    for sx, dz, kk in ((-1, 0.95, 1.0), (1, 1.05, 0.8)):
        f.poly(star, m["yellow"], dy=-0.05, d=0.15 * u, ol=0.01, sc=0.5 * u * kk, ox=sx * 1.15 * R, oz=dz * R)
    rr = 0.55 * u * {1: 0.8, 2: 0.85, 3: 1.0, 4: 1.1}[t]
    g = F(k, V(hc.x + 1.0 * u + rr * 0.3, hc.y - 0.3 * s, hc.z + Rh[2] * 0.95 + rr * 0.6), rr, A); em_flask(g, m)
    for dx, dz, r_ in ((0.05, 1.35, 0.14), (-0.15, 1.7, 0.1), (0.2, 2.0, 0.08)): g.ball(dx, dz, r_, m["lime"], dy=-0.5, ol=0.008)
    if t >= 2:
        mr = 0.42 * u * {2: 0.85, 3: 1.0, 4: 1.1}[t]
        h = F(k, V(hc.x - 1.0 * u - mr * 0.3, hc.y - 0.3 * s, hc.z + Rh[2] * 0.95 + mr * 0.8), mr, A); hd_micro(h, m)
    k.hat_top = c.z + R * 1.3


HATS["khoahoc"] = hat_khoahoc4
