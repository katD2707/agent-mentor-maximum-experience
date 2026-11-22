# Shared kit for the Làng gà renders (village, hero frame, character sprites): one look, one light, one camera angle.
# Use from a Blender script:   exec(open(os.path.join(HERE, "lang_lib.py"), encoding="utf-8").read())
# It runs the scene setup of chicken.py (toon helpers + the Chicken class), then defines:
#   paint()           the painted material: real light (sun shadows + AO) -> tone bands with brushy edges, colour variation
#   bbox/blob/tube/plane/grid/scatter/proto    geometry helpers (scatter = geometry-node instancing)
#   tuft/flower/crown/tree/bush/fence/lantern/coop/rock_ring   ready-made pieces
#   rig()             world light, the sun (front left, high) and a soft fill from the camera side
#   camera()          the orthographic camera, CAM_TILT below horizontal; px_per_unit() for sprites
#   grade()           compositor: depth haze, bloom, a little saturation and contrast
# LANG_STYLE=v1 gives the earlier smooth shading (kept for comparison).
import bpy, bmesh, math, os, sys, random
from mathutils import Vector
HERE = os.path.dirname(os.path.abspath(__file__))
_src = open(os.path.join(HERE, "chicken.py"), encoding="utf-8").read()
exec(_src[:_src.index("def camera")])

STYLE = os.environ.get("LANG_STYLE", "paint"); PAINTERLY = STYLE != "v1"
SHADE_OF = {}
CAM_TILT = 26.0                      # degrees below horizontal, for every render of the village and its characters
SUN_DIR = Vector((0.55, 0.75, -0.95)).normalized()   # light travels right, away and down: shadows fall back right

def darker(hexs, k=0.55):
    h = hexs.lstrip("#"); return "#" + "".join(f"{int(int(h[i:i + 2], 16) * k):02x}" for i in (0, 2, 4))
def mixc(a, b, t): return tuple(a[i] * (1 - t) + b[i] * t for i in range(3)) + (1,)

def setup_render(w, h, samples=64):
    e = sc.eevee
    e.taa_render_samples = samples; e.use_shadows = True; e.shadow_ray_count = 2; e.shadow_step_count = 10
    e.use_gtao = True; e.gtao_distance = 1.4; e.shadow_resolution_scale = 1.0
    sc.render.resolution_x, sc.render.resolution_y = w, h; sc.render.resolution_percentage = 100

