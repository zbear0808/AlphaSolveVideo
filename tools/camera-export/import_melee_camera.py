"""Import a Melee camera export into Blender: an animated camera that sees the world the way the video does.

The export is `camera - NAME.json`, written by `slp2alpha render --export-camera` next to the transparent video.

    blender -b [scene.blend] --python tools/camera-export/import_melee_camera.py -- "camera - game.json" \
        [--scale 0.1] [--offset X Y Z] [--frame-start 1] [--no-shake] [--no-scene] [--linear] \
        [--background-video] [--save out.blend]

Or open this file in Blender's Text Editor and Run Script: that adds File > Import > Melee Camera (.json) and
opens the file browser. docs/camera-export.md describes the file and the conversion.

Melee's space is x right, y up, z towards the camera, in the replay's units. A point (X, Y, Z) lands at
offset + scale * (X, -Z, Y) in Blender, which is z up with the front view looking along +y.
"""

bl_info = {
    "name": "Melee Camera (AlphaSolveVideo)",
    "author": "AlphaSolveVideo",
    "version": (1, 0, 0),
    "blender": (4, 4, 0),
    "location": "File > Import > Melee Camera (.json)",
    "description": "Import the camera of a Slippi replay render (slp2alpha render --export-camera)",
    "category": "Import-Export",
}

import json
import math
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import bpy
from bpy.props import BoolProperty, FloatProperty, FloatVectorProperty, IntProperty, StringProperty
from bpy_extras.io_utils import ImportHelper
from mathutils import Matrix, Vector

FORMAT, VERSION = "alphasolve-camera", 1
SENSOR_MM = 36.0
CONSTANT, LINEAR = 0, 1  # Keyframe.interpolation, as foreach_set wants it
# Melee (x right, y up, z towards the camera) -> Blender (x right, y away from the camera, z up)
AXES = Matrix(((1.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0)))
DEFAULT_NAME = "Melee Camera"


@dataclass
class Options:
    scale: float = 1.0                    # Blender units per Melee unit
    offset: tuple = (0.0, 0.0, 0.0)       # where Melee's origin goes
    frame_start: int = 1                  # the Blender frame of the first sample
    shake: bool = True                    # False: subtract the screen shake
    set_scene: bool = True                # resolution, pixel aspect, fps, frame range, scene camera
    interpolation: int = CONSTANT
    background_video: bool = False        # show the transparent video behind the camera (viewport only)
    name: str = ""                        # default: "Melee Camera <replay>"


