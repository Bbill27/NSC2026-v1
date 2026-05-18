"""
===============================================================================
NSC Medical Suite - User Interface Module (Optimised)
===============================================================================
Performance Architecture:
  1. Font Caching: ImageFont.truetype() loaded globally to prevent I/O blocking.
  2. BBox Caching: textbbox() results hashed and reused per unique string.
  3. Allocation Reduction: Direct canvas blending; no redundant np.array copies.
  4. State Hashing: UI strings only rebuild when underlying logic states change.
  5. Math Optimization: Pulse animations use a pre-computed 256-entry Sin table.
===============================================================================
"""

from __future__ import annotations

# =============================================================================
# 1. IMPORTS & ENVIRONMENT SETUP
# =============================================================================
# Standard Library
import os
import csv
import json
import math
import time
import webbrowser
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import font, ttk, filedialog

# Third-Party / Safe Plotting
import matplotlib
matplotlib.use("Agg")  # Must precede pyplot import for thread safety
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# Local Application Modules
import audio
from chatbot import ClinicalChatbot
from utils import _ensure_cv2, _ensure_np, resource_path
from logic import generate_clinical_insights, evaluate_adaptive_difficulty


# =============================================================================
# 2. DESIGN TOKENS & COLOR PALETTE
# =============================================================================
BG_COLOR       = "#0f1623"
SURFACE_COLOR  = "#1c2540"
SURFACE_ALT    = "#243052"
BORDER_COLOR   = "#2e3f6e"
ACCENT_COLOR   = "#00d4aa"
ACCENT_DIM     = "#00a882"
DANGER_COLOR   = "#ff4d6d"
TEXT_COLOR     = "#e8edf5"
MUTED_TEXT     = "#6b7fa3"
HIGHLIGHT_TEXT = "#ffffff"


# =============================================================================
# 3. LOCALIZATION / LANGUAGE DICTIONARY
# =============================================================================
LANG = {
    "EN": {
        "title": "NSC Medical Suite",
        "subtitle": "Clinical Rehabilitation System",
        "btn_loading": "LOADING ENGINE...",
        "btn_start": "START THERAPY SESSION",
        "btn_opening": "OPENING CAMERA...",
        "btn_cam_error": "CAMERA ERROR - TRY AGAIN",
        "btn_progress": "VIEW PROGRESS",
        "btn_tutorial": "TUTORIAL GUIDE",
        "btn_settings": "SETTINGS",
        "btn_credits": "CREDITS",
        "btn_back": "BACK TO MENU",
        "history_title": "Patient History Log",
        "no_history": "No therapy history recorded.",
        "settings_title": "SETTINGS",
        "vol_music": "Music",
        "vol_sfx": "Sound fx",
        "language": "Language",
        "help": "Help",
        "send_msg": "Send a message",
        "cred_text": "Developed for NSC Competition 2026",
        "tut_title": "Interactive Tutorial",
        "tut_desc": "Coming Soon: Expert Video Guides",
        "chart_title": "7-Day Medical Streak",
        "chart_y": "Sets Completed",
        "ai_insight": "Clinical AI Insights",
        "btn_export": "EXPORT DOCTOR REPORT",
        "export_done": "Report saved to Documents folder!",
        "coach_perfect": "Perfect form! Keep going!",
        "coach_close_more": "Try closing fingers fully",
        "coach_open_more": "Relax - open hand first",
        "coach_spread_more": "Spread fingers wider",
        "coach_hold_steady": "Hold position steady",
        "coach_well_done": "Excellent movement!",
        "coach_two_fingers": "Raise index + middle only",
        "coach_pinch_tighter": "Pinch thumb and index together",
        "coach_tremor_detected": "Tremor detected — rest briefly",
        "guide_box": "Place hand here",
        "ex_1": "1. Open/Close", "ex_2": "2. Thumb", "ex_3": "3. Starfish",
        "ex_4": "4. Wrist", "ex_5": "5. O-Ring", "ex_6": "6. V-Sign",
        "move_closer": "NO HAND: MOVE CLOSER",
        "set": "Set", "rep": "Rep", "daily_goal": "Goal Met!",
        "hud_reset": "RESET [R]",
        "hud_menu": "LEAVE [M]",
        "inst_sq_1": "1. Make Fist", "inst_sq_2": "2. Open Hand",
        "inst_th": "Touch",
        "thumb_names": ["INDEX", "MIDDLE", "RING", "PINKY"],
        "inst_st_1": "1. Relax Hand", "inst_st_2": "2. Spread Fingers",
        "inst_fl_1": "1. Palm Up", "inst_fl_2": "2. Palm Down",
        "inst_or_1": "1. Relax", "inst_or_2": "2. Air Grasp",
        "inst_pe_1": "1. Make Fist", "inst_pe_2": "2. V-Sign",
        "acc_title": "Accuracy:", "acc_excel": "EXCELLENT", "acc_good": "GOOD", "acc_needs": "NEEDS WORK",
        "session_complete": "SESSION COMPLETE",
        "total_ex": "Total Exercises:",
        "btn_ok": "OK",
        "role_1": "Game Design",        "name_1": "Punnatorn Chinpitakwattana",
        "role_2": "Software Developer", "name_2": "Pannawat Khoonton",
        "role_3": "Video Editor",       "name_3": "Phuwasit Khorsermsri",
        "role_4": "Report",             "name_4": "Phuwasit Khorsermsri",
        "btn_ai_chat": "AI CLINICAL ASSISTANT",
        "lbl_login_title": "User Login",
        "lbl_username": "Username",
        "lbl_password": "Password",
        "lbl_remember": "Remember me",
        "lbl_forgot": "Forgot Password?",
        "btn_login": "LOGIN",
        "err_login": "Invalid username or password",
        "btn_logout": "LOG OUT",
    },
    "TH": {
        "title": "ชุดโปรแกรมการแพทย์ NSC",
        "subtitle": "ระบบฟื้นฟูสมรรถภาพทางการแพทย์",
        "btn_loading": "กำลังเตรียมระบบ AI...",
        "btn_start": "เริ่มการบำบัด",
        "btn_opening": "กำลังเชื่อมต่อกล้อง...",
        "btn_cam_error": "ข้อผิดพลาดของกล้อง - ลองอีกครั้ง",
        "btn_progress": "ประวัติและผลการบำบัด",
        "btn_tutorial": "คู่มือการใช้งาน",
        "btn_settings": "ตั้งค่าระบบ",
        "btn_credits": "รายชื่อผู้พัฒนา",
        "btn_back": "กลับสู่เมนูหลัก",
        "history_title": "บันทึกประวัติการบำบัด",
        "no_history": "ยังไม่มีประวัติการบำบัดในระบบ",
        "settings_title": "การตั้งค่า",
        "vol_music": "ระดับเสียงดนตรี",
        "vol_sfx": "ระดับเสียงเอฟเฟกต์",
        "language": "ภาษา",
        "help": "ช่วยเหลือ",
        "send_msg": "ติดต่อเรา",
        "cred_text": "พัฒนาเพื่อการแข่งขัน NSC 2026",
        "tut_title": "คู่มือการใช้งาน",
        "tut_desc": "เร็วๆ นี้: วิดีโอแนะนำจากผู้เชี่ยวชาญ",
        "chart_title": "สถิติการบำบัด 7 วัน",
        "chart_y": "จำนวนเซ็ตที่ทำสำเร็จ",
        "ai_insight": "การวิเคราะห์จาก AI ทางการแพทย์",
        "btn_export": "ส่งออกรายงานแพทย์",
        "export_done": "บันทึกรายงานสำเร้จ!",
        "coach_perfect": "ฟอร์มดีมาก! ทำต่อไป!",
        "coach_close_more": "ลองกำมือให้แน่นขึ้น",
        "coach_open_more": "ผ่อนคลาย แบมือก่อน",
        "coach_spread_more": "กางนิ้วออกให้กว้างกว่านี้",
        "coach_hold_steady": "ค้างท่าให้นิ่ง",
        "coach_well_done": "การเคลื่อนไหวดีเยี่ยม!",
        "coach_two_fingers": "ชูแค่นิ้วชี้และนิ้วกลาง",
        "coach_pinch_tighter": "จีบนิ้วโป้งกับนิ้วชี้ให้แน่นขึ้น",
        "coach_tremor_detected": "พบการสั่น — พักสักครู่",
        "guide_box": "วางมือที่นี่",
        "ex_1": "1. กำมือ/แบมือ", "ex_2": "2. แตะนิ้วโป้ง", "ex_3": "3. ปลาดาว",
        "ex_4": "4. หมุนข้อมือ", "ex_5": "5. จีบนิ้ว", "ex_6": "6. ชูสองนิ้ว",
        "move_closer": "ไม่พบมือ: กรุณาขยับเข้ามาใกล้",
        "set": "เซ็ต", "rep": "ครั้ง", "daily_goal": "สำเร็จเป้าหมาย!",
        "hud_reset": "Reset [R]",
        "hud_menu": "ออก [M]",
        "inst_sq_1": "1. กำมือ", "inst_sq_2": "2. แบมือ",
        "inst_th": "แตะนิ้ว",
        "thumb_names": ["ชี้", "กลาง", "นาง", "ก้อย"],
        "inst_st_1": "1. พักมือ", "inst_st_2": "2. กางนิ้วออก",
        "inst_fl_1": "1. หงายมือ", "inst_fl_2": "2. คว่ำมือ",
        "inst_or_1": "1. พักมือ", "inst_or_2": "2. จีบนิ้ว",
        "inst_pe_1": "1. กำมือ", "inst_pe_2": "2. ชูสองนิ้ว",
        "acc_title": "ความแม่นยำ:", "acc_excel": "ดีเยี่ยม", "acc_good": "ดี", "acc_needs": "พยายามอีกนิด",
        "session_complete": "สรุปผลการบำบัด",
        "total_ex": "จำนวนท่าที่ฝึก:",
        "btn_ok": "ตกลง",
        "role_1": "ออกแบบเกม",       "name_1": "ปัณณธร ชินพิทักษ์วัฒนา",
        "role_2": "พัฒนาซอฟต์แวร์",  "name_2": "ปัณณวัฒน์ ขุนทน",
        "role_3": "ตัดต่อวิดีโอ",     "name_3": "ภูวศิษฎ์ ขอเสริมศรี",
        "role_4": "จัดทำรายงาน",      "name_4": "ภูวศิษฎ์ ขอเสริมศรี",
        "btn_ai_chat": "ผู้ช่วยอัจฉริยะ AI",
        "lbl_login_title": "เข้าสู่ระบบ",
        "lbl_username": "ชื่อผู้ใช้งาน",
        "lbl_password": "รหัสผ่าน",
        "lbl_remember": "จดจำการเข้าระบบ",
        "lbl_forgot": "ลืมรหัสผ่าน?",
        "btn_login": "เข้าสู่ระบบ",
        "err_login": "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง",
        "btn_logout": "ออกจากระบบ",
    },
}