# ---------------------------------------------------------------- painted material
TEXDIR = os.path.join(HERE, "tex")
DETAIL = os.environ.get("LANG_DETAIL", "1") != "0"   # painted detail maps on (LANG_DETAIL=0 to compare without)
def paint(name, lit, shade, mid=None, hi=None, var=0.0, vscale=0.3, rand=0.0, grad=None, grain=0.0, up=False,
          ao=0.5, rim=0.5, speck=0.0, ellipse=None, strokes=0.0, glow=0.0, tex=None):
    """Light (sun shadows + AO) -> tone bands (shade, mid, lit, highlight) whose edges wobble like brush strokes;
    then colour variation: world-space patches, per-piece random, a base-to-tip gradient on UV v, wood grain, specks,
    long brush dabs, a darker worn rim of an ellipse; a warm rim light on the lit side. up: shade as if facing up
    (grass and straw take the light of the ground). glow: emissive boost (lanterns, windows at night)."""
    key = "p_" + name
    if key in MATS: return MATS[key]
    m = bpy.data.materials.new(key); m.use_nodes = True; nt = m.node_tree; n = nt.nodes; n.clear(); Lk = nt.links.new
    out = n.new("ShaderNodeOutputMaterial"); em = n.new("ShaderNodeEmission")
    dif = n.new("ShaderNodeBsdfDiffuse")
    if up:
        cx = n.new("ShaderNodeCombineXYZ"); cx.inputs[2].default_value = 1.0; Lk(cx.outputs[0], dif.inputs["Normal"])
    s2r = n.new("ShaderNodeShaderToRGB"); Lk(dif.outputs[0], s2r.inputs[0])
    bw = n.new("ShaderNodeRGBToBW"); Lk(s2r.outputs[0], bw.inputs[0]); v = bw.outputs[0]
    if ao:
        aon = n.new("ShaderNodeAmbientOcclusion"); aon.inputs["Distance"].default_value = 1.2
        mr = n.new("ShaderNodeMapRange"); mr.inputs[3].default_value = 1 - ao; mr.inputs[4].default_value = 1.0
        Lk(aon.outputs["AO"], mr.inputs[0])
        mu = n.new("ShaderNodeMath"); mu.operation = "MULTIPLY"; Lk(v, mu.inputs[0]); Lk(mr.outputs[0], mu.inputs[1]); v = mu.outputs[0]
    SHADE_OF[key] = shade
    ramp = n.new("ShaderNodeValToRGB"); cr = ramp.color_ramp
    L = lin(lit); S = lin(shade); M = lin(mid) if mid else mixc(S, L, 0.55)
    if PAINTERLY:
        # brush: a noise nudges the light value, so the edges between tone bands wobble like strokes;
        # the ground (up) gets bigger, gentler strokes, so shadow edges wobble without looking scribbled
        bs, ba = (1.3, 0.05) if up else (2.2, 0.07)
        nzb = n.new("ShaderNodeTexNoise"); nzb.inputs["Scale"].default_value = bs; nzb.inputs["Detail"].default_value = 2
        nzb.inputs["Roughness"].default_value = 0.5; nzb.inputs["Distortion"].default_value = 0.4
        Lk(n.new("ShaderNodeNewGeometry").outputs["Position"], nzb.inputs["Vector"])
        mrb = n.new("ShaderNodeMapRange"); mrb.inputs[1].default_value = 0.3; mrb.inputs[2].default_value = 0.7
        mrb.inputs[3].default_value = -ba; mrb.inputs[4].default_value = ba; Lk(nzb.outputs["Fac"], mrb.inputs[0])
        adb = n.new("ShaderNodeMath"); adb.operation = "ADD"; Lk(v, adb.inputs[0]); Lk(mrb.outputs[0], adb.inputs[1]); v = adb.outputs[0]
        cr.interpolation = "LINEAR"  # flat tone bands with short soft steps between them
        cr.elements[0].position = 0.0; cr.elements[0].color = S
        cr.elements[1].position = 0.2; cr.elements[1].color = S
        for pos, c in ((0.24, M), (0.4, M), (0.45, L), (0.86 if hi else 1.0, L)):
            x = cr.elements.new(pos); x.color = c
        if hi: x = cr.elements.new(0.9); x.color = lin(hi)
    else:
        cr.interpolation = "EASE"
        cr.elements[0].position = 0.05; cr.elements[0].color = S
        cr.elements[1].position = 0.5; cr.elements[1].color = L
        x = cr.elements.new(0.24); x.color = M
        if hi: x = cr.elements.new(0.9); x.color = lin(hi)
    Lk(v, ramp.inputs[0]); col = ramp.outputs[0]

    def mul(c, f):
        mx = n.new("ShaderNodeMixRGB"); mx.blend_type = "MULTIPLY"; mx.inputs[0].default_value = 1.0
        Lk(c, mx.inputs[1]); Lk(f, mx.inputs[2]); return mx.outputs[0]
    def band(fac, lo, hi_, p0=0.0, p1=1.0, interp="LINEAR"):
        r = n.new("ShaderNodeValToRGB"); rc = r.color_ramp; rc.interpolation = interp
        rc.elements[0].position = p0; rc.elements[0].color = lo; rc.elements[1].position = p1; rc.elements[1].color = hi_
        Lk(fac, r.inputs[0]); return r.outputs[0]
    geo = n.new("ShaderNodeNewGeometry")
    if var:  # big soft patches: a little darker and cooler / lighter and warmer
        nz = n.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = vscale; nz.inputs["Detail"].default_value = 5
        nz.inputs["Roughness"].default_value = 0.62; Lk(geo.outputs["Position"], nz.inputs["Vector"])
        col = mul(col, band(nz.outputs["Fac"], (1 - var, 1 - var * 0.5, 1 - var * 0.1, 1), (1 + var * 0.7, 1 + var * 0.6, 1 - var * 0.5, 1), 0.3, 0.72))
    if strokes:  # long flat dabs, as if painted with a wide brush across the picture
        mp2 = n.new("ShaderNodeMapping"); mp2.inputs["Scale"].default_value = (0.55, 2.4, 1.0); Lk(geo.outputs["Position"], mp2.inputs[0])
        nz2 = n.new("ShaderNodeTexNoise"); nz2.inputs["Scale"].default_value = 1.6; nz2.inputs["Detail"].default_value = 2; Lk(mp2.outputs[0], nz2.inputs["Vector"])
        col = mul(col, band(nz2.outputs["Fac"], (1 - strokes, 1 - strokes * 0.7, 1 - strokes * 0.3, 1), (1 + strokes * 0.6, 1 + strokes * 0.6, 1 - strokes * 0.2, 1), 0.38, 0.64))
    if rand:  # each plank, shingle, blade a touch different
        oi = n.new("ShaderNodeObjectInfo")
        col = mul(col, band(oi.outputs["Random"], (1 - rand, 1 - rand * 0.8, 1 - rand * 0.4, 1), (1 + rand * 0.6, 1 + rand * 0.5, 1 - rand * 0.2, 1)))
    if grad:  # base to tip along UV v
        uv = n.new("ShaderNodeUVMap"); sp = n.new("ShaderNodeSeparateXYZ"); Lk(uv.outputs[0], sp.inputs[0])
        g0, g1 = grad
        col = mul(col, band(sp.outputs[1], (g0, g0, g0 * 1.05, 1), (g1, g1 * 1.02, g1 * 0.86, 1)))
    if grain:  # wood grain along the object's long axis
        tc = n.new("ShaderNodeTexCoord"); wv = n.new("ShaderNodeTexWave"); wv.wave_type = "BANDS"; wv.bands_direction = "X"
        wv.inputs["Scale"].default_value = 3.2; wv.inputs["Distortion"].default_value = 7.0; wv.inputs["Detail"].default_value = 3
        mp = n.new("ShaderNodeMapping"); mp.inputs["Scale"].default_value = (0.3, 1.0, 0.3); mp.inputs["Rotation"].default_value = (0, math.radians(90), 0)
        Lk(tc.outputs["Object"], mp.inputs[0]); Lk(mp.outputs[0], wv.inputs["Vector"])
        col = mul(col, band(wv.outputs["Fac"], (1 - grain, 1 - grain * 1.1, 1 - grain * 1.2, 1), (1 + grain * 0.3, 1 + grain * 0.3, 1 + grain * 0.2, 1)))
    if speck:  # small darker grains (dirt, stone)
        vo = n.new("ShaderNodeTexVoronoi"); vo.inputs["Scale"].default_value = 9.0; Lk(geo.outputs["Position"], vo.inputs["Vector"])
        col = mul(col, band(vo.outputs["Distance"], (1 - speck, 1 - speck * 1.1, 1 - speck * 1.15, 1), (1, 1, 1, 1), 0.06, 0.12))
    if ellipse:  # worn darker towards the rim of an ellipse: (cx, cy, rx, ry, amount)
        cx_, cy_, rx_, ry_, amt = ellipse
        sb = n.new("ShaderNodeVectorMath"); sb.operation = "SUBTRACT"; sb.inputs[1].default_value = (cx_, cy_, 0); Lk(geo.outputs["Position"], sb.inputs[0])
        sm = n.new("ShaderNodeVectorMath"); sm.operation = "MULTIPLY"; sm.inputs[1].default_value = (1 / rx_, 1 / ry_, 0); Lk(sb.outputs[0], sm.inputs[0])
        ln = n.new("ShaderNodeVectorMath"); ln.operation = "LENGTH"; Lk(sm.outputs[0], ln.inputs[0])
        col = mul(col, band(ln.outputs["Value"], (1, 1, 1, 1), (1 - amt, 1 - amt * 1.15, 1 - amt * 1.35, 1), 0.5, 1.0, "EASE"))
    if tex and DETAIL:  # hand-painted detail (tex/<name>-d.png: strokes, cracks, grain, moss around mid grey), overlaid
        tname, tscale, tamt = tex; tp = os.path.join(TEXDIR, tname + "-d.png")
        if os.path.exists(tp):
            im = bpy.data.images.get(tname + "-d.png") or bpy.data.images.load(tp); im.colorspace_settings.name = "Non-Color"
            ti = n.new("ShaderNodeTexImage"); ti.image = im; ti.interpolation = "Cubic"
            mp3 = n.new("ShaderNodeMapping"); mp3.inputs["Scale"].default_value = (tscale, tscale, tscale)
            if up:  # ground: painted from above, in world space so it runs on across pieces
                Lk(geo.outputs["Position"], mp3.inputs[0]); ti.projection = "FLAT"
            else:   # objects: box projection in their own space (planks, stones, tiles keep their pattern)
                Lk(n.new("ShaderNodeTexCoord").outputs["Object"], mp3.inputs[0]); ti.projection = "BOX"; ti.projection_blend = 0.35
            Lk(mp3.outputs[0], ti.inputs["Vector"])
            ov = n.new("ShaderNodeMixRGB"); ov.blend_type = "OVERLAY"; ov.inputs[0].default_value = tamt
            Lk(col, ov.inputs[1]); Lk(ti.outputs["Color"], ov.inputs[2]); col = ov.outputs[0]
    rim = rim * 0.6  # a softer rim: a strong one reads as plastic
    if rim:  # warm light along the silhouette, on the lit side only
        lw = n.new("ShaderNodeLayerWeight"); lw.inputs[0].default_value = 0.14
        rr = band(lw.outputs["Facing"], (0, 0, 0, 1), lin("#ffeec4"), 0.78, 0.97, "EASE")
        lm = n.new("ShaderNodeMath"); lm.operation = "MULTIPLY"; lm.inputs[1].default_value = rim; Lk(bw.outputs[0], lm.inputs[0])
        rf = n.new("ShaderNodeMixRGB"); rf.blend_type = "MULTIPLY"; rf.inputs[0].default_value = 1.0; Lk(rr, rf.inputs[1]); Lk(lm.outputs[0], rf.inputs[2])
        ad = n.new("ShaderNodeMixRGB"); ad.blend_type = "ADD"; ad.inputs[0].default_value = 1.0; Lk(col, ad.inputs[1]); Lk(rf.outputs[0], ad.inputs[2])
        col = ad.outputs[0]
    Lk(col, em.inputs[0]); em.inputs[1].default_value = 1.0 + glow; Lk(em.outputs[0], out.inputs[0])
    MATS[key] = m; return m

