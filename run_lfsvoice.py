"""Point d'entrée de LFS Voice (utilisé par PyInstaller)."""
import ctypes
import locale
import os
import sys
import traceback


def _system_locale():
    try:
        buf = ctypes.create_unicode_buffer(85)
        if ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85):
            return buf.value
    except Exception:
        pass
    try:
        return locale.getlocale()[0] or ""
    except Exception:
        return ""


def main():
    from lfsvoice import config as C
    from lfsvoice import i18n

    first_run = not os.path.exists(C.CONFIG_PATH)
    cfg = C.load()
    if first_run:
        lang = i18n.default_language(_system_locale())
        cfg["ui_language"] = lang
        cfg["allowed_languages"] = [lang if lang in i18n.SPEECH_LANGS else "en"]
        cfg["lfs_exe"] = C.find_lfs()
        try:
            C.save(cfg)
        except OSError:
            pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # texte net sur écrans HiDPI
    except Exception:
        pass
    from lfsvoice.gui import App
    App(cfg).mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        err = traceback.format_exc()
        try:
            from lfsvoice import config as C
            with open(C.LOG_PATH, "a", encoding="utf-8") as f:
                f.write(err)
        except Exception:
            pass
        try:
            ctypes.windll.user32.MessageBoxW(0, err[-1500:], "LFS Voice", 0x10)
        except Exception:
            print(err, file=sys.stderr)
        sys.exit(1)
