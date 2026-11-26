"""Interface graphique (tkinter) de LFS Voice."""
import copy
import os
import queue
import subprocess
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__
from . import config as C
from . import i18n, models
from .engine import Engine
from .joystick import JoystickMonitor

MODEL_KEYS = ["tiny", "base", "small", "medium"]
CAPTURE_TIMEOUT_MS = 15000
TAB_BUTTONS, TAB_SPEECH, TAB_OPTIONS, TAB_LOG = range(4)


class App(tk.Tk):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.q = queue.Queue()
        self.engine = None
        self.joy = JoystickMonitor()
        self.joy.start()
        self.run_state = ("stopped", {})
        self.insim_on = False
        self.log_lines = []
        self.cap_token = 0           # identifie la capture en cours (0 = aucune)
        self._cap_listener = None
        self._trim_log_file()
        self.minsize(580, 560)
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._pump)

    # ----------------------------------------------------------------- utilitaires
    def t(self, name, /, **kw):
        return i18n.tr(self.cfg["ui_language"], name, **kw)

    def _save(self):
        try:
            C.save(self.cfg)
        except OSError as e:
            self._log(f"Could not save settings: {e}")
        if self.engine:
            self.v_hint.set(self.t("restart_needed"))

    def _log(self, msg):
        self.q.put(("log", msg))

    def _trim_log_file(self):
        try:
            if os.path.getsize(C.LOG_PATH) > 1_000_000:
                os.remove(C.LOG_PATH)
        except OSError:
            pass

    # -------------------------------------------------------------------- interface
    def _build_ui(self):
        keep = 0
        if hasattr(self, "nb"):
            try:
                keep = self.nb.index("current")
            except tk.TclError:
                keep = 0
        for w in self.winfo_children():
            w.destroy()
        self.title("LFS Voice")

        top = ttk.Frame(self, padding=(12, 10, 12, 4))
        top.pack(fill="x")
        self.v_status = tk.StringVar()
        ttk.Label(top, textvariable=self.v_status, font=("Segoe UI", 10, "bold")).pack(side="left")
        self.btn_toggle = ttk.Button(top, command=self._toggle, width=14)
        self.btn_toggle.pack(side="right")
        ttk.Button(top, text=self.t("btn_launch"), command=self._launch_lfs, width=16).pack(
            side="right", padx=6)

        info = ttk.Frame(self, padding=(12, 0, 12, 4))
        info.pack(fill="x")
        self.v_insim = tk.StringVar()
        ttk.Label(info, textvariable=self.v_insim, foreground="gray").pack(side="left")
        self.v_hint = tk.StringVar()
        ttk.Label(info, textvariable=self.v_hint, foreground="#b45309").pack(side="right")

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        tabs = [ttk.Frame(self.nb, padding=12) for _ in range(4)]
        for frame, key in zip(tabs, ("tab_buttons", "tab_speech", "tab_options", "tab_log")):
            self.nb.add(frame, text=self.t(key))
        self._tab_buttons(tabs[TAB_BUTTONS])
        self._tab_speech(tabs[TAB_SPEECH])
        self._tab_options(tabs[TAB_OPTIONS])
        self._tab_log(tabs[TAB_LOG])
        self.nb.select(keep)
        self._refresh_status()

    # -- onglet Boutons --------------------------------------------------------
    def _tab_buttons(self, f):
        ttk.Label(f, text=self.t("help_buttons"), wraplength=520, justify="left").pack(
            anchor="w", pady=(0, 10))
        self.bind_frame = ttk.Frame(f)
        self.bind_frame.pack(fill="x")
        row = ttk.Frame(f)
        row.pack(anchor="w", pady=10)
        ttk.Button(row, text=self.t("btn_add_wheel"), command=self._add_wheel).pack(side="left")
        ttk.Button(row, text=self.t("btn_add_key"), command=self._add_key).pack(side="left", padx=8)
        self.v_capture = tk.StringVar()
        ttk.Label(f, textvariable=self.v_capture, foreground="#0a5").pack(anchor="w")
        self._render_bindings()

    def _lang_choices(self):
        names = [i18n.NAMES[c] for c in i18n.SPEECH_LANGS]
        return [self.t("lang_auto")] + names

    def _render_bindings(self):
        for w in self.bind_frame.winfo_children():
            w.destroy()
        binds = self.cfg["bindings"]
        if not binds:
            ttk.Label(self.bind_frame, text=self.t("no_bindings"), foreground="gray").pack(anchor="w")
            return
        choices = self._lang_choices()
        for i, b in enumerate(binds):
            row = ttk.Frame(self.bind_frame)
            row.pack(fill="x", pady=3)
            if b.get("kind") == "joystick":
                text = self.t("bind_wheel", device=b.get("device", "?"), n=int(b.get("button", 0)) + 1)
            else:
                text = self.t("bind_key", hotkey=b.get("key", "?"))
            ttk.Label(row, text=text, width=42).pack(side="left")
            ttk.Label(row, text=self.t("lang_label")).pack(side="left", padx=(8, 4))
            cb = ttk.Combobox(row, values=choices, state="readonly", width=14)
            lang = b.get("lang")
            cb.current(0 if lang not in i18n.SPEECH_LANGS else i18n.SPEECH_LANGS.index(lang) + 1)
            cb.bind("<<ComboboxSelected>>", lambda e, i=i, cb=cb: self._set_bind_lang(i, cb.current()))
            cb.pack(side="left")
            ttk.Button(row, text=self.t("btn_remove"), width=10,
                       command=lambda i=i: self._remove_bind(i)).pack(side="right")

    def _set_bind_lang(self, i, idx):
        self.cfg["bindings"][i]["lang"] = None if idx == 0 else i18n.SPEECH_LANGS[idx - 1]
        self._save()

    def _remove_bind(self, i):
        del self.cfg["bindings"][i]
        self._save()
        self._render_bindings()

    # -- capture d'un bouton -----------------------------------------------------
    def _begin_capture(self, prompt):
        self._end_capture()
        self.cap_token += 1
        token = self.cap_token
        self.v_capture.set(prompt)
        self.after(CAPTURE_TIMEOUT_MS, lambda: self._capture_timeout(token))
        return token

    def _end_capture(self):
        self.cap_token = 0
        if self._cap_listener:
            self.joy.remove_listener(self._cap_listener)
            self._cap_listener = None
        self.joy.suppress = False
        if hasattr(self, "v_capture"):
            self.v_capture.set("")

    def _capture_timeout(self, token):
        if self.cap_token == token:
            self._end_capture()

    def _add_wheel(self):
        token = self._begin_capture(self.t("press_wheel"))
        self.joy.suppress = True  # le moteur ignore les boutons pendant la capture

        def on(name, button, down):
            if down:
                self.q.put(("cap_wheel", (token, name, button)))

        self._cap_listener = on
        self.joy.add_listener(on)

    def _add_key(self):
        token = self._begin_capture(self.t("press_key"))
        self.joy.suppress = True

        def work():
            try:
                import keyboard
                self.q.put(("cap_key", (token, keyboard.read_hotkey(suppress=False))))
            except Exception as e:
                self._log(f"Key capture failed: {e}")

        threading.Thread(target=work, daemon=True).start()

    def _add_binding(self, b):
        b = dict(b, lang=None)
        if b not in self.cfg["bindings"]:
            self.cfg["bindings"].append(b)
            self._save()
        self._render_bindings()

    # -- onglet Voix -------------------------------------------------------------
    def _tab_speech(self, f):
        ttk.Label(f, text=self.t("speech_langs"), font=("Segoe UI", 9, "bold")).pack(anchor="w")
        ttk.Label(f, text=self.t("help_speech"), wraplength=520, justify="left").pack(
            anchor="w", pady=(0, 6))
        grid = ttk.Frame(f)
        grid.pack(anchor="w")
        self.lang_vars = {}
        allowed = set(self.cfg["allowed_languages"])
        codes = sorted(i18n.SPEECH_LANGS, key=lambda c: i18n.NAMES[c].lower())
        for n, code in enumerate(codes):
            var = tk.BooleanVar(value=code in allowed)
            self.lang_vars[code] = var
            ttk.Checkbutton(grid, text=i18n.NAMES[code], variable=var,
                            command=lambda c=code: self._on_lang_toggle(c)).grid(
                row=n // 3, column=n % 3, sticky="w", padx=(0, 18), pady=1)
        ttk.Label(f, text=self.t("ga_note"), foreground="gray").pack(anchor="w", pady=(4, 10))

        ttk.Label(f, text=self.t("model"), font=("Segoe UI", 9, "bold")).pack(anchor="w")
        labels = [self.t("model_" + k) for k in MODEL_KEYS]
        self.cb_model = ttk.Combobox(f, values=labels, state="readonly", width=34)
        cur = self.cfg["model_size"]
        self.cb_model.current(MODEL_KEYS.index(cur) if cur in MODEL_KEYS else 2)
        self.cb_model.pack(anchor="w", pady=2)
        self.cb_model.bind("<<ComboboxSelected>>", self._on_model)
        self.v_model_note = tk.StringVar()
        ttk.Label(f, textvariable=self.v_model_note, foreground="gray").pack(anchor="w")
        self._update_model_note()

        self.v_gpu = tk.BooleanVar(value=self.cfg["device"] == "cuda")
        ttk.Checkbutton(f, text=self.t("gpu"), variable=self.v_gpu, command=self._on_gpu).pack(
            anchor="w", pady=(10, 0))

        ttk.Label(f, text=self.t("mic"), font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(10, 0))
        mics = [self.t("mic_default")] + self._mic_names()
        self.cb_mic = ttk.Combobox(f, values=mics, state="readonly", width=48)
        cur_mic = self.cfg.get("mic_device")
        self.cb_mic.current(mics.index(cur_mic) if cur_mic in mics else 0)
        self.cb_mic.pack(anchor="w", pady=2)
        self.cb_mic.bind("<<ComboboxSelected>>", self._on_mic)

    def _mic_names(self):
        try:
            import sounddevice as sd
            seen, out = set(), []
            for d in sd.query_devices():
                if d["max_input_channels"] > 0 and d["name"] not in seen:
                    seen.add(d["name"])
                    out.append(d["name"])
            return out
        except Exception:
            return []

    def _on_lang_toggle(self, code):
        chosen = [c for c, v in self.lang_vars.items() if v.get()]
        if not chosen:           # au moins une langue
            self.lang_vars[code].set(True)
            return
        self.cfg["allowed_languages"] = chosen
        self._save()

    def _on_model(self, _e=None):
        self.cfg["model_size"] = MODEL_KEYS[self.cb_model.current()]
        self._update_model_note()
        self._save()

    def _update_model_note(self):
        size = self.cfg["model_size"]
        if models.is_downloaded(size):
            self.v_model_note.set("")
        else:
            self.v_model_note.set(self.t("model_note", mb=models.MODEL_MB.get(size, 500)))

    def _on_gpu(self):
        self.cfg["device"] = "cuda" if self.v_gpu.get() else "cpu"
        self._save()

    def _on_mic(self, _e=None):
        idx = self.cb_mic.current()
        self.cfg["mic_device"] = None if idx == 0 else self.cb_mic.get()
        self._save()

    # -- onglet Options -------------------------------------------------------------
    def _tab_options(self, f):
        ttk.Label(f, text=self.t("ui_language"), font=("Segoe UI", 9, "bold")).pack(anchor="w")
        codes = sorted(i18n.NAMES, key=lambda c: i18n.NAMES[c].lower())
        cb = ttk.Combobox(f, values=[i18n.NAMES[c] for c in codes], state="readonly", width=24)
        cb.current(codes.index(self.cfg["ui_language"]))
        cb.pack(anchor="w", pady=2)
        cb.bind("<<ComboboxSelected>>", lambda e: self._on_ui_lang(codes[cb.current()]))

        ttk.Label(f, text=self.t("send_mode"), font=("Segoe UI", 9, "bold")).pack(
            anchor="w", pady=(12, 0))
        self.v_send = tk.StringVar(value=self.cfg["send_mode"])
        for val, key in (("auto", "send_auto"), ("keys", "send_keys"), ("insim", "send_insim")):
            ttk.Radiobutton(f, text=self.t(key), value=val, variable=self.v_send,
                            command=self._on_send).pack(anchor="w")

        row = ttk.Frame(f)
        row.pack(anchor="w", pady=(12, 0))
        ttk.Label(row, text=self.t("chat_key")).pack(side="left")
        self.v_chat = tk.StringVar(value=self.cfg["chat_key"])
        e = ttk.Entry(row, width=6, textvariable=self.v_chat)
        e.pack(side="left", padx=8)
        self.v_chat.trace_add("write", lambda *a: self._on_chat_key())

        row = ttk.Frame(f)
        row.pack(anchor="w", pady=(6, 0))
        ttk.Label(row, text=self.t("clean_delay")).pack(side="left")
        d = self.cfg.get("clean_delay")
        self.v_clean = tk.StringVar(value="" if d is None else str(d))
        ttk.Entry(row, width=6, textvariable=self.v_clean).pack(side="left", padx=8)
        self.v_clean.trace_add("write", lambda *a: self._on_clean())

        ttk.Label(f, text=self.t("lfs_exe"), font=("Segoe UI", 9, "bold")).pack(
            anchor="w", pady=(12, 0))
        row = ttk.Frame(f)
        row.pack(fill="x")
        self.v_exe = tk.StringVar(value=self.cfg["lfs_exe"])
        ttk.Entry(row, textvariable=self.v_exe).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text=self.t("browse"), command=self._browse_exe).pack(side="left", padx=6)
        self.v_exe.trace_add("write", lambda *a: self._on_exe())

        ttk.Label(f, text=self.t("admin_hint"), foreground="gray", wraplength=520,
                  justify="left").pack(anchor="w", pady=(14, 4))
        ttk.Button(f, text=self.t("open_logs"), command=self._open_data).pack(anchor="w")
        ttk.Label(f, text=f"LFS Voice {__version__}", foreground="gray").pack(anchor="w", pady=(14, 0))

    def _on_ui_lang(self, code):
        self.cfg["ui_language"] = code
        self._save()
        self.after(0, self._build_ui)  # après la fin de l'événement du menu déroulant

    def _on_send(self):
        self.cfg["send_mode"] = self.v_send.get()
        self._save()

    def _on_chat_key(self):
        v = self.v_chat.get().strip()
        if v:
            self.cfg["chat_key"] = v
            self._save()

    def _on_clean(self):
        v = self.v_clean.get().strip().replace(",", ".")
        if not v:
            self.cfg["clean_delay"] = None
        else:
            try:
                self.cfg["clean_delay"] = max(0.0, float(v))
            except ValueError:
                return
        self._save()

    def _on_exe(self):
        self.cfg["lfs_exe"] = self.v_exe.get().strip()
        self._save()

    def _browse_exe(self):
        p = filedialog.askopenfilename(title="LFS.exe",
                                       filetypes=[("LFS.exe", "LFS.exe"), ("*.exe", "*.exe")])
        if p:
            self.v_exe.set(os.path.normpath(p))

    def _open_data(self):
        try:
            os.startfile(C.DATA_DIR)  # Windows uniquement
        except Exception:
            pass

    # -- onglet Journal ----------------------------------------------------------------
    def _tab_log(self, f):
        self.txt = tk.Text(f, height=16, wrap="word", state="disabled")
        sb = ttk.Scrollbar(f, command=self.txt.yview)
        self.txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.txt.pack(side="left", fill="both", expand=True)
        for line in self.log_lines:
            self._append_log(line)

    def _append_log(self, line):
        self.txt.config(state="normal")
        self.txt.insert("end", line + "\n")
        self.txt.see("end")
        self.txt.config(state="disabled")

    # ------------------------------------------------------------------------ statut
    def _refresh_status(self):
        kind, kw = self.run_state
        key = {"stopped": "st_stopped", "loading": "st_loading", "downloading": "st_downloading",
               "ready": "st_ready", "error": "st_error"}.get(kind, "st_stopped")
        self.v_status.set(self.t(key, **{k: kw.get(k, "") for k in ("pct", "msg")}))
        self.btn_toggle.config(text=self.t("btn_stop" if self.engine else "btn_start"))
        if self.engine and self.cfg["send_mode"] != "keys":
            self.v_insim.set(self.t("insim_on" if self.insim_on else "insim_off"))
        else:
            self.v_insim.set("")
        if not self.engine:
            self.v_hint.set("")

    # ----------------------------------------------------------------------- actions
    def _toggle(self):
        if self.engine:
            self._stop_engine()
        else:
            self._start_engine()

    def _start_engine(self):
        if not self.cfg["bindings"]:
            messagebox.showinfo("LFS Voice", self.t("err_no_binding"))
            self.nb.select(TAB_BUTTONS)
            return False
        self.v_hint.set("")
        self.insim_on = False
        self.engine = Engine(
            copy.deepcopy(self.cfg), self.joy, self._log,
            lambda kind, **kw: self.q.put(("status", (kind, kw))),
            lambda on: self.q.put(("insim", on)))
        self.run_state = ("loading", {})
        self.engine.start()
        self._refresh_status()
        return True

    def _stop_engine(self):
        eng, self.engine = self.engine, None
        if eng:
            eng.stop()
        self.run_state = ("stopped", {})
        self._refresh_status()

    def _launch_lfs(self):
        exe = self.cfg.get("lfs_exe") or C.find_lfs()
        if not exe or not os.path.isfile(exe):
            messagebox.showerror("LFS Voice", self.t("err_lfs_missing"))
            self.nb.select(TAB_OPTIONS)
            return
        if self.cfg["lfs_exe"] != exe:
            self.cfg["lfs_exe"] = exe
            self.v_exe.set(exe)
            self._save()
        if not self.engine and not self._start_engine():
            return
        try:
            proc = subprocess.Popen([exe], cwd=os.path.dirname(exe))
        except OSError as e:
            messagebox.showerror("LFS Voice", str(e))
            return
        threading.Thread(target=lambda: (proc.wait(), self.q.put(("lfs_closed", None))),
                         daemon=True).start()

    # ------------------------------------------------------------- file de messages
    def _pump(self):
        try:
            while True:
                kind, data = self.q.get_nowait()
                self._handle(kind, data)
        except queue.Empty:
            pass
        self.after(100, self._pump)

    def _handle(self, kind, data):
        if kind == "log":
            line = time.strftime("%H:%M:%S ") + str(data).rstrip()
            self.log_lines.append(line)
            self.log_lines = self.log_lines[-500:]
            try:
                with open(C.LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError:
                pass
            if hasattr(self, "txt") and self.txt.winfo_exists():
                self._append_log(line)
        elif kind == "status":
            if not self.engine and data[0] != "error":
                return  # message tardif d'un moteur déjà arrêté
            self.run_state = data
            if data[0] == "error":
                self.engine = None
            self._refresh_status()
        elif kind == "insim":
            self.insim_on = bool(data)
            self._refresh_status()
        elif kind == "cap_wheel":
            token, name, button = data
            if token == self.cap_token:
                self._end_capture()
                self._add_binding({"kind": "joystick", "device": name, "button": button})
        elif kind == "cap_key":
            token, key = data
            if token == self.cap_token:
                self._end_capture()
                self._add_binding({"kind": "keyboard", "key": key})
        elif kind == "lfs_closed":
            if self.engine:
                self._stop_engine()

    def _on_close(self):
        self._end_capture()
        if self.engine:
            self._stop_engine()
        self.joy.stop()
        self.destroy()
