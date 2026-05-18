"""
===============================================================================
NSC Medical Suite - Clinical Chatbot Module (Optimised)
===============================================================================
Provides a text-based AI assistant interface using Google Gemini.
Automatically pulls patient therapy data to provide context-aware medical
guidance. Includes robust async handling and live rate-limit countdowns.
===============================================================================
"""

from __future__ import annotations

import os
import re
import json
import threading
import tkinter as tk
from tkinter import scrolledtext
from typing import Any

import google.generativeai as genai

from logic import evaluate_adaptive_difficulty

# =============================================================================
# 1. API CONFIGURATION & DESIGN TOKENS
# =============================================================================
API_KEY = "AQ.Ab8RN6I6nmenS4G4tiA_f-qfpjEdt5jUU0NGs9XoKkA2X-F8TA"

BG_COLOR = "#0f1623"
SURFACE_COLOR = "#1c2540"
ACCENT_COLOR = "#00d4aa"
TEXT_COLOR = "#e8edf5"
MUTED_TEXT = "#6b7fa3"
HIGHLIGHT_TEXT = "#ffffff"


# =============================================================================
# 2. CHATBOT GUI CLASS
# =============================================================================
class ClinicalChatbot(tk.Frame):
    """
    Tkinter Frame containing the chat interface, input controls, and background
    threading logic for communicating with the Gemini API safely.
    """

    def __init__(self, parent: Any, app: Any):
        super().__init__(parent, bg=BG_COLOR)
        self.app = app
        self.ai_ready = False

        # ── Boot Sequence ──
        self._initialize_ai()
        self._build_gui()

    # =========================================================================
    # 3. AI INITIALIZATION & CONTEXT GATHERING
    # =========================================================================
    def _initialize_ai(self) -> None:
        """Reads local patient data, formulates the system prompt, and boots Gemini."""
        # 3.1 Fetch Patient History
        history = {}
        if hasattr(self.app, 'save_file') and os.path.exists(self.app.save_file):
            try:
                with open(self.app.save_file) as f:
                    history = json.load(f)
            except Exception:
                pass

        # 3.2 Calculate Today's Targets via logic.py
        try:
            diff_res = evaluate_adaptive_difficulty(history)
            current_targets = diff_res[1] if isinstance(diff_res, tuple) else diff_res
        except Exception:
            current_targets = {}

        # 3.3 Format Targets for AI Consumption
        target_str = ""
        ex_names = {
            "sq": "Squeeze (กำมือ/แบมือ)",
            "thumb": "Thumb Touch (แตะนิ้วโป้ง)",
            "star": "Starfish (ปลาดาว)",
            "flip": "Wrist Flip (หมุนข้อมือ)",
            "oring": "O-Ring (จีบนิ้ว)",
            "peace": "V-Sign (ชูสองนิ้ว)"
        }

        for key, name in ex_names.items():
            val = current_targets.get(key, [2, 20])
            goal = val[0] if isinstance(val, (list, tuple)) else int(val)
            target_str += f"- {name}: {goal} Sets\n"

        # 3.4 Build System Prompt
        system_prompt = f"""You are a highly professional Physical Therapy Assistant for 'NSC Medical Suite'.

        STRICT RULES:
        1. LANGUAGE: You MUST strictly reply in the exact same language the user uses. If they type in English, reply ONLY in English. If they type in Thai, reply ONLY in Thai.
        2. FORMATTING: Output PLAIN TEXT ONLY. Do NOT use any markdown formatting (no asterisks **, no bolding, no hashtag). Use simple text layout.
        3. TONE: Maintain a highly professional, clinical, and polite tone. Do NOT use any emojis under any circumstances.
        4. MEDICAL SAFETY: If a patient feels sharp pain, advise them to rest immediately and see a doctor.

        [CRITICAL PATIENT DATA]
        Here is the patient's exact workout plan for TODAY:
        {target_str}

        IMPORTANT RULE: You ALREADY know their fitness plan. Do NOT ask the patient about their fitness goals, equipment, or current level. 
        If the patient asks about their sets or workout today, answer them directly using ONLY the [CRITICAL PATIENT DATA] provided above.
        """

        # 3.5 Configure API Session
        try:
            genai.configure(api_key=API_KEY)
            self.model = genai.GenerativeModel(
                model_name="gemini-2.5-flash",
                system_instruction=system_prompt
            )
            self.chat_session = self.model.start_chat(history=[])
            self.ai_ready = True
        except Exception:
            self.ai_ready = False

    # =========================================================================
    # 4. GUI CONSTRUCTION
    # =========================================================================
    def _build_gui(self) -> None:
        """Assembles the Tkinter widgets for the chat interface."""
        # 4.1 Top Header & Back Button
        header = tk.Frame(self, bg=BG_COLOR)
        header.pack(fill="x", padx=40, pady=(30, 0))

        back_btn = tk.Button(
            header, text="< BACK TO MENU", font=("Leelawadee UI", 12, "bold"),
            bg=BG_COLOR, fg=MUTED_TEXT, relief="flat", borderwidth=0,
            cursor="hand2", command=self.hide
        )
        back_btn.pack(side="left")
        back_btn.bind("<Enter>", lambda e: back_btn.config(fg=ACCENT_COLOR))
        back_btn.bind("<Leave>", lambda e: back_btn.config(fg=MUTED_TEXT))

        # 4.2 Title
        tk.Label(
            self, text="AI CLINICAL ASSISTANT", font=("Leelawadee UI", 24, "bold"),
            fg=HIGHLIGHT_TEXT, bg=BG_COLOR
        ).pack(pady=(20, 10))
        tk.Frame(self, bg=ACCENT_COLOR, height=3, width=50).pack()

        # 4.3 Chat History Area
        self.chat_card = tk.Frame(
            self, bg=SURFACE_COLOR, padx=2, pady=2,
            highlightbackground="#2e3f6e", highlightthickness=1
        )
        self.chat_card.pack(fill="both", expand=True, padx=60, pady=(30, 20))

        self.chat_area = scrolledtext.ScrolledText(
            self.chat_card, wrap=tk.WORD, font=("Leelawadee UI", 11),
            bg=BG_COLOR, fg=TEXT_COLOR, borderwidth=0, padx=20, pady=20
        )
        self.chat_area.pack(fill="both", expand=True)
        self.chat_area.config(state='disabled')

        # 4.4 Input Area
        input_container = tk.Frame(self, bg=BG_COLOR)
        input_container.pack(fill="x", padx=60, pady=(0, 40))

        self.msg_entry = tk.Entry(
            input_container, font=("Leelawadee UI", 13), bg=SURFACE_COLOR,
            fg=TEXT_COLOR, insertbackground=TEXT_COLOR, relief="flat"
        )
        self.msg_entry.pack(side="left", fill="x", expand=True, ipady=12, padx=(0, 15))
        self.msg_entry.bind("<Return>", lambda e: self.send_message())

        self.send_btn = tk.Button(
            input_container, text="SEND MESSAGE", font=("Leelawadee UI", 11, "bold"),
            bg=ACCENT_COLOR, fg=BG_COLOR, relief="flat", padx=30,
            command=self.send_message, cursor="hand2"
        )
        self.send_btn.pack(side="right", ipady=10)

        # 4.5 Welcome Message
        self.display_msg("Assistant",
                         "Hello! I am your AI Assistant. How can I help you with your physical therapy today?")

    # =========================================================================
    # 5. USER INTERACTION & ASYNC LOGIC
    # =========================================================================
    def hide(self) -> None:
        """Hides the chatbot frame and returns to the main application menu."""
        self.place_forget()
        self.app.menu_frame.place(relx=0.5, rely=0.5, anchor="center")

    def send_message(self) -> None:
        """Reads user input, updates UI, and spawns the API thread."""
        user_text = self.msg_entry.get().strip()
        if not user_text:
            return

        self.display_msg("You", user_text)
        self.msg_entry.delete(0, tk.END)

        # Lock UI during API request
        self.msg_entry.config(state="disabled")
        self.send_btn.config(state="disabled", text="THINKING...")

        threading.Thread(target=self.fetch_ai_response, args=(user_text,), daemon=True).start()

    def fetch_ai_response(self, user_text: str) -> None:
        """Background worker that calls the Gemini API."""
        if not getattr(self, 'ai_ready', False) or API_KEY == "YOUR_API_KEY_HERE":
            self.after(0, lambda: self.finish_ai_response("[System Alert] Please configure a valid Gemini API Key."))
            return

        try:
            response = self.chat_session.send_message(user_text)
            reply = response.text
            self.after(0, lambda: self.finish_ai_response(reply))

        except Exception as e:
            error_msg = str(e)

            # Detect Rate Limit (429) or Quota limits
            if "429" in error_msg or "quota" in error_msg.lower():
                match = re.search(r"retry in ([\d\.]+)s", error_msg)
                if match:
                    wait_seconds = int(float(match.group(1))) + 2
                else:
                    wait_seconds = 60

                self.after(0, lambda: self.start_countdown(wait_seconds, user_text))

            else:
                reply = "[System Error] Please check your internet connection."
                self.after(0, lambda: self.finish_ai_response(reply))

    # =========================================================================
    # 6. RATE LIMIT COUNTDOWN (UI Updates)
    # =========================================================================
    def start_countdown(self, wait_seconds: int, user_text: str) -> None:
        """Initializes the live countdown sequence in the chat window."""
        self.chat_area.config(state='normal')
        self.cd_index = self.chat_area.index("end-1c")
        self.chat_area.insert(tk.END, "\n[Initializing auto-retry sequence...]\n")
        self.chat_area.config(state='disabled')
        self.chat_area.yview(tk.END)

        self.update_countdown(wait_seconds, user_text)

    def update_countdown(self, remaining: int, user_text: str) -> None:
        """Recursively updates the countdown timer every 1000ms."""
        if remaining > 0:
            m = remaining // 60
            s = remaining % 60
            t_str = f"{m} min {s} sec" if m > 0 else f"{s} seconds"

            new_msg = f"System Alert: AI quota limit reached. Auto-retrying in {t_str}..."

            self.chat_area.config(state='normal')
            self.chat_area.delete(self.cd_index, self.cd_index + " lineend")
            self.chat_area.insert(self.cd_index, new_msg, ("warning",))
            self.chat_area.tag_config("warning", foreground="#f59e0b", font=("Leelawadee UI", 10, "italic"))
            self.chat_area.config(state='disabled')

            self.send_btn.config(text=f"WAIT {t_str}")

            # Re-call this function after 1 second
            self.after(1000, lambda: self.update_countdown(remaining - 1, user_text))
        else:
            # Countdown finished, clean up and retry
            self.chat_area.config(state='normal')
            self.chat_area.delete(self.cd_index, self.cd_index + " lineend")
            self.chat_area.config(state='disabled')

            self.send_btn.config(text="RETRYING...")

            threading.Thread(target=self.fetch_ai_response, args=(user_text,), daemon=True).start()

    # =========================================================================
    # 7. UI PRESENTATION HELPERS
    # =========================================================================
    def finish_ai_response(self, reply: str) -> None:
        """Unlocks the UI and renders the AI's final text."""
        self.display_msg("Assistant", reply)
        self.msg_entry.config(state="normal")
        self.send_btn.config(state="normal", text="SEND MESSAGE")
        self.msg_entry.focus()

    def display_msg(self, sender: str, text: str) -> None:
        """Appends a formatted message to the scrolled text area."""
        self.chat_area.config(state='normal')

        self.chat_area.insert(tk.END, f"\n{sender.upper()}\n", (sender,))
        self.chat_area.tag_config("Assistant", foreground=ACCENT_COLOR, font=("Leelawadee UI", 10, "bold"))
        self.chat_area.tag_config("You", foreground=MUTED_TEXT, font=("Leelawadee UI", 10, "bold"))

        self.chat_area.insert(tk.END, f"{text}\n")

        self.chat_area.config(state='disabled')
        self.chat_area.yview(tk.END)
