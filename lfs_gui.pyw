"""
Interface graphique de LFS Voice : réglages, détection des boutons du volant,
test du script avec son journal en direct. Les réglages sont enregistrés dans
config.json (même dossier), lu par lfs_voice.py.
"""
import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# Lecture du volant même quand une autre fenêtre (LFS) a le focus
os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "config.json")
SCRIPT = os.path.join(HERE, "lfs_voice.py")
NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW

DEFAULTS = {
    "PTT_KEY": "alt+f9",
    "JOY_INDEX": 1,
    "JOY_BUTTON": 2,
    "JOY_LANG_BUTTONS": {},
    "LANGUAGE": None,
    "ALLOWED_LANGUAGES": ["fr", "en"],
    "MODEL_SIZE": "small",
    "DEVICE": "cpu",
    "COMPUTE_TYPE": "int8",
    "USE_INSIM": False,
    "CHAT_CLEAN_DELAY": 0.15,
    "LFS_EXE": "",
}
LANGS = ["fr", "en", "es", "de", "it", "pt", "nl"]
EXTRA_ROWS = 3


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except FileNotFoundError:
        pass
    except Exception as e:
        messagebox.showwarning("LFS Voice", f"config.json illisible, valeurs par défaut utilisées.\n{e}")
    return cfg


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LFS Voice")
        self.resizable(False, False)
        self.cfg = load_config()
        self.child = None
        self.log_queue = queue.Queue()
        self._pg_ready = False
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._drain_log)

    # ---------------------------------------------------------------- UI
    def _build(self):
        pad = {"padx": 8, "pady": 4}
        root = ttk.Frame(self, padding=8)
        root.grid(sticky="nsew")

        # --- Volant
        f = ttk.LabelFrame(root, text="Bouton du volant (push-to-talk)")
        f.grid(row=0, column=0, sticky="ew", **pad)
        self.v_index = tk.StringVar(value=str(self.cfg["JOY_INDEX"]))
        self.v_button = tk.StringVar(value="" if self.cfg["JOY_BUTTON"] is None else str(self.cfg["JOY_BUTTON"]))
        ttk.Label(f, text="Périphérique n°").grid(row=0, column=0, sticky="w", **pad)
        ttk.Spinbox(f, from_=0, to=15, width=5, textvariable=self.v_index).grid(row=0, column=1, **pad)
        ttk.Label(f, text="Bouton n°").grid(row=0, column=2, sticky="w", **pad)
        ttk.Entry(f, width=5, textvariable=self.v_button).grid(row=0, column=3, **pad)
        ttk.Button(f, text="Détecter…", command=self._detect_main).grid(row=0, column=4, **pad)
        self.v_devname = tk.StringVar(value="")
        ttk.Label(f, textvariable=self.v_devname, foreground="gray").grid(row=1, column=0, columnspan=5, sticky="w", **pad)

        # --- Langues
        f = ttk.LabelFrame(root, text="Langues")
        f.grid(row=1, column=0, sticky="ew", **pad)
        ttk.Label(f, text="Bouton principal :").grid(row=0, column=0, sticky="w", **pad)
        self.v_lang = tk.StringVar(value=self.cfg["LANGUAGE"] or "auto")
        ttk.Combobox(f, width=8, state="readonly", values=["auto"] + LANGS,
                     textvariable=self.v_lang).grid(row=0, column=1, **pad)
        ttk.Label(f, text="(auto = détection parmi les langues autorisées)",
                  foreground="gray").grid(row=0, column=2, columnspan=3, sticky="w", **pad)
        ttk.Label(f, text="Langues autorisées :").grid(row=1, column=0, sticky="w", **pad)
        self.v_allowed = tk.StringVar(value=", ".join(self.cfg["ALLOWED_LANGUAGES"]))
        ttk.Entry(f, width=24, textvariable=self.v_allowed).grid(row=1, column=1, columnspan=2, sticky="w", **pad)

        ttk.Label(f, text="Boutons dédiés à une langue (n° bouton → langue) :").grid(
            row=2, column=0, columnspan=5, sticky="w", **pad)
        self.extra_btn, self.extra_lang = [], []
        items = list(self.cfg["JOY_LANG_BUTTONS"].items())
        for i in range(EXTRA_ROWS):
            btn, lang = items[i] if i < len(items) else ("", "en")
            vb, vl = tk.StringVar(value=str(btn)), tk.StringVar(value=lang)
            self.extra_btn.append(vb)
            self.extra_lang.append(vl)
            ttk.Label(f, text="Bouton n°").grid(row=3 + i, column=0, sticky="e", **pad)
            ttk.Entry(f, width=5, textvariable=vb).grid(row=3 + i, column=1, sticky="w", **pad)
            ttk.Combobox(f, width=6, state="readonly", values=LANGS, textvariable=vl).grid(
                row=3 + i, column=2, **pad)
            ttk.Button(f, text="Détecter…",
                       command=lambda v=vb: self._detect_extra(v)).grid(row=3 + i, column=3, **pad)

        # --- Reconnaissance
        f = ttk.LabelFrame(root, text="Reconnaissance vocale")
        f.grid(row=2, column=0, sticky="ew", **pad)
        ttk.Label(f, text="Modèle :").grid(row=0, column=0, sticky="w", **pad)
        self.v_model = tk.StringVar(value=self.cfg["MODEL_SIZE"])
        ttk.Combobox(f, width=10, state="readonly", values=["tiny", "base", "small", "medium", "large-v3"],
                     textvariable=self.v_model).grid(row=0, column=1, **pad)
        ttk.Label(f, text="Calcul :").grid(row=0, column=2, sticky="w", **pad)
        self.v_device = tk.StringVar(value=self.cfg["DEVICE"])
        ttk.Combobox(f, width=6, state="readonly", values=["cpu", "cuda"],
                     textvariable=self.v_device).grid(row=0, column=3, **pad)
        ttk.Label(f, text="plus gros = plus précis mais plus lent ; cuda = carte NVIDIA",
                  foreground="gray").grid(row=1, column=0, columnspan=4, sticky="w", **pad)

        # --- Envoi
        f = ttk.LabelFrame(root, text="Envoi dans LFS")
        f.grid(row=3, column=0, sticky="ew", **pad)
        self.v_insim = tk.BooleanVar(value=self.cfg["USE_INSIM"])
        ttk.Checkbutton(f, text="Envoyer via InSim (meilleur pour les accents ; /insim=29999 dans LFS)",
                        variable=self.v_insim).grid(row=0, column=0, columnspan=3, sticky="w", **pad)
        ttk.Label(f, text="Touche clavier PTT :").grid(row=1, column=0, sticky="w", **pad)
        self.v_ptt = tk.StringVar(value=self.cfg["PTT_KEY"])
        ttk.Entry(f, width=12, textvariable=self.v_ptt).grid(row=1, column=1, sticky="w", **pad)
        ttk.Label(f, text="Délai effacement du « t » (s) :").grid(row=2, column=0, sticky="w", **pad)
        d = self.cfg["CHAT_CLEAN_DELAY"]
        self.v_clean = tk.StringVar(value="" if d is None else str(d))
        ttk.Entry(f, width=8, textvariable=self.v_clean).grid(row=2, column=1, sticky="w", **pad)
        ttk.Label(f, text="(vide = désactivé)", foreground="gray").grid(row=2, column=2, sticky="w", **pad)

        # --- LFS
        f = ttk.LabelFrame(root, text="LFS.exe (pour le lanceur start_lfs.bat)")
        f.grid(row=4, column=0, sticky="ew", **pad)
        self.v_exe = tk.StringVar(value=self.cfg["LFS_EXE"])
        ttk.Entry(f, width=48, textvariable=self.v_exe).grid(row=0, column=0, **pad)
        ttk.Button(f, text="Parcourir…", command=self._browse_exe).grid(row=0, column=1, **pad)

        # --- Actions + journal
        f = ttk.Frame(root)
        f.grid(row=5, column=0, sticky="ew", **pad)
        ttk.Button(f, text="Enregistrer", command=self._save).grid(row=0, column=0, **pad)
        self.btn_test = ttk.Button(f, text="Tester le script", command=self._toggle_test)
        self.btn_test.grid(row=0, column=1, **pad)
        self.v_status = tk.StringVar(value="")
        ttk.Label(f, textvariable=self.v_status, foreground="#0a5").grid(row=0, column=2, sticky="w", **pad)

        self.log = tk.Text(root, height=10, width=70, state="disabled", wrap="word")
        self.log.grid(row=6, column=0, **pad)

    # ------------------------------------------------------------ config
    def _collect(self):
        def to_int(s, what):
            try:
                return int(s.strip())
            except ValueError:
                raise ValueError(f"{what} : « {s} » n'est pas un nombre entier.")

        cfg = dict(self.cfg)
        cfg["JOY_INDEX"] = to_int(self.v_index.get(), "Périphérique")
        b = self.v_button.get().strip()
        cfg["JOY_BUTTON"] = to_int(b, "Bouton principal") if b else None
        lang = self.v_lang.get()
        cfg["LANGUAGE"] = None if lang == "auto" else lang
        cfg["ALLOWED_LANGUAGES"] = [x.strip() for x in self.v_allowed.get().split(",") if x.strip()]
        extra = {}
        for vb, vl in zip(self.extra_btn, self.extra_lang):
            if vb.get().strip():
                extra[str(to_int(vb.get(), "Bouton dédié"))] = vl.get()
        cfg["JOY_LANG_BUTTONS"] = extra
        cfg["MODEL_SIZE"] = self.v_model.get()
        cfg["DEVICE"] = self.v_device.get()
        cfg["COMPUTE_TYPE"] = "float16" if cfg["DEVICE"] == "cuda" else "int8"
        cfg["USE_INSIM"] = bool(self.v_insim.get())
        cfg["PTT_KEY"] = self.v_ptt.get().strip() or DEFAULTS["PTT_KEY"]
        c = self.v_clean.get().strip()
        if c:
            try:
                cfg["CHAT_CLEAN_DELAY"] = float(c.replace(",", "."))
            except ValueError:
                raise ValueError(f"Délai : « {c} » n'est pas un nombre.")
        else:
            cfg["CHAT_CLEAN_DELAY"] = None
        cfg["LFS_EXE"] = self.v_exe.get().strip()
        return cfg

    def _save(self, quiet=False):
        try:
            cfg = self._collect()
            with open(CONFIG, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception as e:
            messagebox.showerror("LFS Voice", str(e))
            return False
        self.cfg = cfg
        if not quiet:
            self.v_status.set("Réglages enregistrés (pris en compte au prochain lancement du script).")
        return True

    def _browse_exe(self):
        p = filedialog.askopenfilename(title="Choisir LFS.exe",
                                       filetypes=[("LFS.exe", "LFS.exe"), ("Exécutables", "*.exe")])
        if p:
            self.v_exe.set(os.path.normpath(p))

    # --------------------------------------------------------- detection
    def _detect_main(self):
        def done(idx, btn, name):
            self.v_index.set(str(idx))
            self.v_button.set(str(btn))
            self.v_devname.set(f"Détecté : {name}")
        self._detect(done)

    def _detect_extra(self, var):
        def done(idx, btn, name):
            var.set(str(btn))
            self.v_status.set(f"Bouton {btn} détecté sur « {name} » (périphérique {idx}).")
        self._detect(done)

    def _detect(self, callback):
        try:
            import pygame
        except ImportError:
            messagebox.showerror("LFS Voice", "pygame n'est pas installé.\n\npy -3.12 -m pip install pygame")
            return
        try:
            if not self._pg_ready:
                pygame.display.init()
                pygame.display.set_mode((1, 1), pygame.HIDDEN)
                self._pg_ready = True
            pygame.joystick.quit()
            pygame.joystick.init()
            joys = [pygame.joystick.Joystick(i) for i in range(pygame.joystick.get_count())]
        except Exception as e:
            messagebox.showerror("LFS Voice", f"Impossible de lire les périphériques : {e}")
            return
        if not joys:
            messagebox.showinfo("LFS Voice", "Aucun volant/manette détecté.")
            return

        def pressed():
            return {(i, b) for i, j in enumerate(joys) for b in range(j.get_numbuttons()) if j.get_button(b)}

        pygame.event.pump()
        held = pressed()
        deadline = time.time() + 10
        self.v_status.set("Appuie sur le bouton voulu du volant (10 s)…")

        def poll():
            nonlocal held
            pygame.event.pump()
            now = pressed()
            new = now - held
            held = now
            if new:
                i, b = sorted(new)[0]
                callback(i, b, joys[i].get_name())
                return
            if time.time() > deadline:
                self.v_status.set("Aucun bouton détecté.")
                return
            self.after(20, poll)

        poll()

    # -------------------------------------------------------------- test
    def _toggle_test(self):
        if self.child and self.child.poll() is None:
            self._stop_child()
            return
        if not self._save(quiet=True):
            return
        self._log_clear()
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
        try:
            self.child = subprocess.Popen(
                [sys.executable, SCRIPT], cwd=HERE, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                creationflags=NO_WINDOW,
            )
        except Exception as e:
            messagebox.showerror("LFS Voice", f"Lancement impossible : {e}")
            return
        threading.Thread(target=self._read_child, args=(self.child,), daemon=True).start()
        self.btn_test.config(text="Arrêter le test")
        self.v_status.set("Script en cours (ne lance pas LFS via start_lfs.bat en même temps).")

    def _read_child(self, child):
        for line in child.stdout:
            self.log_queue.put(line.decode("utf-8", errors="replace"))
        self.log_queue.put(None)

    def _stop_child(self):
        if self.child and self.child.poll() is None:
            self.child.terminate()

    def _drain_log(self):
        try:
            while True:
                line = self.log_queue.get_nowait()
                if line is None:
                    self.btn_test.config(text="Tester le script")
                    self.v_status.set("Script arrêté.")
                else:
                    self._log_append(line)
        except queue.Empty:
            pass
        self.after(100, self._drain_log)

    def _log_append(self, text):
        self.log.config(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.config(state="disabled")

    def _log_clear(self):
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")

    def _on_close(self):
        self._stop_child()
        self.destroy()


if __name__ == "__main__":
    try:
        App().mainloop()
    except Exception as e:  # .pyw : pas de console, on affiche l'erreur
        messagebox.showerror("LFS Voice", f"Erreur : {e}")
