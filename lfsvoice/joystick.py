"""Surveillance des boutons de volant/manette (un seul fil possède pygame)."""
import os
import threading
import time


class JoystickMonitor:
    def __init__(self):
        self.listeners = []     # fonctions (device_name, button, pressed)
        self.names = {}         # instance_id -> nom du périphérique
        self.suppress = False   # True pendant la capture d'un bouton dans l'interface
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if not self._thread:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()

    def add_listener(self, fn):
        if fn not in self.listeners:
            self.listeners.append(fn)

    def remove_listener(self, fn):
        if fn in self.listeners:
            self.listeners.remove(fn)

    def device_names(self):
        return sorted(set(self.names.values()))

    def _run(self):
        # Permet de lire le volant même quand LFS a le focus
        os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
        try:
            import pygame
            pygame.display.init()
            pygame.display.set_mode((1, 1), pygame.HIDDEN)
            pygame.joystick.init()
        except Exception:
            return
        joys = {}

        def add(index):
            try:
                j = pygame.joystick.Joystick(index)
                joys[j.get_instance_id()] = j
                self.names[j.get_instance_id()] = j.get_name()
            except Exception:
                pass

        for i in range(pygame.joystick.get_count()):
            add(i)
        while not self._stop.is_set():
            for e in pygame.event.get():
                if e.type == pygame.JOYDEVICEADDED:
                    add(e.device_index)
                elif e.type == pygame.JOYDEVICEREMOVED:
                    joys.pop(e.instance_id, None)
                    self.names.pop(e.instance_id, None)
                elif e.type in (pygame.JOYBUTTONDOWN, pygame.JOYBUTTONUP):
                    name = self.names.get(e.instance_id)
                    if name is None:
                        continue
                    down = e.type == pygame.JOYBUTTONDOWN
                    for fn in list(self.listeners):
                        try:
                            fn(name, e.button, down)
                        except Exception:
                            pass
            time.sleep(0.005)
