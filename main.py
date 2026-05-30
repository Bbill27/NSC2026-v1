"""
CerebroMotion Clinical Suite - Main Application Controller
Handles the core application lifecycle, OpenCV camera feed, state management, and 10-exercise clinical tracking.
"""

# =============================================================================
# 1. IMPORTS
# =============================================================================
print("[BOOT 1/7] Loading standard libraries...")
import os
import sys
import time
import math
import json
import queue
import threading
import traceback
import tkinter as tk

print("[BOOT 2/7] Loading local utilities...")
from utils import (
    ensure_single_instance, resource_path,
    _ensure_cv2, _ensure_np, _ensure_pil, _ensure_mp, get_distance_2d
)
from audio import (
    play_success_sound, play_celebration_sound, start_bgm,
    play_menu_click_sound, play_exit_reset_sound
)

print("[BOOT 3/7] Loading AI & Logic modules...")
from vision import (
    prewarm_libs, HandStabilizer, draw_skeleton,
    _prewarm_done, _detector_ready, _prebuilt_detector
)
from logic import (
    get_therapy_day, get_movement_accuracy, evaluate_adaptive_difficulty,
    HandGeometry, KinematicAnalyzer, CoachStateMachine,
    _score_squeeze_closed, _score_squeeze_open
)

print("[BOOT 4/7] Loading UI modules...")
from ui import (
    init_tkinter_ui, recalc_ui_metrics, populate_dashboard,
    draw_dashboard, show_session_summary, LANG
)
from login import LoginScreen

