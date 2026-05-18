"""
NSC Medical Suite - Main Application Controller
Handles the core application lifecycle, threading, OpenCV camera feed, and state management.
"""

# =============================================================================
# 1. IMPORTS
# =============================================================================
# Standard Library
import os
import sys
import time
import math
import json
import queue
import threading
import traceback
import tkinter as tk

# Local Utilities & Helpers
from utils import (
    ensure_single_instance, resource_path,
    _ensure_cv2, _ensure_np, _ensure_pil, _ensure_mp, get_distance_2d
)
from audio import (
    play_success_sound, play_celebration_sound, start_bgm,
    play_menu_click_sound, play_exit_reset_sound
)

# AI & Logic Modules
from vision import (
    prewarm_libs, HandStabilizer, draw_skeleton,
    _prewarm_done, _detector_ready, _prebuilt_detector
)
from logic import (
    get_therapy_day, get_movement_accuracy, evaluate_adaptive_difficulty,
    HandGeometry, KinematicAnalyzer, CoachStateMachine,
    _score_squeeze_closed, _score_squeeze_open, _score_starfish, _score_peace, _score_oring
)

# UI & Presentation
from ui import (
    init_tkinter_ui, recalc_ui_metrics, populate_dashboard,
    draw_dashboard, show_session_summary, LANG
)
from login import LoginScreen

