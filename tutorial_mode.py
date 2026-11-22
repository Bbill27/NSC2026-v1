"""
===============================================================================
CerebroMotion - Interactive Tutorial (Ghost Hand + Live Checklist)
===============================================================================
Replaces the plain tutorial video with a guided, camera-checked lesson:

  1. WATCH     - an animated "ghost hand" demonstrates every step of the exercise
                 and a Thai voice explains it.
  2. PRACTICE  - the patient copies one step at a time. A live checklist shows
                 which parts are right (e.g. "Ring finger bent ✓") using the same
                 geometry the scoring engine uses. A step passes when the real
                 score (logic.get_movement_accuracy) stays >= 70 for a short hold.
                 Practice reps are NOT counted as therapy and never trigger the
                 fatigue lock.
  3. DONE      - after a few correct rounds the exercise is marked as learned.
===============================================================================
"""

from __future__ import annotations

import json
import math
import statistics
import time
from functools import lru_cache

import theme as T
from camera_mode import CameraMode
from hand_model import EXERCISE_POSES, fit_box_for, lerp_pose, render_hand
from logic import LI, HandGeometry, _d2, get_movement_accuracy

PASS_SCORE = 70
HOLD_SECONDS = 0.8
HINT_AFTER = 8.0

# =============================================================================
# 1. TEXT
# =============================================================================
FINGER_TH = ["นิ้วชี้", "นิ้วกลาง", "นิ้วนาง", "นิ้วก้อย"]
FINGER_EN = ["index", "middle", "ring", "pinky"]

EX_NAME = {
    "SQUEEZE": ("กำ / แบมือ", "Open / Close Fist"),
    "THUMB": ("แตะนิ้วโป้ง", "Thumb Taps"),
    "WIPER": ("โบกมือซ้าย-ขวา", "Hand Wiper"),
    "FLIP": ("หงาย / คว่ำมือ", "Palm Up / Down"),
    "TABLETOP": ("มือรูปตัว L", "L-Shape Hand"),
    "SCISSOR": ("หุบ / กางนิ้ว", "Finger Spread"),
    "HOOK": ("มือตะขอ", "The Claw"),
    "WRIST": ("กระดกข้อมือ", "Wrist Bend"),
    "PIANO": ("พรมนิ้วเปียโน", "Piano Fingers"),
    "HITCH": ("ชูนิ้วโป้ง", "Hitchhiker"),
}

EX_INTRO = {
    "SQUEEZE": ("กรุณากำมือให้แน่น แล้วแบมือออกให้สุด", "Please make a firm fist, then open your hand fully."),
    "THUMB": ("กรุณาแตะปลายนิ้วหัวแม่มือกับปลายนิ้วแต่ละนิ้ว เรียงจากนิ้วชี้ไปจนถึงนิ้วก้อย",
              "Please touch your thumb to each fingertip in turn, from index to little finger."),
    "WIPER": ("กรุณาเหยียดนิ้วให้ตรง แล้วเอียงมือไปทางซ้ายและทางขวาสลับกัน",
              "Keep your fingers straight and tilt your hand to the left, then to the right."),
    "FLIP": ("กรุณาแบมือโดยหันฝ่ามือเข้าหากล้อง แล้วพลิกมือให้หลังมือหันเข้าหากล้อง",
             "Open your hand with the palm facing the camera, then turn it over."),
    "TABLETOP": ("กรุณาหันด้านข้างของมือเข้าหากล้อง กำมือ แล้วเหยียดนิ้วให้ตรงโดยงอเฉพาะที่โคนนิ้วเป็นมุมฉาก",
                 "Turn the side of your hand to the camera. Make a fist, then straighten the fingers, "
                 "bending only at the knuckles to form an L shape."),
    "SCISSOR": ("กรุณาหุบนิ้วให้ชิดกัน แล้วกางนิ้วออกให้กว้างที่สุด",
                "Hold your fingers together, then spread them as wide as you can."),
    "HOOK": ("กรุณาหันด้านข้างของมือเข้าหากล้อง เหยียดนิ้วให้ตรง แล้วงอปลายนิ้วโดยให้โคนนิ้วยังตรงอยู่",
             "Turn the side of your hand to the camera. Straighten the fingers, then curl the fingertips "
             "while keeping the knuckles straight."),
    "WRIST": ("กรุณาหันด้านข้างของมือเข้าหากล้อง แล้วกระดกข้อมือขึ้น จากนั้นกดข้อมือลง",
              "Turn the side of your hand to the camera. Bend your wrist up, then down."),
    "PIANO": ("กรุณายกนิ้วขึ้นทีละนิ้ว โดยให้นิ้วอื่นอยู่ในท่างอเล็กน้อย",
              "Please lift one finger at a time while the other fingers stay slightly bent."),
    "HITCH": ("กรุณากำมือโดยเก็บนิ้วหัวแม่มือไว้ แล้วกางนิ้วหัวแม่มือออก",
              "Make a fist with the thumb tucked in, then extend the thumb outwards."),
}


