"""Test du moteur avec un faux clavier, un faux modèle et un faux serveur InSim."""
import copy
import os
import sys
import tempfile
import threading
import time
import types
import unittest

os.environ.setdefault("APPDATA", tempfile.mkdtemp())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402

CALLS = []
fake_kb = types.ModuleType("keyboard")
fake_kb.send = lambda k: CALLS.append(("send", k))
fake_kb.write = lambda t, delay=0: CALLS.append(("write", t))
fake_kb.release = lambda k: CALLS.append(("release", k))
fake_kb.add_hotkey = lambda *a, **k: "hk"
fake_kb.on_release_key = lambda *a, **k: "rk"
fake_kb.remove_hotkey = lambda h: None
fake_kb.unhook = lambda h: None
sys.modules["keyboard"] = fake_kb

from lfsvoice import config as C  # noqa: E402
from lfsvoice.engine import Engine, RATE  # noqa: E402
from lfsvoice.insim import InSimLink  # noqa: E402
from lfsvoice.joystick import JoystickMonitor  # noqa: E402
from test_core import FakeLFS  # noqa: E402


class Seg:
    def __init__(self, text):
        self.text = text


class FakeModel:
    def __init__(self, text="bonjour à tous", detected="fr"):
        self.text, self.detected = text, detected
        self.forced = []

    def detect_language(self, audio):
        other = "en" if self.detected == "fr" else "fr"
        return self.detected, 0.9, [(self.detected, 0.9), (other, 0.1), ("ja", 0.0)]

    def transcribe(self, audio, language=None, **kw):
        self.forced.append(language)
        return [Seg(self.text)], types.SimpleNamespace(language=language or self.detected)


def make_engine(mode="keys", bindings=None, allowed=("fr", "en"), model=None):
    cfg = copy.deepcopy(C.DEFAULTS)
    cfg.update(send_mode=mode, clean_delay=0.01, min_seconds=0.4,
               allowed_languages=list(allowed),
               bindings=bindings or [{"kind": "joystick", "device": "Wheel", "button": 2, "lang": None}])
    e = Engine(cfg, JoystickMonitor(), lambda m: None, lambda k, **kw: None)
    e.running = True
    e.model = model or FakeModel()
    return e


def speak(e, seconds=1.0, device="Wheel", button=2):
    e._on_joy(device, button, True)
    time.sleep(0.1)                                  # laisse l'invite s'ouvrir
    e._audio_cb(np.zeros((int(RATE * seconds), 1), dtype="float32"), 0, None, None)
    e._on_joy(device, button, False)


def wait_for(pred, timeout=3):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.02)
    return False


class TestEngineKeys(unittest.TestCase):
    def setUp(self):
        CALLS.clear()

    def test_full_cycle_keyboard_mode(self):
        e = make_engine("keys")
        speak(e)
        self.assertTrue(wait_for(lambda: ("send", "enter") in CALLS))
        self.assertEqual(CALLS[0], ("send", "t"))                    # ouvre l'invite
        self.assertEqual(CALLS[1], ("send", "backspace"))            # efface le "t" parasite
        self.assertIn(("write", "bonjour à tous"), CALLS)
        self.assertEqual(CALLS[-1], ("send", "enter"))
        self.assertIsNone(e.active)

    def test_too_short_press_closes_prompt(self):
        e = make_engine("keys")
        speak(e, seconds=0.1)
        self.assertTrue(wait_for(lambda: ("send", "esc") in CALLS))
        self.assertFalse([c for c in CALLS if c[0] == "write"])

    def test_nothing_recorded_closes_prompt(self):
        e = make_engine("keys")
        e._on_joy("Wheel", 2, True)
        e._on_joy("Wheel", 2, False)
        self.assertIn(("send", "esc"), CALLS)

    def test_empty_transcription_closes_prompt(self):
        e = make_engine("keys", model=FakeModel(text="  "))
        speak(e)
        self.assertTrue(wait_for(lambda: ("send", "esc") in CALLS))
        self.assertFalse([c for c in CALLS if c[0] == "write"])

    def test_other_device_or_button_ignored(self):
        e = make_engine("keys")
        e._on_joy("Other", 2, True)
        e._on_joy("Wheel", 5, True)
        self.assertIsNone(e.active)
        self.assertEqual(CALLS, [])

    def test_suppressed_during_capture(self):
        e = make_engine("keys")
        e.joy.suppress = True
        e._on_joy("Wheel", 2, True)
        self.assertIsNone(e.active)
        e.joy.suppress = False

    def test_second_press_while_active_ignored(self):
        e = make_engine("keys")
        e._on_joy("Wheel", 2, True)
        e._on_joy("Wheel", 2, True)
        time.sleep(0.1)
        self.assertEqual([c for c in CALLS if c == ("send", "t")], [("send", "t")])

    def test_release_without_press_is_harmless(self):
        e = make_engine("keys")
        e._on_joy("Wheel", 2, False)
        self.assertEqual(CALLS, [])

    def test_keyboard_binding_releases_modifier_before_chat_key(self):
        b = [{"kind": "keyboard", "key": "alt+f9", "lang": None}]
        e = make_engine("keys", bindings=b)
        e._press(0)
        time.sleep(0.1)
        self.assertEqual(CALLS[0], ("release", "alt"))
        self.assertEqual(CALLS[1], ("send", "t"))

    def test_forced_language_skips_detection(self):
        m = FakeModel(detected="fr")
        b = [{"kind": "joystick", "device": "Wheel", "button": 2, "lang": "en"}]
        e = make_engine("keys", bindings=b, model=m)
        speak(e)
        self.assertTrue(wait_for(lambda: ("send", "enter") in CALLS))
        self.assertEqual(m.forced, ["en"])

    def test_auto_language_picks_best_allowed(self):
        m = FakeModel(detected="ja")          # "ja" n'est pas autorisé -> on garde le meilleur parmi fr/en
        e = make_engine("keys", model=m)
        speak(e)
        self.assertTrue(wait_for(lambda: ("send", "enter") in CALLS))
        self.assertEqual(m.forced, ["fr"])    # parmi fr/en, "fr" a la meilleure probabilité (0.1 contre 0.0)

    def test_single_allowed_language_used_directly(self):
        m = FakeModel()
        e = make_engine("keys", allowed=("de",), model=m)
        speak(e)
        self.assertTrue(wait_for(lambda: ("send", "enter") in CALLS))
        self.assertEqual(m.forced, ["de"])

    def test_resample_when_device_rate_differs(self):
        e = make_engine("keys")
        e.rate = 48000
        e._on_joy("Wheel", 2, True)
        e._audio_cb(np.zeros((48000, 1), dtype="float32"), 0, None, None)
        e._on_joy("Wheel", 2, False)
        self.assertTrue(wait_for(lambda: ("send", "enter") in CALLS))


