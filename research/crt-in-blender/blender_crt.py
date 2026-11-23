"""crt-royale drawn by Blender's GPU module: librashader's filter chain, pass by pass, with no librashader at run time.
Runs inside Blender, in the background (gpu.init()), on whatever backend Blender uses: Metal, OpenGL or Vulkan.

    blender -b --factory-startup [--gpu-backend opengl] --python blender_crt.py -- CHAIN IN W H OUT_W OUT_H PARAMS OUT \
        [--frames N] [--passes N]

CHAIN is prep_chain.py's folder. IN is raw RGBA frames of W x H, OUT gets raw RGBA frames of OUT_W x OUT_H (a file,
a named pipe to an encoding ffmpeg, or /dev/null), top row first both ways, as ffmpeg's rawvideo has them. PARAMS
are the shader parameters, as render_video.py passes them (mask_type=0,mask_triad_size_desired=3,...).

Rows go through unflipped. librashader puts an image's top row at texture coordinate v = 0 and reads the output
back from v = 0 first; Blender's GPU module does the same with a buffer's first row, whatever the backend. crt-royale
isn't symmetric top to bottom (its scanlines and mask start from the top edge), so flipping the frame on the way in
and back on the way out gives a different picture: 0.8-1.7/255 from librashader's, against 0.2-0.4 unflipped.
--passes N stops after the first N passes, the last of them drawn at OUT_W x OUT_H, as a preset cut to its first N
passes draws: to find the pass where two renderers part.

Prints one line: the compile time, frames per second, and each part's time per frame.

What follows librashader 0.12.1's runtime (librashader-runtime-gl's filter_chain/chain.rs, librashader-runtime's
scaling.rs): each pass's Source is sampled with that pass's own filter and wrap mode; an alias or the Original with
the producing pass's; each pass's output size is its scale of the source, viewport or original, rounded; the last
pass draws at the viewport's size; intermediate passes use the identity MVP. Not done: mip levels (Blender's Python
can't build them), which crt-royale reads only for its large mask textures (mask_sample_mode 1, not the default)
and for its last pass's input.
"""
import json
import re
import sys
import time
from pathlib import Path

import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader

TYPES = {"float": "FLOAT", "vec2": "VEC2", "vec3": "VEC3", "vec4": "VEC4", "mat4": "MAT4", "uint": "UINT", "int": "INT"}
SIZE = {"float": 4, "uint": 4, "int": 4, "vec2": 8, "vec3": 12, "vec4": 16, "mat4": 64}
FORMATS = {"R8G8B8A8Srgb": "SRGB8_A8", "R16G16B16A16Sfloat": "RGBA16F", "R8G8B8A8Unorm": "RGBA8", "Unknown": "RGBA8"}
WRAP = {"ClampToBorder": "CLAMP_TO_BORDER", "ClampToEdge": "EXTEND", "Repeat": "REPEAT",
        "MirroredRepeat": "MIRRORED_REPEAT"}
IDENTITY = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]
QUAD = (((-1, -1, 0, 1), (1, -1, 0, 1), (-1, 1, 0, 1), (1, 1, 0, 1)), ((0, 0), (1, 0), (0, 1), (1, 1)))


def fields(block):
    return [tuple(m.split()) for m in (x.strip().rstrip(";") for x in block.split("\n")) if m]