# =============================================================================
# 4. PERFORMANCE OPTIMIZATION CACHES
# =============================================================================
_FONTS: dict[str, object] = {}
_FONTS_LOADED = False
_TEXT_BBOX_CACHE: dict[tuple, tuple[int, int]] = {}
_UI_TEXT_STATE: tuple = ()
_UI_TEXT_RESULT: dict = {}
_PULSE_TABLE = [abs(math.sin(i * math.pi / 128)) for i in range(256)]

def _ensure_fonts():
    """Loads all PIL fonts exactly once for the lifetime of the process."""
    global _FONTS_LOADED
    if _FONTS_LOADED: return

    from PIL import ImageFont
    _FONTS_LOADED = True
    for name, path, size in [
        ("tab",   "tahomabd.ttf", 22),
        ("large", "tahomabd.ttf", 36),
        ("small", "tahomabd.ttf", 20),
        ("coach", "tahomabd.ttf", 28),
        ("tiny",  "tahoma.ttf",   16),
    ]:
        for candidate in (path, path.replace("bd", ""), ""):
            try:
                _FONTS[name] = ImageFont.truetype(candidate, size) if candidate else ImageFont.load_default()
                break
            except Exception:
                continue
        if name not in _FONTS:
            _FONTS[name] = ImageFont.load_default()

def _text_size(draw_obj, text: str, font_obj, font_key: str) -> tuple[int, int]:
    """Returns cached (width, height) of text."""
    cache_key = (text, font_key)
    if cache_key not in _TEXT_BBOX_CACHE:
        bb = draw_obj.textbbox((0, 0), text, font=font_obj)
        _TEXT_BBOX_CACHE[cache_key] = (bb[2] - bb[0], bb[3] - bb[1])
    return _TEXT_BBOX_CACHE[cache_key]

def _draw_centered_text(draw_obj, cx, cy, text, font_obj, fill_color, font_key=""):
    """Draws cached-size centered text to the canvas."""
    if font_key:
        w, h = _text_size(draw_obj, text, font_obj, font_key)
        bb = draw_obj.textbbox((0, 0), text, font=font_obj)
        tx = cx - w / 2 - bb[0]
        ty = cy - h / 2 - bb[1]
    else:
        bb = draw_obj.textbbox((0, 0), text, font=font_obj)
        w, h = bb[2] - bb[0], bb[3] - bb[1]
        tx, ty = cx - w / 2 - bb[0], cy - h / 2 - bb[1]
    draw_obj.text((tx, ty), text, font=font_obj, fill=fill_color)

def _get_ui_text_cached(app) -> dict:
    """Caches UI generation to prevent redundant string rebuilding every frame."""
    ex = app.current_exercise
    state = (
        ex,
        getattr(app, 'sq_state', ''), getattr(app, 'star_state', ''),
        getattr(app, 'flip_state', ''), getattr(app, 'oring_state', ''),
        getattr(app, 'peace_state', ''), getattr(app, 'curr_thumb_idx', 0),
        getattr(app, 'sq_reps', 0), getattr(app, 'sq_sets', 0),
        getattr(app, 'thumb_reps', 0), getattr(app, 'thumb_sets', 0),
        getattr(app, 'star_reps', 0), getattr(app, 'star_sets', 0),
        getattr(app, 'flip_reps', 0), getattr(app, 'flip_sets', 0),
        getattr(app, 'oring_reps', 0), getattr(app, 'oring_sets', 0),
        getattr(app, 'peace_reps', 0), getattr(app, 'peace_sets', 0),
        getattr(app, 'current_lang', 'EN'),
    )
    global _UI_TEXT_STATE, _UI_TEXT_RESULT
    if state != _UI_TEXT_STATE:
        _UI_TEXT_STATE  = state
        _UI_TEXT_RESULT = app._get_current_ui_text()
    return _UI_TEXT_RESULT

def _pulse(now: float) -> float:
    """Returns 0-1 pulse value using pre-computed Sine table."""
    idx = int((now * 60) % 256)
    return _PULSE_TABLE[idx]


# =============================================================================
# 5. USER SETTINGS & IO
# =============================================================================
def get_settings_path():
    app_data_dir = os.path.join(os.path.expanduser("~"), "Documents", "NSC Medical Suite")
    os.makedirs(app_data_dir, exist_ok=True)
    return os.path.join(app_data_dir, "user_settings.json")

def load_user_settings(app):
    path = get_settings_path()
    app.user_settings = {"bgm_vol": 0.5, "sfx_vol": 0.8, "lang": "EN"}
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                app.user_settings.update(json.load(f))
        except Exception:
            pass
    app.current_lang = app.user_settings["lang"]
    audio.set_bgm_volume(app.user_settings["bgm_vol"])
    audio.set_sfx_volume(app.user_settings["sfx_vol"])

def save_user_settings(app):
    try:
        with open(get_settings_path(), "w") as f:
            json.dump(app.user_settings, f)
    except Exception:
        pass

def apply_language(app):
    t = LANG[app.current_lang]

    # Login Screen
    if hasattr(app, 'lbl_login_title'):  app.lbl_login_title.config(text=t["lbl_login_title"])
    if hasattr(app, 'lbl_username'):     app.lbl_username.config(text=t["lbl_username"])
    if hasattr(app, 'lbl_password'):     app.lbl_password.config(text=t["lbl_password"])
    if hasattr(app, 'chk_remember'):     app.chk_remember.config(text=t["lbl_remember"])
    if hasattr(app, 'lbl_forgot'):       app.lbl_forgot.config(text=t["lbl_forgot"])
    if hasattr(app, 'btn_login_submit'): app.btn_login_submit.config(text=t["btn_login"])
    if hasattr(app, 'btn_logout'):       app.btn_logout.config(text=t["btn_logout"])

    # Main Menu
    app.lbl_title.config(text=t["title"])
    app.lbl_subtitle.config(text=t["subtitle"])
    if app.start_btn['state'] == 'normal':
        if "ERROR" in app.start_btn['text'] or "ข้อผิดพลาด" in app.start_btn['text']:
            app.start_btn.config(text=t["btn_cam_error"])
        else:
            app.start_btn.config(text=t["btn_start"])
    else:
        if "OPENING" in app.start_btn['text'] or "เชื่อมต่อกล้อง" in app.start_btn['text']:
            app.start_btn.config(text=t["btn_opening"])
        else:
            app.start_btn.config(text=t["btn_loading"])

    app.btn_prog.config(text=t["btn_progress"])
    app.btn_tut.config(text=t["btn_tutorial"])
    app.btn_set.config(text=t["btn_settings"])
    app.btn_cred.config(text=t["btn_credits"])
    if hasattr(app, 'btn_ai_chat'): app.btn_ai_chat.config(text=t["btn_ai_chat"])

    # Settings Screen
    app.lbl_set_title.config(text=t["settings_title"])
    app.lbl_vol_m.config(text=t["vol_music"])
    app.lbl_vol_s.config(text=t["vol_sfx"])
    app.lbl_lang.config(text=t["language"])
    app.lbl_help.config(text=t["help"])
    app.btn_help.config(text=t["send_msg"])
    app.btn_set_back.config(text=f"< {t['btn_back']}")

    # Progress & Credits
    app.lbl_dash_title.config(text=t["history_title"])
    if hasattr(app, 'btn_dash_back'): app.btn_dash_back.config(text=f"< {t['btn_back']}")
    if hasattr(app, 'btn_export'):    app.btn_export.config(text=t["btn_export"])
    app.lbl_cred_1.config(text=t["cred_text"])
    app.btn_cred_back.config(text=f"< {t['btn_back']}")
    app.lbl_tut_1.config(text=t["tut_title"])
    app.lbl_tut_2.config(text=t["tut_desc"])
    app.btn_tut_back.config(text=f"< {t['btn_back']}")

    if hasattr(app, 'credit_labels'):
        for lbl_role, lbl_name, role_key, name_key in app.credit_labels:
            lbl_role.config(text=t.get(role_key, ""))
            lbl_name.config(text=t.get(name_key, ""))
    if hasattr(app, 'btn_license'):
        app.btn_license.config(text="View License Agreement" if app.current_lang == "EN" else "ข้อตกลงการใช้งาน (License)")

    # Invalidate cache
    global _UI_TEXT_STATE
    _UI_TEXT_STATE = ()

