"""The owner's courtyard house: the courtyard house's shell and garden with the rooms re-laid from their sketch
(south: bedroom, entry, WC, bath and a corridor; west: tatami room; north: kitchen and dining; east: living).

A contemporary Japanese courtyard house at blue hour in Blender, built from a pen sketch (14 x 14 m, a 7 x 7 m
courtyard with a red maple) and 3 reference renders.

Everything is cut the way a carpenter would cut it, so a film can fly it in part by part: footings, sills, joists,
posts, plates, tie beams, struts, ridge, rafters, standing-seam roof strips, cladding boards, floor boards, tatami,
shoji frames with every kumiko strip, glass doors, furniture, garden stones. K.PARTS holds them with their stage.

Plan frame: x east, y north, the house on 0..14 x 0..14, the courtyard 3.5..10.5. Each wing is addressed by its side
(0 south, 1 east, 2 north, 3 west) in (u, v): u runs along the wing, v is the distance in from the outer wall, so one
piece of code builds all four wings and the hips and valleys of the ring roof fall on the diagonals.

Run:
  blender -b --factory-startup -P houses/my_courtyard/build.py -- aerial tatami engawa --samples 192 --res 1920x1080
Stills land in blueprint-out/courtyard/render_<shot><tag>.png.
"""
import math
import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "kit"))
import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import bkit as K  # noqa: E402
from bkit import beam, box, camera, clip_poly, cyl, fbm, light, place, place_variant, sphere, sstep, tube, vec  # noqa: E402

OPTS, SHOTS = K.args(("aerial", "tatami", "engawa"))
scene = K.setup(OPTS)
# the light: 'day' (bright after rain, a low sun from the south-east) or 'dusk' (the refs' blue hour)
LOOK = str(OPTS.get("look", "day"))
DAY = LOOK == "day"
SUN_AZ, SUN_EL = math.radians(float(OPTS.get("sun_az", 300))), math.radians(float(OPTS.get("sun_el", 30)))
FILM = K.FILM
OUT = os.path.join(os.environ.get("BLUEPRINT_OUT", "blueprint-out"), "my_courtyard")
os.makedirs(OUT, exist_ok=True)
t0 = time.time()


def stage(s):
    K.STAGE[0] = s


# ---------------------------------------------------------------- the plan (metres)
S = 14.0  # the sketch's 14.0 m square
W = 3.5  # wing depth
C0, C1 = W, S - W  # courtyard 3.5 .. 10.5
EG = 0.9  # engawa width
G0, G1 = C0 + EG, C1 - EG  # the garden inside the engawa 4.4 .. 9.6
FL = 0.45  # finished floor
CEIL = 2.9
PL0, PL1 = 2.98, 3.13  # top plates
TP = math.tan(math.radians(18))  # roof pitch
RD = W / 2  # the ridge over each wing's middle
ZR = 3.82  # ridge (roof surface)
V_OUT, V_IN = -0.9, G0 + 0.15  # eaves: 0.9 m out, over the engawa on the court side
T_OUT = 0.14  # exterior wall
BAY = 1.75


def roof_z(v):
    return ZR - TP * abs(v - RD)


def sxy(k, u, v):
    """(u, v) on side k -> plan (x, y). Side 0 south, 1 east, 2 north, 3 west."""
    return ((u, v), (S - v, u), (S - u, S - v), (v, S - u))[k]


def ubox(k, name, u0, u1, v0, v1, z0, z1, mat, **kw):
    (xa, ya), (xb, yb) = sxy(k, u0, v0), sxy(k, u1, v1)
    return box(name, xa, xb, ya, yb, z0, z1, mat, **kw)


def ubeam(k, name, u0, v0, z0, u1, v1, z1, w, h, mat, bevel=0.003):
    return beam(name, (*sxy(k, u0, v0), z0), (*sxy(k, u1, v1), z1), w, h, mat, bevel=bevel)


def along_axis(k):
    return "x" if k in (0, 2) else "y"


# ---------------------------------------------------------------- materials
def wet(m, coat=0.7, cr=0.05):
    b = m.node_tree.nodes["Principled BSDF"]
    K.inp(b, ["Coat Weight", "Clearcoat"], coat)
    K.inp(b, ["Coat Roughness", "Clearcoat Roughness"], cr)
    return m


def moss_mat():
    m, N, L, b = K.new_mat("moss")
    tc = N.new("ShaderNodeTexCoord")
    v = tc.outputs["Object"]
    n1 = K.noise_tex(N, L, v, 1.6, 6.0, 0.62)
    col = K.ramp(N, L, n1, [(0.3, (0.018, 0.045, 0.01)), (0.52, (0.045, 0.09, 0.018)), (0.75, (0.09, 0.14, 0.03))])
    # the cushion texture of real moss: the CC0 forest floor (moss, needles, leaves) turned greener, in patches
    fc, fr, fn = K.tex_maps(N, L, "forest_leaves_02", 1.2, v)
    hs = N.new("ShaderNodeHueSaturation")
    hs.inputs["Hue"].default_value = 0.56
    hs.inputs["Saturation"].default_value = 1.3
    hs.inputs["Value"].default_value = 0.7
    L.new(fc, hs.inputs["Color"])
    patch = N.new("ShaderNodeMapRange")
    patch.inputs["From Min"].default_value = 0.45
    patch.inputs["From Max"].default_value = 0.6
    L.new(K.noise_tex(N, L, v, 0.9, 3.0), patch.inputs["Value"])
    col = K.mix_rgb(N, L, K.math_node(N, L, "MULTIPLY", patch.outputs[0], 0.7), col, hs.outputs["Color"])
    col = K.mix_rgb(N, L, 0.45, col, hs.outputs["Color"], "MULTIPLY")
    nm = N.new("ShaderNodeNormalMap")
    nm.inputs["Strength"].default_value = 1.5
    L.new(fn, nm.inputs["Color"])
    L.new(nm.outputs["Normal"], b.inputs["Normal"])
    # fallen maple leaves: sparse red specks, densest under the tree
    vo = N.new("ShaderNodeTexVoronoi")
    vo.inputs["Scale"].default_value = 11.0
    L.new(v, vo.inputs["Vector"])
    spot = N.new("ShaderNodeMapRange")
    spot.inputs["From Min"].default_value = 0.1
    spot.inputs["From Max"].default_value = 0.05
    L.new(vo.outputs["Distance"], spot.inputs["Value"])
    sparse = K.math_node(N, L, "GREATER_THAN", K.noise_tex(N, L, v, 5.0, 2.0), 0.56)
    leaf = K.math_node(N, L, "MULTIPLY", spot.outputs[0], sparse)
    col = K.mix_rgb(N, L, leaf, col, (0.42, 0.05, 0.02))
    L.new(col, b.inputs["Base Color"])
    K.inp(b, "Roughness", 0.75)
    K.bump_into(N, L, b, K.noise_tex(N, L, v, 18.0, 5.0, 0.7), 0.7, 0.01)
    return m


def ground_mat():
    """Forest floor at two scales, blended by a large noise and darkened in broad patches: no tiling rows."""
    m, N, L, b = K.new_mat("ground")
    tc = N.new("ShaderNodeTexCoord")
    v = tc.outputs["Object"]
    c1, r1, n1 = K.tex_maps(N, L, "forest_leaves_02", 2.6, v)
    c2, r2, n2 = K.tex_maps(N, L, "forest_leaves_02", 9.0, v, rot=1.1)
    mask = N.new("ShaderNodeMapRange")
    mask.inputs["From Min"].default_value = 0.4
    mask.inputs["From Max"].default_value = 0.6
    L.new(K.noise_tex(N, L, v, 0.07, 4.0), mask.inputs["Value"])
    col = K.mix_rgb(N, L, mask.outputs[0], c1, c2)
    hs = N.new("ShaderNodeHueSaturation")
    hs.inputs["Hue"].default_value = float(OPTS.get("ground_hue", 0.63))  # ref 1: moss green
    hs.inputs["Saturation"].default_value = float(OPTS.get("ground_sat", 1.5))
    hs.inputs["Value"].default_value = 0.38
    L.new(col, hs.inputs["Color"])
    dark = K.ramp(N, L, K.noise_tex(N, L, v, 0.03, 3.0), [(0.35, (0.45, 0.45, 0.45)), (0.65, (1.0, 1.0, 1.0))])
    # haze by distance from the camera, so the valley and the far slopes fade into the fog like the ridges (ref 1)
    cam = N.new("ShaderNodeCameraData")
    haze = K.math_node(N, L, "SUBTRACT", 1.0, K.math_node(N, L, "EXPONENT", K.math_node(N, L, "MULTIPLY", cam.outputs["View Distance"], -1.0 / float(OPTS.get("haze_d", 500)))))
    fogc = (0.74, 0.78, 0.82, 1) if DAY else (0.2, 0.24, 0.3, 1)
    L.new(K.mix_rgb(N, L, haze, K.mix_rgb(N, L, 1.0, hs.outputs["Color"], dark, "MULTIPLY"), fogc), b.inputs["Base Color"])
    K.inp(b, "Roughness", 0.8)
    nm = N.new("ShaderNodeNormalMap")
    nm.inputs["Strength"].default_value = 1.0
    L.new(K.mix_rgb(N, L, mask.outputs[0], n1, n2), nm.inputs["Color"])
    L.new(nm.outputs["Normal"], b.inputs["Normal"])
    return m


def gravel_mat():
    m, N, L, b = K.new_mat("gravel")
    tc = N.new("ShaderNodeTexCoord")
    vo = N.new("ShaderNodeTexVoronoi")
    vo.inputs["Scale"].default_value = 38.0
    L.new(tc.outputs["Object"], vo.inputs["Vector"])
    sep = N.new("ShaderNodeSeparateColor")
    L.new(vo.outputs["Color"], sep.inputs[0])
    col = K.ramp(N, L, sep.outputs[0], [(0.0, (0.05, 0.05, 0.05)), (0.5, (0.12, 0.115, 0.11)), (1.0, (0.22, 0.21, 0.2))])
    L.new(col, b.inputs["Base Color"])
    K.inp(b, "Roughness", 0.25)
    K.bump_into(N, L, b, K.math_node(N, L, "SUBTRACT", 1.0, vo.outputs["Distance"]), 1.0, 0.012)
    return m


def roof_mat():
    m, N, L, b = K.new_mat("roof_metal")
    K.inp(b, "Base Color", (0.1, 0.1, 0.1, 1))  # ref 1: charcoal grey, not blue
    K.inp(b, "Metallic", 0.15)
    tc = N.new("ShaderNodeTexCoord")
    n = K.noise_tex(N, L, tc.outputs["Object"], 3.0, 4.0)
    L.new(K.math_node(N, L, "MULTIPLY_ADD", n, 0.25, 0.12), b.inputs["Roughness"])
    # rain on the metal: fine beads
    vo = N.new("ShaderNodeTexVoronoi")
    vo.inputs["Scale"].default_value = 70.0
    L.new(tc.outputs["Object"], vo.inputs["Vector"])
    bead = N.new("ShaderNodeMapRange")
    bead.inputs["From Min"].default_value = 0.22
    bead.inputs["From Max"].default_value = 0.0
    L.new(vo.outputs["Distance"], bead.inputs["Value"])
    K.bump_into(N, L, b, bead.outputs[0], 0.25, 0.002)
    return wet(m, 0.8, 0.02)


