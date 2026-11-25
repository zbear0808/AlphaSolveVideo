"""A CRT shader preset drawn by Blender's GPU module: librashader's filter chain rebuilt on `gpu.types`, for a whole
video in one process. Runs inside Blender, in the background; render_video.py --runtime blender starts it:

    blender -b --factory-startup -noaudio [--gpu-backend opengl] --python-exit-code 1 --python blender_crt.py -- \
        CHAIN LUTS IN_FD OUT_FD W H OUT_W OUT_H PARAMS [--warmup N]

CHAIN is one of blender-chain/<shader>/ (vendor_chain.py): each pass's GLSL as librashader-cli compiles it, and
chain.json. LUTS is a folder with the mask textures as raw RGBA and luts.json ({name: [width, height]}). IN_FD and
OUT_FD are inherited file descriptors: raw RGBA frames of W x H come in, raw RGBA frames of OUT_W x OUT_H go out, top
row first both ways, as ffmpeg's rawvideo has them. PARAMS are the shader's parameters (mask_type=0,...). --warmup N
draws the first frame N extra times before it, as frames 0 to N - 1, so the state across frames starts settled.

On stderr: `CRT_READY backend; renderer; seconds` once the preset is compiled, `CRT_FRAMES n` after each frame, and
`CRT_DONE n seconds` at the end. Blender's own messages go to stdout and stderr too.

What follows librashader 0.12.1's runtime (librashader-runtime-mtl's filter_chain.rs, librashader-runtime's
scaling.rs and binding.rs):
  - each pass's Source is sampled with that pass's filter and wrap mode; an alias, PassOutputN, or a feedback with
    its producing pass's; the Original and OriginalHistory0 (which binding.rs binds to the Original) with the first
    pass's;
  - each pass's output is its scale of the source, the viewport or the original, rounded, in its format
    (R16G16B16A16Sfloat as RGBA16F); the last pass draws at the viewport's size into the host's 8-bit target;
  - frame n of the video (after the warm-up) is drawn with FrameCount = N + n, modulo the pass's frame_count_mod;
  - a pass read as <alias>Feedback (guest's afterglow and average luminance) has two targets, swapped before each
    frame: it reads its output of the frame before, black (zero) on the first frame;
  - the host's other values are librashader-cli's defaults (HOST): FrameDirection 1, OriginalFPS 1, HDRMode 0 (SDR),
    BrightnessNits 200, ...; a scalar that nothing declares as a parameter is 0;
  - every pass uses the identity MVP; an image's top row is at v = 0, as librashader uploads it, and the output is
    read back from v = 0.
split() rewrites what Blender's GLSL-to-Metal translation can't compile, the same way for OpenGL:
  - a whole-array copy in a declaration (`vec3 a[9] = b;`, crt-royale's last pass) or an assignment
    (`a = b;`, guest-ntsc's ntsc-pass2) as a loop over the elements;
  - a local array initialised by a constructor (`float a[33] = float[](...);`, ntsc-pass2) as its declaration and one
    assignment per element. Making it const doesn't work: the pass assigns to it later;
  - constant arrays of arrays (Megatron's mask tables, `const uint t[3][4][3] = uint[][][](...)`) as flat arrays,
    each use `t[a][b][c]` as `t[((int(a)) * 4 + int(b)) * 3 + int(c)]`, and without the #extension line;
  - each constant array (`const float k[15] = float[](...)`) as a function with a switch, each `k[i]` as
    `k(int(i))`. This one is for speed: Blender's Metal backend makes the shader's global constants members of a
    class that every pixel builds, and Megatron's last pass took 280 ms a 3504x2880 frame on the Mac instead of 32.
crt-royale's source comes out of them as before, so its frames are byte for byte the same.
Not done: mip levels (Blender's Python can't build them; librashader builds them for a pass whose next pass has
mipmap_input). crt-royale reads them only from its large mask textures (mask_sample_mode 1, not the default) and for
its last pass's input, which it samples at full size here. guest reads them only in avg-lum.slang's textureLod, for
the average luminance in the alpha channel, which only moves the picture through raster bloom (BLOOM, 0 by default).
Against librashader-cli on the same Mac (Metal) frames are 0.003/255 apart on average for crt-royale, and within
0.001/255 for guest, guest-ntsc and Megatron, on every look tried.
"""
import json
import math
import os
import queue
import re
import sys
import threading
import time
from pathlib import Path

try:
    import gpu
    import numpy as np
    from gpu_extras.batch import batch_for_shader
except ImportError:   # outside Blender: test_crt.py tests the GLSL rewrites
    gpu = np = batch_for_shader = None