class TestDiagnostics(unittest.TestCase):
    def setUp(self):
        CALLS.clear()

    def test_vad_failure_falls_back_and_still_sends(self):
        class NoVad(FakeModel):
            def transcribe(self, audio, language=None, **kw):
                if kw.get("vad_filter"):
                    raise RuntimeError("silero asset missing")
                return super().transcribe(audio, language=language, **kw)

        e = make_engine("keys", model=NoVad())
        logs = []
        e.log = logs.append
        speak(e)
        self.assertTrue(wait_for(lambda: ("send", "enter") in CALLS))
        self.assertIn(("write", "bonjour à tous"), CALLS)
        self.assertTrue(any("without it" in m for m in logs))

    def test_journal_traces_each_step(self):
        e = make_engine("keys")
        logs = []
        e.log = logs.append
        speak(e)
        self.assertTrue(wait_for(lambda: ("send", "enter") in CALLS))
        text = "\n".join(logs)
        for expected in ("Button pressed", "Recorded", "Transcribing", "[fr] bonjour", "Sending via keyboard"):
            self.assertIn(expected, text)

    def test_silent_microphone_is_reported(self):
        e = make_engine("keys")
        logs = []
        e.log = logs.append
        speak(e)                                   # speak() envoie du silence (zéros)
        self.assertTrue(wait_for(lambda: ("send", "enter") in CALLS))
        self.assertTrue(any("seems silent" in m for m in logs))

    def test_no_audio_is_reported(self):
        e = make_engine("keys")
        logs = []
        e.log = logs.append
        e._on_joy("Wheel", 2, True)
        e._on_joy("Wheel", 2, False)
        self.assertTrue(any("No audio received" in m for m in logs))


class TestEngineInSim(unittest.TestCase):
    def setUp(self):
        CALLS.clear()

    def _connected_engine(self, fake, mode):
        e = make_engine(mode)
        e.insim = InSimLink(fake.port, lambda m: None)
        e.insim.start()
        self.assertTrue(wait_for(lambda: e.insim.connected, 5))
        return e

    def test_insim_delivery_with_codepage(self):
        fake = FakeLFS()
        e = self._connected_engine(fake, "insim")
        try:
            speak(e)
            self.assertTrue(fake.done.wait(5))
        finally:
            e.insim.stop()
        self.assertIn(("send", "esc"), CALLS)                 # invite fermée avant l'envoi InSim
        self.assertNotIn(("write", "bonjour à tous"), CALLS)  # rien tapé au clavier
        self.assertEqual(fake.msx[0][4:].split(b"\0")[0], b"^L" + "bonjour à tous".encode("cp1252"))

    def test_auto_mode_prefers_insim_when_connected(self):
        fake = FakeLFS()
        e = self._connected_engine(fake, "auto")
        try:
            speak(e)
            self.assertTrue(fake.done.wait(5))
        finally:
            e.insim.stop()
        self.assertFalse([c for c in CALLS if c[0] == "write"])

    def test_auto_mode_falls_back_to_keyboard(self):
        e = make_engine("auto")
        e.insim = InSimLink(1, lambda m: None)   # jamais connecté
        speak(e)
        self.assertTrue(wait_for(lambda: ("send", "enter") in CALLS))
        self.assertIn(("write", "bonjour à tous"), CALLS)

    def test_insim_only_mode_without_connection_sends_nothing(self):
        e = make_engine("insim")
        e.insim = InSimLink(1, lambda m: None)
        speak(e)
        self.assertTrue(wait_for(lambda: ("send", "esc") in CALLS))
        self.assertFalse([c for c in CALLS if c[0] == "write"])


if __name__ == "__main__":
    unittest.main()
