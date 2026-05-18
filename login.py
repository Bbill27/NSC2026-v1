"""
===============================================================================
NSC Medical Suite - Authentication Module (Optimised)
===============================================================================
Handles secure user login, registration, and local JSON database management.
Designed to seamlessly integrate with the main Tkinter application flow.
===============================================================================
"""

from __future__ import annotations

import os
import json
import tkinter as tk

# =============================================================================
# 1. DESIGN TOKENS (Synced with ui.py)
# =============================================================================
BG_COLOR = "#0f1623"  # Near-black navy
SURFACE_ALT = "#243052"  # Slightly lifted surface
ACCENT_COLOR = "#00d4aa"  # Teal-green
ACCENT_DIM = "#00a882"  # Dimmed accent
HIGHLIGHT_TEXT = "#ffffff"  # Pure white labels
DANGER_COLOR = "#ff4d6d"  # Warning red
TEXT_COLOR = "#e8edf5"  # Primary text


# =============================================================================
# 2. LOCAL DATABASE UTILITIES
# =============================================================================
def get_db_path() -> str:
    """Returns the absolute path to the local user database JSON file."""
    app_data_dir = os.path.join(os.path.expanduser("~"), "Documents", "NSC Medical Suite")
    os.makedirs(app_data_dir, exist_ok=True)
    return os.path.join(app_data_dir, "users_db.json")


def load_users_db() -> dict:
    """Loads the user database from disk. Returns an empty dict if not found."""
    path = get_db_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_users_db(db: dict) -> None:
    """Saves the user database dictionary to disk."""
    try:
        with open(get_db_path(), "w", encoding="utf-8") as f:
            json.dump(db, f, indent=4)
    except Exception:
        pass


# =============================================================================
# 3. LOGIN SCREEN GUI
# =============================================================================
class LoginScreen:
    """
    Renders the authentication overlay and handles credential validation.
    Calls the provided `on_success` callback upon valid login.
    """

    def __init__(self, root: tk.Tk, on_success: callable):
        self.root = root
        self.on_success = on_success

        # ── 3.1 Main Container ──────────────────────────────────────────
        self.frame = tk.Frame(self.root, bg=BG_COLOR)
        self.frame.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(
            self.frame, text="CLINICAL LOGIN",
            font=("Leelawadee UI", 24, "bold"), fg=HIGHLIGHT_TEXT, bg=BG_COLOR
        ).pack(pady=(0, 30))

        # ── 3.2 Username Input ──────────────────────────────────────────
        u_frame = tk.Frame(self.frame, bg=BG_COLOR)
        u_frame.pack(fill="x", pady=8)

        tk.Label(
            u_frame, text="👤", font=("Leelawadee UI", 16),
            fg=ACCENT_COLOR, bg=SURFACE_ALT, width=3, pady=6
        ).pack(side="left")

        self.ent_user = tk.Entry(
            u_frame, font=("Leelawadee UI", 14),
            bg=HIGHLIGHT_TEXT, fg="#000000", relief="flat", width=20
        )
        self.ent_user.pack(side="left", ipady=8, padx=(2, 0))

        # ── 3.3 Password Input ──────────────────────────────────────────
        p_frame = tk.Frame(self.frame, bg=BG_COLOR)
        p_frame.pack(fill="x", pady=8)

        tk.Label(
            p_frame, text="🔒", font=("Leelawadee UI", 16),
            fg=ACCENT_COLOR, bg=SURFACE_ALT, width=3, pady=6
        ).pack(side="left")

        self.ent_pass = tk.Entry(
            p_frame, font=("Leelawadee UI", 14),
            bg=HIGHLIGHT_TEXT, fg="#000000", relief="flat", width=20, show="*"
        )
        self.ent_pass.pack(side="left", ipady=8, padx=(2, 0))

        # Allow hitting 'Enter' to attempt login
        self.ent_pass.bind("<Return>", lambda e: self.attempt_login())

        # ── 3.4 Error / Status Label ────────────────────────────────────
        self.lbl_err = tk.Label(
            self.frame, text="", font=("Leelawadee UI", 10),
            fg=DANGER_COLOR, bg=BG_COLOR
        )
        self.lbl_err.pack(pady=4)

        # ── 3.5 Action Buttons ──────────────────────────────────────────
        btn_f = tk.Frame(self.frame, bg=BG_COLOR)
        btn_f.pack(pady=(10, 0))

        # Login Button
        self.btn_login = tk.Button(
            btn_f, text="Log in", font=("Leelawadee UI", 12, "bold"),
            bg=ACCENT_DIM, fg=BG_COLOR, relief="flat", width=10, pady=8,
            command=self.attempt_login, cursor="hand2",
            activebackground=ACCENT_COLOR, activeforeground=BG_COLOR
        )
        self.btn_login.pack(side="left", padx=5)

        # Sign Up Button
        self.btn_signup = tk.Button(
            btn_f, text="Sign up", font=("Leelawadee UI", 12, "bold"),
            bg=SURFACE_ALT, fg=HIGHLIGHT_TEXT, relief="flat", width=10, pady=8,
            command=self.attempt_signup, cursor="hand2",
            activebackground=ACCENT_DIM, activeforeground=BG_COLOR
        )
        self.btn_signup.pack(side="left", padx=5)

        # Hover Effects
        self.btn_login.bind("<Enter>", lambda e: self.btn_login.config(bg=ACCENT_COLOR))
        self.btn_login.bind("<Leave>", lambda e: self.btn_login.config(bg=ACCENT_DIM))
        self.btn_signup.bind("<Enter>", lambda e: self.btn_signup.config(bg=ACCENT_DIM))
        self.btn_signup.bind("<Leave>", lambda e: self.btn_signup.config(bg=SURFACE_ALT))

    # =============================================================================
    # 4. AUTHENTICATION LOGIC
    # =============================================================================
    def attempt_login(self) -> None:
        """Validates credentials against the local JSON database."""
        user = self.ent_user.get().strip()
        pw = self.ent_pass.get().strip()

        db = load_users_db()

        if user in db and db[user]["password"] == pw:
            self.frame.destroy()
            self.on_success(user)  # Pass control back to the main app
        else:
            self.lbl_err.config(text="Invalid credentials!", fg=DANGER_COLOR)

    def attempt_signup(self) -> None:
        """Creates a new user profile if the credentials meet requirements."""
        user = self.ent_user.get().strip()
        pw = self.ent_pass.get().strip()

        db = load_users_db()

        if len(user) < 3 or len(pw) < 3:
            self.lbl_err.config(text="Min 3 characters required.", fg=DANGER_COLOR)
            return

        if user in db:
            self.lbl_err.config(text="User already exists!", fg=DANGER_COLOR)
        else:
            db[user] = {"password": pw}
            save_users_db(db)
            self.lbl_err.config(text="Account created! Please log in.", fg=ACCENT_COLOR)