# ---------------------------------------------------------------- geometry helpers
def outline(o, t):
    if not t: return o
    om = outline_mat()
    if PAINTERLY and o.data.materials and o.data.materials[0].name in SHADE_OF:  # outline in a deep tone of the surface
        base = o.data.materials[0].name; om = flat("ol_" + base, darker(SHADE_OF[base], 0.62)); om.use_backface_culling = True
    o.data.materials.append(om); k = len(o.data.materials) - 1
    so = o.modifiers.new("ol", "SOLIDIFY"); so.thickness = t; so.offset = 1; so.use_flip_normals = True
    so.material_offset = k; so.use_rim = False
    return o

def bbox(name, c, size, mat, rot=(0, 0, 0), bev=0.035, ol=0.018, seg=2):
    """A box with its real size in the mesh (scale 1), so bevels and outlines keep their width."""
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0); bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    o = mesh_obj(name, bm); o.location = c; o.rotation_euler = rot
    if bev:
        b = o.modifiers.new("bev", "BEVEL"); b.width = bev; b.segments = seg; b.limit_method = "NONE"
    o.data.materials.append(mat)
    return outline(o, ol)

def blob(name, c, r, mat, squash=(1, 1, 1), rough=0.3, nscale=0.6, subdiv=3, ol=0.0, smooth=True):
    """A displaced icosphere: rocks, crowns, bushes, sacks."""
    bm = bmesh.new(); bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=r)
    bmesh.ops.scale(bm, vec=Vector(squash), verts=bm.verts)
    o = mesh_obj(name, bm); o.location = c
    if rough:
        tex = bpy.data.textures.new(name + "_n", "CLOUDS"); tex.noise_scale = nscale; tex.noise_depth = 2
        d = o.modifiers.new("disp", "DISPLACE"); d.texture = tex; d.strength = r * rough; d.mid_level = 0.5; d.texture_coords = "GLOBAL"
    o.data.materials.append(mat)
    for p in o.data.polygons: p.use_smooth = smooth
    return outline(o, ol)

def tube(name, c, r0, r1, h, mat, seg=14, rot=(0, 0, 0), ol=0.0, rough=0.0):
    """A tapered cylinder standing on c (or rotated by rot around c)."""
    bm = bmesh.new(); bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r0, radius2=r1, depth=h)
    bmesh.ops.translate(bm, vec=Vector((0, 0, h / 2)), verts=bm.verts)
    o = mesh_obj(name, bm); o.location = c; o.rotation_euler = rot
    if rough:
        s = o.modifiers.new("sub", "SUBSURF"); s.levels = s.render_levels = 2
        tex = bpy.data.textures.new(name + "_n", "CLOUDS"); tex.noise_scale = 0.5
        d = o.modifiers.new("disp", "DISPLACE"); d.texture = tex; d.strength = rough; d.texture_coords = "GLOBAL"
    o.data.materials.append(mat)
    for p in o.data.polygons: p.use_smooth = True
    return outline(o, ol)

def plane(name, verts_xy, mat, z=0.0):
    bm = bmesh.new(); vs = [bm.verts.new((x, y, z)) for x, y in verts_xy]; bm.faces.new(vs)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    o = mesh_obj(name, bm); o.data.materials.append(mat); return o

