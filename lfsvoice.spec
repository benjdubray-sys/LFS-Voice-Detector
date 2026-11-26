# -*- mode: python ; coding: utf-8 -*-
# Build : pyinstaller --noconfirm lfsvoice.spec   (voir build.bat)
# Mode "onedir" volontairement : démarrage plus rapide, moins de faux positifs
# antivirus qu'un .exe unique, et pygame (LGPL) reste un fichier séparé remplaçable.
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
for pkg in ("faster_whisper", "ctranslate2", "onnxruntime", "av", "sounddevice",
            "_sounddevice_data", "pygame", "keyboard", "tokenizers", "huggingface_hub"):
    try:
        d, b, h = collect_all(pkg)
    except Exception as exc:  # paquet absent ou sans données : on continue
        print(f"collect_all({pkg}) ignoré : {exc}")
        continue
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["run_lfsvoice.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["matplotlib", "scipy", "pandas", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LFSVoice",
    console=False,      # application fenêtrée, sans console noire
    upx=False,          # UPX augmente les faux positifs antivirus
    icon=None,          # mets ici "icon.ico" si tu en crées un
)
coll = COLLECT(exe, a.binaries, a.datas, name="LFSVoice", upx=False)