def contact_support():
    webbrowser.open("https://mail.google.com/mail/?view=cm&fs=1&to=6822771034@g.siit.tu.ac.th&su=NSC+Medical+Suite+Support+Request")


# =============================================================================
# 6. REUSABLE WIDGET BUILDERS
# =============================================================================
def _make_primary_btn(parent, text, command, font_obj, state="normal"):
    def _on_enter(e):
        if btn["state"] == "normal": btn.config(bg=ACCENT_COLOR, fg=BG_COLOR)
    def _on_leave(e):
        if btn["state"] == "normal": btn.config(bg=ACCENT_DIM, fg=BG_COLOR)
    def _wrapped():
        try: audio.play_menu_click_sound()
        except Exception: pass
        command()
    btn = tk.Button(parent, text=text, font=font_obj,
        bg=ACCENT_DIM if state == "normal" else SURFACE_ALT,
        fg=BG_COLOR if state == "normal" else MUTED_TEXT,
        relief="flat", borderwidth=0, width=28, pady=13, cursor="hand2",
        command=_wrapped, state=state, activebackground=ACCENT_COLOR, activeforeground=BG_COLOR)
    btn.bind("<Enter>", _on_enter)
    btn.bind("<Leave>", _on_leave)
    return btn

def _make_secondary_btn(parent, text, command, font_obj, width=28):
    def _on_enter(e): btn.config(bg=SURFACE_ALT)
    def _on_leave(e): btn.config(bg=SURFACE_COLOR)
    def _wrapped():
        try: audio.play_menu_click_sound()
        except Exception: pass
        command()
    btn = tk.Button(parent, text=text, font=font_obj, bg=SURFACE_COLOR, fg=TEXT_COLOR,
        relief="flat", borderwidth=0, width=width, pady=11, cursor="hand2",
        command=_wrapped, activebackground=SURFACE_ALT, activeforeground=HIGHLIGHT_TEXT)
    btn.bind("<Enter>", _on_enter)
    btn.bind("<Leave>", _on_leave)
    return btn

def _make_ghost_btn(parent, text, command, font_obj, padx=20, pady=9):
    def _on_enter(e): btn.config(fg=ACCENT_COLOR)
    def _on_leave(e): btn.config(fg=MUTED_TEXT)
    def _wrapped():
        try: audio.play_exit_reset_sound()
        except Exception: pass
        command()
    btn = tk.Button(parent, text=f"< {text}", font=font_obj, bg=BG_COLOR, fg=MUTED_TEXT,
        relief="flat", borderwidth=0, padx=padx, pady=pady, cursor="hand2",
        command=_wrapped, activebackground=BG_COLOR, activeforeground=ACCENT_COLOR)
    btn.bind("<Enter>", _on_enter)
    btn.bind("<Leave>", _on_leave)
    return btn

# =============================================================================
# 7. DISCLAIMER POPUP
# =============================================================================
def show_nsc_disclaimer(app):
    try: audio.play_menu_click_sound()
    except Exception: pass

    win = tk.Toplevel(app.root)
    win_title = "License Agreement" if app.current_lang == "EN" else "ข้อตกลงการใช้งาน"
    win.title(win_title)
    win.geometry("760x540")
    win.configure(bg=BG_COLOR)
    win.resizable(False, False)
    win.transient(app.root)

    px = app.root.winfo_x() + app.root.winfo_width() // 2 - 380
    py = app.root.winfo_y() + app.root.winfo_height() // 2 - 270
    win.geometry(f"+{px}+{py}")

    tk.Frame(win, bg=ACCENT_COLOR, height=4).pack(fill="x")
    header_text = "NSC License Agreement" if app.current_lang == "EN" else "ข้อตกลงในการใช้ซอฟต์แวร์ (NSC License Agreement)"
    tk.Label(win, text=header_text, font=("Leelawadee UI", 16, "bold"), fg=HIGHLIGHT_TEXT, bg=BG_COLOR).pack(pady=(24, 10))

    text_frame = tk.Frame(win, bg=SURFACE_COLOR)
    text_frame.pack(fill="both", expand=True, padx=36, pady=(0, 20))
    sb = tk.Scrollbar(text_frame)
    sb.pack(side="right", fill="y")

    txt = tk.Text(text_frame, wrap="word", font=("Leelawadee UI", 11), bg=SURFACE_COLOR, fg=TEXT_COLOR,
                  relief="flat", padx=20, pady=20, yscrollcommand=sb.set)
    txt.pack(side="left", fill="both", expand=True)
    sb.config(command=txt.yview)

    txt.tag_configure("highlight", foreground=ACCENT_COLOR, font=("Leelawadee UI", 11, "bold"))

    if app.current_lang == "EN":
        txt.insert("end", "This software is a work developed by ")
        txt.insert("end", "Phuwasit Khorsermsri, Punnatorn Chinpitakwattana, and Pannawat Khoonton", "highlight")
        txt.insert("end", " from ")
        txt.insert("end", "Sirindhorn International Institute of Technology (SIIT)", "highlight")
        txt.insert("end", " under the provision of ")
        txt.insert("end", "Prof. David Beckham", "highlight")
        txt.insert("end", " under ")
        txt.insert("end", "RehabAI: Smart Hand Therapy System", "highlight")
        txt.insert("end", """, which has been supported by the National Science and Technology Development Agency """
            """(NSTDA)...\n\nThe intellectual property of this software shall belong to the developer and the """
            """developer gives NSTDA a permission to distribute this software as an "as is" and non-modified """
            """software for a temporary and non-exclusive use without remuneration to anyone for his or her own """
            """purpose or academic purpose, which are not commercial purposes.""")
    else:
        txt.insert("end", "ซอฟต์แวร์นี้เป็นผลงานที่พัฒนาขึ้นโดย ")
        txt.insert("end", "ภูวศิษฏ์ ขอเสริมศรี, ปัณณธร ชินพิทักษ์วัฒนา และ ปัณณวัฒน์ ขุนทน", "highlight")
        txt.insert("end", " จาก ")
        txt.insert("end", "สถาบันเทคโนโลยีนานาชาติสิรินธร (SIIT)", "highlight")
        txt.insert("end", " ภายใต้การดูแลของ ")
        txt.insert("end", "อาจารย์ เดวิด เบคแคม", "highlight")
        txt.insert("end", " ภายใต้โครงการ ")
        txt.insert("end", "RehabAI: Smart Hand Therapy System", "highlight")
        txt.insert("end", """ ซึ่งสนับสนุนโดย สำนักงานพัฒนาวิทยาศาสตร์และเทคโนโลยีแห่งชาติ...\n\n"""
            """ลิขสิทธิ์ของซอฟต์แวร์นี้จึงเป็นของผู้พัฒนา ซึ่งผู้พัฒนาได้อนุญาตให้สำนักงานพัฒนาวิทยาศาสตร์ """
            """และเทคโนโลยีแห่งชาติ เผยแพร่ซอฟต์แวร์นี้ตาม "ต้นฉบับ" โดยไม่มีการแก้ไขดัดแปลงใด ๆ""")
    txt.config(state="disabled")


