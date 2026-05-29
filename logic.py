"""
===============================================================================
CerebroMotion Clinical Suite - Core AI & Logic Engine (v3 - Field Test Fixes)
===============================================================================
v3 fixes based on live testing:
  - HallucinationValidator: removed w/h ratio check entirely — it rejects
    side-on hands (Flip, Wrist, Thumb) where the hand is naturally narrow.
    Also removed the jump check that was resetting state on fast movements.
  - _score_squeeze_closed: raised sigmoid center from 0.62→0.75 so an OPEN
    hand no longer scores >70. Previously an open hand scored ~65% as "closed"
    blocking the state machine from ever registering the fist step.
  - _score_squeeze_open: loosened spread requirement (center 0.90→0.70) since
    patients post-stroke may not spread fingers wide but hand IS open.
  - _score_starfish_relax: was requiring low spread which rejected a flat open
    hand. Now just checks that fingers are extended (low curl).
  - _score_wrist_up / _score_wrist_down: dy threshold was 0.30 — too high for
    a wrist bend done close to camera. Lowered to 0.18.
  - _score_flip: cross-product heuristic is unreliable for side-on hands.
    Replaced with a z-depth only model using wrist.z vs fingertip.z.
  - Thumb tap: loosened contact distance center from 0.32→0.45 — patients
    can't always achieve full fingertip contact.
  - KinematicAnalyzer.is_moving threshold lowered 0.007→0.006 to avoid
    rejecting slow deliberate movements by patients with limited mobility.
===============================================================================
"""

from __future__ import annotations

import math
import statistics
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import IntEnum
from typing import Any, NamedTuple


# =============================================================================
# 1. MATH PRIMITIVES & ENUMS
# =============================================================================
def _d2(a: Any, b: Any) -> float:
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2)


def _d3(a: Any, b: Any) -> float:
    az = getattr(a, 'z', 0.0)
    bz = getattr(b, 'z', 0.0)
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (az - bz) ** 2)


def _sigmoid(val: float, center: float, steep: float = 12.0) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-steep * (val - center)))
    except OverflowError:
        return 0.0 if val < center else 1.0


def _nail(tip: Any, dip: Any, f: float = 0.30) -> Any:
    """Extrapolates the position of the fingernail beyond the fingertip."""
    class _P:
        x = tip.x + (tip.x - dip.x) * f
        y = tip.y + (tip.y - dip.y) * f
    return _P()


def _pip_angle(lms: list, mcp: int, pip: int, tip: int) -> float:
    """
    Angle AT the PIP joint via cosine rule.
    Straight finger  → angle near 170–180°
    Fully curled     → angle near 50–80°
    """
    ab = _d2(lms[mcp], lms[pip])
    bc = _d2(lms[pip], lms[tip])
    ac = _d2(lms[mcp], lms[tip])
    denom = 2.0 * ab * bc
    if denom < 1e-9:
        return 170.0  # default to straight if degenerate
    cos_a = (ab * ab + bc * bc - ac * ac) / denom
    return math.degrees(math.acos(max(-1.0, min(1.0, cos_a))))

class LI(IntEnum):
    WRIST = 0; THUMB_CMC = 1; THUMB_MCP = 2; THUMB_IP = 3; THUMB_TIP = 4
    INDEX_MCP = 5;  INDEX_PIP = 6;  INDEX_DIP = 7;  INDEX_TIP = 8
    MIDDLE_MCP = 9; MIDDLE_PIP = 10; MIDDLE_DIP = 11; MIDDLE_TIP = 12
    RING_MCP = 13;  RING_PIP = 14;  RING_DIP = 15;  RING_TIP = 16
    PINKY_MCP = 17; PINKY_PIP = 18; PINKY_DIP = 19; PINKY_TIP = 20


# =============================================================================
# 2. ANTI-HALLUCINATION VALIDATOR
# =============================================================================
class HallucinationValidator:
    """
    Minimal validator — only rejects genuinely impossible detections.
    Removed w/h ratio check (rejected side-on hands for Flip/Wrist/Thumb).
    Removed jump check (was resetting on fast patient movements).
    Kept: landmark count, palm size bounds, MCP width sanity check.
    """
    _MIN_PALM = 0.03   # slightly lower to catch small/distant hands
    _MAX_PALM = 0.90

    def __init__(self) -> None:
        pass

    def is_valid(self, lms: list) -> bool:
        if not lms or len(lms) < 21:
            return False
        palm_size = _d2(lms[LI.WRIST], lms[LI.MIDDLE_MCP])
        if palm_size < self._MIN_PALM or palm_size > self._MAX_PALM:
            return False
        # MCP row must have some width — catches truly degenerate detections
        mcp_span = _d2(lms[LI.INDEX_MCP], lms[LI.PINKY_MCP])
        if mcp_span < palm_size * 0.04:
            return False
        return True

    def reset(self) -> None:
        pass