def lantern_mat(name, strength=7.0):
    """Washi on a bamboo spiral: the glow with darker rib bands."""
    m, N, L, b = K.new_mat(name)
    N.remove(b)
    tc = N.new("ShaderNodeTexCoord")
    wv = N.new("ShaderNodeTexWave")
    wv.bands_direction = "Z"
    wv.inputs["Scale"].default_value = 9.0
    L.new(tc.outputs["Object"], wv.inputs["Vector"])
    rib = N.new("ShaderNodeMapRange")
    rib.inputs["From Min"].default_value = 0.92
    rib.inputs["From Max"].default_value = 1.0
    L.new(wv.outputs["Fac"], rib.inputs["Value"])
    e = N.new("ShaderNodeEmission")
    L.new(K.mix_rgb(N, L, K.math_node(N, L, "MULTIPLY", rib.outputs[0], 0.5), (1.0, 0.74, 0.46), (0.55, 0.36, 0.2)), e.inputs["Color"])
    e.inputs["Strength"].default_value = strength
    L.new(e.outputs[0], N["Material Output"].inputs["Surface"])
    return m


def fog_mat(name, near, far, top, k):
    """A ridge in mist: the forest colour fading into the fog colour, lighter towards its foot."""
    m, N, L, b = K.new_mat(name)
    N.remove(b)
    geo = N.new("ShaderNodeNewGeometry")
    sep = N.new("ShaderNodeSeparateXYZ")
    L.new(geo.outputs["Position"], sep.inputs[0])
    fz = N.new("ShaderNodeMapRange")
    fz.inputs["From Min"].default_value = top
    fz.inputs["From Max"].default_value = top - 60.0
    L.new(sep.outputs[2], fz.inputs["Value"])
    f = K.math_node(N, L, "MAXIMUM", fz.outputs[0], k)
    nz = K.noise_tex(N, L, geo.outputs["Position"], 0.03, 3.0)
    f = K.math_node(N, L, "MINIMUM", K.math_node(N, L, "MULTIPLY_ADD", nz, 0.2, f), 1.0)
    e = N.new("ShaderNodeEmission")
    L.new(K.mix_rgb(N, L, f, near, far), e.inputs["Color"])
    e.inputs["Strength"].default_value = 1.0
    L.new(e.outputs[0], N["Material Output"].inputs["Surface"])
    return m


def mist_mat(name, color, density):
    m, N, L, b = K.new_mat(name)
    N.remove(b)
    tc = N.new("ShaderNodeTexCoord")
    mp = N.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.006, 0.012, 1.0)
    L.new(tc.outputs["Object"], mp.inputs["Vector"])
    n = K.noise_tex(N, L, mp.outputs["Vector"], 1.0, 5.0, 0.6)
    a = N.new("ShaderNodeMapRange")
    a.inputs["From Min"].default_value = 0.42
    a.inputs["From Max"].default_value = 0.75
    a.inputs["To Max"].default_value = density
    L.new(n, a.inputs["Value"])
    e = N.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = (*color, 1)
    tr = N.new("ShaderNodeBsdfTransparent")
    mx = N.new("ShaderNodeMixShader")
    L.new(a.outputs[0], mx.inputs[0])
    L.new(tr.outputs[0], mx.inputs[1])
    L.new(e.outputs[0], mx.inputs[2])
    L.new(mx.outputs[0], N["Material Output"].inputs["Surface"])
    return m


def water_mat():
    m, N, L, b = K.new_mat("basin_water")
    K.inp(b, "Base Color", (0.02, 0.03, 0.03, 1))
    K.inp(b, "Roughness", 0.02)
    tc = N.new("ShaderNodeTexCoord")
    K.bump_into(N, L, b, K.noise_tex(N, L, tc.outputs["Object"], 9.0, 2.0), 0.08, 0.004)
    return m


WARM = (1.0, 0.66, 0.38)
M = {
    "yakisugi": wet(K.textured("yakisugi", "japanese_cedar_planks", 1.13, value=0.05, sat=0.2, rough=(0.55, 0.3)), 0.35, 0.1),
    "cedar": K.textured("cedar", "japanese_cedar_planks", 1.13, value=1.0, sat=0.7, rough=(0.5, 0.35)),
    "cedar_band": K.textured("cedar_band", "japanese_cedar_planks", 1.13, value=0.7, sat=0.9, rough=(0.5, 0.35)),
    "engawa": wet(K.textured("engawa", "japanese_cedar_planks", 1.13, rot=math.pi / 2, value=0.36, sat=0.85, rough=(0.4, 0.1)), 1.0, 0.02),
    "hinoki": K.textured("hinoki", "oak_veneer_01", 0.9, value=1.12, sat=0.7, rough=(0.5, 0.3)),
    "oak": K.textured("oak", "oak_veneer_01", 0.9, value=0.95, sat=0.85, rough=(0.4, 0.18)),
    "oak_x": K.textured("oak_x", "oak_veneer_01", 0.9, rot=math.pi / 2, value=0.95, sat=0.85, rough=(0.4, 0.18)),
    "walnut": K.textured("walnut", "smoked_walnut_veneer", 1.0, value=0.17, sat=1.2, tint=(1.0, 0.82, 0.72), rough=(0.4, 0.25)),
    "walnut_lt": K.textured("walnut_lt", "american_walnut_veneer", 1.0, value=1.0, rough=(0.4, 0.15)),
    "tatami": K.textured("tatami", "tatami_mat", 1.8, value=0.9, sat=0.55, tint=(0.95, 0.96, 0.74), rough=(0.6, 0.3)),
    "heri": K.fabric("heri", (0.025, 0.025, 0.03), bump=0.6, size=0.05),
    "plaster": K.textured("plaster", "white_plaster_02", 1.0, tint=(0.98, 0.95, 0.9), rough=(0.4, 0.55)),
    "stucco": wet(K.textured("stucco", "white_stucco", 2.0, value=0.92, tint=(0.82, 0.78, 0.7), rough=(0.4, 0.45)), 0.25, 0.15),
    "concrete": K.textured("concrete", "concrete_wall_008", 1.5, value=0.55, sat=0.4, rough=(0.5, 0.4)),
    "roof": roof_mat(),
    "fascia": wet(K.principled("fascia", (0.035, 0.038, 0.042), 0.35, 0.6), 0.6, 0.03),
    "frame": K.principled("door_frame", (0.03, 0.026, 0.022), 0.4, 0.4),
    "glass": K.glass("glass"),
    "shoji": K.paper("shoji", (0.93, 0.9, 0.83), WARM, 0.25, 0.65),
    "closet_shoji": K.paper("closet_shoji", (0.95, 0.92, 0.85), WARM, 0.6, 0.7),
    "stone": wet(K.textured("stone", "lichen_rock", 1.4, value=0.42, sat=0.45, rough=(0.5, 0.2)), 0.9, 0.04),
    "basin": wet(K.textured("basin", "mossy_rock", 1.2, value=0.5, sat=0.7, rough=(0.5, 0.2)), 0.8, 0.05),
    "slate": wet(K.textured("slate", "japanese_stone_wall", 1.9, value=0.45, sat=0.3, rough=(0.4, 0.2)), 0.5, 0.05),
    "moss": moss_mat(),
    "gravel": gravel_mat(),
    "gravel_site": gravel_mat(),
    "ground": ground_mat(),
    "bamboo": wet(K.principled("bamboo", (0.12, 0.13, 0.05), 0.35), 0.6, 0.05),
    "water": water_mat(),
    "linen": K.fabric("linen", (0.86, 0.84, 0.79), bump=0.4, size=0.27),
    "cushion": K.fabric("cushion", (0.3, 0.27, 0.24), bump=0.5, size=0.25),
    "sofa": K.fabric("sofa", (0.62, 0.58, 0.52), bump=0.5, size=0.25),
    "rug": K.fabric("rug", (0.4, 0.36, 0.3), rough=1.0, bump=0.9, size=0.15),
    "black": K.principled("black", (0.02, 0.02, 0.02), 0.4, 0.6),
    "steel": K.principled("steel", (0.6, 0.58, 0.55), 0.25, 1.0),
    "counter": K.textured("counter", "concrete_wall_008", 1.2, value=1.15, sat=0.2, tint=(0.86, 0.84, 0.8), rough=(0.4, 0.25)),
    "ceramic": K.principled("ceramic", (0.75, 0.72, 0.66), 0.3),
    "ceramic_dk": K.principled("ceramic_dk", (0.08, 0.07, 0.06), 0.35),
    "white": K.principled("white", (0.85, 0.84, 0.82), 0.3),
    "lantern": lantern_mat("lantern", 6.0),
    "lantern_sm": lantern_mat("lantern_sm", 4.0),
    "downlight": K.emissive("downlight", WARM, 25.0),
    "andon": K.paper("andon", (0.95, 0.9, 0.8), WARM, 5.0, 0.6),
    "crawl": K.principled("crawl", (0.02, 0.02, 0.02), 1.0),
}


# ---------------------------------------------------------------- foundation, sills, joists
stage("foundation")
for k in range(4):
    for a in range(4):  # the outer footing in 3.5 m runs
        ubox(k, "footing", a * 3.5, (a + 1) * 3.5, 0.0, 0.15, -0.15, 0.3, M["concrete"], bevel=0.004)
    for a in range(2):  # the court footing under the glass line
        ubox(k, "footing", C0 + a * 3.5, C0 + (a + 1) * 3.5, C0 - 0.07, C0 + 0.07, -0.15, 0.3, M["concrete"], bevel=0.004)
stage("site")  # the dark under the floor is no part: in the film it shows with the ground
box("crawl", 0.15, S - 0.15, 0.15, S - 0.15, -0.01, 0.0, M["crawl"], bevel=0)
stage("foundation")
# engawa: a foundation stone under every post on the garden edge
EP = G0 + 0.06  # the engawa's edge posts
# only the four corners carry posts: the eave beam spans the garden side clear, so the views into the court stay open
edge_posts = sorted({(round(x, 3), round(y, 3)) for k in range(4) for u in (EP, S - EP) for x, y in [sxy(k, u, EP)]})
for x, y in edge_posts:
    cyl("sorishi", x, y, 0.15, -0.05, 0.16, M["stone"], verts=14, bevel=0.03)

stage("frame")
for k in range(4):
    for a in range(4):
        ubox(k, "dodai", a * 3.5, (a + 1) * 3.5, 0.015, 0.135, 0.3, 0.42, M["hinoki"], bevel=0.003)
    for a in range(2):
        ubox(k, "dodai", C0 + a * 3.5, C0 + (a + 1) * 3.5, C0 - 0.06, C0 + 0.06, 0.3, 0.42, M["hinoki"], bevel=0.003)
    # the engawa's edge sill on the stones
    ubox(k, "engawa_sill", EP - 0.05, S - EP + 0.05, EP - 0.05, EP + 0.05, 0.16, 0.42, M["hinoki"], bevel=0.003)
# joists across the wings (the corner squares belong to the south and north wings), and short ones under the engawa
for k in range(4):
    lo, hi = (0.2, S - 0.2) if k in (0, 2) else (C0 + 0.2, C1 - 0.2)
    u = lo
    while u <= hi:
        ubox(k, "neda", u - 0.022, u + 0.022, 0.15, C0 - 0.07, 0.36, 0.42, M["hinoki"], bevel=0.0)
        u += 0.455
    u = C0 + 0.25
    while u <= C1 - 0.25:
        top = min(EP, u, S - u) - 0.02
        if top - (C0 + 0.07) > 0.15:
            ubox(k, "neda", u - 0.022, u + 0.022, C0 + 0.07, top, 0.36, 0.42, M["hinoki"], bevel=0.0)
        u += 0.455

