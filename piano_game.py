"""
===============================================================================
CerebroMotion - Finger Piano Tiles (therapy mini-game)
===============================================================================
An elderly-friendly "piano tiles" game built on the PIANO FINGERS exercise.

  * 4 lanes = index, middle, ring, pinky. Lift the matching finger when a tile
    reaches the keys and the note plays - the patient hears the song appear.
  * Difficulty is adjustable the way a therapist would want it:
      - Song (simple -> wider melody), Speed (very slow -> fast),
      - "Wait for me" mode: tiles stop at the keys until the patient succeeds,
        so nobody can fail. No game over, ever.
  * Every hit uses the real scoring engine (logic.get_movement_accuracy) and
    counts toward today's PIANO reps (4 finger lifts = 1 rep).
  * The result screen shows a hit rate per finger and the reaction time, so the
    weak finger is visible to the patient (and later the doctor), and suggests
    the next difficulty.

All songs are public-domain melodies. Notes are synthesised in code (offline).
===============================================================================
"""

from __future__ import annotations

import json
import statistics
import time

import theme as T
from camera_mode import CameraMode
from logic import get_movement_accuracy

HIT_SCORE = 65          # a little easier than the 70 used in therapy - it's a game
REARM_DROP = 20         # score must fall this much before the same finger can fire again
TRAVEL_SECONDS = 3.0    # time a tile takes to fall from the top to the keys

# =============================================================================
# 1. SONGS (MIDI note, beats). Public-domain melodies, simplified rhythms.
# =============================================================================
C4, D4, E4, F4, G4, A4, B4 = 60, 62, 64, 65, 67, 69, 71
C5, D5, E5, F5, G5 = 72, 74, 76, 77, 79
G3 = 55

SONGS = [
    {"id": "mary", "th": "แมรี่มีลูกแกะ", "en": "Mary Had a Little Lamb", "level": 1,
     "notes": [(E4, 1), (D4, 1), (C4, 1), (D4, 1), (E4, 1), (E4, 1), (E4, 2), (D4, 1), (D4, 1), (D4, 2),
               (E4, 1), (G4, 1), (G4, 2), (E4, 1), (D4, 1), (C4, 1), (D4, 1), (E4, 1), (E4, 1), (E4, 1),
               (E4, 1), (D4, 1), (D4, 1), (E4, 1), (D4, 1), (C4, 3)]},
    {"id": "twinkle", "th": "ทวิงเคิล ทวิงเคิล ลิตเติลสตาร์", "en": "Twinkle Twinkle Little Star", "level": 1,
     "notes": [(C4, 1), (C4, 1), (G4, 1), (G4, 1), (A4, 1), (A4, 1), (G4, 2), (F4, 1), (F4, 1), (E4, 1),
               (E4, 1), (D4, 1), (D4, 1), (C4, 2), (G4, 1), (G4, 1), (F4, 1), (F4, 1), (E4, 1), (E4, 1),
               (D4, 2), (C4, 1), (C4, 1), (G4, 1), (G4, 1), (A4, 1), (A4, 1), (G4, 2), (F4, 1), (F4, 1),
               (E4, 1), (E4, 1), (D4, 1), (D4, 1), (C4, 3)]},
    {"id": "ode", "th": "บทเพลงแห่งความสุข (เบโธเฟน)", "en": "Ode to Joy (Beethoven)", "level": 2,
     "notes": [(E4, 1), (E4, 1), (F4, 1), (G4, 1), (G4, 1), (F4, 1), (E4, 1), (D4, 1), (C4, 1), (C4, 1),
               (D4, 1), (E4, 1), (E4, 1.5), (D4, 0.5), (D4, 2), (E4, 1), (E4, 1), (F4, 1), (G4, 1), (G4, 1),
               (F4, 1), (E4, 1), (D4, 1), (C4, 1), (C4, 1), (D4, 1), (E4, 1), (D4, 1.5), (C4, 0.5), (C4, 3)]},
    {"id": "jacques", "th": "บราเดอร์จอห์น (Frère Jacques)", "en": "Frère Jacques", "level": 2,
     "notes": [(C4, 1), (D4, 1), (E4, 1), (C4, 1), (C4, 1), (D4, 1), (E4, 1), (C4, 1), (E4, 1), (F4, 1),
               (G4, 2), (E4, 1), (F4, 1), (G4, 2), (G4, 0.5), (A4, 0.5), (G4, 0.5), (F4, 0.5), (E4, 1),
               (C4, 1), (G4, 0.5), (A4, 0.5), (G4, 0.5), (F4, 0.5), (E4, 1), (C4, 1), (C4, 1), (G3, 1),
               (C4, 2), (C4, 1), (G3, 1), (C4, 3)]},
    {"id": "birthday", "th": "สุขสันต์วันเกิด", "en": "Happy Birthday", "level": 3,
     "notes": [(G4, 0.5), (G4, 0.5), (A4, 1), (G4, 1), (C5, 1), (B4, 2), (G4, 0.5), (G4, 0.5), (A4, 1),
               (G4, 1), (D5, 1), (C5, 2), (G4, 0.5), (G4, 0.5), (G5, 1), (E5, 1), (C5, 1), (B4, 1), (A4, 2),
               (F5, 0.5), (F5, 0.5), (E5, 1), (C5, 1), (D5, 1), (C5, 3)]},
    {"id": "jingle", "th": "จิงเกิลเบลล์", "en": "Jingle Bells", "level": 3,
     "notes": [(E4, 1), (E4, 1), (E4, 2), (E4, 1), (E4, 1), (E4, 2), (E4, 1), (G4, 1), (C4, 1.5), (D4, 0.5),
               (E4, 3), (F4, 1), (F4, 1), (F4, 1.5), (F4, 0.5), (F4, 1), (E4, 1), (E4, 1), (E4, 0.5), (E4, 0.5),
               (E4, 1), (D4, 1), (D4, 1), (E4, 1), (D4, 2), (G4, 3)]},
]

