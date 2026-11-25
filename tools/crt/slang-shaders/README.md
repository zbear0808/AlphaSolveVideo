# slang-shaders (vendored)

The files of [libretro/slang-shaders](https://github.com/libretro/slang-shaders) that our CRT presets need, at commit [`2345ee91`](https://github.com/libretro/slang-shaders/tree/2345ee91602a7404d3a1a6a5df6108d7305fdad4) (8 November 2026), unmodified and in their original folders, so the presets' relative paths work. 88 files, 1.4 MB:

- **crt-royale**, `crt/crt-royale.slangp` (38 files, 1069 KB): its 12 shader passes and everything they `#include` (`crt/shaders/crt-royale/src/`, `blurs/shaders/royale/`, `include/`), its six phosphor-mask textures (`crt/shaders/crt-royale/*.png`), and crt-royale's `LICENSE.TXT`, `README.TXT` and `THANKS.TXT`.
- **crt-guest-advanced**, `crt/crt-guest-advanced.slangp` (16 files, 150 KB): its 12 passes in `crt/shaders/guest/advanced/` and its 4 colour LUTs (`crt/shaders/guest/advanced/lut/*.png`). Also `crt/shaders/guest/advanced/README_old`, guest's guide to the parameters.
- **crt-guest-advanced-ntsc**, `crt/crt-guest-advanced-ntsc.slangp` (22 files, 181 KB, 9 of them shared with crt-guest-advanced): its 19 passes, from `crt/shaders/guest/advanced/`, `crt/shaders/guest/advanced/ntsc/` and two from `crt/shaders/guest/hd/` (`gaussian_horizontal.slang`, `bloom_horizontal.slang`), and the same 4 LUTs.
- **Sony Megatron v2**, `hdr/crt-sony-megatron-v2-default.slangp` (17 files, 80 KB): the preset it `#reference`s (`hdr/shaders/crt-sony-megatron-v2.slangp`), its 2 passes in `hdr/shaders/` and what they `#include` (`hdr/shaders/include/`). Also the SDR preset `hdr/crt-sony-megatron-v2-default-sdr.slangp` and 4 display presets in `hdr/sony_megatron_v2_presets/` (Sony PVM-2730, PVM-20L4, PVM-1910, Bang & Olufsen MX8000), which only set parameters.

`MANIFEST` lists every file with its git blob id: in a checkout of slang-shaders, `git ls-tree -r 2345ee91 -- PATH` shows the same id. `python3 tools/crt/vendor_shaders.py check` (also run by `test_crt.py`) checks that the files are all there and unchanged, and that nothing a preset references or includes is missing. `vendor_shaders.py copy CHECKOUT` copies them again, for example after moving to a newer commit.

`.gitattributes` keeps these files' bytes as they are on every platform (`-text`: no CRLF on Windows checkouts).

## Licences

- **crt-royale** (`crt/shaders/crt-royale/`, by TroggleMonkey, 2014): GNU GPL version 2 or any later version, in `crt/shaders/crt-royale/LICENSE.TXT` and each file's header. This repo is GPL version 3.
- **The blur and include files** (`blurs/shaders/royale/`, `include/*.h`, also by TroggleMonkey): the MIT licence, in each file's header.
- **`include/compat_macros.inc`**: a few `#define`s without a licence header, as in slang-shaders.
- **crt-guest-advanced** (`crt/shaders/guest/`, by guest(r), 2018-2025): GNU GPL version 2 or any later version, in each shader's header. Four files have no licence header: `stock.slang` (a pass-through) and `ntsc/ntsc-pass1.slang` ... `ntsc-pass3.slang` ("based on Themaister's NTSC shader").
- **Sony Megatron** (`hdr/`, by Major Pain The Cactus): no licence header in its files, and slang-shaders has no licence at its top level. Vendored with that note, as `include/compat_macros.inc` is. `hdr/shaders/include/hdr10.h` has two matrices marked "Converted from (Copyright (c) Microsoft Corporation - Licensed under the MIT License.)".
