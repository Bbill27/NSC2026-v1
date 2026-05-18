"""
===============================================================================
NSC Medical Suite - Core AI & Logic Engine (Optimised)
===============================================================================
This module contains the mathematical heart of the rehabilitation system.
It handles 3D spatial geometry, kinematic smoothing, hallucination rejection,
gesture scoring via Sigmoid curves, and the Adaptive Difficulty (XAI) engine.
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
    """Calculates the 2D Euclidean distance between two landmarks."""
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2)


def _sigmoid(val: float, center: float, steep: float = 12.0) -> float:
    """Maps a physical measurement into a smooth 0.0-1.0 confidence score."""
    try:
        return 1.0 / (1.0 + math.exp(-steep * (val - center)))
    except OverflowError:
        return 0.0 if val < center else 1.0


def _nail(tip: Any, dip: Any, f: float = 0.32) -> Any:
    """Extrapolates the position of the fingernail beyond the fingertip."""

    class _P:
        x = tip.x + (tip.x - dip.x) * f
        y = tip.y + (tip.y - dip.y) * f

    return _P()


def _pip_angle(lms: list, mcp: int, pip: int, tip: int) -> float:
    """Calculates the angle AT the PIP joint in degrees using the Cosine rule."""
    ab = _d2(lms[mcp], lms[pip])
    bc = _d2(lms[pip], lms[tip])
    ac = _d2(lms[mcp], lms[tip])
    denom = 2.0 * ab * bc
    if denom < 1e-9:
        return 180.0
    return math.degrees(math.acos(max(-1.0, min(1.0, (ab * ab + bc * bc - ac * ac) / denom))))


class LI(IntEnum):
    """MediaPipe Hand Landmark Indices."""
    WRIST = 0;
    THUMB_CMC = 1;
    THUMB_MCP = 2;
    THUMB_IP = 3;
    THUMB_TIP = 4
    INDEX_MCP = 5;
    INDEX_PIP = 6;
    INDEX_DIP = 7;
    INDEX_TIP = 8
    MIDDLE_MCP = 9;
    MIDDLE_PIP = 10;
    MIDDLE_DIP = 11;
    MIDDLE_TIP = 12
    RING_MCP = 13;
    RING_PIP = 14;
    RING_DIP = 15;
    RING_TIP = 16
    PINKY_MCP = 17;
    PINKY_PIP = 18;
    PINKY_DIP = 19;
    PINKY_TIP = 20


# =============================================================================
# 2. ANTI-HALLUCINATION VALIDATOR
# =============================================================================
class HallucinationValidator:
    """Rejects MediaPipe detections that are geometrically implausible."""
    _MIN_PALM = 0.04
    _MAX_PALM = 0.85
    _MAX_JUMP = 0.45

    def __init__(self) -> None:
        self._prev_wrist = None

    def is_valid(self, lms: list) -> bool:
        if not lms or len(lms) < 21: return False
        palm_size = _d2(lms[LI.WRIST], lms[LI.MIDDLE_MCP])
        if palm_size < self._MIN_PALM or palm_size > self._MAX_PALM: return False
        tip_dist = _d2(lms[LI.MIDDLE_TIP], lms[LI.WRIST])
        mcp_dist = _d2(lms[LI.MIDDLE_MCP], lms[LI.WRIST])
        if tip_dist < mcp_dist * 0.8: return False
        finger_span = _d2(lms[LI.INDEX_TIP], lms[LI.PINKY_TIP])
        if finger_span < palm_size * 0.1: return False

        wrist = lms[LI.WRIST]
        if self._prev_wrist is not None:
            jump = math.hypot(wrist.x - self._prev_wrist[0], wrist.y - self._prev_wrist[1])
            if jump > self._MAX_JUMP:
                self._prev_wrist = None
                return False
        self._prev_wrist = (wrist.x, wrist.y)

        xs = [lm.x for lm in lms];
        ys = [lm.y for lm in lms]
        w = max(xs) - min(xs);
        h = max(ys) - min(ys)
        if h < 1e-6: return False
        ratio = w / h
        if ratio < 0.20 or ratio > 3.0: return False
        return True

    def reset(self) -> None:
        self._prev_wrist = None


# =============================================================================
# 3. SPATIAL GEOMETRY
# =============================================================================
@dataclass(slots=True, frozen=True)
class HandGeometry:
    """Immutable data structure representing the physical state of the hand."""
    palm_size: float
    spread_ratio: float
    raised_count: int
    palm_facing_camera: bool
    finger_extensions: tuple
    finger_angles: tuple
    nail_distances: dict

    @staticmethod
    def from_landmarks(lms: list) -> HandGeometry:
        palm_size = _d2(lms[LI.WRIST], lms[LI.MIDDLE_MCP]) or 0.001
        spread_ratio = _d2(lms[LI.THUMB_TIP], lms[LI.PINKY_TIP]) / palm_size

        tips = [LI.INDEX_TIP, LI.MIDDLE_TIP, LI.RING_TIP, LI.PINKY_TIP]
        mcps = [LI.INDEX_MCP, LI.MIDDLE_MCP, LI.RING_MCP, LI.PINKY_MCP]
        extensions = []

        for t, m in zip(tips, mcps):
            ratio = _d2(lms[t], lms[LI.WRIST]) / (_d2(lms[m], lms[LI.WRIST]) or 0.001)
            extensions.append(max(0.0, min(1.0, (ratio - 1.0) / 0.7)))

        thumb_ext = max(0.0, min(1.0, _d2(lms[LI.THUMB_TIP], lms[LI.PINKY_MCP]) / (palm_size * 2.0)))
        extensions.insert(0, thumb_ext)
        raised_count = sum(1 for e in extensions if e > 0.55)
        cross_z = ((lms[LI.INDEX_MCP].x - lms[LI.WRIST].x) * (lms[LI.PINKY_MCP].y - lms[LI.WRIST].y) -
                   (lms[LI.INDEX_MCP].y - lms[LI.WRIST].y) * (lms[LI.PINKY_MCP].x - lms[LI.WRIST].x))

        nail_d = {(LI.THUMB_TIP, tip): _d2(lms[LI.THUMB_TIP], lms[tip]) / palm_size for tip in tips}

        return HandGeometry(
            palm_size=palm_size, spread_ratio=spread_ratio, raised_count=raised_count,
            palm_facing_camera=(cross_z > 0), finger_extensions=tuple(extensions),
            finger_angles=tuple([0.0] * 5), nail_distances=nail_d
        )


# =============================================================================
# 4. GESTURE SCORING (AI Confidence Models)
# =============================================================================
class GestureScore(NamedTuple):
    accuracy: int


def _score_squeeze_closed(geo: HandGeometry) -> GestureScore:
    avg_ext = statistics.mean(geo.finger_extensions[1:])
    return GestureScore(int((1.0 - _sigmoid(avg_ext, 0.35, 12.0)) * 100))


def _score_squeeze_open(geo: HandGeometry) -> GestureScore:
    avg_ext = statistics.mean(geo.finger_extensions)
    return GestureScore(int(_sigmoid(avg_ext, 0.55, 10.0) * 100))


def _score_starfish(geo: HandGeometry) -> GestureScore:
    ext = _sigmoid(statistics.mean(geo.finger_extensions), 0.60, 10.0)
    sprd = _sigmoid(geo.spread_ratio, 1.15, 8.0)
    return GestureScore(int(ext * sprd * 100))


def _score_peace(geo: HandGeometry) -> GestureScore:
    up = _sigmoid((geo.finger_extensions[1] + geo.finger_extensions[2]) / 2.0, 0.35, 12.0)
    down = _sigmoid(1.0 - (geo.finger_extensions[3] + geo.finger_extensions[4]) / 2.0, 0.35, 12.0)
    return GestureScore(int(min(1.0, up * down * 1.05) * 100))


def _score_oring(geo: HandGeometry, lms: list) -> GestureScore:
    palm = geo.palm_size
    pip_ang = _pip_angle(lms, LI.INDEX_MCP, LI.INDEX_PIP, LI.INDEX_TIP)
    if pip_ang > 140.0: return GestureScore(0)

    n_th = _nail(lms[LI.THUMB_TIP], lms[LI.THUMB_IP])
    n_ix = _nail(lms[LI.INDEX_TIP], lms[LI.INDEX_DIP])
    nail_gap = math.hypot(n_th.x - n_ix.x, n_th.y - n_ix.y) / palm
    if nail_gap > 0.60: return GestureScore(0)

    pinch = 1.0 - _sigmoid(nail_gap, 0.30, 14.0)
    curl = 1.0 - _sigmoid(pip_ang, 90.0, 0.06)
    m_ext = _d2(lms[LI.MIDDLE_TIP], lms[LI.MIDDLE_MCP]) / palm
    r_ext = _d2(lms[LI.RING_TIP], lms[LI.RING_MCP]) / palm
    p_ext = _d2(lms[LI.PINKY_TIP], lms[LI.PINKY_MCP]) / palm
    ext = _sigmoid((m_ext + r_ext + p_ext) / 3.0, 0.65, 10.0)
    return GestureScore(int(min(1.0, pinch * curl * ext * 1.15) * 100))


def get_movement_accuracy(exercise_name: str, current_step: int, raised_fingers: int, lms: list | None = None) -> int:
    """Master Router: Directs the current exercise step to the correct scoring function."""
    if not lms: return 0
    geo = HandGeometry.from_landmarks(lms)
    if exercise_name == "SQUEEZE":
        return (_score_squeeze_closed(geo) if current_step == 0 else _score_squeeze_open(geo)).accuracy
    elif exercise_name == "THUMB":
        return int((1.0 - _sigmoid(min(geo.nail_distances.values()) if geo.nail_distances else 1.0, 0.45, 12.0)) * 100)
    elif exercise_name == "STARFISH":
        return (_score_squeeze_closed(geo) if current_step == 0 else _score_starfish(geo)).accuracy
    elif exercise_name == "PEACE":
        return (_score_squeeze_closed(geo) if current_step == 0 else _score_peace(geo)).accuracy
    elif exercise_name == "O_RING":
        return (_score_squeeze_closed(geo) if current_step == 0 else _score_oring(geo, lms)).accuracy
    elif exercise_name == "FLIP":
        return 100
    return 80


# =============================================================================
# 5. KINEMATIC VELOCITY TRACKING
# =============================================================================
@dataclass
class KinematicAnalyzer:
    """Tracks hand velocity over a rolling window to determine if the patient is steady."""
    window: int = 8
    _buf: deque = field(default_factory=lambda: deque(maxlen=8))

    def update(self, lms: list) -> None:
        self._buf.append([(l.x, l.y) for l in lms])

    def velocity(self) -> float:
        if len(self._buf) < 2: return 0.0
        s = [(sum(p[0] for p in f) / len(f), sum(p[1] for p in f) / len(f)) for f in self._buf]
        return statistics.mean(
            math.sqrt((s[i][0] - s[i - 1][0]) ** 2 + (s[i][1] - s[i - 1][1]) ** 2) for i in range(1, len(s)))

    def is_moving(self, threshold: float = 0.008) -> bool: return self.velocity() > threshold

    def motion_label(self) -> str: return "moving" if self.is_moving() else "still"


# =============================================================================
# 6. CLINICAL COACHING ENGINE
# =============================================================================
@dataclass
class CoachStateMachine:
    """Provides real-time clinical feedback based on kinematic and geometric state."""
    _last_key: str = ""
    _frames: int = 999

    def get_feedback(self, exercise: str, step: int, geo: HandGeometry, kinematics: KinematicAnalyzer) -> tuple[
                                                                                                              str, str] | None:
        self._frames += 1
        if kinematics.is_moving():
            key, sev = "coach_hold_steady", "warn"
        elif exercise in ("SQUEEZE", "O_RING") and step == 0 and geo.finger_extensions[1] > 0.4:
            key, sev = "coach_close_more", "warn"
        elif exercise == "SQUEEZE" and step == 1 and statistics.mean(geo.finger_extensions) < 0.65:
            key, sev = "coach_open_more", "warn"
        elif exercise == "STARFISH" and step == 1 and geo.spread_ratio < 1.0:
            key, sev = "coach_spread_more", "warn"
        elif exercise == "O_RING" and step == 1:
            nail_gap = geo.nail_distances.get((LI.THUMB_TIP, LI.INDEX_TIP), 1.0)
            key, sev = ("coach_perfect", "good") if nail_gap < 0.35 else ("coach_pinch_tighter", "warn")
        else:
            key, sev = "coach_perfect", "good"

        if key == self._last_key and self._frames < 12: return None
        self._last_key = key;
        self._frames = 0
        return key, sev


# =============================================================================
# 7. ADAPTIVE DIFFICULTY & XAI REPORTING
# =============================================================================
from datetime import datetime, timedelta


def get_therapy_day() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def generate_clinical_insights(history: dict, lang: str = "EN") -> list[str]:
    """Generates multi-factor clinical insights (Adherence, Volume, Quality, Trends)."""
    if not history or len(history) < 2:
        return ["Awaiting more data. Recommend daily therapy."] if lang == "EN" else [
            "รอข้อมูลเพิ่มเติม แนะนำทำกายภาพทุกวัน"]

    today = datetime.now()
    last_7_dates = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

    active_days = 0
    total_sets = 0
    recent_acc_list = []

    for d in last_7_dates:
        if d in history:
            day_data = history[d]
            sets_today = sum(day_data.get(k, 0) for k in
                             ["sq_sets", "thumb_sets", "star_sets", "flip_sets", "oring_sets", "peace_sets"])

            if sets_today > 0:
                active_days += 1
                total_sets += sets_today

            acc_vals = [day_data.get(k, 0) for k in
                        ["sq_acc", "thumb_acc", "star_acc", "flip_acc", "oring_acc", "peace_acc"] if
                        day_data.get(k, 0) > 0]
            if acc_vals:
                recent_acc_list.append(sum(acc_vals) / len(acc_vals))

    adherence_pct = (active_days / 7.0) * 100
    avg_acc = sum(recent_acc_list) / len(recent_acc_list) if recent_acc_list else 0

    sorted_history_dates = sorted([d for d in history.keys()], reverse=True)
    gaps = 0
    for i in range(len(sorted_history_dates) - 1):
        try:
            d1 = datetime.strptime(sorted_history_dates[i], "%Y-%m-%d")
            d2 = datetime.strptime(sorted_history_dates[i + 1], "%Y-%m-%d")
            if (d1 - d2).days > 1 and d1 >= today - timedelta(days=14):
                gaps += 1
        except Exception:
            pass

    insights = []

    if adherence_pct < 50:
        insights.append(
            f"Low adherence ({active_days}/7 days). Inconsistent practice limits neuroplastic recovery." if lang == "EN" else f"ความสม่ำเสมอต่ำ ({active_days}/7 วัน) การฝึกที่ไม่ต่อเนื่องอาจทำให้ฟื้นตัวช้า")
    elif total_sets < 15:
        insights.append(
            f"Low training volume ({total_sets} sets/week). Increase repetitions for better neuroplasticity." if lang == "EN" else f"ปริมาณการฝึกต่ำ {total_sets} เซ็ตต่อสัปดาห์ ควรเพิ่มจำนวนครั้งเพื่อกระตุ้นการฟื้นฟู")
    else:
        insights.append(
            f"Good recovery behavior: Consistent and effective training volume ({total_sets} sets/week)." if lang == "EN" else f"พฤติกรรมการฟื้นฟูดี: ปริมาณการฝึกสม่ำเสมอและมีประสิทธิภาพ {total_sets} เซ็ตต่อสัปดาห์")

    if avg_acc >= 80:
        insights.append(
            f"Motor control is high ({avg_acc:.1f}%)." if lang == "EN" else f"การควบคุมกล้ามเนื้ออยู่ในเกณฑ์สูง ({avg_acc:.1f}%)")
    elif avg_acc >= 50:
        insights.append(
            f"Moderate motor control ({avg_acc:.1f}%). Focus on movement quality." if lang == "EN" else f"การควบคุมกล้ามเนื้อปานกลาง ({avg_acc:.1f}%) ควรเน้นคุณภาพของการเคลื่อนไหว")
    elif active_days > 0:
        insights.append(
            f"Poor motor control ({avg_acc:.1f}%). Consider therapist review." if lang == "EN" else f"การควบคุมกล้ามเนื้อต่ำ ({avg_acc:.1f}%) ควรปรึกษานักกายภาพ")

    if gaps >= 1 and active_days > 0 and adherence_pct < 80:
        insights.append(
            "Irregular training pattern detected. Avoid skipping consecutive days." if lang == "EN" else "พบรูปแบบการฝึกที่ไม่สม่ำเสมอ หลีกเลี่ยงการหยุดพักติดต่อกันหลายวัน")

    latest_date = sorted_history_dates[0] if sorted_history_dates else None
    if latest_date:
        latest = history[latest_date]
        valid = {k: v for k, v in latest.items() if "acc" in k and v > 0}
        if valid:
            wk = min(valid, key=valid.get)
            names_en = {"sq_acc": "Squeeze", "thumb_acc": "Thumb Tap", "star_acc": "Starfish", "flip_acc": "Wrist Flip",
                        "oring_acc": "O-Ring", "peace_acc": "V-Sign"}
            names_th = {"sq_acc": "กำมือ/แบมือ", "thumb_acc": "แตะนิ้วโป้ง", "star_acc": "ปลาดาว",
                        "flip_acc": "หมุนข้อมือ", "oring_acc": "จีบนิ้ว", "peace_acc": "ชูสองนิ้ว"}
            n = names_th.get(wk, wk) if lang == "TH" else names_en.get(wk, wk)
            insights.append(
                f"Recommended focus: '{n}' (Current accuracy: {valid[wk]:.0f}%)." if lang == "EN" else f"ท่าที่ควรเน้นฝึก: '{n}' (ความแม่นยำ: {valid[wk]:.0f}%)")

    _, _, xai_reason = evaluate_adaptive_difficulty(history, False, lang)
    insights.append(xai_reason)

    return insights


def evaluate_adaptive_difficulty(history: dict, is_weak: bool = False, lang: str = "EN") -> tuple[int, dict, str]:
    """Scales the required Sets/Reps up or down based on clinical 2-for-2 rule."""
    s = 1 if is_weak else 3
    base = {"sq": [s, 20], "thumb": [s, 20], "star": [s, 15], "flip": [s, 15], "oring": [s + 1, 15],
            "peace": [s + 1, 10]}

    if not history:
        return 0, base, "AI Baseline: New patient profile created." if lang == "EN" else "AI Baseline: สร้างโปรไฟล์ผู้ป่วยใหม่"

    today = datetime.now()
    last_7 = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
    past_days = sorted([d for d in last_7 if d in history])

    done, days = 0, 0
    for d in last_7:
        if d in history:
            done += sum(history[d].get(k, 0) for k in
                        ["sq_sets", "thumb_sets", "star_sets", "flip_sets", "oring_sets", "peace_sets"])
            days += 1

    score = int(min(done / (days * 18) * 100, 100)) if days > 0 else 0
    new_goals = {}
    increased = decreased = False

    ex_keys = [("sq", "sq_sets", "sq_acc"), ("thumb", "thumb_sets", "thumb_acc"), ("star", "star_sets", "star_acc"),
               ("flip", "flip_sets", "flip_acc"), ("oring", "oring_sets", "oring_acc"),
               ("peace", "peace_sets", "peace_acc")]

    for prefix, set_key, acc_key in ex_keys:
        target = base[prefix][0]
        consec_good = 0
        consec_poor = 0

        for d in past_days:
            sets_done = history[d].get(set_key, 0)
            acc = history[d].get(acc_key, 0)

            if sets_done == 0:
                consec_good = 0
                consec_poor = 0
                continue

            if sets_done >= target and acc >= 80:
                consec_good += 1
                consec_poor = 0
            elif sets_done < target or acc < 50:
                consec_poor += 1
                consec_good = 0
            else:
                consec_good = 0
                consec_poor = 0

            if consec_good >= 2:
                target = min(8, target + 1)
                consec_good = 0
                increased = True
            if consec_poor >= 2:
                target = max(1, target - 1)
                consec_poor = 0
                decreased = True

        new_goals[prefix] = [target, base[prefix][1]]

    if increased:
        reason = "AI Adaptation: Goals increased due to high performance." if lang == "EN" else "AI Adaptation: เพิ่มเป้าหมายเนื่องจากประสิทธิภาพสูง"
    elif decreased:
        reason = "AI Adaptation: Goals reduced to prevent muscle fatigue." if lang == "EN" else "AI Adaptation: ลดเป้าหมายเพื่อป้องกันกล้ามเนื้อล้า"
    else:
        reason = "AI Adaptation: Goals maintained for consistency." if lang == "EN" else "AI Adaptation: คงเป้าหมายเดิมเพื่อความสม่ำเสมอ"

    return score, new_goals, reason