TYPES = {"float": "FLOAT", "vec2": "VEC2", "vec3": "VEC3", "vec4": "VEC4", "mat4": "MAT4", "uint": "UINT", "int": "INT"}
SIZE = {"float": 4, "uint": 4, "int": 4, "vec2": 8, "vec3": 12, "vec4": 16, "mat4": 64}
FORMATS = {"R8G8B8A8Srgb": "SRGB8_A8", "R16G16B16A16Sfloat": "RGBA16F", "R8G8B8A8Unorm": "RGBA8", "Unknown": "RGBA8"}
WRAP = {"ClampToBorder": "CLAMP_TO_BORDER", "ClampToEdge": "EXTEND", "Repeat": "REPEAT",
        "MirroredRepeat": "MIRRORED_REPEAT"}
IDENTITY = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]
# What librashader-cli 0.12.1 binds for the host's semantics by default (librashader-runtime's binding.rs, FrameOptions)
HOST = dict(FrameDirection=1, Rotation=0, TotalSubFrames=1, CurrentSubFrame=1, OriginalFPS=1.0, FrameTimeDelta=0,
            HDRMode=0, BrightnessNits=200.0, ExpandGamut=0, Scanlines=0.0, InverseTonemap=0.0, HDR10=0.0,
            SubpixelLayout=0)
QUAD = (((-1, -1, 0, 1), (1, -1, 0, 1), (-1, 1, 0, 1), (1, 1, 0, 1)), ((0, 0), (1, 0), (0, 1), (1, 1)))


def fields(block):
    return [tuple(m.split()) for m in (x.strip().rstrip(";") for x in block.split("\n")) if m]


def closing(text, i):
    """The index just past the bracket that closes the one at text[i]."""
    want = []
    for j in range(i, len(text)):
        c = text[j]
        if c in "([{":
            want.append(")]}"["([{".index(c)])
        elif c in ")]}":
            if not want or want.pop() != c:
                break
            if not want:
                return j + 1
    raise ValueError(f"unbalanced {text[i]!r} at {i}: {text[i:i + 60]!r}")


def arguments(text):
    """The comma-separated items of `text`, outside any brackets."""
    items, depth, start = [], 0, 0
    for j, c in enumerate(text):
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            items.append(text[start:j].strip())
            start = j + 1
    return items + [text[start:].strip()]


CONSTRUCTOR = re.compile(r"\w+(?:\[\d*\])+\(")


def leaves(expr):
    """The elements of a (nested) array constructor `T[][](T[](a, b), ...)`, in order."""
    m = CONSTRUCTOR.match(expr)
    if not m or closing(expr, m.end() - 1) != len(expr):
        return [expr]
    return [x for item in arguments(expr[m.end():-1]) for x in leaves(item)]


def flat_indices(text, dims):
    """`a[i][j][k]` for each array `a` of `dims` (name -> its sizes) as `a[((int(i)) * J + int(j)) * K + int(k)]`."""
    if not dims:
        return text
    use = re.compile(r"\b(%s)\s*\[" % "|".join(map(re.escape, dims)))
    out, pos = [], 0
    while True:
        m = use.search(text, pos)
        if not m:
            return "".join(out) + text[pos:]
        name, j, index = m.group(1), m.end() - 1, []
        for _ in dims[name]:
            while text[j].isspace():
                j += 1
            if text[j] != "[":
                raise ValueError(f"{name} has {len(dims[name])} dimensions but is indexed with {len(index)}")
            end = closing(text, j)
            index.append(flat_indices(text[j + 1:end - 1], dims))
            j = end
        flat = f"int({index[0]})"
        for size, i in zip(dims[name][1:], index[1:]):
            flat = f"({flat}) * {size} + int({i})"
        out.append(f"{text[pos:m.start()]}{name}[{flat}]")
        pos = j


NESTED_ARRAY = re.compile(r"^const (\w+) (\w+)((?:\[\d+\]){2,}) = ", re.M)


def flatten_nested_arrays(body):
    """Constant arrays of arrays as one-dimensional arrays, and every use of them indexed to match."""
    dims, decls, out, pos = {}, [], [], 0
    for m in NESTED_ARRAY.finditer(body):
        t, name, sizes = m.group(1), m.group(2), [int(s) for s in re.findall(r"\d+", m.group(3))]
        ctor = CONSTRUCTOR.match(body, m.end())
        end = closing(body, ctor.end() - 1)
        items = leaves(body[m.end():end])
        if body[end] != ";" or len(items) != math.prod(sizes):
            raise ValueError(f"can't flatten {name}: {len(items)} elements for {sizes}")
        dims[name] = sizes
        decls.append(f"const {t} {name}[{len(items)}] = {t}[]({', '.join(items)});")
        out.append(f"{body[pos:m.start()]}@FLAT{len(decls) - 1}@")
        pos = end + 1
    body = flat_indices("".join(out) + body[pos:], dims)
    return re.sub(r"@FLAT(\d+)@", lambda m: decls[int(m.group(1))], body)


