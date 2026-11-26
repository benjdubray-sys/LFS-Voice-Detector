"""Téléchargement et chargement du modèle de reconnaissance vocale (faster-whisper)."""
import os
import threading

from . import config as C

# Taille approximative des téléchargements, en Mo (sert à la barre de progression)
MODEL_MB = {"tiny": 75, "base": 145, "small": 485, "medium": 1500, "large-v3": 3000}


def _dir_size(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def is_downloaded(size):
    try:
        from faster_whisper.utils import download_model
        download_model(size, cache_dir=C.MODELS_DIR, local_files_only=True)
        return True
    except Exception:
        return False


def ensure(size, progress):
    """Renvoie le dossier du modèle, en le téléchargeant si besoin (progress(pct 0-99))."""
    from faster_whisper.utils import download_model
    try:
        return download_model(size, cache_dir=C.MODELS_DIR, local_files_only=True)
    except Exception:
        pass
    os.makedirs(C.MODELS_DIR, exist_ok=True)
    stop = threading.Event()
    expected = MODEL_MB.get(size, 500) * 1024 * 1024

    def poll():
        while not stop.wait(0.5):
            progress(min(99, int(_dir_size(C.MODELS_DIR) * 100 / expected)))

    threading.Thread(target=poll, daemon=True).start()
    try:
        return download_model(size, cache_dir=C.MODELS_DIR)
    finally:
        stop.set()


def _warmup(model):
    """Force un vrai calcul. Les bibliothèques CUDA manquantes (cublas, cudnn) ne se
    plaignent pas au chargement du modèle mais seulement au premier calcul."""
    import numpy as np
    segments, _ = model.transcribe(np.zeros(16000, dtype="float32"), language="en",
                                   beam_size=1, vad_filter=False)
    for _ in segments:
        pass


def load(size, device, progress, log):
    from faster_whisper import WhisperModel
    path = ensure(size, progress)
    if device == "cuda":
        try:
            model = WhisperModel(path, device="cuda", compute_type="float16")
            _warmup(model)
            return model
        except Exception as e:
            log(f"NVIDIA GPU mode unavailable ({e}); using the CPU instead")
    return WhisperModel(path, device="cpu", compute_type="int8")
