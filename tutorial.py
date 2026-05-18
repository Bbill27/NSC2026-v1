# =============================================================================
# NSC Medical Suite - Automated Enterprise Video Player (Bug-Free Audio Release)
# =============================================================================
import cv2
import tkinter as tk
from PIL import Image, ImageTk
import os
import pygame
import tempfile
from utils import resource_path
from moviepy import VideoFileClip


class TutorialPlayer:
    def __init__(self, parent_frame):
        self.parent = parent_frame
        self.cap = None
        self.playing = False
        self.total_frames = 1
        self.fps = 30
        self.user_is_seeking = False
        self.saved_global_volume = 1.0

        self.temp_audio_path = os.path.join(tempfile.gettempdir(), "nsc_tut_temp_audio.wav")

        try:
            pygame.mixer.init()
        except Exception:
            pass

        # ─── MAIN VIDEO SCREEN ───
        self.main_frame = tk.Frame(self.parent, bg="#000000")
        self.main_frame.pack(fill="both", expand=True, pady=(0, 20), padx=40)

        self.video_label = tk.Label(self.main_frame, bg="#000000", fg="#00d4aa", font=("Leelawadee UI", 16),
                                    cursor="hand2")
        self.video_label.pack(fill="both", expand=True)
        self.video_label.bind("<Button-1>", lambda e: self.play_pause())

        # ─── CONTROLS AREA ───
        self.controls_frame = tk.Frame(self.main_frame, bg="#0f1623", height=70)
        self.controls_frame.pack(fill="x", side="bottom")
        self.controls_frame.pack_propagate(False)

        # 1. VIDEO PROGRESS BAR
        self.progress_slider = tk.Scale(self.controls_frame, from_=0, to=100, orient="horizontal",
                                        showvalue=0, bg="#0f1623", fg="#ff4d6d", troughcolor="#243052",
                                        sliderrelief="flat", highlightthickness=0, cursor="hand2")
        self.progress_slider.pack(fill="x", side="top", pady=(0, 5))

        self.progress_slider.bind("<ButtonPress-1>", self._on_seek_start)
        self.progress_slider.bind("<ButtonRelease-1>", self._on_seek_end)

        # Bottom Row for Buttons
        self.bottom_row = tk.Frame(self.controls_frame, bg="#0f1623")
        self.bottom_row.pack(fill="both", expand=True, padx=20)

        btn_font = ("Leelawadee UI", 11, "bold")

        # 2. PLAY/PAUSE
        self.play_btn = tk.Button(self.bottom_row, text="PAUSE", font=btn_font, bg="#0f1623", fg="#ffffff",
                                  relief="flat", borderwidth=0, cursor="hand2", command=self.play_pause,
                                  activebackground="#0f1623", activeforeground="#00d4aa", width=6)
        self.play_btn.pack(side="left", padx=(0, 15))

        # 3. TIME LABEL
        self.time_label = tk.Label(self.bottom_row, text="00:00 / 00:00", font=("Leelawadee UI", 11),
                                   bg="#0f1623", fg="#e8edf5")
        self.time_label.pack(side="left")

        # 4. VOLUME SLIDER
        self.vol_slider = tk.Scale(self.bottom_row, from_=0, to=100, orient="horizontal", showvalue=0,
                                   length=100, bg="#0f1623", troughcolor="#243052", highlightthickness=0,
                                   command=self.set_volume, sliderrelief="flat", cursor="hand2")
        self.vol_slider.set(80)
        self.vol_slider.pack(side="right", padx=(5, 0))

        self.vol_lbl = tk.Label(self.bottom_row, text="VOL:", font=btn_font, bg="#0f1623", fg="#ffffff")
        self.vol_lbl.pack(side="right")

    def start(self):
        video_path = resource_path(os.path.join("assets", "tutorial.mp4"))

        if not os.path.exists(video_path):
            self.video_label.config(text="ERROR: tutorial.mp4 not found in assets folder.")
            return

        # ─── 1. ISOLATE MAIN GAME AUDIO ───
        try:
            self.saved_global_volume = pygame.mixer.music.get_volume()
            pygame.mixer.music.stop()
            # Force Pygame to let go of any previous music files
            if hasattr(pygame.mixer.music, 'unload'):
                pygame.mixer.music.unload()
        except Exception:
            self.saved_global_volume = 1.0

        # ─── 2. SMART AUDIO EXTRACTION (Only runs if file doesn't exist) ───
        if not os.path.exists(self.temp_audio_path):
            self.video_label.config(text="Extracting Audio Engine...")
            self.parent.update()
            try:
                clip = VideoFileClip(video_path)
                clip.audio.write_audiofile(self.temp_audio_path, logger=None)
                clip.close()
            except Exception as e:
                print(f"[AUDIO EXTRACT ERROR]: {e}")

        # ─── 3. LOAD THE AUDIO ───
        try:
            pygame.mixer.music.load(self.temp_audio_path)
            pygame.mixer.music.set_volume(self.vol_slider.get() / 100.0)
            pygame.mixer.music.play(-1)
        except Exception as e:
            print(f"[AUDIO LOAD ERROR]: {e}")

        # ─── 4. LOAD VIDEO ───
        self.cap = cv2.VideoCapture(video_path)
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
        self.progress_slider.config(to=self.total_frames)

        self.playing = True
        self.play_btn.config(text="PAUSE")
        self._update_frame()

    def _update_frame(self):
        if not self.parent.winfo_exists() or self.cap is None:
            return

        if self.playing and not self.user_is_seeking:
            ret, frame = self.cap.read()
            if ret:
                win_w = self.main_frame.winfo_width()
                win_h = self.main_frame.winfo_height() - 70
                if win_w > 10 and win_h > 10:
                    h, w = frame.shape[:2]
                    scale = min(win_w / w, win_h / h)
                    new_w, new_h = int(w * scale), int(h * scale)
                    frame = cv2.resize(frame, (new_w, new_h))

                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame)
                imgtk = ImageTk.PhotoImage(image=img)
                self.video_label.imgtk = imgtk
                self.video_label.configure(image=imgtk)

                current_frame = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
                self.progress_slider.set(current_frame)
                self._update_time_label(current_frame)
            else:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                try:
                    pygame.mixer.music.play(-1, start=0.0)
                except Exception:
                    pass

        self.parent.after(int(1000 / self.fps), self._update_frame)

    def stop(self):
        self.playing = False
        if self.cap:
            self.cap.release()
            self.cap = None

        # ─── THE BGM FIX ───
        try:
            pygame.mixer.music.stop()

            # Forcefully unlock the tutorial audio file so it doesn't break later
            if hasattr(pygame.mixer.music, 'unload'):
                pygame.mixer.music.unload()

            pygame.mixer.music.set_volume(self.saved_global_volume)

            # Use the correct function name to restart your background music
            import audio
            audio.start_bgm()
        except Exception as e:
            print(f"[BGM RESTART ERROR]: {e}")

    def play_pause(self):
        self.playing = not self.playing
        if self.playing:
            self.play_btn.config(text="PAUSE")
            try:
                target_sec = self.progress_slider.get() / self.fps
                pygame.mixer.music.play(-1, start=target_sec)
            except Exception:
                pass
        else:
            self.play_btn.config(text="PLAY")
            try:
                pygame.mixer.music.pause()
            except Exception:
                pass

    def set_volume(self, val):
        try:
            pygame.mixer.music.set_volume(float(val) / 100.0)
        except Exception:
            pass

    def _on_seek_start(self, event):
        self.user_is_seeking = True
        try:
            pygame.mixer.music.pause()
        except Exception:
            pass

        slider_width = self.progress_slider.winfo_width()
        if slider_width > 0:
            click_percentage = event.x / slider_width
            target_frame = int(click_percentage * self.total_frames)
            target_frame = max(0, min(self.total_frames, target_frame))

            self.progress_slider.set(target_frame)
            if self.cap:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            self._update_time_label(target_frame)

    def _on_seek_end(self, event):
        if self.cap:
            target_frame = self.progress_slider.get()
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            self._update_time_label(target_frame)

            if self.playing:
                try:
                    target_sec = target_frame / self.fps
                    pygame.mixer.music.play(-1, start=target_sec)
                except Exception:
                    pass

        self.user_is_seeking = False

    def _update_time_label(self, current_frame):
        cur_sec = int(current_frame / self.fps)
        tot_sec = int(self.total_frames / self.fps)
        cur_str = f"{cur_sec // 60:02d}:{cur_sec % 60:02d}"
        tot_str = f"{tot_sec // 60:02d}:{tot_sec % 60:02d}"
        self.time_label.config(text=f"{cur_str} / {tot_str}")