# ---------------------------------------------------------------- posts, plates, tie beams, ridge
posts = set()
for k in range(4):
    for i in range(9):
        posts.add(tuple(round(c, 3) for c in sxy(k, min(S - 0.07, max(0.07, i * BAY)), 0.07)))  # inside the cladding at the corners
    for i in range(5):
        posts.add(tuple(round(c, 3) for c in sxy(k, C0 + i * BAY, C0)))
posts -= {(C0, 7.0)}  # ref 2: the tatami room's court opening stands clear between its jambs (3.5 m)
for x, y in sorted(posts):
    box("hashira", x - 0.06, x + 0.06, y - 0.06, y + 0.06, 0.42, PL0, M["hinoki"], bevel=0.004)
EB0, EB1 = roof_z(EP) - 0.115 - 0.14, roof_z(EP) - 0.115  # the engawa's eave beam
for x, y in edge_posts:
    box("engawa_post", x - 0.052, x + 0.052, y - 0.052, y + 0.052, 0.16, EB0, M["hinoki"], bevel=0.004)
for k in range(4):
    for a in range(4):
        ubox(k, "keta", a * 3.5, (a + 1) * 3.5, 0.0, 0.14, PL0, PL1, M["hinoki"], bevel=0.004)
    for a in range(2):
        ubox(k, "keta", C0 + a * 3.5, C0 + (a + 1) * 3.5, C0 - 0.06, C0 + 0.06, PL0, PL1, M["hinoki"], bevel=0.004)
    ubox(k, "eave_beam", EP - 0.06, S - EP + 0.06, EP - 0.055, EP + 0.055, EB0, EB1, M["hinoki"], bevel=0.004)
    # tie beams across the wing at every bay, a strut on each to the ridge
    for i in range(1, 8):
        u = i * BAY
        if k in (1, 3) and not (C0 <= u <= C1):
            continue
        # the tie beam sits between the plates (above the ceiling, under the rafters), a strut on it to the ridge
        ubox(k, "hari", u - 0.06, u + 0.06, 0.07, C0 - 0.06, PL0, PL1, M["hinoki"], bevel=0.004)
        ubox(k, "tsuka", u - 0.045, u + 0.045, RD - 0.045, RD + 0.045, PL1, ZR - 0.115 - 0.15, M["hinoki"], bevel=0.003)
    for a in range(3):
        u0, u1 = RD + a * 3.5, RD + (a + 1) * 3.5
        ubox(k, "munagi", u0, u1, RD - 0.06, RD + 0.06, ZR - 0.115 - 0.15, ZR - 0.115, M["hinoki"], bevel=0.004)

# ---------------------------------------------------------------- rafters and the ring roof
stage("roof_frame")
for k in range(4):
    u = V_OUT + 0.2
    while u < S - V_OUT - 0.1:
        for va, vb in ((V_OUT + 0.02, min(RD, u, S - u)), (RD, min(V_IN - 0.02, u, S - u))):
            if vb - va > 0.12:
                za, zb = roof_z(va) - 0.025 - 0.045, roof_z(vb) - 0.025 - 0.045
                ubeam(k, "taruki", u, va, za, u, vb, zb, 0.045, 0.09, M["cedar"], bevel=0.002)
        u += 0.455
    # hip (outer corner) and valley (court corner) rafters on the diagonal
    ubeam(k, "sumigi", V_OUT, V_OUT, roof_z(V_OUT) - 0.025 - 0.07, RD, RD, ZR - 0.025 - 0.07, 0.09, 0.14, M["cedar"])
    ubeam(k, "tanigi", RD, RD, ZR - 0.025 - 0.07, V_IN, V_IN, roof_z(V_IN) - 0.025 - 0.07, 0.09, 0.14, M["cedar"])

stage("roof")


def roof_strip(k, u0, u1, va, vb, rib=True):
    """One standing-seam strip between u0 and u1, cut on the hip / valley diagonals, with its seam rib at u1."""
    polys = []
    p = [(u0, va), (u1, va), (u1, vb), (u0, vb)]
    p = clip_poly(p, -1.0, 1.0, 0.0)  # v <= u
    p = clip_poly(p, 1.0, 1.0, S)  # v <= S - u
    if len(p) >= 3:
        polys.append((p, 0.0, 0.025))
    if rib:
        r = [(u1 - 0.012, va), (u1 + 0.012, va), (u1 + 0.012, vb), (u1 - 0.012, vb)]
        r = clip_poly(clip_poly(r, -1.0, 1.0, 0.0), 1.0, 1.0, S)
        if len(r) >= 3:
            polys.append((r, 0.035, 0.035))
    if not polys:
        return None
    bm = bmesh.new()
    for poly, lift, thick in polys:
        pts = [sxy(k, a, b) + (b,) for a, b in poly]
        top = [bm.verts.new((x, y, roof_z(v) + lift)) for x, y, v in pts]
        bot = [bm.verts.new((x, y, roof_z(v) + lift - thick)) for x, y, v in pts]
        ft = bm.faces.new(top)
        fb = bm.faces.new(list(reversed(bot)))
        n = len(pts)
        sides = [bm.faces.new((top[i], top[(i + 1) % n], bot[(i + 1) % n], bot[i])) for i in range(n)]
        bm.normal_update()
        if ft.normal.z < 0:
            bmesh.ops.reverse_faces(bm, faces=[ft, fb] + sides)
        fb.material_index = 1 if lift == 0.0 else 0
    return K._obj("roof_strip", bm, [M["roof"], M["cedar"]])


for k in range(4):
    u = V_OUT
    while u < S - V_OUT - 1e-6:
        u1 = min(u + 0.45, S - V_OUT)
        roof_strip(k, u, u1, V_OUT, RD, rib=u1 < S - V_OUT - 1e-6)
        roof_strip(k, u, u1, RD, V_IN, rib=u1 < S - V_OUT - 1e-6)
        u = u1
    # ridge cap, hip cap, valley flashing, fascia at both eaves
    ubeam(k, "ridge_cap", RD, RD, ZR + 0.03, S - RD, RD, ZR + 0.03, 0.24, 0.05, M["fascia"])
    ubeam(k, "hip_cap", V_OUT, V_OUT, roof_z(V_OUT) + 0.03, RD, RD, ZR + 0.03, 0.16, 0.05, M["fascia"])
    ubeam(k, "valley", RD, RD, ZR + 0.004, V_IN, V_IN, roof_z(V_IN) + 0.004, 0.16, 0.01, M["fascia"])
    ubeam(k, "fascia", V_OUT, V_OUT - 0.02, roof_z(V_OUT) - 0.05, S - V_OUT, V_OUT - 0.02, roof_z(V_OUT) - 0.05, 0.04, 0.16, M["fascia"])
    ubeam(k, "fascia", V_IN, V_IN + 0.02, roof_z(V_IN) - 0.05, S - V_IN, V_IN + 0.02, roof_z(V_IN) - 0.05, 0.04, 0.16, M["fascia"])


# ---------------------------------------------------------------- walls
def run_wall(name, k, u0, u1, v0, v1, z0, z1, mat, holes=(), bevel=0.002):
    """A wall along side k from u0 to u1, v0..v1 thick, z0..z1 high, with holes [(u0, u1, z0, z1)] through it."""
    cuts = sorted({u0, u1} | {h[0] for h in holes if u0 < h[0] < u1} | {h[1] for h in holes if u0 < h[1] < u1})
    for p, q in zip(cuts, cuts[1:]):
        mid = (p + q) / 2
        spans = [(z0, z1)]
        for h in holes:
            if h[0] <= mid <= h[1]:
                spans = [s for sp in spans for s in ((sp[0], min(sp[1], h[2])), (max(sp[0], h[3]), sp[1])) if s[1] - s[0] > 0.004]
        for za, zb in spans:
            ubox(k, name, p, q, v0, v1, za, zb, mat, bevel=bevel)


def cladding(k, u0, u1, holes, mat, w, depth, gap, alt=0.0, name="clad"):
    """Boards (or panels) on the outer face of side k, cut around the holes."""
    n = max(1, round((u1 - u0) / w))
    w = (u1 - u0) / n
    for i in range(n):
        p, q = u0 + i * w + gap / 2, u0 + (i + 1) * w - gap / 2
        mid = (p + q) / 2
        spans = [(0.32, roof_z(0.0) - 0.12)]
        for h in holes:
            if h[0] - 0.01 <= mid <= h[1] + 0.01:
                spans = [s for sp in spans for s in ((sp[0], min(sp[1], h[2])), (max(sp[0], h[3]), sp[1])) if s[1] - s[0] > 0.004]
        d = depth + (alt if i % 2 else 0.0)
        for za, zb in spans:
            ubox(k, name, p, q, -d, 0.0, za, zb, mat, bevel=0.002, seg=1)


def window(k, u0, u1, z0, z1, v=T_OUT / 2, shoji_in=False):
    """A fixed window in the outer wall of side k: dark frame, glass, optional shoji behind."""
    f = 0.045
    ubox(k, "win_frame", u0, u1, v - 0.03, v + 0.03, z0, z0 + f, M["frame"], bevel=0.002)
    ubox(k, "win_frame", u0, u1, v - 0.03, v + 0.03, z1 - f, z1, M["frame"], bevel=0.002)
    ubox(k, "win_frame", u0, u0 + f, v - 0.03, v + 0.03, z0, z1, M["frame"], bevel=0.002)
    ubox(k, "win_frame", u1 - f, u1, v - 0.03, v + 0.03, z0, z1, M["frame"], bevel=0.002)
    if u1 - u0 > 1.6:
        um = (u0 + u1) / 2
        ubox(k, "win_frame", um - f / 2, um + f / 2, v - 0.03, v + 0.03, z0, z1, M["frame"], bevel=0.002)
    ubox(k, "win_glass", u0 + f, u1 - f, v - 0.004, v + 0.004, z0 + f, z1 - f, M["glass"], bevel=0)
    if shoji_in:
        n = 2 if u1 - u0 < 2.4 else 3
        wd = (u1 - u0) / n
        for i in range(n):
            shoji(k, u0 + i * wd, u0 + (i + 1) * wd, v + 0.07 + (0.035 if i % 2 else 0.0), z0 + 0.02, z1 - 0.02, out=-1)


def shoji(k, u0, u1, v, z0, z1, out=1, koshi=0.0, cell=0.3, mat=None):
    """A shoji panel on side k at depth v: hinoki frame, every kumiko strip, the paper on the 'out' side."""
    fr = 0.032
    d = 0.03
    ubox(k, "shoji_stile", u0, u0 + fr, v - d / 2, v + d / 2, z0, z1, M["hinoki"], bevel=0.0015, seg=1)
    ubox(k, "shoji_stile", u1 - fr, u1, v - d / 2, v + d / 2, z0, z1, M["hinoki"], bevel=0.0015, seg=1)
    ubox(k, "shoji_rail", u0 + fr, u1 - fr, v - d / 2, v + d / 2, z1 - 0.04, z1, M["hinoki"], bevel=0.0015, seg=1)
    zb = z0 + max(koshi, 0.04)
    ubox(k, "shoji_rail", u0 + fr, u1 - fr, v - d / 2, v + d / 2, z0, zb, M["hinoki"], bevel=0.0015, seg=1)
    a0, a1, b0, b1 = u0 + fr, u1 - fr, zb, z1 - 0.04
    cols = max(2, round((a1 - a0) / cell))
    rows = max(3, round((b1 - b0) / cell))
    for i in range(1, cols):
        uu = a0 + (a1 - a0) * i / cols
        ubox(k, "kumiko", uu - 0.006, uu + 0.006, v - 0.01, v + 0.01, b0, b1, M["hinoki"], bevel=0.0, seg=1)
    for j in range(1, rows):
        zz = b0 + (b1 - b0) * j / rows
        ubox(k, "kumiko", a0, a1, v - 0.01, v + 0.01, zz - 0.006, zz + 0.006, M["hinoki"], bevel=0.0, seg=1)
    pv = v + out * 0.012
    ubox(k, "washi", a0, a1, pv - 0.001, pv + 0.001, b0, b1, mat or M["shoji"], bevel=0.0)


