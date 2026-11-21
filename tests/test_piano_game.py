"""Headless playthrough of the piano game with a simulated patient."""
import os, sys, types, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HOME"] = tempfile.mkdtemp()          # keep score files out of the real Documents folder
sys.modules['audio'] = types.SimpleNamespace(speak_message=lambda *a, **k: None, play_success_sound=lambda: None,
    play_celebration_sound=lambda: None, play_menu_click_sound=lambda: None, sfx_vol=0.8)
import numpy as np
import piano_game as PG
from hand_model import EXERCISE_POSES, pose_landmarks, HandPose
from hand_model import _PIANO_REST

class App:
    current_lang = "EN"
    def __init__(self): self.credited = 0
    def credit_reps(self, ex, n, acc=None): self.credited += n
    class root: 
        @staticmethod
        def after(*a, **k): pass

REST = pose_landmarks(_PIANO_REST, frame=(1000, 1000), palm_px=260)
LIFT = [pose_landmarks(p, frame=(1000, 1000), palm_px=260) for p in EXERCISE_POSES["PIANO"]]
FRAME = np.zeros((720, 1280, 3), np.uint8)

def play(wait_mode, skill, song_idx=0, speed_idx=1, hand_gap=None):
    """skill: probability the patient lifts the right finger when a tile is due."""
    rng = np.random.default_rng(1)
    app = App(); m = PG.PianoGameMode(app)
    m.song_idx, m.speed_idx, m.wait_mode = song_idx, speed_idx, wait_mode
    m.handle_action("play")
    now, fps = 1000.0, 30
    lifting, lift_until = None, 0
    will_play = {}                       # decided ONCE per note, not per frame
    for frame in range(30 * 400):
        now += 1 / fps
        lms = REST
        if m.state == "PLAY":
            if lifting is not None and now < lift_until:
                lms = LIFT[lifting]
            else:
                lifting = None
                due = [n for n in m.chart if n["state"] == "wait" and 0 <= m.song_time - n["time"] + 0.05 < 0.25
                       or (n["state"] == "wait" and wait_mode and m.song_time >= n["time"] - 1e-6)]
                if due and will_play.setdefault(id(due[0]), rng.random() < skill):
                    n = due[0]
                    lifting = m.lane_finger[n["lane"]]
                    lift_until = now + 0.35
                    lms = LIFT[lifting]
        if hand_gap and m.state == "PLAY" and hand_gap[0] <= frame <= hand_gap[1]:
            lms = None
        m.on_frame(FRAME, lms, now, (1600, 900))
        if m.state == "RESULT":
            return m, app, frame
    return m, app, None

def test_wait_mode_cannot_fail():
    m, app, done = play(True, 1.0)
    assert done is not None, f"game never finished (state={m.state})"
    assert m.accuracy == 100, m.accuracy
    assert app.credited == m.reps_credited == len(m.chart) // 4

def test_normal_mode_perfect_player():
    m, app, done = play(False, 1.0, speed_idx=0)
    assert done is not None, f"state={m.state}"
    assert m.accuracy >= 90, m.accuracy

def test_normal_mode_bad_player_still_finishes():
    m, app, done = play(False, 0.3, speed_idx=1)
    assert done is not None
    assert 0 <= m.accuracy < 70, m.accuracy

def test_pause_when_hand_leaves():
    m, app, done = play(True, 1.0, hand_gap=(150, 400))
    assert done is not None and m.accuracy == 100

def test_all_songs_chart_ok():
    for s in PG.SONGS:
        for bpm, *_ in PG.SPEEDS:
            ch = PG.build_chart(s, bpm)
            assert len(ch) == len(s["notes"])
            assert {n["lane"] for n in ch} <= {0, 1, 2, 3}
            assert all(b["time"] > a["time"] for a, b in zip(ch, ch[1:]))

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
