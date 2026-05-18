"""
===============================================================================
NSC Medical Suite - Core Utilities & Environment (Optimised)
===============================================================================
Contains foundational helper functions, environment overrides for fast boot,
lazy-loading module caches, and Nuitka/PyInstaller pathing resolutions.
===============================================================================
"""

from __future__ import annotations

import os
import sys
import math
import socket
import ctypes
from typing import Any, Tuple

# =============================================================================
# 1. ENVIRONMENT OVERRIDES (Performance & Clean Boot)
# =============================================================================
# Disable hardware transforms and suppress excessive logging for a clean, fast start
os.environ["OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS"] = "0"
os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["GLOG_minloglevel"] = "3"
os.environ["MEDIAPIPE_DISABLE_GPU"] = "1"

# =============================================================================
# 2. SINGLE INSTANCE GUARD
# =============================================================================
_LOCK_SOCKET = None


def ensure_single_instance() -> None:
    """
    Binds a dummy socket to a specific port to prevent the user from
    accidentally opening the application multiple times in the background.
    """
    global _LOCK_SOCKET
    try:
        _LOCK_SOCKET = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _LOCK_SOCKET.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        _LOCK_SOCKET.bind(("127.0.0.1", 47892))
        _LOCK_SOCKET.listen(1)
    except OSError:
        # Prompt a Windows-native alert box
        ctypes.windll.user32.MessageBoxW(
            0,
            "NSC Medical Suite is already running.\nCheck your taskbar.",
            "Already Running",
            0x30
        )
        sys.exit(0)


# =============================================================================
# 3. RESOURCE PATH MANAGEMENT
# =============================================================================
def resource_path(relative_path: str) -> str:
    """
    Retrieves the absolute path to a resource. Works seamlessly in standard
    development environments as well as compiled Nuitka/PyInstaller distributions.
    """
    try:
        # PyInstaller/Nuitka stores the temp extraction folder path in sys._MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # Fallback for standard Python execution (VS Code, terminal, etc.)
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


# =============================================================================
# 4. LAZY LOADING & MODULE CACHING (Fast Startup)
# =============================================================================
# Prevents heavy libraries from blocking the initial GUI rendering
_cv2, _np, _mp, _PIL_Image, _PIL_ImageTk = None, None, None, None, None


def _ensure_cv2() -> Any:
    global _cv2
    if _cv2 is None:
        import cv2
        _cv2 = cv2
    return _cv2


def _ensure_np() -> Any:
    global _np
    if _np is None:
        import numpy as np
        _np = np
    return _np


def _ensure_mp() -> Any:
    global _mp
    if _mp is None:
        import mediapipe as mp
        import mediapipe.tasks.python
        import mediapipe.tasks.python.vision
        _mp = mp
    return _mp


def _ensure_pil() -> Tuple[Any, Any]:
    global _PIL_Image, _PIL_ImageTk
    if _PIL_Image is None:
        from PIL import Image, ImageTk
        _PIL_Image, _PIL_ImageTk = Image, ImageTk
    return _PIL_Image, _PIL_ImageTk


# =============================================================================
# 5. RAW SPATIAL MATH PRIMITIVES
# =============================================================================
def get_distance_2d(lm1: Any, lm2: Any) -> float:
    """Calculates the exact Euclidean distance between two 2D landmarks."""
    dx, dy = lm1.x - lm2.x, lm1.y - lm2.y
    return math.sqrt(dx * dx + dy * dy)


def get_dist2_sq(lm1: Any, lm2: Any) -> float:
    """Calculates the squared Euclidean distance (avoids expensive sqrt overhead)."""
    dx, dy = lm1.x - lm2.x, lm1.y - lm2.y
    return dx * dx + dy * dy


class Point3D:
    """
    Lightweight 3D coordinate struct.
    Uses __slots__ to prevent dictionary allocation, vastly improving memory and speed.
    """
    __slots__ = ('x', 'y', 'z')

    def __init__(self, x: float, y: float, z: float):
        self.x = x
        self.y = y
        self.z = z
