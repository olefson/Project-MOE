"""Minimal Pygame window test. Run from project root: python scripts/test_face.py
If this fails, the full app face will fail with the same error."""
import sys
import os

if sys.platform == "win32":
    os.environ.setdefault("SDL_VIDEODRIVER", "windows")

try:
    import pygame
    pygame.init()
    screen = pygame.display.set_mode((400, 300))
    pygame.display.set_caption("Pygame test - close window to exit")
    print("Window opened. Close the window to exit.")
    running = True
    while running:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
        screen.fill((60, 50, 168))  # similar to face skin
        pygame.display.flip()
    pygame.quit()
    print("OK")
except Exception as e:
    print("Pygame failed:", e)
    import traceback
    traceback.print_exc()
    sys.exit(1)