def split(src):
    """One transpiled stage: its uniform block, push constants, samplers, inputs, outputs, and the rest."""
    ubo = re.search(r"layout\(std140\) uniform \w+\s*\{(.*?)\}\s*(\w+);", src, re.S)
    push = re.search(r"struct (LIBRA_PUSH_\w+)\s*\{(.*?)\};\s*uniform \1 (\w+);", src, re.S)
    samplers = re.findall(r"^uniform sampler2D (\w+);", src, re.M)
    ins = re.findall(r"^(?:layout\(location = (\d+)\) )?in (\w+) (\w+);", src, re.M)
    outs = re.findall(r"^(?:layout\(location = (\d+)\) )?out (\w+) (\w+);", src, re.M)
    body = src
    for m in (ubo, push):
        if m:
            body = body.replace(m.group(0), "")
    skip = re.compile(r"^(#version|uniform sampler2D|(layout\(location = \d+\) )?(in|out) \w+ \w+;)")
    body = "\n".join(line for line in body.split("\n") if not skip.match(line))
    # Blender's GLSL-to-Metal translation can't copy a whole array (`vec3 a[9] = b;`, in crt-royale's last pass)
    body = re.sub(r"(\w+) (\w+)\[(\d+)\] = (\w+);", r"\1 \2[\3]; for (int _k = 0; _k < \3; _k++) { \2[_k] = \4[_k]; }",
                  body)
    for old, new in ((ubo and ubo.group(2), "ubo"), (push and push.group(3), "push")):
        if old:
            body = re.sub(rf"\b{old}\b", new, body)
    return fields(ubo.group(1)) if ubo else [], fields(push.group(2)) if push else [], samplers, ins, outs, body