def grid(name, size, res, keep, mat=None, z=0.0, center=(0, 0)):
    """A ground grid (size may be (w, h)); faces whose centre fails keep(x, y) are dropped (to cut holes)."""
    w, h = (size, size) if not isinstance(size, (tuple, list)) else size
    rx, ry = (res, res) if not isinstance(res, (tuple, list)) else res
    bm = bmesh.new(); bmesh.ops.create_grid(bm, x_segments=rx, y_segments=ry, size=0.5)
    bmesh.ops.scale(bm, vec=Vector((w, h, 1)), verts=bm.verts); bmesh.ops.translate(bm, vec=Vector((center[0], center[1], 0)), verts=bm.verts)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if not keep(*f.calc_center_median().xy)], context="FACES")
    o = mesh_obj(name, bm); o.location.z = z
    if mat: o.data.materials.append(mat)
    return o

def scatter(name, surf, inst, density, s=(0.8, 1.2), seed=0, align=False, tilt=0.15, keep=False, clump=None):
    """Instances of inst on the faces of surf (geometry nodes). keep: also render surf itself.
    clump=(noise scale, low, high[, t0, t1]): the density follows a noise, so things grow in patches."""
    ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, Lk = ng.nodes, ng.links.new
    gi = N.new("NodeGroupInput"); go = N.new("NodeGroupOutput")
    d = N.new("GeometryNodeDistributePointsOnFaces"); d.inputs["Density"].default_value = density; d.inputs["Seed"].default_value = seed
    Lk(gi.outputs[0], d.inputs["Mesh"])
    if clump:
        nz = N.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = clump[0]; nz.inputs["Detail"].default_value = 2
        t0, t1 = (clump[3], clump[4]) if len(clump) > 3 else (0.42, 0.62)
        mr = N.new("ShaderNodeMapRange"); mr.inputs[1].default_value = t0; mr.inputs[2].default_value = t1
        mr.inputs[3].default_value = clump[1] * density; mr.inputs[4].default_value = clump[2] * density
        Lk(nz.outputs["Fac"], mr.inputs[0]); Lk(mr.outputs[0], d.inputs["Density"])
    oi = N.new("GeometryNodeObjectInfo"); oi.inputs["Object"].default_value = inst
    iop = N.new("GeometryNodeInstanceOnPoints"); Lk(d.outputs["Points"], iop.inputs["Points"]); Lk(oi.outputs["Geometry"], iop.inputs["Instance"])
    rs = N.new("FunctionNodeRandomValue"); rs.data_type = "FLOAT"; rs.inputs[2].default_value = s[0]; rs.inputs[3].default_value = s[1]; rs.inputs[8].default_value = seed + 1
    Lk([o for o in rs.outputs if o.type == "VALUE"][0], iop.inputs["Scale"])
    rv = N.new("FunctionNodeRandomValue"); rv.data_type = "FLOAT_VECTOR"; rv.inputs[0].default_value = (-tilt, -tilt, 0)
    rv.inputs[1].default_value = (tilt, tilt, 6.283); rv.inputs[8].default_value = seed + 2
    e2r = N.new("FunctionNodeEulerToRotation"); Lk([o for o in rv.outputs if o.type == "VECTOR"][0], e2r.inputs[0])
    if align:
        rr = N.new("FunctionNodeRotateRotation"); rr.rotation_space = "LOCAL"
        Lk(d.outputs["Rotation"], rr.inputs[0]); Lk(e2r.outputs[0], rr.inputs[1]); Lk(rr.outputs[0], iop.inputs["Rotation"])
    else:
        Lk(e2r.outputs[0], iop.inputs["Rotation"])
    if keep:
        j = N.new("GeometryNodeJoinGeometry"); Lk(gi.outputs[0], j.inputs[0]); Lk(iop.outputs[0], j.inputs[0]); Lk(j.outputs[0], go.inputs[0])
    else:
        Lk(iop.outputs[0], go.inputs[0])
    mod = surf.modifiers.new(name, "NODES"); mod.node_group = ng
    return surf

def proto(o):
    """A hidden prototype for scatter. Object Info reads the mesh without the object's own transform, so bake
    location / rotation / scale into the mesh first."""
    bpy.ops.object.select_all(action="DESELECT"); o.select_set(True); bpy.context.view_layer.objects.active = o
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    o.select_set(False); o.hide_render = True; o.hide_viewport = True; return o

def join(name, parts):
    bpy.ops.object.select_all(action="DESELECT")
    for p in parts: p.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]; bpy.ops.object.join()
    o = bpy.context.view_layer.objects.active; o.name = name; bpy.ops.object.select_all(action="DESELECT"); return o

