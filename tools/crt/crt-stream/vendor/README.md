# librashader's Metal and wgpu runtimes, patched

`librashader-runtime-mtl` and `librashader-runtime-wgpu` 0.12.1, as published on crates.io, with a small fix each. `../Cargo.toml` uses them in place of the published crates (`[patch.crates-io]`). Every other file is byte for byte as published (`.gitattributes` keeps their CRLF line endings), less cargo's `.cargo-ok` marker. Each change is marked `crt-stream patch` in the source.

**What was wrong.** When a pass's output feeds a pass with `mipmap_input = true`, its target must have mip levels. `OwnedTexture::scale` (Metal) and `OwnedImage::scale` (wgpu) see that the target has one level, and make it again, but with `self.max_miplevels` levels: one again. So:

- the target is made again on every frame, and its mip levels are never built;
- if the pass is also read as feedback, its previous frame is lost on every frame. That's crt-guest-advanced's afterglow: pass 2 (`AfterglowPass`, read as `AfterglowPassFeedback`) is followed by pass 3 with `mipmap_input3 = true`.

Through `crt-stream` with the published crates, a white-then-black clip through guest went from 222.4 to 0.0 on the first black frame, on Metal and on wgpu. With the fix it decays 35.7, 28.8, 22.6, …, as the crt-royale TouchDesigner project measured it with its patched `tools/lrs-seq` (`pipelines/guest_advanced/temporal_results.json`) [verified on an M1, 25 November].

The Vulkan, Direct3D 11 and 12 and OpenGL runtimes 0.12.1 don't have this bug: they size the levels from `mipmap` (`if mipmap { u32::MAX } else { 1 }`, or `calculate_miplevels()`).

**The changes.**

- `librashader-runtime-mtl-0.12.1/src/texture.rs`: `scale` makes the target with `if mipmap { u32::MAX } else { 1 }` levels (as `tools/lrs-seq`'s copy does; there the file also lost its CRLF line endings).
- `librashader-runtime-wgpu-0.12.1/src/texture.rs`: the same in `scale`. Then two things the bug had hidden, since no target ever had more than one level:
  - `generate_mipmaps` builds the levels the texture has (`self.levels`), not `max_miplevels`, which is now `u32::MAX`;
  - each target gets `target_view`, a view of level 0 alone, because wgpu draws only into one mip level.
- `librashader-runtime-wgpu-0.12.1/src/framebuffer.rs`: a pass draws into `target_view`.

**Licence.** librashader is MPL-2.0 or GPL-3.0-only, at your choice (each crate's `Cargo.toml`), by Ronny Chan and its contributors: https://github.com/SnowflakePowered/librashader. The changes here are under the same terms.