# =============================================================================
# 8. MAIN UI INITIALIZATION (Tkinter Tree)
# =============================================================================
def init_tkinter_ui(app):
    app.root.configure(bg=BG_COLOR)

    # ── 8.1 Setup Fonts & Auth ──────────────────────────────────
    title_font   = font.Font(family="Leelawadee UI", size=30, weight="bold")
    sub_font     = font.Font(family="Leelawadee UI", size=12)
    btn_font     = font.Font(family="Leelawadee UI", size=13, weight="bold")
    label_font   = font.Font(family="Leelawadee UI", size=12, weight="bold")
    small_font   = font.Font(family="Leelawadee UI", size=11)
    caption_font = font.Font(family="Leelawadee UI", size=9)

    load_user_settings(app)

    auth_dir     = os.path.join(os.path.expanduser("~"), "Documents", "NSC Medical Suite")
    os.makedirs(auth_dir, exist_ok=True)
    users_file   = os.path.join(auth_dir, "users.json")
    session_file = os.path.join(auth_dir, "active_session.json")

    if not os.path.exists(users_file):
        with open(users_file, "w") as f:
            json.dump({"user": {"password": "1234", "profile_id": "p_001"}}, f)

    # ── 8.2 Login Frame ─────────────────────────────────────────
    app.login_frame = tk.Frame(app.root, bg=BG_COLOR)
    login_card = tk.Frame(app.login_frame, bg=SURFACE_COLOR, padx=60, pady=50, highlightbackground=BORDER_COLOR, highlightthickness=1)
    login_card.place(relx=0.5, rely=0.5, anchor="center")

    app.lbl_login_title = tk.Label(login_card, text="User Login", font=("Leelawadee UI", 24, "bold"), fg=HIGHLIGHT_TEXT, bg=SURFACE_COLOR)
    app.lbl_login_title.pack(pady=(0, 30))

    app.lbl_username = tk.Label(login_card, text="Username", font=small_font, fg=MUTED_TEXT, bg=SURFACE_COLOR)
    app.lbl_username.pack(anchor="w")
    app.entry_user = tk.Entry(login_card, font=btn_font, bg=BG_COLOR, fg=TEXT_COLOR, insertbackground=TEXT_COLOR, relief="flat", width=30)
    app.entry_user.pack(fill="x", pady=(5, 15), ipady=10)

    app.lbl_password = tk.Label(login_card, text="Password", font=small_font, fg=MUTED_TEXT, bg=SURFACE_COLOR)
    app.lbl_password.pack(anchor="w")
    app.entry_pass = tk.Entry(login_card, font=btn_font, bg=BG_COLOR, fg=TEXT_COLOR, insertbackground=TEXT_COLOR, relief="flat", show="*", width=30)
    app.entry_pass.pack(fill="x", pady=(5, 10), ipady=10)

    opt_frame = tk.Frame(login_card, bg=SURFACE_COLOR)
    opt_frame.pack(fill="x", pady=(0, 25))
    app.var_remember = tk.BooleanVar(value=True)
    app.chk_remember = tk.Checkbutton(opt_frame, text="Remember me", variable=app.var_remember, bg=SURFACE_COLOR, fg=MUTED_TEXT, selectcolor=BG_COLOR, activebackground=SURFACE_COLOR, activeforeground=TEXT_COLOR, font=caption_font)
    app.chk_remember.pack(side="left")

    app.lbl_forgot = tk.Label(opt_frame, text="Forgot Password?", font=caption_font, fg=ACCENT_COLOR, bg=SURFACE_COLOR, cursor="hand2")
    app.lbl_forgot.pack(side="right")

    app.lbl_login_err = tk.Label(login_card, text="", font=caption_font, fg=DANGER_COLOR, bg=SURFACE_COLOR)
    app.lbl_login_err.pack(pady=(0, 10))

    def attempt_login(event=None):
        try: audio.play_menu_click_sound()
        except Exception: pass
        u, p = app.entry_user.get().strip(), app.entry_pass.get().strip()
        try:
            with open(users_file, "r") as f:
                users_data = json.load(f)
            if u in users_data and users_data[u]["password"] == p:
                app.lbl_login_err.config(text="")
                if app.var_remember.get():
                    with open(session_file, "w") as sf: json.dump({"is_logged_in": True, "username": u}, sf)
                app.login_frame.place_forget()
                app.menu_frame.place(relx=0.5, rely=0.5, anchor="center")
            else:
                app.lbl_login_err.config(text=LANG[app.current_lang].get("err_login", "Invalid credentials"))
        except Exception:
            app.lbl_login_err.config(text="Database Error")

    app.entry_pass.bind("<Return>", attempt_login)
    app.btn_login_submit = tk.Button(login_card, text="LOGIN", font=btn_font, bg=SURFACE_ALT, fg=TEXT_COLOR, relief="flat", borderwidth=0, cursor="hand2", command=attempt_login, activebackground=ACCENT_DIM, activeforeground=BG_COLOR)
    app.btn_login_submit.bind("<Enter>", lambda e: app.btn_login_submit.config(bg=ACCENT_COLOR, fg=BG_COLOR))
    app.btn_login_submit.bind("<Leave>", lambda e: app.btn_login_submit.config(bg=SURFACE_ALT, fg=TEXT_COLOR))
    app.btn_login_submit.pack(fill="x", ipady=12)

    # ── 8.3 Main Menu ───────────────────────────────────────────
    app.menu_frame = tk.Frame(app.root, bg=BG_COLOR)
    brand_block = tk.Frame(app.menu_frame, bg=BG_COLOR)
    brand_block.pack(pady=(50, 0))

    tk.Frame(brand_block, bg=ACCENT_COLOR, height=3, width=60).pack(anchor="center", pady=(0, 10))
    app.lbl_title = tk.Label(brand_block, font=title_font, fg=HIGHLIGHT_TEXT, bg=BG_COLOR)
    app.lbl_title.pack()
    app.lbl_subtitle = tk.Label(brand_block, font=sub_font, fg=MUTED_TEXT, bg=BG_COLOR)
    app.lbl_subtitle.pack(pady=(4, 0))
    tk.Frame(brand_block, bg=BORDER_COLOR, height=1, width=220).pack(anchor="center", pady=(12, 0))

    btn_container = tk.Frame(app.menu_frame, bg=BG_COLOR)
    btn_container.pack(pady=(36, 50))
    t = LANG[app.current_lang]

    app.start_btn = _make_primary_btn(btn_container, t["btn_loading"], app.start_therapy, btn_font, state="disabled")
    app.start_btn.pack(pady=(0, 6))
    tk.Frame(btn_container, bg=BORDER_COLOR, height=1, width=300).pack(pady=10)

    app.btn_prog = _make_secondary_btn(btn_container, t["btn_progress"], app.show_dashboard, btn_font)
    app.btn_prog.pack(pady=4)
    app.btn_tut = _make_secondary_btn(btn_container, t["btn_tutorial"], app.show_coming_soon, btn_font)
    app.btn_tut.pack(pady=4)
    app.btn_set = _make_secondary_btn(btn_container, t["btn_settings"], app.show_settings, btn_font)
    app.btn_set.pack(pady=4)
    app.btn_cred = _make_secondary_btn(btn_container, t["btn_credits"], app.show_credits, btn_font)
    app.btn_cred.pack(pady=4)

    app.chatbot_frame = ClinicalChatbot(app.root, app)

    def open_chatbot():
        try:
            audio.play_menu_click_sound()
        except Exception:
            pass
        app.menu_frame.place_forget()
        app.chatbot_frame.place(x=0, y=0, relwidth=1, relheight=1)
        app.chatbot_frame.lift()

    app.btn_ai_chat = tk.Button(btn_container, text=t["btn_ai_chat"], font=btn_font, bg=SURFACE_COLOR, fg=ACCENT_COLOR,
                                relief="flat", borderwidth=0, width=28, pady=11, cursor="hand2", command=open_chatbot,
                                activebackground=SURFACE_ALT, activeforeground=ACCENT_COLOR)
    app.btn_ai_chat.bind("<Enter>", lambda e: app.btn_ai_chat.config(bg=SURFACE_ALT))
    app.btn_ai_chat.bind("<Leave>", lambda e: app.btn_ai_chat.config(bg=SURFACE_COLOR))
    app.btn_ai_chat.pack(pady=(12, 4))

    # ── 8.4 Settings Frame ──────────────────────────────────────
    app.settings_frame = tk.Frame(app.root, bg=BG_COLOR, width=app.render_w, height=app.render_h)
    app.settings_frame.pack_propagate(False)
    set_topbar = tk.Frame(app.settings_frame, bg=BG_COLOR)
    set_topbar.pack(fill="x", padx=40, pady=(30, 0))
    app.btn_set_back = _make_ghost_btn(set_topbar, t["btn_back"], app.hide_settings, label_font)
    app.btn_set_back.pack(side="left")
    app.lbl_set_title = tk.Label(app.settings_frame, font=title_font, fg=HIGHLIGHT_TEXT, bg=BG_COLOR)
    app.lbl_set_title.pack(pady=(10, 4))
    tk.Frame(app.settings_frame, bg=ACCENT_COLOR, height=2, width=50).pack()

    card = tk.Frame(app.settings_frame, bg=SURFACE_COLOR, padx=36, pady=28, highlightbackground=BORDER_COLOR, highlightthickness=1)
    card.pack(pady=28, ipadx=10)

    def on_music_vol(v): audio.set_bgm_volume(float(v)); app.user_settings["bgm_vol"] = float(v); save_user_settings(app)
    def on_sfx_vol(v):   audio.set_sfx_volume(float(v)); app.user_settings["sfx_vol"] = float(v); save_user_settings(app)

    style = ttk.Style(); style.theme_use("clam")
    style.configure("Custom.Horizontal.TScale", troughcolor=SURFACE_ALT, sliderlength=18, sliderrelief="flat", background=ACCENT_COLOR)
    ROW_PAD = {"pady": 12, "padx": 10}

    app.lbl_vol_m = tk.Label(card, font=label_font, fg=TEXT_COLOR, bg=SURFACE_COLOR, anchor="w", width=18)
    app.lbl_vol_m.grid(row=0, column=0, sticky="w", **ROW_PAD)
    ttk.Scale(card, from_=0.0, to=1.0, value=app.user_settings["bgm_vol"], command=on_music_vol, style="Custom.Horizontal.TScale", length=220).grid(row=0, column=1, sticky="ew", **ROW_PAD)

    app.lbl_vol_s = tk.Label(card, font=label_font, fg=TEXT_COLOR, bg=SURFACE_COLOR, anchor="w", width=18)
    app.lbl_vol_s.grid(row=1, column=0, sticky="w", **ROW_PAD)
    ttk.Scale(card, from_=0.0, to=1.0, value=app.user_settings["sfx_vol"], command=on_sfx_vol, style="Custom.Horizontal.TScale", length=220).grid(row=1, column=1, sticky="ew", **ROW_PAD)

    tk.Frame(card, bg=BORDER_COLOR, height=1).grid(row=2, column=0, columnspan=2, sticky="ew", pady=4)
    app.lbl_lang = tk.Label(card, font=label_font, fg=TEXT_COLOR, bg=SURFACE_COLOR, anchor="w", width=18)
    app.lbl_lang.grid(row=3, column=0, sticky="w", **ROW_PAD)

    style.configure("TCombobox", fieldbackground=SURFACE_ALT, background=SURFACE_ALT, foreground=TEXT_COLOR, arrowcolor=ACCENT_COLOR, bordercolor=BORDER_COLOR, lightcolor=SURFACE_ALT, darkcolor=SURFACE_ALT, selectbackground=ACCENT_DIM, selectforeground=BG_COLOR)
    style.map("TCombobox", fieldbackground=[("readonly", SURFACE_ALT)], foreground=[("readonly", TEXT_COLOR)])
    lang_cb = ttk.Combobox(card, values=["EN", "TH"], state="readonly", font=label_font, width=8)
    lang_cb.set(app.current_lang)

    def change_lang(event):
        app.current_lang = lang_cb.get(); app.user_settings["lang"] = app.current_lang; save_user_settings(app)
        audio.play_menu_click_sound(); apply_language(app)

    lang_cb.bind("<<ComboboxSelected>>", change_lang)
    lang_cb.grid(row=3, column=1, sticky="w", **ROW_PAD)

    tk.Frame(card, bg=BORDER_COLOR, height=1).grid(row=4, column=0, columnspan=2, sticky="ew", pady=4)
    app.lbl_help = tk.Label(card, font=label_font, fg=TEXT_COLOR, bg=SURFACE_COLOR, anchor="w", width=18)
    app.lbl_help.grid(row=5, column=0, sticky="w", **ROW_PAD)
    app.btn_help = tk.Button(card, font=label_font, bg=DANGER_COLOR, fg=HIGHLIGHT_TEXT, relief="flat", borderwidth=0, padx=18, pady=6, cursor="hand2", command=contact_support, activebackground="#ff6b85", activeforeground=HIGHLIGHT_TEXT)
    app.btn_help.grid(row=5, column=1, sticky="w", **ROW_PAD)
    tk.Frame(card, bg=BORDER_COLOR, height=1).grid(row=6, column=0, columnspan=2, sticky="ew", pady=(20, 10))

    def do_logout():
        try:
            audio.play_exit_reset_sound()  # <-- CHANGED TO EXIT SOUND
        except Exception:
            pass

        if hasattr(app, "session_file") and os.path.exists(app.session_file): os.remove(app.session_file)
        app.entry_user.delete(0, tk.END);
        app.entry_pass.delete(0, tk.END)
        app.hide_settings();
        app.menu_frame.place_forget()
        app.login_frame.place(x=0, y=0, relwidth=1, relheight=1)

    app.btn_logout = tk.Button(card, text="LOG OUT", font=label_font, bg=BG_COLOR, fg=DANGER_COLOR, relief="flat", borderwidth=0, cursor="hand2", command=do_logout, activebackground=DANGER_COLOR, activeforeground=HIGHLIGHT_TEXT)
    app.btn_logout.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(0, 10), ipady=5)

    # ── 8.5 Video Frame ─────────────────────────────────────────
    app.video_frame = tk.Frame(app.root, bg="#000000")
    app.video_label = tk.Label(app.video_frame, bg="#000000")
    app.video_label.pack(fill="both", expand=True)
    app.video_label.bind("<Configure>", app._handle_resize)
    app.video_label.bind("<Button-1>", app._handle_click)

    # ── 8.6 Dashboard Frame ─────────────────────────────────────
    app.dashboard_frame = tk.Frame(app.root, bg=BG_COLOR)
    dash_topbar = tk.Frame(app.dashboard_frame, bg=BG_COLOR)
    dash_topbar.pack(fill="x", padx=40, pady=(24, 0))
    app.btn_dash_back = _make_ghost_btn(dash_topbar, t["btn_back"], app.hide_dashboard, label_font)
    app.btn_dash_back.pack(side="left")

    def export_report():
        try:
            from audio import play_success_sound
            play_success_sound()
        except Exception:
            pass

        from tkinter import filedialog
        import csv
        import json
        import os
        from datetime import datetime

        # 1. Setup the Save Dialogue for CSV
        default_name = f"NSC_Clinical_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        doc_path = filedialog.asksaveasfilename(
            initialfile=default_name,
            defaultextension=".csv",
            filetypes=[("CSV Document", "*.csv")],
            title="Save Doctor Report"
        )
        if not doc_path:
            return

        # 2. Define layout and map to exact JSON variables
        exercises = ["SQUEEZE", "THUMB", "STARFISH", "FLIP", "O_RING", "PEACE"]
        prefix_map = {
            "SQUEEZE": "sq", "THUMB": "thumb", "STARFISH": "star",
            "FLIP": "flip", "O_RING": "oring", "PEACE": "peace"
        }

        try:
            with open(doc_path, mode='w', newline='', encoding='utf-8-sig') as file:
                writer = csv.writer(file)
                writer.writerow(["Date"] + exercises)  # Write Headers

                # 3. Read the FULL patient history from the JSON file
                history = {}
                if os.path.exists(app.save_file):
                    try:
                        with open(app.save_file) as f:
                            history = json.load(f)
                    except Exception:
                        pass

                # 4. Write every day of history into the CSV
                if history:
                    for date_key in sorted(history.keys()):
                        day_data = history[date_key]
                        formatted_date = f"{date_key[8:10]}/{date_key[5:7]}/{date_key[0:4]}"
                        row_data = [formatted_date]

                        for ex in exercises:
                            prefix = prefix_map[ex]

                            # Pulls exact reps from JSON (e.g., "sq_reps", "oring_reps")
                            reps = day_data.get(f"{prefix}_reps", 0)
                            row_data.append(reps)

                        writer.writerow(row_data)
                else:
                    # Failsafe: If no history exists, write a blank row so the file isn't empty
                    writer.writerow([datetime.now().strftime("%Y-%m-%d"), 0, 0, 0, 0, 0, 0])

            print(f"[SYSTEM] Formal clinical CSV report generated: {doc_path}")

            if hasattr(app, 'jarvis') and getattr(app.jarvis, 'is_active', False):
                app.jarvis.speak("บันทึกรายงานผลการทำกายภาพบำบัดเรียบร้อยแล้วครับ")

            app.btn_export.config(text=LANG[app.current_lang].get("export_done", "Exported!"), bg=ACCENT_COLOR,
                                  fg=BG_COLOR)
            app.root.after(3000, lambda: app.btn_export.config(text=LANG[app.current_lang].get("btn_export", "Export"),
                                                               bg=SURFACE_ALT, fg=TEXT_COLOR))

        except Exception as e:
            print(f"[EXPORT ERROR]: Could not generate CSV. {e}")
            if hasattr(app, 'jarvis') and getattr(app.jarvis, 'is_active', False):
                app.jarvis.speak("ขออภัยครับ เกิดข้อผิดพลาดในการบันทึกข้อมูล")

    app.btn_export = tk.Button(dash_topbar, font=small_font, bg=SURFACE_ALT, fg=TEXT_COLOR, relief="flat", borderwidth=0, padx=14, pady=7, cursor="hand2", command=export_report, activebackground=ACCENT_DIM, activeforeground=BG_COLOR)
    app.btn_export.pack(side="right")
    title_row = tk.Frame(app.dashboard_frame, bg=BG_COLOR)
    title_row.pack(fill="x", padx=40, pady=(16, 0))
    app.lbl_dash_title = tk.Label(title_row, font=title_font, fg=HIGHLIGHT_TEXT, bg=BG_COLOR, anchor="w")
    app.lbl_dash_title.pack(side="left")
    tk.Frame(app.dashboard_frame, bg=ACCENT_COLOR, height=2, width=50).pack(anchor="w", padx=40)
    app.dash_content = tk.Frame(app.dashboard_frame, bg=BG_COLOR)
    app.dash_content.pack(pady=10, padx=40, fill="both", expand=True)

    # ── 8.7 Credits Frame ───────────────────────────────────────
    app.credits_frame = tk.Frame(app.root, bg=BG_COLOR, width=app.render_w, height=app.render_h)
    app.credits_frame.pack_propagate(False)
    cred_topbar = tk.Frame(app.credits_frame, bg=BG_COLOR)
    cred_topbar.pack(fill="x", padx=40, pady=(24, 0))

    def wrap_cred_back():
        app.hide_credits()

    app.btn_cred_back = _make_ghost_btn(cred_topbar, t["btn_back"], wrap_cred_back, label_font)
    app.btn_cred_back.pack(side="left")
    tk.Label(app.credits_frame, text="CREDITS", font=title_font, fg=HIGHLIGHT_TEXT, bg=BG_COLOR).pack(pady=(20, 2))
    tk.Frame(app.credits_frame, bg=ACCENT_COLOR, height=3, width=48).pack()
    app.lbl_cred_1 = tk.Label(app.credits_frame, font=caption_font, fg=MUTED_TEXT, bg=BG_COLOR)
    app.lbl_cred_1.pack(pady=(8, 24))

    roles_card = tk.Frame(app.credits_frame, bg=SURFACE_COLOR, padx=50, pady=30, highlightbackground=BORDER_COLOR, highlightthickness=1)
    roles_card.pack()
    app.credit_labels = []

    def add_credit(role_key, name_key):
        row = tk.Frame(roles_card, bg=SURFACE_COLOR); row.pack(fill="x", pady=8)
        lbl_role = tk.Label(row, text=t.get(role_key, ""), font=label_font, fg=ACCENT_COLOR, bg=SURFACE_COLOR, width=20, anchor="e")
        lbl_role.pack(side="left", padx=(0, 16))
        tk.Frame(row, bg=BORDER_COLOR, width=1, height=20).pack(side="left", padx=(0, 16))
        lbl_name = tk.Label(row, text=t.get(name_key, ""), font=small_font, fg=TEXT_COLOR, bg=SURFACE_COLOR, anchor="w")
        lbl_name.pack(side="left")
        app.credit_labels.append((lbl_role, lbl_name, role_key, name_key))

    for r, n in [("role_1","name_1"),("role_2","name_2"),("role_3","name_3"),("role_4","name_4")]: add_credit(r, n)
    btn_container_cred = tk.Frame(app.credits_frame, bg=BG_COLOR)
    btn_container_cred.pack(pady=(35, 0))
    app.btn_license = _make_secondary_btn(btn_container_cred, "View License Agreement", lambda: show_nsc_disclaimer(app), btn_font, width=28)
    app.btn_license.pack()

    # ── 8.8 Coming Soon Frame ───────────────────────────────────
    from tutorial import TutorialPlayer

    app.coming_soon_frame = tk.Frame(app.root, bg=BG_COLOR, width=app.render_w, height=app.render_h)
    app.coming_soon_frame.pack_propagate(False)
    tut_topbar = tk.Frame(app.coming_soon_frame, bg=BG_COLOR)
    tut_topbar.pack(fill="x", padx=40, pady=(24, 0))

    def wrap_tut_back():
        app.tut_player.stop()
        app.hide_coming_soon()

    app.btn_tut_back = _make_ghost_btn(tut_topbar, t["btn_back"], wrap_tut_back, label_font)
    app.btn_tut_back.pack(side="left")

    app.lbl_tut_1 = tk.Label(app.coming_soon_frame, font=title_font, fg=HIGHLIGHT_TEXT, bg=BG_COLOR)
    app.lbl_tut_1.pack(pady=(20, 0))
    tk.Frame(app.coming_soon_frame, bg=ACCENT_COLOR, height=2, width=44).pack(pady=(6, 10))
    app.lbl_tut_2 = tk.Label(app.coming_soon_frame)
    app.tut_player = TutorialPlayer(app.coming_soon_frame)

    apply_language(app)
    # ── 8.9 Boot Sequence Validation ────────────────────────────
    app.session_file = os.path.join(os.path.expanduser("~"), "Documents", "NSC Medical Suite", "active_session.json")
    auto_login = False
    if os.path.exists(app.session_file):
        try:
            with open(app.session_file, "r") as f:
                sess = json.load(f)
                if sess.get("is_logged_in"): auto_login = True
        except Exception: pass

    if auto_login: app.menu_frame.place(relx=0.5, rely=0.5, anchor="center")
    else: app.login_frame.place(relx=0, rely=0, relwidth=1, relheight=1)


