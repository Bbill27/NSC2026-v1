"""
===============================================================================
CerebroMotion - Parametric "Ghost Hand" Model
===============================================================================
A small 2D hand model used by the Interactive Tutorial to *demonstrate* each
exercise step as a smooth animation (instead of a video clip).

The same model also produces the 21 MediaPipe-style landmarks for every pose.
That lets us verify (see tests/test_hand_model.py) that every pose the tutorial
shows is accepted by the real scoring engine in logic.py, so the guide teaches
exactly what the therapy session measures.

Two camera views are supported:
  * "front" - palm facing the camera (fists, taps, piano, spread, flip, wiper)
  * "side"  - hand seen from the thumb side (L-shape, claw, wrist bend)
===============================================================================
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields, replace
from typing import Iterable

# =============================================================================
# 1. POSE DESCRIPTION
# =============================================================================
@dataclass(frozen=True)
class HandPose:
    view: str = "front"               # "front" | "side"
    mcp: tuple = (5, 5, 5, 5)         # knuckle flexion per finger (index..pinky), degrees
    pip: tuple = (5, 5, 5, 5)         # middle joint flexion
    dip: tuple = (3, 3, 3, 3)         # end joint flexion
    spread: float = 8.0               # finger fan, degrees between neighbours
    thumb_abd: float = 40.0           # thumb opening away from the index finger, degrees
    thumb_flex: float = 0.0           # 0 = straight, 1 = folded across the palm
    touch: tuple = (0, 0, 0, 0)       # thumb-to-fingertip opposition weights (index..pinky)
    tilt: float = 0.0                 # front view: in-plane rotation, + = to the right
    back: float = 0.0                 # front view: 0 = palm, 1 = back of the hand
    base_angle: float = -90.0         # side view: forearm direction (0 = right, -90 = up)
    wrist_flex: float = 0.0           # side view: wrist bend, + = clockwise on screen
    highlight: tuple = ()             # fingers drawn in the accent colour (0 = thumb .. 4 = pinky)


def _ease(t: float) -> float:
    """Smooth ease-in-out so the ghost hand moves like a person, not a robot."""
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def lerp_pose(a: HandPose, b: HandPose, t: float) -> HandPose:
    """Interpolates every numeric field of two poses."""
    if t >= 1.0:
        return b          # exact object, so the renderer's cache hits while the hand is at rest
    if t <= 0.0:
        return a
    t = _ease(t)
    out = {}
    for f in fields(HandPose):
        va, vb = getattr(a, f.name), getattr(b, f.name)
        if f.name in ("view", "highlight"):
            out[f.name] = va if t < 0.5 else vb
        elif isinstance(va, tuple):
            out[f.name] = tuple(x + (y - x) * t for x, y in zip(va, vb))
        else:
            out[f.name] = va + (vb - va) * t
    return HandPose(**out)


# =============================================================================
# 2. FORWARD KINEMATICS (hand units: wrist at 0,0 ; wrist->middle MCP = 1)
# =============================================================================
_MCP_POS = [(-0.30, -0.95), (-0.08, -1.00), (0.14, -0.96), (0.33, -0.86)]
_SEG = [(0.45, 0.27, 0.22), (0.50, 0.30, 0.24), (0.46, 0.28, 0.23), (0.36, 0.21, 0.19)]
_FAN = [-4.0, -1.0, 2.0, 6.0]
_SPREAD_K = [-1.5, -0.5, 0.5, 1.5]
_CMC = (-0.30, -0.24)
_THUMB_SEG = (0.36, 0.30, 0.25)

_PALM_POLY_FRONT = [(-0.30, 0.05), (-0.40, -0.30), (-0.41, -0.90), (-0.30, -1.04),
                    (-0.08, -1.09), (0.15, -1.05), (0.40, -0.93), (0.42, -0.40), (0.31, 0.06)]


def _rot(p, deg, origin=(0.0, 0.0)):
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    x, y = p[0] - origin[0], p[1] - origin[1]
    return (origin[0] + x * c - y * s, origin[1] + x * s + y * c)


def _dir_from_vertical(deg):
    """Unit vector: 0 deg = straight up on screen, + = clockwise (to the right)."""
    r = math.radians(deg)
    return (math.sin(r), -math.cos(r))


def _dir_from_angle(deg):
    """Unit vector: 0 deg = right, 90 deg = down (screen coordinates)."""
    r = math.radians(deg)
    return (math.cos(r), math.sin(r))


def _bezier(p0, c, p1, t):
    u = 1.0 - t
    return (u * u * p0[0] + 2 * u * t * c[0] + t * t * p1[0],
            u * u * p0[1] + 2 * u * t * c[1] + t * t * p1[1])


def _front_points(pose: HandPose):
    """Returns (pts[21] as (x, y, z), palm_poly, forearm_poly) in hand units."""
    pts = [(0.0, 0.0, 0.0)] * 21
    pts[0] = (0.0, 0.0, 0.0)

    touch = list(pose.touch)
    tips = []
    for i in range(4):
        a = _FAN[i] + _SPREAD_K[i] * pose.spread
        d = _dir_from_vertical(a)
        # Fingers being touched by the thumb bend a little to meet it.
        extra_m, extra_p = 32.0 * touch[i], 30.0 * touch[i]
        flex = [pose.mcp[i] + extra_m, pose.pip[i] + extra_p, pose.dip[i] + 10.0 * touch[i]]
        x, y = _MCP_POS[i]
        z = 0.0
        base = 5 + i * 4
        pts[base] = (x, y, z)
        cum = 0.0
        for k in range(3):
            cum += flex[k]
            L = _SEG[i][k]
            c = math.cos(math.radians(cum))
            x += d[0] * L * c
            y += d[1] * L * c
            z -= L * math.sin(math.radians(cum)) * 0.5
            pts[base + 1 + k] = (x, y, z)
        tips.append(pts[base + 3])

    # Thumb: normal chain (abduction + flexion across the palm)
    cmc = _CMC
    chain = [cmc]
    ang = -pose.thumb_abd
    bends = (40.0, 45.0, 35.0)
    x, y = cmc
    for k in range(3):
        ang += pose.thumb_flex * bends[k]
        d = _dir_from_vertical(ang)
        x += d[0] * _THUMB_SEG[k]
        y += d[1] * _THUMB_SEG[k]
        chain.append((x, y))

    # Opposition: bend the thumb along a curve to meet the chosen fingertip(s)
    w = sum(touch)
    if w > 1e-3:
        tx = sum(tips[i][0] * touch[i] for i in range(4)) / w
        ty = sum(tips[i][1] * touch[i] for i in range(4)) / w
        target = (tx - 0.03, ty + 0.03)
        ctrl = (cmc[0] - 0.28, cmc[1] - 0.50)
        opp = [cmc] + [_bezier(cmc, ctrl, target, t) for t in (0.42, 0.74, 1.0)]
        wb = min(1.0, w)
        chain = [(c[0] + (o[0] - c[0]) * wb, c[1] + (o[1] - c[1]) * wb) for c, o in zip(chain, opp)]

    for k in range(4):
        pts[1 + k] = (chain[k][0], chain[k][1], -0.05 * k)

    palm = list(_PALM_POLY_FRONT)
    forearm = [(-0.30, 0.05), (0.31, 0.06), (0.36, 1.10), (-0.36, 1.10)]

    # Flip to the back of the hand (mirror with a "turning" squash in between)
    sx = math.cos(math.pi * max(0.0, min(1.0, pose.back)))
    if abs(sx) < 0.08:
        sx = 0.08 if sx >= 0 else -0.08

    def tf(p):
        q = (p[0] * sx, p[1])
        return _rot(q, pose.tilt)

    pts = [tf(p) + (p[2],) for p in pts]
    palm = [tf(p) for p in palm]
    forearm = [tf(p) for p in forearm]
    return pts, palm, forearm


def _side_points(pose: HandPose):
    """Hand seen from the thumb side. Fingers flex clockwise on screen."""
    alpha = pose.base_angle + pose.wrist_flex
    u = _dir_from_angle(alpha)
    v = _dir_from_angle(alpha + 90.0)          # towards the palm side
    pts = [(0.0, 0.0, 0.0)] * 21

    knuckle_len = (0.97, 1.00, 0.97, 0.90)
    stack = (-0.05, 0.0, 0.05, 0.10)
    for i in range(4):
        x = u[0] * knuckle_len[i] + v[0] * stack[i]
        y = u[1] * knuckle_len[i] + v[1] * stack[i]
        base = 5 + i * 4
        pts[base] = (x, y, 0.0)
        cum = alpha
        for k, flex in enumerate((pose.mcp[i], pose.pip[i], pose.dip[i])):
            cum += flex
            d = _dir_from_angle(cum)
            x += d[0] * _SEG[i][k]
            y += d[1] * _SEG[i][k]
            pts[base + 1 + k] = (x, y, 0.0)

    cmc = (u[0] * 0.22 + v[0] * 0.16, u[1] * 0.22 + v[1] * 0.16)
    x, y = cmc
    pts[1] = (x, y, 0.0)
    ang = alpha + 14.0 - pose.thumb_abd * 0.3
    for k in range(3):
        ang += pose.thumb_flex * (35.0, 40.0, 30.0)[k]
        d = _dir_from_angle(ang)
        x += d[0] * _THUMB_SEG[k]
        y += d[1] * _THUMB_SEG[k]
        pts[2 + k] = (x, y, 0.0)

    def at(a, b):
        return (u[0] * a + v[0] * b, u[1] * a + v[1] * b)

    palm = [at(0.0, -0.20), at(0.55, -0.17), at(1.0, -0.14), at(1.04, 0.10),
            at(0.92, 0.22), at(0.45, 0.30), at(0.0, 0.22)]
    fu = _dir_from_angle(pose.base_angle)
    fv = _dir_from_angle(pose.base_angle + 90.0)

    def fa(a, b):
        return (fu[0] * a + fv[0] * b, fu[1] * a + fv[1] * b)

    forearm = [fa(0.02, -0.18), fa(0.02, 0.22), fa(-1.15, 0.26), fa(-1.15, -0.22)]
    return pts, palm, forearm


def hand_points(pose: HandPose):
    return _side_points(pose) if pose.view == "side" else _front_points(pose)


# =============================================================================
# 3. LANDMARK OUTPUT (MediaPipe-compatible, normalised to a camera frame)
# =============================================================================
class _LM:
    __slots__ = ("x", "y", "z")

    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z


def pose_landmarks(pose: HandPose, frame=(1280, 720), center=(0.5, 0.62), palm_px=190.0):
    """Returns 21 landmark objects (x, y normalised to the frame like MediaPipe)."""
    pts, _, _ = hand_points(pose)
    fw, fh = frame
    cx, cy = center[0] * fw, center[1] * fh
    return [_LM((cx + p[0] * palm_px) / fw, (cy + p[1] * palm_px) / fh, p[2] * 0.1) for p in pts]


# =============================================================================
# 4. RENDERER (PIL, 2x supersampled cartoon hand)
# =============================================================================
SKIN = (247, 207, 178)
SKIN_BACK = (236, 188, 156)
OUTLINE = (176, 120, 92)
CREASE = (210, 150, 120)
NAIL = (255, 232, 226)
HL_FILL = (125, 192, 255)
HL_OUTLINE = (30, 110, 200)
FOREARM = (238, 196, 168)

_FINGER_W = 0.17
_THUMB_W = 0.19


def _all_points(pose: HandPose):
    pts, palm, forearm = hand_points(pose)
    return [(p[0], p[1]) for p in pts] + list(palm) + list(forearm)


def fit_box_for(poses: Iterable[HandPose], pad=0.16):
    """Bounding box covering several poses, so an animation never rescales."""
    xs, ys = [], []
    for p in poses:
        for q in _all_points(p):
            xs.append(q[0])
            ys.append(q[1])
    return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)


def render_hand(pose: HandPose, size=(420, 420), box=None, bg=None, ss=2):
    """Draws the pose and returns an RGBA PIL image of the given size."""
    from PIL import Image, ImageDraw

    W, H = size[0] * ss, size[1] * ss
    img = Image.new("RGBA", (W, H), bg if bg else (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    pts, palm, forearm = hand_points(pose)
    if box is None:
        box = fit_box_for([pose])
    bx0, by0, bx1, by1 = box
    scale = min(W / (bx1 - bx0), H / (by1 - by0))
    ox = (W - (bx1 - bx0) * scale) / 2 - bx0 * scale
    oy = (H - (by1 - by0) * scale) / 2 - by0 * scale

    def P(p):
        return (ox + p[0] * scale, oy + p[1] * scale)

    ow = max(2, int(0.025 * scale))

    def capsule(a, b, width, fill, outline, outline_pass):
        a, b = P(a), P(b)
        wpx = width * scale
        if outline_pass:
            wpx += 2 * ow
            col = outline
        else:
            col = fill
        d.line([a, b], fill=col, width=int(wpx))
        r = wpx / 2
        for c in (a, b):
            d.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], fill=col)

    back = pose.view == "front" and pose.back > 0.5
    skin = SKIN_BACK if back else SKIN

    # Forearm + rounded wrist joint (bridges forearm and palm when the wrist bends)
    d.polygon([P(p) for p in forearm], fill=FOREARM, outline=OUTLINE, width=ow)
    if pose.view == "side":
        wc, wr = P((0.0, 0.0)), 0.21 * scale
        d.ellipse([wc[0] - wr, wc[1] - wr, wc[0] + wr, wc[1] + wr], fill=FOREARM)

    def draw_finger(chain, width, idx):
        hl = idx in pose.highlight
        fill = HL_FILL if hl else skin
        outl = HL_OUTLINE if hl else OUTLINE
        segs = list(zip(chain[:-1], chain[1:]))
        for a, b in segs:
            capsule(a, b, width, fill, outl, True)
        for a, b in segs:
            capsule(a, b, width, fill, outl, False)
        # joint creases
        for j in range(1, len(chain) - 1):
            a, b = chain[j - 1], chain[j + 1]
            dx, dy = b[0] - a[0], b[1] - a[1]
            n = math.hypot(dx, dy) or 1.0
            px, py = -dy / n * width * 0.32, dx / n * width * 0.32
            c = chain[j]
            d.line([P((c[0] - px, c[1] - py)), P((c[0] + px, c[1] + py))],
                   fill=HL_OUTLINE if hl else CREASE, width=max(1, ow - 1))
        if back:
            tip, prev = chain[-1], chain[-2]
            dx, dy = tip[0] - prev[0], tip[1] - prev[1]
            n = math.hypot(dx, dy) or 1.0
            c = (tip[0] - dx / n * width * 0.35, tip[1] - dy / n * width * 0.35)
            r = width * 0.30 * scale
            cc = P(c)
            d.ellipse([cc[0] - r, cc[1] - r, cc[0] + r, cc[1] + r], fill=NAIL, outline=CREASE)

    fingers = [[(pts[b + k][0], pts[b + k][1]) for k in range(4)] for b in (5, 9, 13, 17)]
    thumb = [(pts[k][0], pts[k][1]) for k in range(1, 5)]

    if pose.view == "side":
        # Far fingers first (pinky) so the index finger sits in front.
        for i in (3, 2, 1):
            draw_finger(fingers[i], _FINGER_W, i + 1)
        d.polygon([P(p) for p in palm], fill=skin, outline=OUTLINE, width=ow)
        draw_finger(fingers[0], _FINGER_W, 1)
        draw_finger(thumb, _THUMB_W, 0)
    else:
        d.polygon([P(p) for p in palm], fill=skin, outline=OUTLINE, width=ow)
        if back:
            draw_finger(thumb, _THUMB_W, 0)
        for i in range(4):
            draw_finger(fingers[i], _FINGER_W, i + 1)
        if not back:
            draw_finger(thumb, _THUMB_W, 0)

    if ss != 1:
        img = img.reduce(ss)       # exact box filter for the supersampling factor (much faster than LANCZOS)
    return img


# =============================================================================
# 5. EXERCISE POSE LIBRARY (one pose per exercise step)
# =============================================================================
OPEN = HandPose(mcp=(4, 4, 4, 4), pip=(4, 4, 4, 4), dip=(2, 2, 2, 2), spread=20, thumb_abd=60)
FIST = HandPose(mcp=(85, 88, 88, 85), pip=(100, 100, 100, 100), dip=(60, 60, 60, 60),
                spread=0, thumb_abd=15, thumb_flex=0.8)
TOGETHER = HandPose(mcp=(3, 3, 3, 3), pip=(3, 3, 3, 3), dip=(2, 2, 2, 2), spread=-3, thumb_abd=18)
SPREAD = HandPose(mcp=(3, 3, 3, 3), pip=(3, 3, 3, 3), dip=(2, 2, 2, 2), spread=19, thumb_abd=55,
                  highlight=(1, 2, 3, 4))
_TAP_BASE = HandPose(mcp=(10, 10, 10, 10), pip=(10, 10, 10, 10), dip=(5, 5, 5, 5), spread=7, thumb_abd=35)
_PIANO_REST = HandPose(mcp=(40, 40, 40, 40), pip=(70, 70, 70, 70), dip=(30, 30, 30, 30), spread=4, thumb_abd=30)


def _tap(i):
    t = [0, 0, 0, 0]
    t[i] = 1
    return replace(_TAP_BASE, touch=tuple(t), highlight=(0, i + 1))


def _piano(i):
    m, p, dd = list(_PIANO_REST.mcp), list(_PIANO_REST.pip), list(_PIANO_REST.dip)
    m[i], p[i], dd[i] = 0, 3, 0
    return replace(_PIANO_REST, mcp=tuple(m), pip=tuple(p), dip=tuple(dd), highlight=(i + 1,))


HITCH_FIST = replace(FIST, thumb_abd=10, thumb_flex=0.9)
HITCH_OUT = replace(FIST, thumb_abd=72, thumb_flex=0.0, highlight=(0,))
WIPE_LEFT = replace(OPEN, spread=6, tilt=-28)
WIPE_RIGHT = replace(OPEN, spread=6, tilt=28)
PALM_UP = replace(OPEN, spread=6)
PALM_DOWN = replace(OPEN, spread=6, back=1.0)

_SIDE_FLAT = HandPose(view="side", mcp=(0, 0, 0, 0), pip=(2, 2, 2, 2), dip=(2, 2, 2, 2),
                      thumb_abd=0, thumb_flex=0.15, base_angle=-90)
SIDE_FIST = replace(_SIDE_FLAT, mcp=(85, 88, 88, 85), pip=(100, 100, 100, 100), dip=(60, 60, 60, 60),
                    thumb_flex=0.7)
SIDE_L = replace(_SIDE_FLAT, mcp=(90, 90, 90, 90), pip=(0, 0, 0, 0), dip=(0, 0, 0, 0),
                 highlight=(1, 2, 3, 4))
SIDE_CLAW = replace(_SIDE_FLAT, mcp=(0, 0, 0, 0), pip=(95, 95, 95, 95), dip=(70, 70, 70, 70),
                    highlight=(1, 2, 3, 4))
WRIST_UP = replace(_SIDE_FLAT, base_angle=0, wrist_flex=-50)
WRIST_DOWN = replace(_SIDE_FLAT, base_angle=0, wrist_flex=50)

EXERCISE_POSES: dict[str, list[HandPose]] = {
    "SQUEEZE": [FIST, OPEN],
    "THUMB": [_tap(i) for i in range(4)],
    "WIPER": [WIPE_LEFT, WIPE_RIGHT],
    "FLIP": [PALM_UP, PALM_DOWN],
    "TABLETOP": [SIDE_FIST, SIDE_L],
    "SCISSOR": [TOGETHER, SPREAD],
    "HOOK": [_SIDE_FLAT, SIDE_CLAW],
    "WRIST": [WRIST_UP, WRIST_DOWN],
    "PIANO": [_piano(i) for i in range(4)],
    "HITCH": [HITCH_FIST, HITCH_OUT],
}