def load(path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("format") != FORMAT:
        raise ValueError(f"{Path(path).name} is not a Melee camera export (no \"format\": \"{FORMAT}\")")
    if data.get("version") != VERSION:
        raise ValueError(f"{Path(path).name} is camera export version {data.get('version')}; this importer reads "
                         f"version {VERSION}")
    samples = data.get("samples") or []
    if len(samples) != data.get("frames", {}).get("count"):
        raise ValueError(f"{Path(path).name}: {len(samples)} samples, but frames.count is "
                         f"{data.get('frames', {}).get('count')}")
    for key in ("render", "projection"):
        if key not in data:
            raise ValueError(f"{Path(path).name}: no \"{key}\"")
    return data


# ---------------------------------------------------------------- Melee -> Blender
def melee_point(p, opts: Options) -> Vector:
    return Vector(opts.offset) + opts.scale * (AXES @ Vector(p))


def roll_up(fwd: Vector, roll: float) -> Vector:
    """roll2upvec (cobj.c): world up made perpendicular to the view direction, turned by -roll about it."""
    e = fwd
    if 1.0 - abs(e.y) < 0.0001:
        x = math.sqrt(e.y * e.y + e.z * e.z)
        v0 = Vector((x, -e.y * e.x / x, -e.z * e.x / x))
    else:
        h = math.sqrt(e.x * e.x + e.z * e.z)
        v0 = Vector((-e.x * e.y / h, h, -e.z * e.y / h))
    if roll:
        v0 = Matrix.Rotation(-roll, 3, e) @ v0
    return v0.normalized()


def camera_matrix(eye, interest, roll: float = 0.0, up=None) -> Matrix:
    """The camera's rotation in Melee space, built like C_MTXLookAt: columns right, up, look (look points from
    the look-at point back to the eye). Blender cameras look along their -z with +y up, the same convention."""
    fwd = (Vector(interest) - Vector(eye)).normalized()
    hint = Vector(up).normalized() if up else roll_up(fwd, roll)
    look = -fwd
    right = hint.cross(look).normalized()
    return Matrix((right, look.cross(right), look)).transposed()


def lens_mm(fov_deg: float, aspect: float) -> float:
    """Focal length for a horizontal 36 mm sensor: the width spans tan(fov / 2) * aspect either side."""
    return (SENSOR_MM / 2) / (math.tan(math.radians(fov_deg) / 2) * aspect)


def blender_fps(text: str):
    """("60/1") -> (60, 1.0); ("60000/1001") -> (60, 1.001). Blender's fps is an integer up to 32767."""
    rate = Fraction(text)
    fps = max(1, round(rate))
    return fps, float(fps / rate)


def pixel_aspect(aspect: float, width: int, height: int):
    """The recording's pixels cover aspect * height / width times more world across than up."""
    ratio = aspect * height / width
    return (ratio, 1.0) if ratio >= 1.0 else (1.0, 1.0 / ratio)


# ---------------------------------------------------------------- animation (slotted actions, Blender 4.4+)
def channelbag(id_block):
    from bpy_extras import anim_utils

    ad = id_block.animation_data or id_block.animation_data_create()
    action = bpy.data.actions.new(f"{id_block.name} Action")
    slot = action.slots.new(id_type=id_block.id_type, name=id_block.name)
    ad.action = action
    ad.action_slot = slot
    return anim_utils.action_ensure_channelbag_for_slot(action, slot)


def key(bag, path: str, index: int, frames, values, interpolation: int) -> None:
    fc = bag.fcurves.new(path, index=index)
    fc.keyframe_points.add(len(frames))
    fc.keyframe_points.foreach_set("co", [c for fv in zip(frames, values) for c in fv])
    fc.keyframe_points.foreach_set("interpolation", [interpolation] * len(frames))
    fc.update()


def _remove_old(name: str) -> None:
    ob = bpy.data.objects.get(name)
    if ob is None:
        return
    data = ob.data
    for owner in (ob, data):
        ad = getattr(owner, "animation_data", None)
        if ad and ad.action and ad.action.users <= 1:
            bpy.data.actions.remove(ad.action)
    bpy.data.objects.remove(ob)
    if data is not None and data.users == 0 and isinstance(data, bpy.types.Camera):
        bpy.data.cameras.remove(data)


# ---------------------------------------------------------------- import
def build(scene, data: dict, opts: Options):
    samples = data["samples"]
    aspect = float(data["projection"]["aspect"])
    name = opts.name or f"{DEFAULT_NAME} {Path(data.get('replay', 'replay')).stem}"
    _remove_old(name)
    cam = bpy.data.cameras.new(name)
    ob = bpy.data.objects.new(name, cam)
    scene.collection.objects.link(ob)
    cam.sensor_fit = "HORIZONTAL"
    cam.sensor_width = SENSOR_MM
    cam.shift_x = cam.shift_y = 0.0
    cam.clip_start = max(1e-6, float(data["projection"]["near"]) * opts.scale)
    cam.clip_end = float(data["projection"]["far"]) * opts.scale
    cam.dof.use_dof = False
    ob.rotation_mode = "QUATERNION"

    frames = [opts.frame_start + i for i in range(len(samples))]
    rotation = AXES.to_quaternion()
    locs, quats, lenses = [], [], []
    prev = None
    for s in samples:
        eye, interest = list(s["eye"]), list(s["interest"])
        if not opts.shake:
            sx, sy = s.get("shake", (0.0, 0.0))
            eye[0] -= sx
            eye[1] -= sy
            interest[0] -= sx
            interest[1] -= sy
        q = rotation @ camera_matrix(eye, interest, s.get("roll", 0.0), s.get("up")).to_quaternion()
        if prev is not None and prev.dot(q) < 0:
            q.negate()  # the same rotation; keeps a later switch to linear interpolation from spinning
        prev = q
        locs.append(melee_point(eye, opts))
        quats.append(q)
        lenses.append(lens_mm(float(s["fov"]), aspect))

    # Values at the first frame, so the camera is right even before the animation is evaluated
    ob.location, ob.rotation_quaternion, cam.lens = locs[0], quats[0], lenses[0]
    ob["slippi_frame"] = int(samples[0]["frame"])
    ob["shake_x"], ob["shake_y"] = (float(v) for v in samples[0].get("shake", (0.0, 0.0)))
    ob["mode"] = int(samples[0].get("mode", 0))
    ob["replay"] = str(data.get("replay", ""))
    ob["stage"] = str(data.get("stage", {}).get("name", ""))
    ob["source"] = str(data.get("_path", ""))
    ob["units_per_melee_unit"] = float(opts.scale)

    bag = channelbag(ob)
    for i in range(3):
        key(bag, "location", i, frames, [v[i] for v in locs], opts.interpolation)
    for i in range(4):
        key(bag, "rotation_quaternion", i, frames, [q[i] for q in quats], opts.interpolation)
    key(bag, '["slippi_frame"]', 0, frames, [s["frame"] for s in samples], CONSTANT)
    key(bag, '["shake_x"]', 0, frames, [s.get("shake", (0.0, 0.0))[0] for s in samples], CONSTANT)
    key(bag, '["shake_y"]', 0, frames, [s.get("shake", (0.0, 0.0))[1] for s in samples], CONSTANT)
    key(bag, '["mode"]', 0, frames, [s.get("mode", 0) for s in samples], CONSTANT)
    cam_bag = channelbag(cam)
    key(cam_bag, "lens", 0, frames, lenses, opts.interpolation)
    if any("near" in s for s in samples):  # the stage changed near and far during the export
        near, far = float(data["projection"]["near"]), float(data["projection"]["far"])
        key(cam_bag, "clip_start", 0, frames, [max(1e-6, float(s.get("near", near)) * opts.scale) for s in samples],
            CONSTANT)
        key(cam_bag, "clip_end", 0, frames, [float(s.get("far", far)) * opts.scale for s in samples], CONSTANT)
    return ob


def setup_scene(scene, data: dict, ob, opts: Options) -> None:
    render = data["render"]
    width, height = int(render["width"]), int(render["height"])
    r = scene.render
    r.resolution_x, r.resolution_y, r.resolution_percentage = width, height, 100
    r.pixel_aspect_x, r.pixel_aspect_y = pixel_aspect(float(data["projection"]["aspect"]), width, height)
    r.fps, r.fps_base = blender_fps(str(render["fps"]))
    frames = max(int(data["frames"]["count"]), int(data["frames"].get("video") or 0))
    scene.frame_start = opts.frame_start
    scene.frame_end = opts.frame_start + frames - 1
    scene.camera = ob


def add_background(scene, ob, data: dict, json_path: Path, opts: Options):
    """The transparent video behind the camera in the viewport, to check the fit by eye."""
    video = Path(json_path).parent / data["render"]["transparent"]
    if not video.exists():
        return f"no background: {video.name} isn't next to the camera file"
    clip = bpy.data.movieclips.load(str(video), check_existing=True)
    clip.frame_start = opts.frame_start
    bg = ob.data.background_images.new()
    bg.source = "MOVIE_CLIP"
    bg.clip = clip
    bg.frame_method = "STRETCH"
    bg.alpha = 1.0
    ob.data.show_background_images = True
    return None


def import_file(path, opts: Options = None, scene=None) -> dict:
    """Import one camera export into `scene` (default: the current one). Returns a short report."""
    opts = opts or Options()
    scene = scene or bpy.context.scene
    path = Path(path).expanduser().resolve()
    data = load(path)
    data["_path"] = str(path)
    ob = build(scene, data, opts)
    notes = []
    if opts.set_scene:
        setup_scene(scene, data, ob, opts)
    if opts.background_video:
        note = add_background(scene, ob, data, path, opts)
        if note:
            notes.append(note)
    modes = sorted({int(s.get("mode", 0)) for s in data["samples"]})
    if any(m not in (0, 4) for m in modes):
        notes.append(f"camera modes {modes}: some frames aren't the normal or the fixed camera")
    count, video = int(data["frames"]["count"]), int(data["frames"].get("video") or 0)
    if video > count:
        notes.append(f"the video has {video} frames and the camera {count}: the last {video - count} hold the "
                     "last camera")
    return {"object": ob.name, "frames": [opts.frame_start, opts.frame_start + count - 1],
            "slippi_frames": [data["frames"]["first"], data["frames"]["last"]], "notes": notes}


# ---------------------------------------------------------------- the menu entry
class IMPORT_SCENE_OT_melee_camera(bpy.types.Operator, ImportHelper):
    """Import the camera of a Slippi replay render (slp2alpha render --export-camera)"""

    bl_idname = "import_scene.melee_camera"
    bl_label = "Import Melee Camera"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})
    scale: FloatProperty(name="Scale", description="Blender units per Melee unit", default=1.0, min=1e-6,
                         soft_max=10.0)
    offset: FloatVectorProperty(name="Offset", description="Where Melee's origin goes", size=3, default=(0, 0, 0))
    frame_start: IntProperty(name="Frame Start", description="Blender frame of the video's first frame", default=1)
    shake: BoolProperty(name="Screen Shake", description="Keep the screen shake, as in the video", default=True)
    set_scene: BoolProperty(name="Set Up Scene", default=True,
                            description="Resolution, pixel aspect, frame rate, frame range and scene camera")
    linear: BoolProperty(name="Linear Interpolation", default=False,
                         description="Interpolate between frames instead of holding each one")
    background_video: BoolProperty(name="Video as Background", default=False,
                                   description="Show the transparent video behind the camera (viewport only)")

    def execute(self, context):
        opts = Options(self.scale, tuple(self.offset), self.frame_start, self.shake, self.set_scene,
                       LINEAR if self.linear else CONSTANT, self.background_video)
        try:
            report = import_file(self.filepath, opts, context.scene)
        except (OSError, ValueError, KeyError) as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        for note in report["notes"]:
            self.report({"WARNING"}, note)
        self.report({"INFO"}, f"{report['object']}: frames {report['frames'][0]} to {report['frames'][1]}")
        return {"FINISHED"}