# =============================================================================
# 3. SPATIAL GEOMETRY
# =============================================================================
_FINGER_TRIPLETS = [
    (LI.INDEX_MCP,  LI.INDEX_PIP,  LI.INDEX_TIP),
    (LI.MIDDLE_MCP, LI.MIDDLE_PIP, LI.MIDDLE_TIP),
    (LI.RING_MCP,   LI.RING_PIP,   LI.RING_TIP),
    (LI.PINKY_MCP,  LI.PINKY_PIP,  LI.PINKY_TIP),
]

# Calibrated angle thresholds:
#   fully straight finger PIP ≈ 160–180°  →  curl = 0.0
#   fully curled fist PIP     ≈  50–80°   →  curl = 1.0
_STRAIGHT_ANGLE = 155.0
_CURL_ANGLE     = 80.0    # lowered from 120 — 120 was too high, many mid-curl states got curl=1.0 prematurely


@dataclass(slots=True, frozen=True)
class HandGeometry:
    """
    finger_curl : (index,middle,ring,pinky) — 0.0=straight, 1.0=fully curled
    finger_ext  : inverse of finger_curl
    pip_angles  : raw PIP angles in degrees (index→pinky)
    thumb_ext   : 0=tucked, 1=fully abducted
    spread_ratio: index_tip to pinky_tip distance / palm_size
    """
    palm_size: float
    spread_ratio: float
    palm_facing_camera: bool
    finger_curl: tuple
    finger_ext: tuple
    thumb_ext: float
    pip_angles: tuple
    nail_distances: dict

    @staticmethod
    def from_landmarks(lms: list) -> 'HandGeometry':
        palm_size = _d2(lms[LI.WRIST], lms[LI.MIDDLE_MCP]) or 0.001

        pip_angles_raw = []
        finger_curl = []
        finger_ext  = []
        for mcp, pip, tip in _FINGER_TRIPLETS:
            angle = _pip_angle(lms, mcp, pip, tip)
            pip_angles_raw.append(angle)
            # curl: 1.0 when angle=_CURL_ANGLE, 0.0 when angle=_STRAIGHT_ANGLE
            curl = 1.0 - max(0.0, min(1.0,
                (angle - _CURL_ANGLE) / (_STRAIGHT_ANGLE - _CURL_ANGLE)))
            finger_curl.append(curl)
            finger_ext.append(1.0 - curl)

        # Thumb: distance from thumb tip to pinky MCP / (2 * palm_size)
        thumb_ext = max(0.0, min(1.0,
            _d2(lms[LI.THUMB_TIP], lms[LI.PINKY_MCP]) / (palm_size * 2.2)))

        spread_ratio = _d2(lms[LI.INDEX_TIP], lms[LI.PINKY_TIP]) / palm_size

        # Palm facing: cross-product of index_mcp→wrist and pinky_mcp→wrist
        cross_z = ((lms[LI.INDEX_MCP].x - lms[LI.WRIST].x) *
                   (lms[LI.PINKY_MCP].y - lms[LI.WRIST].y) -
                   (lms[LI.INDEX_MCP].y - lms[LI.WRIST].y) *
                   (lms[LI.PINKY_MCP].x - lms[LI.WRIST].x))

        # Push the points 30% outward past the tip to simulate the actual nail/skin boundary
        thumb_nail = _nail(lms[LI.THUMB_TIP], lms[LI.THUMB_IP], f=0.3)
        tips_and_dips = [
            (LI.INDEX_TIP, LI.INDEX_DIP),
            (LI.MIDDLE_TIP, LI.MIDDLE_DIP),
            (LI.RING_TIP, LI.RING_DIP),
            (LI.PINKY_TIP, LI.PINKY_DIP)
        ]

        nail_d = {}
        for tip, dip in tips_and_dips:
            finger_nail = _nail(lms[tip], lms[dip], f=0.3)
            nail_d[(LI.THUMB_TIP, tip)] = _d2(thumb_nail, finger_nail) / palm_size

        return HandGeometry(
            palm_size=palm_size,
            spread_ratio=spread_ratio,
            palm_facing_camera=(cross_z > 0),
            finger_curl=tuple(finger_curl),
            finger_ext=tuple(finger_ext),
            thumb_ext=thumb_ext,
            pip_angles=tuple(pip_angles_raw),
            nail_distances=nail_d,
        )


