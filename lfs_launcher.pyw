"""
Lance le script vocal ET LFS ensemble, puis arrête le script vocal quand LFS
se ferme. Aucun processus ne tourne en dehors de ta session de jeu.
Les messages du script vocal sont écrits dans lfs_voice.log (même dossier).
"""
import ctypes
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "lfs_voice.py")
LOG = os.path.join(HERE, "lfs_voice.log")
LFS_EXE = ""           # chemin complet de LFS.exe, ex. r"F:\LFS\LFS.exe" ; vide = détection auto
NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW


def alert(msg):
    ctypes.windll.user32.MessageBoxW(0, msg, "LFS Voice", 0x10)


def find_lfs():
    if LFS_EXE and os.path.isfile(LFS_EXE):
        return LFS_EXE
    # Chemin enregistré par l'interface graphique (config.json)
    try:
        import json
        with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
            p = json.load(f).get("LFS_EXE", "")
        if p and os.path.isfile(p):
            return p
    except Exception:
        pass
    # Cherche LFS.exe dans le dossier du script puis dans son dossier parent
    for d in (HERE, os.path.dirname(HERE)):
        p = os.path.join(d, "LFS.exe")
        if os.path.isfile(p):
            return p
    return None


def main():
    exe = find_lfs()
    if not exe:
        alert("LFS.exe introuvable.\nRenseigne LFS_EXE dans lfs_launcher.pyw.")
        return

    log = open(LOG, "w", encoding="utf-8")
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    voice = subprocess.Popen(
        [sys.executable, SCRIPT], cwd=HERE, env=env,
        stdout=log, stderr=subprocess.STDOUT, creationflags=NO_WINDOW,
    )
    try:
        game = subprocess.Popen([exe], cwd=os.path.dirname(exe))
        game.wait()  # attend la fermeture de LFS
    finally:
        if voice.poll() is None:
            voice.terminate()


if __name__ == "__main__":
    main()