# ---------------------------------------------------------------- materials
M_grass = paint("grass", "#8fcc5c", "#3a7a5e", "#66ad56", var=0.24, vscale=0.09, up=True, ao=0.4, rim=0, strokes=0.07, tex=("grass", 0.22, 0.6))
M_blade = paint("blade", "#a2e46a", "#3b8456", "#6ebe5a", "#dcf7a0", up=True, grad=(0.5, 1.12), rand=0.12, ao=0.55, rim=0)
M_path = paint("path", "#ecc994", "#b0806a", "#d4a97c", var=0.12, vscale=0.4, up=True, speck=0.07, ao=0.45, rim=0)
M_sand = paint("sand", "#f4dca6", "#c09070", "#e0c08a", var=0.1, vscale=0.35, up=True, speck=0.06, ao=0.45, rim=0)
M_rock = paint("rock", "#e2ddd2", "#8a88a3", "#bdb6ad", "#fbf7ef", var=0.06, rand=0.12, speck=0.05, tex=("stone", 0.55, 0.55))
M_wood = paint("wood", "#dca266", "#7c4a40", "#b87a4c", "#f4cc92", grain=0.06, rand=0.12, tex=("wood", 0.45, 0.55))
M_woodd = paint("woodd", "#b07443", "#5a3430", "#8e5a3a", "#d79a62", grain=0.06, rand=0.1, tex=("wood", 0.5, 0.55))
M_wall = paint("wall", "#efc184", "#9a6250", "#d39e68", "#fbe0b0", grain=0.05, rand=0.14, tex=("wood", 0.4, 0.5))
M_plaster = paint("plaster", "#fbf0da", "#b8a0a0", "#e6d4bc", "#ffffff", var=0.05, vscale=0.8)
M_shingle = paint("shingle", "#e06a4e", "#8c3550", "#c04a42", "#ffab88", rand=0.16, tex=("roof", 0.9, 0.4))
M_ridge = paint("ridge", "#c9503f", "#6e2a42", "#a83d3c", "#f08a6a", rand=0.05)
M_shingle_b = paint("shingleb", "#5a8cdc", "#2c4a8e", "#4672c2", "#a6c8ff", rand=0.14, tex=("roof", 0.9, 0.4))
M_ridge_b = paint("ridgeb", "#3f6fc0", "#223a76", "#3459a0", "#7fa6ea", rand=0.05)
M_hole = flat("hole", "#3b2320")
M_glass = paint("glass", "#9fe0f5", "#3f7fb4", "#6fb8e2", "#e8fbff", ao=0.2)
M_straw = paint("straw", "#f6da7c", "#b5843e", "#dcb25a", "#fff2b8", rand=0.15, up=True)
M_bale = paint("bale", "#f6da7c", "#b5843e", "#dcb25a", "#fff2b8", grain=0.16, rand=0.05)
M_leaf = paint("leaf", "#8ad96a", "#2c6d58", "#56a75c", "#d2f59a", var=0.12, vscale=0.25, rand=0.06, ao=0.65, rim=0.25)
M_leaf2 = paint("leaf2", "#72c95c", "#24604f", "#4a9a54", "#bfe98c", var=0.12, vscale=0.25, rand=0.06, ao=0.65, rim=0.25)
M_pink = paint("pink", "#ffc0d6", "#b0638e", "#f08fb4", "#fff0f6", var=0.1, vscale=0.3, rand=0.06, ao=0.6, rim=0.25)
M_trunk = paint("trunk", "#a8744c", "#4e3036", "#7e5240", grain=0.05, tex=("bark", 0.7, 0.6))
M_burlap = paint("burlap", "#e1c495", "#8c6656", "#c2a072", "#f6e4c0", var=0.05, vscale=2.0)
M_petal = [paint("petw", "#ffffff", "#b5b8d8", "#e8e6f2", ao=0.3, rand=0.05), paint("petp", "#ff9cc2", "#b2507e", "#f077a2", ao=0.3, rand=0.08),
           paint("pety", "#ffd94a", "#c98a24", "#f2b934", ao=0.3, rand=0.08), paint("petv", "#b99cff", "#6a50b0", "#9479e6", ao=0.3, rand=0.08)]
M_core = paint("core", "#ffcc3a", "#c2771e", ao=0.2, rim=0)
M_lant = paint("lant", "#f0533f", "#8e2340", "#c83a3c", "#ffb08a")
M_gold = paint("gold", "#f6c64a", "#9a6a22", "#d49a2e", "#fff0a8")
M_grain = paint("grainm", "#ffe08a", "#c08a3a", ao=0.3, rim=0, rand=0.2)
M_water = paint("water", "#7fdcef", "#2f86b8", "#4fb6dc", "#e8fdff", var=0.1, vscale=0.5, up=True, ao=0.3, rim=0)
M_cloth = [paint("clr", "#ef5a4a", "#8e2a40", "#c8403e", "#ff9f8a"), paint("clw", "#fffaf0", "#b9b0c4", "#e8e0dc", "#ffffff"),
           paint("cly", "#ffcf3d", "#b97a1e", "#eaa82a", "#fff0a0"), paint("clb", "#4fa3ee", "#24508e", "#3a7ccc", "#a8d6ff")]
M_hill = [paint("hill1", "#a9d98a", "#6aa07e", "#8ec27c", var=0.1, vscale=0.08, ao=0.2, rim=0.3),
          paint("hill2", "#bfe2a4", "#8ab6a0", "#a8d096", var=0.08, vscale=0.06, ao=0.2, rim=0.3)]

# ---------------------------------------------------------------- pieces
def tuft(name, n=5, h=0.55, w=0.075, mat=None):
    """A clump of bent grass blades with a UV gradient (prototype for scatter)."""
    bm = bmesh.new(); uvl = bm.loops.layers.uv.new("UVMap")
    for i in range(n):
        a = i / n * 2 * math.pi + random.uniform(-0.3, 0.3); hh = h * random.uniform(0.7, 1.15); lean = random.uniform(0.15, 0.35)
        d = Vector((math.cos(a), math.sin(a), 0)); side = Vector((-d.y, d.x, 0))
        rows = []
        for j in range(4):
            t = j / 3; ww = w * (1 - t) + 0.004
            c = d * (lean * hh * t * t) + Vector((0, 0, hh * t))
            rows.append((bm.verts.new(c - side * ww), bm.verts.new(c + side * ww), t))
        for j in range(3):
            (a0, b0, t0), (a1, b1, t1) = rows[j], rows[j + 1]
            f = bm.faces.new((a0, b0, b1, a1))
            for lp, uv in zip(f.loops, ((0, t0), (1, t0), (1, t1), (0, t1))): lp[uvl].uv = uv
    o = mesh_obj(name, bm); o.data.materials.append(mat or M_blade)
    for p in o.data.polygons: p.use_smooth = True
    return proto(o)
T1 = tuft("tuft1"); T2 = tuft("tuft2", 7, 0.42, 0.06)

_FLOWERS = {}
def flower(pm):
    """A five-petal flower on a stem (prototype for scatter), one per petal material."""
    if pm.name in _FLOWERS: return _FLOWERS[pm.name]
    nm = "flower_" + pm.name
    parts = [blob(nm + "c", (0, 0, 0.32), 0.06, M_core, rough=0, subdiv=2)]
    for i in range(5):
        a = i / 5 * 2 * math.pi
        p = blob(nm + "p", (math.cos(a) * 0.09, math.sin(a) * 0.09, 0.31), 0.07, pm, squash=(1, 0.7, 0.35), rough=0, subdiv=2)
        p.rotation_euler = (0, 0, a); parts.append(p)
    parts.append(tube(nm + "s", (0, 0, 0), 0.015, 0.012, 0.3, M_blade, seg=6))
    o = proto(join(nm, parts)); _FLOWERS[pm.name] = o; return o

STRAW = proto(tube("strawp", (0, 0, 0), 0.02, 0.012, 0.5, M_straw, seg=5, rot=(0, math.radians(84), 0)))
PEBBLE = proto(blob("pebble", (0, 0, 0), 0.12, M_rock, squash=(1.3, 1, 0.55), rough=0.35, subdiv=2))