def _step_names(ex: str, lang: str) -> list[str]:
    th = lang == "TH"
    two = {
        "SQUEEZE": (("กำมือ", "แบมือ"), ("Make a fist", "Open hand")),
        "WIPER": (("เอียงมือไปทางซ้าย", "เอียงมือไปทางขวา"), ("Tilt left", "Tilt right")),
        "FLIP": (("หันฝ่ามือเข้ากล้อง", "หันหลังมือเข้ากล้อง"), ("Palm to camera", "Back of hand to camera")),
        "TABLETOP": (("กำมือ", "ทำมือรูปตัว L"), ("Make a fist", "Make an L-shape")),
        "SCISSOR": (("หุบนิ้วชิดกัน", "กางนิ้วออก"), ("Fingers together", "Spread fingers")),
        "HOOK": (("เหยียดนิ้วตรง", "งอนิ้วเป็นตะขอ"), ("Fingers straight", "Make a claw")),
        "WRIST": (("กระดกข้อมือขึ้น", "กดข้อมือลง"), ("Wrist up", "Wrist down")),
        "HITCH": (("กำมือ เก็บนิ้วโป้ง", "กางนิ้วโป้งออก"), ("Fist, thumb in", "Thumb out")),
    }
    if ex in two:
        return list(two[ex][0 if th else 1])
    names = FINGER_TH if th else FINGER_EN
    if ex == "THUMB":
        return [(f"แตะนิ้วโป้งกับ{n}" if th else f"Thumb to {n}") for n in names]
    return [(f"ยก{n}" if th else f"Lift {n}") for n in names]


UI = {
    "TH": {
        "title": "คู่มือการฝึกท่าทาง", "back": "กลับเมนูหลัก", "watch": "ดูท่าตัวอย่าง",
        "practice": "ฝึกปฏิบัติ", "done": "ผ่านแล้ว", "step": "ขั้นที่", "round": "รอบที่",
        "start": "เริ่มฝึกปฏิบัติ", "rewatch": "ดูตัวอย่างอีกครั้ง", "next": "ท่าถัดไป",
        "again": "ฝึกซ้ำ", "checklist": "ตรวจสอบท่าทาง", "no_hand": "กรุณายกมือให้อยู่ในกรอบกล้อง",
        "copy": "กรุณาทำตามท่าตัวอย่าง", "ready": "เมื่อพร้อม กรุณายกมือขึ้น ระบบจะเริ่มการฝึกปฏิบัติโดยอัตโนมัติ",
        "great": "ผ่านการฝึกท่านี้แล้ว", "hold": "กรุณาค้างท่าไว้", "good": "ท่าทางถูกต้อง",
        "your_hand": "ภาพจากกล้อง", "learned": "ผ่านแล้ว", "skip": "ข้ามขั้นตอนนี้",
        "skip_hint": "หากทำได้ยาก สามารถข้ามขั้นตอนนี้ได้", "demo": "ท่าตัวอย่าง",
    },
    "EN": {
        "title": "Movement Guide", "back": "Back to menu", "watch": "Demonstration",
        "practice": "Practice", "done": "Completed", "step": "Step", "round": "Round",
        "start": "Start practice", "rewatch": "Repeat demonstration", "next": "Next exercise",
        "again": "Practice again", "checklist": "Posture check", "no_hand": "Please place your hand within the camera frame",
        "copy": "Please follow the demonstrated posture",
        "ready": "When ready, raise your hand. Practice will begin automatically.",
        "great": "Exercise completed", "hold": "Please hold the position", "good": "Correct posture",
        "your_hand": "Camera view", "learned": "Completed", "skip": "Skip this step",
        "skip_hint": "If this is difficult, you may skip this step", "demo": "Demonstration",
    },
}