# =============================================================================
# 2. MAIN APPLICATION CLASS
# =============================================================================
class RehabApp:
    _EXERCISES = [
        ("SQUEEZE", "1. Open/Close"), ("THUMB", "2. Thumb Tap"),
        ("STARFISH", "3. Finger Lift"), ("FLIP", "4. Wrist Twist"),
        ("O_RING", "5. Air Grasp"), ("PEACE", "6. Sim Tasks")
    ]

    def __init__(self, root):
        # ---------------------------------------------------------
        # A. Window Setup
        # ---------------------------------------------------------
        self.root = root
        self.root.title("CerebroMotion Clinical Suite v1.0")
        self.root.configure(bg="#1e272e")
        self.root.attributes('-fullscreen', True)
        self.root.geometry("1024x768")
        self.root.minsize(800, 600)

        self.render_w = self.root.winfo_screenwidth()
        self.render_h = self.root.winfo_screenheight()

        # ---------------------------------------------------------
        # B. UI State & Caching
        # ---------------------------------------------------------
        self.ui = {}
        self._ui_text_cache = {}
        recalc_ui_metrics(self)

        # ---------------------------------------------------------
        # C. AI, Kinematics & Threading
        # ---------------------------------------------------------
        self.stabilizer = HandStabilizer()
        self.kinematics = KinematicAnalyzer(window=8)
        self.coach_engine = CoachStateMachine()

        self.cap = None
        self.detector = None
        self.cam_thread = None
        self.running = True
        self.in_therapy = False

        self.frame_queue = queue.Queue(maxsize=1)
        self.frame_count = 0
        self._canvas_buf = None
        self._overlay_buf = None

        # ---------------------------------------------------------
        # D. Therapy Session State
        # ---------------------------------------------------------
        self.current_exercise = "SQUEEZE"
        self.last_timestamp_ms = 0
        self.hold_start_time = 0
        self.hold_duration = 0.5
        self.show_celebration = False
        self.celebration_timer = 0
        self.last_correct_time = time.time()

        self.current_accuracy = 0
        self.coach_msg = ""
        self.coach_msg_type = "neutral"
        self.session_reps = 0
        self.prev_palm_pos = None
        self.smooth_acc = 0

        # ---------------------------------------------------------
        # E. Goal Tracking & Progress
        # ---------------------------------------------------------
        self.session_acc = {ex: {"sum": 0, "frames": 0} for ex in
                            ["SQUEEZE", "THUMB", "STARFISH", "FLIP", "O_RING", "PEACE"]}
        self.daily_acc = {"sq_acc": 0, "thumb_acc": 0, "star_acc": 0, "flip_acc": 0, "oring_acc": 0, "peace_acc": 0}

        self.sq_state, self.sq_goal = "WAITING_FOR_FIST", (3, 20)
        self.thumb_targets = [8, 12, 16, 20]
        self.thumb_names = ["INDEX", "MIDDLE", "RING", "PINKY"]
        self.curr_thumb_idx, self.thumb_goal = 0, (3, 20)
        self.star_state, self.star_goal = "WAITING_FOR_RELAX", (3, 15)
        self.flip_state, self.flip_goal = "WAITING_FOR_UP", (3, 15)
        self.oring_state, self.oring_goal = "WAITING_FOR_RELAX", (4, 15)
        self.peace_state, self.peace_goal = "WAITING_FOR_FIST", (4, 10)

        self.sq_reps = self.thumb_reps = self.star_reps = 0
        self.flip_reps = self.oring_reps = self.peace_reps = 0
        self.sq_sets = self.thumb_sets = self.star_sets = 0
        self.flip_sets = self.oring_sets = self.peace_sets = 0

        self.save_file = resource_path("rehab_progress.json")
        self._last_save = 0

        # ---------------------------------------------------------
        # F. Event Binding & Boot
        # ---------------------------------------------------------
        self.root.bind("<Escape>", self._exit_fullscreen)
        self.root.bind("<Configure>", self._check_maximize)
        self.root.bind("<FocusOut>", self._on_focus_out)
        self.root.bind("<FocusIn>", self._on_focus_in)

        self.load_progress()
        init_tkinter_ui(self)
        start_bgm()
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
        if self.root.focus_get() is None:
            try:
                from audio import pause_bgm
                pause_bgm()
            except Exception:
                pass

    def _on_focus_in(self, event):
        try:
            from audio import unpause_bgm
            unpause_bgm()
        except Exception:
            pass

    def _handle_resize(self, event):
        if event.width > 100 and event.height > 100:
            self.render_w = event.width
            self.render_h = event.height
            recalc_ui_metrics(self)
            self._canvas_buf = None
            self._overlay_buf = None

    def _handle_click(self, event):
        u = self.ui
        # Top Navigation Bar Click
        if 0 < event.y < u['btn_h']:
            try:
                play_menu_click_sound()
            except Exception:
                pass
            exs = getattr(self, 'exercise_list', ["SQUEEZE", "THUMB", "STARFISH", "FLIP", "O_RING", "PEACE"])
            try:
                self.current_exercise = exs[min(event.x // u['btn_w'], len(exs) - 1)]
            except Exception:
                self.current_exercise = "SQUEEZE"
            self.hold_start_time = 0
            self.last_correct_time = time.time()
            return

        # Reset Button Click
        if (u['reset_x'] < event.x < u['reset_x'] + u['reset_w'] and
                u['reset_y'] < event.y < u['reset_y'] + u['reset_h']):
            try:
                play_exit_reset_sound()
            except Exception:
                pass
            self.reset_current_exercise()
            return

        # Menu Button Click
        if (u['menu_x'] < event.x < u['menu_x'] + u['menu_w'] and
                u['menu_y'] < event.y < u['menu_y'] + u['menu_h']):
            try:
                play_exit_reset_sound()
            except Exception:
                pass
            self.return_to_menu()
            return

    def on_close(self):
        self.running = False
        if self.cam_thread and self.cam_thread.is_alive():
            self.cam_thread.join(timeout=1.0)
        if self.cap:
            self.cap.release()
        try:
            self.detector.close()
        except Exception:
            pass
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
            except Exception:
                pass

        if history:
            _, new_goals, _ = evaluate_adaptive_difficulty(history)
            self.sq_goal = (new_goals["sq"][0], 20)
            self.thumb_goal = (new_goals["thumb"][0], 20)
            self.star_goal = (new_goals["star"][0], 15)
            self.flip_goal = (new_goals["flip"][0], 15)
            self.oring_goal = (new_goals["oring"][0], 15)
            self.peace_goal = (new_goals["peace"][0], 10)

        day = history.get(get_therapy_day(), {})
        self.sq_reps = day.get("sq_reps", 0);
        self.sq_sets = day.get("sq_sets", 0)
        self.thumb_reps = day.get("thumb_reps", 0);
        self.thumb_sets = day.get("thumb_sets", 0)
        self.star_reps = day.get("star_reps", 0);
        self.star_sets = day.get("star_sets", 0)
        self.flip_reps = day.get("flip_reps", 0);
        self.flip_sets = day.get("flip_sets", 0)
        self.oring_reps = day.get("oring_reps", 0);
        self.oring_sets = day.get("oring_sets", 0)
        self.peace_reps = day.get("peace_reps", 0);
        self.peace_sets = day.get("peace_sets", 0)

        for k in self.daily_acc:
            self.daily_acc[k] = day.get(k, 0)

    def save_progress(self, force=False):
        now = time.time()
        if not force and now - self._last_save < 1.0:
            return
        self._last_save = now

        for ex, key in [("SQUEEZE", "sq_acc"), ("THUMB", "thumb_acc"), ("STARFISH", "star_acc"),
                        ("FLIP", "flip_acc"), ("O_RING", "oring_acc"), ("PEACE", "peace_acc")]:
            if self.session_acc[ex]["frames"] > 0:
                self.daily_acc[key] = int(self.session_acc[ex]["sum"] / self.session_acc[ex]["frames"])

        today = get_therapy_day()
        history = {}
        if os.path.exists(self.save_file):
            try:
                with open(self.save_file) as f:
                    history = json.load(f)
                if "date" in history:
                    old = history.pop("date", today)
                    history = {old: history}
            except Exception:
                history = {}

        history[today] = {
            "sq_reps": self.sq_reps, "sq_sets": self.sq_sets, "sq_acc": self.daily_acc["sq_acc"],
            "thumb_reps": self.thumb_reps, "thumb_sets": self.thumb_sets, "thumb_acc": self.daily_acc["thumb_acc"],
            "star_reps": self.star_reps, "star_sets": self.star_sets, "star_acc": self.daily_acc["star_acc"],
            "flip_reps": self.flip_reps, "flip_sets": self.flip_sets, "flip_acc": self.daily_acc["flip_acc"],
            "oring_reps": self.oring_reps, "oring_sets": self.oring_sets, "oring_acc": self.daily_acc["oring_acc"],
            "peace_reps": self.peace_reps, "peace_sets": self.peace_sets, "peace_acc": self.daily_acc["peace_acc"],
        }

        try:
            with open(self.save_file, "w") as f:
                json.dump(history, f, indent=2)
        except Exception:
            pass

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

    def show_coming_soon(self):
        self.menu_frame.place_forget()
        self.coming_soon_frame.place(relx=0.5, rely=0.5, anchor="center")
        self.tut_player.start()  # <-- Add this one line so the video plays!

    # =============================================================================
    # 6. AI & SYSTEM BOOT SEQUENCE
    # =============================================================================
    def _init_backend(self):
        try:
            if not _prewarm_done.is_set():
                _prewarm_done.wait()
            _detector_ready.wait()

            if _prebuilt_detector is not None:
                self.detector = _prebuilt_detector
            else:
                from mediapipe.tasks import python as mp_python
                from mediapipe.tasks.python import vision
                import urllib.request

                model_path = resource_path(os.path.join("assets", "hand_landmarker.task"))
                if not os.path.exists(model_path):
                    os.makedirs(os.path.dirname(model_path), exist_ok=True)
                    urllib.request.urlretrieve(
                        "https://storage.googleapis.com/mediapipe-models/"
                        "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
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
        except Exception:
            pass

    def _on_backend_ready(self):
        if hasattr(self, 'start_btn'):
            lang = getattr(self, 'current_lang', 'EN')
            self.start_btn.config(
                state="normal",
                text="START THERAPY SESSION" if lang == "EN" else "เริ่มการบำบัด",
                bg="#10b981", fg="white", cursor="hand2",
            )
            self.start_btn.update()
        else:
            self.root.after(100, self._on_backend_ready)

    def start_therapy(self):
        # Clinical Safety Lockout (Priority 2)
        total_sets_today = (self.sq_sets + self.thumb_sets + self.star_sets +
                            self.flip_sets + self.oring_sets + self.peace_sets)

        if total_sets_today >= 8:
            lang = getattr(self, 'current_lang', 'EN')
            msg = "SAFETY LOCK: Daily limit reached. Please rest." if lang == "EN" else "แจ้งเตือนความปลอดภัย: ถึงขีดจำกัดแล้ว โปรดพัก"
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
        self.start_btn.config(text="CAMERA ERROR - TRY AGAIN", bg="#e74c3c", state=tk.NORMAL)

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
        self.in_therapy = False
        self.video_frame.pack_forget()
        lang = getattr(self, 'current_lang', 'EN')
        self.start_btn.config(
            text="START THERAPY SESSION" if lang == "EN" else "เริ่มการบำบัด",
            bg="#10b981", state=tk.NORMAL, cursor="hand2",
        )
        self.menu_frame.place(relx=0.5, rely=0.5, anchor="center")
        if self.session_reps == 0:
            for ex in self.session_acc:
                self.session_acc[ex] = {"sum": 0, "frames": 0}
        show_session_summary(self)

    def reset_current_exercise(self):
        ex = self.current_exercise
        if ex == "SQUEEZE":
            self.sq_reps = 0; self.sq_sets = 0; self.sq_state = "WAITING_FOR_FIST"
        elif ex == "THUMB":
            self.thumb_reps = 0; self.thumb_sets = 0; self.curr_thumb_idx = 0
        elif ex == "STARFISH":
            self.star_reps = 0; self.star_sets = 0; self.star_state = "WAITING_FOR_RELAX"
        elif ex == "FLIP":
            self.flip_reps = 0; self.flip_sets = 0; self.flip_state = "WAITING_FOR_UP"
        elif ex == "O_RING":
            self.oring_reps = 0; self.oring_sets = 0; self.oring_state = "WAITING_FOR_RELAX"
        elif ex == "PEACE":
            self.peace_reps = 0; self.peace_sets = 0; self.peace_state = "WAITING_FOR_FIST"

        self.hold_start_time = 0
        self.show_celebration = False
        self.last_correct_time = time.time()
        self.save_progress(force=True)

    def _process_timers(self):
        t = time.time()
        if self.hold_start_time == 0:
            self.hold_start_time = t
            return
        if t - self.hold_start_time < self.hold_duration:
            return

        self.hold_start_time = 0
        self.session_reps += 1
        ex = self.current_exercise
        frames = getattr(self, "rep_acc_frames", 1)
        final_score = int(getattr(self, "rep_acc_sum", 100) / max(1, frames))
        self.session_acc[ex]["sum"] += final_score
        self.session_acc[ex]["frames"] += 1
        self.rep_acc_sum = 0
        self.rep_acc_frames = 0

        def add_rep(reps, sets, goal):
            reps += 1
            if reps >= goal[1]: sets += 1; reps = 0
            return reps, sets

        if ex == "SQUEEZE":
            if self.sq_state == "WAITING_FOR_FIST":
                self.sq_state = "WAITING_FOR_OPEN"
            else:
                self.sq_reps, self.sq_sets = add_rep(self.sq_reps, self.sq_sets, self.sq_goal)
                self.sq_state = "WAITING_FOR_FIST";
                self.save_progress()
        elif ex == "THUMB":
            self.curr_thumb_idx += 1
            if self.curr_thumb_idx > 3:
                self.curr_thumb_idx = 0
                self.thumb_reps, self.thumb_sets = add_rep(self.thumb_reps, self.thumb_sets, self.thumb_goal)
                self.save_progress()
        elif ex == "STARFISH":
            if self.star_state == "WAITING_FOR_RELAX":
                self.star_state = "WAITING_FOR_SPREAD"
            else:
                self.star_reps, self.star_sets = add_rep(self.star_reps, self.star_sets, self.star_goal)
                self.star_state = "WAITING_FOR_RELAX";
                self.save_progress()
        elif ex == "FLIP":
            if self.flip_state == "WAITING_FOR_UP":
                self.flip_state = "WAITING_FOR_DOWN"
            else:
                self.flip_reps, self.flip_sets = add_rep(self.flip_reps, self.flip_sets, self.flip_goal)
                self.flip_state = "WAITING_FOR_UP";
                self.save_progress()
        elif ex == "O_RING":
            if self.oring_state == "WAITING_FOR_RELAX":
                self.oring_state = "WAITING_FOR_PINCH"
            else:
                self.oring_reps, self.oring_sets = add_rep(self.oring_reps, self.oring_sets, self.oring_goal)
                self.oring_state = "WAITING_FOR_RELAX";
                self.save_progress()
        elif ex == "PEACE":
            if self.peace_state == "WAITING_FOR_FIST":
                self.peace_state = "WAITING_FOR_PEACE"
            else:
                self.peace_reps, self.peace_sets = add_rep(self.peace_reps, self.peace_sets, self.peace_goal)
                self.peace_state = "WAITING_FOR_FIST";
                self.save_progress()

        try:
            play_success_sound()
        except Exception:
            pass

    # =============================================================================
    # 8. HUD & OVERLAY RENDERERS
    # =============================================================================
    def _get_text_size(self, cv2, text, font, scale, thick):
        key = (text, scale, thick)
        if key not in self._ui_text_cache:
            self._ui_text_cache[key] = cv2.getTextSize(text, font, scale, thick)[0]
        return self._ui_text_cache[key]

    def _draw_ui(self, canvas):
        draw_dashboard(self, canvas)

    def _get_current_ui_text(self):
        t = LANG[getattr(self, 'current_lang', 'EN')]
        ex = self.current_exercise
        inst = "";
        reps, sets, goal = 0, 0, (1, 1)

        if ex == "SQUEEZE":
            reps, sets, goal = self.sq_reps, self.sq_sets, self.sq_goal
            inst = t["inst_sq_1"] if self.sq_state == "WAITING_FOR_FIST" else t["inst_sq_2"]
        elif ex == "THUMB":
            reps, sets, goal = self.thumb_reps, self.thumb_sets, self.thumb_goal
            inst = f"{t['inst_th']} {t['thumb_names'][self.curr_thumb_idx]}"
        elif ex == "STARFISH":
            reps, sets, goal = self.star_reps, self.star_sets, self.star_goal
            inst = t["inst_st_1"] if self.star_state == "WAITING_FOR_RELAX" else t["inst_st_2"]
        elif ex == "FLIP":
            reps, sets, goal = self.flip_reps, self.flip_sets, self.flip_goal
            inst = t["inst_fl_1"] if self.flip_state == "WAITING_FOR_UP" else t["inst_fl_2"]
        elif ex == "O_RING":
            reps, sets, goal = self.oring_reps, self.oring_sets, self.oring_goal
            inst = t.get("inst_sq_1", "Make Fist") if self.oring_state == "WAITING_FOR_RELAX" else t.get("inst_or_2",
                                                                                                         "Pinch")
        elif ex == "PEACE":
            reps, sets, goal = self.peace_reps, self.peace_sets, self.peace_goal
            inst = t["inst_pe_1"] if self.peace_state == "WAITING_FOR_FIST" else t["inst_pe_2"]

        if sets >= goal[0]:
            progress_text = f"{t['daily_goal']} | {t['set']}: {sets + 1} | {t['rep']}: {reps}/{goal[1]}"
        else:
            progress_text = f"{t['set']}: {sets + 1}/{goal[0]} | {t['rep']}: {reps}/{goal[1]}"
        return {"inst": inst, "progress_text": progress_text}

    def update_gui(self):
        """Pulls generated frames from the queue and updates the Tkinter Video Label."""
        if not self.in_therapy:
            return
        _, ImageTk = _ensure_pil()
        try:
            pil_img = self.frame_queue.get_nowait()
            imgtk = ImageTk.PhotoImage(image=pil_img)
            self.video_label.imgtk = imgtk
            self.video_label.configure(image=imgtk)
        except queue.Empty:
            pass
        self.root.after(33, self.update_gui)

    # =============================================================================
    # 9. OPENCV / MEDIAPIPE CAMERA THREAD
    # =============================================================================
    def camera_loop(self):
        cv2 = _ensure_cv2()
        np = _ensure_np()
        mp = _ensure_mp()
        Image, ImageTk = _ensure_pil()
        INTER_LINEAR = cv2.INTER_LINEAR
        COLOR_BGR2RGB = cv2.COLOR_BGR2RGB

        score_closed = _score_squeeze_closed
        score_open = _score_squeeze_open
        score_star = _score_starfish
        score_peace = _score_peace
        score_oring = _score_oring

        lang = getattr(self, 'current_lang', 'EN')

        while self.running and self.in_therapy:
            if not self.cap or not self.cap.isOpened():
                time.sleep(0.1)
                continue

            try:
                # --- 9.1 Read & Format Frame ---
                success, raw_frame = self.cap.read()
                if not success:
                    time.sleep(0.01)
                    continue

                raw_frame = cv2.flip(raw_frame, 1)
                ai_frame = cv2.resize(raw_frame, (320, 180), interpolation=INTER_LINEAR)
                rgb_frame = cv2.cvtColor(ai_frame, COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

                # --- 9.2 Handle AI Video Timestamps ---
                ts_ms = int(time.time() * 1000)
                if ts_ms <= self.last_timestamp_ms:
                    ts_ms = self.last_timestamp_ms + 1
                self.last_timestamp_ms = ts_ms

                # --- 9.3 AI Inference ---
                result = self.detector.detect_for_video(mp_image, ts_ms)

                # --- 9.4 Scale for Display ---
                cam_h, cam_w = raw_frame.shape[:2]
                scale = min(self.render_w / cam_w, self.render_h / cam_h)
                new_w, new_h = int(cam_w * scale), int(cam_h * scale)

                need_shape = (self.render_h, self.render_w, 3)
                if self._canvas_buf is None or self._canvas_buf.shape != need_shape:
                    self._canvas_buf = np.zeros(need_shape, dtype=np.uint8)

                canvas = self._canvas_buf
                canvas[:] = 0
                y_off, x_off = (self.render_h - new_h) // 2, (self.render_w - new_w) // 2
                canvas[y_off:y_off + new_h, x_off:x_off + new_w] = cv2.resize(
                    raw_frame, (new_w, new_h), interpolation=INTER_LINEAR)

                # --- 9.5 Hand Validity Check ---
                raw_lms = None
                if result.hand_landmarks:
                    hand_ok = True
                    if hasattr(result, 'handedness') and result.handedness:
                        if result.handedness[0][0].score < 0.60:
                            hand_ok = False
                    if hand_ok:
                        raw_lms = result.hand_landmarks[0]

                # --- 9.6 Process Skeleton & Scoring ---
                if raw_lms:
                    stable_lms = self.stabilizer.stabilize(raw_lms)
                    self.kinematics.update(stable_lms)
                    geo = HandGeometry.from_landmarks(stable_lms)

                    draw_skeleton(canvas[y_off:y_off + new_h, x_off:x_off + new_w], stable_lms)

                    is_steady = not self.kinematics.is_moving()
                    ex = self.current_exercise
                    raised = geo.raised_count
                    step = 0

                    if ex == "SQUEEZE" and self.sq_state == "WAITING_FOR_OPEN": step = 1
                    if ex == "STARFISH" and self.star_state == "WAITING_FOR_SPREAD": step = 1
                    if ex == "PEACE" and self.peace_state == "WAITING_FOR_PEACE": step = 1
                    if ex == "FLIP" and self.flip_state == "WAITING_FOR_DOWN": step = 1
                    if ex == "O_RING" and self.oring_state == "WAITING_FOR_PINCH": step = 1

                    # Determine Accuracy
                    if ex == "FLIP":
                        raw_acc = 50
                    elif ex == "O_RING" and step == 1:
                        raw_acc = score_oring(geo, stable_lms).accuracy
                    elif ex == "O_RING":
                        raw_acc = score_closed(geo).accuracy
                    elif ex == "SQUEEZE" and step == 0:
                        raw_acc = score_closed(geo).accuracy
                    elif ex == "SQUEEZE":
                        raw_acc = score_open(geo).accuracy
                    elif ex == "STARFISH" and step == 0:
                        raw_acc = score_closed(geo).accuracy
                    elif ex == "STARFISH":
                        raw_acc = score_star(geo).accuracy
                    elif ex == "PEACE" and step == 0:
                        raw_acc = score_closed(geo).accuracy
                    elif ex == "PEACE":
                        raw_acc = score_peace(geo).accuracy
                    else:
                        raw_acc = get_movement_accuracy(ex, step, raised, stable_lms)

                    # Determine Posture Correctness
                    if is_steady:
                        self.last_correct_time = time.time()
                        posture_correct = False

                        if ex == "FLIP":
                            x_diff = stable_lms[5].x - stable_lms[17].x
                            if abs(x_diff) > 0.02:
                                cur_dir = 1 if x_diff > 0 else -1
                                if (not hasattr(self, 'flip_base_dir') or
                                        (self.flip_reps == 0 and self.flip_state == "WAITING_FOR_UP")):
                                    self.flip_base_dir = cur_dir
                                if self.flip_state == "WAITING_FOR_UP" and cur_dir == self.flip_base_dir:
                                    posture_correct = True
                                elif self.flip_state == "WAITING_FOR_DOWN" and cur_dir != self.flip_base_dir:
                                    posture_correct = True

                        elif ex == "THUMB":
                            target_idx = self.thumb_targets[self.curr_thumb_idx]
                            gaps = {
                                8: geo.nail_distances.get((4, 8), 1.0),
                                12: geo.nail_distances.get((4, 12), 1.0),
                                16: geo.nail_distances.get((4, 16), 1.0),
                                20: geo.nail_distances.get((4, 20), 1.0),
                            }
                            closest = min(gaps, key=gaps.get)
                            tol = {8: 0.70, 12: 0.85, 16: 1.05, 20: 1.25}[target_idx]
                            if closest == target_idx and gaps[target_idx] < tol:
                                posture_correct = True
                        else:
                            if raw_acc > 60: posture_correct = True

                        if posture_correct:
                            self._process_timers()
                        else:
                            if time.time() - getattr(self, "hold_start_time", 0) > 0.25:
                                self.hold_start_time = 0
                    else:
                        self.hold_start_time = 0

                    if ex == "FLIP":
                        raw_acc = 100 if (is_steady and posture_correct) else 20

                    # Smoothing & Storage
                    self.smooth_acc = int(0.3 * raw_acc + 0.7 * getattr(self, "smooth_acc", 0))
                    self.current_accuracy = self.smooth_acc

                    if is_steady and getattr(self, "hold_start_time", 0) > 0:
                        self.rep_acc_sum = getattr(self, "rep_acc_sum", 0) + raw_acc
                        self.rep_acc_frames = getattr(self, "rep_acc_frames", 0) + 1
                    elif not is_steady:
                        self.rep_acc_sum = 0
                        self.rep_acc_frames = 0

                    # Coach Feedback
                    ckey, ctype = self.coach_engine.get_feedback(ex, step, geo, self.kinematics) or ("", "")
                    if ex == "FLIP":
                        if not is_steady:
                            self.coach_msg, self.coach_msg_type = LANG[lang].get("coach_hold_steady", ""), "warn"
                        elif posture_correct:
                            self.coach_msg, self.coach_msg_type = LANG[lang].get("coach_well_done", ""), "good"
                        else:
                            self.coach_msg, self.coach_msg_type = "", ""
                    elif ckey:
                        self.coach_msg, self.coach_msg_type = LANG[lang].get(ckey, ""), ctype
                    else:
                        self.coach_msg = ""

                # --- 9.7 No Hand Detected ---
                else:
                    self.stabilizer.hist = None
                    self.current_accuracy = 0
                    self.coach_msg = ""
                    if time.time() - getattr(self, "hold_start_time", 0) > 0.25:
                        self.hold_start_time = 0

                # --- 9.8 UI Overlay & Queue Push ---
                self._draw_ui(canvas)
                pil_img = Image.fromarray(cv2.cvtColor(canvas, COLOR_BGR2RGB))

                fq = self.frame_queue
                if fq.full():
                    try:
                        fq.get_nowait()
                    except queue.Empty:
                        pass
                fq.put_nowait(pil_img)

            except Exception:
                time.sleep(0.05)

        # Cleanup on Exit
        if self.cap:
            self.cap.release()
            self.cap = None
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                pass


# =============================================================================
# 10. SYSTEM BOOTSTRAP
# =============================================================================
if __name__ == "__main__":
    try:
        import pyi_splash

        pyi_splash.close()
    except Exception:
        pass

    ensure_single_instance()
    prewarm_libs()

    root = tk.Tk()

    # --- UPDATED ICON LOADING ---
    try:
        root.iconbitmap(resource_path(os.path.join('assets', 'rehab.ico')))
    except Exception:
        pass
    # ----------------------------

    app = RehabApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