# =============================================================================
# 9. DASHBOARD CHARTING
# =============================================================================
def _add_progress_chart(app, parent, history):
    plt.rcParams['font.family'] = 'Leelawadee UI'
    plt.rcParams['axes.unicode_minus'] = False
    t = LANG[app.current_lang]
    today = datetime.now()
    days   = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
    labels = [(today - timedelta(days=i)).strftime("%d/%m")    for i in range(6, -1, -1)]

    exercise_keys = [
        ("sq_sets",    "#00d4aa", t.get("ex_1", "1")),
        ("thumb_sets", "#f59e0b", t.get("ex_2", "2")),
        ("star_sets",  "#3b82f6", t.get("ex_3", "3")),
        ("flip_sets",  "#8b5cf6", t.get("ex_4", "4")),
        ("oring_sets", "#ec4899", t.get("ex_5", "5")),
        ("peace_sets", "#ef4444", t.get("ex_6", "6")),
    ]

    fig, ax = plt.subplots(figsize=(9, 3.6), facecolor=BG_COLOR)
    ax.set_facecolor(SURFACE_COLOR)
    highest = 5

    for key, colour, label in exercise_keys:
        values = [history.get(d, {}).get(key, 0) for d in days]
        if values and max(values) > highest: highest = max(values)
        ax.plot(labels, values, color=colour, linewidth=2.5, marker="o", markersize=6, label=label)

    num_ex = len(exercise_keys)
    legend_cols = 3 if num_ex <= 6 else 4
    legend_font = 8 if num_ex <= 6 else 7
    headroom = (num_ex // legend_cols) + 1

    ax.set_ylim(-0.5, highest + headroom * 1.5)
    ax.set_title(t.get("chart_title", "7-Day Streak"), color=TEXT_COLOR, fontsize=11, pad=10)
    ax.set_ylabel(t.get("chart_y", "Sets"), color=MUTED_TEXT, fontsize=9)
    ax.tick_params(colors=MUTED_TEXT, labelsize=9)
    ax.spines[:].set_color(BORDER_COLOR)
    ax.grid(axis="y", color="#2e3f6e", linestyle="--", linewidth=0.7)

    legend = ax.legend(loc="upper left", fontsize=legend_font, framealpha=0.25, labelcolor="white", ncol=legend_cols)
    legend.get_frame().set_facecolor(BG_COLOR)
    fig.tight_layout(pad=1.6)

    chart_frame = tk.Frame(parent, bg=BG_COLOR)
    chart_frame.pack(fill="both", expand=True)
    canvas_widget = FigureCanvasTkAgg(fig, master=chart_frame)
    canvas_widget.draw()
    canvas_widget.get_tk_widget().pack(fill="both", expand=True)
    plt.close(fig)

def populate_dashboard(app):
    for widget in app.dash_content.winfo_children(): widget.destroy()
    t = LANG[app.current_lang]
    history = {}

    if os.path.exists(app.save_file):
        try:
            with open(app.save_file) as f: history = json.load(f)
        except Exception: pass

    if not history:
        tk.Label(app.dash_content, text=t["no_history"], font=("Leelawadee UI", 13), fg=MUTED_TEXT, bg=BG_COLOR).pack(pady=60)
        return

    insight_card = tk.Frame(app.dash_content, bg=SURFACE_COLOR, padx=20, pady=14, highlightbackground=BORDER_COLOR, highlightthickness=1)
    insight_card.pack(fill="x", pady=(0, 14))
    insight_header = tk.Frame(insight_card, bg=SURFACE_COLOR)
    insight_header.pack(fill="x", pady=(0, 6))
    tk.Label(insight_header, text=t['ai_insight'], font=("Leelawadee UI", 11, "bold"), fg="#38bdf8", bg=SURFACE_COLOR, anchor="w").pack(side="left")

    for insight in generate_clinical_insights(history, app.current_lang):
        row = tk.Frame(insight_card, bg=SURFACE_COLOR); row.pack(fill="x", pady=2)
        tk.Label(row, text="—", font=("Leelawadee UI", 10), fg=ACCENT_COLOR, bg=SURFACE_COLOR).pack(side="left", padx=(0,6))
        tk.Label(row, text=insight, font=("Leelawadee UI", 10), fg=TEXT_COLOR, bg=SURFACE_COLOR, anchor="w").pack(side="left")

    tree_frame = tk.Frame(app.dash_content, bg=BG_COLOR); tree_frame.pack(fill="x", pady=(0, 10))
    style = ttk.Style(); style.theme_use("clam")
    style.configure("Treeview", background=SURFACE_COLOR, foreground=TEXT_COLOR, fieldbackground=SURFACE_COLOR, rowheight=32, borderwidth=0, font=("Leelawadee UI", 10))
    style.configure("Treeview.Heading", background=SURFACE_ALT, foreground=ACCENT_COLOR, font=("Leelawadee UI", 10, "bold"), borderwidth=0, relief="flat")
    style.map("Treeview", background=[("selected", ACCENT_DIM)], foreground=[("selected", BG_COLOR)])

    cols = ("Date", "Squeeze", "Thumb", "Starfish", "Wrist", "O-Ring", "Peace")
    tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=5)
    sb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)

    for c in cols:
        tree.heading(c, text=c)
        tree.column(c, anchor="center", width=110 if c == "Date" else 108)
    tree.pack(side="left", fill="x", expand=True); sb.pack(side="right", fill="y")

    def fmt_cell(sets, goal, acc):
        display_acc = acc if sets > 0 else 0
        # Forces the UI to ALWAYS show sets/goal (e.g., 7/3)
        return f"{sets}/{goal} ({display_acc}%)"

    ex_keys = [
        ("sq", "sq_sets", "sq_acc"), ("thumb", "thumb_sets", "thumb_acc"),
        ("star", "star_sets", "star_acc"), ("flip", "flip_sets", "flip_acc"),
        ("oring", "oring_sets", "oring_acc"), ("peace", "peace_sets", "peace_acc"),
    ]
    sorted_dates = sorted(history.keys(), reverse=True)

    from datetime import datetime, timedelta

    for d in sorted_dates:
        v = history[d]
        row_values = [d]

        for prefix, set_key, acc_key in ex_keys:
            sets, acc = v.get(set_key, 0), v.get(acc_key, 0)

            # Pulls your base targets
            base_targets = {"sq": 3, "thumb": 3, "star": 3, "flip": 3, "oring": 4, "peace": 4}
            target = base_targets.get(prefix, 3)

            # --- THE CLINICAL TIME-TRAVEL FIX ---
            # Scan ALL dates before this row so the AI remembers if they leveled up weeks ago
            past_dates = sorted([pd for pd in history.keys() if pd < d])
            consec_good = 0
            consec_poor = 0

            for pd in past_dates:
                p_sets = history[pd].get(set_key, 0)
                p_acc = history[pd].get(acc_key, 0)

                if p_sets == 0:
                    consec_good = 0
                    consec_poor = 0
                    continue

                # Clinical Rule: Exceeded goal with >=80% accuracy
                if p_sets >= target and p_acc >= 80:
                    consec_good += 1
                    consec_poor = 0
                # Clinical Rule: Failed goal OR <50% accuracy
                elif p_sets < target or p_acc < 50:
                    consec_poor += 1
                    consec_good = 0
                else:
                    consec_good = 0
                    consec_poor = 0

                if consec_good >= 2:
                    target = min(8, target + 1)
                    consec_good = 0
                if consec_poor >= 2:
                    target = max(1, target - 1)
                    consec_poor = 0

            row_values.append(fmt_cell(sets, target, acc))

        tree.insert("", "end", values=tuple(row_values))

    # --- YOUR CHART REMAINS UNTOUCHED ---
    chart_wrapper = tk.Frame(app.dash_content, bg=BG_COLOR)
    chart_wrapper.pack(fill="both", expand=True)
    _add_progress_chart(app, chart_wrapper, history)


