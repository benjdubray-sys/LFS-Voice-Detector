# LFS Voice

Push-to-talk speech-to-chat for **Live for Speed**: hold a wheel button, speak,
release — your message is sent to the LFS chat. Built for VR players who cannot
type while driving.

*Parle, relâche, le message part dans le chat de LFS. Conçu pour la VR.*

- Interface in the 24 official EU languages (English, français, Deutsch, …).
- Speech recognition in 23 EU languages (Irish is not supported by Whisper).
- Wheel/gamepad buttons or keyboard keys, one language per button if you wish.
- Works offline after the first start (the speech model is downloaded once).

## For players — install

1. Download `LFSVoice-Setup.exe`, run it (no administrator rights needed).
2. Open **LFS Voice**. Tab **Buttons** → *Add wheel button* → press the button.
3. Press **Start**. The first start downloads the speech model (~485 MB for
   the default quality) — a progress percentage is shown.
4. In LFS, type `/insim=29999` once in the chat (needed for accents and non-Latin
   alphabets; without it the app falls back to simulated keystrokes).
5. Hold the button, speak, release.

**Launch LFS** starts the game and the speech engine together and stops the engine
when you close LFS.

If your keys are not detected, run LFS Voice as administrator.

## For the maintainer — build

Needs Windows, Python 3.12 (`winget install Python.Python.3.12`) and optionally
Inno Setup 6 (`winget install JRSoftware.InnoSetup`).

```
build.bat
```

→ `dist\LFSVoice\LFSVoice.exe` (application) and
`installer_output\LFSVoice-Setup.exe` (installer).

Run from source: `py -3.12 -m pip install -r requirements.txt` then
`py -3.12 run_lfsvoice.py`. Tests (no Windows needed): `python -m unittest discover -s tests`.

### Layout

| File | Role |
|---|---|
| `run_lfsvoice.py` | Entry point, first-run defaults |
| `lfsvoice/gui.py` | tkinter interface |
| `lfsvoice/engine.py` | Record → transcribe → send |
| `lfsvoice/insim.py` | InSim link (auto-connect / reconnect) |
| `lfsvoice/lfsenc.py` | Encoding for the LFS chat (code pages) |
| `lfsvoice/joystick.py` | Wheel button monitor (pygame) |
| `lfsvoice/models.py` | Model download / loading |
| `lfsvoice/i18n.py` | Translations (edit a language block to fix it) |
| `lfsvoice.spec`, `installer.iss`, `build.bat` | Packaging |

Settings and logs live in `%APPDATA%\LFSVoice` (`config.json`, `lfsvoice.log`, `models\`).

## Known limits

-  Expect a first round of fixes.
- **Translations were written without native-speaker review.** Please correct them.
- **Display of non-Latin-1 languages needs InSim.** LFS chat uses Windows code
  pages. The app selects the right one (Latin, Central European, Baltic, Greek,
  Cyrillic) for each message; characters LFS cannot show are replaced by the
  nearest letter or `?`. Without InSim, only Latin-1 languages are typed correctly.
- **Recognition quality varies by language.** Whisper is strongest in English and
  major European languages; Maltese, Latvian, Lithuanian, Croatian, etc. are weaker.
  Use a higher quality setting or force the language with a dedicated button.
- **NVIDIA GPU mode is experimental** (needs CUDA libraries that are not bundled).
- **Antivirus:** programs that read global keys can be flagged. The installer is not
  code-signed; publish the source so users can verify.
- **Anti-cheat / server rules:** the app only types in the chat like a keyboard, or
  uses LFS's own InSim interface. Check the LFS forum rules before announcing it.
- Messages are limited to 95 bytes per chat line; longer ones are split.