# =============================================================================
# 4. GESTURE SCORING
# =============================================================================
class GestureScore(NamedTuple):
    accuracy: int


# ── 4.1  Open / Close Fist ──────────────────────────────────────────────────

def _score_squeeze_closed(geo: HandGeometry) -> GestureScore:
    """
    Full fist. Requires ALL four fingers deeply curled.
    v3: center raised 0.62→0.75 so an open hand (curl≈0.1–0.3) scores LOW.
    Previously open hands were scoring ~60–65% which was above the 70% trigger.
    """
    avg_curl = statistics.mean(geo.finger_curl)
    score = _sigmoid(avg_curl, 0.75, 16.0)
    return GestureScore(int(score * 100))


def _score_squeeze_open(geo: HandGeometry) -> GestureScore:
    """
    Open hand. Three signals:
      1. Mean PIP angle large (fingers straight)
      2. Mean extension high
      3. Spread present — loosened center 0.90→0.70 for patients with limited spread
    v3: spread threshold lowered so a flat but not-spread hand still scores well.
    """
    mean_angle = statistics.mean(geo.pip_angles)
    s1 = _sigmoid(mean_angle, 140.0, 0.10)   # angle > 140° = extended

    mean_ext = statistics.mean(geo.finger_ext)
    s2 = _sigmoid(mean_ext, 0.45, 10.0)

    # Loosened: spread_ratio > 0.70 (was 0.90) — patients may not fully spread
    s3 = _sigmoid(geo.spread_ratio, 0.70, 8.0)

    return GestureScore(int(s1 * s2 * s3 * 100))


# ── 4.2  Thumb Taps ─────────────────────────────────────────────────────────

def _score_thumb_tap(geo: HandGeometry, finger_idx: int) -> GestureScore:
    tips = [LI.INDEX_TIP, LI.MIDDLE_TIP, LI.RING_TIP, LI.PINKY_TIP]
    target_key = (LI.THUMB_TIP, tips[finger_idx])

    # Get distance using our newly extrapolated "nail" points
    target_dist = geo.nail_distances.get(target_key, 1.0)

    # Distance < 0.35 palm-lengths = contact
    contact_score = 1.0 - _sigmoid(target_dist, 0.35, 16.0)

    # Isolation: Ensure we aren't just mashing all fingers together into a fist
    other_dists = [
        geo.nail_distances.get((LI.THUMB_TIP, tips[i]), 1.0)
        for i in range(4) if i != finger_idx
    ]
    min_other = min(other_dists) if other_dists else 1.0

    # As long as the target finger is noticeably closer to the thumb than the others, it passes.
    ratio = target_dist / (min_other + 0.001)
    isolation = 1.0 - _sigmoid(ratio, 0.85, 12.0)

    return GestureScore(int(contact_score * isolation * 100))


# ── 4.3  Hand Wiper ─────────────────────────────────────────────────────────

def _score_wiper_left(geo: HandGeometry, lms: list) -> GestureScore:
    """
    MCP centroid deviated LEFT of wrist in screen space.
    Hand must be reasonably extended.
    """
    centroid_x = (lms[LI.INDEX_MCP].x + lms[LI.MIDDLE_MCP].x +
                  lms[LI.RING_MCP].x  + lms[LI.PINKY_MCP].x) / 4.0
    deviation  = centroid_x - lms[LI.WRIST].x   # negative = left
    dev_score  = _sigmoid(-deviation, 0.03, 80.0)
    ext_score  = _sigmoid(statistics.mean(geo.finger_ext), 0.30, 8.0)
    return GestureScore(int(dev_score * ext_score * 100))


def _score_wiper_right(geo: HandGeometry, lms: list) -> GestureScore:
    centroid_x = (lms[LI.INDEX_MCP].x + lms[LI.MIDDLE_MCP].x +
                  lms[LI.RING_MCP].x  + lms[LI.PINKY_MCP].x) / 4.0
    deviation  = centroid_x - lms[LI.WRIST].x   # positive = right
    dev_score  = _sigmoid(deviation, 0.03, 80.0)
    ext_score  = _sigmoid(statistics.mean(geo.finger_ext), 0.30, 8.0)
    return GestureScore(int(dev_score * ext_score * 100))