# =============================================================================
# 10. SESSION SUMMARY
# =============================================================================
def show_session_summary(app):
    if getattr(app, "summary_open", False): return
    try:
        audio.play_celebration_sound()
    except Exception:
        pass
    try:
        total_frames = sum(d["frames"] for d in app.session_acc.values())
        if total_frames == 0: return
        avg_acc  = int(sum(d["sum"] for d in app.session_acc.values()) / total_frames)
        total_ex = sum(1 for d in app.session_acc.values() if d['frames'] > 0)
    except Exception:
        return

    app.summary_open = True
    t = LANG[app.current_lang]

    if avg_acc >= 85:   q_text, q_color = t.get("acc_excel", "EXCELLENT"), ACCENT_COLOR
    elif avg_acc >= 60: q_text, q_color = t.get("acc_good", "GOOD"), "#f59e0b"
    else:               q_text, q_color = t.get("acc_needs", "NEEDS WORK"), DANGER_COLOR

    summary_win = tk.Toplevel(app.root)
    summary_win.title(t.get("session_complete", "Session Complete"))
    summary_win.geometry("440x340"); summary_win.configure(bg=BG_COLOR)
    summary_win.resizable(False, False); summary_win.transient(app.root)

    px = app.root.winfo_x() + app.root.winfo_width()  // 2 - 220
    py = app.root.winfo_y() + app.root.winfo_height() // 2 - 170
    summary_win.geometry(f"440x340+{px}+{py}")

    def close_summary():
        app.summary_open = False; summary_win.destroy()
    summary_win.protocol("WM_DELETE_WINDOW", close_summary)

    tk.Frame(summary_win, bg=ACCENT_COLOR, height=4).pack(fill="x")
    header_frame = tk.Frame(summary_win, bg=BG_COLOR); header_frame.pack(fill="x", padx=36, pady=(24, 0))
    tk.Label(header_frame, text=t.get("session_complete", "SESSION COMPLETE"), font=("Leelawadee UI", 18, "bold"), fg=HIGHLIGHT_TEXT, bg=BG_COLOR, anchor="w").pack(side="left")
    tk.Frame(summary_win, bg=BORDER_COLOR, height=1).pack(fill="x", padx=36, pady=(14, 0))

    stats_card = tk.Frame(summary_win, bg=SURFACE_COLOR, padx=28, pady=18, highlightbackground=BORDER_COLOR, highlightthickness=1)
    stats_card.pack(fill="x", padx=36, pady=14)

    ex_row = tk.Frame(stats_card, bg=SURFACE_COLOR); ex_row.pack(fill="x", pady=(0, 10))
    tk.Label(ex_row, text=t.get("total_ex", "Total Exercises:"), font=("Leelawadee UI", 12), fg=MUTED_TEXT, bg=SURFACE_COLOR, anchor="w").pack(side="left")
    tk.Label(ex_row, text=str(total_ex), font=("Leelawadee UI", 14, "bold"), fg=HIGHLIGHT_TEXT, bg=SURFACE_COLOR).pack(side="right")
    tk.Frame(stats_card, bg=BORDER_COLOR, height=1).pack(fill="x", pady=4)

    acc_row = tk.Frame(stats_card, bg=SURFACE_COLOR); acc_row.pack(fill="x", pady=(10, 0))
    tk.Label(acc_row, text=t.get("acc_title", "Accuracy:"), font=("Leelawadee UI", 12), fg=MUTED_TEXT, bg=SURFACE_COLOR, anchor="w").pack(side="left")
    acc_right = tk.Frame(acc_row, bg=SURFACE_COLOR); acc_right.pack(side="right")
    tk.Label(acc_right, text=f"{avg_acc}%", font=("Leelawadee UI", 14, "bold"), fg=HIGHLIGHT_TEXT, bg=SURFACE_COLOR).pack(side="left", padx=(0, 8))
    tk.Label(acc_right, text=q_text, font=("Leelawadee UI", 10, "bold"), fg=q_color, bg=SURFACE_COLOR).pack(side="left")

    ok_btn = tk.Button(summary_win, text=t.get("btn_ok", "OK"), command=close_summary, font=("Leelawadee UI", 12, "bold"), bg=ACCENT_DIM, fg=BG_COLOR, relief="flat", padx=40, pady=10, cursor="hand2", activebackground=ACCENT_COLOR, activeforeground=BG_COLOR)
    ok_btn.bind("<Enter>", lambda e: ok_btn.config(bg=ACCENT_COLOR))
    ok_btn.bind("<Leave>", lambda e: ok_btn.config(bg=ACCENT_DIM))
    ok_btn.pack(pady=(0, 24))

    for ex in app.session_acc:
        app.session_acc[ex] = {"sum": 0, "frames": 0}