LOCAL_ARRAY = re.compile(r"^([ \t]+)(\w+) (\w+)\[(\d+)\] = \2\[\]\(", re.M)


def unroll_local_arrays(body):
    """`T a[N] = T[](x0, x1, ...);` inside a function as `T a[N]; a[0] = x0; a[1] = x1; ...`."""
    out, pos = [], 0
    for m in LOCAL_ARRAY.finditer(body):
        indent, t, name, n = m.groups()
        end = closing(body, m.end() - 1)
        items = arguments(body[m.end():end - 1])
        if body[end] != ";" or len(items) != int(n):
            raise ValueError(f"can't unroll {name}: {len(items)} elements for {n}")
        out.append(f"{body[pos:m.start()]}{indent}{t} {name}[{n}];"
                   + "".join(f" {name}[{k}] = {x};" for k, x in enumerate(items)))
        pos = end + 1
    return "".join(out) + body[pos:]


def copy_arrays(body):
    """`a = b;` for two arrays as a loop over their elements."""
    sizes = dict(re.findall(r"\b(?:float|u?int|bool|[iub]?vec[234]|mat[234]) (\w+)\[(\d+)\]", body))
    def loop(m):
        indent, a, b = m.groups()
        if a not in sizes or sizes.get(b) != sizes[a]:
            return m.group(0)
        return f"{indent}for (int _k = 0; _k < {sizes[a]}; _k++) {{ {a}[_k] = {b}[_k]; }}"
    return re.sub(r"^([ \t]+)(\w+) = (\w+);$", loop, body, flags=re.M)


CONSTANT_ARRAY = re.compile(r"^const (\w+) (\w+)\[(\d+)\] = \1\[\]\(", re.M)


def calls(text, names):
    """Each `a[i]` of an array in `names` as `a(int(i))`."""
    if not names:
        return text
    use, out, pos = re.compile(r"\b(%s)\s*\[" % "|".join(map(re.escape, names))), [], 0
    while True:
        m = use.search(text, pos)
        if not m:
            return "".join(out) + text[pos:]
        end = closing(text, m.end() - 1)
        out.append(f"{text[pos:m.start()]}{m.group(1)}(int({calls(text[m.end():end - 1], names)}))")
        pos = end


