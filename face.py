"""
Pygame face – cute character; mouth syncs to TTS, idle animations, error frown.
Skin #4c32a8, window 800x480. Fullscreen on Raspberry Pi (or when PMO_FACE_FULLSCREEN=1).
"""
import math
import os
import sys
import time
import traceback

# Skin color (user-specified)
SKIN = (0x4c, 0x32, 0xa8)  # #4c32a8
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
MOUTH_INNER = (0x38, 0x68, 0x3e)
MOUTH_TONGUE = (0x9c, 0xbc, 0x60)

WIDTH, HEIGHT = 800, 480


def _use_fullscreen() -> bool:
    """True on Raspberry Pi (for kiosk/fullscreen), or when PMO_FACE_FULLSCREEN=1. False on dev PC."""
    env = os.getenv("PMO_FACE_FULLSCREEN", "").strip().lower()
    if env in ("1", "true", "yes"):
        return True
    if env in ("0", "false", "no"):
        return False
    if sys.platform != "linux":
        return False
    try:
        with open("/proc/device-tree/model", "rb") as f:
            return b"Raspberry" in f.read()
    except Exception:
        return False


# Shared state (written from agent thread, read in face loop)
_last_interaction_time = [time.time()]  # list so we can mutate from outside
_error_until = [0.0]  # time.time() until when to show frown
_running = False
_screen = None  # Created on main thread, used by run_face_loop()
_face_ok = False  # True only if the display started successfully


def record_interaction() -> None:
    """Call when user sends a message or assistant replies (resets idle timer)."""
    _last_interaction_time[0] = time.time()


def show_error(duration_seconds: float = 2.0) -> None:
    """Show frown for the given duration. Call when an error occurs."""
    _error_until[0] = time.time() + duration_seconds


