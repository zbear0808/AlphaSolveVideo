"""Render the logo as seen by one stage's fixed Melee camera. Runs inside Blender, started by plate.py:

    Blender -b logo_metal_fracture.blend -S SH010_Reveal --python blender_plate.py -- JOB.json

The logo keeps its own size (1.77 m wide, so the lights, the HDRI, the scratch maps and the bevel stay exactly as
they were built). Melee's world is mapped onto it instead: one Melee unit is `s` logo metres, the logo's ground
line is Melee's stage top, and the camera is placed where Melee's camera would be after the same mapping. The
projection does not change under a uniform scale, so the picture is what a logo `s` times bigger would give.

    Melee (X right, Y up, Z to the camera)  ->  Blender (X right, Y away from the camera, Z up)
    Blender point = (cx + (X - xc) / s,   y0 - Z / s,   zg + (Y - ground_y) / s)

Any other model works the same way (job key `model`): a .blend that Blender opened, or a file imported into an
empty scene (glTF, FBX, OBJ, STL, PLY, USD, Alembic). Its separate objects are fitted as one, and it gets a light
rig of its own if it brings no lights.

With a camera export (job key `camera_export`, `slp2alpha render --export-camera`) the camera moves as the game's
did, and every frame is rendered into the folder `out` (000001.png for the video's first frame).

Job keys: out (png, or a folder with camera_export), camera {eye, fov, vert, horz, aspect, interest}, scale (output
size multiplier, 640x528 at 1), size ([width, height] of the recording, default 640x528 per scale step), style
(metal | cel | original), fit {width, center_x, to: bbox | letters, scale}, ground {y, line: xheight | top, offset},
depth_shift, outline_px, samples, frame, model {path, objects, rotation}, camera_export, frames ([first, last]
Blender frames of a camera export to render).
"""

import json
import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import projection  # noqa: E402

CAMERA_EXPORT_DIR = os.path.join(os.path.dirname(HERE), "camera-export")
LOGO = "SM_Logo_Hero"
# How far above the logo the project's front shot (CAM_SH020_Still_Front) looks at it: 0.2 m up at 4.45 m.
REFERENCE_ELEVATION_DEG = 2.57
# Object types whose evaluated geometry is a mesh, so they can be measured and drawn in the cel finish.
GEOMETRY = {"MESH", "CURVE", "SURFACE", "FONT", "META"}
# Importers by file extension: (operator module, operator name).
IMPORTERS = {
    ".glb": ("import_scene", "gltf"), ".gltf": ("import_scene", "gltf"),
    ".fbx": ("import_scene", "fbx"),
    ".obj": ("wm", "obj_import"),
    ".stl": ("wm", "stl_import"),
    ".ply": ("wm", "ply_import"),
    ".usd": ("wm", "usd_import"), ".usda": ("wm", "usd_import"), ".usdc": ("wm", "usd_import"),
    ".usdz": ("wm", "usd_import"),
    ".abc": ("wm", "alembic_import"),
}

# The cel finish of the kitty_logo_crash project (klc_cel.py), without the cracks: flat colour bands from a hard
# ramp on 0.45 N.L + 0.55 (where the view ray reflects), a hard specular glint, a chrome horizon, a flat diagonal gleam.
CEL = dict(
    light=(0.41, -0.709, 0.574), w_diffuse=0.45, w_reflect=0.55, bias=0.0,
    ramp=[(0.00, (0.035, 0.040, 0.130)), (0.26, (0.100, 0.120, 0.300)), (0.41, (0.260, 0.320, 0.540)),
          (0.64, (0.640, 0.720, 0.880)), (0.86, (0.975, 0.985, 1.000))],
    spec_cut=0.975, spec_col=(1.0, 1.0, 1.0),
    horizon=dict(z=1.12, drop=0.14, line=0.005, facing=0.80),
    gleam=dict(dir=(0.62, 0.0, 0.78), period=0.62, width=0.040, gap=0.026, width2=0.014, phase=0.10, min_ndl=0.55),
    ink=(0.020, 0.010, 0.030, 1.0),
)


def log(*a):
    print("[plate]", *a, flush=True)


