"""
Affiche le numéro des boutons de ton volant quand tu les presses.
Lance :  py -3.12 joy_test.py   puis appuie sur le bouton voulu. Ctrl+C pour quitter.
"""
import os
import time

os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
import pygame

pygame.display.init()
pygame.display.set_mode((1, 1), pygame.HIDDEN)
pygame.joystick.init()

count = pygame.joystick.get_count()
if count == 0:
    print("Aucun volant/manette détecté.")
    raise SystemExit

joys = [pygame.joystick.Joystick(i) for i in range(count)]
for i, j in enumerate(joys):
    print(f"[{i}] {j.get_name()} - {j.get_numbuttons()} boutons")
print("Appuie sur un bouton du volant (Ctrl+C pour quitter)...")

state = {}
try:
    while True:
        pygame.event.pump()
        for i, j in enumerate(joys):
            for b in range(j.get_numbuttons()):
                down = bool(j.get_button(b))
                if down and not state.get((i, b)):
                    print(f"Volant {i} : bouton {b} pressé  -> JOY_INDEX = {i}, JOY_BUTTON = {b}")
                state[(i, b)] = down
        time.sleep(0.01)
except KeyboardInterrupt:
    pass
