import time
import json
import os

class FatigueDetector:
    def __init__(self):
        # Time tracking
        self.last_state = ""
        self.state_start_time = time.time()

        # Velocity / Speed tracking
        self.rep_durations = []
        self.baseline_speed = 0.0

        # Enforcement locks
        self.is_locked = False
        self.lock_end_time = 0
        self.cooldown_file = "fatigue_cooldown.json"

        # Check if the patient tried to escape a previous lockout!
        self._load_cooldown_state()

    def _load_cooldown_state(self):
        """Reads the hard drive on boot to see if a penalty is still active."""
        if os.path.exists(self.cooldown_file):
            try:
                with open(self.cooldown_file, "r") as f:
                    data = json.load(f)
                    saved_end_time = data.get("lock_end_time", 0)

                    # If the current computer time is STILL less than the penalty end time...
                    if time.time() < saved_end_time:
                        self.is_locked = True
                        self.lock_end_time = saved_end_time
            except Exception:
                pass

    def _save_cooldown_state(self):
        """Saves the exact unescapable end time to the hard drive."""
        try:
            with open(self.cooldown_file, "w") as f:
                json.dump({"lock_end_time": self.lock_end_time}, f)
        except Exception:
            pass

    def check_fatigue(self, current_state, current_lang="EN", hand_visible=True):
        """
        Evaluates real-time fatigue and safely pauses if the hand leaves the camera frame.
        Returns: (Lock_Game_Boolean, Warning_Message, Message_Color)
        """
        now = time.time()

        # ── 1. HANDLE ACTIVE CLINICAL LOCKOUT (Must come first!) ──
        if self.is_locked:
            if now < self.lock_end_time:
                remain = int(self.lock_end_time - now)
                msg = f"Take a break ({remain}s)" if current_lang == "EN" else f"พักกล้ามเนื้อ ({remain} วิ)"
                return True, msg, "warn"
            else:
                # Rest period over, release the lock
                self.is_locked = False
                self.state_start_time = now
                self.rep_durations.clear()
                self.lock_end_time = 0
                self._save_cooldown_state() # <-- Clear the penalty from disk

        # ── 2. THE CAMERA PAUSE CONDITION ──
        if not hand_visible:
            self.state_start_time = now
            self.last_state = "NO_HAND"
            return False, "", "neutral"

        # ── 3. TRACK STATE CHANGES (Successful Rep) ──
        if current_state != self.last_state:
            if "WAITING" in self.last_state and self.last_state != "NO_HAND":
                duration = now - self.state_start_time
                self.rep_durations.append(duration)
                if len(self.rep_durations) > 5:
                    self.rep_durations.pop(0)

            self.last_state = current_state
            self.state_start_time = now
            return False, "", "neutral"

        # ── 4. DETECT "STRUGGLE" (Time-to-Target Fatigue) ──
        is_active_state = "WAITING" in current_state and "RELAX" not in current_state
        time_in_state = now - self.state_start_time

        if is_active_state:
            # MILD FATIGUE: Just a gentle UI warning
            if 12.0 < time_in_state <= 20.0:
                msg = "You seem tired. Do your best!" if current_lang == "EN" else "พยายามอีกนิด ค่อยๆทำ"
                return False, msg, "warn"

            # HIGH FATIGUE: Hard Stop / Safety Lockout
            elif time_in_state > 20.0:
                print(f"[FATIGUE SYSTEM] Muscle failure detected in state: {current_state}")
                self.is_locked = True
                self.lock_end_time = now + 20.0  # Force 20-second mandatory rest
                self._save_cooldown_state()      # <-- Save the penalty to disk

                try:
                    import audio
                    audio.play_exit_reset_sound()
                except Exception:
                    pass

                return True, "Fatigue Detected!", "warn"

        return False, "", "neutral"
