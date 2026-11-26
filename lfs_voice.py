"""
LFS Voice Chat - parle pour envoyer un message dans Live For Speed (via InSim).

Dépendances (Windows) :
    pip install faster-whisper sounddevice numpy keyboard

Dans LFS, active InSim en tapant dans le chat :   /insim=29999
Lance ensuite ce script (en administrateur : la lib "keyboard" l'exige parfois
pour capter une touche quand le jeu est au premier plan).

Utilisation : maintiens la touche PTT_KEY, parle, relâche -> le message part.
"""

import socket
import struct
import threading
import time

import keyboard
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

# ---------------- Configuration ----------------
HOST = "127.0.0.1"
PORT = 29999            # même port que /insim=29999
PTT_KEY = "alt+f9"      # touche push-to-talk (mappe un bouton de volant dessus)
CHAT_KEY = "t"          # touche qui ouvre l'invite de chat dans LFS
# Délai (s) avant d'effacer le "t" parasite qui reste dans l'invite après l'ouverture.
# Augmente-le (0.3, 0.5) si un "t" reste malgré tout ; mets None pour désactiver.
CHAT_CLEAN_DELAY = 0.15
# False : le script tape le texte puis appuie sur Entrée (comme toi au clavier)
# True  : il ferme l'invite (Echap) et envoie le texte via InSim
#         (plus fiable pour les accents, nécessite /insim=29999 dans LFS)
USE_INSIM = False

# Lecture directe d'un bouton du volant (recommandé avec un volant).
# None = désactivé (seule la touche clavier PTT_KEY est utilisée).
# Sinon mets le numéro du bouton (trouvé avec joy_test.py).
JOY_BUTTON = 2
JOY_INDEX = 1           # 0 = premier volant/manette détecté (ici : Thrustmaster)
# Boutons supplémentaires qui FORCENT une langue (aucune détection, donc fiable).
# Exemple : {3: "en"} -> le bouton n°3 transcrit toujours en anglais.
# Trouve les numéros avec joy_test.py.
JOY_LANG_BUTTONS = {}
# Langue de reconnaissance :
#   None  = détection automatique à chaque message, limitée à ALLOWED_LANGUAGES
#   "fr"  = toujours cette langue (plus fiable, pas de détection)
LANGUAGE = None
ALLOWED_LANGUAGES = ["fr", "en"]   # ajoute-en : "es", "de", "it", "pt", "nl"…
MODEL_SIZE = "small"    # "base" = plus rapide, "medium" = plus précis
DEVICE = "cpu"          # "cuda" si tu as une carte NVIDIA configurée pour CUDA
COMPUTE_TYPE = "int8"   # "float16" avec cuda
MIN_SECONDS = 0.4       # ignore les appuis trop courts
SAMPLE_RATE = 16000
# -----------------------------------------------

# Réglages enregistrés par l'interface graphique (config.json, même dossier) :
# s'il existe, il remplace les valeurs ci-dessus.
import json
import os

_CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
if os.path.isfile(_CFG):
    try:
        with open(_CFG, encoding="utf-8") as _f:
            _data = json.load(_f)
        if "JOY_LANG_BUTTONS" in _data:
            _data["JOY_LANG_BUTTONS"] = {int(k): v for k, v in _data["JOY_LANG_BUTTONS"].items()}
        globals().update({k: v for k, v in _data.items() if k in globals()})
    except Exception as _e:
        print(f"config.json ignoré : {_e}")

ISP_ISI, ISP_TINY, ISP_MSX = 1, 3, 38
MAX_MSG = 95  # IS_MSX : 96 octets dont le \0 final


class InSim:
    def __init__(self, host, port):
        self.sock = socket.create_connection((host, port), timeout=5)
        self.sock.settimeout(None)
        self.lock = threading.Lock()
        # IS_ISI : Size=44/4, Type, ReqI, Zero, UDPPort, Flags, InSimVer, Prefix, Interval, Admin, IName
        isi = struct.pack("<BBBBHHBBH16s16s", 11, ISP_ISI, 1, 0, 0, 0, 8, 0, 0, b"", b"VoiceChat")
        self.sock.sendall(isi)
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        """Lit les paquets entrants et répond aux keepalive (TINY_NONE)."""
        buf = b""
        try:
            while True:
                data = self.sock.recv(4096)
                if not data:
                    print("Connexion InSim fermée par LFS.")
                    return
                buf += data
                while buf:
                    size = buf[0] * 4
                    if size == 0 or len(buf) < size:
                        break
                    pkt, buf = buf[:size], buf[size:]
                    if pkt[1] == ISP_TINY and pkt[3] == 0:  # TINY_NONE
                        with self.lock:
                            self.sock.sendall(struct.pack("<BBBB", 1, ISP_TINY, 0, 0))
        except OSError:
            pass

    def send_message(self, text):
        text = text.replace("^", "").replace("|", " ").strip()
        if not text:
            return
        # LFS utilise la page de code Windows (cp1252 pour le français)
        raw = text.encode("cp1252", errors="replace")[:MAX_MSG]
        pkt = struct.pack("<BBBB96s", 25, ISP_MSX, 0, 0, raw)
        with self.lock:
            self.sock.sendall(pkt)


