"""
===============================================================================
NSC Medical Suite - Audio Engine (Hybrid Online/Offline)
===============================================================================
Handles sound effects (SFX) and AI Voice Coaching.
- ONLINE MODE: Uses Microsoft Edge Neural Voice (edge-tts) for high-quality coaching.
- OFFLINE MODE: Gracefully silences voice coaching without crashing the app.
===============================================================================
"""

from __future__ import annotations

import os
import time
import threading
import asyncio
import tempfile
from typing import Dict, Optional

# Safely import pygame and hide the default console greeting prompt
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
import pygame

# Import the Microsoft Edge Neural Voice library
import edge_tts

from utils import resource_path

# =============================================================================
# 1. AUDIO ENGINE INITIALIZATION
# =============================================================================
# Force a strong audio buffer to prevent the webcam from stealing audio focus!
try:
    pygame.mixer.pre_init(44100, -16, 2, 4096)
    pygame.mixer.init()
    _audio_enabled = True
except Exception as e:
    _audio_enabled = False
    print(f"[AUDIO WARN] Failed to initialize PyGame mixer: {e}")

# =============================================================================
# 2. AUDIO STATE & CACHE
# =============================================================================
sfx_vol: float = 0.8
_sounds: Dict[str, pygame.mixer.Sound] = {}


# =============================================================================
# 3. CORE AUDIO CONTROLS (SFX)
# =============================================================================
def load_sfx(filename: str) -> Optional[pygame.mixer.Sound]:
    """Loads and caches a sound effect from the assets folder."""
    if not _audio_enabled: return None

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
    sfx_vol = max(0.0, min(1.0, float(vol)))


# =============================================================================
# 4. EVENT WRAPPERS (UI Triggers)
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


# =============================================================================
# 5. AI VOICE COACHING (HYBRID ONLINE/OFFLINE)
# =============================================================================
_is_speaking = False

def speak_message(text: str, lang: str = "TH") -> None:
    """
    Triggers the AI voice. Wrapped in a thread to prevent OpenCV camera freezing!
    """
    global _is_speaking
    if not _audio_enabled or _is_speaking or not text:
        return

    threading.Thread(target=_run_tts, args=(text, lang), daemon=True).start()

def _run_tts(text: str, lang: str) -> None:
    global _is_speaking
    _is_speaking = True

    try:
        if lang == "TH":
            voice_model = "th-TH-NiwatNeural"
        else:
            voice_model = "en-US-ChristopherNeural"

        temp_filename = f"temp_coach_{int(time.time() * 1000)}.mp3"
        audio_file = os.path.join(tempfile.gettempdir(), temp_filename)

        async def create_voice():
            communicate = edge_tts.Communicate(text, voice_model)
            await communicate.save(audio_file)

        # If offline, this asyncio block will instantly throw an exception,
        # skip the playback, and jump straight to the except block.
        asyncio.run(create_voice())

        if os.path.exists(audio_file):
            pygame.mixer.music.load(audio_file)
            pygame.mixer.music.set_volume(1.0)
            pygame.mixer.music.play()

            time.sleep(0.2)
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)

            try:
                pygame.mixer.music.unload()
            except AttributeError:
                pass

        if os.path.exists(audio_file):
            try: os.remove(audio_file)
            except Exception: pass

    except Exception as e:
        # App is Offline or Edge-TTS failed.
        # Fails silently without crashing the main application.
        print(f"[OFFLINE MODE] Voice coaching disabled. Network required.")

    finally:
        _is_speaking = False

# =============================================================================
# 6. BGM DUMMY SHIELDS (Prevents crashes from legacy code)
# =============================================================================
def start_bgm() -> None: pass
def pause_bgm() -> None: pass
def unpause_bgm() -> None: pass
def set_bgm_volume(vol: float) -> None: pass
