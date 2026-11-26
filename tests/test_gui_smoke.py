"""Test de fumée de gui.py avec un faux tkinter (n'évalue pas l'apparence : il exécute
tout le code de l'interface pour détecter fautes de frappe, noms inconnus, formats)."""
import copy
import os
import sys
import tempfile
import types
import unittest

os.environ.setdefault("APPDATA", tempfile.mkdtemp())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Var:
    def __init__(self, master=None, value=None, **kw):
        self.v = value

    def get(self):
        return self.v

    def set(self, v):
        self.v = v

    def trace_add(self, *a, **k):
        pass


class Widget:
    instances = []

    def __init__(self, *a, **k):
        Widget.instances.append(self)

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **k: 0

    def winfo_children(self):
        return []

    def winfo_exists(self):
        return True


class FakeTk(Widget):
    def __init__(self, *a, **k):
        super().__init__()
        self.scheduled = []

    def after(self, ms, fn=None, *a):
        self.scheduled.append((ms, fn))

    def __getattr__(self, name):
        # Comme un vrai Tk : seuls les attributs/méthodes réels existent (sinon hasattr mentirait)
        if name in {"title", "minsize", "protocol", "destroy", "mainloop", "geometry"}:
            return lambda *a, **k: 0
        raise AttributeError(name)


tk = types.ModuleType("tkinter")
tk.Tk, tk.Text, tk.Frame = FakeTk, Widget, Widget
tk.StringVar = lambda master=None, value=None, **k: Var(value=value)
tk.BooleanVar = lambda master=None, value=None, **k: Var(value=value)
tk.TclError = type("TclError", (Exception,), {})
ttk = types.ModuleType("tkinter.ttk")
for n in ("Frame", "Label", "Button", "Notebook", "Combobox", "Checkbutton",
          "Radiobutton", "Entry", "Scrollbar"):
    setattr(ttk, n, Widget)
tk.ttk = ttk
fd = types.ModuleType("tkinter.filedialog")
fd.askopenfilename = lambda **k: ""
mb = types.ModuleType("tkinter.messagebox")
mb.CALLS = []
mb.showinfo = lambda *a, **k: mb.CALLS.append(("info", a))
mb.showerror = lambda *a, **k: mb.CALLS.append(("error", a))
tk.filedialog, tk.messagebox = fd, mb
sys.modules.update({"tkinter": tk, "tkinter.ttk": ttk, "tkinter.filedialog": fd,
                    "tkinter.messagebox": mb})

kb = types.ModuleType("keyboard")
for n in ("send", "write", "release", "add_hotkey", "on_release_key", "remove_hotkey",
          "unhook", "read_hotkey"):
    setattr(kb, n, lambda *a, **k: None)
sys.modules.setdefault("keyboard", kb)

from lfsvoice import config as C, i18n  # noqa: E402
from lfsvoice import gui  # noqa: E402

BINDS = [{"kind": "joystick", "device": "Thrustmaster TX Racing Wheel", "button": 2, "lang": None},
         {"kind": "keyboard", "key": "alt+f9", "lang": "en"}]


def make_app(lang="en"):
    cfg = copy.deepcopy(C.DEFAULTS)
    cfg.update(ui_language=lang, bindings=copy.deepcopy(BINDS), allowed_languages=["fr", "en"])
    C.CONFIG_PATH = os.path.join(tempfile.mkdtemp(), "config.json")
    return gui.App(cfg)


