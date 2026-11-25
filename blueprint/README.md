# Courtyard house: from a pen sketch to a Blender build

A single-storey Japanese courtyard house, 14 x 14 m around a 7 x 7 m court with a red maple, built in Blender from
one hand-drawn plan (`houses/my_courtyard/sketch.png`) and three look references (`houses/my_courtyard/refs/`).
Nothing is modelled by hand: `build.py` is the whole house as one Python script.

It is based on the [blueprint](https://github.com/Nyxera0x/blueprint) skill's courtyard house (MIT, see `LICENSE`),
with the rooms re-laid from the sketch:

| Wing | Rooms (metres from the outer south-west corner, x east, y north) |
|---|---|
| South | bedroom 1.4-5.6 with a corridor closet at 0.2-1.4, entry 5.6-8.4 (sliding pair meeting at 7.0), WC 8.4-10.5, bath 10.5-14; a corridor behind them along the court |
| West | tatami room 3.5-10.5, nine mats, the court wall slid open 3.5 m |
| North | kitchen counter 3.6-8.8 on the north wall, a table for six at about (10.5, 12.3) |
| East | living 3.5-10.5 |
| Court | maple at (6.1, 7.6), stepping stones to the basin at (8.95, 5.0), a 0.9 m engawa all round |

Every part is its own object tagged with its stage (footings, sills, joists, posts, plates, tie beams, rafters,
standing-seam roof strips, charred-cedar cladding boards, floor boards, tatami with their black edging, shoji with
every kumiko strip, glass doors, furniture, garden stones), about 2,900 in all. The four wings are one function
addressed by side and (u, v), so the roof's hips and valleys land on the diagonals. Materials and plants are CC0
from Poly Haven.

## Run it

Needs Blender 4.2 or newer on PATH, Python 3 with Pillow, and ffmpeg for the film. From this `blueprint/` folder:

```bash
python houses/my_courtyard/fetch_assets.py
```

```bash
blender -b --factory-startup -P houses/my_courtyard/make_tree_lod.py -- 0.12
```

```bash
blender -b --factory-startup -P houses/my_courtyard/build.py -- aerial tatami engawa --samples 192 --res 1920x1080
```

Stills land in `blueprint-out/my_courtyard/render_<view>.png`. Other options:

- `--lod`: use the decimated conifers in stills too (needed on machines with less than about 16 GB of RAM).
- `--look dusk`: blue hour instead of the bright day after rain.
- `plan`: a straight-down view with the roof and ceilings lifted off, to check the layout against the sketch.
- `living`, `dining`, `court`, `corner`: more views.
- `--census`: print the number of parts per stage and per kind, and render nothing.

The film (it opens on the sketch, builds the house part by part on the paper with a counter, then flies in to the
tatami room):

```bash
blender -b --factory-startup -P houses/my_courtyard/film.py -- --res 1920x1080 --samples 64
```

```bash
python houses/my_courtyard/hud.py --frames blueprint-out/my_courtyard/film --out blueprint-out/my_courtyard/silent.mp4
```

`--step 3 --res 480x270 --samples 6` renders a quick preview. The action sounds (`score.py`) and music need the
blueprint skill's `sfx` and `tools` folders.

## Changes to the kit

`kit/bkit.py` renders on the CPU with OpenImageDenoise when no OptiX GPU is found (the original assumes one).
`hud.py` scales low-resolution preview frames up to 1080p before laying the counter over them.