# ── 4.4  Palm Up / Down (Flip) ──────────────────────────────────────────────

def _score_flip(geo: HandGeometry, lms: list, target_facing: bool) -> GestureScore:
    """
    Calculates Palm Up / Palm Down using 2D geometric orientation.
    Removed Z-depth entirely because single-camera depth estimation is too noisy.
    """
    # 1. Ensure the hand is relatively flat/open
    mean_ext = statistics.mean(geo.finger_ext)
    flatness_score = _sigmoid(mean_ext, 0.45, 10.0)

    # 2. Check if the palm direction matches the current step
    # (Index and Pinky swapping sides triggers this)
    facing_match = (geo.palm_facing_camera == target_facing)

    # If the orientation matches, score is based on how flat the hand is.
    final_score = flatness_score if facing_match else 0.0

    return GestureScore(int(final_score * 100))


# ── 4.5  Tabletop / L-Shape (Replaces Starfish) ─────────────────────────────

def _score_tabletop_fist(geo: HandGeometry) -> GestureScore:
    """Starting position: Full fist."""
    avg_curl = statistics.mean(geo.finger_curl)
    score = _sigmoid(avg_curl, 0.75, 16.0)
    return GestureScore(int(score * 100))

def _score_tabletop_flex(geo: HandGeometry, lms: list) -> GestureScore:
    """Fingers remain straight, but the main MCP knuckles are bent ~90 degrees."""
    # 1. Fingers must be straight (PIP joints NOT curled)
    mean_ext = statistics.mean(geo.finger_ext)
    ext_score = _sigmoid(mean_ext, 0.55, 12.0)

    # 2. Measure the bend at the main knuckle (Wrist -> MCP -> PIP)
    angles = []
    for mcp, pip in [(LI.INDEX_MCP, LI.INDEX_PIP), (LI.MIDDLE_MCP, LI.MIDDLE_PIP),
                     (LI.RING_MCP, LI.RING_PIP), (LI.PINKY_MCP, LI.PINKY_PIP)]:
        ab = _d2(lms[LI.WRIST], lms[mcp])
        bc = _d2(lms[mcp], lms[pip])
        ac = _d2(lms[LI.WRIST], lms[pip])
        denom = 2.0 * ab * bc
        if denom > 1e-6:
            cos_a = (ab * ab + bc * bc - ac * ac) / denom
            angles.append(math.degrees(math.acos(max(-1.0, min(1.0, cos_a)))))

    mean_mcp_angle = statistics.mean(angles) if angles else 180.0

    # A flat hand is ~180°. A Tabletop bend is ~90-110°.
    # Score goes to 100% as the angle drops below 130°.
    mcp_score = 1.0 - _sigmoid(mean_mcp_angle, 125.0, 0.08)

    return GestureScore(int(ext_score * mcp_score * 100))


# ── 4.6  Finger Spread / Scissor ────────────────────────────────────────────

def _score_scissor_closed(geo: HandGeometry) -> GestureScore:
    """Fingers together: extended but NOT spread."""
    mean_ext = statistics.mean(geo.finger_ext)
    ext_ok   = _sigmoid(mean_ext, 0.40, 10.0)
    together = 1.0 - _sigmoid(geo.spread_ratio, 1.00, 12.0)
    return GestureScore(int(ext_ok * together * 100))


def _score_scissor(geo: HandGeometry) -> GestureScore:
    """Fingers spread wide."""
    mean_ext  = statistics.mean(geo.finger_ext)
    ext_score = _sigmoid(mean_ext, 0.55, 10.0)
    spr_score = _sigmoid(geo.spread_ratio, 1.25, 12.0)
    return GestureScore(int(ext_score * spr_score * 100))


# ── 4.7  The Claw / Hook ────────────────────────────────────────────────────

def _score_hook_flat(geo: HandGeometry) -> GestureScore:
    """Starting flat position: all fingers straight."""
    mean_angle = statistics.mean(geo.pip_angles)
    return GestureScore(int(_sigmoid(mean_angle, 140.0, 0.10) * 100))