def _draw_face(
    screen: "pygame.Surface",
    talking: bool,
    mouth_open: bool,
    eyes_closed: bool,
    look_offset: float,
    frown: bool,
    drift_phase: float | None,
) -> None:
    """Draw the face with optional look offset and drift (face parts displaced)."""
    import pygame
    screen.fill(SKIN)

    cx, cy = WIDTH // 2, HEIGHT // 2
    base_eye_y = int(HEIGHT * 0.38)
    base_eye_offset = 120
    eye_radius = 28
    base_mouth_y = int(HEIGHT * 0.62)
    mouth_width = 140
    mouth_height_open = 50

    # Drift: displace eyes and mouth apart then back (0 -> 1 -> 0)
    if drift_phase is not None:
        # 0 = normal, 0.5 = max drift, 1 = back
        drift = math.sin(drift_phase * math.pi) * 1.0
        eye_dx = int(80 * drift)   # eyes move apart
        mouth_dy = int(30 * drift) # mouth moves down
    else:
        eye_dx = 0
        mouth_dy = 0

    eye_y = base_eye_y
    eye_offset = base_eye_offset + eye_dx
    mouth_y = base_mouth_y + mouth_dy
    # Look side to side: shift both eyes together
    look = int(look_offset)

    # Eyes
    if eyes_closed:
        for dx in (-eye_offset, eye_offset):
            x = cx + dx + look
            rect = pygame.Rect(x - 22, eye_y - 22, 44, 44)
            pygame.draw.arc(screen, BLACK, rect, 0, 3.14159, 5)
    else:
        for dx in (-eye_offset, eye_offset):
            pygame.draw.circle(screen, BLACK, (cx + dx + look, eye_y), eye_radius)

    # Mouth
    if frown:
        # Downward arc (sad)
        mouth_rect = pygame.Rect(cx - mouth_width // 2, mouth_y - 30, mouth_width, 40)
        pygame.draw.arc(screen, BLACK, mouth_rect, 0, 3.14159, 6)
    elif talking and mouth_open:
        mx_left = cx - mouth_width // 2
        mouth_rect = pygame.Rect(mx_left, mouth_y - 8, mouth_width, mouth_height_open + 8)
        pygame.draw.rect(screen, BLACK, mouth_rect, border_radius=12)
        inner = pygame.Rect(mx_left + 6, mouth_y, mouth_width - 12, mouth_height_open - 4)
        pygame.draw.rect(screen, MOUTH_INNER, inner, border_radius=8)
        teeth = pygame.Rect(mx_left + 8, mouth_y - 2, mouth_width - 16, 14)
        pygame.draw.rect(screen, WHITE, teeth, border_radius=4)
        tongue_rect = pygame.Rect(mx_left + 20, mouth_y + mouth_height_open - 28, mouth_width - 40, 22)
        pygame.draw.ellipse(screen, MOUTH_TONGUE, tongue_rect)
    else:
        # Closed smile
        mouth_rect = pygame.Rect(cx - mouth_width // 2, mouth_y - 10, mouth_width, 40)
        pygame.draw.arc(screen, BLACK, mouth_rect, 3.14, 6.28, 6)


def _face_loop(screen: "pygame.Surface | None") -> None:
    """Run the face draw loop. If screen is None, display failed."""
    global _face_ok
    import pygame
    if screen is None:
        _face_ok = False
        return
    _face_ok = True
    clock = pygame.time.Clock()

    blink_timer = 0.0
    eyes_closed = False
    talk_timer = 0.0
    look_phase = 0.0
    drift_phase = None
    drift_duration = 4.0
    drift_elapsed = 0.0
    long_idle_triggered = False

    global _running
    _running = True
    while _running:
        dt = clock.get_time() / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                _running = False
                break
        if not _running:
            break

        now = time.time()
        talking = pygame.mixer.get_busy()
        show_frown = now < _error_until[0]

        # Talk timer: close mouth briefly every 1.5s while talking
        if talking:
            talk_timer += dt
        else:
            talk_timer = 0.0
        talk_cycle = talk_timer % 1.5
        mouth_open = talking and (talk_cycle > 0.15)

        # Blink
        blink_timer += dt
        if 3.8 < blink_timer < 4.2:
            eyes_closed = True
        elif blink_timer > 4.2:
            eyes_closed = False
            blink_timer = 0.0

        # Look side to side: starts after short idle, subtle and reactive
        time_since_interaction = now - _last_interaction_time[0]
        look_delay = 2.5  # seconds before look starts (feels reactive)
        look_amount = 12   # pixels each way (subtle)
        if not talking and drift_phase is None and time_since_interaction > look_delay:
            look_phase += dt * 1.2
            look_offset = look_amount * math.sin(look_phase)
        else:
            look_offset = 0.0

        # Long idle (55s): face splits apart way after look-around easter egg
        drift_idle_delay = 55.0
        if time_since_interaction > drift_idle_delay and drift_phase is None and not long_idle_triggered:
            long_idle_triggered = True
            drift_phase = 0.0
            drift_elapsed = 0.0
        if drift_phase is not None:
            drift_elapsed += dt
            drift_phase = min(1.0, drift_elapsed / drift_duration)
            if drift_phase >= 1.0:
                drift_phase = None
                long_idle_triggered = False
                _last_interaction_time[0] = time.time()

        _draw_face(
            screen,
            talking=talking,
            mouth_open=mouth_open,
            eyes_closed=eyes_closed,
            look_offset=look_offset,
            frown=show_frown,
            drift_phase=drift_phase,
        )
        pygame.display.flip()
        clock.tick(30)
    pygame.quit()


def _log(msg: str) -> None:
    print(msg, flush=True)


def start_face() -> None:
    """Create the face window on the current (main) thread. Call once at startup.
    Then the caller must run run_face_loop() on the same thread so the window appears (required on Windows)."""
    global _screen, _face_ok
    _log("[Face] start_face() called.")
    if _screen is not None:
        _log("[Face] Window already exists, skipping.")
        return
    _last_interaction_time[0] = time.time()
    try:
        if sys.platform == "win32":
            import os
            os.environ.setdefault("SDL_VIDEODRIVER", "windows")
            os.environ.setdefault("SDL_VIDEO_WINDOW_POS", "100,100")
        _log("[Face] Importing pygame and creating window...")
        import pygame
        pygame.init()
        pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
        flags = pygame.FULLSCREEN if _use_fullscreen() else 0
        _screen = pygame.display.set_mode((WIDTH, HEIGHT), flags)
        pygame.display.set_caption("Assistant")
        pygame.display.flip()
        if sys.platform == "win32":
            try:
                wm_info = pygame.display.get_wm_info()
                hwnd = wm_info.get("window") or wm_info.get("hwnd")
                if hwnd:
                    import ctypes
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
            except Exception:
                pass
        _face_ok = True
        _log("[Face] Window created (800x480)." + (" Fullscreen." if _use_fullscreen() else ""))
    except Exception as e:
        print(f"[Face] Could not start display: {e}", flush=True)
        traceback.print_exc()
        print("[Face] On Pi: use a connected display, or set PMO_FACE=0. For framebuffer try: export SDL_VIDEODRIVER=kmsdrm", flush=True)
        print("[Face] On Windows: run in a normal terminal (not WSL without GUI). Try: python scripts/test_face.py", flush=True)
        _face_ok = False
        _screen = None


def run_face_loop() -> None:
    """Run the face event/draw loop. Blocks until stop_face() is called. Must be called on the main thread (same thread that called start_face())."""
    global _running
    _running = True
    if _screen is not None:
        _log("[Face] Entering event loop.")
        _face_loop(_screen)
    else:
        _log("[Face] No display; skipping event loop.")
    _running = False


def stop_face() -> None:
    """Signal the face window to close."""
    global _running
    _running = False