def glass_door(k, u0, u1, v, z0=FL + 0.01, z1=FL + 2.09):
    f, d = 0.04, 0.035
    ubox(k, "door_stile", u0, u0 + f, v - d / 2, v + d / 2, z0, z1, M["frame"], bevel=0.0015, seg=1)
    ubox(k, "door_stile", u1 - f, u1, v - d / 2, v + d / 2, z0, z1, M["frame"], bevel=0.0015, seg=1)
    ubox(k, "door_rail", u0 + f, u1 - f, v - d / 2, v + d / 2, z1 - 0.05, z1, M["frame"], bevel=0.0015, seg=1)
    ubox(k, "door_rail", u0 + f, u1 - f, v - d / 2, v + d / 2, z0, z0 + 0.06, M["frame"], bevel=0.0015, seg=1)
    ubox(k, "door_glass", u0 + f, u1 - f, v - 0.004, v + 0.004, z0 + 0.06, z1 - 0.05, M["glass"], bevel=0.0)


stage("walls")
WALL_TOP = PL0
# outer walls: the openings per side in u (side 0 u = x, 1 u = y, 2 u = 14 - x, 3 u = 14 - y)
# read off the owner's sketch (sketch.png, ~60 px per metre)
HOLES = {
    0: [(1.4, 2.5, 0.95, 2.45), (10.8, 11.7, 1.6, 2.45)],  # bedroom; bath (high)
    1: [(4.6, 6.5, 1.05, 2.45), (10.8, 12.0, 0.95, 2.45)],  # living, over the sofa; dining
    2: [(2.2, 3.0, 0.95, 2.45), (6.95, 7.75, 1.45, 2.45), (11.0, 11.8, 0.95, 2.45)],  # dining; over the sink; kitchen
    3: [(2.5, 3.4, 0.95, 2.45), (9.4, 10.4, 0.75, 2.45)],  # kitchen; the tatami room's tokonoma
}
SPANS = {0: [(0.0, 5.6), (8.4, S)], 1: [(0.0, S)], 2: [(0.0, S)], 3: [(0.0, S)]}
for k in range(4):
    for a, b in SPANS[k]:
        run_wall("wall", k, a, b, 0.0, T_OUT, 0.42, WALL_TOP, M["plaster"], HOLES[k])
        cladding(k, a, b, HOLES[k], M["yakisugi"], 0.15, 0.018, 0.006, alt=0.012, name="yakisugi")  # refs: charred cedar all round
stage("shoji")
for k in range(4):
    for h in HOLES[k]:
        window(k, h[0], h[1], h[2], h[3], shoji_in=(k, h[0]) in ((0, 1.4), (3, 9.4)))
stage("walls")
# the entry on side 0 (sketch: the door at 7.0 m): two posts, two sliding glass doors, a cedar band above
for x in (5.6, 8.4):
    box("hashira", x - 0.06, x + 0.06, 0.01, 0.13, 0.42, PL0, M["hinoki"], bevel=0.004)
box("kamoi", 5.6, 8.4, 0.02, 0.12, FL + 2.1, FL + 2.2, M["hinoki"], bevel=0.003)
box("ranma", 5.6, 8.4, 0.04, 0.1, FL + 2.2, PL0, M["cedar_band"], bevel=0.002)
glass_door(0, 5.66, 7.04, 0.05)
glass_door(0, 6.96, 8.34, 0.1)
box("step_stone", 5.7, 8.3, -0.75, -0.05, -0.05, 0.2, M["slate"], bevel=0.02)

# the court facades (sketch: sliding doors on all four sides): sill, head, transom, glass doors outside, shoji inside the tatami room
CT = {k: [("glass", C0 + i * BAY, C0 + (i + 1) * BAY, False) for i in range(4)] for k in range(3)}
CT[3] = [("open", C0, C1, True)]
for k in range(4):
    stage("walls")
    ubox(k, "shikii", C0, C1, C0 - 0.06, C0 + 0.06, 0.42, FL + 0.01, M["hinoki"], bevel=0.002)
    ubox(k, "kamoi", C0, C1, C0 - 0.06, C0 + 0.06, FL + 2.1, FL + 2.2, M["hinoki"], bevel=0.003)
    ubox(k, "ranma", C0, C1, C0 - 0.05, C0 + 0.05, FL + 2.2, PL0, M["yakisugi"], bevel=0.002)
    stage("shoji")
    for kind, a, b, sh in CT[k]:
        if kind == "open":
            pw = (b - a) / 4
            for u0, u1, du in ((a + 0.06, a + pw, 0.04), (b - pw, b - 0.06, -0.04)):
                glass_door(k, u0, u1, C0 + 0.035)
                glass_door(k, u0 + du, u1 + du, C0 + 0.075)
                shoji(k, u0, u1, C0 - 0.035, FL + 0.01, FL + 2.09, out=1, koshi=0.22)
                shoji(k, u0 + du, u1 + du, C0 - 0.07, FL + 0.01, FL + 2.09, out=1, koshi=0.22)
            continue
        glass_door(k, a + 0.06, (a + b) / 2 + 0.02, C0 + 0.035)
        glass_door(k, (a + b) / 2 - 0.02, b - 0.06, C0 + 0.075)
        if sh:
            shoji(k, a + 0.06, (a + b) / 2 + 0.015, C0 - 0.035, FL + 0.01, FL + 2.09, out=1, koshi=0.22)
            shoji(k, (a + b) / 2 - 0.015, b - 0.06, C0 - 0.07, FL + 0.01, FL + 2.09, out=1, koshi=0.22)
stage("walls")

# partitions (plaster, door holes)
PT = 0.05
YR = 2.4  # the back wall of the south rooms (sketch 2.37); a corridor runs behind them along the court


def part_x(y, x0, x1, holes=()):
    """A partition along x at y (side 0 frame), door holes [(x0, x1)]."""
    run_wall("partition", 0, x0, x1, y - PT, y + PT, FL, CEIL, M["plaster"], [(a, b, FL - 0.1, FL + 2.0) for a, b in holes])


def part_y(x, y0, y1, holes=()):
    """A partition along y at x (side 1 frame: u = y, v = 14 - x)."""
    run_wall("partition", 1, y0, y1, S - x - PT, S - x + PT, FL, CEIL, M["plaster"], [(a, b, FL - 0.1, FL + 2.0) for a, b in holes])


part_x(YR, T_OUT, 5.6, [(0.63, 1.38), (2.04, 3.96)])  # closet, bedroom | corridor (sketch: closet gap, bedroom sliding pair)
part_y(1.39, T_OUT, YR)  # closet | bedroom
part_x(YR, 8.4, C1, [(9.05, 9.85)])  # WC | corridor
part_x(YR, C1, S - T_OUT, [(12.9, 13.7)])  # bath | corridor
part_y(5.6, T_OUT, YR)  # bedroom | entry
part_y(8.4, T_OUT, YR)  # entry | WC
part_y(C1, T_OUT, YR)  # WC | bath
part_x(C0, T_OUT, C0 - 0.06, [(2.11, 2.9)])  # corridor | tatami
part_x(C1, T_OUT, C0 - 0.06, [(1.85, 2.65)])  # tatami | kitchen
part_y(1.7, 9.7, C1)  # the tatami closet's side
part_x(C0, C1 + 0.06, S - T_OUT, [(11.2, 12.4)])  # corridor | living
part_x(C1, C1 + 0.06, S - T_OUT, [(11.2, 12.4)])  # living | dining

# ---------------------------------------------------------------- floors
stage("floor")


def boards_y(x0, x1, y0, y1, mat, w=0.15, piece=1.75, z1=FL, name="ita"):
    n = max(1, round((x1 - x0) / w))
    w = (x1 - x0) / n
    for i in range(n):
        off = (i * 0.61) % piece
        cuts = [y0] + [y for y in (y0 + off + j * piece for j in range(int((y1 - y0) / piece) + 2)) if y0 + 0.2 < y < y1 - 0.2] + [y1]
        for a, b in zip(cuts, cuts[1:]):
            box(name, x0 + i * w + 0.0015, x0 + (i + 1) * w - 0.0015, a + 0.0015, b - 0.0015, z1 - 0.025, z1, mat, bevel=0.0015, seg=1)


def boards_x(x0, x1, y0, y1, mat, w=0.15, piece=1.75, z1=FL, name="ita"):
    n = max(1, round((y1 - y0) / w))
    w = (y1 - y0) / n
    for i in range(n):
        off = (i * 0.61) % piece
        cuts = [x0] + [x for x in (x0 + off + j * piece for j in range(int((x1 - x0) / piece) + 2)) if x0 + 0.2 < x < x1 - 0.2] + [x1]
        for a, b in zip(cuts, cuts[1:]):
            box(name, a + 0.0015, b - 0.0015, y0 + i * w + 0.0015, y0 + (i + 1) * w - 0.0015, z1 - 0.025, z1, mat, bevel=0.0015, seg=1)


boards_x(T_OUT, 5.6 - PT, T_OUT, YR - PT, M["oak_x"])  # bedroom
boards_x(8.4 + PT, C1 - PT, T_OUT, YR - PT, M["oak_x"])  # WC
boards_x(5.6 + PT, 8.4 - PT, 1.3, YR + PT, M["oak_x"])  # entry hall
boards_x(T_OUT, S - T_OUT, YR + PT, C0 - 0.06, M["oak_x"])  # corridor
boards_y(C1 + 0.06, S - T_OUT, C0 + PT, C1 - PT, M["oak"])  # living
boards_x(T_OUT, S - T_OUT, C1 + 0.06, S - T_OUT, M["oak_x"])  # kitchen + dining
box("genkan", 5.6 + PT, 8.4 - PT, T_OUT, 1.3, 0.1, 0.15, M["slate"], bevel=0.004)
box("agarikamachi", 5.6 + PT, 8.4 - PT, 1.25, 1.36, 0.15, FL, M["walnut"], bevel=0.004)
box("kutsunugi", 6.4, 7.6, 0.9, 1.24, 0.15, 0.27, M["stone"], bevel=0.02)
# bath: dark slate tiles
BT0, BT1, BTY0, BTY1 = C1 + PT, S - T_OUT, T_OUT, YR - PT
for i in range(5):
    for j in range(8):
        x0, x1 = BT0 + i * 0.662, min(BT1, BT0 + (i + 1) * 0.662)
        y0, y1 = BTY0 + j * 0.3, min(BTY1, BTY0 + (j + 1) * 0.3)
        if x1 - x0 > 0.02 and y1 - y0 > 0.02:
            box("bath_tile", x0 + 0.002, x1 - 0.002, y0 + 0.002, y1 - 0.002, FL - 0.03, FL - 0.005, M["slate"], bevel=0.002, seg=1)
# tatami room (west wing): 9 mats in three rows down the wing, a cedar strip along the court glass, the tokonoma at the
# south end under its window, a closet and the door to the kitchen at the north end
TX0, TX1, TY0, TY1 = T_OUT, T_OUT + 2.7, 4.3, 9.7
MW, ML = 0.9, 1.8