def _score_hook(geo: HandGeometry, lms: list) -> GestureScore:
    """
    Claw: PIP joints curled, MCP joints still raised.
    Signal 1: PIP curl present
    Signal 2: MCP distance from wrist (knuckles still up)
    Signal 3: PIP angle < 130° on middle finger (direct curl confirm)
    """
    mean_pip_curl = statistics.mean(geo.finger_curl)
    pip_score     = _sigmoid(mean_pip_curl, 0.45, 12.0)

    mcp_raise = _d2(lms[LI.MIDDLE_MCP], lms[LI.WRIST]) / geo.palm_size
    mcp_score = _sigmoid(mcp_raise, 0.80, 8.0)

    mid_pip_ang   = geo.pip_angles[1]
    curl_confirm  = 1.0 - _sigmoid(mid_pip_ang, 130.0, 0.08)

    return GestureScore(int(pip_score * mcp_score * curl_confirm * 100))


# ── 4.8  Wrist Bend ─────────────────────────────────────────────────────────

def _score_wrist_up(geo: HandGeometry, lms: list) -> GestureScore:
    """
    Wrist bent UP (extension): MCP row is above the wrist in the image.
    v3: threshold lowered 0.30→0.18 — exercises are done close to camera
    so the pixel delta is smaller than expected.
    Also added a secondary angle: wrist-to-MCP vector angle vs vertical.
    """
    # Primary: normalised y-delta (wrist.y > middle_mcp.y = wrist below knuckles = wrist up)
    dy = (lms[LI.WRIST].y - lms[LI.MIDDLE_MCP].y) / geo.palm_size
    dy_score = _sigmoid(dy, 0.18, 10.0)

    # Secondary: angle of wrist→middle_mcp vector vs horizontal
    dx_vec = lms[LI.MIDDLE_MCP].x - lms[LI.WRIST].x
    dy_vec = lms[LI.MIDDLE_MCP].y - lms[LI.WRIST].y
    angle  = math.degrees(math.atan2(-dy_vec, abs(dx_vec) + 1e-6))  # positive = MCP above wrist
    ang_score = _sigmoid(angle, 15.0, 0.12)

    return GestureScore(int(max(dy_score, ang_score * 0.8) * 100))


def _score_wrist_down(geo: HandGeometry, lms: list) -> GestureScore:
    """Wrist bent DOWN (flexion): MCP row is below the wrist."""
    dy = (lms[LI.MIDDLE_MCP].y - lms[LI.WRIST].y) / geo.palm_size
    dy_score = _sigmoid(dy, 0.18, 10.0)

    dx_vec = lms[LI.MIDDLE_MCP].x - lms[LI.WRIST].x
    dy_vec = lms[LI.MIDDLE_MCP].y - lms[LI.WRIST].y
    angle  = math.degrees(math.atan2(dy_vec, abs(dx_vec) + 1e-6))
    ang_score = _sigmoid(angle, 15.0, 0.12)

    return GestureScore(int(max(dy_score, ang_score * 0.8) * 100))


# ── 4.9  Piano Fingers ──────────────────────────────────────────────────────

def _score_piano(geo: HandGeometry, finger_idx: int) -> GestureScore:
    """
    Lift ONE finger while others stay flat.
    finger_idx: 0=index, 1=middle, 2=ring, 3=pinky
    Uses PIP angle directly: target should have HIGH angle (extended),
    others should have LOW angle (flat on surface).
    """
    target_pip = geo.pip_angles[finger_idx]
    others_pip = [geo.pip_angles[i] for i in range(4) if i != finger_idx]
    avg_other  = statistics.mean(others_pip)

    # Target should be extended (high angle)
    lift_score = _sigmoid(target_pip, 145.0, 0.10)

    # Others should be flat (lower angle than target)
    flat_score = 1.0 - _sigmoid(avg_other, 150.0, 0.08)

    # Delta: target PIP angle clearly higher than others
    delta_score = _sigmoid(target_pip - avg_other, 20.0, 0.10)

    return GestureScore(int(lift_score * flat_score * delta_score * 100))


# ── 4.10  Hitchhiker ────────────────────────────────────────────────────────

def _score_hitchhiker_fist(geo: HandGeometry) -> GestureScore:
    """Fist with thumb tucked in."""
    fist_score = _score_squeeze_closed(geo).accuracy / 100.0
    thumb_down = 1.0 - _sigmoid(geo.thumb_ext, 0.50, 10.0)
    return GestureScore(int(fist_score * thumb_down * 100))


def _score_hitchhiker(geo: HandGeometry) -> GestureScore:
    """Thumbs-up: fingers curled, thumb extended."""
    fist_score  = _sigmoid(statistics.mean(geo.finger_curl), 0.65, 14.0)
    thumb_score = _sigmoid(geo.thumb_ext, 0.60, 12.0)
    return GestureScore(int(fist_score * thumb_score * 100))


