"""Moteur : enregistre la voix tant qu'un bouton est maintenu, transcrit, envoie dans LFS."""
import threading
import time
import traceback

import numpy as np

from . import lfsenc, models
from .insim import InSimLink

RATE = 16000


class Engine:
    def __init__(self, cfg, joy, log, status, on_insim=None):
        self.cfg, self.joy = cfg, joy
        self.log, self.status, self.on_insim = log, status, on_insim
        self.model = None
        self.insim = None
        self.stream = None
        self.rate = RATE
        self.bindings = cfg["bindings"]
        self.chunks = []
        self.recording = threading.Event()
        self.active = None
        self.lock = threading.Lock()
        self.tlock = threading.Lock()
        self.hooks = []
        self.running = False
        self._warned_unicode = False

    # ------------------------------------------------------------ cycle de vie
    def start(self):
        self.running = True
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self.running = False
        self.recording.clear()
        self.joy.remove_listener(self._on_joy)
        try:
            import keyboard
            for kind, h in self.hooks:
                try:
                    keyboard.remove_hotkey(h) if kind == "hotkey" else keyboard.unhook(h)
                except Exception:
                    pass
        except Exception:
            pass
        self.hooks = []
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
        if self.insim:
            self.insim.stop()
            self.insim = None
        self.model = None
        self.status("stopped")

    def _run(self):
        try:
            self.status("loading")
            self.model = models.load(
                self.cfg["model_size"], self.cfg["device"],
                lambda pct: self.status("downloading", pct=pct), self.log)
            if not self.running:
                return
            self._open_stream()
            self._setup_bindings()
            if self.cfg["send_mode"] != "keys":
                self.insim = InSimLink(self.cfg["insim_port"], self.log, self.on_insim)
                self.insim.start()
            self.status("ready")
            self.log("Ready")
        except Exception as e:
            self.log(traceback.format_exc())
            self.stop()
            self.status("error", msg=str(e))

    # ------------------------------------------------------------------ audio
    def _find_mic(self):
        name = self.cfg.get("mic_device")
        if not name:
            return None
        import sounddevice as sd
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0 and d["name"] == name:
                return i
        self.log(f"Microphone '{name}' not found; using system default")
        return None

    def _open_stream(self):
        import sounddevice as sd
        dev = self._find_mic()
        info = sd.query_devices(dev, "input")
        last = None
        for rate in (RATE, int(info["default_samplerate"])):
            try:
                self.stream = sd.InputStream(samplerate=rate, channels=1, dtype="float32",
                                             device=dev, callback=self._audio_cb)
                self.stream.start()
                self.rate = rate
                return
            except Exception as e:
                last = e
        raise last

    def _audio_cb(self, indata, frames, t, status):
        if self.recording.is_set():
            self.chunks.append(indata.copy())

    # ------------------------------------------------------------- commandes
    def _setup_bindings(self):
        import keyboard
        self.joy.add_listener(self._on_joy)
        for i, b in enumerate(self.bindings):
            if b.get("kind") == "keyboard" and b.get("key"):
                key = b["key"]
                h1 = keyboard.add_hotkey(key, lambda i=i: self._press(i), suppress=False)
                h2 = keyboard.on_release_key(key.split("+")[-1].strip(),
                                             lambda e, i=i: self._release(i))
                self.hooks += [("hotkey", h1), ("hook", h2)]

    def _on_joy(self, name, button, down):
        if self.joy.suppress or not self.running:
            return
        for i, b in enumerate(self.bindings):
            if b.get("kind") == "joystick" and b.get("device") == name and b.get("button") == button:
                (self._press if down else self._release)(i)

    def _press(self, i):
        if self.joy.suppress or not self.running:
            return
        with self.lock:
            if self.active is not None:
                return
            self.active = i
            self.chunks.clear()
            self.recording.set()
        b = self.bindings[i]
        self.log(f"Button pressed ({b.get('device') or b.get('key')} {b.get('button', '')})".rstrip(" )") + ")")
        mods = b["key"].split("+")[:-1] if b.get("kind") == "keyboard" else []
        threading.Thread(target=self._open_chat, args=(mods,), daemon=True).start()

    def _open_chat(self, mods):
        import keyboard
        for m in mods:  # sinon LFS recevrait Alt+T au lieu de T
            keyboard.release(m.strip())
        keyboard.send(self.cfg["chat_key"])
        delay = self.cfg.get("clean_delay")
        if delay is not None:
            # La touche simulée ouvre l'invite, mais le "t" s'y retrouve : on l'efface.
            time.sleep(delay)
            keyboard.send("backspace")

    def _release(self, i):
        import keyboard
        with self.lock:
            if self.active != i:
                return
            self.active = None
            self.recording.clear()
        if not self.chunks:
            self.log("No audio received from the microphone (check the Speech tab > Microphone)")
            keyboard.send("esc")
            return
        audio = np.concatenate(self.chunks).flatten()
        peak = float(np.abs(audio).max()) if len(audio) else 0.0
        self.log(f"Recorded {len(audio) / self.rate:.1f} s, peak level {peak:.3f}")
        if peak < 0.003:
            self.log("Warning: the microphone seems silent. Check the selected microphone and the "
                     "Windows privacy settings (Settings > Privacy > Microphone).")
        if self.rate != RATE:
            n = int(len(audio) * RATE / self.rate)
            audio = np.interp(np.linspace(0, len(audio), n, endpoint=False),
                              np.arange(len(audio)), audio).astype("float32")
        if len(audio) / RATE < self.cfg["min_seconds"]:
            self.log("Too short, ignored")
            keyboard.send("esc")  # appui trop court : on ferme l'invite
            return
        threading.Thread(target=self._transcribe, args=(audio, self.bindings[i].get("lang")),
                         daemon=True).start()

    # ---------------------------------------------------------- transcription
    def _pick_language(self, audio, forced):
        if forced:
            return forced
        allowed = self.cfg["allowed_languages"]
        if len(allowed) == 1:
            return allowed[0]
        if allowed:
            try:
                _, _, probs = self.model.detect_language(audio)
                cand = [(p, l) for l, p in probs if l in allowed]
                if cand:
                    return max(cand)[1]
            except Exception:
                pass
        return None  # Whisper détectera lui-même

    def _whisper(self, audio, lang):
        try:
            return self.model.transcribe(audio, language=lang, beam_size=1, vad_filter=True)
        except Exception as e:
            self.log(f"Voice-activity detection unavailable ({e}); continuing without it")
            return self.model.transcribe(audio, language=lang, beam_size=1, vad_filter=False)

    def _transcribe(self, audio, forced):
        import keyboard
        with self.tlock:
            try:
                if not self.model:
                    return
                lang = self._pick_language(audio, forced)
                self.log("Transcribing…")
                segments, info = self._whisper(audio, lang)
                text = " ".join(s.text.strip() for s in segments).strip()
                used = lang or info.language
                if not text:
                    self.log("(nothing understood)")
                    keyboard.send("esc")
                    return
                self.log(f"[{used}] {text}")
                self._deliver(text, used)
            except Exception:
                self.log(traceback.format_exc())
                try:
                    keyboard.send("esc")
                except Exception:
                    pass

    def _deliver(self, text, lang):
        import keyboard
        mode = self.cfg["send_mode"]
        via_insim = mode == "insim" or (mode == "auto" and self.insim and self.insim.connected)
        if via_insim:
            if not (self.insim and self.insim.connected):
                self.log("InSim not connected: message not sent (enable /insim in LFS)")
                keyboard.send("esc")
                return
            self.log("Sending via InSim")
            keyboard.send("esc")
            time.sleep(0.1)
            self.insim.send_text(text, lang)
        else:
            if not lfsenc.uses_latin1(lang) and not self._warned_unicode:
                self._warned_unicode = True
                self.log("Note: this language needs InSim to display correctly in LFS")
            self.log("Sending via keyboard")
            keyboard.write(text, delay=0.01)
            time.sleep(0.05)
            keyboard.send("enter")
