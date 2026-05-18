# NSC Medical Suite

**AI-Powered Clinical Rehabilitation Tracking System** built for the National Software Contest (NSC).

## Quick Start: Download and Run
To evaluate the software immediately without downloading the source code or installing Python libraries, please download our compiled launcher. 

**Download Launcher:** (https://drive.google.com/file/d/13cJJREbfQCYJE9hNPWmiwMs3Mf_yrDKz/view?usp=sharing)

# Login password

**Username**: user
**Password**: 1234

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
2. Install the required dependencies: `pip install opencv-python mediapipe pygame google-genai`
3. Execute `main.py` to run from source.