# =============================================================================
# 5. MASTER SCORING ROUTER
# =============================================================================

def get_movement_accuracy(
    exercise_name: str,
    current_step: int,
    raised_fingers: int,
    lms: list | None = None,
) -> int:
    if not lms:
        return 0
    geo = HandGeometry.from_landmarks(lms)

    if exercise_name == "SQUEEZE":
        return (_score_squeeze_closed(geo) if current_step == 0
                else _score_squeeze_open(geo)).accuracy

    elif exercise_name == "THUMB":
        return _score_thumb_tap(geo, current_step).accuracy

    elif exercise_name == "WIPER":
        return (_score_wiper_left(geo, lms) if current_step == 0
                else _score_wiper_right(geo, lms)).accuracy

    elif exercise_name == "FLIP":
        # step 0 = palm facing camera (palm up), step 1 = dorsum facing (palm down)
        return _score_flip(geo, lms, target_facing=(current_step == 0)).accuracy

    elif exercise_name == "TABLETOP":
        return (_score_tabletop_fist(geo) if current_step == 0
                else _score_tabletop_flex(geo, lms)).accuracy

    elif exercise_name == "SCISSOR":
        return (_score_scissor_closed(geo) if current_step == 0
                else _score_scissor(geo)).accuracy

    elif exercise_name == "HOOK":
        return (_score_hook_flat(geo) if current_step == 0
                else _score_hook(geo, lms)).accuracy

    elif exercise_name == "WRIST":
        return (_score_wrist_up(geo, lms) if current_step == 0
                else _score_wrist_down(geo, lms)).accuracy

    elif exercise_name == "PIANO":
        return _score_piano(geo, current_step).accuracy

    elif exercise_name == "HITCH":
        return (_score_hitchhiker_fist(geo) if current_step == 0
                else _score_hitchhiker(geo)).accuracy

    return 80


# =============================================================================
# 6. KINEMATIC VELOCITY TRACKING
# =============================================================================
@dataclass
class KinematicAnalyzer:
    window: int = 8
    _buf: deque = field(default_factory=lambda: deque(maxlen=8))

    def update(self, lms: list) -> None:
        self._buf.append([(l.x, l.y) for l in lms])

    def velocity(self) -> float:
        if len(self._buf) < 2:
            return 0.0
        s = [
            (sum(p[0] for p in f) / len(f), sum(p[1] for p in f) / len(f))
            for f in self._buf
        ]
        return statistics.mean(
            math.sqrt((s[i][0] - s[i-1][0])**2 + (s[i][1] - s[i-1][1])**2)
            for i in range(1, len(s))
        )

    def is_moving(self, threshold: float = 0.006) -> bool:
        return self.velocity() > threshold

    def motion_label(self) -> str:
        return "moving" if self.is_moving() else "still"


# =============================================================================
# 7. CLINICAL COACHING ENGINE
# =============================================================================
@dataclass
class CoachStateMachine:
    _last_key: str = ""
    _frames: int = 999

    def get_feedback(
        self,
        exercise: str,
        step: int,
        geo: HandGeometry,
        kinematics: KinematicAnalyzer,
    ) -> tuple[str, str] | None:
        self._frames += 1

        if kinematics.is_moving():
            key, sev = "coach_hold_steady", "warn"
        elif exercise in ("SQUEEZE", "HOOK") and step == 0 and statistics.mean(geo.finger_curl) < 0.50:
            key, sev = "coach_close_more", "warn"
        elif exercise == "SQUEEZE" and step == 1 and statistics.mean(geo.finger_ext) < 0.45:
            key, sev = "coach_open_more", "warn"
        elif exercise in ("TABLETOP", "SCISSOR") and step == 1 and geo.spread_ratio < 1.05:
            key, sev = "coach_spread_more", "warn"
        elif exercise == "PIANO" and 0 <= step <= 3:
            target_ext = geo.finger_ext[step]
            key, sev = ("coach_lift_finger", "warn") if target_ext < 0.40 else ("coach_perfect", "good")
        elif exercise == "HITCH" and step == 1 and geo.thumb_ext < 0.45:
            key, sev = "coach_thumb_up", "warn"
        else:
            key, sev = "coach_perfect", "good"

        if key == self._last_key and self._frames < 12:
            return None
        self._last_key = key
        self._frames   = 0
        return key, sev