SPEEDS = [  # (beats per minute, Thai, English)
    (45, "ช้ามาก", "Very slow"),
    (65, "ช้า", "Slow"),
    (85, "ปานกลาง", "Medium"),
    (110, "เร็ว", "Fast"),
]

NOTE_NAMES_TH = {0: "โด", 2: "เร", 4: "มี", 5: "ฟา", 7: "ซอล", 9: "ลา", 11: "ที"}
FINGER_TH = ["นิ้วชี้", "นิ้วกลาง", "นิ้วนาง", "นิ้วก้อย"]
FINGER_EN = ["Index", "Middle", "Ring", "Pinky"]

TXT = {
    "TH": {"title": "เกมเปียโนฝึกนิ้ว", "back": "กลับเมนูหลัก", "choose": "เลือกเพลง", "speed": "ความเร็วในการฝึก",
           "wait": "โหมดรอผู้ป่วย (ไม่มีการนับพลาด)", "wait_on": "เปิด", "wait_off": "ปิด", "play": "เริ่มการฝึก",
           "best": "ผลดีที่สุด", "raise": "กรุณายกมือให้อยู่ในกรอบกล้อง", "ready": "พร้อมเริ่มการฝึก",
           "paused": "หยุดชั่วคราว กรุณายกมือให้อยู่ในกรอบกล้อง", "hits": "จำนวนที่ถูกต้อง",
           "again": "ฝึกอีกครั้ง", "songs": "เลือกเพลงใหม่", "result": "สรุปผลการฝึก", "acc": "ความแม่นยำ",
           "react": "เวลาตอบสนองเฉลี่ย", "per_finger": "ความแม่นยำรายนิ้ว", "reps": "นับเป็นการฝึกพรมนิ้ว",
           "times": "ครั้ง", "sec": "วินาที",
           "up": "ผลการฝึกอยู่ในเกณฑ์ดีมาก แนะนำให้เพิ่มความเร็วในครั้งถัดไป",
           "keep": "ผลการฝึกอยู่ในเกณฑ์ดี แนะนำให้ฝึกที่ความเร็วนี้ต่อไป",
           "down": "แนะนำให้ลดความเร็ว หรือเปิดโหมดรอผู้ป่วย",
           "focus": "นิ้วที่ควรฝึกเพิ่ม", "lift": "ยกนิ้วขึ้นเมื่อแผ่นโน้ตมาถึงแป้น",
           "hand_tip": "วางมือโดยหันฝ่ามือเข้าหากล้อง งอนิ้วเล็กน้อย แล้วยกนิ้วขึ้นทีละนิ้ว",
           "level": "ระดับ", "lv": ["ง่าย", "ปานกลาง", "ยาก"], "grade": "ผลการประเมิน",
           "g_high": "ดีมาก", "g_mid": "ดี", "g_low": "ควรฝึกเพิ่มเติม", "combo": "ต่อเนื่อง", "user": "ผู้ใช้งาน"},
    "EN": {"title": "Finger Piano Exercise", "back": "Back to menu", "choose": "Select a song", "speed": "Training speed",
           "wait": "Patient-paced mode (no misses)", "wait_on": "On", "wait_off": "Off", "play": "Start exercise",
           "best": "Best", "raise": "Please place your hand within the camera frame", "ready": "Ready to begin",
           "paused": "Paused. Please place your hand within the camera frame", "hits": "Correct",
           "again": "Repeat exercise", "songs": "Choose another song", "result": "Exercise summary", "acc": "Accuracy",
           "react": "Average reaction time", "per_finger": "Accuracy by finger", "reps": "Counted as piano-finger repetitions",
           "times": "", "sec": "s",
           "up": "Results are excellent. Consider a faster speed next time.",
           "keep": "Results are good. Continue at this speed.",
           "down": "Consider a slower speed or patient-paced mode.",
           "focus": "Finger to practise", "lift": "Lift the finger when the note reaches the key",
           "hand_tip": "Place your hand with the palm facing the camera, fingers slightly bent, and lift one finger at a time.",
           "level": "Level", "lv": ["Easy", "Moderate", "Advanced"], "grade": "Assessment",
           "g_high": "Excellent", "g_mid": "Good", "g_low": "Needs more practice", "combo": "Streak", "user": "User"},
}