def tatami_mat(cx, cy, along_x):
    lx, ly = (ML, MW) if along_x else (MW, ML)
    # built along x and turned, so the weave turns with the mat
    o = box("tatami", cx - ML / 2 + 0.002, cx + ML / 2 - 0.002, cy - MW / 2 + 0.002, cy + MW / 2 - 0.002, FL - 0.055, FL, M["tatami"], bevel=0.006, seg=2)
    if not along_x:
        o.rotation_euler = (0, 0, math.pi / 2)
    # the heri: black cloth along both long edges
    for s in (-1, 1):
        if along_x:
            box("heri", cx - lx / 2 + 0.004, cx + lx / 2 - 0.004, cy + s * (ly / 2 - 0.018) - 0.016, cy + s * (ly / 2 - 0.018) + 0.016, FL - 0.004, FL + 0.001, M["heri"], bevel=0.001, seg=1)
        else:
            box("heri", cx + s * (lx / 2 - 0.018) - 0.016, cx + s * (lx / 2 - 0.018) + 0.016, cy - ly / 2 + 0.004, cy + ly / 2 - 0.004, FL - 0.004, FL + 0.001, M["heri"], bevel=0.001, seg=1)


for i in range(3):
    for j in range(3):
        tatami_mat(TX0 + MW / 2 + i * MW, TY0 + ML / 2 + j * ML, False)
boards_y(TX1, C0 - 0.06, C0 + PT, C1 - PT, M["cedar"], w=0.2)
boards_x(TX0, TX1, TY1, C1 - PT, M["oak_x"])
boards_x(TX0, TX1, C0 + PT, TY0, M["oak_x"])  # the south end, at the door from the corridor
# engawa boards: 7 rows per side, mitred on the diagonals, each row in two lengths
stage("engawa")
for k in range(4):
    for r in range(7):
        va, vb = C0 + 0.065 + r * 0.122, C0 + 0.065 + (r + 1) * 0.122 - 0.006
        if vb > EP + 0.05:
            vb = EP + 0.05
        for ua, ub in ((C0, S / 2), (S / 2, C1)):
            p = [(ua, va), (ub, va), (ub, vb), (ua, vb)]
            p = clip_poly(clip_poly(p, -1.0, 1.0, 0.0), 1.0, 1.0, S)
            if len(p) >= 3:
                K.prism("engawa_board", [sxy(k, a, b) for a, b in p], lambda x, y: FL, 0.028, M["engawa"])

# ---------------------------------------------------------------- ceilings
stage("ceiling")
for x0, x1, y0, y1 in ((T_OUT, S - T_OUT, T_OUT, C0 - 0.06), (T_OUT, S - T_OUT, C1 + 0.06, S - T_OUT), (C1 + 0.06, S - T_OUT, C0 - 0.06, C1 + 0.06)):
    box("ceiling", x0, x1, y0, y1, CEIL, CEIL + 0.03, M["plaster"], bevel=0.0)
# tatami: cedar boards with battens running to the garden, two beams
box("ceiling_board", T_OUT, C0 - 0.06, C0 - 0.06, C1 + 0.06, CEIL + 0.01, CEIL + 0.03, M["cedar"], bevel=0.0)
yy = C0 + 0.15
while yy < C1 - 0.1:
    box("saobuchi", T_OUT, C0 - 0.06, yy - 0.015, yy + 0.015, CEIL - 0.03, CEIL + 0.01, M["hinoki"], bevel=0.002, seg=1)
    yy += 0.3
xx = T_OUT + 0.44
while xx < C0 - 0.2:
    box("saobuchi", xx - 0.015, xx + 0.015, C0 - 0.06, C1 + 0.06, CEIL - 0.03, CEIL + 0.01, M["hinoki"], bevel=0.002, seg=1)
    xx += 0.44
for by in (TY0 + 1.8, TY1 - 1.8):
    box("tenjo_beam", T_OUT, C0 - 0.06, by - 0.06, by + 0.06, CEIL - 0.14, CEIL, M["hinoki"], bevel=0.004)

# ---------------------------------------------------------------- the tatami closet: shoji fronts, lit from inside
stage("shoji")
for i in range(2):
    a = T_OUT + i * (1.7 - T_OUT) / 2
    shoji(0, a, a + (1.7 - T_OUT) / 2, TY1 + 0.02 + (0.03 if i % 2 else 0.0), FL, FL + 2.1, out=1, cell=0.27, mat=M["closet_shoji"])
box("kamoi", T_OUT, 1.7, TY1 - 0.05, TY1 + 0.05, FL + 2.1, CEIL, M["plaster"], bevel=0.002)
light("closet_glow", "AREA", (0.9, TY1 + 0.45, FL + 1.1), float(OPTS.get("closet", 90)) * 0.5, WARM, size=1.4, size_y=1.8,
      rot=(math.radians(-90), 0, 0))


# ---------------------------------------------------------------- furniture
stage("furniture")


def low_table(cx, cy, lx, ly, h, mat):
    box("table_top", cx - lx / 2, cx + lx / 2, cy - ly / 2, cy + ly / 2, FL + h - 0.06, FL + h, mat, bevel=0.008, seg=3)
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = cx + sx * (lx / 2 - 0.12), cy + sy * (ly / 2 - 0.12)
            box("table_leg", x - 0.05, x + 0.05, y - 0.05, y + 0.05, FL, FL + h - 0.06, mat, bevel=0.006)


def cushion(cx, cy, s, h, mat, z=FL, rot=0.0):
    o = box("zabuton", cx - s / 2, cx + s / 2, cy - s / 2, cy + s / 2, z, z + h, mat, bevel=h * 0.45, seg=5)
    o.rotation_euler = (0, 0, rot)
    return o


def akari(x, y, h, r, z=FL):
    for a in range(3):
        ang = math.radians(90 + a * 120)
        tube("akari_leg", (x + 0.22 * r / 0.25 * math.cos(ang), y + 0.22 * r / 0.25 * math.sin(ang), z), (x, y, z + h - r * 1.6), 0.006, M["black"], 8)
    sphere("akari_shade", x, y, z + h - r, r, M["lantern"], squash=1.0, seg=32)
    light("akari_bulb", "POINT", (x, y, z + h - r), float(OPTS.get("akari", 40)), WARM, size=r * 0.6)


# tatami room: a walnut table on the axis of the court glass, a cushion each side, a paper lantern
low_table(2.1, 7.0, 0.9, 1.5, 0.36, M["walnut"])
box("tea_tray", 1.9, 2.3, 7.05, 7.4, FL + 0.36, FL + 0.375, M["walnut_lt"], bevel=0.003)
sphere("tetsubin", 2.1, 7.22, FL + 0.375 + 0.07, 0.075, M["black"], squash=0.85, seg=24)
tube("tetsubin_spout", (2.1, 7.15, FL + 0.44), (2.1, 7.08, FL + 0.48), 0.012, M["black"], 8)
cyl("chawan", 2.05, 6.7, 0.055, FL + 0.36, FL + 0.42, M["ceramic_dk"], verts=24, bevel=0.01)
cushion(2.1, 5.75, 0.62, 0.1, M["cushion"])
cushion(2.1, 8.25, 0.62, 0.1, M["cushion"])
akari(2.95, 9.4, 0.8, 0.24)
# living (east wing): sofa on the east wall under the window, a long low table, a pouf, a shelf
box("rug", 10.9, 13.3, 4.6, 8.4, FL, FL + 0.012, M["rug"], bevel=0.004)
box("sofa_base", 13.0, 13.82, 5.0, 8.1, FL, FL + 0.18, M["walnut"], bevel=0.008)
box("sofa_seat", 13.02, 13.8, 5.02, 8.08, FL + 0.18, FL + 0.38, M["sofa"], bevel=0.05, seg=4)
for y in (5.5, 6.55, 7.6):
    box("sofa_back", 13.55, 13.82, y - 0.5, y + 0.5, FL + 0.38, FL + 0.78, M["sofa"], bevel=0.06, seg=4)
low_table(12.15, 6.55, 0.7, 1.9, 0.32, M["walnut"])
cushion(11.6, 4.95, 0.5, 0.36, M["cushion"], rot=0.6)
akari(13.45, 9.9, 1.5, 0.22)
box("shelf", 12.6, 13.84, C0 + PT, C0 + 0.45, FL, FL + 1.2, M["walnut"], bevel=0.006)
# kitchen (north wall, sketch: counter 3.6 .. 8.8 m, the sink under the window, the hob at the east end)
box("tall_unit", 3.0, 3.6, 13.18, 13.86, FL, FL + 2.1, M["walnut"], bevel=0.005)
box("counter_base", 3.6, 8.8, 13.22, 13.86, FL, FL + 0.86, M["walnut"], bevel=0.005)
box("counter_top", 3.58, 8.82, 13.18, 13.86, FL + 0.86, FL + 0.9, M["counter"], bevel=0.003)
box("sink", 6.38, 6.98, 13.3, 13.72, FL + 0.88, FL + 0.905, M["steel"], bevel=0.004)
tube("tap", (6.68, 13.8, FL + 0.9), (6.68, 13.8, FL + 1.22), 0.012, M["steel"])
tube("tap_spout", (6.68, 13.8, FL + 1.22), (6.68, 13.6, FL + 1.2), 0.012, M["steel"])
box("hob", 8.0, 8.6, 13.28, 13.76, FL + 0.9, FL + 0.906, M["black"], bevel=0.002)
box("open_shelf", 4.0, 5.4, 13.55, 13.86, FL + 1.5, FL + 1.53, M["walnut"], bevel=0.003)
# dining (sketch: a table for six at the east end of the north wing)
DX, DY = 10.5, 12.3
low_table(DX, DY, 1.6, 0.95, 0.72, M["walnut"])


def chair(x, y, fx, fy):
    """A plain walnut chair at (x, y), the sitter facing (fx, fy)."""
    h = 0.21
    box("chair_seat", x - h, x + h, y - h, y + h, FL + 0.42, FL + 0.46, M["walnut_lt"], bevel=0.008)
    for sx in (-1, 1):
        for sy in (-1, 1):
            tube("chair_leg", (x + sx * (h - 0.03), y + sy * (h - 0.03), FL), (x + sx * (h - 0.03), y + sy * (h - 0.03), FL + 0.42), 0.014, M["walnut_lt"], 8)
    bx, by = x - fx * (h - 0.02), y - fy * (h - 0.02)
    if fx:
        box("chair_back", bx - 0.02, bx + 0.02, y - h, y + h, FL + 0.6, FL + 0.84, M["walnut_lt"], bevel=0.006)
    else:
        box("chair_back", x - h, x + h, by - 0.02, by + 0.02, FL + 0.6, FL + 0.84, M["walnut_lt"], bevel=0.006)
    for sx in (-1, 1):
        if fx:
            tube("chair_post", (bx, y + sx * (h - 0.03), FL + 0.46), (bx, y + sx * (h - 0.03), FL + 0.84), 0.012, M["walnut_lt"], 8)
        else:
            tube("chair_post", (x + sx * (h - 0.03), by, FL + 0.46), (x + sx * (h - 0.03), by, FL + 0.84), 0.012, M["walnut_lt"], 8)


for x in (DX - 0.45, DX + 0.45):
    chair(x, DY + 0.72, 0, -1)
    chair(x, DY - 0.72, 0, 1)
chair(DX - 1.05, DY, 1, 0)
chair(DX + 1.05, DY, -1, 0)
for x in (DX - 0.4, DX + 0.4):
    cyl("pendant", x, DY, 0.14, FL + 1.55, FL + 1.8, M["lantern_sm"], verts=32, bevel=0.0)
    tube("pendant_cord", (x, DY, FL + 1.8), (x, DY, CEIL), 0.003, M["black"], 6)
    light("pendant_bulb", "POINT", (x, DY, FL + 1.65), float(OPTS.get("pendant", 25)), WARM, size=0.08)
