"""What the logo scene costs and animates, from inside Blender:

    blender -b --factory-startup PROJECT.blend -S SH010_Reveal --python scene_probe.py

Prints the EEVEE settings, the lights and their shadow settings, every animated or driven datablock, the objects'
modifiers, and the world's images.
"""
import bpy

sc = bpy.context.scene
ee = sc.eevee
print("PROBE engine", sc.render.engine, "frames", sc.frame_start, sc.frame_end, "fps", sc.render.fps)
for attr in sorted(dir(ee)):
    if attr.startswith(("shadow", "use_", "taa", "ray", "fast_gi", "volumetric", "gi_", "clamp", "horizon",
                        "light_threshold", "overscan")):
        try:
            v = getattr(ee, attr)
        except Exception:
            continue
        if isinstance(v, (int, float, bool, str)):
            print("PROBE eevee", attr, v)
rt = getattr(ee, "ray_tracing_options", None)
if rt:
    for attr in dir(rt):
        if not attr.startswith(("_", "bl_", "rna")):
            v = getattr(rt, attr)
            if isinstance(v, (int, float, bool, str)):
                print("PROBE raytracing", attr, v)
for ob in sc.objects:
    if ob.type == "LIGHT":
        d = ob.data
        print("PROBE light", ob.name, d.type, "energy", d.energy, "shadow", getattr(d, "use_shadow", None),
              "jitter", getattr(d, "use_shadow_jitter", None), "resolution_limit",
              getattr(d, "shadow_maximum_resolution", None), "soft", getattr(d, "shadow_soft_size", None),
              "hidden", ob.hide_render)
    mods = [f"{m.type}:{m.name}" for m in getattr(ob, "modifiers", [])]
    if mods:
        print("PROBE modifiers", ob.name, ob.type, "hidden" if ob.hide_render else "", mods)
for coll in ("objects", "materials", "node_groups", "worlds", "lights", "cameras", "meshes", "shape_keys"):
    for idb in getattr(bpy.data, coll):
        ad = getattr(idb, "animation_data", None)
        if ad and (ad.action or ad.drivers):
            act = ad.action
            rng = tuple(act.frame_range) if act else None
            print("PROBE animated", coll, idb.name, "action", act.name if act else None, "range", rng,
                  "drivers", len(ad.drivers))
        nt = getattr(idb, "node_tree", None)
        if nt is not None and nt.animation_data and (nt.animation_data.action or nt.animation_data.drivers):
            print("PROBE animated node_tree of", coll, idb.name)
for img in bpy.data.images:
    print("PROBE image", img.name, tuple(img.size), img.filepath)
print("PROBE compositing", getattr(sc, "use_nodes", None), getattr(sc, "compositing_node_group", None))