# ---------------------------------------------------------------- the logo
def logo_islands(ob):
    """(x0, x1, z0, z1) of every separate piece of the evaluated logo (letters, i-dot, hearts), sorted by x."""
    import bmesh
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.transform(ob.matrix_world)
    seen, islands = set(), []
    for v in bm.verts:
        if v.index in seen:
            continue
        stack, comp = [v], []
        seen.add(v.index)
        while stack:
            a = stack.pop()
            comp.append(a)
            for e in a.link_edges:
                b = e.other_vert(a)
                if b.index not in seen:
                    seen.add(b.index)
                    stack.append(b)
        xs, zs = [p.co.x for p in comp], [p.co.z for p in comp]
        ys = [p.co.y for p in comp]
        islands.append((min(xs), max(xs), min(zs), max(zs), min(ys), max(ys)))
    bm.free()
    ev.to_mesh_clear()
    return sorted(islands)


def median(vals):
    vals = sorted(vals)
    n = len(vals)
    return vals[n // 2] if n % 2 else 0.5 * (vals[n // 2 - 1] + vals[n // 2])


def logo_frame(ob, fit_to, ground_line):
    """Where the logo's fit width (x0, x1) and its ground line sit, in Blender metres."""
    isl = logo_islands(ob)
    used = isl[1:-1] if (fit_to == "letters" and len(isl) > 2) else isl
    x0, x1 = min(i[0] for i in used), max(i[1] for i in used)
    top = max(i[3] for i in isl)
    ground = top if ground_line == "top" else median([i[3] for i in isl])
    return dict(x0=x0, x1=x1, ground=ground, top=top, bottom=min(i[2] for i in isl),
                y0=min(i[4] for i in isl), y1=max(i[5] for i in isl), islands=len(isl))


# ---------------------------------------------------------------- any other model
def drawn_objects():
    """The scene's objects with geometry that a render draws: in the view layer, not hidden from renders."""
    return [ob for ob in bpy.context.view_layer.objects
            if ob.type in GEOMETRY and not ob.hide_render and not any(c.hide_render for c in ob.users_collection)]


def load_model(sc, model):
    """The model's objects: the ones the job names, or every one with geometry that renders. Blender has opened a
    .blend already; any other file is imported into the startup scene, emptied first (its cube, light and camera)."""
    path = Path(model["path"])
    ext = path.suffix.lower()
    if ext != ".blend":
        if ext not in IMPORTERS:
            raise ValueError(f"can't import {path.name}: supported are .blend, {', '.join(sorted(IMPORTERS))}")
        for ob in list(sc.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        module, name = IMPORTERS[ext]
        before = set(bpy.data.objects)
        getattr(getattr(bpy.ops, module), name)(filepath=str(path))
        for ob in [o for o in bpy.data.objects if o not in before and o.type == "CAMERA"]:
            bpy.data.objects.remove(ob, do_unlink=True)   # the stage's camera is the only one
    drawn = drawn_objects()
    names = model.get("objects")
    if names:
        missing = [n for n in names if n not in sc.objects]
        if missing:
            have = ", ".join(sorted(o.name for o in drawn)[:20])
            raise ValueError(f"{path.name} has no object named {', '.join(missing)} (it has: {have})")
        objects = [sc.objects[n] for n in names]
        for ob in drawn:
            if ob not in objects:
                ob.hide_render = True
    else:
        objects = drawn
    if not objects:
        raise ValueError(f"{path.name} has nothing to draw (no mesh, curve or text object that renders)")
    return objects


def turn(objects, degrees):
    """Turn the model (its hierarchies' roots, so rigs and children follow) about the world's origin: `degrees`
    is the angle about the vertical, or [x, y, z] Euler angles (XYZ, degrees)."""
    from mathutils import Euler
    x, y, z = (0.0, 0.0, float(degrees)) if isinstance(degrees, (int, float)) else (float(d) for d in degrees)
    r = Euler((math.radians(x), math.radians(y), math.radians(z)), "XYZ").to_matrix().to_4x4()
    roots = set()
    for ob in objects:
        while ob.parent is not None:
            ob = ob.parent
        roots.add(ob)
    for ob in roots:
        ob.matrix_world = r @ ob.matrix_world
    bpy.context.view_layer.update()


def island_tops(me, z):
    """The highest z of each separate piece (connected vertices) of a mesh."""
    import numpy as np
    n = len(me.vertices)
    edges = np.empty(2 * len(me.edges), dtype=np.int32)
    me.edges.foreach_get("vertices", edges)
    a, b = edges[0::2], edges[1::2]
    label = np.arange(n)
    while True:   # each vertex takes the smallest label it touches, then jumps along the labels
        low = np.minimum(label[a], label[b])
        new = label.copy()
        np.minimum.at(new, a, low)
        np.minimum.at(new, b, low)
        new = new[new]
        if np.array_equal(new, label):
            break
        label = new
    tops = np.full(n, -np.inf)
    np.maximum.at(tops, label, z)
    return [float(t) for t in tops[np.unique(label)]]


def model_frame(objects, ground_line):
    """logo_frame for any objects, fitted as one: their bounding box in Blender units, and the ground line at the
    highest point (top) or at the median of the tops of the separate pieces (xheight: a logo's lowercase letters)."""
    import numpy as np
    dg = bpy.context.evaluated_depsgraph_get()
    lows, highs, tops = [], [], []
    for ob in objects:
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        try:
            n = len(me.vertices)
            if not n:
                continue
            co = np.empty(3 * n, dtype=np.float32)
            me.vertices.foreach_get("co", co)
            m = np.array(ev.matrix_world, dtype=np.float64)
            world = co.reshape(-1, 3).astype(np.float64) @ m[:3, :3].T + m[:3, 3]
            lows.append(world.min(axis=0))
            highs.append(world.max(axis=0))
            if ground_line == "xheight":
                tops += island_tops(me, world[:, 2])
        finally:
            ev.to_mesh_clear()
    if not lows:
        raise ValueError("the model has no vertices")
    lo, hi = np.min(lows, axis=0), np.max(highs, axis=0)
    if hi[0] - lo[0] <= 0:
        raise ValueError("the model has no width")
    ground = median(tops) if ground_line == "xheight" and tops else float(hi[2])
    return dict(x0=float(lo[0]), x1=float(hi[0]), ground=ground, top=float(hi[2]), bottom=float(lo[2]),
                y0=float(lo[1]), y1=float(hi[1]), islands=len(tops) or len(lows))


def as_mesh(ob):
    """A mesh object drawing what `ob` draws (a curve or text becomes a mesh, hidden original), for the cel finish."""
    if ob.type == "MESH":
        return ob
    dg = bpy.context.evaluated_depsgraph_get()
    mesh = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    new = bpy.data.objects.new(f"{ob.name}_mesh", mesh)
    new.matrix_world = ob.matrix_world.copy()
    for col in ob.users_collection:
        col.objects.link(new)
    ob.hide_render = True
    return new


def add_light_rig(sc, eye, target):
    """Lights for a model that brings none: a key from the camera's upper left, a softer fill from the right, a rim
    from behind, and a dim grey world so that what the key doesn't reach isn't black."""
    fwd = (target - eye).normalized()
    up = Vector((0.0, 0.0, 1.0))
    right = fwd.cross(up).normalized()
    up = right.cross(fwd).normalized()
    for name, travels, energy, angle in (("LGT_Key", fwd + 0.6 * right - 0.8 * up, 3.0, 4.0),
                                         ("LGT_Fill", fwd - 0.9 * right - 0.2 * up, 1.0, 15.0),
                                         ("LGT_Rim", -fwd + 0.3 * right - 0.9 * up, 2.5, 4.0)):
        data = bpy.data.lights.new(name, "SUN")
        data.energy, data.angle = energy, math.radians(angle)
        ob = bpy.data.objects.new(name, data)
        sc.collection.objects.link(ob)
        ob.rotation_euler = travels.normalized().to_track_quat("-Z", "Y").to_euler()   # a sun shines along its -Z
    world = sc.world or bpy.data.worlds.new("WRL_Plate")
    sc.world = world
    world.use_nodes = True
    bg = next((n for n in world.node_tree.nodes if n.type == "BACKGROUND"), None)
    if bg is not None:
        bg.inputs["Color"].default_value = (0.20, 0.21, 0.23, 1.0)
        bg.inputs["Strength"].default_value = 0.8


# ---------------------------------------------------------------- Melee -> Blender
class Mapping:
    def __init__(self, s, xc, ground_y, cx, zg, y0):
        self.s, self.xc, self.ground_y, self.cx, self.zg, self.y0 = s, xc, ground_y, cx, zg, y0

    def point(self, p):
        X, Y, Z = p
        return Vector((self.cx + (X - self.xc) / self.s, self.y0 - Z / self.s, self.zg + (Y - self.ground_y) / self.s))


def make_camera(sc, cam, mapping, scale, size=None, clip=(0.05, 400.0)):
    """A Blender camera that sees the mapped world exactly as Melee's camera sees the real one. With `interest`
    in the job the camera looks at that point (the game's own, projection.game_interest), else at the point
    Camera.interest works out from the stage's angles. size: the recording's [width, height]."""
    aspect = cam.get("aspect", projection.ASPECT)
    if cam.get("interest"):
        mc = projection.LookAtCamera(tuple(cam["eye"]), tuple(cam["interest"]), cam["fov"], 0.0, aspect)
    else:
        mc = projection.Camera(tuple(cam["eye"]), cam["fov"], cam["vert"], cam.get("horz", 0.0), aspect)
    width, height = (int(size[0]), int(size[1])) if size else mc.size(scale)
    data = bpy.data.cameras.new("CAM_Melee")
    data.sensor_fit = "HORIZONTAL"
    data.sensor_width = 36.0
    data.lens = (data.sensor_width / 2) / mc.tan_half_h
    data.clip_start, data.clip_end = clip
    data.dof.use_dof = False
    ob = bpy.data.objects.new("CAM_Melee", data)
    sc.collection.objects.link(ob)
    eye, target = mapping.point(mc.eye), mapping.point(mc.interest)
    ob.location = eye
    ob.rotation_euler = (target - eye).to_track_quat("-Z", "Y").to_euler()
    sc.camera = ob
    bpy.context.view_layer.update()   # world_to_camera_view reads matrix_world, which is stale until now
    r = sc.render
    r.resolution_x, r.resolution_y, r.resolution_percentage = width, height, 100
    # Melee's picture is 640 x 528 for a camera aspect of 1.2173: the pixels are a hair wider than tall. A raw
    # recording, 640 x 480, has pixels narrower than tall; Blender's pixel aspects are 1 or more, so that one goes
    # on y (as import_melee_camera.pixel_aspect does).
    wide = height * mc.aspect / width
    r.pixel_aspect_x, r.pixel_aspect_y = (wide, 1.0) if wide >= 1.0 else (1.0, 1.0 / wide)
    return ob, mc


def world_to_pixel(sc, cam_ob, p):
    """(u, v) of a Blender point in the render, v down, using Blender's own camera model."""
    from bpy_extras.object_utils import world_to_camera_view
    c = world_to_camera_view(sc, cam_ob, p)
    return c.x * sc.render.resolution_x, (1.0 - c.y) * sc.render.resolution_y


# ---------------------------------------------------------------- the cel finish
class Graph:
    def __init__(self, mat):
        self.nt = mat.node_tree
        self.N, self.L = self.nt.nodes, self.nt.links

    def node(self, idname, name, **props):
        nd = self.N.new(idname)
        nd.name = nd.label = name
        for k, v in props.items():
            setattr(nd, k, v)
        return nd

    def link(self, a, b):
        self.L.new(a, b)

    def _feed(self, sock, v):
        if hasattr(v, "is_output"):
            self.link(v, sock)
        elif v is not None:
            sock.default_value = v

    def vmath(self, name, op, a=None, b=None, scale=None):
        nd = self.node("ShaderNodeVectorMath", name, operation=op)
        for i, v in enumerate((a, b)):
            self._feed(nd.inputs[i], v)
        if scale is not None:
            nd.inputs[3].default_value = scale
        return nd

    def math(self, name, op, a=None, b=None, c=None, clamp=False):
        nd = self.node("ShaderNodeMath", name, operation=op, use_clamp=clamp)
        for i, v in enumerate((a, b, c)):
            self._feed(nd.inputs[i], v)
        return nd

    def ramp(self, name, stops, fac):
        nd = self.node("ShaderNodeValToRGB", name)
        cr = nd.color_ramp
        cr.interpolation = "CONSTANT"
        while len(cr.elements) > 1:
            cr.elements.remove(cr.elements[-1])
        cr.elements[0].position, cr.elements[0].color = stops[0][0], (*stops[0][1], 1.0)
        for pos, col in stops[1:]:
            cr.elements.new(pos).color = (*col, 1.0)
        self.link(fac, nd.inputs["Fac"])
        return nd

    def mix(self, name, fac, a, b):
        nd = self.node("ShaderNodeMix", name, data_type="RGBA", blend_type="MIX")
        for sock, v in ((nd.inputs[0], fac), (nd.inputs[6], a), (nd.inputs[7], b)):
            if hasattr(v, "is_output"):
                self.link(v, sock)
            elif isinstance(v, (int, float)):
                sock.default_value = v
            else:
                sock.default_value = (*v, 1.0)
        return nd.outputs[2]


def build_cel_material(name="MAT_Logo_Cel", p=CEL):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    g = Graph(mat)
    out = g.node("ShaderNodeOutputMaterial", "OUT")
    geo = g.node("ShaderNodeNewGeometry", "GEO")
    L = tuple(p["light"])
    ndl = g.vmath("VM_NdotL", "DOT_PRODUCT", geo.outputs["Normal"], L)
    d01 = g.math("M_D01", "MULTIPLY_ADD", ndl.outputs["Value"], 0.5, 0.5)
    neg_i = g.vmath("VM_NegIncoming", "SCALE", geo.outputs["Incoming"], None, scale=-1.0)
    refl = g.vmath("VM_Reflect", "REFLECT", neg_i.outputs[0], geo.outputs["Normal"])
    sepr = g.node("ShaderNodeSeparateXYZ", "SEP_Reflect")
    g.link(refl.outputs[0], sepr.inputs[0])
    r01 = g.math("M_R01", "MULTIPLY_ADD", sepr.outputs["Z"], 0.5, 0.5)
    sd = g.math("M_SD", "MULTIPLY", d01.outputs[0], p["w_diffuse"])
    s = g.math("M_S", "MULTIPLY_ADD", r01.outputs[0], p["w_reflect"], sd.outputs[0])
    if p["bias"]:
        s = g.math("M_SBias", "ADD", s.outputs[0], p["bias"])

    sep = g.node("ShaderNodeSeparateXYZ", "SEP_Pos")
    g.link(geo.outputs["Position"], sep.inputs[0])
    hz = p["horizon"]
    front = g.math("M_HzFacing", "GREATER_THAN", d01.outputs[0], hz["facing"])
    below = g.math("M_HzBelow", "LESS_THAN", sep.outputs["Z"], hz["z"])
    low = g.math("M_HzLow", "MULTIPLY", below.outputs[0], front.outputs[0])
    s = g.math("M_SHorizon", "MULTIPLY_ADD", low.outputs[0], -hz["drop"], s.outputs[0])
    dz = g.math("M_HzDist", "SUBTRACT", sep.outputs["Z"], hz["z"])
    az = g.math("M_HzAbs", "ABSOLUTE", dz.outputs[0])
    near = g.math("M_HzNear", "LESS_THAN", az.outputs[0], hz["line"])
    hz_line = g.math("M_HzLine", "MULTIPLY", near.outputs[0], front.outputs[0])
    band = g.ramp("RAMP_Bands", p["ramp"], s.outputs[0])

    half = g.vmath("VM_Half", "ADD", L, geo.outputs["Incoming"])
    half_n = g.vmath("VM_HalfN", "NORMALIZE", half.outputs[0])
    nh = g.vmath("VM_NdotH", "DOT_PRODUCT", geo.outputs["Normal"], half_n.outputs[0])
    spec = g.math("M_Spec", "GREATER_THAN", nh.outputs["Value"], p["spec_cut"])
    col = g.mix("MIX_Spec", spec.outputs[0], band.outputs["Color"], p["spec_col"])
    col = g.mix("MIX_HzLine", hz_line.outputs[0], col, p["spec_col"])

    gl = p["gleam"]
    per = gl["period"]
    gdir = g.vmath("VM_GleamDot", "DOT_PRODUCT", geo.outputs["Position"], gl["dir"])
    gph = g.math("M_GleamPhase", "MULTIPLY_ADD", gdir.outputs["Value"], 1.0 / per, gl["phase"] / per)
    gfr = g.math("M_GleamFract", "FRACT", gph.outputs[0])
    w1, g1, w2 = gl["width"] / per, gl["gap"] / per, gl["width2"] / per
    in1 = g.math("M_GleamBand1", "LESS_THAN", gfr.outputs[0], w1)
    lo2 = g.math("M_GleamBand2Lo", "GREATER_THAN", gfr.outputs[0], w1 + g1)
    hi2 = g.math("M_GleamBand2Hi", "LESS_THAN", gfr.outputs[0], w1 + g1 + w2)
    in2 = g.math("M_GleamBand2", "MULTIPLY", lo2.outputs[0], hi2.outputs[0])
    both = g.math("M_GleamBands", "ADD", in1.outputs[0], in2.outputs[0], clamp=True)
    gfc = g.math("M_GleamFacing", "GREATER_THAN", ndl.outputs["Value"], gl["min_ndl"])
    gmk = g.math("M_GleamMask", "MULTIPLY", both.outputs[0], gfc.outputs[0])
    col = g.mix("MIX_Gleam", gmk.outputs[0], col, p["spec_col"])

    em = g.node("ShaderNodeEmission", "EM_Cel")
    em.inputs["Strength"].default_value = 1.0
    g.link(col, em.inputs["Color"])
    g.link(em.outputs[0], out.inputs["Surface"])
    return mat


def build_ink_material(name="M_Outline_Ink", color=CEL["ink"]):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = color
    em.inputs["Strength"].default_value = 1.0
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    mat.use_backface_culling = True   # only the shell's inside faces show: an outline around the silhouette
    return mat


def apply_cel(ob, thickness, materials=None):
    """Flat toon bands plus an ink outline shell (Solidify, flipped normals, offset +1), like the character's.
    materials: the (cel, ink) pair to use, so that several objects share one."""
    cel, ink = materials or (build_cel_material(), build_ink_material())
    me = ob.data
    me.materials.clear()
    me.materials.append(cel)
    me.materials.append(ink)
    me.polygons.foreach_set("material_index", [0] * len(me.polygons))
    me.update()
    mod = ob.modifiers.new("Outline", "SOLIDIFY")
    mod.use_flip_normals = True
    mod.offset = 1.0
    mod.use_rim = False
    mod.use_even_offset = False
    mod.thickness = thickness
    mod.material_offset = 1
    return cel, ink


# ---------------------------------------------------------------- render settings
def set_enum(obj, attr, options):
    for o in options:
        try:
            setattr(obj, attr, o)
            return o
        except (TypeError, ValueError):
            continue
    raise ValueError(f"none of {options} accepted for {attr}")


def tilt_studio(sc, beta_deg, center):
    """Keep the metal's look when the camera sees the logo from higher up than the project's own front shot does.

    A polished vertical face mirrors whatever lies along the reflected view ray, which points as far below the
    horizon as the camera is above the logo. The project's front shot (CAM_SH020_Still_Front) is 2.6 degrees above
    the logo, so the face mirrors the studio's horizon; from the stage camera (18 degrees above the logo on
    Battlefield) it would mirror the bright floor and the low fill light and turn white. Rotating the whole
    studio (lights and HDRI) about the logo's centre by the difference puts the same things back in the mirror."""
    b = math.radians(beta_deg)
    pivot = Matrix.Translation(center) @ Matrix.Rotation(b, 4, "X") @ Matrix.Translation(-center)
    moved = []
    for ob in sc.objects:
        if ob.type != "LIGHT":
            continue
        if ob.name.startswith("LGT_Sweep"):    # the animated glint of the hero shot
            ob.data.energy = 0.0
            continue
        ob.matrix_world = pivot @ ob.matrix_world
        moved.append(ob.name)
    node = sc.world.node_tree.nodes.get("PARAM_HDRI_Rotation") if sc.world and sc.world.node_tree else None
    if node is not None:
        node.inputs["Rotation"].default_value = (-b, 0.0, 0.0)
    return moved


def configure_render(sc, job):
    r = sc.render
    set_enum(r, "engine", ["BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"])
    ee = sc.eevee
    cel = job["style"] == "cel"
    samples = int(job.get("samples") or (32 if cel else 64))
    # No overscan: EEVEE's moves the picture off the camera's projection (up to 0.5 px at 640 x 528, 1.6 px with
    # the non-square pixels of a raw recording), which the fighters would then not stand on. The cel finish is
    # emission only, so shadows change none of its pixels, and cost it two thirds of each frame on an M1. Job key
    # `shadows` (default true) turns them off for the other finishes too.
    shadows = not cel and bool(job.get("shadows", True))
    for attr, value in (("taa_render_samples", samples), ("use_raytracing", not cel), ("use_shadows", shadows),
                        ("use_overscan", False), ("motion_blur_steps", 1)):
        if hasattr(ee, attr):
            setattr(ee, attr, value)
    r.use_motion_blur = False
    r.film_transparent = True
    if cel:   # flat colours stay flat: Standard view, no bloom; a narrower pixel filter keeps the ink line crisp
        set_enum(sc.view_settings, "view_transform", ["Standard"])
        set_enum(sc.view_settings, "look", ["None"])
        r.filter_size = float(job.get("filter_size", 0.6))
    im = r.image_settings
    if hasattr(im, "media_type"):
        im.media_type = "IMAGE"
    im.file_format = "PNG"
    im.color_mode = "RGBA"
    im.color_depth = "16"
    im.compression = 15
    r.use_file_extension = False
    r.filepath = job["out"]
    if hasattr(sc, "compositing_node_group"):
        sc.compositing_node_group = None   # the project's own render script adds a glow pass in memory; not wanted here
    apply_eevee_overrides(sc, job.get("eevee") or {})


def apply_eevee_overrides(sc, overrides):
    """Job key `eevee`: EEVEE settings to set last, by name (`use_shadows`, `shadow_resolution_scale`, ...); names
    starting `ray_tracing_options.` go to the ray-tracing options. For measuring what each setting costs."""
    ee = sc.eevee
    for name, value in overrides.items():
        target, attr = (ee.ray_tracing_options, name.split(".", 1)[1]) if name.startswith("ray_tracing_options.") \
            else (ee, name)
        if not hasattr(target, attr):
            raise ValueError(f"EEVEE has no setting {name}")
        setattr(target, attr, value)
        log("eevee", name, "=", value)


def import_moving_camera(sc, path, mapping):
    """The camera export as an animated camera in the mapped world (tools/camera-export/import_melee_camera.py):
    Melee's point (X, Y, Z) lands at offset + (X, -Z, Y) / s there, which is mapping.point. It also sets the
    scene's resolution, pixel aspect, frame rate (exactly 60) and frame range to the video's."""
    if CAMERA_EXPORT_DIR not in sys.path:
        sys.path.insert(0, CAMERA_EXPORT_DIR)
    import import_melee_camera as imc
    opts = imc.Options(scale=1.0 / mapping.s, offset=tuple(mapping.point((0.0, 0.0, 0.0))), frame_start=1,
                       name="CAM_Melee_Moving")
    return imc.import_file(path, opts, sc)


def render_sequence(sc, job):
    """Every frame of the moving camera (or the job's `frames` of them) as out/000001.png, out/000002.png...
    Frames already there are kept, so an interrupted render picks up where it stopped."""
    folder = Path(job["out"])
    folder.mkdir(parents=True, exist_ok=True)
    if job.get("frames"):
        sc.frame_start, sc.frame_end = (int(f) for f in job["frames"])
    r = sc.render
    r.filepath = str(folder / "######.png")
    r.use_overwrite = False
    r.use_placeholder = False
    r.image_settings.color_depth = "8"
    log(f"frames {sc.frame_start} to {sc.frame_end} -> {folder}")
    bpy.ops.render.render(animation=True)
    return [sc.frame_start, sc.frame_end]


def main():
    job = json.loads(Path(sys.argv[sys.argv.index("--") + 1]).read_text(encoding="utf-8"))
    sc = bpy.context.scene
    model = job.get("model")
    log("scene", sc.name, "model", model["path"] if model else LOGO, "style", job["style"], "->", job["out"])
    sc.frame_set(int(job.get("frame", 1)))

    fit, ground = job["fit"], job["ground"]
    if model:
        objects = load_model(sc, model)
        if model.get("rotation"):
            turn(objects, model["rotation"])
        lf = model_frame(objects, ground.get("line", "top"))
    else:
        objects = [sc.objects[LOGO]]
        lf = logo_frame(objects[0], fit.get("to", "bbox"), ground.get("line", "xheight"))
    s = fit["width"] * float(fit.get("scale", 1.0)) / (lf["x1"] - lf["x0"])
    cx = 0.5 * (lf["x0"] + lf["x1"])
    # y0: where Melee's z = 0 plane sits across the logo's depth (0 = the logo's middle, +1 = its front face)
    y_mid = 0.5 * (lf["y0"] + lf["y1"])
    y0 = y_mid + float(job.get("depth_shift", 0.0)) * 0.5 * (lf["y0"] - lf["y1"])
    zg = lf["ground"] - float(ground.get("offset", 0.0)) / s
    mapping = Mapping(s, fit["center_x"], ground.get("y", 0.0), cx, zg, y0)
    scale = int(job.get("scale", 1))
    size = job.get("size")
    # A model can be any size in Blender: clip where Melee does (0.1 and 16384 units), in its units.
    clip = (0.1 / s, 16384.0 / s) if model else (0.05, 400.0)
    cam_ob, mc = make_camera(sc, job["camera"], mapping, scale, size, clip)

    width_px, _ = mc.pixels_per_unit(fit["center_x"], ground.get("y", 0.0), 0.0, scale, size)
    px_per_m = width_px * s
    if job["style"] == "cel":
        outline_px = float(job.get("outline_px") or max(1.0, 0.6 * scale))
        materials = (build_cel_material(), build_ink_material())
        for ob in objects:
            apply_cel(as_mesh(ob), outline_px / px_per_m, materials)
    elif model and not any(o.type == "LIGHT" for o in sc.objects):
        add_light_rig(sc, mapping.point(mc.eye), mapping.point(mc.interest))
    configure_render(sc, job)
    if model and Path(model["path"]).suffix.lower() != ".blend":
        # an imported model's colours as authored, like the game's (a .blend keeps its own colour management)
        set_enum(sc.view_settings, "view_transform", ["Standard"])
        set_enum(sc.view_settings, "look", ["None"])
    env_tilt = None
    if not model and job["style"] == "metal" and job.get("tilt_studio", True):
        eye_b, spot = mapping.point(mc.eye), mapping.point((fit["center_x"], ground.get("y", 0.0), 0.0))
        elevation = math.degrees(math.atan2(eye_b.z - spot.z, abs(eye_b.y - spot.y)))
        env_tilt = elevation - REFERENCE_ELEVATION_DEG
        tilt_studio(sc, env_tilt, Vector((0.0, 0.5 * (lf["y0"] + lf["y1"]), 0.5 * (lf["top"] + lf["bottom"]))))

    report = dict(
        scale_melee_per_m=s, logo_width_m=lf["x1"] - lf["x0"], ground_z=zg, logo_top_z=lf["top"],
        logo_bottom_z=lf["bottom"], px_per_logo_m=px_per_m, size=[sc.render.resolution_x, sc.render.resolution_y],
        pixel_aspect=[sc.render.pixel_aspect_x, sc.render.pixel_aspect_y], islands=lf["islands"],
        lens_mm=cam_ob.data.lens, camera_logo_space=list(cam_ob.location), studio_tilt_deg=env_tilt,
        objects=[ob.name for ob in objects],
    )
    # Blender's own projection of the stage's anchor points, to compare with projection.py
    probes = {name: mapping.point(p) for name, p in job.get("probes", {}).items()}
    report["probes_blender_px"] = {name: list(world_to_pixel(sc, cam_ob, p)) for name, p in probes.items()}
    report["probes_melee_px"] = {name: list(mc.project(p, scale, size)) for name, p in job.get("probes", {}).items()}
    if job.get("camera_export"):
        report["moving_camera"] = import_moving_camera(sc, job["camera_export"], mapping)
        report["size"] = [sc.render.resolution_x, sc.render.resolution_y]
        if job.get("render", True):
            report["frames"] = render_sequence(sc, job)
    elif job.get("render", True):
        bpy.ops.render.render(write_still=True)
    print("PLATE_REPORT " + json.dumps(report))
    if job.get("report"):
        Path(job["report"]).write_text(json.dumps(report, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