class TestGuiSmoke(unittest.TestCase):
    def test_builds_in_all_24_languages(self):
        for lang in i18n.NAMES:
            app = make_app(lang)
            app._build_ui()
            for state in (("stopped", {}), ("loading", {}), ("downloading", {"pct": 42}),
                          ("ready", {}), ("error", {"msg": "boom"})):
                app.run_state = state
                app._refresh_status()
            app.engine = object()
            app.insim_on = True
            app._refresh_status()
            app.insim_on = False
            app._refresh_status()
            app.engine = None
            app._render_bindings()

    def test_bindings_edit(self):
        app = make_app()
        app._set_bind_lang(0, 3)
        self.assertEqual(app.cfg["bindings"][0]["lang"], i18n.SPEECH_LANGS[2])
        app._set_bind_lang(0, 0)
        self.assertIsNone(app.cfg["bindings"][0]["lang"])
        app._remove_bind(1)
        self.assertEqual(len(app.cfg["bindings"]), 1)

    def test_capture_wheel_and_key(self):
        app = make_app()
        n = len(app.cfg["bindings"])
        app._add_wheel()
        token = app.cap_token
        self.assertTrue(app.joy.suppress)
        app._handle("cap_wheel", (token, "Pad", 7))
        self.assertFalse(app.joy.suppress)
        self.assertEqual(app.cfg["bindings"][-1],
                         {"kind": "joystick", "device": "Pad", "button": 7, "lang": None})
        app._handle("cap_wheel", (token, "Late", 1))                 # capture périmée : ignorée
        self.assertEqual(len(app.cfg["bindings"]), n + 1)
        app._add_key()
        app._handle("cap_key", (app.cap_token, "ctrl+f8"))
        self.assertEqual(app.cfg["bindings"][-1]["key"], "ctrl+f8")
        app._add_wheel()                                              # doublon : pas ajouté deux fois
        app._handle("cap_wheel", (app.cap_token, "Pad", 7))
        self.assertEqual(len(app.cfg["bindings"]), n + 2)

    def test_capture_timeout_releases_suppression(self):
        app = make_app()
        app._add_wheel()
        app._capture_timeout(app.cap_token)
        self.assertFalse(app.joy.suppress)
        self.assertEqual(app.cap_token, 0)

    def test_language_toggle_keeps_one(self):
        app = make_app()
        app._tab_speech(Widget())
        for v in app.lang_vars.values():
            v.set(False)
        app._on_lang_toggle("fr")
        self.assertTrue(app.lang_vars["fr"].get())

    def test_start_without_binding_warns(self):
        app = make_app()
        app.cfg["bindings"] = []
        gui.messagebox.CALLS.clear()
        app._toggle()
        self.assertIsNone(app.engine)
        self.assertEqual(gui.messagebox.CALLS[0][0], "info")

    def test_launch_lfs_missing_exe_errors(self):
        app = make_app()
        app.cfg["lfs_exe"] = ""
        gui.messagebox.CALLS.clear()
        orig, C.find_lfs = C.find_lfs, lambda: ""
        try:
            app._launch_lfs()
        finally:
            C.find_lfs = orig
        self.assertEqual(gui.messagebox.CALLS[0][0], "error")

    def test_status_messages_after_stop_are_ignored(self):
        app = make_app()
        app.engine = None
        app.run_state = ("stopped", {})
        app._handle("status", ("ready", {}))
        self.assertEqual(app.run_state[0], "stopped")
        app._handle("status", ("error", {"msg": "x"}))
        self.assertEqual(app.run_state[0], "error")

    def test_error_after_stop_event_ends_in_error_state(self):
        app = make_app()
        app.engine = object()
        app._handle("status", ("stopped", {}))
        self.assertIsNotNone(app.engine)
        app._handle("status", ("error", {"msg": "x"}))
        self.assertIsNone(app.engine)
        self.assertEqual(app.run_state[0], "error")

    def test_log_and_pump(self):
        app = make_app()
        app._log("hello")
        app.q.put(("insim", True))
        app._pump()
        self.assertTrue(app.insim_on)
        self.assertTrue(any("hello" in line for line in app.log_lines))

    def test_options_handlers(self):
        app = make_app()
        app._tab_options(Widget())
        app.v_clean.set("0,3")
        app._on_clean()
        self.assertEqual(app.cfg["clean_delay"], 0.3)
        app.v_clean.set("")
        app._on_clean()
        self.assertIsNone(app.cfg["clean_delay"])
        app.v_clean.set("abc")
        app.cfg["clean_delay"] = 0.2
        app._on_clean()
        self.assertEqual(app.cfg["clean_delay"], 0.2)
        app.v_chat.set(" ")
        app._on_chat_key()
        self.assertEqual(app.cfg["chat_key"], "t")


if __name__ == "__main__":
    unittest.main()
