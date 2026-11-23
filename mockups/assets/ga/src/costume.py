# Gunny-style costume sets for the Lang ga chickens. Data driven: SPEC[subject]["stages"][1..4] names a head piece, a top, a back
# piece, shoes and extras; the builders below turn those names into 3D parts on the chicken built by chicken.py.
#   chicken.py <out> <mode> <subject> <stage> costume      (5th argument turns the costume on)
# Fabric detail comes from tex/<name>-d.png (knit, wool, brocade, leather: FLUX tileable patterns, see gen_tex.py).
import bpy, bmesh, math, os
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__)); TEXDIR = os.path.join(HERE, "tex")

# ---- the spec: the outfit of one subject, per stage -------------------------------------------------------------------------
# colours: main/dark/hi = the subject accent, deep = a darker robe tone, cream = lining/shirt; metal per stage (silver -> gold)
SPEC = {
    "toan": dict(
        theme="Nha toan hoc: len, thuoc ke, compa, thuoc do do",
        main=("#4a86f2", "#2a56b8", "#a8c6ff"), deep=("#2f55b8", "#1b2f78", "#7f9fe8"), cream=("#fff3d6", "#d9c39a", "#ffffff"),
        emblem="maths", held="setsq", halo="protractor", orbit=["maths"], motif="ticks",
        stages={
            1: dict(head="beanie", top="bib", back=None, feet="booties", extra=[], metal="silver"),
            2: dict(head="cap", top="vest", back="satchel", feet="shoes", extra=["bowtie", "chest", "held"], metal="silver"),
            3: dict(head="tam", top="coat", back="cape", feet="boots", extra=["glasses", "brooch", "cuffs", "chest", "held"], metal="gold"),
            4: dict(head="tall", top="robe", back="cape_long", feet="gilded", extra=["glasses", "brooch", "cuffs", "epaulettes", "halo", "orbit", "chest", "held"], metal="gold"),
        }),
}


def _S(main, deep, cream, emblem, held, metal="gold", halo="ring", glow="#ffe9a0", orbit=None, theme=""):
    """a subject's costume spec: the hat is subject specific (gunny.HATS), the rest is the shared Gunny wardrobe in the subject colours"""
    return dict(theme=theme, main=main, deep=deep, cream=cream, emblem=emblem, held=held, halo=halo, glow=glow, orbit=orbit or [emblem], motif="",
                stages={1: dict(head="gunny", top="bib", back=None, feet="booties", extra=[], metal="silver"),
                        2: dict(head="gunny", top="vest", back=None, feet="shoes", extra=["chest", "held"], metal="silver"),
                        3: dict(head="gunny", top="coat", back="cape", feet="boots", extra=["chest", "held", "cuffs"], metal=metal),
                        4: dict(head="gunny", top="robe", back="cape_long", feet="gilded", extra=["chest", "held", "cuffs", "epaulettes", "halo", "orbit"], metal=metal)})


SPEC.update(
    van=_S(("#a8714a", "#6a4128", "#e0b88e"), ("#5a4036", "#2e1f19", "#9a7a6a"), ("#fff0d0", "#dcc59a", "#ffffff"), "ink", "writing", halo="ring", theme="Ruy bang, long vu khong lo, vo viet tay, vet muc"),
    anh=_S(("#25a9a3", "#13756f", "#8ae6df"), ("#157a76", "#0b4a47", "#5cc7c1"), ("#fff6e8", "#e0cfae", "#ffffff"), "union", "dict", halo="ring", orbit=["union"], theme="Tai nghe, bong bong Hello, co Anh"),
    li=_S(("#f4c21f", "#c9930a", "#ffe58a"), ("#d99a0a", "#8a5a00", "#ffd060"), ("#fff8d8", "#e8d49a", "#ffffff"), "bolt", "magnet", halo="ring", orbit=["bolt"], theme="Vuong mien tia chop, nam cham"),
    hoa=_S(("#9b59d0", "#6d3a9c", "#d2b0f0"), ("#6d3a9c", "#40206a", "#a07cd0"), ("#f3ecff", "#cdbfe8", "#ffffff"), "h2o", "beaker", halo="ring", orbit=["flask"], theme="Binh cau soi bong bong, kinh bao ho"),
    sinh=_S(("#3cbf6a", "#26894a", "#9be8b4"), ("#26894a", "#145a2e", "#5ac888"), ("#f2ffe6", "#cfe6b0", "#ffffff"), "dna", "magnifier", halo="ring", orbit=["leaf", "dna"], theme="Vuong mien la non, ADN, kinh lup"),
    su=_S(("#b8452e", "#86301f", "#ec8b74"), ("#86301f", "#4e1a10", "#c8644e"), ("#ffe9b8", "#d9b878", "#ffffff"), "drum", "scroll", halo="drum", glow="#ffd27a", orbit=["drum"], theme="Mu long chim Lac Viet, trong dong Dong Son"),
    dia=_S(("#cfae6a", "#8f7236", "#efd9a0"), ("#2e9bd6", "#1d6f9c", "#93d0f2"), ("#fff3dc", "#dcc89c", "#ffffff"), "compass", "globe", halo="ring", glow="#bfeaff", orbit=["compass"], theme="Non nha tham hiem, la ban, qua dia cau"),
    cd=_S(("#3a3d52", "#20222f", "#8a8fb0"), ("#20222f", "#101119", "#565a78"), ("#f6f2e8", "#d4cbb8", "#ffffff"), "scales", "lawbook", halo="ring", glow="#ffe9a0", orbit=["scales"], theme="Mu quan toa den, can cong ly vang lon, sach Luat"),
    tin=_S(("#34405f", "#1c2338", "#7f8fb8"), ("#222a42", "#10152a", "#566088"), ("#7ff0ff", "#1fb0c9", "#e0ffff"), "code", "laptop", metal="silver", halo="ring", glow="#9ff4ff", orbit=["code"], theme="Ao hoodie, tai nghe, </>, laptop"),
    cn=_S(("#ef8a2a", "#bf6412", "#ffc48a"), ("#bf6412", "#7a3a08", "#f0a050"), ("#fff0d0", "#e0c898", "#ffffff"), "gear", "wrench", halo="gear", orbit=["gear"], theme="Non bao ho, banh rang, co le"),
    khoahoc=_S(("#2f4fb8", "#1c2f78", "#8fa6ee"), ("#8bc34a", "#5d8f22", "#cdee9a"), ("#f2ffd8", "#cfe0a0", "#ffffff"), "atom", "telescope", metal="gold", halo="ring", glow="#cfe8ff", orbit=["atom"], theme="Hanh tinh co vanh, ngoi sao, kinh thien van"),
    nghethuat=_S(("#e94f9a", "#b52f70", "#ffaed4"), ("#b52f70", "#7a1a4a", "#e080b0"), ("#fff0f6", "#e8c0d4", "#ffffff"), "palette", "paintbrush", halo="rainbow", glow="#ffd0ee", orbit=["palette"], theme="Bang mau, co ve"),
    kynang=_S(("#6a5cf0", "#4639b8", "#b9b2ff"), ("#4639b8", "#2a2178", "#8f86e0"), ("#f0eeff", "#cac4f0", "#ffffff"), "clock", "planner", halo="ring", glow="#d6d0ff", orbit=["clock"], theme="Dong ho bao thuc, dong ho cat, so ke hoach"),
    khmt=_S(("#19b5ea", "#0d83b0", "#8fdcf7"), ("#0d83b0", "#07506f", "#4fb4dc"), ("#f0fbff", "#c4e4f0", "#ffffff"), "flow", "laptop", halo="ring", glow="#aef0ff", orbit=["flow"], theme="{ }, so 0 1, so do thuat toan"),
    ktmt=_S(("#7a8794", "#4a5560", "#bcc7d2"), ("#4a5560", "#2a3139", "#8894a0"), ("#f2f5f8", "#ccd3da", "#ffffff"), "chip", "pcb", metal="silver", halo="ring", glow="#d0e8ff", orbit=["chip"], theme="Mu robot, an-ten, chip, bo mach"),
    httt=_S(("#2fb86a", "#1d8a4c", "#98e6b8"), ("#1d8a4c", "#0e5a30", "#5cc88a"), ("#f0fff4", "#c4e8d0", "#ffffff"), "db", "tablet", halo="ring", glow="#baffd6", orbit=["db"], theme="Chong dia co so du lieu, bang du lieu"),
    khdl=_S(("#f06292", "#c03e6e", "#ffb3cc"), ("#c03e6e", "#822044", "#e07a9c"), ("#fff0f5", "#e8c4d2", "#ffffff"), "pie", "chart", halo="ring", glow="#ffd0e0", orbit=["pie"], theme="Bieu do cot tang, bieu do tron"),
    vatli=_S(("#f08a1c", "#bf600a", "#ffc888"), ("#bf600a", "#783a04", "#e8a050"), ("#fff3de", "#e4cca0", "#ffffff"), "formula", "cradle", halo="ring", glow="#ffd9a0", orbit=["atom"], theme="Nguyen tu va electron, E=mc2, con lac Newton"),
    hoahoc=_S(("#f6f0ff", "#bfb0e0", "#ffffff"), ("#8e5ad6", "#62389e", "#cdb2f5"), ("#ffffff", "#ddd0f0", "#ffffff"), "hex", "tubes", metal="silver", halo="ring", glow="#e0ccff", orbit=["hex"], theme="Phan tu benzen, ong nghiem"),
    kinhte=_S(("#e6b422", "#b08410", "#ffe58a"), ("#1f7a4a", "#0e4a2a", "#5cc088"), ("#fff6d8", "#e4d098", "#ffffff"), "coin", "coins", halo="ring", orbit=["coin"], theme="Mu chong den, dong xu vang"),
    ketoan=_S(("#8c7ae6", "#6252b8", "#cfc6fb"), ("#6252b8", "#3c3080", "#9a8ce0"), ("#f6f2ff", "#d4cdf0", "#ffffff"), "ledger", "calctape", halo="ring", glow="#e4ddff", orbit=["ledger"], theme="Mu che nang xanh, but chi, con dau, may tinh voi bang giay, so cai"),
    daicuong=_S(("#3a4552", "#232a33", "#8a96a5"), ("#232a33", "#12161c", "#5c6878"), ("#f0f2f5", "#c8ced6", "#ffffff"), "books", "bookstack", halo="ring", glow="#ffe9a0", orbit=["books"], theme="Mu cu nhan co tua vang, chong sach cao"),
)