# =============================================================================
# 2. LIVE CHECKLIST (explainable feedback that mirrors logic.py's scoring)
# =============================================================================
def _mcp_angle(lms, mcp, pip):
    ab, bc, ac = _d2(lms[LI.WRIST], lms[mcp]), _d2(lms[mcp], lms[pip]), _d2(lms[LI.WRIST], lms[pip])
    den = 2 * ab * bc
    if den < 1e-9:
        return 180.0
    return math.degrees(math.acos(max(-1.0, min(1.0, (ab * ab + bc * bc - ac * ac) / den))))


def checklist(ex: str, step: int, lms, lang: str) -> list[tuple[str, bool]]:
    th = lang == "TH"
    g = HandGeometry.from_landmarks(lms)
    fn = FINGER_TH if th else FINGER_EN
    tips = [LI.INDEX_TIP, LI.MIDDLE_TIP, LI.RING_TIP, LI.PINKY_TIP]
    items: list[tuple[str, bool]] = []

    if ex == "SQUEEZE" and step == 0:
        for i in range(4):
            tucked = _d2(lms[tips[i]], lms[LI.WRIST]) / g.palm_size < 1.2
            items.append(((f"งอ{fn[i]}" if th else f"Bend {fn[i]} finger"), g.finger_curl[i] >= 0.6 or tucked))
    elif ex == "SQUEEZE":
        for i in range(4):
            items.append(((f"เหยียด{fn[i]}" if th else f"Straighten {fn[i]} finger"), g.finger_ext[i] >= 0.6))
        items.append(("กางนิ้วออกเล็กน้อย" if th else "Fingers slightly apart", g.spread_ratio >= 0.7))
    elif ex == "THUMB":
        key = (LI.THUMB_TIP, tips[step])
        d = g.nail_distances.get(key, 1.0)
        others = [g.nail_distances.get((LI.THUMB_TIP, tips[i]), 1.0) for i in range(4) if i != step]
        items.append(((f"แตะนิ้วโป้งกับ{fn[step]}" if th else f"Thumb touches {fn[step]}"), d < 0.45))
        items.append(("นิ้วอื่นอยู่ห่างจากนิ้วโป้ง" if th else "Other fingers stay away",
                      d < min(others) * 0.85))
    elif ex == "WIPER":
        cx = sum(lms[i].x for i in (LI.INDEX_MCP, LI.MIDDLE_MCP, LI.RING_MCP, LI.PINKY_MCP)) / 4
        dev = cx - lms[LI.WRIST].x
        items.append(("เหยียดนิ้วให้ตรง" if th else "Keep fingers straight", statistics.mean(g.finger_ext) >= 0.3))
        if step == 0:
            items.append(("เอียงมือไปทางซ้าย" if th else "Tilt hand to the left", dev < -0.03))
        else:
            items.append(("เอียงมือไปทางขวา" if th else "Tilt hand to the right", dev > 0.03))
    elif ex == "FLIP":
        items.append(("แบมือให้ตรง" if th else "Hand open and flat", statistics.mean(g.finger_ext) >= 0.45))
        want = step == 0
        items.append(((("หันฝ่ามือเข้าหากล้อง" if want else "หันหลังมือเข้าหากล้อง") if th else
                       ("Palm faces the camera" if want else "Back of hand faces the camera")),
                      g.palm_facing_camera == want))
    elif ex == "TABLETOP" and step == 0:
        for i in range(4):
            items.append(((f"งอ{fn[i]}" if th else f"Bend {fn[i]} finger"), g.finger_curl[i] >= 0.7))
    elif ex == "TABLETOP":
        ang = statistics.mean(_mcp_angle(lms, m, p) for m, p in
                              [(LI.INDEX_MCP, LI.INDEX_PIP), (LI.MIDDLE_MCP, LI.MIDDLE_PIP),
                               (LI.RING_MCP, LI.RING_PIP), (LI.PINKY_MCP, LI.PINKY_PIP)])
        items.append(("นิ้วเหยียดตรง" if th else "Fingers straight", statistics.mean(g.finger_ext) >= 0.55))
        items.append(("พับที่โคนนิ้วเป็นมุมฉาก" if th else "Bend at the knuckles (about 90°)", ang < 125))
    elif ex == "SCISSOR":
        items.append(("เหยียดนิ้วให้ตรง" if th else "Fingers straight", statistics.mean(g.finger_ext) >= 0.45))
        if step == 0:
            items.append(("หุบนิ้วให้ชิดกัน" if th else "Fingers close together", g.spread_ratio < 1.0))
        else:
            items.append(("กางนิ้วออกให้กว้าง" if th else "Spread fingers wide", g.spread_ratio > 1.25))
    elif ex == "HOOK" and step == 0:
        items.append(("เหยียดนิ้วทุกนิ้วให้ตรง" if th else "All fingers straight",
                      statistics.mean(g.pip_angles) > 140))
    elif ex == "HOOK":
        items.append(("งอข้อกลางนิ้ว" if th else "Curl the middle joints", statistics.mean(g.finger_curl) >= 0.45))
        items.append(("โคนนิ้วยังตรงอยู่" if th else "Knuckles stay straight",
                      _d2(lms[LI.MIDDLE_MCP], lms[LI.WRIST]) / g.palm_size > 0.8))
        items.append(("นิ้วกลางงอชัดเจน" if th else "Middle finger clearly curled", g.pip_angles[1] < 130))
    elif ex == "WRIST":
        dy = (lms[LI.WRIST].y - lms[LI.MIDDLE_MCP].y) / g.palm_size
        if step == 0:
            items.append(("กระดกข้อมือขึ้น" if th else "Bend wrist up", dy > 0.18))
        else:
            items.append(("กดข้อมือลง" if th else "Bend wrist down", dy < -0.18))
    elif ex == "PIANO":
        tgt = g.pip_angles[step]
        others = statistics.mean(g.pip_angles[i] for i in range(4) if i != step)
        items.append(((f"ยก{fn[step]}ให้ตรง" if th else f"Lift the {fn[step]} finger straight"), tgt > 145))
        items.append(("นิ้วอื่นงอลงไว้" if th else "Other fingers stay down", others < 150))
        items.append(((f"{fn[step]}สูงกว่านิ้วอื่น" if th else f"{fn[step].capitalize()} higher than others"),
                      tgt - others > 20))
    elif ex == "HITCH":
        fist = statistics.mean(g.finger_curl) >= 0.65
        items.append(("กำนิ้วทั้งสี่" if th else "Four fingers curled", fist))
        if step == 0:
            items.append(("เก็บนิ้วโป้งไว้" if th else "Thumb tucked in", g.thumb_ext < 0.5))
        else:
            items.append(("กางนิ้วโป้งออก" if th else "Thumb sticks out", g.thumb_ext > 0.6))
    return items