def menu_func_import(self, context):
    self.layout.operator(IMPORT_SCENE_OT_melee_camera.bl_idname, text="Melee Camera (.json)")


def register():
    bpy.utils.register_class(IMPORT_SCENE_OT_melee_camera)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.utils.unregister_class(IMPORT_SCENE_OT_melee_camera)


# ---------------------------------------------------------------- command line
def parse(argv):
    import argparse

    ap = argparse.ArgumentParser(prog="import_melee_camera.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("camera", help="camera - NAME.json")
    ap.add_argument("--scale", type=float, default=1.0, help="Blender units per Melee unit (default 1)")
    ap.add_argument("--offset", type=float, nargs=3, default=(0.0, 0.0, 0.0), metavar=("X", "Y", "Z"),
                    help="where Melee's origin goes, in Blender units")
    ap.add_argument("--frame-start", type=int, default=1, help="Blender frame of the video's first frame")
    ap.add_argument("--no-shake", action="store_true", help="subtract the screen shake")
    ap.add_argument("--no-scene", action="store_true", help="leave resolution, fps and frame range alone")
    ap.add_argument("--linear", action="store_true", help="interpolate between frames instead of holding them")
    ap.add_argument("--background-video", action="store_true", help="the transparent video behind the camera")
    ap.add_argument("--name", default="", help="camera object name (default: 'Melee Camera <replay>')")
    ap.add_argument("--save", help="save the .blend here")
    return ap.parse_args(argv)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not argv:  # run from the Text Editor: add the menu entry and ask for a file
        try:
            unregister()
        except (RuntimeError, ValueError):
            pass
        register()
        if not bpy.app.background:
            bpy.ops.import_scene.melee_camera("INVOKE_DEFAULT")
        return
    args = parse(argv)
    opts = Options(args.scale, tuple(args.offset), args.frame_start, not args.no_shake, not args.no_scene,
                   LINEAR if args.linear else CONSTANT, args.background_video, args.name)
    report = import_file(args.camera, opts)
    for note in report["notes"]:
        print(f"note: {note}")
    print(f"{report['object']}: Blender frames {report['frames'][0]} to {report['frames'][1]} "
          f"(Slippi frames {report['slippi_frames'][0]} to {report['slippi_frames'][1]})")
    print("MELEE_CAMERA_REPORT " + json.dumps(report))
    if args.save:
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(args.save).expanduser().resolve()))
        print(f"saved {args.save}")


if __name__ == "__main__":
    main()
