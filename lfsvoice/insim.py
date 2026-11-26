"""Lien InSim vers LFS : connexion automatique (et reconnexion) + envoi de messages."""
import socket
import struct
import threading
import time

from . import lfsenc

ISP_ISI, ISP_TINY, ISP_MSX = 1, 3, 39   # 38 = ISP_MCI (paquet envoyé par LFS), 39 = ISP_MSX
# Depuis InSim 9, l'octet Size est exprimé en unités de 4 octets. Annoncer une version
# plus ancienne avec ce format fait refuser la connexion par LFS
# ("ISI states old InSimVer but Size byte is new style").
INSIM_VERSION = 9


class InSimLink:
    def __init__(self, port, log, on_change=None, host="127.0.0.1"):
        self.host, self.port = host, port
        self.log = log
        self.on_change = on_change
        self.connected = False
        self.sock = None
        self._lock = threading.Lock()
        self._stop = threading.Event()

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._stop.set()
        self._drop()

    # -- interne -----------------------------------------------------------
    def _set(self, value):
        if value != self.connected:
            self.connected = value
            self.log("InSim connected" if value else "InSim disconnected")
            if self.on_change:
                self.on_change(value)

    def _drop(self):
        s, self.sock = self.sock, None
        if s:
            try:
                s.close()
            except OSError:
                pass

    def _loop(self):
        # IS_ISI : Size=44/4, Type, ReqI, Zero, UDPPort, Flags, InSimVer, Prefix, Interval, Admin, IName
        isi = struct.pack("<BBBBHHBBH16s16s", 11, ISP_ISI, 1, 0, 0, 0, INSIM_VERSION, 0, 0, b"", b"LFS Voice")
        while not self._stop.is_set():
            wait = 3
            try:
                s = socket.create_connection((self.host, self.port), timeout=1.5)
                s.settimeout(None)
                s.sendall(isi)
                self.sock = s
                started = time.time()
                self._set(True)
                try:
                    self._read(s)
                finally:
                    if time.time() - started < 3:   # LFS a refusé la connexion : ne pas insister
                        self.log("InSim refused by LFS; retrying in 30 s")
                        wait = 30
            except OSError:
                pass
            finally:
                self._drop()
                self._set(False)
            self._stop.wait(wait)

    def _read(self, s):
        """Lit les paquets entrants ; répond aux keepalive (TINY_NONE)."""
        buf = b""
        while True:
            data = s.recv(4096)
            if not data:
                return
            buf += data
            while buf:
                size = buf[0] * 4
                if size == 0 or len(buf) < size:
                    break
                pkt, buf = buf[:size], buf[size:]
                if pkt[1] == ISP_TINY and pkt[3] == 0:
                    with self._lock:
                        s.sendall(struct.pack("<BBBB", 1, ISP_TINY, 0, 0))

    # -- API ---------------------------------------------------------------
    def send_text(self, text, lang):
        s = self.sock
        if not s:
            raise ConnectionError("InSim not connected")
        with self._lock:
            for raw in lfsenc.chunks(text, lang):
                s.sendall(struct.pack("<BBBB96s", 25, ISP_MSX, 0, 0, raw))