# =============================================================================
# 8. ADAPTIVE DIFFICULTY & XAI
# =============================================================================
def get_therapy_day() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def generate_clinical_insights(history: dict, lang: str = "EN") -> list[str]:
    if not history or len(history) < 2:
        return (["Awaiting more data. Recommend daily therapy."]
                if lang == "EN" else ["รอข้อมูลเพิ่มเติม แนะนำทำกายภาพทุกวัน"])

    today        = datetime.now()
    last_7_dates = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
    active_days  = 0
    total_sets   = 0
    recent_acc_list = []

    for d in last_7_dates:
        if d in history:
            day_data   = history[d]

            # PERFECTED SET SUMMATION LIST
            sets_today = sum(day_data.get(k, 0) for k in
                ["squeeze_sets","thumb_sets","wiper_sets","flip_sets","tabletop_sets",
                 "scissor_sets","hook_sets","wrist_sets","piano_sets","hitch_sets"])

            if sets_today > 0:
                active_days += 1
                total_sets  += sets_today

            # PERFECTED ACCURACY EXTRACTION LIST
            acc_vals = [day_data.get(k, 0) for k in
                ["squeeze_acc","thumb_acc","wiper_acc","flip_acc","tabletop_acc",
                 "scissor_acc","hook_acc","wrist_acc","piano_acc","hitch_acc"]
                if day_data.get(k, 0) > 0]

            if acc_vals:
                recent_acc_list.append(sum(acc_vals) / len(acc_vals))

    adherence_pct = (active_days / 7.0) * 100
    avg_acc       = sum(recent_acc_list) / len(recent_acc_list) if recent_acc_list else 0
    sorted_dates  = sorted(history.keys(), reverse=True)
    gaps = 0
    for i in range(len(sorted_dates) - 1):
        try:
            d1 = datetime.strptime(sorted_dates[i],   "%Y-%m-%d")
            d2 = datetime.strptime(sorted_dates[i+1], "%Y-%m-%d")
            if (d1 - d2).days > 1 and d1 >= today - timedelta(days=14):
                gaps += 1
        except Exception:
            pass

    insights = []
    if adherence_pct < 50:
        insights.append(f"Low adherence ({active_days}/7 days). Inconsistent practice limits neuroplastic recovery."
                        if lang == "EN" else f"ความสม่ำเสมอต่ำ ({active_days}/7 วัน)")
    elif total_sets < 15:
        insights.append(f"Low training volume ({total_sets} sets/week)."
                        if lang == "EN" else f"ปริมาณการฝึกต่ำ {total_sets} เซ็ต/สัปดาห์")
    else:
        insights.append(f"Good recovery: {total_sets} sets/week."
                        if lang == "EN" else f"ฝึกได้ดี: {total_sets} เซ็ต/สัปดาห์")

    if avg_acc >= 80:
        insights.append(f"Motor control is high ({avg_acc:.1f}%)."
                        if lang == "EN" else f"การควบคุมกล้ามเนื้อดี ({avg_acc:.1f}%)")
    elif avg_acc >= 50:
        insights.append(f"Moderate motor control ({avg_acc:.1f}%)."
                        if lang == "EN" else f"การควบคุมกล้ามเนื้อปานกลาง ({avg_acc:.1f}%)")
    elif active_days > 0:
        insights.append(f"Poor motor control ({avg_acc:.1f}%). Consider therapist review."
                        if lang == "EN" else f"การควบคุมกล้ามเนื้อต่ำ ({avg_acc:.1f}%)")

    if gaps >= 1 and active_days > 0 and adherence_pct < 80:
        insights.append("Irregular training pattern. Avoid skipping days."
                        if lang == "EN" else "พบรูปแบบฝึกไม่สม่ำเสมอ")

    latest_date = sorted_dates[0] if sorted_dates else None
    if latest_date:
        latest = history[latest_date]
        valid  = {k: v for k, v in latest.items() if "acc" in k and v > 0}
        if valid:
            wk = min(valid, key=valid.get)

            # PERFECTED DICTIONARY NAMES
            names_en = {"squeeze_acc": "Open/Close", "thumb_acc": "Thumb Taps", "wiper_acc": "Hand Wiper",
                        "flip_acc": "Palm Up/Down", "tabletop_acc": "L-Shape", "scissor_acc": "Finger Spread",
                        "hook_acc": "The Claw", "wrist_acc": "Wrist Bend", "piano_acc": "Piano Fingers",
                        "hitch_acc": "Hitchhiker"}
            names_th = {"squeeze_acc": "กำ/แบมือ", "thumb_acc": "แตะนิ้วโป้ง", "wiper_acc": "โบกมือ",
                        "flip_acc": "หงาย/คว่ำ", "tabletop_acc": "ทำตัว L", "scissor_acc": "กางนิ้ว",
                        "hook_acc": "ทำตะขอ", "wrist_acc": "พับข้อมือ", "piano_acc": "พรมนิ้ว",
                        "hitch_acc": "ชูนิ้วโป้ง"}

            n = names_th.get(wk, wk) if lang == "TH" else names_en.get(wk, wk)
            insights.append(f"Recommended focus: '{n}' ({valid[wk]:.0f}%)."
                            if lang == "EN" else f"ท่าที่ควรเน้น: '{n}' ({valid[wk]:.0f}%)")

    _, _, xai_reason = evaluate_adaptive_difficulty(history, False, lang)
    insights.append(xai_reason)
    return insights