# =============================================================================
# 2. MAIN APPLICATION CLASS
# =============================================================================
class RehabApp:
    # --- The Complete 10-Exercise Arsenal ---
    _EXERCISES = [
        ("SQUEEZE", "1. Open/Close Fist"),
        ("THUMB", "2. Thumb Taps"),
        ("WIPER", "3. Hand Wiper"),
        ("FLIP", "4. Palm Up/Down"),
        ("TABLETOP", "5. L-Shape Hand"),
        ("SCISSOR", "6. Finger Spread"),
        ("HOOK", "7. The Claw"),
        ("WRIST", "8. Wrist Bend"),
        ("PIANO", "9. Piano Fingers"),
        ("HITCH", "10. Hitchhiker")
    ]

    def __init__(self, root):
        print("[APP INIT] Setting up window...")
        self.root = root
        self.root.title("CerebroMotion Clinical Suite v1.0")
        self.root.configure(bg="#1e272e")
        self.root.attributes('-fullscreen', True)
        self.root.geometry("1024x768")
        self.root.minsize(800, 600)

        self.render_w = self.root.winfo_screenwidth()
        self.render_h = self.root.winfo_screenheight()

        self.ui = {}
        self._ui_text_cache = {}
        recalc_ui_metrics(self)

        self.stabilizer = HandStabilizer()
        self.kinematics = KinematicAnalyzer(window=8)
        self.coach_engine = CoachStateMachine()

        # Initialize the fatigue assessment engine
        from fatigue_detector import FatigueDetector
        self.fatigue_detector = FatigueDetector()

        self.last_correct_time = time.time()

        self.cap = None
        self.detector = None
        self.cam_thread = None
        self.running = True
        self.in_therapy = False

        self.frame_queue = queue.Queue(maxsize=1)
        self.frame_count = 0
        self._canvas_buf = None
        self._overlay_buf = None

        # Session Variables
        self.current_exercise = "SQUEEZE"
        self.last_timestamp_ms = 0
        self.hold_duration = 0.5
        self.show_celebration = False
        self.celebration_timer = 0
        self.last_correct_time = time.time()
        self.current_accuracy = 0
        self.hold_start_time = 0
        self.coach_msg = ""
        self.coach_msg_type = "neutral"

        # [FIX 4]: Reset clinical fatigue state for the new exercise
        if hasattr(self, 'fatigue_detector'):
            self.fatigue_detector.last_state = ""
            self.fatigue_detector.state_start_time = time.time()
            self.fatigue_detector.rep_durations.clear()
            self.fatigue_detector.baseline_speed = 0.0
        self.session_reps = 0
        self.prev_palm_pos = None
        self.smooth_acc = 0

        # Init accuracy tracking
        self.rep_acc_sum = 0
        self.rep_acc_frames = 0

        # Goal Tracking & Progress Dictionaries (Expanded for 10 Exercises)
        self.exercise_keys = ["SQUEEZE", "THUMB", "WIPER", "FLIP", "TABLETOP", "SCISSOR", "HOOK", "WRIST", "PIANO",
                              "HITCH"]
        self.session_acc = {ex: {"sum": 0, "frames": 0} for ex in self.exercise_keys}
        self.daily_acc = {f"{ex.lower()}_acc": 0 for ex in self.exercise_keys}

        # 10-Exercise State Machines & Goals (Standardized for AI Mapping)
        self.sq_state, self.squeeze_goal = "WAITING_FOR_FIST", (3, 20)

        self.thumb_targets = [8, 12, 16, 20]
        self.thumb_names = ["INDEX", "MIDDLE", "RING", "PINKY"]
        self.curr_thumb_idx, self.thumb_goal = 0, (3, 20)

        self.wiper_state, self.wiper_goal = "WAITING_FOR_LEFT", (3, 15)
        self.flip_state, self.flip_goal = "WAITING_FOR_UP", (3, 15)
        self.table_state, self.tabletop_goal = "WAITING_FOR_FIST", (3, 15)
        self.scissor_state, self.scissor_goal = "WAITING_FOR_RELAX", (4, 15)
        self.hook_state, self.hook_goal = "WAITING_FOR_RELAX", (3, 15)
        self.wrist_state, self.wrist_goal = "WAITING_FOR_UP", (3, 15)

        self.curr_piano_idx, self.piano_goal = 0, (3, 20)
        self.hitch_state, self.hitch_goal = "WAITING_FOR_FIST", (3, 10)

        # Reps and Sets Counters
        self.reps_data = {ex: 0 for ex in self.exercise_keys}
        self.sets_data = {ex: 0 for ex in self.exercise_keys}

        self.save_file = resource_path("rehab_progress.json")
        self._last_save = 0

        # Bindings
        self.root.bind("<Escape>", self._exit_fullscreen)
        self.root.bind("<Configure>", self._check_maximize)
        self.root.bind("<FocusOut>", self._on_focus_out)
        self.root.bind("<FocusIn>", self._on_focus_in)

        print("[APP INIT] Loading progress from JSON...")
        self.load_progress()
        print("[APP INIT] Initializing Tkinter UI...")
        init_tkinter_ui(self)

        print("[APP INIT] Applying AI Adaptive Difficulty...")
        self.apply_adaptive_goals()

        print("[APP INIT] Starting Backend AI Thread...")
        threading.Thread(target=self._init_backend, daemon=True).start()

    # =============================================================================
    # 3. WINDOW & EVENT HANDLERS
    # =============================================================================
    def _exit_fullscreen(self, event=None):
        self.root.attributes("-fullscreen", False)
        self.root.state('normal')

    def _check_maximize(self, event=None):
        if event and event.widget == self.root:
            if self.root.state() == 'zoomed':
                self.root.attributes('-fullscreen', True)

    def _on_focus_out(self, event):
        try:
            focused = self.root.focus_get()
        except KeyError:
            focused = self.root
        if focused is None:
            try:
                from audio import pause_bgm
                pause_bgm()
            except Exception: pass

    def _on_focus_in(self, event):
        try:
            from audio import unpause_bgm
            unpause_bgm()
        except Exception: pass

    def _handle_resize(self, event):
        if event.width > 100 and event.height > 100:
            self.render_w = event.width
            self.render_h = event.height
            recalc_ui_metrics(self)
            self._canvas_buf = None
            self._overlay_buf = None

    def _handle_click(self, event):
        u = self.ui
        if 0 < event.y < u['btn_h']:
            try:
                play_menu_click_sound()
            except Exception:
                pass
            idx = min(event.x // u['btn_w'], len(self._EXERCISES) - 1)
            self.current_exercise = self._EXERCISES[idx][0]
            self.hold_start_time = 0
            self.last_correct_time = time.time()

            # Wipe accuracy clean for the new exercise
            self.rep_acc_sum = 0
            self.rep_acc_frames = 0
            self.current_accuracy = 0

            # Reset clinical fatigue tracker variables for the new exercise target
            if hasattr(self, 'fatigue_detector'):
                self.fatigue_detector.last_state = ""
                self.fatigue_detector.state_start_time = time.time()
                self.fatigue_detector.rep_durations.clear()
                self.fatigue_detector.baseline_speed = 0.0
            return

        if (u['reset_x'] < event.x < u['reset_x'] + u['reset_w'] and
                u['reset_y'] < event.y < u['reset_y'] + u['reset_h']):
            try: play_exit_reset_sound()
            except Exception: pass
            self.reset_current_exercise()
            return

        if (u['menu_x'] < event.x < u['menu_x'] + u['menu_w'] and
                u['menu_y'] < event.y < u['menu_y'] + u['menu_h']):
            try: play_exit_reset_sound()
            except Exception: pass
            self.return_to_menu()
            return

    def on_close(self):
        self.running = False
        if self.cam_thread and self.cam_thread.is_alive():
            self.cam_thread.join(timeout=1.0)
        if self.cap: self.cap.release()
        try: self.detector.close()
        except Exception: pass
        self.root.destroy()

    # =============================================================================
    # 4. DATA I/O & PROGRESS TRACKING
    # =============================================================================
    def load_progress(self):
        history = {}
        if os.path.exists(self.save_file):
            try:
                with open(self.save_file) as f:
                    history = json.load(f)
            except Exception: pass

        day = history.get(get_therapy_day(), {})
        for ex in self.exercise_keys:
            self.reps_data[ex] = day.get(f"{ex.lower()}_reps", 0)
            self.sets_data[ex] = day.get(f"{ex.lower()}_sets", 0)
            self.daily_acc[f"{ex.lower()}_acc"] = day.get(f"{ex.lower()}_acc", 0)

    def save_progress(self, force=False):
        now = time.time()
        if not force and now - self._last_save < 1.0: return
        self._last_save = now

        for ex in self.exercise_keys:
            if self.session_acc[ex]["frames"] > 0:
                self.daily_acc[f"{ex.lower()}_acc"] = int(self.session_acc[ex]["sum"] / self.session_acc[ex]["frames"])

        today = get_therapy_day()
        history = {}
        if os.path.exists(self.save_file):
            try:
                with open(self.save_file) as f:
                    history = json.load(f)
                if "date" in history:
                    old = history.pop("date", today)
                    history = {old: history}
            except Exception: pass

        day_data = {}
        for ex in self.exercise_keys:
            day_data[f"{ex.lower()}_reps"] = self.reps_data[ex]
            day_data[f"{ex.lower()}_sets"] = self.sets_data[ex]
            day_data[f"{ex.lower()}_acc"] = self.daily_acc[f"{ex.lower()}_acc"]

        history[today] = day_data

        try:
            with open(self.save_file, "w") as f:
                json.dump(history, f, indent=2)
        except Exception: pass

    def apply_adaptive_goals(self):
        """Fetches smart goals from logic.py and overwrites the hardcoded defaults."""
        history = {}
        if os.path.exists(self.save_file):
            try:
                with open(self.save_file) as f:
                    history = json.load(f)
            except Exception:
                pass

        # 1. Ask logic.py to analyze the patient's history and generate custom goals
        lang = getattr(self, 'current_lang', 'EN')
        _, new_goals, reason = evaluate_adaptive_difficulty(history, False, lang)

        # 2. Overwrite the state machine variables dynamically
        self.squeeze_goal = tuple(new_goals.get("squeeze", (3, 20)))
        self.thumb_goal = tuple(new_goals.get("thumb", (3, 20)))
        self.wiper_goal = tuple(new_goals.get("wiper", (3, 15)))
        self.flip_goal = tuple(new_goals.get("flip", (3, 15)))
        self.tabletop_goal = tuple(new_goals.get("tabletop", (3, 15)))
        self.scissor_goal = tuple(new_goals.get("scissor", (4, 15)))
        self.hook_goal = tuple(new_goals.get("hook", (3, 15)))
        self.wrist_goal = tuple(new_goals.get("wrist", (3, 15)))
        self.piano_goal = tuple(new_goals.get("piano", (3, 20)))
        self.hitch_goal = tuple(new_goals.get("hitch", (3, 10)))

        print(f"[AI CLINIC] {reason}")

    # =============================================================================
    # 5. UI NAVIGATION HELPERS
    # =============================================================================
    def show_credits(self):
        self.menu_frame.place_forget()
        self.credits_frame.place(relx=0.5, rely=0.5, anchor="center")

    def hide_credits(self):
        self.credits_frame.place_forget()
        self.menu_frame.place(relx=0.5, rely=0.5, anchor="center")

    def show_coming_soon(self):
        self.menu_frame.place_forget()
        self.coming_soon_frame.place(relx=0.5, rely=0.5, anchor="center")
        if hasattr(self, 'tut_player'): self.tut_player.start()

    def hide_coming_soon(self):
        self.coming_soon_frame.place_forget()
        self.menu_frame.place(relx=0.5, rely=0.5, anchor="center")

    def show_dashboard(self):
        self.menu_frame.place_forget()
        populate_dashboard(self)
        self.dashboard_frame.place(relx=0.5, rely=0.5, anchor="center")

    def hide_dashboard(self):
        self.dashboard_frame.place_forget()
        self.menu_frame.place(relx=0.5, rely=0.5, anchor="center")

    def show_settings(self):
        self.menu_frame.place_forget()
        self.settings_frame.place(relx=0.5, rely=0.5, anchor="center")

    def hide_settings(self):
        self.settings_frame.place_forget()
        self.menu_frame.place(relx=0.5, rely=0.5, anchor="center")

    # =============================================================================
    # 6. AI & SYSTEM BOOT SEQUENCE
    # =============================================================================
    def _init_backend(self):
        print("[BACKEND] Thread started. Waiting for libs...")
        try:
            if not _prewarm_done.is_set(): _prewarm_done.wait()
            _detector_ready.wait()

            if _prebuilt_detector is not None:
                self.detector = _prebuilt_detector
            else:
                from mediapipe.tasks import python as mp_python
                from mediapipe.tasks.python import vision
                import urllib.request

                model_path = resource_path(os.path.join("assets", "hand_landmarker.task"))
                if os.path.exists(model_path) and os.path.getsize(model_path) < 1000000:
                    os.remove(model_path)

                if not os.path.exists(model_path):
                    os.makedirs(os.path.dirname(model_path), exist_ok=True)
                    urllib.request.urlretrieve(
                        "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
                        model_path)

                base_opts = mp_python.BaseOptions(model_asset_path=model_path)
                options = vision.HandLandmarkerOptions(
                    base_options=base_opts, num_hands=1,
                    min_hand_detection_confidence=0.65,
                    min_hand_presence_confidence=0.65,
                    min_tracking_confidence=0.65,
                    running_mode=vision.RunningMode.VIDEO,
                )
                self.detector = vision.HandLandmarker.create_from_options(options)

            self.root.after(0, self._on_backend_ready)
        except Exception as e:
            print(f"[BACKEND ERROR] {e}")

    def _on_backend_ready(self):
        if hasattr(self, 'start_btn'):
            lang = getattr(self, 'current_lang', 'EN')
            self.start_btn.config(
                state="normal", text="START THERAPY SESSION" if lang == "EN" else "เริ่มการบำบัด",
                bg="#10b981", fg="white", cursor="hand2",
            )
            self.start_btn.update()
        else:
            self.root.after(100, self._on_backend_ready)

    def start_therapy(self):
        total_sets_today = sum(self.sets_data.values())
        if total_sets_today >= 12:
            lang = getattr(self, 'current_lang', 'EN')
            msg = "SAFETY LOCK: Daily limit reached. Please rest." if lang == "EN" else "แจ้งเตือนความปลอดภัย: ถึงขีดจำกัดแล้ว"
            self.start_btn.config(text=msg, bg="#e74c3c", state="disabled")
            return

        if self.start_btn['state'] in ('normal', 'active'):
            self.start_btn.config(state="disabled", text="OPENING CAMERA...", bg="#475569")
            self.start_btn.update()
            threading.Thread(target=self._open_camera_and_start, daemon=True).start()

    def _open_camera_and_start(self):
        cv2 = _ensure_cv2()
        self.cap = cv2.VideoCapture(0)
        time.sleep(1.0)
        success = False
        for _ in range(5):
            success, _ = self.cap.read()
            if success: break
            time.sleep(0.1)

        if not success:
            if self.cap: self.cap.release()
            self.cap = None
            self.root.after(0, self._camera_failed)
            return
        self.root.after(0, self._begin_therapy_session)

    def _camera_failed(self):
        self.start_btn.config(text="CAMERA ERROR - TRY AGAIN", bg="#e74c3c", state="normal")

    def _begin_therapy_session(self):
        self.in_therapy = True
        self.last_correct_time = time.time()
        self.menu_frame.place_forget()
        self.video_frame.pack(fill="both", expand=True)
        self.cam_thread = threading.Thread(target=self.camera_loop, daemon=True)
        self.cam_thread.start()
        self.update_gui()

    # =============================================================================
    # 7. THERAPY STATE & TIMERS
    # =============================================================================
    def return_to_menu(self):
        # 1. Tell the background thread to stop tracking
        self.in_therapy = False

        # 2. Physically release the webcam hardware to save battery!
        if self.cap is not None:
            self.cap.release()
            self.cap = None

        # 3. Hide the video screen and restore the menu button
        self.video_frame.pack_forget()
        lang = getattr(self, 'current_lang', 'EN')
        self.start_btn.config(
            text="START THERAPY SESSION" if lang == "EN" else "เริ่มการบำบัด",
            bg="#10b981", state="normal", cursor="hand2",
        )
        self.menu_frame.place(relx=0.5, rely=0.5, anchor="center")

        # 4. Show the score popup
        show_session_summary(self)

    def reset_current_exercise(self):
        ex = self.current_exercise
        self.reps_data[ex] = 0
        self.sets_data[ex] = 0

        if ex == "SQUEEZE": self.sq_state = "WAITING_FOR_FIST"
        elif ex == "THUMB": self.curr_thumb_idx = 0
        elif ex == "WIPER":
            self.wiper_state = "WAITING_FOR_LEFT"
        elif ex == "FLIP":
            self.flip_state = "WAITING_FOR_UP"
        elif ex == "TABLETOP":
            self.table_state = "WAITING_FOR_FIST"
        elif ex == "SCISSOR":
            self.scissor_state = "WAITING_FOR_RELAX"
        elif ex == "HOOK": self.hook_state = "WAITING_FOR_RELAX"
        elif ex == "WRIST": self.wrist_state = "WAITING_FOR_UP"
        elif ex == "PIANO": self.curr_piano_idx = 0
        elif ex == "HITCH": self.hitch_state = "WAITING_FOR_FIST"

        self.hold_start_time = 0
        self.last_correct_time = time.time()

        self.rep_acc_sum = 0
        self.rep_acc_frames = 0
        self.current_accuracy = 0

        self.save_progress(force=True)

        # Reset fatigue history when manually wiping progress metrics
        if hasattr(self, 'fatigue_detector'):
            self.fatigue_detector.last_state = ""
            self.fatigue_detector.state_start_time = time.time()
            self.fatigue_detector.rep_durations.clear()
            self.fatigue_detector.baseline_speed = 0.0

    def _process_timers(self):
        t = time.time()
        # Prevent AttributeError if not initialized
        if not hasattr(self, "rep_acc_sum"): self.rep_acc_sum = 0
        if not hasattr(self, "rep_acc_frames"): self.rep_acc_frames = 0

        if self.hold_start_time == 0:
            self.hold_start_time = t
            return
        if t - self.hold_start_time < self.hold_duration:
            return

        self.hold_start_time = 0
        self.session_reps += 1
        ex = self.current_exercise

        # SAFETY CHECK: Ensure the exercise key exists in the dictionary!
        if ex not in self.session_acc:
            self.session_acc[ex] = {"sum": 0, "frames": 0}

        frames = getattr(self, "rep_acc_frames", 1)
        self.session_acc[ex]["sum"] += int(getattr(self, "rep_acc_sum", 100) / max(1, frames))
        self.session_acc[ex]["frames"] += 1
        self.rep_acc_sum, self.rep_acc_frames = 0, 0

        goal = getattr(self, f"{ex.lower()}_goal", (3, 15))

        # -------------------------------------------------------------
        # 10-EXERCISE STATE TOGGLE (Hardcoded to prevent crashes!)
        # -------------------------------------------------------------
        if ex == "THUMB":
            self.curr_thumb_idx = (self.curr_thumb_idx + 1) % 4
            if self.curr_thumb_idx == 0: self.reps_data[ex] += 1
        elif ex == "PIANO":
            self.curr_piano_idx = (self.curr_piano_idx + 1) % 4
            if self.curr_piano_idx == 0: self.reps_data[ex] += 1
        elif ex == "SQUEEZE":
            if getattr(self, 'sq_state', '') == "WAITING_FOR_FIST":
                self.sq_state = "WAITING_FOR_OPEN"
            else:
                self.sq_state = "WAITING_FOR_FIST"
                self.reps_data[ex] += 1
        elif ex == "WIPER":
            if getattr(self, 'wiper_state', '') == "WAITING_FOR_LEFT":
                self.wiper_state = "WAITING_FOR_RIGHT"
            else:
                self.wiper_state = "WAITING_FOR_LEFT"
                self.reps_data[ex] += 1
        elif ex == "FLIP":
            if getattr(self, 'flip_state', '') == "WAITING_FOR_UP":
                self.flip_state = "WAITING_FOR_DOWN"
            else:
                self.flip_state = "WAITING_FOR_UP"
                self.reps_data[ex] += 1
        elif ex == "TABLETOP":
            if getattr(self, 'table_state', '') == "WAITING_FOR_FIST":
                self.table_state = "WAITING_FOR_LSHAPE"
            else:
                self.table_state = "WAITING_FOR_FIST"
                self.reps_data[ex] += 1
        elif ex == "SCISSOR":
            if getattr(self, 'scissor_state', '') == "WAITING_FOR_RELAX":
                self.scissor_state = "WAITING_FOR_SPREAD"
            else:
                self.scissor_state = "WAITING_FOR_RELAX"
                self.reps_data[ex] += 1
        elif ex == "HOOK":
            if getattr(self, 'hook_state', '') == "WAITING_FOR_RELAX":
                self.hook_state = "WAITING_FOR_HOOK"
            else:
                self.hook_state = "WAITING_FOR_RELAX"
                self.reps_data[ex] += 1
        elif ex == "WRIST":
            if getattr(self, 'wrist_state', '') == "WAITING_FOR_UP":
                self.wrist_state = "WAITING_FOR_DOWN"
            else:
                self.wrist_state = "WAITING_FOR_UP"
                self.reps_data[ex] += 1
        elif ex == "HITCH":
            if getattr(self, 'hitch_state', '') == "WAITING_FOR_FIST":
                self.hitch_state = "WAITING_FOR_HITCH"
            else:
                self.hitch_state = "WAITING_FOR_FIST"
                self.reps_data[ex] += 1

        # Check Sets
        if self.reps_data[ex] >= goal[1]:
            self.sets_data[ex] += 1
            self.reps_data[ex] = 0

        self.save_progress()
        try:
            from audio import play_success_sound
            play_success_sound()
        except Exception:
            pass

    # =============================================================================
    # 8. HUD & UI OVERLAY
    # =============================================================================
    def _draw_ui(self, canvas):
        draw_dashboard(self, canvas)

    def _get_current_ui_text(self):
        ex = self.current_exercise
        reps = self.reps_data.get(ex, 0)
        sets = self.sets_data.get(ex, 0)
        goal = getattr(self, f"{ex.lower()}_goal", (3, 15))
        lang = getattr(self, 'current_lang', 'EN')

        # Hardcoded foolproof translations
        if lang == "TH":
            inst_map = {
                "SQUEEZE": "1. กำมือ" if getattr(self, 'sq_state', '') == "WAITING_FOR_FIST" else "2. แบมือ",
                "THUMB": f"แตะนิ้ว {['ชี้', 'กลาง', 'นาง', 'ก้อย'][getattr(self, 'curr_thumb_idx', 0)]}",
                "WIPER": "1. เอียงซ้าย" if getattr(self, 'wiper_state', '') == "WAITING_FOR_LEFT" else "2. เอียงขวา",
                "FLIP": "1. หงายมือ" if getattr(self, 'flip_state', '') == "WAITING_FOR_UP" else "2. คว่ำมือ",
                "TABLETOP": "1. กำมือ" if getattr(self, 'table_state', '') == "WAITING_FOR_FIST" else "2. ทำมือรูปตัว L",
                "SCISSOR": "1. รวบนิ้ว" if getattr(self, 'scissor_state', '') == "WAITING_FOR_RELAX" else "2. กางนิ้ว",
                "HOOK": "1. แบมือ" if getattr(self, 'hook_state', '') == "WAITING_FOR_RELAX" else "2. ทำตะขอ",
                "WRIST": "1. กระดกข้อมือ" if getattr(self, 'wrist_state', '') == "WAITING_FOR_UP" else "2. กดข้อมือ",
                "PIANO": f"ยกนิ้ว {['ชี้', 'กลาง', 'นาง', 'ก้อย'][getattr(self, 'curr_piano_idx', 0)]}",
                "HITCH": "1. กำมือ" if getattr(self, 'hitch_state', '') == "WAITING_FOR_FIST" else "2. ชูนิ้วโป้ง"
            }
            progress_text = f"เซ็ต: {sets + 1}/{goal[0]} | ครั้ง: {reps}/{goal[1]}"
        else:
            inst_map = {
                "SQUEEZE": "Make Fist" if getattr(self, 'sq_state', '') == "WAITING_FOR_FIST" else "Open Hand",
                "THUMB": f"Touch {['INDEX', 'MIDDLE', 'RING', 'PINKY'][getattr(self, 'curr_thumb_idx', 0)]}",
                "WIPER": "Wipe Left" if getattr(self, 'wiper_state', '') == "WAITING_FOR_LEFT" else "Wipe Right",
                "FLIP": "Palm Up" if getattr(self, 'flip_state', '') == "WAITING_FOR_UP" else "Palm Down",
                "TABLETOP": "Make Fist" if getattr(self, 'table_state', '') == "WAITING_FOR_FIST" else "Make L-Shape",
                "SCISSOR": "Close Fingers" if getattr(self, 'scissor_state',
                                                      '') == "WAITING_FOR_RELAX" else "Spread Fingers",
                "HOOK": "Hand Flat" if getattr(self, 'hook_state', '') == "WAITING_FOR_RELAX" else "Make Claw",
                "WRIST": "Wrist Up" if getattr(self, 'wrist_state', '') == "WAITING_FOR_UP" else "Wrist Down",
                "PIANO": f"Lift {['INDEX', 'MIDDLE', 'RING', 'PINKY'][getattr(self, 'curr_piano_idx', 0)]}",
                "HITCH": "Make Fist" if getattr(self, 'hitch_state', '') == "WAITING_FOR_FIST" else "Thumb Out"
            }
            progress_text = f"Set: {sets + 1}/{goal[0]} | Rep: {reps}/{goal[1]}"

        inst = inst_map.get(ex, "Follow Movement")
        return {"inst": inst, "progress_text": progress_text}

    def update_gui(self):
        if not self.in_therapy: return
        _, ImageTk = _ensure_pil()
        try:
            pil_img = self.frame_queue.get_nowait()
            imgtk = ImageTk.PhotoImage(image=pil_img)
            self.video_label.imgtk = imgtk
            self.video_label.configure(image=imgtk)
        except queue.Empty: pass
        self.root.after(33, self.update_gui)

    # =============================================================================
    # 9. CAMERA & AI LOOP
    # =============================================================================
    def camera_loop(self):
        cv2 = _ensure_cv2()
        np = _ensure_np()
        mp = _ensure_mp()
        Image, ImageTk = _ensure_pil()

        while self.running and self.in_therapy:
            if not self.cap or not self.cap.isOpened():
                time.sleep(0.1)
                continue

            try:
                success, raw_frame = self.cap.read()
                if not success or raw_frame is None:
                    time.sleep(0.01)
                    continue

                raw_frame = cv2.flip(raw_frame, 1)
                rgb_frame = cv2.cvtColor(cv2.resize(raw_frame, (320, 180)), cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

                ts_ms = int(time.time() * 1000)
                if ts_ms <= self.last_timestamp_ms: ts_ms = self.last_timestamp_ms + 1
                self.last_timestamp_ms = ts_ms

                result = self.detector.detect_for_video(mp_image, ts_ms)

                # Setup Canvas
                cam_h, cam_w = raw_frame.shape[:2]
                scale = min(self.render_w / cam_w, self.render_h / cam_h)
                new_w, new_h = int(cam_w * scale), int(cam_h * scale)
                need_shape = (self.render_h, self.render_w, 3)
                if self._canvas_buf is None or self._canvas_buf.shape != need_shape:
                    self._canvas_buf = np.zeros(need_shape, dtype=np.uint8)

                canvas = self._canvas_buf
                canvas[:] = 0
                y_off, x_off = (self.render_h - new_h) // 2, (self.render_w - new_w) // 2
                canvas[y_off:y_off + new_h, x_off:x_off + new_w] = cv2.resize(raw_frame, (new_w, new_h))

                raw_lms = None
                if result.hand_landmarks and (
                        not hasattr(result, 'handedness') or result.handedness[0][0].score > 0.60):
                    raw_lms = result.hand_landmarks[0]

                if raw_lms:
                    self.is_hand_visible = True  # <-- Real-time visibility tracking!
                    stable_lms = self.stabilizer.stabilize(raw_lms)
                    self.kinematics.update(stable_lms)  # <-- Restored for coaching logic
                    geo = HandGeometry.from_landmarks(stable_lms)
                    draw_skeleton(canvas[y_off:y_off + new_h, x_off:x_off + new_w], stable_lms)

                    # --- NEW SCORING LOGIC ---
                    ex = self.current_exercise
                    step = 0
                    if ex == "SQUEEZE":
                        step = 0 if self.sq_state == "WAITING_FOR_FIST" else 1
                    elif ex == "THUMB":
                        step = self.curr_thumb_idx
                    elif ex == "WIPER":
                        step = 0 if self.wiper_state == "WAITING_FOR_LEFT" else 1
                    elif ex == "FLIP":
                        step = 0 if self.flip_state == "WAITING_FOR_UP" else 1
                    elif ex == "TABLETOP":
                        step = 0 if self.table_state == "WAITING_FOR_FIST" else 1
                    elif ex == "SCISSOR":
                        step = 0 if self.scissor_state == "WAITING_FOR_RELAX" else 1
                    elif ex == "HOOK":
                        step = 0 if self.hook_state == "WAITING_FOR_RELAX" else 1
                    elif ex == "WRIST":
                        step = 0 if self.wrist_state == "WAITING_FOR_UP" else 1
                    elif ex == "PIANO":
                        step = self.curr_piano_idx
                    elif ex == "HITCH":
                        step = 0 if self.hitch_state == "WAITING_FOR_FIST" else 1

                    raw_acc = get_movement_accuracy(ex, step, 0, stable_lms)

                    # <-- Apply 60/40 smoothing to accuracy -->
                    if not hasattr(self, 'smooth_acc'): self.smooth_acc = raw_acc
                    self.smooth_acc = int(0.60 * raw_acc + 0.40 * self.smooth_acc)
                    self.current_accuracy = self.smooth_acc

                    # 1. Lower threshold to 70% and untie from steadiness
                    posture_correct = raw_acc >= 70

                    # 2. Extract clinical state machine string
                    state_attr_map = {
                        "SQUEEZE": "sq_state",
                        "TABLETOP": "table_state",
                    }
                    state_attr = state_attr_map.get(ex, f"{ex.lower()}_state")
                    current_state = getattr(self, state_attr, "") if ex not in ("THUMB", "PIANO") else f"STEP_{step}"

                    # 3. Call fatigue detector analysis
                    is_locked, fatigue_msg, fatigue_color = self.fatigue_detector.check_fatigue(
                        current_state=current_state,
                        current_lang=getattr(self, 'current_lang', 'EN'),
                        hand_visible=True
                    )

                    if is_locked:
                        # HIGH FATIGUE: Enforce hard safety lock and block progress
                        self.hold_start_time = 0
                        self.coach_msg = fatigue_msg
                        self.coach_msg_type = fatigue_color
                    else:
                        # NORMAL GAME ENGINE: Process exercise frames
                        if posture_correct:
                            self.rep_acc_sum += raw_acc
                            self.rep_acc_frames += 1
                            self._process_timers()

                            lang = getattr(self, 'current_lang', 'EN')
                            self.coach_msg = LANG[lang].get("coach_hold_steady", "Hold steady")
                            self.coach_msg_type = "good"
                        else:
                            self.hold_start_time = 0
                            lang = getattr(self, 'current_lang', 'EN')

                            # <-- Fixed Coaching Call and Guard -->
                            result = self.coach_engine.get_feedback(ex, step, geo, self.kinematics)
                            if result is not None:
                                coach_key, coach_sev = result
                                self.coach_msg = LANG[lang].get(coach_key, coach_key)
                                self.coach_msg_type = coach_sev

                        # MODERATE FATIGUE OVERRIDE: Inject warning message over normal engine
                        if fatigue_msg:
                            self.coach_msg = fatigue_msg
                            self.coach_msg_type = fatigue_color


                else:

                    self.is_hand_visible = False  # <-- Real-time visibility tracking!

                    # HAND IS OUT OF FRAME: Keep updating the countdown timer if locked!

                    if hasattr(self, 'fatigue_detector'):
                        is_locked, fatigue_msg, fatigue_color = self.fatigue_detector.check_fatigue(
                            current_state="NO_HAND",
                            current_lang=getattr(self, 'current_lang', 'EN'),
                            hand_visible=False
                        )
                        # If we are locked out, ensure the UI gets the updated countdown text
                        if is_locked:
                            self.coach_msg = fatigue_msg
                            self.coach_msg_type = fatigue_color
                    self.hold_start_time = 0  # Reset rep timer so they don't get free reps
                self._draw_ui(canvas)
                pil_img = Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))
                if self.frame_queue.full():
                    try:
                        self.frame_queue.get_nowait()
                    except queue.Empty:
                        pass
                self.frame_queue.put_nowait(pil_img)
            except Exception as e:
                import traceback
                print("\n=== CAMERA CRASH LOG ===")
                traceback.print_exc()
                print("========================\n")
                time.sleep(0.05)

# =============================================================================
# BOOT SEQUENCE (MUST BE FLUSH AGAINST THE LEFT WALL)
# =============================================================================
if __name__ == "__main__":
    # Temporarily bypass the stuck lockfile
    ensure_single_instance()

    prewarm_libs()
    root = tk.Tk()
    try:
        root.iconbitmap(resource_path(os.path.join('assets', 'rehab.ico')))
    except Exception:
        pass
    app = RehabApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
