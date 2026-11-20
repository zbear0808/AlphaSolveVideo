# slang-shaders (vendored)

The files of [libretro/slang-shaders](https://github.com/libretro/slang-shaders) that `crt/crt-royale.slangp` needs, at commit [`2345ee91`](https://github.com/libretro/slang-shaders/tree/2345ee91602a7404d3a1a6a5df6108d7305fdad4) (8 November 2026), unmodified and in their original folders, so the preset's relative paths work:

- the preset, `crt/crt-royale.slangp`;
- its 12 shader passes and everything they `#include` (`crt/shaders/crt-royale/src/`, `blurs/shaders/royale/`, `include/`);
- its six phosphor-mask textures (`crt/shaders/crt-royale/*.png`);
- crt-royale's `LICENSE.TXT`, `README.TXT` and `THANKS.TXT`.

`MANIFEST` lists every file with its git blob id: in a checkout of slang-shaders, `git ls-tree -r 2345ee91 -- PATH` shows the same id. `python3 tools/crt/vendor_shaders.py check` (also run by `test_crt.py`) checks that the files are all there and unchanged, and that nothing the preset includes is missing. `vendor_shaders.py copy CHECKOUT` copies them again, for example after moving to a newer commit.

`.gitattributes` keeps these files' bytes as they are on every platform (`-text`: no CRLF on Windows checkouts).

## Licences

- **crt-royale** (`crt/shaders/crt-royale/`, by TroggleMonkey, 2014): GNU GPL version 2 or any later version, in `crt/shaders/crt-royale/LICENSE.TXT` and each file's header. This repo is GPL version 3.
- **The blur and include files** (`blurs/shaders/royale/`, `include/*.h`, also by TroggleMonkey): the MIT licence, in each file's header.
- **`include/compat_macros.inc`**: a few `#define`s without a licence header, as in slang-shaders.
