"""
===============================================================================
NSC Medical Suite - Vision & Rendering Module (Optimised)
===============================================================================
Handles all computer vision tasks, AI model instantiation, kinematic smoothing,
and high-performance OpenCV skeleton rendering.

Key Components:
  1. MediaPipe Task Prewarming (Async)
  2. HandStabilizer (Digital Low-Pass Filter for Jitter Reduction)
  3. Anatomically Correct Skeleton Topology Constants
  4. draw_skeleton (Optimized OpenCV HUD Renderer)
===============================================================================
"""

from __future__ import annotations

import os
import math
import threading
import traceback
import urllib.request
from typing import Any

from utils import resource_path, _ensure_cv2, _ensure_np, Point3D


# =============================================================================
# 1. MEDIAPIPE AI INITIALIZATION & PREWARMING
# =============================================================================
_prewarm_done: threading.Event = threading.Event()
_detector_ready: threading.Event = threading.Event()
_prebuilt_detector: Any = None

_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
)

def _thread_import_basics() -> None:
    """Imports heavy libraries on a background thread to prevent UI freezing on boot."""
    try:
        _ensure_np()
        _ensure_cv2()
        from utils import _ensure_pil
        _ensure_pil()
    except Exception:
        pass
    _prewarm_done.set()

def _thread_build_detector() -> None:
    """Downloads (if necessary) and pre-builds the MediaPipe Hand Landmarker."""
    global _prebuilt_detector
    try:
        from utils import _ensure_mp
        _ensure_mp()
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        model_path = resource_path(os.path.join("assets", "hand_landmarker.task"))
        if not os.path.exists(model_path):
            os.makedirs(os.path.dirname(model_path), exist_ok=True)
            tmp = model_path + ".part"
            try:
                urllib.request.urlretrieve(_MODEL_URL, tmp)
                os.replace(tmp, model_path)
            except Exception:
                if os.path.exists(tmp):
                    os.remove(tmp)
                raise

        base_opts = mp_python.BaseOptions(model_asset_path=model_path)
        options = vision.HandLandmarkerOptions(
            base_options=base_opts,
            num_hands=1,
            min_hand_detection_confidence=0.50,
            min_hand_presence_confidence=0.50,
            min_tracking_confidence=0.50,
            running_mode=vision.RunningMode.IMAGE,
        )
        _prebuilt_detector = vision.HandLandmarker.create_from_options(options)
    except Exception:
        traceback.print_exc()
    _detector_ready.set()

def prewarm_libs() -> None:
    """Triggers the async loading of libraries and AI models."""
    threading.Thread(target=_thread_import_basics, daemon=True).start()
    threading.Thread(target=_thread_build_detector, daemon=True).start()


# =============================================================================
# 2. KINEMATIC STABILIZATION & INTERPOLATION
# =============================================================================
class HandStabilizer:
    """
    Applies a dynamic exponential moving average (EMA) to hand landmarks.
    Reduces physical jitter/vibration, specifically targeting the ring and pinky fingers.
    """
    __slots__ = ("hist", "_vel", "_np")

    _ALPHA_FAST = 0.88
    _ALPHA_SLOW = 0.30
    _VEL_THRESH = 0.006

    def __init__(self) -> None:
        self.hist = None
        self._vel = None
        self._np = None

    def stabilize(self, raw_lms: list) -> list:
        np = self._np or _ensure_np()
        self._np = np

        raw = np.array([[l.x, l.y, l.z] for l in raw_lms], dtype=np.float32)

        if self.hist is None:
            self.hist = raw.copy()
            self._vel = np.zeros_like(raw)
            return raw_lms

        # Calculate movement speed to determine base smoothing factor
        speed = np.linalg.norm(raw[:, :2] - self.hist[:, :2], axis=1)
        alpha = np.where(speed > self._VEL_THRESH, self._ALPHA_FAST, self._ALPHA_SLOW)

        # Vibration Fix: Aggressively smooth Ring (13-16) and Pinky (17-20) fingers
        vibration_indices = [13, 14, 15, 16, 17, 18, 19, 20]
        for idx in vibration_indices:
            alpha[idx] *= 0.6

        alpha = alpha[:, np.newaxis]

        # Apply exponential moving average
        prev = self.hist.copy()
        self.hist = self.hist * (1.0 - alpha) + raw * alpha
        self._vel = self.hist - prev

        h = self.hist
        return [Point3D(float(h[i, 0]), float(h[i, 1]), float(h[i, 2])) for i in range(21)]


class OcclusionInterpolator:
    """Provides fallback landmark positions if the hand is temporarily obscured."""
    _MAX_MISS = 6

    def __init__(self, stabilizer: HandStabilizer) -> None:
        self._stab = stabilizer
        self._missed = 0
        self._last_lms: list | None = None

    def feed(self, raw_lms: list | None) -> list | None:
        if raw_lms is not None:
            self._missed = 0
            smoothed = self._stab.stabilize(raw_lms)
            self._last_lms = smoothed
            return smoothed

        self._missed += 1
        if self._missed > self._MAX_MISS or self._last_lms is None:
            return None

        vel = self._stab._vel
        if vel is None:
            return self._last_lms

        # Decay velocity over time to prevent the hand from "flying away"
        decay = 0.75 ** self._missed
        pts: list[Point3D] = []
        for i, p in enumerate(self._last_lms):
            pts.append(Point3D(
                float(p.x + vel[i, 0] * decay),
                float(p.y + vel[i, 1] * decay),
                float(p.z + vel[i, 2] * decay),
            ))
        self._last_lms = pts
        return pts