def main():
    print("Chargement du modèle de reconnaissance vocale…")
    model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)

    insim = None
    if USE_INSIM:
        print(f"Connexion à LFS ({HOST}:{PORT})… (as-tu tapé /insim={PORT} dans LFS ?)")
        insim = InSim(HOST, PORT)
    print(f"Prêt. Maintiens [{PTT_KEY}] pour parler. Ctrl+C pour quitter.")

    chunks = []
    recording = threading.Event()
    state = {"lang": None}  # langue forcée par le bouton utilisé (None = réglage LANGUAGE)

    def callback(indata, frames, t, status):
        if recording.is_set():
            chunks.append(indata.copy())

    stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=callback)
    stream.start()

    def transcribe_and_send(audio, forced_lang=None):
        lang = forced_lang or LANGUAGE
        if lang is None:
            # Whisper évalue la probabilité de chaque langue ; on garde la
            # meilleure parmi celles autorisées (évite les détections absurdes).
            _, _, probs = model.detect_language(audio)
            allowed = [(l, p) for l, p in probs if not ALLOWED_LANGUAGES or l in ALLOWED_LANGUAGES]
            lang = max(allowed, key=lambda x: x[1])[0] if allowed else None
            print(f"[langue détectée : {lang}]")
        segments, _ = model.transcribe(audio, language=lang, beam_size=1, vad_filter=True)
        text = " ".join(s.text.strip() for s in segments).strip()
        if not text:
            print("(rien compris)")
            keyboard.send("esc")  # ferme l'invite vide
            return
        print(f"> {text}")
        if insim:
            keyboard.send("esc")
            time.sleep(0.05)
            insim.send_message(text)
        else:
            keyboard.write(text, delay=0.01)
            time.sleep(0.05)
            keyboard.send("enter")

    def open_chat():
        # Relâche virtuellement Alt/Ctrl/Maj de la combinaison, sinon LFS
        # recevrait Alt+T au lieu de T.
        for mod in PTT_KEY.split("+")[:-1]:
            keyboard.release(mod.strip())
        keyboard.send(CHAT_KEY)
        if CHAT_CLEAN_DELAY is not None:
            # La touche simulée ouvre l'invite mais le caractère "t" s'y retrouve
            # aussi : on l'efface (sans effet si l'invite est déjà vide).
            time.sleep(CHAT_CLEAN_DELAY)
            keyboard.send("backspace")

    def on_press(_, lang=None):
        if not recording.is_set():
            chunks.clear()
            state["lang"] = lang
            recording.set()
            threading.Thread(target=open_chat, daemon=True).start()

    def on_release(_):
        if not recording.is_set():
            return
        recording.clear()
        if not chunks:
            keyboard.send("esc")
            return
        audio = np.concatenate(chunks).flatten()
        if len(audio) / SAMPLE_RATE < MIN_SECONDS:
            keyboard.send("esc")  # appui trop court : on ferme l'invite
            return
        threading.Thread(target=transcribe_and_send, args=(audio, state["lang"]), daemon=True).start()

    # Fonctionne pour une touche seule ("f9") comme pour une combinaison ("alt+f9") :
    # l'enregistrement démarre quand la combinaison est pressée, et s'arrête
    # quand on relâche la dernière touche de la combinaison.
    keyboard.add_hotkey(PTT_KEY, lambda: on_press(None), suppress=False)
    keyboard.on_release_key(PTT_KEY.split("+")[-1].strip(), on_release)

    def joystick_loop():
        import os
        # Permet de lire le volant même quand LFS a le focus
        os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
        import pygame
        pygame.display.init()
        pygame.display.set_mode((1, 1), pygame.HIDDEN)
        pygame.joystick.init()
        if pygame.joystick.get_count() <= JOY_INDEX:
            print("Aucun volant/manette détecté par pygame.")
            return
        joy = pygame.joystick.Joystick(JOY_INDEX)
        # bouton -> langue forcée (None = réglage LANGUAGE)
        buttons = {}
        if JOY_BUTTON is not None:
            buttons[JOY_BUTTON] = None
        buttons.update(JOY_LANG_BUTTONS)
        print(f"Volant détecté : {joy.get_name()} (boutons {buttons})")
        was_down = {b: False for b in buttons}
        active = None
        while True:
            pygame.event.pump()
            for b, lang in buttons.items():
                down = bool(joy.get_button(b))
                if down and not was_down[b] and active is None:
                    active = b
                    on_press(None, lang)
                elif not down and was_down[b] and active == b:
                    active = None
                    on_release(None)
                was_down[b] = down
            time.sleep(0.01)

    if JOY_BUTTON is not None or JOY_LANG_BUTTONS:
        threading.Thread(target=joystick_loop, daemon=True).start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        stream.stop()


if __name__ == "__main__":
    main()