# bedroom (south-west): a wardrobe at the west end, the bed along the room with its head on the entry wall, a lamp
box("closet_shelves", T_OUT, 0.6, T_OUT, YR - 0.3, FL, FL + 2.1, M["walnut"], bevel=0.005)
box("bed_base", 3.45, 5.45, 0.3, 1.9, FL, FL + 0.18, M["walnut"], bevel=0.008)
box("mattress", 3.48, 5.42, 0.33, 1.87, FL + 0.18, FL + 0.42, M["linen"], bevel=0.06, seg=4)
box("duvet", 3.44, 4.8, 0.32, 1.88, FL + 0.38, FL + 0.48, M["linen"], bevel=0.05, seg=4)
for y in (0.7, 1.5):
    box("pillow", 4.95, 5.4, y - 0.33, y + 0.33, FL + 0.42, FL + 0.56, M["linen"], bevel=0.05, seg=4)
box("headboard", 5.45, 5.6 - PT, 0.2, 2.0, FL, FL + 0.9, M["walnut"], bevel=0.005)
box("side_table", 5.05, 5.5, 1.95, 2.3, FL, FL + 0.35, M["walnut"], bevel=0.005)
cyl("lamp_sm", 5.27, 2.12, 0.1, FL + 0.35, FL + 0.6, M["lantern_sm"], verts=32, bevel=0.0)
light("bed_lamp", "POINT", (5.27, 2.12, FL + 0.5), float(OPTS.get("bedlamp", 18)), WARM, size=0.05)
# WC and bath (south-east): toilet and basin; a hinoki tub along the south wall, a stool, a vanity
box("toilet", 9.2, 9.7, 0.25, 0.9, FL, FL + 0.42, M["white"], bevel=0.06, seg=4)
box("wc_basin", 10.0, 10.4, T_OUT, 0.45, FL + 0.75, FL + 0.82, M["walnut"], bevel=0.004)
for x0, x1, y0, y1 in ((11.6, 13.2, 0.25, 0.31), (11.6, 13.2, 1.09, 1.15), (11.6, 11.66, 0.25, 1.15), (13.14, 13.2, 0.25, 1.15)):
    box("ofuro", x0, x1, y0, y1, FL - 0.03, FL + 0.6, M["hinoki"], bevel=0.004)
box("ofuro_water", 11.66, 13.14, 0.31, 1.09, FL + 0.4, FL + 0.48, M["water"], bevel=0)
box("bath_stool", 12.2, 12.5, 1.45, 1.75, FL, FL + 0.25, M["hinoki"], bevel=0.01)
box("vanity", 13.3, 13.86, 1.4, 2.3, FL + 0.75, FL + 0.82, M["walnut"], bevel=0.004)
# entry: shoe cabinet with a vase and a branch on the bedroom wall
box("getabako", 5.6 + PT, 6.1, 1.4, 2.3, FL, FL + 0.95, M["walnut"], bevel=0.005)
cyl("vase", 5.87, 1.85, 0.07, FL + 0.95, FL + 1.25, M["ceramic_dk"], verts=24, bevel=0.01)
for a in range(3):
    ang = math.radians(a * 120 + 20)
    tube("branch", (5.87, 1.85, FL + 1.2), (5.87 + 0.25 * math.cos(ang), 1.85 + 0.25 * math.sin(ang), FL + 1.75 + 0.1 * a), 0.006, M["walnut"], 6)

# ---------------------------------------------------------------- the garden
stage("garden")
GA0, GA1 = G0 + 0.28, G1 - 0.28
MOUNDS = [(6.1, 7.6, 1.6, 0.34), (8.6, 8.6, 0.9, 0.18), (5.2, 5.3, 1.0, 0.16), (8.4, 5.4, 0.7, 0.06), (5.0, 9.0, 0.7, 0.14)]


def moss_z(x, y):
    z = 0.06 + 0.015 * fbm(x, y, 1.3, 3, 4.0)
    for mx, my, r, a in MOUNDS:
        d2 = ((x - mx) ** 2 + (y - my) ** 2) / (r * r)
        z += a * math.exp(-d2 * 1.6)
    edge = min(x - GA0, GA1 - x, y - GA0, GA1 - y)
    return z * sstep(-0.05, 0.35, edge) + 0.03 * (1 - sstep(-0.05, 0.35, edge))


