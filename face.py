"""
Pygame face – cute character; mouth syncs to TTS, idle animations, error frown.
Skin #4c32a8, window 800x480.
"""
import math
import threading
import time

# Skin color (user-specified)
SKIN = (0x4c, 0x32, 0xa8)  # #4c32a8
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
MOUTH_INNER = (0x38, 0x68, 0x3e)
MOUTH_TONGUE = (0x9c, 0xbc, 0x60)

WIDTH, HEIGHT = 800, 480

# Shared state (written from main thread, read in face thread)
_last_interaction_time = [time.time()]  # list so we can mutate from outside
_error_until = [0.0]  # time.time() until when to show frown
_running = False
_thread = None


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


def _face_loop() -> None:
    import pygame
    pygame.init()
    pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Assistant")
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


def start_face() -> None:
    """Start the face window in a background thread. Call once at startup."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _last_interaction_time[0] = time.time()
    _thread = threading.Thread(target=_face_loop, daemon=True)
    _thread.start()
    time.sleep(0.3)


def stop_face() -> None:
    """Signal the face window to close."""
    global _running
    _running = False
