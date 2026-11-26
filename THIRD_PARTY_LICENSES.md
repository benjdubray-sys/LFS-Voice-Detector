# Third-party software / Logiciels tiers

LFS Voice bundles or downloads the components below. Licences are listed to the
best of the author's knowledge — **verify each one against the version you ship**
before distributing, and keep the licence texts that come with each package.

| Component | Licence | Role |
|---|---|---|
| faster-whisper | MIT | Speech recognition engine |
| CTranslate2 | MIT | Inference backend of faster-whisper |
| OpenAI Whisper model weights (downloaded at first start, `Systran/faster-whisper-*`) | MIT | Speech recognition models |
| ONNX Runtime | MIT | Voice-activity detection |
| PyAV | BSD-3-Clause (bundles FFmpeg libraries under their own licence — verify) | Audio decoding |
| tokenizers, huggingface_hub | Apache-2.0 | Model loading / download |
| keyboard | MIT | Global hotkeys, simulated key presses |
| sounddevice (+ PortAudio) | MIT | Microphone capture |
| NumPy | BSD-3-Clause | Audio arrays |
| pygame | LGPL-2.1 | Reading wheel / gamepad buttons |
| Python, tkinter | PSF | Runtime and user interface |
| PyInstaller (build tool) | GPL-2.0 with bootloader exception | Packaging |
| Inno Setup (build tool) | Inno Setup licence | Installer |

**pygame (LGPL):** the application is packaged in "one-directory" mode so that
the pygame library stays a separate, replaceable file.

LFS Voice is not affiliated with Scawen Roadgames or Live for Speed.
"Live for Speed" and "LFS" belong to their owners.
