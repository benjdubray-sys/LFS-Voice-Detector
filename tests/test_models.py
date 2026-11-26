"""Repli sur le processeur quand le mode carte graphique échoue (ex. cublas64_12.dll manquante)."""
import os
import sys
import tempfile
import types
import unittest

os.environ.setdefault("APPDATA", tempfile.mkdtemp())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CREATED = []


class FakeWhisperModel:
    def __init__(self, path, device="cpu", compute_type="int8"):
        self.device = device
        CREATED.append((device, compute_type))

    def transcribe(self, audio, **kw):
        if self.device == "cuda":
            def gen():  # comme faster-whisper : l'erreur n'apparaît qu'à l'itération
                raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")
                yield
            return gen(), None
        return iter([]), None


fw = types.ModuleType("faster_whisper")
fw.WhisperModel = FakeWhisperModel
fwu = types.ModuleType("faster_whisper.utils")
fwu.download_model = lambda size, **kw: "model-dir"
fw.utils = fwu
sys.modules["faster_whisper"] = fw
sys.modules["faster_whisper.utils"] = fwu

from lfsvoice import models  # noqa: E402


class TestModelFallback(unittest.TestCase):
    def setUp(self):
        CREATED.clear()

    def test_gpu_failure_at_first_compute_falls_back_to_cpu(self):
        logs = []
        m = models.load("small", "cuda", lambda p: None, logs.append)
        self.assertEqual(m.device, "cpu")
        self.assertEqual(CREATED, [("cuda", "float16"), ("cpu", "int8")])
        self.assertTrue(any("cublas64_12.dll" in x and "CPU" in x for x in logs))

    def test_cpu_mode_loads_directly(self):
        m = models.load("small", "cpu", lambda p: None, lambda x: None)
        self.assertEqual(m.device, "cpu")
        self.assertEqual(CREATED, [("cpu", "int8")])


if __name__ == "__main__":
    unittest.main()