_patched = set()


class Kit:
    def __init__(self, ch, H, subject, stage):
        self.ch, self.H, self.subject, self.stage = ch, H, subject, stage
        self.spec = SPEC[subject]; self.st = self.spec["stages"][stage]
        self.s = ch.s; self.chick = stage == 1
        self.hc, self.rh, self.bc, self.rb = ch.hc, ch.rh, ch.bc, ch.rb
        s = self.s
        self.Rh = (self.rh, self.rh * (0.96 if self.chick else 0.95), self.rh * (0.94 if self.chick else 0.93))
        self.Rb = (self.rb, self.rb * 0.95, self.rb * 1.02)
        sp = self.spec
        sx = "_" + subject; self.m_main = H.toon("c_main" + sx, *sp["main"]); self.m_deep = H.toon("c_deep" + sx, *sp["deep"])
        metal = self.st["metal"]
        self.m_metal = H.toon("c_" + metal, *({"gold": ("#ffcf3d", "#c98a0e", "#fff3b0"), "silver": ("#eef3fa", "#8793a8", "#ffffff")}[metal]))
        self.m_gold = H.toon("c_gold", "#ffcf3d", "#c98a0e", "#fff3b0")
        self.m_red = H.toon("comb", "#ff3d3d", "#c22a2a", "#ff8a8a")
        self.m_ink = H.toon("c_ink", "#3a2f4a", "#1e1828", "#7a6f8c")
        self.m_leather = self.fab("c_leather", "#b9794a", "#7a4a26", "#e8b27c", "leather", 0.5, 0.35)
        self.m_cream = H.toon("c_cream" + sx, *sp["cream"]); self.hat_top = self.hc.z + self.Rh[2] + 0.2 * self.s

    # ---- materials ----------------------------------------------------------------------------------------------------
    def fab(self, name, lit, shade, hi, tex=None, scale=0.5, amt=0.4):
        name = name + "_" + self.subject
        m = self.H.toon(name, lit, shade, hi)
        if tex and name not in _patched:
            _patched.add(name); tp = os.path.join(TEXDIR, tex + "-d.png")
            if os.path.exists(tp):
                nt = m.node_tree; n = nt.nodes
                add = next(x for x in n if x.type == "MIX_RGB" and x.blend_type == "ADD")
                src = add.inputs[1].links[0].from_socket
                im = bpy.data.images.get(tex + "-d.png") or bpy.data.images.load(tp); im.colorspace_settings.name = "Non-Color"
                ti = n.new("ShaderNodeTexImage"); ti.image = im; ti.interpolation = "Cubic"; ti.projection = "BOX"; ti.projection_blend = 0.35
                mp = n.new("ShaderNodeMapping"); mp.inputs["Scale"].default_value = (scale,) * 3
                nt.links.new(n.new("ShaderNodeTexCoord").outputs["Object"], mp.inputs[0]); nt.links.new(mp.outputs[0], ti.inputs["Vector"])
                ov = n.new("ShaderNodeMixRGB"); ov.blend_type = "OVERLAY"; ov.inputs[0].default_value = amt
                nt.links.new(src, ov.inputs[1]); nt.links.new(ti.outputs["Color"], ov.inputs[2]); nt.links.new(ov.outputs[0], add.inputs[1])
        return m

    # ---- geometry helpers -----------------------------------------------------------------------------------------------
    def surf(self, C, R, phi, zu, lift=0.0, fl=None):
        r = math.sqrt(max(0.0, 1 - zu * zu)); a = math.radians(phi); k = fl(zu) if fl else 1.0
        p = Vector((r * math.cos(a) * R[0] * k, r * math.sin(a) * R[1] * k, zu * R[2]))
        n = Vector((r * math.cos(a) / R[0], r * math.sin(a) / R[1], zu / R[2])).normalized()
        return Vector(C) + p + n * lift, n

    def tube(self, name, pts, r, mat, closed=False, outline=0.012, sides=8, sub=1):
        bm = bmesh.new(); M = len(pts); rings = []
        for i, p in enumerate(pts):
            t = (pts[(i + 1) % M] - pts[(i - 1) % M]) if closed else (pts[min(i + 1, M - 1)] - pts[max(i - 1, 0)])
            t = t.normalized(); up = Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))
            n1 = t.cross(up).normalized(); n2 = t.cross(n1).normalized()
            ri = r(i / max(M - 1, 1)) if callable(r) else r
            rings.append([bm.verts.new(p + (n1 * math.cos(k / sides * 2 * math.pi) + n2 * math.sin(k / sides * 2 * math.pi)) * ri) for k in range(sides)])
        for i in range(M if closed else M - 1):
            a, b = rings[i], rings[(i + 1) % M]
            for k in range(sides): bm.faces.new((a[k], a[(k + 1) % sides], b[(k + 1) % sides], b[k]))
        if not closed:
            bm.faces.new(rings[0][::-1]); bm.faces.new(rings[-1])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        o = self.H.mesh_obj(name, bm)
        return self.H.finish(o, mat, outline, subsurf=sub)

    def ring(self, name, C, R, zu, lift, r, mat, a0=0, a1=360, n=48, outline=0.012, zdrop=None, fl=None):
        pts = []
        for i in range(n + 1 if a1 - a0 < 360 else n):
            ph = a0 + (a1 - a0) * i / n
            z = zu if zdrop is None else zu + zdrop(ph)
            pts.append(self.surf(C, R, ph, z, lift, fl)[0])
        return self.tube(name, pts, r, mat, closed=(a1 - a0 >= 360), outline=outline)

    def shell(self, name, C, R, mat, zr=(-1, 1), flare=None, gap=None, keep=False, back=None, thick=0.05, ol=0.016, rot=(0, 0, 0), seg=(48, 24), front_only=None):
        """a clipped, thickened piece of an ellipsoid: a hat dome, a coat, a cape. gap = planes (co, no) removing a front wedge (keep=True keeps only it)."""
        bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=seg[0], v_segments=seg[1], radius=1.0)
        G = lambda: bm.verts[:] + bm.edges[:] + bm.faces[:]
        if zr[1] < 1: bmesh.ops.bisect_plane(bm, geom=G(), plane_co=(0, 0, zr[1]), plane_no=(0, 0, 1), clear_outer=True)
        if zr[0] > -1: bmesh.ops.bisect_plane(bm, geom=G(), plane_co=(0, 0, zr[0]), plane_no=(0, 0, 1), clear_inner=True)
        if back is not None: bmesh.ops.bisect_plane(bm, geom=G(), plane_co=(0, back, 0), plane_no=(0, 1, 0), clear_inner=True)
        if gap:
            for co, no in gap: bmesh.ops.bisect_plane(bm, geom=G(), plane_co=co, plane_no=no)
            kill = []
            for f in bm.faces:
                c = f.calc_center_median(); ins = c.y < 0 and all((c - Vector(co)).dot(Vector(no)) > 0 for co, no in gap)
                if ins != keep: kill.append(f)
            bmesh.ops.delete(bm, geom=kill, context="FACES")
        if flare:
            for v in bm.verts:
                k = flare(v.co.z); v.co.x *= k; v.co.y *= k
        o = self.H.mesh_obj(name, bm); o.location = C; o.scale = R; o.rotation_euler = rot
        mean = sum(R) / 3
        so = o.modifiers.new("th", "SOLIDIFY"); so.thickness = thick / mean; so.offset = 1
        return self.H.finish(o, mat, ol / max(R), subsurf=1)

    def poly(self, name, loop, depth, mat, outline=0.012, sub=0, bevel=0.0):
        """a flat shape from a closed outline (list of Vectors in the xz plane), extruded in y"""
        bm = bmesh.new(); vs = [bm.verts.new(p) for p in loop]; bm.faces.new(vs)
        o = self.H.mesh_obj(name, bm)
        so = o.modifiers.new("th", "SOLIDIFY"); so.thickness = depth; so.offset = 0
        if bevel:
            bv = o.modifiers.new("bev", "BEVEL"); bv.width = bevel; bv.segments = 2
        return self.H.finish(o, mat, outline, subsurf=sub)

    def solid(self, kind, name, loc, size, mat, rot=(0, 0, 0), outline=0.01):
        bm = bmesh.new()
        if kind == "cube": bmesh.ops.create_cube(bm, size=1.0)
        elif kind == "octa":
            bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1.0)
            bmesh.ops.delete(bm, geom=bm.verts[:], context="VERTS") if False else None
        elif kind == "tetra":
            vs = [bm.verts.new(p) for p in ((1, 1, 1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1))]
            for a, b, c in ((0, 1, 2), (0, 3, 1), (0, 2, 3), (1, 3, 2)): bm.faces.new((vs[a], vs[b], vs[c]))
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        elif kind == "ico": bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1.0)
        elif kind == "diamond":
            top, bot = bm.verts.new((0, 0, 1.2)), bm.verts.new((0, 0, -1.2)); eq = [bm.verts.new((math.cos(a * math.pi / 2), math.sin(a * math.pi / 2), 0)) for a in range(4)]
            for i in range(4): bm.faces.new((eq[i], eq[(i + 1) % 4], top)); bm.faces.new((eq[(i + 1) % 4], eq[i], bot))
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        o = self.H.mesh_obj(name, bm); o.location = loc; o.scale = (size,) * 3 if not isinstance(size, tuple) else size; o.rotation_euler = rot
        o.data.materials.append(mat); o.data.materials.append(self.H.outline_mat())
        so = o.modifiers.new("ol", "SOLIDIFY"); so.thickness = outline / (size if not isinstance(size, tuple) else max(size)); so.offset = 1; so.use_flip_normals = True; so.material_offset = 1; so.use_rim = False
        for p in o.data.polygons: p.use_smooth = False
        return o

    def plus(self, loc, k, outline=0.012):
        H = self.H
        a = H.rbox("plus_h", loc, (0.46 * k, 0.16 * k, 0.16 * k), self.m_red); b = H.rbox("plus_v", loc, (0.16 * k, 0.16 * k, 0.46 * k), self.m_red)
        return a, b

    def yaw(self, d): return (0, 0, math.atan2(d.x, -d.y))

    # ---- head pieces ------------------------------------------------------------------------------------------------------
    def head(self):
        H, s, hc, rh = self.H, self.s, self.hc, self.rh; kind = self.st["head"]; ch = self.ch
        if kind == "gunny":
            import gunny; gunny.HATS[self.subject](self, self.stage); return
        blue = self.fab("c_knit_b", *self.spec["main"], tex="knit", scale=0.4, amt=0.45)
        cream_k = self.fab("c_knit_c", *self.spec["cream"], tex="knit", scale=0.4, amt=0.4)
        wool = self.fab("c_wool_d", *self.spec["deep"], tex="wool", scale=1.5, amt=0.55)
        Rh = self.Rh
        if kind == "beanie":
            R = (Rh[0] * 1.08, Rh[1] * 1.08, Rh[2] * 1.16); zu = 0.5
            ch.addh(self.shell("beanie", hc, R, blue, zr=(zu, 1), thick=0.07 * s, ol=0.02, seg=(56, 28)))
            ch.addh(self.ring("cuff", hc, R, zu, 0.03 * s, 0.1 * s, cream_k, outline=0.014, n=56))
            for o in self.plus(hc + Vector((0, 0.03 * s, R[2] * 0.97 + 0.14 * s)), 0.62 * s): ch.addh(o)
            # a few silver-white stitched diamonds on the beanie, like a knitted pattern
            for ph in (-130, -90, -50):
                p, n = self.surf(hc, R, ph, 0.78, 0.075 * s)
                ch.addh(self.solid("diamond", "stitch", p, 0.045 * s, cream_k, rot=(math.pi / 2 - math.asin(max(-1, min(1, n.z))) * 0 , 0, math.atan2(n.x, -n.y)), outline=0.006))
        elif kind == "cap":
            R = (Rh[0] * 1.06, Rh[1] * 1.06, Rh[2] * 1.08); zu = 0.46
            ch.addh(self.shell("cap", hc, R, blue if False else wool, zr=(zu, 1), thick=0.08 * s, ol=0.02, seg=(56, 28)))
            band = self.fab("c_band", *self.spec["cream"], tex=None)
            ch.addh(self.ring("capband", hc, R, zu, 0.03 * s, 0.07 * s, band, outline=0.012, n=56))
            # ruler ticks on the band
            for k in range(36):
                ph = k * 10; long = k % 3 == 0
                p, n = self.surf(hc, R, ph, zu, 0.085 * s)
                if (ph % 360) > 180 and False: continue
                o = H.rbox("tick", p, (0.022 * s, 0.05 * s, (0.075 if long else 0.045) * s), self.m_metal, outline=0.004)
                o.rotation_euler = (0, 0, math.radians(ph + 90)); ch.addh(o)
            # a short brim in front, slightly tilted down
            bp, bn = self.surf(hc, R, -90, zu + 0.06, 0.02 * s)
            br = H.ball("brim", bp + Vector((0, -0.1 * s, -0.04 * s)), (Rh[0] * 0.6, Rh[1] * 0.42, 0.05 * s), self.m_deep, rot=(0.12, 0, 0), outline=0.016); ch.addh(br)
            top = hc + Vector((0, 0.03 * s, R[2] * 0.99 + 0.11 * s))
            for o in self.plus(top, 0.58 * s): ch.addh(o)
        elif kind == "tam":
            R = (Rh[0] * 1.07, Rh[1] * 1.05, Rh[2] * 0.62); C = hc + Vector((0.06 * s, 0.03 * s, Rh[2] * 0.7))
            ch.addh(self.shell("tam", C, R, wool, zr=(-0.15, 1), thick=0.07 * s, ol=0.02, rot=(0, 0.16, 0), seg=(56, 28)))
            for o in (self.ring("tamband", C, R, -0.15, 0.03 * s, 0.065 * s, self.m_gold, outline=0.012, n=56),): ch.addh(o)
            # gold compass pin at the front: two legs, a hinge and an arc
            fp, fn = self.surf(C, R, -90, 0.45, 0.06 * s)
            ch.addh(self.compass(fp + Vector((0, -0.04 * s, 0)), 0.34 * s))
            for o in self.plus(C + Vector((0.0, 0.0, R[2] * 0.98 + 0.10 * s)), 0.5 * s): ch.addh(o)
        elif kind == "tall":
            base_z = hc.z + Rh[2] * 0.46; hh = 0.78 * rh; r0 = Rh[0] * 0.93
            ctr = Vector((hc.x, hc.y + 0.03 * s, base_z))
            wool4 = self.fab("c_wool_r", *self.spec["deep"], tex="wool", scale=1.5, amt=0.55)
            tab = [(1.0, 0.0), (0.95, 0.2), (0.94, 0.45), (1.02, 0.72), (1.14, 0.92), (1.2, 1.0)]
            prof = [(r0 * a, hh * b) for a, b in tab]
            ch.addh(self.lathe("crown", ctr, prof, wool4, k=0.97)); rt = r0 * 1.2
            rr = lambda h: r0 * float(__import__("numpy").interp(h / hh, [b for a, b in tab], [a for a, b in tab]))
            def band(h, r_, mat, extra=0.02, n=56, k=0.97): return self.tube("crownband", [ctr + Vector((math.cos(a) * (rr(h) + extra * s), math.sin(a) * (rr(h) + extra * s) * k, h)) for a in [i / n * 2 * math.pi for i in range(n)]], r_, mat, closed=True, outline=0.014)
            ch.addh(band(0.0, 0.06 * s, self.m_gold)); ch.addh(band(hh * 0.5, 0.035 * s, self.m_gold, 0.01))
            ch.addh(band(hh * 0.98, 0.07 * s, self.m_gold, 0.03)); ch.addh(band(hh * 0.86, 0.04 * s, self.m_cream, 0.02))
            # gold spikes round the front of the rim
            for ang in range(-170, 11, 20):
                a = math.radians(ang); p = ctr + Vector((math.cos(a) * (rt + 0.02 * s), math.sin(a) * (rt + 0.02 * s) * 0.97, hh + 0.03 * s))
                big = ang % 40 == 10 or ang == -90
                sp = H.cone("spike", p + Vector((0, 0, 0.12 * s)), 0.06 * s, 0.24 * s * (1.3 if ang == -90 else 1.0), self.m_gold, (0, 0, 0), outline=0.008); ch.addh(sp)
            # a jewel set in gold on the front, and a red plus gem on top
            gem = H.toon("c_gem", "#7fb6ff", "#2d62c8", "#ffffff")
            h = hh * 0.55; fp = ctr + Vector((0, -(rr(h) * 0.97) - 0.05 * s, h))
            ch.addh(H.ball("gemset", fp, (0.17 * s, 0.07 * s, 0.17 * s), self.m_gold, outline=0.01))
            ch.addh(self.solid("diamond", "gem", fp + Vector((0, -0.06 * s, 0)), (0.1 * s, 0.07 * s, 0.13 * s), gem, outline=0.006))
            for ang in range(-150, -29, 30):
                a = math.radians(ang); h2 = hh * 0.2
                p = ctr + Vector((math.cos(a) * (rr(h2) + 0.06 * s), math.sin(a) * (rr(h2) + 0.06 * s) * 0.97, h2))
                ch.addh(self.solid("diamond", "hd", p, (0.05 * s, 0.035 * s, 0.075 * s), self.m_gold, rot=(0, 0, math.radians(ang + 90)), outline=0.006))
            top = ctr + Vector((0, 0.0, hh + 0.12 * s))
            ch.addh(H.ball("gemset2", top, (0.15 * s,) * 3, self.m_gold, outline=0.01))
            for o in self.plus(top + Vector((0, -0.08 * s, 0.12 * s)), 0.5 * s): ch.addh(o)
            self.hat_top = top
        if self.subject == "toan":
            import gunny; gunny.pi_top(self, self.stage)

    def lathe(self, name, C, prof, mat, n=40, k=1.0, outline=0.02):
        """a surface of revolution: prof = [(radius, height)] from the base up, closed by a flat top"""
        bm = bmesh.new(); rings = []
        for r_, h in prof:
            rings.append([bm.verts.new(C + Vector((math.cos(i / n * 2 * math.pi) * r_, math.sin(i / n * 2 * math.pi) * r_ * k, h))) for i in range(n)])
        for j in range(len(rings) - 1):
            for i in range(n): bm.faces.new((rings[j][i], rings[j][(i + 1) % n], rings[j + 1][(i + 1) % n], rings[j + 1][i]))
        bm.faces.new(rings[-1][::-1]); bm.faces.new(rings[0])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        o = self.H.mesh_obj(name, bm)
        return self.H.finish(o, mat, outline, subsurf=1)

    def compass(self, p, size):
        H = self.H; legs = []
        top = p + Vector((0, 0, size * 0.6))
        for sx in (-1, 1):
            foot = p + Vector((sx * size * 0.42, -0.0, -size * 0.55))
            legs.append(self.tube("clegs", [top, (top + foot) / 2, foot], size * 0.075, self.m_metal, outline=0.006, sides=6))
        hinge = H.ball("chinge", top, (size * 0.12,) * 3, self.m_gold, outline=0.006)
        arc = self.tube("carc", [p + Vector((math.cos(a) * size * 0.34, -0.01, -size * 0.15 + math.sin(a) * size * 0.06)) for a in [math.radians(x) for x in (210, 240, 270, 300, 330)]], size * 0.04, self.m_gold, outline=0.004, sides=6)
        root = H.link(bpy.data.objects.new("compass", None))
        for o in legs + [hinge, arc]: o.parent = root
        # the parts hold world positions; the root sits at the origin, so the group keeps them
        return root

    def protractor(self, p, r, mat, ink, back=None, n=28):
        """a flat half-disc ring with tick marks, facing the viewer (-y)"""
        H = self.H; root = H.link(bpy.data.objects.new("protractor", None))
        outer = [Vector((math.cos(math.radians(a)) * r, 0, math.sin(math.radians(a)) * r)) for a in range(0, 181, 10)]
        inner = [Vector((math.cos(math.radians(a)) * r * 0.58, 0, math.sin(math.radians(a)) * r * 0.58)) for a in range(180, -1, -10)]
        d = self.poly("prot", [p + v for v in outer + inner], 0.05 * r * 2, mat, outline=0.01, bevel=0.01)
        d.parent = root
        for a in range(0, 181, 15):
            c, sn = math.cos(math.radians(a)), math.sin(math.radians(a)); rr = r * (0.8 if a % 45 == 0 else 0.86)
            t = H.rbox("ptick", p + Vector((c * rr, -0.045 * r, sn * rr)), (0.02 * r * 2 if a % 45 else 0.03 * r * 2, 0.02 * r, r * 0.14 if a % 45 else r * 0.2), ink, outline=0.0)
            t.rotation_euler = (0, -math.radians(a - 90), 0); t.parent = root
        base = H.rbox("pbase", p + Vector((0, 0, -0.02 * r)), (r * 2.12, 0.1 * r, r * 0.1), mat, outline=0.008); base.parent = root
        return root

    # ---- body pieces ------------------------------------------------------------------------------------------------------
    def top(self):
        H, s, ch, bc, Rb, rb = self.H, self.s, self.ch, self.bc, self.Rb, self.rb; kind = self.st["top"]
        cream_k = self.fab("c_knit_c", *self.spec["cream"], tex="knit", scale=0.4, amt=0.4)
        blue = self.fab("c_knit_b", *self.spec["main"], tex="knit", scale=0.4, amt=0.45)
        wool = self.fab("c_wool_m", *self.spec["main"], tex="wool", scale=1.5, amt=0.55)
        coatm = self.fab("c_coat", *self.spec["main"], tex="brocade", scale=0.9, amt=0.3)
        woolD = self.fab("c_wool_d", *self.spec["deep"], tex="wool", scale=1.5, amt=0.55)
        brocade = self.fab("c_brocade", *self.spec["cream"], tex="brocade", scale=0.7, amt=0.5)
        hc, rh = self.hc, self.rh
        def Vline(wtop, zt, zb):  # planes for a V opening: wide wtop at zu=zt narrowing to a point at zu=zb (unit-sphere coords)
            def pl(sx):
                a = Vector((sx * wtop, 0, zt)); b = Vector((0, 0, zb)); d = a - b; nrm = Vector((-d.z * sx, 0, d.x * sx))  # inside = between the lines
                nrm = Vector((-d.z, 0, d.x)) if sx > 0 else Vector((d.z, 0, -d.x))
                return (tuple(b), tuple(nrm))
            return [pl(-1), pl(1)]
        if kind == "bib":  # the chick: a small bib on its chest, tied at the neck
            Rh_ = self.Rh
            d = Vector((0, -0.74, -0.67)).normalized(); c = hc + Vector((d.x * Rh_[0], d.y * Rh_[1], d.z * Rh_[2])) * 0.99
            ch.add(H.ball("bib", c, (0.34 * s, 0.07 * s, 0.3 * s), blue, rot=H.face_rot(d), outline=0.014))
            u1 = Vector((1, 0, 0)); u2 = Vector((0, d.z, -d.y)); u2 = -u2 if u2.z < 0 else u2
            ch.add(self.tube("bibedge", [c + u1 * math.cos(a) * 0.34 * s + u2 * math.sin(a) * 0.3 * s + d * 0.05 * s for a in [i / 36 * 2 * math.pi for i in range(36)]], 0.03 * s, cream_k, closed=True, outline=0.008))
            if True:
                import gunny; gunny.chest(self, self.spec["emblem"], c + Vector((0, -0.17 * s, 0.02 * s)), 0.17 * s, 1)
            tri = [Vector((-0.13 * s, 0, 0.08 * s)), Vector((0.13 * s, 0, 0.08 * s)), Vector((0, 0, -0.13 * s))]
            t = self.poly("bibtri", tri, 0.02 * s, cream_k, outline=0.006, bevel=0.004)
            t.location = c + d * 0.075 * s; t.rotation_euler = (0.85, 0, 0); ch.add(t)
            tp, tn = self.surf(hc, Rh_, -90, -0.5, 0.05 * s)
            ch.add(self.ring("tie", hc, Rh_, -0.5, 0.03 * s, 0.04 * s, self.m_main, outline=0.01, n=48))
            ch.add(self.tube("bibstrap", [tp, (tp + c + u2 * 0.2 * s) / 2 + d * 0.04 * s, c + u2 * 0.28 * s], 0.03 * s, self.m_main, outline=0.006, sides=5))
            for sx in (-1, 1):
                b = H.cone("bow", tp + Vector((sx * 0.09 * s, -0.03 * s, 0)), 0.1 * s, 0.2 * s, cream_k, (0, math.radians(90 * sx), 0)); b.scale = (1, 1.2, 0.5); ch.add(b)
            ch.add(H.ball("bowknot", tp + Vector((0, -0.03 * s, 0)), (0.045 * s,) * 3, cream_k, outline=0.006))
            return
        # adult bodies: neckline height and the vest / coat / robe shell
        if kind == "vest":
            R = tuple(x * 1.11 for x in Rb)
            ch.add(self.shell("vest", bc, R, wool, zr=(-0.62, 0.68), gap=Vline(0.42, 0.68, -0.15), thick=0.06 * s, ol=0.018, seg=(64, 32)))
            for o in self.hem_ruler(R, -0.62, wool): ch.add(o)
            # silver piping down both edges of the V
            for sx in (-1, 1):
                pts = [self.surf(bc, R, -90 + sx * math.degrees(math.asin(min(1, (0.42 * (z + 0.15) / 0.83) / math.sqrt(max(1e-4, 1 - z * z))))), z, 0.06 * s)[0] for z in [0.68 - i * 0.083 for i in range(11)]]
                ch.add(self.tube("pipe", pts, 0.035 * s, self.m_metal, outline=0.008, sides=6))
            for i, z in enumerate((-0.2, -0.38)):
                p, n = self.surf(bc, R, -90, z, 0.07 * s); ch.add(H.ball("button", p, (0.06 * s,) * 3, self.m_metal, outline=0.008))
        elif kind in ("coat", "robe"):
            robe = kind == "robe"
            R = tuple(x * (1.11 if robe else 1.08) for x in Rb)
            wk, hk, zh = (0.06, 0.3, -0.55) if robe else (0.08, 0.27, -0.5)
            def fl(z):  # chest 1.0, a fitted waist at -0.1, then the skirt flares to the hem
                if z > 0.25: return 1.0
                if z > -0.1: return 1.0 - wk * (0.25 - z) / 0.35
                return 1.0 - wk + hk * min(1.0, (-0.1 - z) / (-0.1 - zh)) ** 0.85
            def vedge(R_, wtop, zt, zb, sx, lift, n=12):
                pts = []
                for i in range(n + 1):
                    z = zt - (zt - zb) * i / n; w = wtop * (z - zb) / (zt - zb)
                    pts.append(self.surf(bc, R_, -90 + sx * math.degrees(math.asin(min(1, w / math.sqrt(max(1e-4, 1 - z * z))))), z, lift, fl)[0])
                return pts
            mat = woolD if robe else coatm
            if not robe:
                zb, wt = -0.3, 0.42
                ch.add(self.shell("coat", bc, R, mat, zr=(zh, 0.7), gap=Vline(wt, 0.7, zb), flare=fl, thick=0.07 * s, ol=0.02, seg=(64, 40)))
                for sx in (-1, 1):
                    ch.add(self.tube("pipe", vedge(R, wt, 0.7, zb, sx, 0.07 * s), 0.04 * s, self.m_gold, outline=0.008, sides=6))
                    b, nin = Vline(wt, 0.7, zb)[0 if sx < 0 else 1]; nv = Vector(nin); out = -nv.normalized() * 0.15
                    b2 = tuple(Vector(b) + out)
                    ch.add(self.shell("lapel", bc, tuple(x * 1.14 for x in Rb), self.m_cream, zr=(-0.12, 0.74), gap=[(b, tuple(-nv)), (b2, tuple(nv))], keep=True, flare=fl, thick=0.04 * s, ol=0.016, seg=(64, 40)))
            else:
                ch.add(self.shell("robe", bc, R, mat, zr=(zh, 0.72), flare=fl, thick=0.08 * s, ol=0.022, seg=(64, 40)))
                R2 = tuple(x * 1.145 for x in Rb)
                gap = [((-0.22, 0, 0), (1, 0, 0)), ((0.22, 0, 0), (-1, 0, 0))]
                ch.add(self.shell("panel", bc, R2, brocade, zr=(zh, 0.72), gap=gap, keep=True, flare=fl, thick=0.06 * s, ol=0.0, seg=(96, 40)))
                for sx in (-1, 1):
                    pts = [self.surf(bc, R2, -90 + sx * math.degrees(math.asin(0.22 / math.sqrt(max(1e-4, 1 - z * z)))), z, 0.075 * s, fl)[0] for z in [0.72 - i * (0.72 - zh - 0.03) / 15 for i in range(16)]]
                    ch.add(self.tube("border", pts, 0.04 * s, self.m_gold, outline=0.01, sides=6))
                for z in (0.5, 0.26, -0.36):
                    p, n = self.surf(bc, R2, -90, z, 0.095 * s, fl)
                    ch.add(self.solid("diamond", "pdia", p, (0.085 * s, 0.05 * s, 0.1 * s), self.m_gold, rot=(-0.25, 0, 0), outline=0.008))
            for o in self.hem_ruler(R, zh, woolD, flare=fl, teeth=True): ch.add(o)
            ch.add(self.ring("belt", bc, R, -0.1, 0.06 * s, 0.065 * s, self.m_gold, outline=0.012, n=64, fl=fl))
            bp, bn = self.surf(bc, R, -90, -0.1, 0.12 * s, fl)
            ch.add(H.rbox("buckle", bp, (0.17 * s, 0.05 * s, 0.15 * s), self.m_gold, outline=0.008))
            ch.add(H.rbox("buckin", bp + Vector((0, -0.03 * s, 0)), (0.09 * s, 0.03 * s, 0.08 * s), self.m_ink, outline=0.0))
            for ang in (-155, -132, -112, -68, -48, -25):
                zs = [-0.16 - i * (zh + 0.04 + 0.16) / -7 for i in range(8)]
                pts = [self.surf(bc, R, ang, z, 0.05 * s, fl)[0] for z in zs]
                ch.add(self.tube("fold", pts, 0.022 * s, self.m_deep if not robe else self.m_ink, outline=0.0, sides=5, sub=0))

    def hem_ruler(self, R, zu, mat, flare=None, teeth=False):
        """gold / silver hem trim: a band, plus ruler ticks (vest) or a row of triangles (coat, robe)"""
        s = self.s; bc = self.bc; out = []; k = flare(zu) if flare else 1
        R2 = (R[0] * k, R[1] * k, R[2])
        out.append(self.ring("hemband", bc, R2, zu, 0.045 * s, 0.062 * s, self.m_metal, outline=0.012, n=64))
        if teeth:
            for i in range(30):
                ph = i * 12
                if 10 < ph < 170: continue  # the back is hidden behind the body anyway
                p, n = self.surf(bc, R2, ph, zu - 0.02, 0.06 * s)
                t = self.solid("tetra", "tooth", p + Vector((0, 0, -0.045 * s)), 0.058 * s, self.m_metal, rot=(math.pi, 0, math.radians(ph)), outline=0.005); out.append(t)
        else:
            for i in range(30):
                ph = i * 12
                if 10 < ph < 170: continue
                p, n = self.surf(bc, R2, ph, zu + 0.12, 0.065 * s)
                o = self.H.rbox("tick", p, (0.022 * s, 0.03 * s, (0.1 if i % 3 == 0 else 0.06) * s), self.m_metal, outline=0.004); o.rotation_euler = (0, 0, math.radians(ph + 90)); out.append(o)
        return out

    def back(self):
        H, s, ch, bc, Rb, rb = self.H, self.s, self.ch, self.bc, self.Rb, self.rb; kind = self.st["back"]
        if not kind: return
        if kind == "satchel":
            # a leather strap round the body on a diagonal, and a bag on the right hip
            pts = [self.surf(bc, tuple(x * 1.075 for x in Rb), ph, 0.12 + 0.5 * math.cos(math.radians(ph + 130)), 0.0)[0] for ph in range(-180, 180, 8)]
            ch.add(self.tube("strap", pts, 0.05 * s, self.m_leather, closed=True, outline=0.012, sides=6))
            p, n = self.surf(bc, tuple(x * 1.075 for x in Rb), -35, -0.38, 0.1 * s)
            bag = H.rbox("bag", p + Vector((0.0, -0.02 * s, 0)), (0.34 * s, 0.2 * s, 0.3 * s), self.m_leather, rot=self.yaw(n)); ch.add(bag)
            flap = H.rbox("flap", p + n * 0.13 * s + Vector((0, 0, 0.06 * s)), (0.36 * s, 0.07 * s, 0.17 * s), self.m_leather, rot=self.yaw(n)); ch.add(flap)
            ch.add(H.ball("clasp", p + n * 0.18 * s + Vector((0, 0, 0.0)), (0.05 * s, 0.025 * s, 0.05 * s), self.m_metal, rot=self.yaw(n), outline=0.006))
        elif kind in ("cape", "cape_long"):
            long = kind == "cape_long"
            R = (Rb[0] * 1.5, Rb[1] * 1.45, Rb[2] * 1.14)
            fl = lambda z: 1 + (0.4 if long else 0.3) * max(0, (-0.1 - z)) / 0.7
            zlo = -0.92 if long else -0.52
            outer = self.fab("c_cape_o", *self.spec["deep"], tex="wool", scale=0.9, amt=0.3)
            capeC = bc + Vector((0, 0.1 * s, -0.02 * s))
            ch.add(self.shell("cape", capeC, R, outer, zr=(zlo, 0.62), flare=fl, back=-0.3, thick=0.05 * s, ol=0.02, seg=(64, 32)))
            k = fl(zlo); R2 = (R[0] * k, R[1] * k, R[2])
            ch.add(self.ring("capeedge", capeC, R2, zlo, 0.03 * s, 0.05 * s, self.m_gold, a0=-30, a1=210, n=60, outline=0.012))

    def mantle(self):
        """a shoulder drape over the top of the body (the wings hang free below it)"""
        H, s, ch, bc, Rb = self.H, self.s, self.ch, self.bc, self.Rb
        long = self.st["back"] == "cape_long"
        R = (Rb[0] * 1.16, Rb[1] * 1.14, Rb[2] * 1.1)
        fl = lambda z: 1 + 0.12 * max(0, (0.64 - z)) / 0.14
        mat = self.fab("c_mant4", "#fff3d6", "#d9c39a", "#ffffff", tex="brocade", scale=0.8, amt=0.4) if long else self.fab("c_mant3", *self.spec["deep"], tex="wool", scale=1.5, amt=0.55)
        gap = [((-0.3, 0, 0), (1, 0, 0)), ((0.3, 0, 0), (-1, 0, 0))]
        ch.add(self.shell("mantle", bc, R, mat, zr=(0.5, 0.8), gap=gap, flare=fl, thick=0.05 * s, ol=0.02, seg=(64, 32)))
        ch.add(self.ring("mantedge", bc, R, 0.5, 0.045 * s, 0.032 * s, self.m_gold, a0=-71, a1=251, n=56, outline=0.012, fl=fl))

    # ---- shoes, cuffs, face and the rest -----------------------------------------------------------------------------------------
    def feet(self):
        H, s, kind = self.H, self.s, self.st["feet"]
        leather = self.fab("c_boot", *({"booties": self.spec["main"], "shoes": self.spec["deep"], "boots": self.spec["deep"], "gilded": ("#fff3d6", "#d9c39a", "#ffffff")}[kind]), tex="leather", scale=0.7, amt=0.25)
        for fp, sx in self.ch.parts["feet"]:
            def onfoot(o): o.parent = fp; o.location = o.location - fp.location; return o
            if kind == "booties":
                onfoot(H.ball("bootie", Vector((0.27 * sx * s, -0.12 * s, 0.07 * s)), (0.15 * s, 0.17 * s, 0.1 * s), leather, outline=0.012))
            else:
                big = kind in ("boots", "gilded")
                onfoot(H.ball("shoe", Vector((0.27 * sx * s, -0.12 * s, 0.085 * s)), (0.17 * s, 0.25 * s, 0.12 * s), leather, outline=0.014))
                onfoot(H.ball("shoeheel", Vector((0.27 * sx * s, 0.06 * s, 0.1 * s)), (0.15 * s, 0.14 * s, 0.13 * s), leather, outline=0.012))
                onfoot(self.tube("shoeband", [Vector((0.27 * sx * s + math.cos(a) * 0.145 * s, 0.04 * s + math.sin(a) * 0.15 * s, 0.17 * s)) for a in [i / 20 * 2 * math.pi for i in range(20)]], 0.04 * s, self.m_cream if kind != "gilded" else self.m_gold, closed=True, outline=0.008, sub=1))
                if big: onfoot(H.cyl("legwrap", Vector((0.27 * sx * s, 0.04 * s, 0.24 * s)), 0.1 * s, 0.14 * s, self.m_cream, outline=0.012))
                cap = self.m_metal if kind != "shoes" else self.m_cream
                onfoot(H.ball("toecap", Vector((0.27 * sx * s, -0.28 * s, 0.075 * s)), (0.12 * s, 0.1 * s, 0.085 * s), cap if big else leather, outline=0.01))
                if big:
                    onfoot(H.rbox("buckle", Vector((0.27 * sx * s, -0.17 * s, 0.185 * s)), (0.08 * s, 0.05 * s, 0.07 * s), self.m_gold, outline=0.006))

    def wing_cuffs(self):
        H, s = self.H, self.s
        for piv, sx in self.ch.parts["wings"]:
            R = lambda a: Vector((sx * 0.05 * s + math.cos(a) * 0.185 * s, math.sin(a) * 0.4 * s, -0.5 * s))
            t = self.tube("wingcuff", [R(i / 28 * 2 * math.pi) for i in range(28)], 0.065 * s, self.m_gold, closed=True, outline=0.012)
            t.parent = piv
            t2 = self.tube("wingcuff2", [R(i / 28 * 2 * math.pi) + Vector((0, 0, 0.1 * s)) for i in range(28)], 0.04 * s, self.m_cream, closed=True, outline=0.01)
            t2.parent = piv

    def epaulettes(self):
        H, s = self.H, self.s
        for piv, sx in self.ch.parts["wings"]:
            p = Vector((sx * 0.1 * s, 0, -0.02 * s))
            e = H.ball("epaulette", p, (0.22 * s, 0.34 * s, 0.17 * s), self.m_gold, rot=(0, -sx * 0.15, 0)); e.parent = piv
            for k, dy in enumerate((-0.2, 0.0, 0.2)):
                t = self.solid("tetra", "spike", p + Vector((sx * 0.2 * s, dy * s, -0.02 * s)), 0.075 * s, self.m_cream, rot=(0, 0, 0), outline=0.006); t.parent = piv

    def glasses(self):
        H, s, hc, rh = self.H, self.s, self.hc, self.rh
        frame = H.toon("c_gframe", "#ffcf3d", "#a8700a", "#fff3b0"); ch = self.ch
        pts_l = []
        for sx in (-1, 1):
            d = Vector((0.34 * sx, -0.92, -0.02)).normalized(); c = hc + Vector((d.x * self.Rh[0], d.y * self.Rh[1], d.z * self.Rh[2])) * 1.03
            yaw = math.atan2(d.x, -d.y); right = Vector((math.cos(yaw), math.sin(yaw), 0))
            pts = [c + right * math.cos(a) * 0.29 * s + Vector((0, 0, math.sin(a) * 0.29 * s)) + Vector((0, 0.03 * s * math.cos(a) * sx * -1, 0)) for a in [i / 28 * 2 * math.pi for i in range(28)]]
            ch.addh(self.tube("lens", pts, 0.035 * s, frame, closed=True, outline=0.008, sides=6))
            g = H.ball("glint", c + right * (-0.12 * s) + Vector((0, -0.05 * s, 0.14 * s)) + d * 0.0, (0.07 * s, 0.015 * s, 0.025 * s), H.flat("white", "#ffffff"), rot=(0, -0.7, yaw), outline=0); ch.addh(g)
            pts_l.append(c + right * (-sx * 0.29 * s))
            arm = self.tube("arm", [c + right * (sx * 0.29 * s), c + right * (sx * 0.33 * s) + Vector((0, 0.18 * s, 0))], 0.022 * s, frame, outline=0.006, sides=5); ch.addh(arm)
        ch.addh(self.tube("bridge", [pts_l[0], (pts_l[0] + pts_l[1]) / 2 + Vector((0, -0.02 * s, 0.03 * s)), pts_l[1]], 0.022 * s, frame, outline=0.006, sides=5))

    def bowtie(self):
        H, s, ch = self.H, self.s, self.ch
        p, n = self.surf(self.bc, self.Rb, -90, 0.6, 0.11 * s)
        p += Vector((0, 0, 0.0))
        for sx in (-1, 1):
            c = H.cone("bow", p + Vector((sx * 0.1 * s, 0, 0)), 0.11 * s, 0.22 * s, self.m_main, (0, math.radians(90 * sx), 0)); c.scale = (1, 1.2, 0.5); ch.add(c)
        ch.add(H.ball("bowknot", p, (0.065 * s,) * 3, self.m_metal, outline=0.008))

    def brooch(self):
        """an emblem on the chest (the subject's, here a protractor) and a clasp at the collar"""
        H, s, ch = self.H, self.s, self.ch
        if self.spec["emblem"] != "protractor":
            cp, cn = self.surf(self.bc, self.Rb, -90, 0.6, 0.14 * s)
            ch.add(H.ball("clasp", cp, (0.1 * s,) * 3, self.m_gold, outline=0.01)); ch.add(H.ball("gem", cp + Vector((0, -0.07 * s, 0)), (0.055 * s,) * 3, self.m_red, outline=0.006))
            return
        p, n = self.surf(self.bc, self.Rb, -62, 0.05, 0.14 * s)
        pr = self.protractor(p + Vector((0, 0, -0.06 * s)), 0.2 * s, self.m_gold, self.m_ink)
        pr.rotation_euler = (0, 0, 0)
        ch.add(pr)
        cp, cn = self.surf(self.bc, self.Rb, -90, 0.6, 0.14 * s)
        ch.add(H.ball("clasp", cp, (0.1 * s,) * 3, self.m_gold, outline=0.01)); ch.add(H.ball("gem", cp + Vector((0, -0.07 * s, 0)), (0.055 * s,) * 3, self.m_red, outline=0.006))

    def collar(self):
        H, s, ch = self.H, self.s, self.ch
        col = self.m_deep if self.st["top"] != "robe" else self.m_gold
        ch.add(self.ring("collar", self.bc, tuple(x * 1.06 for x in self.Rb), 0.62, 0.05 * s, 0.1 * s, col, outline=0.014, a0=-170, a1=-10, n=40))

    def glow_mat(self, name, color, k):
        H = self.H
        gl = bpy.data.materials.new(name); gl.use_nodes = True; nt = gl.node_tree; n = nt.nodes; n.clear()
        out = n.new("ShaderNodeOutputMaterial"); mix = n.new("ShaderNodeMixShader"); tr = n.new("ShaderNodeBsdfTransparent"); em = n.new("ShaderNodeEmission")
        tc = n.new("ShaderNodeTexCoord"); gr = n.new("ShaderNodeTexGradient"); gr.gradient_type = "SPHERICAL"
        sb = n.new("ShaderNodeVectorMath"); sb.operation = "SUBTRACT"; sb.inputs[1].default_value = (0.5, 0.5, 0)
        sc = n.new("ShaderNodeVectorMath"); sc.operation = "SCALE"; sc.inputs["Scale"].default_value = 2.0
        rp = n.new("ShaderNodeValToRGB"); rp.color_ramp.interpolation = "EASE"; rp.color_ramp.elements[0].position = 0.0; rp.color_ramp.elements[0].color = (0, 0, 0, 1)
        rp.color_ramp.elements[1].position = 0.9; rp.color_ramp.elements[1].color = (1, 1, 1, 1)
        iv = n.new("ShaderNodeMath"); iv.operation = "MULTIPLY"; iv.inputs[1].default_value = k
        nt.links.new(tc.outputs["UV"], sb.inputs[0]); nt.links.new(sb.outputs[0], sc.inputs[0]); nt.links.new(sc.outputs[0], gr.inputs["Vector"])
        nt.links.new(gr.outputs["Fac"], rp.inputs[0]); nt.links.new(rp.outputs[0], iv.inputs[0]); nt.links.new(iv.outputs[0], mix.inputs[0])
        em.inputs[0].default_value = H.lin(color); em.inputs[1].default_value = 1.0
        nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(em.outputs[0], mix.inputs[2]); nt.links.new(mix.outputs[0], out.inputs[0])
        for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
            try: setattr(gl, attr, val)
            except Exception: pass
        gl.use_backface_culling = False
        return gl

    def billboard(self, name, c, sx, sy, mat, rotz=0.0):
        H = self.H
        bm = bmesh.new(); bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1.0); o = H.mesh_obj(name, bm)
        o.location = c; o.scale = (sx, sy, 1)
        o.rotation_euler = (Matrix.Rotation(math.radians(74), 3, "X") @ Matrix.Rotation(rotz, 3, "Z")).to_euler()
        uv = o.data.uv_layers.new(name="UVMap")
        for lp in o.data.loops:
            v = o.data.vertices[lp.vertex_index].co; uv.data[lp.index].uv = (v.x * 0.5 + 0.5, v.y * 0.5 + 0.5)
        o.data.materials.append(mat); self.ch.add(o); return o

    def aura(self):
        H, s, ch, hc, rh = self.H, self.s, self.ch, self.hc, self.rh
        kind = self.spec.get("halo", "protractor") if self.spec["emblem"] != "protractor" else "protractor"
        self.hp0 = hp0 = hc + Vector((0, 0.7 * s, 0.85 * s))
        warm = self.glow_mat("glow_w", self.spec.get("glow", "#ffe9a0"), 0.6); ray = self.glow_mat("glow_r", self.spec.get("glow", "#fff0b8"), 0.5)
        self.billboard("halo_glow", hp0 + Vector((0, 0.2 * s, 0)), 2.4, 2.4, warm)
        # soft light rays fanning out behind the head
        for ang in (15, 45, 72, 108, 135, 165, 195, 345):
            a = math.radians(ang); L = 1.9
            self.billboard("ray", hp0 + Vector((math.cos(a) * L * 0.5, 0.1 * s, math.sin(a) * L * 0.5)), 0.2, L * 0.55, ray, rotz=a - math.pi / 2)
        gold_e = H.toon("c_halo", "#ffe27a", "#e0a020", "#ffffff")
        hr = 1.55 * s
        if kind == "rainbow":
            cols = [H.toon("rb%d" % i, *c) for i, c in enumerate((("#ff5a5a", "#c22a2a", "#ffa0a0"), ("#ffae3a", "#c8700a", "#ffd890"), ("#5ad66a", "#2f9a3f", "#a8f0b0"), ("#4aa8ff", "#2a68c0", "#a8d4ff"), ("#b070ff", "#7a3ac0", "#dcb8ff")))]
            for i, c in enumerate(cols):
                rr = hr * (1.0 - i * 0.075)
                ch.add(self.tube("rainbow", [hp0 + Vector((math.cos(a) * rr, 0, math.sin(a) * rr)) for a in [math.radians(-5 + 190 * j / 40) for j in range(41)]], 0.055 * s, c, outline=0.01, sides=6))
            return
        ring = [hp0 + Vector((math.cos(a) * hr, 0, math.sin(a) * hr)) for a in [i / 72 * 2 * math.pi for i in range(72)]]
        ch.add(self.tube("halo", ring, 0.065 * s, gold_e, closed=True, outline=0.012, sides=8))
        ring2 = [hp0 + Vector((math.cos(a) * hr * 0.82, -0.01 * s, math.sin(a) * hr * 0.82)) for a in [i / 72 * 2 * math.pi for i in range(72)]]
        ch.add(self.tube("halo2", ring2, 0.028 * s, gold_e, closed=True, outline=0.006, sides=6))
        if kind == "protractor":
            for a in range(0, 360, 15):
                c_, s_ = math.cos(math.radians(a)), math.sin(math.radians(a)); ln = 0.15 * s if a % 45 == 0 else 0.09 * s
                rr_ = hr * 0.91 - 0.02 * s
                o = H.rbox("htick", hp0 + Vector((c_ * rr_, -0.01 * s, s_ * rr_)), (0.035 * s, 0.035 * s, ln), gold_e, outline=0.004)
                o.rotation_euler = (0, -math.radians(a - 90), 0); ch.add(o)
        elif kind == "gear":
            for a in range(0, 360, 20):
                o = H.rbox("htooth", hp0 + Vector((math.cos(math.radians(a)) * (hr + 0.06 * s), 0, math.sin(math.radians(a)) * (hr + 0.06 * s))), (0.2 * s, 0.1 * s, 0.17 * s), gold_e, outline=0.01)
                o.rotation_euler = (0, -math.radians(a - 90), 0); ch.add(o)
        elif kind == "drum":
            for a in range(0, 360, 15):
                o = self.solid("tetra", "ray", hp0 + Vector((math.cos(math.radians(a)) * (hr + 0.12 * s), 0, math.sin(math.radians(a)) * (hr + 0.12 * s))), 0.09 * s, gold_e, rot=(0, math.radians(a), 0), outline=0.006); ch.add(o)
            star = []
            for i in range(24):
                aa = math.pi / 2 + i * math.pi / 12; rr = hr * (0.55 if i % 2 == 0 else 0.3); star.append(Vector((math.cos(aa) * rr, 0, math.sin(aa) * rr)))
            sp = self.poly("sunstar", [hp0 + v + Vector((0, 0.06 * s, 0)) for v in star], 0.03 * s, gold_e, outline=0.008); ch.add(sp)
        else:
            gem = [H.toon("hg%d" % i, *c) for i, c in enumerate((("#7fb6ff", "#2d62c8", "#ffffff"), ("#ff8aa8", "#c83a60", "#ffffff"), ("#8aff9a", "#2ea04a", "#ffffff")))]
            for j, a in enumerate(range(0, 360, 30)):
                ch.add(self.solid("diamond", "hgem", hp0 + Vector((math.cos(math.radians(a)) * hr, -0.02 * s, math.sin(math.radians(a)) * hr)), (0.07 * s, 0.05 * s, 0.1 * s), gem[j % 3] if j % 2 else gold_e, rot=(0, -math.radians(a - 90), 0), outline=0.006))

    def star(self, c, r, mat):
        pts = []
        for i in range(8):
            a = math.pi / 2 + i * math.pi / 4; rr = r if i % 2 == 0 else r * 0.22
            pts.append(Vector((math.cos(a) * rr, 0, math.sin(a) * rr)))
        o = self.poly("star", pts, 0.02 * self.s, mat, outline=0.0)
        o.location = c; self.ch.add(o); return o

    def orbit(self):
        H, s, ch, hc, rh = self.H, self.s, self.ch, self.hc, self.rh
        mats = [H.toon("o_blue", "#6ea0ff", "#3f6fd8", "#d6e6ff"), self.m_gold, self.m_cream, H.toon("o_cy", "#7fe0ff", "#3aa8d8", "#e0faff")]
        gcol = ["#8fb8ff", "#ffe08a", "#fff0c8", "#9fe8ff"]
        kinds = ["cube", "tetra", "ico", "diamond", "cube", "tetra"]
        cz = hc.z + 0.85 * s; Rx, Ry = 1.85 * s, 0.5 * s
        mini = self.spec["emblem"] != "protractor"
        for k, ang in enumerate((5, 52, 128, 175, 238, 312)):
            a = math.radians(ang); p = Vector((math.cos(a) * Rx, math.sin(a) * Ry + 0.05 * s, cz + 0.14 * s * math.sin(a * 2)))
            sz = (0.24 if k % 2 == 0 else 0.2) * s
            gc = self.spec["main"][2] if mini else gcol[k % 4]
            self.billboard("orbglow", p + Vector((0, 0.1 * s, 0)), 0.42 * s * 1.3, 0.42 * s * 1.3, self.glow_mat("og%d" % k, gc, 0.7))
            if mini and k % 2 == 0:
                import gunny
                names = self.spec["orbit"]; gunny.chest(self, names[(k // 2) % len(names)], p + Vector((0, -0.12 * s, 0)), 0.19 * s, 3)
            else:
                ch.add(self.solid(kinds[k], "orb", p, sz, mats[k % 4] if not mini else (self.m_main, self.m_gold, self.m_cream)[k % 3], rot=(0.5 * k, 0.4, 0.3 * k), outline=0.01))
        sp = H.flat("sparkle", "#fff6c8")
        for ang, dz, k in ((340, 0.7, 1.0), (203, 0.85, 0.85), (98, 0.55, 0.7), (155, 0.0, 0.8), (28, -0.1, 0.65)):
            a = math.radians(ang); p = Vector((math.cos(a) * Rx * 1.12, 0.15 * s, cz + dz * s))
            self.billboard("spkglow", p + Vector((0, 0.1 * s, 0)), 0.3 * s * k * 1.4, 0.3 * s * k * 1.4, self.glow_mat("sg", "#fff2b0", 0.8))
            self.star(p, 0.26 * s * k, sp)

    def build(self):
        st = self.st; ex = st["extra"]
        for piv, sx in self.ch.parts["wings"]: piv.location.x += sx * 0.1 * self.s  # wings stand a little proud of the clothes
        self.head(); (None if os.environ.get("CDBG") == "notop" else self.top()); self.back(); self.feet()
        if "bowtie" in ex: self.bowtie()
        if "glasses" in ex: self.glasses()
        if "cuffs" in ex: self.wing_cuffs()
        if "epaulettes" in ex: self.epaulettes()
        if self.st["back"] in ("cape", "cape_long"): self.mantle()
        if self.st["top"] in ("coat", "robe"): self.collar()
        if "brooch" in ex or ("chest" in ex and self.stage >= 3): self.brooch()
        if "chest" in ex and self.spec["emblem"] != "protractor":
            import gunny; r = {2: 0.27, 3: 0.32, 4: 0.36}[self.stage] * self.s
            p, n = self.surf(self.bc, self.Rb, -86, 0.0 if self.stage >= 3 else 0.12, 0.2 * self.s)
            gunny.chest(self, self.spec["emblem"], p, r, self.stage)
        if "held" in ex and not getattr(self.H, "ANGRY", False):
            import gunny; gunny.held(self, self.spec.get("held"), self.stage)
        if "halo" in ex: self.aura()
        if "orbit" in ex: self.orbit()


def Rh0(k): return k.Rh


def dress(ch, H, subject, stage):
    k = Kit(ch, H, subject, stage); k.build(); return k