def scallop(o, r, scale=0.3, amount=0.12):
    """Leafy bumps: a Voronoi displacement gives a scalloped silhouette like painted foliage."""
    tex = bpy.data.textures.new(o.name + "_v", "VORONOI"); tex.distance_metric = "DISTANCE"; tex.noise_scale = scale * r
    tex.noise_intensity = 1.0; tex.color_mode = "INTENSITY"
    d = o.modifiers.new("scal", "DISPLACE"); d.texture = tex; d.strength = -r * amount; d.mid_level = 0.0; d.texture_coords = "GLOBAL"
    return o

def crown(c, r, mat, seed, lumps=7):
    """One foliage mass: a main ball and smaller balls bulging from its upper and outer side, each scalloped."""
    rnd = random.Random(seed); objs = [scallop(blob("crown", c, r, mat, squash=(1, 0.95, 0.86), rough=0.08, nscale=r, subdiv=5), r)]
    for i in range(lumps):
        a = rnd.uniform(0, 2 * math.pi); el = rnd.uniform(-0.15, 0.75)
        d = Vector((math.cos(a) * math.cos(el), math.sin(a) * math.cos(el) - 0.35, math.sin(el))).normalized()
        rr = r * rnd.uniform(0.38, 0.55)
        objs.append(scallop(blob("lump", c + d * r * 0.78, rr, mat, squash=(1, 0.95, 0.88), rough=0.06, nscale=rr, subdiv=4), rr))
    return objs

def tree(p, kind="leaf", s=1.0, seed=0):
    """A stylised tree about 2 chicken-heights tall at s=0.72. Returns its objects (for occluder layers)."""
    mat = {"leaf": M_leaf, "leaf2": M_leaf2, "pink": M_pink}[kind]; objs = []
    objs.append(tube("trunk", p, 0.55 * s, 0.32 * s, 4.6 * s, M_trunk, seg=16, rough=0.08 * s, ol=0.014))
    for k in range(4):  # root flares
        a = k / 4 * 2 * math.pi + 0.4
        objs.append(tube("root", p + Vector((math.cos(a) * 0.3 * s, math.sin(a) * 0.3 * s, -0.05)), 0.3 * s, 0.06 * s, 0.7 * s, M_trunk,
                         rot=(math.sin(a) * -1.25, math.cos(a) * 1.25, 0), ol=0.01))
    tg = scatter("treegrass", grid("tg", 3.2 * s, 16, lambda x, y: x * x + y * y < (1.5 * s) ** 2), T1, 9.0, (0.6, 1.0), seed=seed % 97)
    tg.location = p; objs.append(tg)
    for k, (dx, dy, dz, r) in enumerate(((0, 0, 6.0, 2.5), (-1.9, 0.3, 5.0, 1.8), (1.9, 0.1, 5.1, 1.9), (0.5, -0.8, 7.4, 1.7),
                                        (-0.9, -1.1, 5.4, 1.6), (1.0, 0.9, 6.8, 1.6))):
        objs += crown(p + Vector((dx * s, dy * s, dz * s)), r * s, mat, k + seed * 13)
    return objs

def bush(p, s=1.0, seed=0, flowers=None):
    objs = []
    for k, (dx, dy, dz, r) in enumerate(((-0.7, 0, 0.7, 1.0), (0.6, 0.2, 0.8, 1.15), (0.1, -0.4, 1.3, 0.85))):
        c = p + Vector((dx * s, dy * s, dz * s)); objs += crown(c, r * s, M_leaf, k + seed * 7, lumps=5)
        if k == 2 and flowers is not None:
            em = blob("bflem", c, r * s * 1.02, M_leaf, rough=0.25, subdiv=3)
            objs.append(scatter("bfl", em, flower(M_petal[flowers]), 1.6, (1.2, 1.6), seed=33 + seed, align=True, tilt=0.1))
    return objs

def fence(x0, x1, y, step=1.7):
    xs = []; x = x0; objs = []
    while x <= x1 + 1e-3: xs.append(x); x += step
    for x in xs:
        objs.append(bbox("fpost", (x, y, 0.75), (0.26, 0.26, 1.5), M_woodd, ol=0.012))
        bm = bmesh.new(); bmesh.ops.create_cone(bm, cap_ends=True, segments=4, radius1=0.2, radius2=0.0, depth=0.3)
        cp = mesh_obj("fcap", bm); cp.location = (x, y, 1.65); cp.rotation_euler = (0, 0, math.radians(45)); cp.data.materials.append(M_woodd)
        objs.append(outline(cp, 0.01))
    for z in (0.55, 1.1):
        for a, b in zip(xs, xs[1:]):
            objs.append(bbox("frail", ((a + b) / 2, y - 0.05, z), (b - a + 0.15, 0.12, 0.2), M_wood, rot=(0, random.uniform(-0.03, 0.03), 0), ol=0.01))
    return objs

def lantern(p, h=3.4, side=1):
    o = [tube("lpost", p, 0.12, 0.1, h, M_woodd, ol=0.012),
         bbox("larm", p + Vector((side * 0.45, 0, h - 0.15)), (0.95, 0.1, 0.1), M_woodd, ol=0.01),
         blob("lantern", p + Vector((side * 0.85, 0, h - 0.7)), 0.34, M_lant, squash=(1, 1, 1.25), rough=0, subdiv=3, ol=0.012)]
    for dz in (0.42, -0.42): o.append(tube("lcap", p + Vector((side * 0.85, 0, h - 0.7 + dz - 0.05)), 0.2, 0.2, 0.1, M_gold, seg=16, ol=0.008))
    return o