# =============================================================================
# 11. PIL DRAW HELPERS (Restored)
# =============================================================================
def _pil_rounded_fill(draw, x1, y1, x2, y2, fill, radius=12):
    draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=fill)


def _pil_rounded_outline(draw, x1, y1, x2, y2, outline, width=2, radius=12):
    draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, outline=outline, width=width)


def _blend_rect(img_arr, np, x1, y1, x2, y2, fill_rgb, alpha=0.72):
    h_arr, w_arr = img_arr.shape[:2]
    x1, y1 = max(0, int(x1)), max(0, int(y1))
    x2, y2 = min(w_arr, int(x2)), min(h_arr, int(y2))
    if x2 <= x1 or y2 <= y1: return
    roi = img_arr[y1:y2, x1:x2].astype(float)
    fill = np.array(fill_rgb[:3], dtype=float)
    img_arr[y1:y2, x1:x2] = (roi * (1 - alpha) + fill * alpha).clip(0, 255).astype(np.uint8)


# =============================================================================
# 12. OPENCV HUD / RENDERER (Optimized Hot Path)
# =============================================================================
def recalc_ui_metrics(app):
    w, h = app.render_w, app.render_h
    app.ui = {
        "btn_w": w // 6, "btn_h": max(60, h // 11),
        "menu_w": 140, "menu_h": 45,
        "reset_w": 140, "reset_h": 45,
    }
    app.ui["menu_x"], app.ui["menu_y"] = 24, h - 75
    app.ui["reset_x"], app.ui["reset_y"] = w - 164, h - 75


