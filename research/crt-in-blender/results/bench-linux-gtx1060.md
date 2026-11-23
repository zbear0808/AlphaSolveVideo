# CRT benchmark: pop-os linux

2026-11-22 22:02; 1500-1739 frames of `DishonestMuddyCoyote.slp`

| Input | Runtime | Format | Encoder | Frames | Seconds | Frames/s | CPU s/frame | MB | GPU MiB |
|---|---|---|---|---|---|---|---|---|---|
| fighters | blender | mov | prores,4444,yuva444p12le | 240/240 | 29.0 | 8.27 | 0.66 | 398 | 439 |
| fighters | wgpu | mov | prores,4444,yuva444p12le | 240/240 | 114.8 | 2.09 | 2.44 | 398 | 1526 |
| fighters | blender | mp4 + matte | h264,High 4:4:4 Predictive,yuv444p | 240/240 | 20.5 | 11.7 | 0.31 | 89 | 2423 |
| fighters | wgpu | mp4 + matte | h264,High 4:4:4 Predictive,yuv444p | 240/240 | 108.6 | 2.21 | 2.04 | 89 | 3515 |
| game | blender | mov | prores,4444,yuv444p12le | 240/240 | 41.6 | 5.76 | 1.06 | 2552 | 439 |
| game | wgpu | mov | prores,4444,yuv444p12le | 240/240 | 125.9 | 1.91 | 2.9 | 2552 | 1270 |
| game | blender | mp4 | h264,High 4:4:4 Predictive,yuv444p | 240/240 | 18.7 | 12.86 | 0.22 | 291 | 1698 |
| game | wgpu | mp4 | h264,High 4:4:4 Predictive,yuv444p | 240/240 | 107.1 | 2.24 | 1.97 | 293 | 2790 |

| Input | Frame | Mask | Against | Mean /255 | Max | Pixels differing % |
|---|---|---|---|---|---|---|
| fighters | 0 | grille | wgpu | 0.0 | 6 | 0.001 |
| fighters | 0 | shadow | wgpu | 0.0 | 6 | 0.001 |
| fighters | 0 | slot | wgpu | 0.0 | 11 | 0.001 |
| fighters | 120 | grille | wgpu | 0.0 | 6 | 0.001 |
| fighters | 120 | shadow | wgpu | 0.0 | 6 | 0.001 |
| fighters | 120 | slot | wgpu | 0.0 | 11 | 0.002 |
| fighters | 239 | grille | wgpu | 0.0 | 6 | 0.002 |
| fighters | 239 | shadow | wgpu | 0.0 | 6 | 0.002 |
| fighters | 239 | slot | wgpu | 0.0 | 7 | 0.003 |
| game | 0 | grille | wgpu | 0.0002 | 6 | 0.016 |
| game | 0 | shadow | wgpu | 0.0002 | 7 | 0.014 |
| game | 0 | slot | wgpu | 0.0002 | 11 | 0.017 |
| game | 120 | grille | wgpu | 0.0001 | 6 | 0.009 |
| game | 120 | shadow | wgpu | 0.0001 | 8 | 0.009 |
| game | 120 | slot | wgpu | 0.0001 | 11 | 0.01 |
| game | 239 | grille | wgpu | 0.0001 | 6 | 0.011 |
| game | 239 | shadow | wgpu | 0.0001 | 7 | 0.01 |
| game | 239 | slot | wgpu | 0.0002 | 13 | 0.012 |
