# NSC Medical Suite

**AI-Powered Clinical Rehabilitation Tracking System** built for the National Software Contest (NSC).

## Quick Start: Download and Run
To evaluate the software immediately without downloading the source code or installing Python libraries, please download our compiled launcher. 

**Download Launcher:** (https://drive.google.com/file/d/13cJJREbfQCYJE9hNPWmiwMs3Mf_yrDKz/view?usp=sharing)

# Login password

**Username**: user           **Password**: 1234

**Instructions:**
1. Download the setup executable from the Google Drive link above.
2. Run the installer and follow the standard setup prompts.
3. Launch the application directly from your desktop shortcut.

## Core Features
* **Real-Time AI Tracking:** Utilizes MediaPipe and OpenCV to accurately track patient joint angles and exercise mechanics.
* **Offline Patient Privacy:** All user profiles and therapy progression data are stored strictly locally on the user's hard drive. No cloud database is required.
* **Clinical CSV Export:** Automatically formats and exports patient session data into time-stamped spreadsheets for clinical review.
* **Integrated Clinical AI:** Features an offline-connected AI assistant capable of retrieving and discussing the user's local rehabilitation progress.

## Developer Source Code
If you wish to review the raw Python files:
1. Clone this repository.
2. Install the required dependencies: `pip install -r requirements.txt`
3. Execute `main.py` to run from source (keep the `assets/` folder next to it).

## New: Interactive Tutorial and Finger Piano (patient, fully offline)
* **Interactive Guide** (`tutorial_mode.py`, `hand_model.py`): an animated *ghost hand* shows every step of an
  exercise, then the patient copies it. A live checklist shows which part is right
  (for example "Ring finger bent"), using the same geometry as the scoring engine. A step passes when the real
  score stays at 70 or more for a short hold. Practice never counts as therapy and never triggers the fatigue lock.
* **Finger Piano** (`piano_game.py`): piano-tiles game on the Piano Fingers exercise. Six public-domain songs,
  four speeds, and a **Wait mode** where tiles wait for the patient (no way to lose). Notes are synthesised in
  code. Each four finger lifts count as one Piano rep in today's therapy record. Results show hit rate per finger
  and reaction time and are saved to `game_scores.json`.
* **Hospital-style UI**: light theme, larger text, "Today's prescription" card on the menu.
* Tests: `python tests/test_hand_model.py` and `python tests/test_piano_game.py`.

## Known limitations
* **Scoring on widescreen cameras.** `logic.py` measures finger spread and thumb distance in normalised image
  coordinates, so the same hand scores differently on 16:9 and 4:3 webcams. With synthetic hands the *Finger Spread*
  (step 2) and *Hitchhiker* (thumb out) steps could not reach 70 on 16:9. Please verify with a real hand and, if
  needed, correct the aspect ratio before measuring (the tutorial offers "Skip this step" meanwhile).
* **Voice coaching needs internet** (edge-tts). Offline, voice is silent; all instructions are also on screen.

