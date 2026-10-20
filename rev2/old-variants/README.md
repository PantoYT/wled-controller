# Dropped rev 2.0 layouts

Drawn with `../gen_board.py` and `../route.py` before `wall` was chosen. Not to be ordered.

| `--size` | Board | Channels | GPIO, CH1 first | Why dropped |
|---|---|---|---|---|
| `phi` | 100 × 61.8 mm | 6, screw terminal + JST-XH each | 4, 18, 19, 21, 22, 23 | XH sockets need SM-to-XH leads made by hand; jack faces the left edge, where the wall mount's rail goes |
| `phi4` | 100 × 61.8 mm | 4, status LEDs, gold logo | 4, 18, 19, 21 | too few channels, LEDs and gold art not wanted |
| `120` | 120 × 74.16 mm | 8 | 4, 32, 33, 25, 26, 27, 14, 13 | too big, past JLC's 100 × 100 mm price bracket |
| `100` | 100 × 100 mm | 8 | 4, 32, 33, 25, 26, 27, 14, 13 | a square, not liked |

`120` and `100` were not regenerated with the 2.6 mm power tracks. The boards here point their
3D models at `../../3d/`; regenerating any of them writes into `../`, not into this folder.