def constant_tables(body):
    """`const T a[N] = T[](x0, ...);` as a function `T a(int i)` with a switch, each `a[i]` as `a(int(i))`."""
    tables = []
    for m in CONSTANT_ARRAY.finditer(body):
        end = closing(body, m.end() - 1)
        items = arguments(body[m.end():end - 1])
        if body[end] != ";" or len(items) != int(m.group(3)):
            raise ValueError(f"can't read {m.group(2)}: {len(items)} elements for {m.group(3)}")
        tables.append((m.start(), end + 1, m.group(1), m.group(2), items))
    rest = "".join(body[s:e] for s, e in zip([0] + [t[1] for t in tables], [t[0] for t in tables] + [len(body)]))
    # an array used as a whole somewhere stays as it is
    names = [t[3] for t in tables if re.findall(rf"\b{t[3]}\b\s*(.?)", rest).count("[") ==
             len(re.findall(rf"\b{t[3]}\b", rest))]
    out, pos = [], 0
    for start, end, t, name, items in tables:
        if name in names:
            cases = " ".join(f"case {k}: return {x};" for k, x in enumerate(items[:-1]))
            out.append(f"{body[pos:start]}{t} {name}(int i) {{ switch (i) {{ {cases} default: return {items[-1]}; }} }}")
        else:
            out.append(body[pos:end])
        pos = end
    return calls("".join(out) + body[pos:], names)


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
    skip = re.compile(r"^(#version|#extension GL_ARB_arrays_of_arrays|uniform sampler2D|"
                      r"(layout\(location = \d+\) )?(in|out) \w+ \w+;)")
    body = "\n".join(line for line in body.split("\n") if not skip.match(line))
    body = flatten_nested_arrays(body)
    # Blender's GLSL-to-Metal translation can't copy a whole array (`vec3 a[9] = b;`, in crt-royale's last pass)
    body = re.sub(r"(\w+) (\w+)\[(\d+)\] = (\w+);", r"\1 \2[\3]; for (int _k = 0; _k < \3; _k++) { \2[_k] = \4[_k]; }",
                  body)
    body = constant_tables(copy_arrays(unroll_local_arrays(body)))
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
            v = values.get(n, 0) if k == 1 else values[n]   # a scalar no parameter declares is 0, as in librashader
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
        # librashader reports an empty alias as the two characters ""
        self.alias = [m["alias"] if m["alias"] not in (None, "", '""') else None for m in self.metas]
        read = {name[len("LIBRA_TEXTURE_"):] for p in self.passes for name in p.samplers}
        self.feedback = {j for j, a in enumerate(self.alias) if f"{a}Feedback" in read or f"PassFeedback{j}" in read}
        sizes = json.loads((luts / "luts.json").read_text(encoding="utf-8"))
        self.luts = {}
        for lut in doc["luts"]:
            w, h = sizes[lut["name"]]
            tex = texture(w, h, (luts / f"{lut['name']}.rgba").read_bytes())
            tex.extend_mode(WRAP[lut["wrap"]])
            tex.filter_mode(lut["filter"] == "Linear")
            self.luts[lut["name"]] = tex
        self.key = None

    def target(self, size, fmt, clear=False):
        tex = gpu.types.GPUTexture(size, format=fmt)
        fb = gpu.types.GPUFrameBuffer(color_slots=(tex,))
        if clear:
            with fb.bind():
                fb.clear(color=(0.0, 0.0, 0.0, 0.0))
        return tex, fb

    def ensure(self, src_size):
        if self.key == src_size:
            return
        sizes, source = [], src_size
        for m in self.metas:
            source = (scaled(m["scale_x"], source[0], self.out_size[0], src_size[0]),
                      scaled(m["scale_y"], source[1], self.out_size[1], src_size[1]))
            sizes.append(source)
        sizes[-1] = self.out_size
        self.targets, self.previous = [], {}
        for i, (m, s) in enumerate(zip(self.metas, sizes)):
            # the last pass draws into the host's 8-bit target, whatever its own format
            fmt = "RGBA8" if i == len(self.metas) - 1 else FORMATS.get(m["format"], "RGBA8")
            self.targets.append(self.target(s, fmt, clear=i in self.feedback))
            if i in self.feedback:
                self.previous[i] = self.target(s, fmt, clear=True)
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
        # as librashader does before each frame: a feedback pass draws over its older output, and reads the last
        for j, old in self.previous.items():
            self.previous[j], self.targets[j] = self.targets[j], old
        first = self.metas[0]
        inputs = {"Original": (image, first), "OriginalHistory0": (image, first)}   # binding.rs: history 0 = Original
        for j, (tex, _) in self.previous.items():
            inputs[f"PassFeedback{j}"] = (tex, self.metas[j])
            if self.alias[j]:
                inputs[f"{self.alias[j]}Feedback"] = (tex, self.metas[j])
        host = dict(HOST, MVP=IDENTITY, OriginalSize=size_vec(*src_size), FinalViewportSize=size_vec(*self.out_size),
                    OriginalAspect=src_size[0] / src_size[1], OriginalAspectRotated=src_size[0] / src_size[1])
        source = image
        for i, (p, m) in enumerate(zip(self.passes, self.metas)):
            tex, fb = self.targets[i]
            values = dict(self.params, **host, SourceSize=size_vec(source.width, source.height),
                          OutputSize=size_vec(tex.width, tex.height),
                          FrameCount=frame % m["frame_count_mod"] if m["frame_count_mod"] else frame)
            for name, (t, _) in inputs.items():
                values[f"{name}Size"] = size_vec(t.width, t.height)
            for name, t in self.luts.items():
                values[f"{name}Size"] = size_vec(t.width, t.height)
            used, binds = {}, {}
            for name in p.samplers:
                key = name[len("LIBRA_TEXTURE_"):]
                if key == "Source":
                    binds[name] = self.sampled(source, m["filter"], m["wrap"], ("Source", i), used)
                elif key in inputs:
                    t, by = inputs[key]
                    binds[name] = self.sampled(t, by["filter"], by["wrap"], (key, i), used)
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
            inputs[f"PassOutput{i}"] = (tex, m)
            if self.alias[i]:
                inputs[self.alias[i]] = (tex, m)
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
    warmup = int(a[a.index("--warmup") + 1]) if "--warmup" in a[9:] else 0
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
                image = texture(w, h, data)
                if n == 0:
                    for k in range(warmup):
                        chain.draw(image, k)
                _, fb = chain.draw(image, warmup + n)
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


if __name__ == "__main__":
    main()