# =============================================================================
# 3. ANATOMICAL SKELETON CONSTANTS
# =============================================================================
_PALM_CONNECTIONS = ((0, 1), (0, 5), (0, 17), (5, 9), (9, 13), (13, 17))

_FINGER_BONES = (
    ((1, 2),   (2, 3),   (3, 4)),    # Thumb
    ((5, 6),   (6, 7),   (7, 8)),    # Index
    ((9, 10),  (10, 11), (11, 12)),  # Middle
    ((13, 14), (14, 15), (15, 16)),  # Ring
    ((17, 18), (18, 19), (19, 20))   # Pinky
)

_FINGER_COLORS: tuple[tuple[int, int, int], ...] = (
    (255, 120, 80),  # Thumb  — Warm Orange
    (80, 255, 160),  # Index  — Teal-Green
    (80, 200, 255),  # Middle — Sky Blue
    (200, 80, 255),  # Ring   — Violet
    (255, 80, 200),  # Pinky  — Pink
)

_TIP_SET: frozenset[int] = frozenset({4, 8, 12, 16, 20})
_MCP_INDICES: tuple[int, ...] = (5, 9, 13, 17)

_GONIO_CACHE: dict[str, tuple[int, int]] = {}


# =============================================================================
# 4. OPENCV SKELETON RENDERER
# =============================================================================
def draw_skeleton(
        image,
        hand_lms: list | None,
        *,
        color: tuple[int, int, int] = (255, 255, 255),
        confidence: float = 1.0,
        draw_depth_cue: bool = True,
        angles: tuple[float, ...] | None = None,
) -> None:
    """
    Renders the 21-point hand skeleton onto a CV2 image array.
    Highly optimized: pre-calculates pixel coordinates to avoid redundant math.
    """
    if not hand_lms:
        return

    cv2 = _ensure_cv2()
    h, w = image.shape[:2]
    alpha = max(0.3, confidence)

    # Pre-calculation pass: convert normalized coordinates to pixels once
    px_pts = [(int(lm.x * w), int(lm.y * h)) for lm in hand_lms]

    if draw_depth_cue:
        # Pseudo-Z depth for thickness/color scaling
        depths = [max(0.5, min(1.0, 1.0 - (lm.z + 0.15) * 2.0)) for lm in hand_lms]
    else:
        depths = [1.0] * 21

    # ── 4.1 Draw Palm Connections ─────────────────────────────────
    for s, e in _PALM_CONNECTIONS:
        d = (depths[s] + depths[e]) * 0.5
        c = (int(color[0] * d * alpha), int(color[1] * d * alpha), int(color[2] * d * alpha))
        cv2.line(image, px_pts[s], px_pts[e], c, max(1, round(2 * d)), cv2.LINE_AA)

    # ── 4.2 Draw Finger Connections (Gradient) ────────────────────
    for fi, bones in enumerate(_FINGER_BONES):
        fc = _FINGER_COLORS[fi]
        for s, e in bones:
            d = (depths[s] + depths[e]) * 0.5
            c = (int(fc[0] * d * alpha), int(fc[1] * d * alpha), int(fc[2] * d * alpha))
            cv2.line(image, px_pts[s], px_pts[e], c, max(1, round(3 * d)), cv2.LINE_AA)

    # ── 4.3 Draw Joints ───────────────────────────────────────────
    for i, px in enumerate(px_pts):
        d = depths[i]
        is_tip = i in _TIP_SET
        r = max(3, round(7 * d)) if is_tip else max(2, round(5 * d))

        # Shadow outline
        cv2.circle(image, px, r + 1, (0, 0, 0), -1, cv2.LINE_AA)

        if draw_depth_cue and is_tip:
            c_joint = (0, int(200 * alpha), int(255 * d * alpha))
        else:
            c_joint = (int(200 * d * alpha), int(255 * d * alpha), int(200 * d * alpha))

        cv2.circle(image, px, r, c_joint, -1, cv2.LINE_AA)

    # ── 4.4 Goniometer HUD (Optional) ─────────────────────────────
    if angles is not None:
        _FONT, _SCALE, _THICK = cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1
        for i, angle_rad in enumerate(angles):
            if i >= len(_MCP_INDICES):
                break

            text = f"{int(math.degrees(angle_rad))}\u00b0"

            if text not in _GONIO_CACHE:
                (tw, th), _ = cv2.getTextSize(text, _FONT, _SCALE, _THICK)
                _GONIO_CACHE[text] = (tw, th)
            else:
                tw, th = _GONIO_CACHE[text]

            px = px_pts[_MCP_INDICES[i]]
            bx1 = (px[0] - 5, px[1] - 30)
            bx2 = (px[0] + tw + 5, px[1] - 30 + th + 10)

            # Draw label background and border
            cv2.rectangle(image, bx1, bx2, (20, 30, 45), -1)
            cv2.rectangle(image, bx1, bx2, (0, 212, 170), 1)
            cv2.putText(image, text, (px[0], px[1] - 20), _FONT, _SCALE, (255, 255, 255), _THICK, cv2.LINE_AA)

# Backward-compat alias
draw_landmarks = draw_skeleton
