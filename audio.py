"""
===============================================================================
NSC Medical Suite - Audio Engine (Optimised)
===============================================================================
Handles background music (BGM) and sound effects (SFX) using PyGame.
Configured with a robust audio buffer to prevent hardware conflicts
with the OpenCV webcam stream.
===============================================================================
"""

from __future__ import annotations

import os
from typing import Dict, Optional

# Safely import pygame and hide the default console greeting prompt
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
import pygame

from utils import resource_path

# =============================================================================
# 1. AUDIO ENGINE INITIALIZATION
# =============================================================================
# Force a strong audio buffer to prevent the webcam from stealing audio focus!
try:
    pygame.mixer.pre_init(44100, -16, 2, 4096)
    pygame.mixer.init()
except Exception as e:
    print(f"[AUDIO WARN] Failed to initialize PyGame mixer: {e}")

# =============================================================================
# 2. AUDIO STATE & CACHE
# =============================================================================
bgm_vol: float = 0.5
sfx_vol: float = 0.8
_sounds: Dict[str, pygame.mixer.Sound] = {}


# =============================================================================
# 3. CORE AUDIO CONTROLS (SFX)
# =============================================================================
def load_sfx(filename: str) -> Optional[pygame.mixer.Sound]:
    """Loads and caches a sound effect from the assets folder."""
    if filename not in _sounds:
        path = resource_path(os.path.join("assets", filename))
        if os.path.exists(path):
            try:
                _sounds[filename] = pygame.mixer.Sound(path)
            except Exception as e:
                print(f"[AUDIO WARN] Could not load SFX {filename}: {e}")
                _sounds[filename] = None
        else:
            _sounds[filename] = None

    return _sounds.get(filename)


def play_sfx(filename: str) -> None:
    """Plays a cached sound effect at the current SFX volume."""
    snd = load_sfx(filename)
    if snd:
        try:
            snd.set_volume(sfx_vol)
            snd.play()
        except Exception:
            pass


def set_sfx_volume(vol: float) -> None:
    """Globally updates the sound effect volume."""
    global sfx_vol
    # Clamp volume strictly between 0.0 and 1.0 to prevent PyGame crashes
    sfx_vol = max(0.0, min(1.0, float(vol)))


# =============================================================================
# 4. BACKGROUND MUSIC (BGM) CONTROLS
# =============================================================================
def start_bgm() -> None:
    """Loads and loops the main background music."""
    path = resource_path(os.path.join("assets", "main_music.mp3"))
    if os.path.exists(path):
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(bgm_vol)
            pygame.mixer.music.play(-1)  # -1 loops indefinitely
        except Exception as e:
            print(f"[AUDIO WARN] Failed to load BGM: {e}")


def set_bgm_volume(vol: float) -> None:
    """Globally updates the background music volume."""
    global bgm_vol
    bgm_vol = max(0.0, min(1.0, float(vol)))
    try:
        pygame.mixer.music.set_volume(bgm_vol)
    except Exception:
        pass


def pause_bgm() -> None:
    """Pauses the background music (used when app loses focus)."""
    try:
        pygame.mixer.music.pause()
    except Exception:
        pass


def unpause_bgm() -> None:
    """Resumes the background music (used when app regains focus)."""
    try:
        pygame.mixer.music.unpause()
    except Exception:
        pass


# =============================================================================
# 5. EVENT WRAPPERS (UI Triggers)
# =============================================================================
def play_success_sound() -> None:
    play_sfx("ding.wav")


def play_celebration_sound() -> None:
    play_sfx("reach_daily_limit.wav")


def play_menu_click_sound() -> None:
    play_sfx("btn_menu.wav")


def play_exit_reset_sound() -> None:
    play_sfx("exit_reset_btn.wav")


def play_change_mode_sound() -> None:
    play_sfx("change_mode.wav")