# =============================================================================
# 2. OFFLINE PIANO SOUND SYNTHESIS
# =============================================================================
_note_cache: dict[int, object] = {}


def _note_sound(midi: int):
    if midi in _note_cache:
        return _note_cache[midi]
    snd = None
    try:
        import numpy as np
        import pygame
        init = pygame.mixer.get_init()
        if init:
            rate, _size, channels = init
            f = 440.0 * 2 ** ((midi - 69) / 12.0)
            dur = 1.3
            t = np.arange(int(rate * dur)) / rate
            wave = np.zeros_like(t)
            for k, amp in enumerate((1.0, 0.45, 0.25, 0.12, 0.06), start=1):
                wave += amp * np.sin(2 * np.pi * f * k * t) * np.exp(-t * (2.2 + k * 1.1))
            attack = np.minimum(1.0, t / 0.006)
            wave = wave * attack
            wave = (wave / np.max(np.abs(wave)) * 0.55 * 32767).astype(np.int16)
            data = np.column_stack([wave] * channels) if channels > 1 else wave
            snd = pygame.mixer.Sound(buffer=np.ascontiguousarray(data).tobytes())
    except Exception as e:
        print(f"[PIANO] sound synthesis unavailable: {e}")
    _note_cache[midi] = snd
    return snd


def _play_note(midi: int) -> None:
    snd = _note_sound(midi)
    if snd is not None:
        try:
            import audio
            snd.set_volume(max(0.15, getattr(audio, "sfx_vol", 0.8)))
            snd.play()
        except Exception:
            pass