def heightfield(name, x0, x1, y0, y1, step, zf, mat):
    nx, ny = int((x1 - x0) / step) + 1, int((y1 - y0) / step) + 1
    verts = [(x0 + i * (x1 - x0) / (nx - 1), y0 + j * (y1 - y0) / (ny - 1), 0) for j in range(ny) for i in range(nx)]
    verts = [(x, y, zf(x, y)) for x, y, _ in verts]
    faces = [(j * nx + i, j * nx + i + 1, (j + 1) * nx + i + 1, (j + 1) * nx + i) for j in range(ny - 1) for i in range(nx - 1)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.materials.append(mat)
    me.shade_smooth()
    return K.link(bpy.data.objects.new(name, me))


heightfield("moss", GA0, GA1, GA0, GA1, 0.06, moss_z, M["moss"])
# the drip-line gravel under the court eaves
for k in range(4):
    p = [(C0, EP + 0.05), (S - C0, EP + 0.05), (S - C0, GA0 + 0.02), (C0, GA0 + 0.02)]
    p = clip_poly(clip_poly(p, -1.0, 1.0, 0.0), 1.0, 1.0, S)
    K.prism("amadare", [sxy(k, a, b) for a, b in p], lambda x, y: 0.05, 0.08, M["gravel"])


def hook_maple(objs):
    K.recolor_leaves(objs, hue=float(OPTS.get("maple_hue", 0.25)), sat=float(OPTS.get("maple_sat", 1.8)), value=float(OPTS.get("maple_val", 0.95)),
                     match=("leaves",))


MAPLE = (6.1, 7.6)
# two stems from one root, turned apart: one sparse canopy alone reads thin against the refs' dense crown
place("tree_small_02", MAPLE[0], MAPLE[1], moss_z(*MAPLE) - 0.08, yaw=float(OPTS.get("maple_yaw", 200)), height=float(OPTS.get("maple_h", 4.8)), hook=hook_maple)
place("tree_small_02", MAPLE[0] + 0.22, MAPLE[1] - 0.18, moss_z(*MAPLE) - 0.08, yaw=float(OPTS.get("maple_yaw2", 330)), height=float(OPTS.get("maple_h2", 3.5)), hook=hook_maple)
place("tree_small_02", MAPLE[0] - 0.2, MAPLE[1] + 0.25, moss_z(*MAPLE) - 0.08, yaw=float(OPTS.get("maple_yaw3", 95)), height=float(OPTS.get("maple_h3", 3.3)), hook=hook_maple)


def step_stone(x, y, r, seed, z_top=None):
    bm = bmesh.new()
    n = 30
    rr = random.Random(seed)
    ring = []
    for i in range(n):
        a = 2 * math.pi * i / n
        k = 1.0 + 0.07 * math.sin(3 * a + seed) + 0.05 * math.sin(5 * a + 2 * seed) + rr.uniform(-0.02, 0.02)
        ring.append((x + r * k * math.cos(a), y + r * 0.92 * k * math.sin(a)))
    zt = (z_top if z_top is not None else moss_z(x, y) + 0.06)
    top = [bm.verts.new((px, py, zt + 0.01 * math.sin(px * 7 + py * 5))) for px, py in ring]
    bot = [bm.verts.new((px, py, zt - 0.22)) for px, py in ring]
    bm.faces.new(top)
    bm.faces.new(list(reversed(bot)))
    for i in range(n):
        bm.faces.new((top[i], top[(i + 1) % n], bot[(i + 1) % n], bot[i]))
    bm.normal_update()
    o = K._obj("tobiishi", bm, [M["stone"]])
    return K._finish(o, 0.035, 3)


for i, (x, y, r) in enumerate(((8.0, 7.0, 0.25), (8.35, 6.55, 0.27), (8.55, 6.05, 0.27), (8.3, 5.6, 0.29), (7.9, 5.2, 0.29), (7.4, 4.95, 0.3))):
    step_stone(x, y, r, i + 3)
# rocks: a big one at the maple's foot, two smaller, pebbles at the basin
place_variant("rock_moss_set_01", 5.45, 8.35, moss_z(5.45, 8.35) - 0.15, yaw=40, height=0.55, k=1)
place_variant("rock_moss_set_01", 5.1, 6.3, moss_z(5.1, 6.3) - 0.1, yaw=120, height=0.38, k=3)
place_variant("rock_moss_set_01", 9.05, 8.05, moss_z(9.05, 8.05) - 0.1, yaw=200, height=0.3, k=4)
place_variant("rock_moss_set_01", 5.25, 9.15, moss_z(5.25, 9.15) - 0.15, yaw=300, height=0.42, k=2)
place_variant("rock_moss_set_01", 7.35, 9.1, moss_z(7.35, 9.1) - 0.12, yaw=15, height=0.45, k=5)
# the tsukubai: a carved basin, a bamboo spout, a thread of water
BX, BY = float(OPTS.get("basin_x", 8.95)), float(OPTS.get("basin_y", 5.0))
bz = moss_z(BX, BY)
bmb = bmesh.new()
res = bmesh.ops.create_cone(bmb, cap_ends=True, segments=48, radius1=0.4, radius2=0.33, depth=0.46)
top = max(bmb.faces, key=lambda f: f.calc_center_median().z)
ins = bmesh.ops.inset_region(bmb, faces=[top], thickness=0.09, depth=0.0)
bmesh.ops.translate(bmb, verts=list(top.verts), vec=(0, 0, -0.1))  # the bowl
for v in bmb.verts:
    if v not in top.verts:
        r = 1.0 + 0.05 * fbm(v.co.x * 3 + 4, v.co.y * 3, 1.0, 3, 8.0)
        v.co.x *= r
        v.co.y *= r
bas = K._obj("tsukubai", bmb, [M["basin"]])
K._finish(bas, 0.03, 3)
bas.location = (BX, BY, bz + 0.12)
cyl("tsukubai_water", BX, BY, 0.236, bz + 0.12 + 0.18, bz + 0.12 + 0.2, M["water"], verts=40, bevel=0)
tube("kakei_post", (BX + 0.52, BY + 0.05, bz - 0.1), (BX + 0.52, BY + 0.05, bz + 0.72), 0.03, M["bamboo"])
tube("kakei", (BX + 0.56, BY + 0.05, bz + 0.66), (BX + 0.12, BY + 0.02, bz + 0.58), 0.024, M["bamboo"])
tube("kakei_stream", (BX + 0.12, BY + 0.02, bz + 0.575), (BX + 0.06, BY + 0.02, bz + 0.29), 0.006, M["glass"], 8)
for i in range(7):
    a = i * 0.9
    place("rock_07", BX + 0.48 * math.cos(a), BY + 0.48 * math.sin(a), moss_z(BX, BY) - 0.02, yaw=i * 50, height=0.12 + 0.05 * (i % 3))
# ferns and low shrubs along the edges
for i, (x, y) in enumerate(((4.9, 8.9), (5.3, 9.2), (9.2, 8.55), (8.9, 9.25), (4.85, 4.85), (6.8, 9.15), (9.25, 6.2))):
    place_variant("fern_02", x, y, moss_z(x, y) - 0.02, yaw=i * 77, height=0.28 + 0.06 * (i % 3), k=i)
for i, (x, y) in enumerate(((4.75, 6.2), (4.7, 7.1), (4.8, 5.4), (5.6, 9.3), (6.9, 9.35), (8.2, 9.3), (9.3, 9.0), (6.2, 4.7), (5.3, 4.75))):
    place_variant("fern_02", x, y, moss_z(x, y) - 0.02, yaw=i * 53, height=0.32 + 0.07 * (i % 3), k=10 + i)
for i, (x, y) in enumerate(((5.0, 7.5), (9.1, 7.8), (6.3, 4.95))):
    place_variant("shrub_02", x, y, moss_z(x, y) - 0.03, yaw=i * 61, height=0.55, k=i)
# garden lights: the maple's uplight, two andon on the path
for dx, dy in ((0.55, -0.6), (-0.6, 0.4)):
    up = light("maple_up", "SPOT", (MAPLE[0] + dx, MAPLE[1] + dy, moss_z(*MAPLE) + 0.12), float(OPTS.get("uplight", 450)), WARM, size=0.05, spot=(75, 0.6))
    K.aim(up, (MAPLE[0] - 0.4 * dx, MAPLE[1] - 0.4 * dy, 3.6))
for x, y in ((5.25, 5.05), (7.4, 6.1)):
    z = moss_z(x, y)
    box("andon_base", x - 0.06, x + 0.06, y - 0.06, y + 0.06, z - 0.05, z + 0.12, M["stone"], bevel=0.01)
    box("andon", x - 0.07, x + 0.07, y - 0.07, y + 0.07, z + 0.12, z + 0.34, M["andon"], bevel=0.004)
    light("andon_bulb", "POINT", (x, y, z + 0.24), float(OPTS.get("andon", 12)), WARM, size=0.04)

# ---------------------------------------------------------------- room lights
stage("lights")
ROOMS = {  # (x, y, z, size_x, size_y, watts)
    "tatami": (1.5, 7.0, CEIL - 0.02, 2.2, 3.6, 160),
    "living": (12.2, 6.5, CEIL - 0.02, 2.4, 3.6, 170),
    "kitchen": (6.0, 12.3, CEIL - 0.02, 5.0, 2.2, 190),
    "dining": (10.8, 12.3, CEIL - 0.02, 2.6, 2.0, 120),
    "bed": (3.0, 1.25, CEIL - 0.02, 4.0, 1.6, 120),
    "wc": (9.45, 1.25, CEIL - 0.02, 1.2, 1.2, 30),
    "bath": (12.2, 1.25, CEIL - 0.02, 2.6, 1.6, 70),
    "entry": (7.0, 1.6, CEIL - 0.02, 2.0, 1.6, 80),
    "corridor": (7.0, 2.95, CEIL - 0.02, 10.0, 0.6, 90),
}
ROOM_L = {}
for nm, (x, y, z, sx, sy, wv) in ROOMS.items():
    ROOM_L[nm] = light("room_" + nm, "AREA", (x, y, z), wv * float(OPTS.get("room", 0.5 if DAY else 1.0)), WARM, size=sx, size_y=sy)
# downlights in the plaster ceilings and under the court eaves
for x, y in ((12.2, 5.0), (12.2, 8.0), (1.0, 2.95), (4.5, 2.95), (9.5, 2.95), (13.0, 2.95), (2.5, 12.3), (5.5, 12.3)):
    cyl("downlight", x, y, 0.045, CEIL - 0.002, CEIL + 0.001, M["downlight"], verts=20, bevel=0)
for k in range(4):
    for u in (C0 + BAY / 2 + i * BAY for i in range(4)):
        v = C0 + 0.45
        x, y = sxy(k, u, v)
        z = roof_z(v) - 0.025 - 0.095
        cyl("eave_light", x, y, 0.035, z - 0.004, z, M["downlight"], verts=16, bevel=0)
        sp = light("eave_spot", "SPOT", (x, y, z - 0.01), float(OPTS.get("eave", 22)), WARM, size=0.03, spot=(80, 0.7))
        K.aim(sp, (x, y, 0.0))

# ---------------------------------------------------------------- the site: hillside, pines, ridges in mist
stage("site")


def site_z(x, y):
    dx = max(0.0, abs(x - 7.0) - 9.0)
    dy = max(0.0, abs(y - 7.0) - 9.0)
    d = math.hypot(dx, dy)
    z = -0.05 - 0.08 * sstep(0.0, 3.0, d)
    z += 0.5 * fbm(x, y, 0.05, 4, 3.0) * sstep(1.0, 8.0, d)
    # ref 1: the plateau breaks off to the north-west (the aerial's view) into a deep valley; forested hills rise
    # beyond it and on both flanks, so the valley reads as a V filled with fog
    vw = (x - 7.0) * -0.69 + (y - 7.0) * 0.72
    lat = (x - 7.0) * 0.72 + (y - 7.0) * 0.69
    z -= 62.0 * sstep(16.0, 55.0, vw)
    z += 34.0 * sstep(55.0, 150.0, abs(lat)) * sstep(30.0, 110.0, vw) * (0.7 + 0.3 * fbm(x, y, 0.02, 3, 9.0))
    z += 9.0 * sstep(18.0, 110.0, -vw) * (0.6 + 0.4 * fbm(x, y, 0.02, 3, 5.0))
    return z


def terrain():
    def axis(a0, a1, near):
        v = [a0]
        while v[-1] < a1:
            c = v[-1]
            d = max(0.0, abs(c - 7.0) - 10.0)
            v.append(min(a1, c + near + d * 0.06))
        return v

    xs, ys = axis(-140.0, 160.0, 0.5), axis(-140.0, 170.0, 0.5)
    nx = len(xs)
    verts = [(x, y, site_z(x, y)) for y in ys for x in xs]
    faces = [(j * nx + i, j * nx + i + 1, (j + 1) * nx + i + 1, (j + 1) * nx + i) for j in range(len(ys) - 1) for i in range(nx - 1)]
    me = bpy.data.meshes.new("site")
    me.from_pydata(verts, [], faces)
    me.materials.append(M["ground"])
    me.shade_smooth()
    print(f"terrain {nx} x {len(ys)}")
    return K.link(bpy.data.objects.new("site", me))


terrain()
# gravel apron and a stepping path to the door
box("apron", -0.9, S + 0.9, -0.9, S + 0.9, -0.06, -0.02, M["gravel_site"], bevel=0)
for i in range(5):
    step_stone(7.0 + 0.3 * math.sin(i * 1.3), -1.35 - i * 0.95, 0.44, 20 + i, z_top=site_z(7.0, -1.35 - i * 0.95) + 0.05)
random.seed(11)
# the film uses decimated conifers (make_tree_lod.py): the full ones peak the 8 GB card under motion blur
TREE = (lambda mid: mid + "_lod") if (FILM or OPTS.get("lod")) and "pine_tree_01_lod" in K.ASSETS else (lambda mid: mid)
PINES = [(-6, 18, 13), (-9, 4, 11), (-5, -9, 12), (19, -6, 10), (22, 9, 12), (12, 22, 11), (-14, 12, 14), (3, 24, 12), (25, -14, 13),
         (-18, -14, 15), (30, 25, 14), (-3, 32, 13), (40, 6, 15), (-26, 26, 16), (8, -18, 12), (-20, -2, 13), (34, -4, 12)]
for i, (x, y, h) in enumerate(PINES):
    near = math.hypot(x - 7, y - 7) < 20
    place_variant(TREE("pine_sapling_medium") if near and i % 2 else TREE("pine_tree_01"), x, y, site_z(x, y) - 0.1, yaw=i * 47, height=h * (0.62 if near and i % 2 else 0.85), k=i)
for i in range(26):
    a = random.uniform(0, 2 * math.pi)
    r = random.uniform(45, 110)
    x, y = 7 + r * math.cos(a), 7 + r * math.sin(a)
    place_variant(TREE("fir_tree_01"), x, y, site_z(x, y) - 0.2, yaw=random.uniform(0, 360), height=random.uniform(11, 18), k=i)
for i, (x, y) in enumerate(((-2.5, 3.0), (16.0, 1.0), (-2.0, 12.0), (15.5, 15.0), (3.0, 16.5), (11.0, -2.5), (-3.0, -2.0))):
    place_variant(TREE("pine_sapling_medium"), x, y, site_z(x, y) - 0.05, yaw=i * 33, height=random.uniform(2.5, 4.0), k=i)
for i, (x, y) in enumerate(((-1.8, 7.0), (15.8, 6.0), (2.0, -2.2), (12.5, 15.9), (-1.6, 14.8), (15.6, -1.4), (9.5, -2.3), (4.5, 15.8))):
    place_variant("shrub_02", x, y, site_z(x, y) - 0.05, yaw=i * 71, height=random.uniform(0.6, 1.1), k=i)
rr = random.Random(5)
for i in range(30):
    a = math.radians(rr.choice((rr.uniform(15, 100), rr.uniform(170, 285))))  # framing the sides: clear to the south-east (the aerial) and the north-west (the valley it looks into)
    r = rr.uniform(12.0, 21.0)
    x, y = 7 + r * math.cos(a), 7 + r * math.sin(a)
    place_variant(TREE("pine_tree_01") if i % 3 else TREE("fir_tree_01"), x, y, site_z(x, y) - 0.15, yaw=rr.uniform(0, 360), height=rr.uniform(11, 17), k=100 + i)
for i in range(22):  # moss boulders, ferns and shrubs up to the gravel
    a = math.radians(rr.uniform(0, 360))
    r = rr.uniform(9.6, 12.5)
    x, y = 7 + r * math.cos(a), 7 + r * math.sin(a)
    if abs(x - 7) < 1.6 and y < 0:
        continue  # the path to the door
    if i % 3 == 0:
        place_variant("rock_moss_set_01", x, y, site_z(x, y) - 0.25, yaw=i * 53, height=rr.uniform(0.6, 1.2), k=200 + i)
    else:
        place_variant("shrub_02" if i % 3 == 1 else "fern_02", x, y, site_z(x, y) - 0.05, yaw=i * 41, height=rr.uniform(0.45, 0.9), k=200 + i)
for i, (x, y, h) in enumerate(((-3.2, 9.5, 1.4), (17.0, 11.0, 1.1), (-2.4, -3.6, 1.0), (18.5, -2.0, 1.6), (5.0, 18.5, 1.2))):
    place_variant("rock_moss_set_01", x, y, site_z(x, y) - 0.3, yaw=i * 90, height=h, k=i)


def ridge_layer(name, dist, h0, amp, mat, seed, a0=-180, a1=180):
    verts, faces = [], []
    n = 0
    a = a0
    while a <= a1:
        r = math.radians(a)
        hz = h0 + amp * (0.55 + 0.45 * fbm(a * 0.035, seed, 1.0, 4, seed)) + amp * 0.1 * fbm(a * 0.15, seed + 3, 1.0, 2, seed + 1)
        x, y = 7 + dist * math.cos(r), 7 + dist * math.sin(r)
        verts += [(x, y, -260.0), (x, y, hz)]
        if n:
            faces.append((2 * n - 2, 2 * n, 2 * n + 1, 2 * n - 1))
        n += 1
        a += 0.5
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.materials.append(mat)
    return K.link(bpy.data.objects.new(name, me))


FOG = (0.72, 0.78, 0.86) if DAY else (0.36, 0.41, 0.5)
RIDGES = (((170, -25, 45, (0.12, 0.2, 0.14), 0.22), (300, -20, 70, (0.22, 0.3, 0.3), 0.4), (520, -10, 105, (0.44, 0.52, 0.6), 0.72),
           (900, 10, 150, (0.55, 0.62, 0.72), 0.85)) if DAY else
          ((170, -25, 45, (0.06, 0.085, 0.09), 0.45), (300, -20, 70, (0.12, 0.15, 0.18), 0.6), (520, -10, 105, (0.19, 0.22, 0.28), 0.74),
           (900, 10, 150, (0.25, 0.29, 0.36), 0.86)))
for i, (d, h0, amp, near, kf) in enumerate(RIDGES):
    ridge_layer(f"ridge_{i}", d, h0, amp, fog_mat(f"ridge_{i}", near, FOG, h0 + amp, kf), 3.0 + i * 7)
# fog lying in the valley in two layers (ref 1), the upper one threading through the trees on the slopes
box("mist_0", 7 - 900, 7 + 900, 7 - 900, 7 + 900, -58.0, -57.99, mist_mat("mist_0", (0.86, 0.88, 0.9) if DAY else (0.24, 0.28, 0.35), 0.75 if DAY else 0.5), bevel=0)
box("mist_1", 7 - 900, 7 + 900, 7 - 900, 7 + 900, -44.0, -43.99, mist_mat("mist_1", (0.9, 0.9, 0.9) if DAY else (0.24, 0.28, 0.35), 0.2 if DAY else 0.25), bevel=0)
# grass clumps on the plateau around the house
for i in range(160):
    a = random.uniform(0, 2 * math.pi)
    r = random.uniform(11.5, 24)
    x, y = 7 + r * math.cos(a), 7 + r * math.sin(a)
    if -2.0 < x < 16.0 and -3.5 < y < 16.0:
        continue
    place_variant("grass_medium_01", x, y, site_z(x, y) - 0.03, yaw=random.uniform(0, 360), height=random.uniform(0.25, 0.5), k=i)
# the forest down the valley sides and up the far slope (ref 1)
rv = random.Random(23)
for i in range(180):
    vw, lat = rv.uniform(24, 115), rv.uniform(-170, 170)
    if vw < 60 and abs(lat) < 22:
        continue  # the view down the valley from the house stays open
    x, y = 7 + vw * -0.69 + lat * 0.72, 7 + vw * 0.72 + lat * 0.69
    place_variant(TREE("fir_tree_01") if i % 3 else TREE("pine_tree_01"), x, y, site_z(x, y) - 0.3, yaw=rv.uniform(0, 360), height=rv.uniform(12, 20), k=300 + i)
# the forest on the slopes below and behind
for i in range(70):
    a = random.uniform(0, 2 * math.pi)
    r = random.uniform(26, 120)
    x, y = 7 + r * math.cos(a), 7 + r * math.sin(a)
    if abs(x - 7) < 16 and abs(y - 7) < 16:
        continue
    place_variant(TREE("fir_tree_01") if i % 3 else TREE("pine_tree_01"), x, y, site_z(x, y) - 0.2, yaw=random.uniform(0, 360), height=random.uniform(9, 17), k=i)

# ---------------------------------------------------------------- sky: blue hour, overcast, brighter low over the valley
world = bpy.data.worlds.new("sky")
scene.world = world
world.use_nodes = True
WN, WL = world.node_tree.nodes, world.node_tree.links
tc = WN.new("ShaderNodeTexCoord")
dirv = WN.new("ShaderNodeVectorMath")
dirv.operation = "NORMALIZE"
WL.new(tc.outputs["Generated"], dirv.inputs[0])
sepw = WN.new("ShaderNodeSeparateXYZ")
WL.new(dirv.outputs["Vector"], sepw.inputs[0])
grad = WN.new("ShaderNodeMapRange")
grad.inputs["From Min"].default_value = -0.05
grad.inputs["From Max"].default_value = 0.7
WL.new(sepw.outputs[2], grad.inputs["Value"])
sky = K.ramp(WN, WL, grad.outputs[0], [(0.0, (0.88, 0.86, 0.82)), (0.1, (0.8, 0.81, 0.82)), (0.4, (0.62, 0.68, 0.76)), (1.0, (0.45, 0.53, 0.66))] if DAY else
             [(0.0, (0.36, 0.41, 0.5)), (0.12, (0.32, 0.38, 0.5)), (0.4, (0.2, 0.26, 0.38)), (1.0, (0.09, 0.12, 0.2))], "EASE")
# a soft glow low over the valley (north-east) where the light went
gd = WN.new("ShaderNodeVectorMath")
gd.operation = "DOT_PRODUCT"
WL.new(dirv.outputs["Vector"], gd.inputs[0])
SUN_DIR = Vector((math.cos(SUN_AZ) * math.cos(SUN_EL), math.sin(SUN_AZ) * math.cos(SUN_EL), math.sin(SUN_EL)))
gd.inputs[1].default_value = SUN_DIR if DAY else (0.55, 0.83, 0.08)
glow = K.math_node(WN, WL, "MULTIPLY", K.math_node(WN, WL, "POWER", K.math_node(WN, WL, "MAXIMUM", gd.outputs["Value"], 0.0), 6.0), 0.25)
sky = K.mix_rgb(WN, WL, glow, sky, (1.0, 0.86, 0.62) if DAY else (0.45, 0.5, 0.62), "ADD")
# clouds: low contrast overcast
proj = WN.new("ShaderNodeCombineXYZ")
inv = K.math_node(WN, WL, "DIVIDE", 1.0, K.math_node(WN, WL, "MAXIMUM", sepw.outputs[2], 0.03))
WL.new(K.math_node(WN, WL, "MULTIPLY", sepw.outputs[0], inv), proj.inputs[0])
WL.new(K.math_node(WN, WL, "MULTIPLY", sepw.outputs[1], inv), proj.inputs[1])
cn = K.noise_tex(WN, WL, proj.outputs[0], 0.35, 6.0, 0.6)
cl = WN.new("ShaderNodeMapRange")
cl.inputs["From Min"].default_value = 0.4
cl.inputs["From Max"].default_value = 0.7
WL.new(cn, cl.inputs["Value"])
sky = K.mix_rgb(WN, WL, K.math_node(WN, WL, "MULTIPLY", cl.outputs[0], 0.6 if DAY else 0.35), sky, (0.93, 0.94, 0.96) if DAY else (0.26, 0.3, 0.4))
WL.new(sky, WN["Background"].inputs["Color"])
WN["Background"].inputs["Strength"].default_value = float(OPTS.get("sky", 1.0 if DAY else 1.3))
# the day's sun, low from the south-east: a rim on the maple, light across the court and into the rooms
DAY_SUN = None
if DAY:
    sd = bpy.data.lights.new("day_sun", "SUN")
    sd.energy = float(OPTS.get("sun", 4.6))
    sd.color = (1.0, 0.82, 0.62)
    sd.angle = math.radians(1.5)
    DAY_SUN = bpy.data.objects.new("day_sun", sd)
    scene.collection.objects.link(DAY_SUN)
    DAY_SUN.rotation_euler = SUN_DIR.to_track_quat("Z", "Y").to_euler()

# ---------------------------------------------------------------- shots
SHOT = {
    # ref 2: high over the south-west corner, the roofs around the court, the valley and the ridges beyond
    "aerial": dict(loc=vec("aerial_loc", (19.0, -6.2, 10.2)), target=vec("aerial_at", (5.6, 8.4, 2.6)), lens=float(OPTS.get("aerial_lens", 22)), ev=0.75 if DAY else 0.4, sun=(200, 22)),
    # low over the south-west corner: the cedar wall, the lit glass of the entry, the maple over the roof, the ridges
    "corner": dict(loc=vec("corner_loc", (-4.2, -4.6, 4.6)), target=vec("corner_at", (8.0, 8.5, 1.4)), lens=float(OPTS.get("corner_lens", 20)), ev=-0.2 if DAY else 0.5),
    # straight down into the court between the roofs
    "court": dict(loc=vec("court_loc", (7.0, -2.5, 13.5)), target=vec("court_at", (7.0, 7.6, 0.0)), lens=float(OPTS.get("court_lens", 24)), ev=-0.2 if DAY else 0.3),
    # seated in the tatami room (west wing), across the table and through the glass to the maple
    "tatami": dict(loc=vec("tatami_loc", (0.3, 7.0, 1.08)), target=vec("tatami_at", (9.0, 7.0, 1.05)), lens=float(OPTS.get("tatami_lens", 15)), ev=0.75 if DAY else -0.3, sun=(330, 16), room=0.35),
    # from the sofa corner of the living room, across the court to the tatami room
    "living": dict(loc=vec("living_loc", (13.4, 4.1, 1.35)), target=vec("living_at", (5.5, 8.0, 1.2)), lens=float(OPTS.get("living_lens", 18)), ev=-0.2 if DAY else 0.0),
    # from the dining table, south over the court to the entry wing
    "dining": dict(loc=vec("dining_loc", (12.9, 13.4, 1.5)), target=vec("dining_at", (7.0, 6.0, 1.0)), lens=float(OPTS.get("dining_lens", 18)), ev=-0.2 if DAY else 0.0),
    # ref 4: on the north engawa looking west, the basin and the maple on the left, the lit rooms on the right
    "engawa": dict(loc=vec("engawa_loc", (4.12, 9.6, 1.0)), target=vec("engawa_at", (3.95, 3.0, 1.15)), lens=float(OPTS.get("engawa_lens", 18)), ev=1.0 if DAY else 0.0, sun=(318, 20)),
}
print(f"built in {time.time() - t0:.1f} s, {len(K.PARTS)} parts")
if OPTS.get("blend"):
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "japan.blend"))
# a check against the sketch: straight down with the roof and the ceilings lifted off
SHOT["plan"] = dict(loc=vec("plan_loc", (7.0, 7.0, 60.0)), target=vec("plan_at", (7.0, 7.02, 0.0)), lens=float(OPTS.get("plan_lens", 70)), ev=0.0)
if OPTS.get("census"):
    from collections import Counter
    st = Counter(t for _, t in K.PARTS)
    nm = Counter(o.name.split(".")[0] for o, _ in K.PARTS)
    print("CENSUS stages", dict(st.most_common()))
    print("CENSUS parts", dict(nm.most_common()))
    SHOTS = []
