"""Chemins et réglages de LFS Voice (stockés dans %APPDATA%\\LFSVoice)."""
import copy
import json
import os

APP_NAME = "LFSVoice"


def data_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, APP_NAME)
    os.makedirs(d, exist_ok=True)
    return d


DATA_DIR = data_dir()
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
LOG_PATH = os.path.join(DATA_DIR, "lfsvoice.log")
MODELS_DIR = os.path.join(DATA_DIR, "models")

# bindings : liste de
#   {"kind": "joystick", "device": "<nom>", "button": <int 0-based>, "lang": None | "fr"}
#   {"kind": "keyboard", "key": "alt+f9", "lang": None | "fr"}
# lang None = détection automatique parmi allowed_languages
DEFAULTS = {
    "ui_language": "en",
    "bindings": [],
    "allowed_languages": ["en"],
    "model_size": "small",
    "device": "cpu",          # "cpu" (sûr) ou "cuda" (expérimental, nécessite les bibliothèques CUDA)
    "mic_device": None,       # nom du micro, None = défaut du système
    "send_mode": "auto",      # "auto" | "keys" | "insim"
    "chat_key": "t",
    "clean_delay": 0.15,      # secondes ; None = désactivé
    "min_seconds": 0.4,
    "lfs_exe": "",
    "insim_port": 29999,
}


def load():
    cfg = copy.deepcopy(DEFAULTS)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            cfg.update({k: v for k, v in data.items() if k in DEFAULTS})
    except FileNotFoundError:
        pass
    except Exception:
        pass  # fichier corrompu : on repart des valeurs par défaut
    return cfg


def save(cfg):
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    os.replace(tmp, CONFIG_PATH)


def find_lfs():
    """Cherche LFS.exe aux emplacements habituels. Renvoie '' si introuvable."""
    subs = ("LFS", "Live for Speed", "Games\\LFS", "Games\\Live for Speed",
            "Program Files (x86)\\Live for Speed", "Program Files\\Live for Speed")
    for drive in "CDEFGHIJ":
        for sub in subs:
            p = f"{drive}:\\{sub}\\LFS.exe"
            if os.path.isfile(p):
                return p
    return ""