# =============================================================================
# 3. SCORE FILE
# =============================================================================
def load_scores() -> list:
    try:
        with open(T.json_path("game_scores.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_score(rec: dict) -> None:
    data = load_scores()
    data.append(rec)
    try:
        with open(T.json_path("game_scores.json"), "w", encoding="utf-8") as f:
            json.dump(data[-500:], f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def best_for(song_id: str) -> int | None:
    accs = [r.get("accuracy", 0) for r in load_scores() if r.get("song") == song_id]
    return max(accs) if accs else None


def build_chart(song: dict, bpm: float) -> list[dict]:
    """Turns a melody into timed tiles and maps pitches onto 4 finger lanes."""
    beat = 60.0 / bpm
    pitches = sorted({n for n, _ in song["notes"]})
    lane_of = {p: min(3, i * 4 // len(pitches)) for i, p in enumerate(pitches)}
    t, chart = 0.0, []
    for midi, beats in song["notes"]:
        chart.append({"time": t, "midi": midi, "lane": lane_of[midi], "beats": max(0.5, beats),
                      "state": "wait", "hit_at": None})
        t += max(0.5, beats) * beat
    return chart


# =============================================================================
# 4. THE MODE
# =============================================================================
class PianoGameMode(CameraMode):
    name = "piano"

    def __init__(self, app):
        super().__init__(app)
        self.song_idx = 0
        self.speed_idx = 1
        self.wait_mode = True
        self.state = "SELECT"
        self.lane_finger = [0, 1, 2, 3]
        self.scores = [0, 0, 0, 0]
        self.armed = [True] * 4
        self.press_scores: list[int] = []
        self.hand_since = 0.0
        self.best = {s["id"]: best_for(s["id"]) for s in SONGS}

    # ── actions ─────────────────────────────────────────────────
    def handle_action(self, action: str) -> None:
        with self.lock:
            if action == "exit":
                pass
            elif action.startswith("song:"):
                self.song_idx = int(action[5:])
            elif action.startswith("speed:"):
                self.speed_idx = int(action[6:])
            elif action == "wait":
                self.wait_mode = not self.wait_mode
            elif action in ("play", "again"):
                self._new_game()
            elif action == "songs":
                self.state = "SELECT"
                self.best = {s["id"]: best_for(s["id"]) for s in SONGS}
        if action == "exit":
            self.request_exit()

    def _new_game(self) -> None:
        song = SONGS[self.song_idx]
        bpm = SPEEDS[self.speed_idx][0]
        self.beat = 60.0 / bpm
        self.window = max(0.45, 0.7 * self.beat)
        self.chart = build_chart(song, bpm)
        self.song_time = -TRAVEL_SECONDS
        self.state = "COUNTDOWN"
        self.count_t = 0.0
        self.last_now = None
        self.hits = 0
        self.combo = 0
        self.reactions: list[float] = []
        self.finger_stats = [[0, 0] for _ in range(4)]   # [hit, total] per finger
        self.effects: list[tuple] = []                   # (lane, t0)
        self.reps_credited = 0
        self.lift_count = 0
        self.armed = [True] * 4

    # ── detection ───────────────────────────────────────────────
    def _detect(self, lms):
        """Updates per-finger lift scores and returns fingers that just 'pressed'."""
        pressed = []
        for f in range(4):
            s = get_movement_accuracy("PIANO", f, 0, lms) if lms else 0
            self.scores[f] = int(0.55 * s + 0.45 * self.scores[f])
            if self.armed[f] and s >= HIT_SCORE:
                self.armed[f] = False
                pressed.append(f)
                self.press_scores.append(s)
            elif not self.armed[f] and s < HIT_SCORE - REARM_DROP:
                self.armed[f] = True
        if lms:
            # Lanes are shown left->right; follow the hand so a left hand works too.
            from logic import LI
            reverse = lms[LI.INDEX_MCP].x > lms[LI.PINKY_MCP].x
            self.lane_finger = [3, 2, 1, 0] if reverse else [0, 1, 2, 3]
        return pressed

    def _credit_rep(self) -> None:
        self.lift_count += 1
        if self.lift_count % 4 == 0:
            self.reps_credited += 1
            credit = getattr(self.app, "credit_reps", None)
            if credit:
                try:
                    recent = self.press_scores[-4:]
                    credit("PIANO", 1, acc=int(statistics.mean(recent)) if recent else None)
                except Exception:
                    pass

    # ── game step ───────────────────────────────────────────────
    def _update(self, lms, now):
        pressed = self._detect(lms)
        if self.state == "SELECT":
            return
        dt = 0.0 if self.last_now is None else min(0.1, now - self.last_now)
        self.last_now = now

        if self.state == "COUNTDOWN":
            if lms:
                self.count_t += dt
            if self.count_t >= 3.0:
                self.state = "PLAY"
            return

        if self.state != "PLAY":
            return

        if not lms:          # pause while the hand is out of view
            return

        self.song_time += dt
        pending = [n for n in self.chart if n["state"] == "wait"]
        if self.wait_mode and pending and self.song_time > pending[0]["time"]:
            self.song_time = pending[0]["time"]          # the tile waits for the patient

        for f in pressed:
            lane = self.lane_finger.index(f)
            cand = [n for n in pending if n["lane"] == lane and abs(n["time"] - self.song_time) <= self.window]
            if self.wait_mode:
                cand = [n for n in pending if n["lane"] == lane and n["time"] - self.song_time <= self.window]
            if cand and cand[0] is (pending[0] if self.wait_mode else cand[0]):
                n = cand[0]
                n["state"] = "hit"
                n["hit_at"] = now
                self.hits += 1
                self.combo += 1
                self.reactions.append(max(0.0, self.song_time - n["time"]) if not self.wait_mode
                                      else max(0.0, now - n.get("arrived", now)))
                self.finger_stats[f][0] += 1
                self.finger_stats[f][1] += 1
                self.effects.append((lane, now))
                _play_note(n["midi"])
                self._credit_rep()

        # arrival time (for reaction time in wait mode) and misses in normal mode
        for n in self.chart:
            if n["state"] == "wait" and "arrived" not in n and self.song_time >= n["time"] - 0.05:
                n["arrived"] = now
            if not self.wait_mode and n["state"] == "wait" and self.song_time - n["time"] > self.window:
                n["state"] = "miss"
                self.combo = 0
                self.finger_stats[self.lane_finger[n["lane"]]][1] += 1

        if all(n["state"] != "wait" for n in self.chart):
            self._finish(now)

    def _finish(self, now) -> None:
        self.state = "RESULT"
        total = len(self.chart)
        self.accuracy = int(round(100 * self.hits / max(1, total)))
        self.avg_react = statistics.mean(self.reactions) if self.reactions else 0.0
        rates = [(s[0] / s[1]) if s[1] else None for s in self.finger_stats]
        known = [(r, i) for i, r in enumerate(rates) if r is not None]
        self.weak_finger = min(known)[1] if known and min(known)[0] < 0.9 else None
        if self.wait_mode:
            self.advice = "up" if self.avg_react < 1.5 else ("keep" if self.avg_react < 3.5 else "down")
        else:
            self.advice = "up" if self.accuracy >= 90 else ("keep" if self.accuracy >= 60 else "down")
        song = SONGS[self.song_idx]
        _save_score({
            "date": time.strftime("%Y-%m-%d %H:%M"), "song": song["id"], "bpm": SPEEDS[self.speed_idx][0],
            "wait_mode": self.wait_mode, "accuracy": self.accuracy, "hits": self.hits, "notes": total,
            "avg_reaction_s": round(self.avg_react, 2),
            "finger_hit_rate": [None if r is None else round(r, 2) for r in rates],
            "reps_credited": self.reps_credited,
        })
        try:
            import audio
            audio.play_celebration_sound()
            audio.speak_message(TXT[self.lang][self.advice], self.lang)
        except Exception:
            pass

    # ── rendering ───────────────────────────────────────────────
    def on_frame(self, frame_bgr, lms, now, size):
        with self.lock:
            self._update(lms, now)
            W, H = size
            img, d = T.new_screen(W, H)
            self._buttons = []
            self._header(d, W, H)
            if self.state == "SELECT":
                self._render_select(img, d, frame_bgr, lms, W, H)
            elif self.state == "RESULT":
                self._render_result(img, d, frame_bgr, lms, W, H)
            else:
                self._render_play(img, d, frame_bgr, lms, now, W, H)
            return img

    def _header(self, d, W, H):
        tx = TXT[self.lang]
        title = tx["title"]
        if self.state != "SELECT":
            title += "  ·  " + SONGS[self.song_idx]["th" if self.lang == "TH" else "en"]
        user = getattr(self.app, "current_user", "") or ""
        who = f"{tx['user']}: {user}" if user else ""
        hh, back = T.draw_header(d, W, H, title, tx["back"], who, icon="note")
        self.add_button(back, "exit")
        self._hh, self._pad = hh, int(H * 0.022)

    def _render_select(self, img, d, frame_bgr, lms, W, H):
        tx = TXT[self.lang]
        th = self.lang == "TH"
        hh, pad = self._hh, self._pad
        f_mid, f_sm, f_xs = T.font(H * 0.036), T.font(H * 0.03), T.font(H * 0.026, False)
        split = int(W * 0.62)
        top = hh + pad

        # Song cards
        T.text_left(d, pad + 6, top + H * 0.03, tx["choose"], f_mid, T.R_HEADING)
        cols, gap = 2, pad
        cw = (split - pad - gap) / cols
        ch = H * 0.125
        y0 = top + H * 0.07
        for i, s in enumerate(SONGS):
            x = pad + (i % cols) * (cw + gap)
            y = y0 + (i // cols) * (ch + gap)
            box = (x, y, x + cw, y + ch)
            sel = i == self.song_idx
            T.card(d, box, fill=(232, 242, 253) if sel else T.R_SURFACE,
                   outline=T.R_PRIMARY if sel else T.R_BORDER, width=4 if sel else 2)
            T.text_left(d, x + 22, y + ch * 0.32, s["th" if th else "en"], f_sm, T.R_HEADING)
            T.text_left(d, x + 22, y + ch * 0.74, f"{tx['level']}: {tx['lv'][s['level'] - 1]}", f_xs, T.R_MUTED)
            b = self.best.get(s["id"])
            if b is not None:
                bw_ = T.text_size(d, f"{tx['best']} {b}%", f_xs)[0]
                T.text_left(d, x + cw - 22 - bw_, y + ch * 0.74, f"{tx['best']} {b}%", f_xs, T.R_SUCCESS)
            self.add_button(box, f"song:{i}")

        # Speed + wait mode
        sy = y0 + 3 * (ch + gap) + H * 0.01
        T.text_left(d, pad + 6, sy + H * 0.025, tx["speed"], f_mid, T.R_HEADING)
        bw = (split - pad - 3 * gap) / 4
        for i, (_bpm, s_th, s_en) in enumerate(SPEEDS):
            x = pad + i * (bw + gap)
            box = (x, sy + H * 0.06, x + bw, sy + H * 0.13)
            T.button(d, box, s_th if th else s_en, f_sm, "primary" if i == self.speed_idx else "secondary")
            self.add_button(box, f"speed:{i}")
        wy = sy + H * 0.16
        wbox = (pad, wy, split, wy + H * 0.075)
        T.card(d, wbox)
        T.text_left(d, pad + 22, wy + H * 0.0375, tx["wait"], f_sm, T.R_HEADING)
        tw, tgx = H * 0.1, split - H * 0.13
        on = self.wait_mode
        d.rounded_rectangle([tgx, wy + H * 0.017, tgx + tw, wy + H * 0.058], radius=int(H * 0.02),
                            fill=T.R_SUCCESS if on else (190, 199, 210))
        kx = tgx + (tw - H * 0.036 if on else H * 0.005)
        d.ellipse([kx, wy + H * 0.02, kx + H * 0.035, wy + H * 0.055], fill=(255, 255, 255))
        T.text_left(d, tgx - H * 0.08, wy + H * 0.0375, tx["wait_on"] if on else tx["wait_off"], f_sm,
                    T.R_SUCCESS if on else T.R_MUTED)
        self.add_button(wbox, "wait")

        # Right: camera + tips + play
        rx0, rx1 = split + pad, W - pad
        cam_box = (rx0, top, rx1, top + (rx1 - rx0) * 0.75)
        T.card(d, cam_box, fill=(30, 41, 56))
        T.place_camera(img, frame_bgr, (rx0 + 6, top + 6, rx1 - 6, cam_box[3] - 6), lms)
        ty = cam_box[3] + pad
        T.card(d, (rx0, ty, rx1, ty + H * 0.22))
        status = tx["ready"] if lms else tx["raise"]
        T.text_left(d, rx0 + 22, ty + H * 0.04, status, f_mid, T.R_SUCCESS if lms else T.R_WARN_TEXT)
        self._wrap(d, tx["hand_tip"], rx0 + 22, ty + H * 0.095, rx1 - rx0 - 44, f_xs, T.R_TEXT, H * 0.037)
        pbox = (rx0, H - pad - H * 0.1, rx1, H - pad)
        T.button(d, pbox, tx["play"], T.font(H * 0.04), "success")
        self.add_button(pbox, "play")

    def _render_play(self, img, d, frame_bgr, lms, now, W, H):
        tx = TXT[self.lang]
        th = self.lang == "TH"
        hh, pad = self._hh, self._pad
        split = int(W * 0.62)
        lx0, ly0, lx1, ly1 = pad, hh + pad, split, H - pad
        T.card(d, (lx0, ly0, lx1, ly1))
        lane_w = (lx1 - lx0) / 4
        key_h = H * 0.12
        hit_y = ly1 - key_h - 10
        fnames = FINGER_TH if th else FINGER_EN

        # progress bar
        done = sum(1 for n in self.chart if n["state"] != "wait")
        d.rounded_rectangle([lx0 + 16, ly0 + 12, lx1 - 16, ly0 + 22], radius=5, fill=T.R_SURFACE_ALT)
        d.rounded_rectangle([lx0 + 16, ly0 + 12, lx0 + 16 + (lx1 - lx0 - 32) * done / len(self.chart),
                             ly0 + 22], radius=5, fill=T.R_PRIMARY)

        # lanes
        for lane in range(4):
            f = self.lane_finger[lane]
            col = T.FINGER_RGB[f]
            x0 = lx0 + lane * lane_w
            tint = tuple(int(255 - (255 - c) * 0.07) for c in col)
            d.rectangle([x0 + 4, ly0 + 30, x0 + lane_w - 4, hit_y], fill=tint)

        # tiles
        px_per_s = (hit_y - (ly0 + 30)) / TRAVEL_SECONDS
        f_tile = T.font(H * 0.03)
        for n in self.chart:
            if n["state"] == "miss":
                continue
            dt = n["time"] - self.song_time
            if n["state"] == "hit":
                age = now - (n["hit_at"] or now)
                if age > 0.35:
                    continue
            y_bot = hit_y - dt * px_per_s
            tile_h = max(H * 0.07, n["beats"] * self.beat * px_per_s * 0.82)
            y_top = y_bot - tile_h
            if y_bot < ly0 + 30 or y_top > hit_y + 4:
                continue
            x0 = lx0 + n["lane"] * lane_w
            col = T.FINGER_RGB[self.lane_finger[n["lane"]]]
            if n["state"] == "hit":
                col = tuple(min(255, c + 90) for c in col)
            ty0, ty1 = max(ly0 + 30, y_top), min(y_bot, hit_y)
            if ty1 - ty0 < 8:
                continue
            rad = max(0, min(16, int((ty1 - ty0) / 2) - 2))
            d.rounded_rectangle([x0 + 14, int(ty0), int(x0 + lane_w - 14), int(ty1)], radius=rad, fill=col)
            name = NOTE_NAMES_TH.get(n["midi"] % 12, "") if th else \
                ["C", "", "D", "", "E", "F", "", "G", "", "A", "", "B"][n["midi"] % 12]
            if y_bot - 30 > ly0 + 40:
                T.text_center(d, x0 + lane_w / 2, min(y_bot, hit_y) - H * 0.03, name, f_tile, (255, 255, 255))

        # keys (one per finger) with live lift meter
        f_key = T.font(H * 0.03)
        nxt = next((n for n in self.chart if n["state"] == "wait"), None)
        for lane in range(4):
            f = self.lane_finger[lane]
            col = T.FINGER_RGB[f]
            x0 = lx0 + lane * lane_w
            kb = (x0 + 8, hit_y + 4, x0 + lane_w - 8, ly1 - 8)
            lit = self.scores[f] >= HIT_SCORE
            fill = col if lit else (250, 251, 253)
            d.rounded_rectangle(kb, radius=16, fill=fill, outline=col, width=5)
            if nxt is not None and nxt["lane"] == lane and nxt["time"] - self.song_time < 0.6:
                d.rounded_rectangle([kb[0] - 4, kb[1] - 4, kb[2] + 4, kb[3] + 4], radius=18,
                                    outline=T.R_WARN, width=4)
            T.text_center(d, (kb[0] + kb[2]) / 2, (kb[1] + kb[3]) / 2, fnames[f], f_key,
                          (255, 255, 255) if lit else col)

        # hit feedback: a single expanding ring on the key (no pop-up words)
        self.effects = [e for e in self.effects if now - e[1] < 0.7]
        for lane, t0 in self.effects:
            a = (now - t0) / 0.7
            cx = lx0 + lane * lane_w + lane_w / 2
            r = H * 0.03 + a * H * 0.05
            d.ellipse([cx - r, hit_y - r * 0.4, cx + r, hit_y + r * 0.4],
                      outline=T.FINGER_RGB[self.lane_finger[lane]], width=3)

        # countdown / pause overlays on the lanes
        cxm, cym = (lx0 + lx1) / 2, (ly0 + hit_y) / 2
        if self.state == "COUNTDOWN":
            msg = str(3 - int(self.count_t)) if lms else tx["raise"]
            fnt = T.font(H * 0.16) if lms else T.font(H * 0.036)
            d.rounded_rectangle([cxm - W * 0.22, cym - H * 0.12, cxm + W * 0.22, cym + H * 0.12], radius=12,
                                fill=(255, 255, 255), outline=T.R_PRIMARY, width=3)
            T.text_center(d, cxm, cym - (H * 0.02 if lms else 0), msg, fnt, T.R_PRIMARY)
            if lms:
                T.text_center(d, cxm, cym + H * 0.08, tx["lift"], T.font(H * 0.026, False), T.R_TEXT)
        elif not lms:
            d.rounded_rectangle([cxm - W * 0.27, cym - H * 0.07, cxm + W * 0.27, cym + H * 0.07], radius=12,
                                fill=(255, 255, 255), outline=T.R_WARN, width=3)
            T.text_center(d, cxm, cym, tx["paused"], T.font(H * 0.03), T.R_WARN_TEXT)

        # right panel: camera, finger meters, score
        rx0, rx1 = split + pad, W - pad
        cam_bot = hh + pad + (rx1 - rx0) * 0.75
        T.card(d, (rx0, hh + pad, rx1, cam_bot), fill=(30, 41, 56))
        T.place_camera(img, frame_bgr, (rx0 + 6, hh + pad + 6, rx1 - 6, cam_bot - 6), lms)

        mb = (rx0, cam_bot + pad, rx1, cam_bot + pad + H * 0.225)
        T.card(d, mb)
        bar_w = (rx1 - rx0 - 60) / 4
        base = mb[3] - H * 0.05
        top = mb[1] + H * 0.03
        thr_y = base - (base - top) * HIT_SCORE / 100
        for lane in range(4):
            f = self.lane_finger[lane]
            bx = rx0 + 30 + lane * bar_w
            d.rounded_rectangle([bx + 10, top, bx + bar_w - 10, base], radius=10, fill=T.R_SURFACE_ALT)
            hgt = (base - top) * min(100, self.scores[f]) / 100
            if hgt > 4:
                d.rounded_rectangle([bx + 10, base - hgt, bx + bar_w - 10, base], radius=10, fill=T.FINGER_RGB[f])
            T.text_center(d, bx + bar_w / 2, base + H * 0.026, fnames[f], T.font(H * 0.024, False), T.R_TEXT)
        d.line([rx0 + 30, thr_y, rx1 - 30, thr_y], fill=T.R_WARN, width=2)

        sb = (rx0, mb[3] + pad, rx1, H - pad)
        T.card(d, sb)
        total = len(self.chart)
        T.text_left(d, rx0 + 24, sb[1] + (sb[3] - sb[1]) * 0.32, f"{tx['hits']}:  {self.hits} / {total}",
                    T.font(H * 0.038), T.R_HEADING)
        if self.combo >= 3:
            T.text_left(d, rx0 + 24, sb[1] + (sb[3] - sb[1]) * 0.74, f"{tx['combo']}: {self.combo}",
                        T.font(H * 0.026, False), T.R_SUCCESS)

    def _render_result(self, img, d, frame_bgr, lms, W, H):
        tx = TXT[self.lang]
        th = self.lang == "TH"
        hh, pad = self._hh, self._pad
        box = (W * 0.14, hh + pad, W * 0.86, H - pad - H * 0.13)
        T.card(d, box)
        cx = (box[0] + box[2]) / 2
        T.text_center(d, cx, box[1] + H * 0.05, tx["result"], T.font(H * 0.04), T.R_HEADING)
        if self.accuracy >= 90:
            g_text, g_col = tx["g_high"], T.R_SUCCESS
        elif self.accuracy >= 65:
            g_text, g_col = tx["g_mid"], T.R_PRIMARY
        else:
            g_text, g_col = tx["g_low"], T.R_WARN_TEXT
        T.text_center(d, cx, box[1] + H * 0.125, f"{tx['grade']}:  {g_text}", T.font(H * 0.04), g_col)
        T.text_center(d, cx, box[1] + H * 0.225, f"{tx['acc']}  {self.accuracy}%", T.font(H * 0.056), T.R_HEADING)
        f_sm, f_xs = T.font(H * 0.03), T.font(H * 0.026, False)
        T.text_center(d, cx, box[1] + H * 0.30,
                      f"{tx['react']}:  {self.avg_react:.1f} {tx['sec']}", f_xs, T.R_TEXT)
        T.text_center(d, cx, box[1] + H * 0.34,
                      f"{tx['reps']}:  {self.reps_credited} {tx['times']}".rstrip(), f_xs, T.R_TEXT)

        # per finger bars
        fy = box[1] + H * 0.385
        T.text_left(d, box[0] + 40, fy + H * 0.02, tx["per_finger"], f_sm, T.R_HEADING)
        fnames = FINGER_TH if th else FINGER_EN
        bw = (box[2] - box[0] - 80) / 4
        for f in range(4):
            hit, tot = self.finger_stats[f]
            rate = hit / tot if tot else None
            bx = box[0] + 40 + f * bw
            by0, by1 = fy + H * 0.06, fy + H * 0.1
            d.rounded_rectangle([bx + 8, by0, bx + bw - 8, by1], radius=12, fill=T.R_SURFACE_ALT)
            if rate:
                d.rounded_rectangle([bx + 8, by0, bx + 8 + (bw - 16) * rate, by1], radius=12, fill=T.FINGER_RGB[f])
            label = f"{fnames[f]}  {int(rate * 100)}%" if rate is not None else f"{fnames[f]}  -"
            T.text_center(d, bx + bw / 2, by1 + H * 0.03, label, f_xs, T.R_TEXT)
        msg = tx[self.advice]
        if self.weak_finger is not None:
            msg += f"   ·   {tx['focus']}: {fnames[self.weak_finger]}"
        T.text_center(d, cx, box[3] - H * 0.05, msg, f_xs,
                      T.R_SUCCESS if self.advice == "up" else T.R_WARN_TEXT if self.advice == "down" else T.R_PRIMARY)

        bw2 = W * 0.22
        y0, y1 = H - pad - H * 0.1, H - pad
        for i, (action, label, style) in enumerate([("songs", tx["songs"], "secondary"),
                                                    ("again", tx["again"], "success")]):
            x = cx - bw2 - pad / 2 + i * (bw2 + pad)
            b = (x, y0, x + bw2, y1)
            T.button(d, b, label, T.font(H * 0.03), style)
            self.add_button(b, action)

    # ── small drawing helpers ───────────────────────────────────
    @staticmethod
    def _wrap(d, text, x, y, width, fnt, fill, line_h):
        words, line = text.split(" "), ""
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
