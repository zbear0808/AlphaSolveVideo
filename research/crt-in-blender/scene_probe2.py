"""Which of the logo scene's animated objects a plate render actually draws or lights with, and what they animate:

    blender -b --factory-startup PROJECT.blend -S SH010_Reveal --python scene_probe2.py
"""
import bpy

sc = bpy.context.scene
vl = bpy.context.view_layer
dg = bpy.context.evaluated_depsgraph_get()
in_depsgraph = {ob.original.name for ob in dg.objects}
visible = {ob.name for ob in vl.objects if ob.visible_get() or not ob.hide_render}
print("PROBE2 view layer objects", len(vl.objects), "in depsgraph", len(in_depsgraph))
renders, animated_rendered = 0, []
for ob in vl.objects:
    hidden = ob.hide_render or any(c.hide_render for c in ob.users_collection)
    ad = ob.animation_data
    if ad and ad.action:
        paths = sorted({fc.data_path for fc in getattr(ad.action, "fcurves", [])})
        if not paths:   # Blender 5's layered actions
            try:
                for layer in ad.action.layers:
                    for strip in layer.strips:
                        for bag in strip.channelbags:
                            paths += [fc.data_path for fc in bag.fcurves]
                paths = sorted(set(paths))
            except AttributeError:
                pass
        if not hidden and ob.name in in_depsgraph:
            animated_rendered.append((ob.name, ob.type, paths))
    if not hidden and ob.type in {"MESH", "CURVE", "FONT", "LIGHT"}:
        renders += 1
print("PROBE2 objects that render (mesh/curve/text/light):", renders)
for name, kind, paths in animated_rendered:
    print("PROBE2 animated and rendered:", name, kind, paths)
for ob in vl.objects:
    if ob.type == "LIGHT" and ob.data.animation_data and ob.data.animation_data.action:
        print("PROBE2 light data animated:", ob.name)
for f in (1, 30, 60, 90, 120, 150, 180, 240):
    sc.frame_set(f)
    hero = sc.objects.get("SM_Logo_Hero")
    sweep = sc.objects.get("LGT_Sweep_SH010")
    print("PROBE2 frame", f, "hero loc", tuple(round(v, 4) for v in hero.matrix_world.translation) if hero else None,
          "sweep energy", round(sweep.data.energy, 3) if sweep else None,
          "sweep loc", tuple(round(v, 3) for v in sweep.matrix_world.translation) if sweep else None)
