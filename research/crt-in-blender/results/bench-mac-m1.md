# CRT benchmark: zubairs-Mac-mini.local darwin

2026-11-22 19:01; 1500-1739 frames of `DishonestMuddyCoyote.slp`

| Input | Runtime | Format | Encoder | Frames | Seconds | Frames/s | CPU s/frame | MB | GPU MiB |
|---|---|---|---|---|---|---|---|---|---|
| fighters | blender | mov | prores,4444,yuva444p12le | 240/240 | 12.5 | 19.18 | 0.12 | 500 | - |
| fighters | metal | mov | prores,4444,yuva444p12le | 240/240 | 47.6 | 5.05 | 0.73 | 500 | - |
| fighters | blender | mp4 + matte | h264,High 4:4:4 Predictive,yuv444p | 240/240 | 43.2 | 5.55 | 0.67 | 36 | - |
| fighters | metal | mp4 + matte | h264,High 4:4:4 Predictive,yuv444p | 240/240 | 222.4 | 1.08 | 1.7 | 36 | - |
| game | blender | mov | prores,4444,yuva444p12le | 240/240 | 60.8 | 3.95 | 0.13 | 1588 | - |
| game | metal | mov | prores,4444,yuva444p12le | 240/240 | 265.7 | 0.9 | 1.18 | 1588 | - |
| game | blender | mp4 | h264,High 4:4:4 Predictive,yuv444p | 240/240 | 198.7 | 1.21 | 1.13 | 101 | - |
| game | metal | mp4 | h264,High 4:4:4 Predictive,yuv444p | 240/240 | 297.8 | 0.81 | 2.16 | 101 | - |

| Input | Frame | Mask | Against | Mean /255 | Max | Pixels differing % |
|---|---|---|---|---|---|---|
| fighters | 0 | grille | metal | 0.0 | 6 | 0.001 |
| fighters | 0 | shadow | metal | 0.0 | 9 | 0.001 |
| fighters | 0 | slot | metal | 0.0 | 9 | 0.001 |
| fighters | 120 | grille | metal | 0.0 | 7 | 0.001 |
| fighters | 120 | shadow | metal | 0.0 | 11 | 0.001 |
| fighters | 120 | slot | metal | 0.0 | 11 | 0.001 |
| fighters | 239 | grille | metal | 0.002 | 31 | 0.112 |
| fighters | 239 | shadow | metal | 0.0023 | 41 | 0.109 |
| fighters | 239 | slot | metal | 0.002 | 31 | 0.112 |
| game | 0 | grille | metal | 0.0043 | 9 | 0.264 |
| game | 0 | shadow | metal | 0.0045 | 20 | 0.259 |
| game | 0 | slot | metal | 0.0044 | 11 | 0.265 |
| game | 120 | grille | metal | 0.0003 | 16 | 0.023 |
| game | 120 | shadow | metal | 0.0003 | 9 | 0.024 |
| game | 120 | slot | metal | 0.0003 | 11 | 0.023 |
| game | 239 | grille | metal | 0.0027 | 31 | 0.172 |
| game | 239 | shadow | metal | 0.003 | 39 | 0.17 |
| game | 239 | slot | metal | 0.0027 | 31 | 0.173 |
