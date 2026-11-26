import os
import re
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest

os.environ.setdefault("APPDATA", tempfile.mkdtemp())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lfsvoice import i18n, lfsenc  # noqa: E402
from lfsvoice.insim import InSimLink  # noqa: E402

EU = "bg cs da de el en es et fi fr ga hr hu it lt lv mt nl pl pt ro sk sl sv".split()
PLACEHOLDER = re.compile(r"\{(\w+)\}")


class TestI18n(unittest.TestCase):
    def test_all_24_eu_languages(self):
        self.assertEqual(sorted(i18n.STRINGS), sorted(EU))
        self.assertEqual(sorted(i18n.NAMES), sorted(EU))

    def test_every_key_translated(self):
        for lang in EU:
            missing = set(i18n.EN) - set(i18n.STRINGS[lang])
            extra = set(i18n.STRINGS[lang]) - set(i18n.EN)
            self.assertFalse(missing, f"{lang} missing {missing}")
            self.assertFalse(extra, f"{lang} unknown keys {extra}")

    def test_placeholders_preserved(self):
        for lang in EU:
            for key, en in i18n.EN.items():
                self.assertEqual(set(PLACEHOLDER.findall(en)),
                                 set(PLACEHOLDER.findall(i18n.STRINGS[lang][key])),
                                 f"{lang}.{key}")

    def test_no_empty_values(self):
        for lang in EU:
            for key, v in i18n.STRINGS[lang].items():
                self.assertTrue(v.strip(), f"{lang}.{key} empty")

    def test_format_all(self):
        values = dict(pct=5, msg="x", device="d", n=1, hotkey="k", mb=485)
        for lang in EU:
            for name in i18n.EN:
                out = i18n.tr(lang, name, **values)
                self.assertNotRegex(out, r"\{\w+\}", f"{lang}.{name} not fully formatted: {out}")

    def test_default_language(self):
        self.assertEqual(i18n.default_language("fr-FR"), "fr")
        self.assertEqual(i18n.default_language("de_AT"), "de")
        self.assertEqual(i18n.default_language("ja-JP"), "en")
        self.assertEqual(i18n.default_language(""), "en")

    def test_speech_langs_exclude_irish(self):
        self.assertNotIn("ga", i18n.SPEECH_LANGS)
        self.assertEqual(len(i18n.SPEECH_LANGS), 23)


class TestEncoding(unittest.TestCase):
    def test_every_eu_language_has_codepage(self):
        for lang in EU:
            self.assertIn(lang, lfsenc.CP)

    def test_french_latin1(self):
        (m,) = lfsenc.chunks("élève à Noël", "fr")
        self.assertEqual(m, b"^L" + "élève à Noël".encode("cp1252"))

    def test_polish_central_european(self):
        (m,) = lfsenc.chunks("zażółć", "pl")
        self.assertTrue(m.startswith(b"^E"))
        self.assertEqual(m[2:], "zażółć".encode("cp1250"))

    def test_greek_and_cyrillic_and_baltic(self):
        self.assertEqual(lfsenc.chunks("γειά", "el")[0], b"^G" + "γειά".encode("cp1253"))
        self.assertEqual(lfsenc.chunks("здрасти", "bg")[0], b"^C" + "здрасти".encode("cp1251"))
        self.assertEqual(lfsenc.chunks("ačiū", "lt")[0], b"^B" + "ačiū".encode("cp1257"))

    def test_maltese_and_romanian_fallbacks(self):
        self.assertEqual(lfsenc.chunks("ħobż", "mt")[0], b"^E" + b"hob" + "ż".encode("cp1250"))
        self.assertEqual(lfsenc.chunks("ș", "ro")[0], b"^E" + "ş".encode("cp1250"))

    def test_unknown_char_becomes_question_mark(self):
        self.assertEqual(lfsenc.chunks("a日b", "en")[0], b"^La?b")

    def test_sanitize(self):
        self.assertEqual(lfsenc.chunks("/kick ^1bob | x", "en")[0], b"^Lkick 1bob x")
        self.assertEqual(lfsenc.chunks("   ", "en"), [])

    def test_splitting_respects_limit(self):
        text = " ".join(["mot"] * 80)
        parts = lfsenc.chunks(text, "fr")
        self.assertGreater(len(parts), 1)
        for p in parts:
            self.assertLessEqual(len(p), 95)
            self.assertTrue(p.startswith(b"^L"))
        joined = b" ".join(p[2:] for p in parts).decode("cp1252")
        self.assertEqual(joined, text)

    def test_very_long_word(self):
        parts = lfsenc.chunks("x" * 300, "en")
        self.assertTrue(all(len(p) <= 95 for p in parts))
        self.assertEqual(sum(len(p) - 2 for p in parts), 300)

    def test_multibyte_never_exceeds_limit(self):
        for lang, word in (("pl", "żółć"), ("el", "γειά"), ("bg", "здрасти")):
            for p in lfsenc.chunks((word + " ") * 60, lang):
                self.assertLessEqual(len(p), 95)


class FakeLFS:
    """Mini serveur InSim : lit IS_ISI, envoie un keepalive, enregistre les IS_MSX."""

    def __init__(self):
        self.srv = socket.socket()
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(1)
        self.port = self.srv.getsockname()[1]
        self.isi = None
        self.keepalive_reply = None
        self.msx = []
        self.conn = None
        self.done = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()

    def _recv(self, n):
        buf = b""
        while len(buf) < n:
            d = self.conn.recv(n - len(buf))
            if not d:
                return buf
            buf += d
        return buf

    def _run(self):
        self.conn, _ = self.srv.accept()
        self.conn.settimeout(5)
        self.isi = self._recv(44)
        self.conn.sendall(struct.pack("<BBBB", 1, 3, 0, 0))  # TINY_NONE (keepalive)
        self.keepalive_reply = self._recv(4)
        try:
            while True:
                pkt = self._recv(100)
                if len(pkt) < 100:
                    break
                self.msx.append(pkt)
                self.done.set()
        except OSError:
            pass


class TestInSim(unittest.TestCase):
    def test_handshake_keepalive_and_message(self):
        fake = FakeLFS()
        logs = []
        link = InSimLink(fake.port, logs.append)
        link.start()
        try:
            deadline = time.time() + 5
            while not link.connected and time.time() < deadline:
                time.sleep(0.05)
            self.assertTrue(link.connected)
            link.send_text("Hello à tous", "fr")
            self.assertTrue(fake.done.wait(5))
        finally:
            link.stop()
        isi = fake.isi
        self.assertEqual(len(isi), 44)
        self.assertEqual((isi[0], isi[1], isi[2]), (11, 1, 1))          # Size/4, ISP_ISI, ReqI
        self.assertGreaterEqual(isi[8], 9)                              # InSimVer : taille en unités de 4 octets
        self.assertTrue(isi[28:44].rstrip(b"\0") == b"LFS Voice")       # IName
        self.assertEqual(fake.keepalive_reply, struct.pack("<BBBB", 1, 3, 0, 0))
        pkt = fake.msx[0]
        self.assertEqual((pkt[0], pkt[1]), (25, 39))                    # Size/4, ISP_MSX (39)
        self.assertEqual(pkt[4:].split(b"\0")[0], b"^L" + "Hello à tous".encode("cp1252"))

    def test_not_connected_raises(self):
        link = InSimLink(1, lambda m: None)
        with self.assertRaises(ConnectionError):
            link.send_text("x", "en")


if __name__ == "__main__":
    unittest.main()