ROOM_E0 = {n: L.data.energy for n, L in ROOM_L.items()}
for s in ([] if FILM else SHOTS):
    c = SHOT[s]
    for n, L in ROOM_L.items():  # a still can dim the room lights (ref 2 is lit by the day)
        L.data.energy = ROOM_E0[n] * float(OPTS.get(f"{s}_room", c.get("room", 1.0)))
    if DAY_SUN is not None:
        az, el = (math.radians(float(OPTS.get(f"{s}_sun_az", c.get("sun", (math.degrees(SUN_AZ), 0))[0]))),
                  math.radians(float(OPTS.get(f"{s}_sun_el", c.get("sun", (0, math.degrees(SUN_EL)))[1]))))
        sdir = Vector((math.cos(az) * math.cos(el), math.sin(az) * math.cos(el), math.sin(el)))
        DAY_SUN.rotation_euler = sdir.to_track_quat("Z", "Y").to_euler()
        gd.inputs[1].default_value = sdir
    for o, st in K.PARTS:
        if st in ("roof", "roof_frame", "ceiling"):
            o.hide_render = s == "plan"
    scene.camera = camera(s, c["loc"], c["target"], c["lens"])
    scene.view_settings.exposure = float(OPTS.get(f"{s}_ev", c.get("ev", 0.0)))
    scene.render.filepath = os.path.join(OUT, f"render_{s}{OPTS.get('tag', '')}.png")
    t1 = time.time()
    bpy.ops.render.render(write_still=True)
    print(f"{s}: rendered in {time.time() - t1:.1f} s")