class Block:
    """A std140 uniform block of scalars and vectors, largest first so that nothing needs padding."""

    def __init__(self, name, members):
        self.name = name
        self.members = sorted(dict.fromkeys(members), key=lambda m: -SIZE[m[0]])
        size = sum(SIZE[t] for t, _ in self.members)
        self.pad = ((-size) % 16) // 4
        self.floats = size // 4 + self.pad
        self.offsets, off = {}, 0
        for t, n in self.members:
            self.offsets[n] = (off // 4, SIZE[t] // 4, t)
            off += SIZE[t]

    def source(self):
        rows = [f"  {t} {n};" for t, n in self.members] + [f"  float _pad{i};" for i in range(self.pad)]
        return "struct %s {\n%s\n};\n" % (self.name, "\n".join(rows))

    def pack(self, values):
        data = np.zeros(self.floats, dtype=np.float32)
        for n, (o, k, t) in self.offsets.items():
            v = values[n]
            if t in ("uint", "int"):
                data[o:o + 1].view(np.uint32 if t == "uint" else np.int32)[0] = int(v)
            else:
                data[o:o + k] = v
        return gpu.types.GPUUniformBuf(gpu.types.Buffer("FLOAT", data.size, data))


class Pass:
    def __init__(self, meta, vsrc, fsrc):
        self.meta = meta
        vu, vp, vs, vin, vout, vbody = split(vsrc)
        fu, fp, fs, _, fout, fbody = split(fsrc)
        self.ubo = Block(f"LibraUbo{meta['id']}", vu + fu)
        self.push = Block(f"LibraPush{meta['id']}", vp + fp)
        self.samplers = list(dict.fromkeys(vs + fs))
        info = gpu.types.GPUShaderCreateInfo()
        info.typedef_source(self.ubo.source() + self.push.source())
        info.uniform_buf(0, self.ubo.name, "ubo")
        info.uniform_buf(1, self.push.name, "push")
        for slot, name in enumerate(self.samplers):
            info.sampler(slot, "FLOAT_2D", name)
        for loc, t, name in vin:
            info.vertex_in(int(loc or 0), TYPES[t], name)
        iface = gpu.types.GPUStageInterfaceInfo(f"libra_{meta['id']}")
        for _, t, name in vout:
            iface.smooth(TYPES[t], name)
        info.vertex_out(iface)
        for loc, t, name in fout:
            info.fragment_out(int(loc or 0), TYPES[t], name)
        info.vertex_source(vbody)
        info.fragment_source(fbody)
        self.shader = gpu.shader.create_from_info(info)
        self.batch = batch_for_shader(self.shader, "TRI_STRIP", {vin[0][2]: QUAD[0], vin[1][2]: QUAD[1]})


def scaled(scale, source, viewport, original):
    kind, f = scale
    if kind == "Absolute":
        return max(1, round(f))
    return max(1, round({"Input": source, "Viewport": viewport, "Original": original}[kind] * f))


def size_vec(w, h):
    return [float(w), float(h), 1.0 / w, 1.0 / h]


_COPY = None


def copy_into(tex, fb):
    global _COPY
    if _COPY is None:
        info = gpu.types.GPUShaderCreateInfo()
        info.sampler(0, "FLOAT_2D", "src")
        info.vertex_in(0, "VEC2", "pos")
        info.fragment_out(0, "VEC4", "col")
        info.vertex_source("void main() { gl_Position = vec4(pos, 0.0, 1.0); }")
        info.fragment_source("void main() { col = texelFetch(src, ivec2(gl_FragCoord.xy), 0); }")
        sh = gpu.shader.create_from_info(info)
        _COPY = sh, batch_for_shader(sh, "TRI_STRIP", {"pos": ((-1, -1), (1, -1), (-1, 1), (1, 1))})
    sh, batch = _COPY
    with fb.bind():
        sh.bind()
        sh.uniform_sampler("src", tex)
        batch.draw(sh)


class Chain:
    def __init__(self, folder: Path, params: dict, out_size, passes=None):
        doc = json.loads((folder / "chain.json").read_text())
        self.metas, self.out_size = doc["passes"][:passes], tuple(out_size)
        self.params = dict(doc["params"], **params)
        t = time.time()
        self.passes = [Pass(m, (folder / f"p{m['id']}.vertex.glsl").read_text(),
                            (folder / f"p{m['id']}.fragment.glsl").read_text()) for m in self.metas]
        self.compile_s = time.time() - t
        self.luts = {}
        for lut in doc["luts"]:
            w, h = lut["size"]
            raw = np.frombuffer((folder / f"{lut['name']}.rgba").read_bytes(), dtype=np.uint8).reshape(h, w, 4)
            flat = raw.astype(np.float32).ravel() / 255.0   # top row first, as librashader uploads images
            tex = gpu.types.GPUTexture((w, h), format="RGBA8", data=gpu.types.Buffer("FLOAT", flat.size, flat))
            tex.extend_mode(WRAP[lut["wrap"]])
            tex.filter_mode(lut["filter"] == "Linear")
            self.luts[lut["name"]] = tex
        self.key = None

    def ensure(self, src_size):
        if self.key == src_size:
            return
        sizes, source = [], src_size
        for m in self.metas:
            source = (scaled(m["scale_x"], source[0], self.out_size[0], src_size[0]),
                      scaled(m["scale_y"], source[1], self.out_size[1], src_size[1]))
            sizes.append(source)
        sizes[-1] = self.out_size
        self.targets = []
        for i, (m, s) in enumerate(zip(self.metas, sizes)):
            # the last pass draws into the output, plain 8-bit, whatever format the pass asks for
            fmt = "RGBA8" if i == len(self.metas) - 1 else FORMATS.get(m["format"], "RGBA8")
            tex = gpu.types.GPUTexture(s, format=fmt)
            self.targets.append((tex, gpu.types.GPUFrameBuffer(color_slots=(tex,))))
        self.copies, self.key = {}, src_size

    def sampled(self, tex, filt, wrap, key, used):
        """`tex` sampled with this filter and wrap mode. Blender keeps sampler state on the texture, so the same
        texture sampled two ways in one pass needs a copy for the second way."""
        want = (filt, wrap)
        if used.setdefault(id(tex), want) == want:
            tex.filter_mode(filt == "Linear")
            tex.extend_mode(WRAP[wrap])
            return tex
        if key not in self.copies:
            c = gpu.types.GPUTexture((tex.width, tex.height), format=tex.format)
            self.copies[key] = (c, gpu.types.GPUFrameBuffer(color_slots=(c,)))
        c, fb = self.copies[key]
        copy_into(tex, fb)
        c.filter_mode(filt == "Linear")
        c.extend_mode(WRAP[wrap])
        return c

    def draw(self, image, frame=0):
        src_size = (image.width, image.height)
        self.ensure(src_size)
        source, aliases = image, {}
        for i, (p, m) in enumerate(zip(self.passes, self.metas)):
            tex, fb = self.targets[i]
            values = dict(self.params, MVP=IDENTITY, SourceSize=size_vec(source.width, source.height),
                          OriginalSize=size_vec(*src_size), OutputSize=size_vec(tex.width, tex.height),
                          FinalViewportSize=size_vec(*self.out_size),
                          FrameCount=frame % m["frame_count_mod"] if m["frame_count_mod"] else frame)
            for name, j in aliases.items():
                values[f"{name}Size"] = size_vec(self.targets[j][0].width, self.targets[j][0].height)
            used, binds = {}, {}
            for name in p.samplers:
                key = name[len("LIBRA_TEXTURE_"):]
                if key == "Source":
                    binds[name] = self.sampled(source, m["filter"], m["wrap"], ("Source", i), used)
                elif key == "Original":
                    first = self.metas[0]
                    binds[name] = self.sampled(image, first["filter"], first["wrap"], ("Original", i), used)
                elif key in aliases:
                    j = aliases[key]
                    binds[name] = self.sampled(self.targets[j][0], self.metas[j]["filter"], self.metas[j]["wrap"],
                                               (key, i), used)
                elif key in self.luts:
                    binds[name] = self.luts[key]
                else:
                    raise KeyError(f"pass {i}: nothing to bind to {name}")
            ubo, push = p.ubo.pack(values), p.push.pack(values)
            with fb.bind():
                gpu.state.blend_set("NONE")
                p.shader.bind()
                p.shader.uniform_block("ubo", ubo)
                p.shader.uniform_block("push", push)
                for name, t in binds.items():
                    p.shader.uniform_sampler(name, t)
                p.batch.draw(p.shader)
            if m["alias"]:
                aliases[m["alias"]] = i
            source = tex
        return self.targets[-1]


def parse_params(text):
    return {k.strip(): float(v) for k, v in (kv.split("=") for kv in text.split(",") if kv)}


def main():
    a = sys.argv[sys.argv.index("--") + 1:]
    limit = int(a[a.index("--frames") + 1]) if "--frames" in a else None
    passes = int(a[a.index("--passes") + 1]) if "--passes" in a else None
    a = [x for i, x in enumerate(a) if not x.startswith("--") and (i == 0 or a[i - 1] not in ("--frames", "--passes"))]
    folder, src, w, h, ow, oh, params, out = Path(a[0]), a[1], int(a[2]), int(a[3]), int(a[4]), int(a[5]), a[6], a[7]
    t0 = time.time()
    gpu.init()
    chain = Chain(folder, parse_params(params), (ow, oh), passes)
    setup = time.time() - t0
    n, t_draw, t_read, t_write = 0, 0.0, 0.0, 0.0
    t_start = time.time()
    with open(src, "rb") as fin, open(out, "wb", buffering=0) as fout:
        while limit is None or n < limit:
            data = fin.read(w * h * 4)
            if len(data) < w * h * 4:
                break
            t = time.time()
            flat = np.frombuffer(data, dtype=np.uint8).astype(np.float32) / 255.0
            image = gpu.types.GPUTexture((w, h), format="RGBA8", data=gpu.types.Buffer("FLOAT", flat.size, flat))
            _, fb = chain.draw(image, n)
            t1 = time.time()
            with fb.bind():
                px = fb.read_color(0, 0, ow, oh, 4, 0, "UBYTE")
            frame = memoryview(px)
            t2 = time.time()
            fout.write(frame)
            t_draw, t_read, t_write = t_draw + t1 - t, t_read + t2 - t1, t_write + time.time() - t2
            n += 1
    dt = time.time() - t_start
    print(f"BLENDER_CRT {gpu.platform.backend_type_get()} {gpu.platform.renderer_get()}: setup {setup:.2f} s "
          f"(compiling {chain.compile_s:.2f} s); {n} frames in {dt:.1f} s, {n / max(dt, 1e-9):.1f} frames/s; per frame: "
          f"upload and draw {t_draw / max(n, 1) * 1000:.0f} ms, read-back {t_read / max(n, 1) * 1000:.0f} ms, "
          f"writing {t_write / max(n, 1) * 1000:.0f} ms", file=sys.stderr, flush=True)


main()