# =============================================================================
# 3. PROGRESS FILE
# =============================================================================
def load_tutorial_progress() -> dict:
    try:
        with open(T.json_path("tutorial_progress.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_learned(ex: str) -> None:
    data = load_tutorial_progress()
    rec = data.get(ex, {"times": 0})
    rec["times"] = rec.get("times", 0) + 1
    rec["last"] = time.strftime("%Y-%m-%d")
    data[ex] = rec
    try:
        with open(T.json_path("tutorial_progress.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


@lru_cache(maxsize=96)
def _ghost(pose, size, box):
    return render_hand(pose, size, box)


# =============================================================================
# 4. THE MODE
# =============================================================================
class TutorialMode(CameraMode):
    name = "tutorial"

    def __init__(self, app, exercise: str | None = None):
        super().__init__(app)
        self.exercises = list(getattr(app, "prescribed_exercises", list(EXERCISE_POSES)))
        self.learned = set(load_tutorial_progress().keys())
        self._select(exercise or self.exercises[0])

    # ── state ───────────────────────────────────────────────────
    def _select(self, ex: str) -> None:
        with self.lock:
            self.ex = ex
            self.poses = EXERCISE_POSES[ex]
            self.n = len(self.poses)
            self.box = fit_box_for(self.poses)
            self.cycles_needed = 2 if self.n > 2 else 3
            self._go_watch()

    def _go_watch(self) -> None:
        self.phase = "WATCH"
        self.t0 = time.time()
        self.hand_since = 0.0
        self.spoken_intro = False

    def _go_practice(self) -> None:
        self.phase = "PRACTICE"
        self.skipped = False
        self.step = 0
        self.cycles = 0
        self.hold_start = 0.0
        self.step_start = time.time()
        self.last_hint = 0.0
        self.flash_until = 0.0
        self.smooth = 0
        self._say(_step_names(self.ex, self.lang)[0])

    def _say(self, text: str) -> None:
        try:
            import audio
            audio.speak_message(text, self.lang)
        except Exception:
            pass

    def handle_action(self, action: str) -> None:
        if action == "exit":
            self.request_exit()
        elif action == "start":
            with self.lock:
                self._go_practice()
        elif action in ("rewatch", "again"):
            with self.lock:
                self._go_watch() if action == "rewatch" else self._go_practice()
        elif action == "skip":
            with self.lock:
                if self.phase == "PRACTICE":
                    self.skipped = True
                    self._step_passed(time.time())
        elif action == "next":
            i = self.exercises.index(self.ex) if self.ex in self.exercises else -1
            self._select(self.exercises[(i + 1) % len(self.exercises)])
        elif action.startswith("tab:"):
            self._select(action[4:])

    # ── logic per frame ─────────────────────────────────────────
    def _update(self, lms, now):
        if self.phase == "WATCH":
            if not self.spoken_intro and now - self.t0 > 0.6:
                self.spoken_intro = True
                self._say(EX_INTRO[self.ex][0 if self.lang == "TH" else 1])
            if lms:
                self.hand_since = self.hand_since or now
            else:
                self.hand_since = 0.0
            loop_len = self.n * 2.0
            if now - self.t0 > loop_len + 1.0 and self.hand_since and now - self.hand_since > 1.5:
                self._go_practice()
            return None, []

        if self.phase != "PRACTICE":
            return None, []

        if not lms:
            self.hold_start = 0.0
            return None, []

        acc = get_movement_accuracy(self.ex, self.step, 0, lms)
        self.smooth = int(0.6 * acc + 0.4 * self.smooth)
        items = checklist(self.ex, self.step, lms, self.lang)

        if acc >= PASS_SCORE:
            self.hold_start = self.hold_start or now
            if now - self.hold_start >= HOLD_SECONDS:
                self._step_passed(now)
        else:
            self.hold_start = 0.0
            if now - self.step_start > HINT_AFTER and now - self.last_hint > 6.0:
                self.last_hint = now
                missing = [label for label, ok in items if not ok]
                if missing:
                    self._say(missing[0])
        return acc, items

    def _step_passed(self, now):
        try:
            import audio
            audio.play_success_sound()
        except Exception:
            pass
        self.flash_until = now + 0.7
        self.hold_start = 0.0
        self.step += 1
        if self.step >= self.n:
            self.step = 0
            self.cycles += 1
            if self.cycles >= self.cycles_needed:
                self.phase = "DONE"
                self.done_at = now
                if not self.skipped:          # a lesson with skipped steps is not marked as learned
                    self.learned.add(self.ex)
                    _save_learned(self.ex)
                try:
                    import audio
                    audio.play_celebration_sound()
                except Exception:
                    pass
                self._say(UI[self.lang]["great"])
                return
        self.step_start = now
        self._say(_step_names(self.ex, self.lang)[self.step])

    def _ghost_pose(self, now):
        if self.phase == "WATCH":
            seg = 2.0
            t = now - self.t0
            k = int(t / seg) % self.n
            frac = (t % seg) / 0.8
            return lerp_pose(self.poses[k - 1], self.poses[k], frac), k
        if self.phase == "PRACTICE":
            frac = ((now - self.step_start) % 3.0) / 0.9
            return lerp_pose(self.poses[self.step - 1], self.poses[self.step], frac), self.step
        return self.poses[-1], self.n - 1

    # ── rendering ───────────────────────────────────────────────
    def on_frame(self, frame_bgr, lms, now, size):
        with self.lock:
            acc, items = self._update(lms, now)
            return self._render(frame_bgr, lms, now, size, acc, items)

    def _render(self, frame_bgr, lms, now, size, acc, items):
        W, H = size
        tx = UI[self.lang]
        th = self.lang == "TH"
        img, d = T.new_screen(W, H)
        self._buttons = []
        pad = int(H * 0.022)
        f_big, f_mid, f_sm, f_xs = T.font(H * 0.05), T.font(H * 0.036), T.font(H * 0.03), T.font(H * 0.026, False)

        # Header bar (shared formal header)
        user = getattr(self.app, "current_user", "") or ""
        who = f"{'ผู้ใช้งาน' if th else 'User'}: {user}" if user else ""
        hh, back_box = T.draw_header(d, W, H, tx["title"], tx["back"], who)
        self.add_button(back_box, "exit")

        # Exercise tabs
        ty0, ty1 = hh + pad * 0.6, hh + pad * 0.6 + H * 0.07
        n_ex = len(self.exercises)
        tab_w = (W - 2 * pad - (n_ex - 1) * 10) / max(1, n_ex)
        for i, ex in enumerate(self.exercises):
            x0 = pad + i * (tab_w + 10)
            box = (x0, ty0, x0 + tab_w, ty1)
            active = ex == self.ex
            d.rounded_rectangle(box, radius=10, fill=T.R_PRIMARY if active else T.R_SURFACE,
                                outline=T.R_PRIMARY if active else T.R_BORDER, width=2)
            label = EX_NAME[ex][0 if th else 1]
            T.text_center(d, x0 + tab_w / 2, (ty0 + ty1) / 2, label, f_xs if len(label) > 14 else f_sm,
                          (255, 255, 255) if active else T.R_HEADING)
            if ex in self.learned:
                T.check_icon(d, x0 + tab_w - 16, ty0 + 14, 9, True)
            self.add_button(box, f"tab:{ex}")

        body_top = ty1 + pad
        foot_h = int(H * 0.095)
        body_bot = H - foot_h - pad
        split = int(W * 0.42)

        # ── Left: ghost hand card ───────────────────────────────
        lbox = (pad, body_top, split, body_bot)
        T.card(d, lbox)
        names = _step_names(self.ex, self.lang)
        pose, k = self._ghost_pose(now)
        if self.phase == "WATCH":
            pill, pill_col = tx["watch"], T.R_PRIMARY
            headline = names[k]
        elif self.phase == "PRACTICE":
            pill = f"{tx['practice']}  ·  {tx['step']} {self.step + 1}/{self.n}"
            pill_col = T.R_PRIMARY
            headline = names[self.step]
        else:
            pill, pill_col, headline = tx["done"], T.R_SUCCESS, tx["great"]
        pw = T.text_size(d, pill, f_sm)[0] + 40
        d.rounded_rectangle([lbox[0] + 24, lbox[1] + 20, lbox[0] + 24 + pw, lbox[1] + 20 + H * 0.056],
                            radius=8, fill=pill_col)
        T.text_center(d, lbox[0] + 24 + pw / 2, lbox[1] + 20 + H * 0.028, pill, f_sm, (255, 255, 255))
        T.text_left(d, lbox[0] + 28, lbox[1] + 20 + H * 0.056 + H * 0.05, headline, f_big, T.R_HEADING)

        gy0 = int(lbox[1] + H * 0.17)
        gy1 = int(lbox[3] - H * 0.055)
        gs = int(min(lbox[2] - lbox[0] - 40, gy1 - gy0))
        ghost = _ghost(pose, (gs, gs), self.box)
        gx = int((lbox[0] + lbox[2] - gs) / 2)
        img.paste(ghost, (gx, gy0), ghost)
        if self.phase == "DONE":
            T.check_icon(d, gx + gs - gs * 0.12, gy0 + gs * 0.12, gs * 0.1, True)
        T.text_center(d, (lbox[0] + lbox[2]) / 2, lbox[3] - H * 0.034,
                      tx["copy"] if self.phase != "WATCH" else EX_NAME[self.ex][0 if th else 1], f_xs, T.R_MUTED)

        # ── Right: camera + checklist ───────────────────────────
        rx0, rx1 = split + pad, W - pad
        cam_bot = int(body_top + (body_bot - body_top) * 0.54)
        cam_box = (rx0, body_top, rx1, cam_bot)
        T.card(d, cam_box, fill=(30, 41, 56), outline=T.R_BORDER)
        cx, cy, cw, ch = T.place_camera(img, frame_bgr, (rx0 + 6, body_top + 6, rx1 - 6, cam_bot - 6), lms)
        T.text_left(d, cx + 14, cy + 24, tx["your_hand"], f_xs, (255, 255, 255))
        if not lms:
            msg = tx["no_hand"]
            mw = T.text_size(d, msg, f_mid)[0]
            mx, my = (rx0 + rx1) / 2, (body_top + cam_bot) / 2
            d.rounded_rectangle([mx - mw / 2 - 30, my - H * 0.045, mx + mw / 2 + 30, my + H * 0.045],
                                radius=10, fill=(255, 255, 255), outline=T.R_WARN, width=3)
            T.text_center(d, mx, my, msg, f_mid, T.R_WARN_TEXT)
        if now < getattr(self, "flash_until", 0):
            d.rounded_rectangle(cam_box, radius=12, outline=T.R_SUCCESS, width=8)
            gw = T.text_size(d, tx["good"], f_big)[0] + 60
            gcx, gcy = (rx0 + rx1) / 2, body_top + H * 0.07
            d.rounded_rectangle([gcx - gw / 2, gcy - H * 0.04, gcx + gw / 2, gcy + H * 0.04], radius=10, fill=T.R_SUCCESS)
            T.text_center(d, gcx, gcy, tx["good"], f_mid, (255, 255, 255))

        ck_box = (rx0, cam_bot + pad, rx1, body_bot)
        T.card(d, ck_box)
        self._draw_checklist(d, ck_box, items, acc, now, H, f_mid, f_sm, f_xs)

        # ── Footer buttons ──────────────────────────────────────
        fy0, fy1 = H - foot_h, H - pad * 0.6
        bw = int(W * 0.24)
        if self.phase == "WATCH":
            btns = [("rewatch", tx["rewatch"], "secondary"), ("start", tx["start"], "primary"),
                    ("next", tx["next"], "secondary")]
        elif self.phase == "PRACTICE":
            btns = [("rewatch", tx["rewatch"], "secondary")]
            if now - self.step_start > 20.0:
                btns.append(("skip", tx["skip"], "primary"))
                T.text_center(d, W / 2, fy0 - H * 0.022, tx["skip_hint"], f_xs, T.R_MUTED)
            btns.append(("next", tx["next"], "secondary"))
        else:
            btns = [("again", tx["again"], "secondary"), ("next", tx["next"], "success")]
        total = len(btns) * bw + (len(btns) - 1) * pad
        x = (W - total) / 2
        for action, label, style in btns:
            box = (x, fy0, x + bw, fy1)
            T.button(d, box, label, f_sm, style)
            self.add_button(box, action)
            x += bw + pad
        return img

    def _draw_checklist(self, d, box, items, acc, now, H, f_mid, f_sm, f_xs):
        tx = UI[self.lang]
        x0, y0, x1, y1 = box
        if self.phase == "WATCH":
            T.text_left(d, x0 + 28, y0 + H * 0.045, tx["watch"], f_mid, T.R_HEADING)
            intro = EX_INTRO[self.ex][0 if self.lang == "TH" else 1]
            self._wrap(d, intro, x0 + 28, y0 + H * 0.1, x1 - x0 - 56, f_sm, T.R_TEXT, H * 0.045)
            T.text_left(d, x0 + 28, y1 - H * 0.04, tx["ready"], f_xs, T.R_MUTED)
            return
        if self.phase == "DONE":
            T.check_icon(d, (x0 + x1) / 2, (y0 + y1) / 2 - H * 0.05, H * 0.04, True)
            T.text_center(d, (x0 + x1) / 2, (y0 + y1) / 2 + H * 0.035, tx["great"], f_mid, T.R_SUCCESS)
            return

        # header: title + round dots
        T.text_left(d, x0 + 28, y0 + H * 0.04, tx["checklist"], f_mid, T.R_HEADING)
        label = f"{tx['round']} {min(self.cycles + 1, self.cycles_needed)}/{self.cycles_needed}"
        lw = T.text_size(d, label, f_sm)[0]
        dots_w = self.cycles_needed * 30
        T.text_left(d, x1 - 28 - dots_w - lw - 16, y0 + H * 0.04, label, f_sm, T.R_TEXT)
        for i in range(self.cycles_needed):
            cx = x1 - 28 - dots_w + i * 30 + 12
            cy = y0 + H * 0.04
            done = i < self.cycles
            d.ellipse([cx - 10, cy - 10, cx + 10, cy + 10], fill=T.R_SUCCESS if done else T.R_SURFACE_ALT,
                      outline=T.R_SUCCESS if done else T.R_BORDER, width=2)

        # items
        cols = 2 if len(items) > 2 else 1
        rows = max(1, math.ceil(len(items) / cols))
        top = y0 + H * 0.085
        items_bottom = y1 - H * 0.105              # keep clear of the "hold" label and progress bar
        row_h = min(H * 0.065, (items_bottom - top) / rows)
        col_w = (x1 - x0 - 56) / cols
        if not items:
            T.text_left(d, x0 + 28, top + row_h / 2, tx["no_hand"], f_sm, T.R_MUTED)
        for idx, (label, ok) in enumerate(items):
            cx = x0 + 28 + (idx % cols) * col_w
            cy = top + (idx // cols) * row_h + row_h / 2
            T.check_icon(d, cx + 18, cy, min(18, row_h * 0.34), ok)
            T.text_left(d, cx + 50, cy, label, f_sm, T.R_SUCCESS if ok else T.R_TEXT)

        # hold bar
        by = y1 - H * 0.045
        bx0, bx1 = x0 + 28, x1 - 28
        d.rounded_rectangle([bx0, by, bx1, by + 16], radius=8, fill=T.R_SURFACE_ALT)
        pct = 0.0
        if self.hold_start:
            pct = min(1.0, (now - self.hold_start) / HOLD_SECONDS)
        elif acc is not None:
            pct = min(0.95, acc / 100.0) * 0.35
        if pct > 0:
            col = T.R_SUCCESS if self.hold_start else T.R_PRIMARY
            d.rounded_rectangle([bx0, by, bx0 + (bx1 - bx0) * pct, by + 16], radius=8, fill=col)
        if self.hold_start:
            T.text_left(d, bx0, by - H * 0.026, tx["hold"], f_xs, T.R_SUCCESS)

    @staticmethod
    def _wrap(d, text, x, y, width, fnt, fill, line_h):
        words = text.split(" ")
        line = ""
        for w in words:
            test = (line + " " + w).strip()
            if T.text_size(d, test, fnt)[0] > width and line:
                T.text_left(d, x, y, line, fnt, fill)
                y += line_h
                line = w
            else:
                line = test
        if line:
            T.text_left(d, x, y, line, fnt, fill)
