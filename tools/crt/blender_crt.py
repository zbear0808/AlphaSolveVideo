"""CRT Royale drawn by Blender's GPU module: librashader's filter chain rebuilt on `gpu.types`, for a whole video in
one process. Runs inside Blender, in the background; render_video.py --runtime blender starts it:

    blender -b --factory-startup -noaudio [--gpu-backend opengl] --python-exit-code 1 --python blender_crt.py -- \
        CHAIN LUTS IN_FD OUT_FD W H OUT_W OUT_H PARAMS

CHAIN is blender-chain/ (vendor_chain.py): each pass's GLSL as librashader-cli compiles it, and chain.json. LUTS is a
folder with the mask textures as raw RGBA and luts.json ({name: [width, height]}). IN_FD and OUT_FD are inherited
file descriptors: raw RGBA frames of W x H come in, raw RGBA frames of OUT_W x OUT_H go out, top row first both
ways, as ffmpeg's rawvideo has them. PARAMS are the shader's parameters (mask_type=0,mask_triad_size_desired=3,...).

On stderr: `CRT_READY backend; renderer; seconds` once the preset is compiled, `CRT_FRAMES n` after each frame, and
`CRT_DONE n seconds` at the end. Blender's own messages go to stdout and stderr too.

What follows librashader 0.12.1's runtime (librashader-runtime-gl's filter_chain/chain.rs, librashader-runtime's
scaling.rs and binding.rs):
  - each pass's Source is sampled with that pass's filter and wrap mode; an alias with its producing pass's; the
    Original with the first pass's;
  - each pass's output is its scale of the source, the viewport or the original, rounded; the last pass draws at
    the viewport's size, in 8 bits;
  - every pass uses the identity MVP, and the frame count is 0, as render_video.draw's librashader-cli runs have it;
  - an image's top row is at v = 0, as librashader uploads it, and the output is read back from v = 0.
Not done: mip levels (Blender's Python can't build them). crt-royale reads them only from its large mask textures
(mask_sample_mode 1, not the default) and for its last pass's input, which it samples at full size here.
Against librashader-cli on the same Mac (Metal) its frames are 0.003/255 apart on average, for every mask.
"""
import json
import os
import queue
import re
import sys
import threading
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


def texture(width, height, rgba: bytes, fmt="RGBA8"):
    flat = np.frombuffer(rgba, dtype=np.uint8).astype(np.float32) / 255.0
    return gpu.types.GPUTexture((width, height), format=fmt, data=gpu.types.Buffer("FLOAT", flat.size, flat))


class Chain:
    def __init__(self, folder: Path, luts: Path, params: dict, out_size):
        doc = json.loads((folder / "chain.json").read_text(encoding="utf-8"))
        self.metas, self.out_size = doc["passes"], tuple(out_size)
        self.params = dict(doc["params"], **params)
        self.passes = [Pass(m, (folder / f"p{m['id']}.vertex.glsl").read_text(encoding="utf-8"),
                            (folder / f"p{m['id']}.fragment.glsl").read_text(encoding="utf-8")) for m in self.metas]
        sizes = json.loads((luts / "luts.json").read_text(encoding="utf-8"))
        self.luts = {}
        for lut in doc["luts"]:
            w, h = sizes[lut["name"]]
            tex = texture(w, h, (luts / f"{lut['name']}.rgba").read_bytes())
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


def read_exactly(f, n):
    chunks, got = [], 0
    while got < n:
        chunk = f.read(n - got)
        if not chunk:
            break
        chunks.append(chunk)
        got += len(chunk)
    return b"".join(chunks)


def report(line):
    sys.stderr.write(line + "\n")
    sys.stderr.flush()


def main():
    a = sys.argv[sys.argv.index("--") + 1:]
    chain_dir, luts, in_fd, out_fd = Path(a[0]), Path(a[1]), int(a[2]), int(a[3])
    w, h, ow, oh, params = int(a[4]), int(a[5]), int(a[6]), int(a[7]), a[8]
    t0 = time.time()
    gpu.init()
    chain = Chain(chain_dir, luts, parse_params(params), (ow, oh))
    report(f"CRT_READY {gpu.platform.backend_type_get()}; {gpu.platform.renderer_get()}; {time.time() - t0:.2f}")
    frame_bytes = w * h * 4
    # The frame read back last is written while the next one draws: the encoder takes its time over each.
    out_q, failed = queue.Queue(maxsize=2), []
    fout = os.fdopen(out_fd, "wb", buffering=0)

    def writer():
        try:
            while True:
                item = out_q.get()
                if item is None:
                    return
                fout.write(item)
        except BaseException as e:   # the encoder stopped: the main loop sees it and stops too
            failed.append(e)
            while out_q.get() is not None:
                pass

    thread = threading.Thread(target=writer, daemon=True)
    thread.start()
    n = 0
    try:
        with os.fdopen(in_fd, "rb") as fin:
            while not failed:
                data = read_exactly(fin, frame_bytes)
                if len(data) < frame_bytes:
                    break
                _, fb = chain.draw(texture(w, h, data), 0)
                with fb.bind():
                    out_q.put(memoryview(fb.read_color(0, 0, ow, oh, 4, 0, "UBYTE")))
                n += 1
                report(f"CRT_FRAMES {n}")
    finally:
        out_q.put(None)
        thread.join()
        fout.close()
    if failed:
        raise RuntimeError(f"couldn't write frame {n}: {failed[0]}")
    report(f"CRT_DONE {n} {time.time() - t0:.1f}")


main()