def draw_dashboard(app, canvas):
    cv2 = _ensure_cv2()
    np = _ensure_np()
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return

    _ensure_fonts()
    f_tab = _FONTS["tab"]
    f_large = _FONTS["large"]
    f_small = _FONTS["small"]
    f_coach = _FONTS["coach"]
    f_tiny = _FONTS["tiny"]

    u = app.ui
    w = app.render_w
    h = app.render_h
    t = LANG[app.current_lang]
    now = time.time()

    ui_data = _get_ui_text_cached(app)
    hand_visible = not (now - app.last_correct_time > 5.0)

    exs = ["SQUEEZE", "THUMB", "STARFISH", "FLIP", "O_RING", "PEACE"]
    try:
        active_idx = exs.index(app.current_exercise)
    except:
        active_idx = 0

    top_h = u["btn_h"]
    _blend_rect(canvas, np, 0, 0, w, top_h, (10, 18, 30), alpha=0.82)

    tab_w = u["btn_w"]
    ax1 = active_idx * tab_w + 4
    ax2 = ax1 + tab_w - 8
    _blend_rect(canvas, np, ax1, 4, ax2, top_h - 4, (0, 168, 130), alpha=0.90)
    canvas[top_h - 3:top_h, ax1:ax2] = (0, 212, 170)

    for i in range(1, 6):
        sx = i * tab_w
        canvas[8:top_h - 8, sx:sx + 1] = (46, 63, 110)

    bot_y = h - 95
    _blend_rect(canvas, np, 0, bot_y, w, h, (10, 18, 30), alpha=0.85)
    canvas[bot_y:bot_y + 1, :] = (46, 63, 110)

    img_pil = Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)

    labels = [t["ex_1"], t["ex_2"], t["ex_3"], t["ex_4"], t["ex_5"], t["ex_6"]]
    for i, text in enumerate(labels):
        color = (255, 255, 255) if i == active_idx else (130, 155, 195)
        _draw_centered_text(draw, i * tab_w + tab_w / 2, top_h / 2, text, f_tab, color, f"tab_{i}")

    if not hand_visible:
        gx1, gy1 = w // 4, top_h + 24
        gx2, gy2 = w - w // 4, h - 110
        pulse_v = _pulse(now)
        line_col = (0, int(180 + pulse_v * 75), int(140 + pulse_v * 60))
        corner_len = 32
        for cx, cy, sx, sy in [(gx1, gy1, 1, 1), (gx2, gy1, -1, 1), (gx1, gy2, 1, -1), (gx2, gy2, -1, -1)]:
            draw.line([(cx, cy), (cx + sx * corner_len, cy)], fill=line_col, width=3)
            draw.line([(cx, cy), (cx, cy + sy * corner_len)], fill=line_col, width=3)

        guide_text = t["guide_box"]
        gw_, gh_ = _text_size(draw, guide_text, f_small, "guide_box")
        gcx, gcy = (gx1 + gx2) // 2, (gy1 + gy2) // 2
        _pil_rounded_fill(draw, gcx - gw_ / 2 - 14, gcy - gh_ / 2 - 8, gcx + gw_ / 2 + 14, gcy + gh_ / 2 + 8,
                          fill=(10, 22, 36), radius=10)
        _draw_centered_text(draw, gcx, gcy, guide_text, f_small, (0, 212, 170), "guide_box")

        warn_text = t["move_closer"]
        ww_, wh_ = _text_size(draw, warn_text, f_small, "move_closer")
        wx1, wy1 = 20, bot_y - wh_ - 30
        wx2, wy2 = wx1 + ww_ + 24, wy1 + wh_ + 14
        _pil_rounded_fill(draw, wx1, wy1, wx2, wy2, fill=(60, 10, 20), radius=10)
        _pil_rounded_outline(draw, wx1, wy1, wx2, wy2, outline=(255, 77, 109), width=2, radius=10)
        _draw_centered_text(draw, (wx1 + wx2) / 2, (wy1 + wy2) / 2, warn_text, f_small, (255, 100, 120), "move_closer")

    if ui_data.get("inst"):
        hold_pct = 0.0
        if app.hold_start_time > 0:
            hold_pct = min(1.0, (now - app.hold_start_time) / app.hold_duration)
        bar_w, bar_h = 400, 8
        bx = (w - bar_w) // 2
        by = bot_y + 75
        _pil_rounded_fill(draw, bx, by, bx + bar_w, by + bar_h, fill=(36, 48, 76), radius=4)
        if hold_pct > 0:
            _pil_rounded_fill(draw, bx, by, bx + int(bar_w * hold_pct), by + bar_h, fill=(0, 180, 220), radius=4)

        header = f"{ui_data['inst']}  ·  {ui_data['progress_text']}"
        _draw_centered_text(draw, w / 2, bot_y + 42, header, f_large, (232, 237, 245), "hdr_" + header[:20])

        btn_r = 10
        mx1, my1 = u["menu_x"], u["menu_y"]
        mx2, my2 = mx1 + u["menu_w"], my1 + u["menu_h"]
        _pil_rounded_fill(draw, mx1, my1, mx2, my2, fill=(50, 38, 80), radius=btn_r)
        _pil_rounded_outline(draw, mx1, my1, mx2, my2, outline=(120, 80, 180), width=2, radius=btn_r)
        _draw_centered_text(draw, mx1 + u["menu_w"] / 2, my1 + u["menu_h"] / 2, t["hud_menu"], f_small, (200, 180, 255),
                            "hud_menu")

        rx1, ry1 = u["reset_x"], u["reset_y"]
        rx2, ry2 = rx1 + u["reset_w"], ry1 + u["reset_h"]
        _pil_rounded_fill(draw, rx1, ry1, rx2, ry2, fill=(60, 30, 20), radius=btn_r)
        _pil_rounded_outline(draw, rx1, ry1, rx2, ry2, outline=(160, 100, 60), width=2, radius=btn_r)
        _draw_centered_text(draw, rx1 + u["reset_w"] / 2, ry1 + u["reset_h"] / 2, t["hud_reset"], f_small,
                            (255, 190, 120), "hud_reset")

    accuracy = getattr(app, "current_accuracy", 0)
    if hand_visible and accuracy > 0:
        if accuracy >= 85:
            qual_text, qual_color = t.get("acc_excel", "EXCELLENT"), (0, 212, 170)
            badge_bg, badge_brd = (0, 40, 32), (0, 160, 130)
        elif accuracy >= 60:
            qual_text, qual_color = t.get("acc_good", "GOOD"), (245, 158, 11)
            badge_bg, badge_brd = (40, 30, 0), (180, 120, 0)
        else:
            qual_text, qual_color = t.get("acc_needs", "NEEDS WORK"), (255, 100, 120)
            badge_bg, badge_brd = (50, 10, 18), (200, 50, 80)

        acc_line1 = f"{accuracy}%"
        acc_line2 = qual_text
        w1, h1 = _text_size(draw, acc_line1, f_large, f"acc_pct_{accuracy}")
        w2, h2 = _text_size(draw, acc_line2, f_tiny, f"acc_qual_{accuracy}")
        gap, pad_x, pad_y = 14, 40, 16
        card_w = max(w1, w2) + pad_x
        card_h = h1 + gap + h2 + pad_y * 2
        cx1, cy1 = 24, top_h + 24
        cx2, cy2 = cx1 + card_w, cy1 + card_h

        _pil_rounded_fill(draw, cx1, cy1, cx2, cy2, fill=badge_bg, radius=14)
        _pil_rounded_outline(draw, cx1, cy1, cx2, cy2, outline=badge_brd, width=2, radius=14)
        _draw_centered_text(draw, cx1 + card_w / 2, cy1 + pad_y + h1 / 2, acc_line1, f_large, qual_color,
                            f"acc_pct_{accuracy}")
        _draw_centered_text(draw, cx1 + card_w / 2, cy1 + pad_y + h1 + gap + h2 / 2, acc_line2, f_tiny, qual_color,
                            f"acc_qual_{accuracy}")

    coach_text = getattr(app, "coach_msg", "")
    coach_type = getattr(app, "coach_msg_type", "neutral")
    if coach_text and hand_visible:
        c_color, c_bg, c_brd = {
            "good": ((0, 212, 170), (0, 30, 24), (0, 140, 110)),
            "warn": ((245, 158, 11), (40, 28, 0), (170, 110, 0)),
            "neutral": ((210, 220, 235), (20, 28, 46), (60, 80, 120)),
        }.get(coach_type, ((210, 220, 235), (20, 28, 46), (60, 80, 120)))

        cw_, ch_ = _text_size(draw, coach_text, f_coach, f"coach_{coach_text[:20]}")
        px1 = (w - cw_) // 2 - 24
        py1 = top_h + 20
        px2, py2 = px1 + cw_ + 48, py1 + ch_ + 20

        _pil_rounded_fill(draw, px1, py1, px2, py2, fill=c_bg, radius=14)
        _pil_rounded_outline(draw, px1, py1, px2, py2, outline=c_brd, width=2, radius=14)
        _draw_centered_text(draw, (px1 + px2) / 2, (py1 + py2) / 2, coach_text, f_coach, c_color,
                            f"coach_{coach_text[:20]}")

    canvas[:] = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