def gable_roof(C, W, D, zr, RW, RH, RD, shingle, ridge, rows=7, cols=11, wall=None, window=True):
    """A gable to the front with two slopes of staggered shingles, fascia boards and a ridge; returns objects."""
    objs = []; slope = math.atan2(RH, RW); Ls = math.hypot(RW, RH)
    gab = bmesh.new(); g3 = [gab.verts.new(v) for v in ((-W / 2, 0, 0), (W / 2, 0, 0), (0, 0, RH * (W / 2) / RW))]; gab.faces.new(g3)
    go = mesh_obj("gable", gab); go.location = C + Vector((0, -D / 2 + 0.05, zr)); go.data.materials.append(wall or M_wall)
    so_ = go.modifiers.new("th", "SOLIDIFY"); so_.thickness = 0.12; objs.append(go)
    if window:
        gw = C + Vector((0, -D / 2 - 0.06, zr + RH * (W / 2) / RW * 0.36))
        objs.append(blob("gwin", gw, 0.36, M_glass, squash=(1, 0.15, 1), rough=0, subdiv=3))
        bpy.ops.mesh.primitive_torus_add(major_radius=0.4, minor_radius=0.07, major_segments=36, minor_segments=8)
        t = bpy.context.active_object; t.name = "gwframe"; t.location = gw + Vector((0, -0.04, 0)); t.rotation_euler = (math.radians(90), 0, 0)
        t.data.materials.append(M_woodd); outline(t, 0.01); t.select_set(False); objs.append(t)
        objs.append(bbox("wbar", gw + Vector((0, -0.07, 0)), (0.7, 0.05, 0.06), M_woodd, bev=0.01, ol=0))
        objs.append(bbox("wbar", gw + Vector((0, -0.07, 0)), (0.06, 0.05, 0.7), M_woodd, bev=0.01, ol=0))
    for sx in (-1, 1):
        objs.append(bbox("slab", C + Vector((sx * RW / 2, 0, zr + RH / 2)), (Ls, RD, 0.12), ridge, rot=(0, sx * slope, 0), bev=0, ol=0))
        for r in range(rows):
            t = (r + 0.5) / rows
            for cidx in range(cols + (r % 2)):
                y = -RD / 2 + (cidx + (0.0 if r % 2 else 0.5)) * RD / cols
                if y > RD / 2 - 0.05: continue
                nrm = Vector((sx * math.sin(slope), 0, math.cos(slope)))
                pos = C + Vector((sx * RW * (1 - t), y, zr + RH * t)) + nrm * 0.1
                objs.append(bbox("shingle", pos, (Ls / rows + 0.12, RD / cols - 0.04, 0.1), shingle,
                                 rot=(random.uniform(-0.03, 0.03), sx * slope + random.uniform(-0.04, 0.04), random.uniform(-0.03, 0.03)), bev=0.035, ol=0.006))
        objs.append(bbox("fascia", C + Vector((sx * RW / 2, -RD / 2 - 0.02, zr + RH / 2 + 0.05)), (Ls + 0.25, 0.16, 0.24), M_woodd, rot=(0, sx * slope, 0), ol=0.012))
    objs.append(tube("ridge", C + Vector((0, -RD / 2 - 0.1, zr + RH + 0.12)), 0.2, 0.2, RD + 0.2, ridge, seg=16, rot=(math.radians(-90), 0, 0), ol=0.012))
    return objs

def coop(C, s=1.0, shingle=None, ridge=None, seed=0):
    """A chicken coop facing the camera: plank walls, a door with a ramp, a nameplate, a shingled gable roof.
    Returns (objects, door point, nameplate point)."""
    rnd = random.Random(seed); objs = []
    W, D, H = 5.2 * s, 4.2 * s, 3.0 * s; z0 = 0.36 * s
    objs.append(bbox("found", C + Vector((0, 0, z0 / 2)), (W + 0.5 * s, D + 0.5 * s, z0), M_rock, bev=0.08, ol=0.016))
    objs.append(bbox("body", C + Vector((0, 0.1, z0 + H / 2)), (W - 0.1, D - 0.2, H), M_wall, bev=0.02, ol=0))
    door_w, door_h = 1.5 * s, 1.85 * s
    pw = 0.4 * s; x = -W / 2 + pw / 2 + 0.02
    while x < W / 2 - 0.1:
        hh = H + rnd.uniform(-0.04, 0.05); zz = z0
        if abs(x) < door_w / 2 + 0.05: zz = z0 + door_h; hh = H - door_h + rnd.uniform(-0.02, 0.04)
        p = bbox("plank", C + Vector((x, -D / 2, zz + hh / 2)), (pw - 0.035, 0.16, hh), M_wall, bev=0.03, ol=0.008)
        p.rotation_euler = (0, rnd.uniform(-0.012, 0.012), 0); objs.append(p); x += pw
    objs.append(bbox("doorhole", C + Vector((0, -D / 2 + 0.03, z0 + door_h / 2)), (door_w, 0.1, door_h), M_hole, bev=0, ol=0))
    for sx in (-1, 1): objs.append(bbox("jamb", C + Vector((sx * (door_w / 2 + 0.08), -D / 2 - 0.1, z0 + door_h / 2)), (0.2, 0.2, door_h + 0.1), M_woodd, ol=0.012))
    objs.append(bbox("lintel", C + Vector((0, -D / 2 - 0.12, z0 + door_h + 0.08)), (door_w + 0.6, 0.24, 0.24), M_woodd, ol=0.012))
    for k in range(5):
        objs.append(bbox("slat", C + Vector((0, -D / 2 - 0.45 * s - k * 0.32 * s, z0 * 0.8 - k * 0.06 * s)), (door_w * 0.9, 0.26 * s, 0.08), M_wood, rot=(0.18, 0, 0), ol=0.008))
    for sx in (-1, 1):
        objs.append(bbox("post", C + Vector((sx * (W / 2 + 0.05), -D / 2 - 0.05, z0 + H / 2 + 0.05)), (0.34 * s, 0.34 * s, H + 0.1), M_woodd, ol=0.014))
    objs.append(bbox("beam", C + Vector((0, -D / 2 - 0.1, z0 + H + 0.05)), (W + 0.5 * s, 0.3 * s, 0.26 * s), M_woodd, ol=0.014))
    plate = C + Vector((0, -D / 2 - 0.26, z0 + H - 0.42 * s))
    objs.append(bbox("plate", plate, (1.9 * s, 0.08, 0.5 * s), M_wood, bev=0.05, ol=0.012))
    for sx in (-1, 1): objs.append(blob("nail", plate + Vector((sx * 0.8 * s, -0.05, 0)), 0.045, M_hole, rough=0, subdiv=1))
    objs += gable_roof(C, W, D, z0 + H + 0.12, W / 2 + 0.55 * s, 2.2 * s, D + 0.9 * s, shingle or M_shingle, ridge or M_ridge)
    st = grid("straw_s", 3 * s, 12, lambda x, y: x * x / (1.6 * s * s) + y * y / (0.5 * s * s) < 1)
    st.location = C + Vector((0.2 * s, -D / 2 - 1.2 * s, 0.04)); objs.append(scatter("straw", st, STRAW, 55 / (s * s), (0.7, 1.3) if s >= 1 else (0.6, 1.1), seed=4 + seed, tilt=0.12))
    door = C + Vector((0, -D / 2 - 2.2 * s, 0))
    return objs, door, plate

