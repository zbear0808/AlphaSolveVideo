# Camera export

Melee's camera on every frame of a render, and the tools to use it in Blender. How it works, what the file holds and what was checked: [`docs/camera-export.md`](../../docs/camera-export.md).

```sh
cd tools/slp2alpha
python3 -m slp2alpha render game.slp --characters-only --export-camera      # writes "camera - game (...).json"
cd ../..
blender -b --python tools/camera-export/import_melee_camera.py -- "camera - game (characters only, 60 fps).json" \
    --save game-camera.blend
```

Needs the headless Dolphin build with the camera patch (`tools/dolphin-build/build-mac-mainline.sh`; `render` says when the build is too old), and Blender 4.4 or later for the import (tested with 5.2.3).

| File | |
|---|---|
| `import_melee_camera.py` | the Blender importer: command line, Text Editor (Run Script adds File > Import > Melee Camera), or add-on |
| `validate_camera.py` | the checks: `check`, `static`, `track`, `blender`, `overlay`, `compare`, `readonly` |
| `blender_probe.py` | runs inside Blender for `validate_camera.py blender` |

```sh
python3 tools/camera-export/validate_camera.py check "camera - game (...).json"
python3 tools/camera-export/validate_camera.py static game.slp            # the fixed camera against the ISO
python3 tools/camera-export/validate_camera.py track game.slp             # which video frame each sample is (numpy)
python3 tools/camera-export/validate_camera.py blender "camera - game (...).json"
```
