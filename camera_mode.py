"""
===============================================================================
CerebroMotion - Camera Mode Base Class
===============================================================================
A "mode" owns the whole screen while the camera is running (Interactive
Tutorial, Piano Tiles game). main.camera_loop() detects the hand and then calls
mode.on_frame(), which returns the finished PIL image to show. Clicks on the
video label are forwarded to mode.on_click().

on_frame() runs on the camera thread and on_click() on the Tk thread, so modes
guard their state with self.lock.
===============================================================================
"""

from __future__ import annotations

import threading


class CameraMode:
    name = "base"

    def __init__(self, app):
        self.app = app
        self.lock = threading.RLock()
        self._buttons: list[tuple[tuple, str]] = []   # (box, action) from the last frame

    @property
    def lang(self) -> str:
        return getattr(self.app, "current_lang", "TH")

    # ── lifecycle ───────────────────────────────────────────────
    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    # ── per frame (camera thread) ───────────────────────────────
    def on_frame(self, frame_bgr, lms, now: float, size: tuple[int, int]):
        """Return a PIL RGB image of `size` for the screen."""
        raise NotImplementedError

    # ── input (Tk thread) ───────────────────────────────────────
    def on_click(self, x: int, y: int) -> None:
        from theme import inside
        with self.lock:
            buttons = list(self._buttons)
        for box, action in buttons:
            if inside(box, x, y):
                try:
                    import audio
                    audio.play_menu_click_sound()
                except Exception:
                    pass
                self.handle_action(action)
                return

    def handle_action(self, action: str) -> None:
        if action == "exit":
            self.request_exit()

    def request_exit(self) -> None:
        """Ask the Tk thread to stop the camera and go back to the menu."""
        self.app.root.after(0, self.app.return_to_menu)

    # ── helpers ─────────────────────────────────────────────────
    def add_button(self, box, action) -> None:
        self._buttons.append((tuple(int(v) for v in box), action))