def rock_ring(edge, n, gap=None, rmin=0.32, rmax=0.46, seed=0):
    """Stones along a closed curve edge(a); gap=(angle, half width) leaves an opening."""
    rnd = random.Random(seed); objs = []
    for k in range(n):
        a = k / n * 2 * math.pi
        if gap and any(abs((a - g0 + math.pi) % (2 * math.pi) - math.pi) < gw for g0, gw in gap): continue
        p = edge(a) + Vector((0, 0, 0.05))
        objs.append(blob("rimstone", p, rnd.uniform(rmin, rmax), M_rock, squash=(1.25, 1.0, 0.55), rough=0.28, ol=0.012))
    return objs

# ---------------------------------------------------------------- light, camera, grade
def rig():
    world.node_tree.nodes["Background"].inputs[0].default_value = lin("#b9daf2"); world.node_tree.nodes["Background"].inputs[1].default_value = 0.3
    sun = bpy.data.lights.new("sun", "SUN"); sun.energy = SUN_E * 1.2; sun.color = lin("#fff4e2")[:3]; sun.use_shadow = True; sun.angle = math.radians(3.5)
    so = link(bpy.data.objects.new("sun", sun)); so.rotation_euler = SUN_DIR.to_track_quat("-Z", "Y").to_euler()
    # a soft fill from the camera side, no shadow: lifts the faces of characters under their own big heads
    fill = bpy.data.lights.new("fill", "SUN"); fill.energy = 0.75; fill.use_shadow = False
    fo = link(bpy.data.objects.new("fill", fill)); fo.rotation_euler = Vector((-0.25, 0.9, -0.35)).normalized().to_track_quat("-Z", "Y").to_euler()
    return so, fo

def cam_fwd():
    th = math.radians(90 - CAM_TILT); return Vector((0, math.sin(th), -math.cos(th)))

def camera(ortho, tgt, res, dist=90):
    """Orthographic camera looking CAM_TILT degrees down at tgt; ortho = width in world units."""
    sc.render.resolution_x, sc.render.resolution_y = res
    cam = bpy.data.cameras.new("cam"); cam.type = "ORTHO"; cam.ortho_scale = ortho; cam.clip_end = 400
    co = link(bpy.data.objects.new("cam", cam)); co.location = Vector(tgt) - cam_fwd() * dist
    co.rotation_euler = (math.radians(90 - CAM_TILT), 0, 0); sc.camera = co
    return co

def grade(haze_from=None, haze_to=None, haze=0.1, bloom=False):
    """Compositor: depth haze (camera distance haze_from..haze_to fades towards a light sky colour), bloom, grade."""
    sc.use_nodes = True; ct = sc.node_tree; rl = ct.nodes.get("Render Layers"); cp_ = ct.nodes.get("Composite")
    img = rl.outputs["Image"]
    if haze_from is not None:
        bpy.context.view_layer.use_pass_z = True
        mr = ct.nodes.new("CompositorNodeMapRange"); mr.inputs[1].default_value = haze_from; mr.inputs[2].default_value = haze_to
        mr.inputs[3].default_value = 0.0; mr.inputs[4].default_value = haze; mr.use_clamp = True
        ct.links.new(rl.outputs["Depth"], mr.inputs[0])
        hz = ct.nodes.new("CompositorNodeMixRGB"); hz.use_alpha = False; hz.inputs[2].default_value = lin("#e4f4ff")
        ct.links.new(mr.outputs[0], hz.inputs[0]); ct.links.new(img, hz.inputs[1]); img = hz.outputs[0]
    if STYLE == "kuw":
        kw = ct.nodes.new("CompositorNodeKuwahara"); kw.variation = "ANISOTROPIC"
        kw.inputs["Size"].default_value = 5; kw.inputs["Uniformity"].default_value = 4; kw.inputs["Sharpness"].default_value = 0.6; kw.inputs["Eccentricity"].default_value = 1.0
        ct.links.new(img, kw.inputs["Image"]); img = kw.outputs[0]
    if bloom:
        gl = ct.nodes.new("CompositorNodeGlare"); gl.glare_type = "BLOOM"; gl.threshold = 0.82; gl.mix = -0.82; gl.size = 7
        ct.links.new(img, gl.inputs["Image"]); img = gl.outputs["Image"]
    hs = ct.nodes.new("CompositorNodeHueSat"); hs.inputs["Saturation"].default_value = 1.04  # vivid, but not candy
    bc = ct.nodes.new("CompositorNodeBrightContrast"); bc.inputs["Contrast"].default_value = 7.0
    ct.links.new(img, hs.inputs["Image"]); ct.links.new(hs.outputs[0], bc.inputs["Image"])
    # keep the render's own alpha (transparent sky, cut-out layers): the filters above may not carry it through
    sa = ct.nodes.new("CompositorNodeSetAlpha"); sa.mode = "REPLACE_ALPHA"
    ct.links.new(bc.outputs[0], sa.inputs["Image"]); ct.links.new(rl.outputs["Alpha"], sa.inputs["Alpha"]); ct.links.new(sa.outputs[0], cp_.inputs["Image"])

def to_screen(co):
    """World point -> (x, y) in 0..1 of the rendered picture, y from the top."""
    from bpy_extras.object_utils import world_to_camera_view
    v = world_to_camera_view(sc, sc.camera, Vector(co)); return (round(v.x, 5), round(1 - v.y, 5))