def evaluate_adaptive_difficulty(
    history: dict,
    is_weak: bool = False,
    lang: str = "EN",
) -> tuple[int, dict, str]:
    s    = 1 if is_weak else 3

    # PERFECTED BASE GOALS
    base = {"squeeze":[s,20],"thumb":[s,20],"wiper":[s,15],"flip":[s,15], "tabletop":[s,15],"scissor":[s+1,15]
        ,"hook":[s,15],"wrist":[s,15],"piano":[s,20],"hitch":[s,10]}

    if not history:
        return (0, base,
                "AI Baseline: New patient profile created."
                if lang == "EN" else "AI Baseline: สร้างโปรไฟล์ผู้ป่วยใหม่")

    today    = datetime.now()
    last_7   = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
    past_days = sorted([d for d in last_7 if d in history])

    done, days = 0, 0
    for d in last_7:
        if d in history:
            # PERFECTED SUMMATION LOOP KEYS
            done += sum(history[d].get(k, 0) for k in
                ["squeeze_sets","thumb_sets","wiper_sets","flip_sets","tabletop_sets",
                 "scissor_sets","hook_sets","wrist_sets","piano_sets","hitch_sets"])
            days += 1

    score     = int(min(done / (days * 18) * 100, 100)) if days > 0 else 0
    new_goals = {}
    increased = decreased = False

    # PERFECTED EXTRACTION KEYS
    ex_keys = [("squeeze", "squeeze_sets", "squeeze_acc"), ("thumb", "thumb_sets", "thumb_acc"),
               ("wiper", "wiper_sets", "wiper_acc"), ("flip", "flip_sets", "flip_acc"),
               ("tabletop", "tabletop_sets", "tabletop_acc"), ("scissor", "scissor_sets", "scissor_acc"),
               ("hook", "hook_sets", "hook_acc"), ("wrist", "wrist_sets", "wrist_acc"),
               ("piano", "piano_sets", "piano_acc"), ("hitch", "hitch_sets", "hitch_acc")]

    for prefix, set_key, acc_key in ex_keys:
        target      = base[prefix][0]
        consec_good = consec_poor = 0
        for d in past_days:
            sets_done = history[d].get(set_key, 0)
            acc       = history[d].get(acc_key, 0)
            if sets_done == 0:
                consec_good = consec_poor = 0
                continue
            if sets_done >= target and acc >= 80:
                consec_good += 1; consec_poor = 0
            elif sets_done < target or acc < 50:
                consec_poor += 1; consec_good = 0
            else:
                consec_good = consec_poor = 0
            if consec_good >= 2:
                target = min(8, target + 1); consec_good = 0; increased = True
            if consec_poor >= 2:
                target = max(1, target - 1); consec_poor = 0; decreased = True
        new_goals[prefix] = [target, base[prefix][1]]

    if increased:
        reason = ("AI Adaptation: Goals increased due to high performance."
                  if lang == "EN" else "AI Adaptation: เพิ่มเป้าหมายเนื่องจากประสิทธิภาพสูง")
    elif decreased:
        reason = ("AI Adaptation: Goals reduced to prevent muscle fatigue."
                  if lang == "EN" else "AI Adaptation: ลดเป้าหมายเพื่อป้องกันกล้ามเนื้อล้า")
    else:
        reason = ("AI Adaptation: Goals maintained for consistency."
                  if lang == "EN" else "AI Adaptation: คงเป้าหมายเดิมเพื่อความสม่ำเสมอ")

    return score, new_goals, reason
