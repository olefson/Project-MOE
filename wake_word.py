"""
Wake word detection using Picovoice Porcupine.
Blocks until the user says the wake phrase, then returns so the main loop can record the question with VAD.
Requires PICOVOICE_ACCESS_KEY in .env (free at https://console.picovoice.ai/).
Use a custom phrase (e.g. "Hey pee moe") by setting PICOVOICE_KEYWORD_PATH to a .ppn file (from Picovoice Console).
"""
import os
import struct
import sys
from pathlib import Path

try:
    import pvporcupine
    import pyaudio
    _DEPS_AVAILABLE = True
except ImportError:
    _DEPS_AVAILABLE = False

# Project root (where main.py and optional .ppn live)
_PROJECT_ROOT = Path(__file__).resolve().parent

# Built-in keyword fallback (say "Bumblebee" to wake PMO when no custom .ppn)
WAKE_KEYWORD = "bumblebee"

# Default custom wake word file names (place in Project-MOE/ or set PICOVOICE_KEYWORD_PATH)
# Picovoice .ppn files are platform-specific: use the Windows build on Windows, Pi on Linux.
DEFAULT_PPN_NAME_LINUX = "Hey-pee-moe_en_raspberry-pi_v4_0_0.ppn"
DEFAULT_PPN_NAME_WINDOWS = "Hey-pee-moe_en_windows_v4_0_0.ppn"


def _get_keyword_path() -> Path | None:
    """Resolve custom .ppn path from env or default file in project root. Uses platform-specific default name if no env set."""
    env_path = os.getenv("PICOVOICE_KEYWORD_PATH", "").strip()
    if env_path:
        p = Path(env_path)
        if not p.is_absolute():
            p = _PROJECT_ROOT / p
        return p if p.exists() else None
    # Default .ppn by platform (must be trained for that platform in Picovoice Console)
    if sys.platform == "linux":
        default = _PROJECT_ROOT / DEFAULT_PPN_NAME_LINUX
    elif sys.platform == "win32":
        default = _PROJECT_ROOT / DEFAULT_PPN_NAME_WINDOWS
    else:
        default = _PROJECT_ROOT / DEFAULT_PPN_NAME_WINDOWS  # try Windows name on Mac too
    return default if default.exists() else None


def get_wake_phrase_display() -> str:
    """Human-readable wake phrase for prompts (custom .ppn or built-in)."""
    if _get_keyword_path():
        return "Hey pee moe"
    return WAKE_KEYWORD


def is_available(access_key: str | None = None) -> bool:
    """True if pvporcupine and pyaudio are installed and access_key is set (or passed)."""
    if not _DEPS_AVAILABLE:
        return False
    key = (access_key or "").strip()
    if not key:
        return False
    try:
        path = _get_keyword_path()
        if path is not None:
            porcupine = pvporcupine.create(access_key=key, keyword_paths=[str(path)])
        else:
            porcupine = pvporcupine.create(access_key=key, keywords=[WAKE_KEYWORD])
        porcupine.delete()
        return True
    except Exception:
        return False


def listen_for_wake_word(
    access_key: str,
    sensitivity: float = 0.5,
    tail_ms: int = 700,
) -> tuple[bool, bytes]:
    """
    Block until the wake word is detected. Returns (True, tail_audio) when heard, (False, b"") on error.
    tail_audio is audio captured for tail_ms after the wake word (same format: 16 kHz mono 16-bit).
    Pass tail_audio to record_until_silence(initial_audio=...) so the rest of the sentence is not lost.
    """
    if not _DEPS_AVAILABLE:
        return False, b""
    path = _get_keyword_path()
    try:
        if path is not None:
            porcupine = pvporcupine.create(
                access_key=access_key.strip(),
                keyword_paths=[str(path)],
                sensitivities=[sensitivity],
            )
        else:
            porcupine = pvporcupine.create(
                access_key=access_key.strip(),
                keywords=[WAKE_KEYWORD],
                sensitivities=[sensitivity],
            )
    except Exception:
        return False, b""

    sample_rate = porcupine.sample_rate
    frame_length = porcupine.frame_length
    frame_bytes = frame_length * 2  # 16-bit

    device_index = None
    try:
        s = os.getenv("PMO_MIC_DEVICE_INDEX", "").strip()
        if s:
            device_index = int(s)
    except ValueError:
        pass

    pa = pyaudio.PyAudio()
    open_kw = {
        "format": pyaudio.paInt16,
        "channels": 1,
        "rate": sample_rate,
        "input": True,
        "frames_per_buffer": frame_length,
    }
    if device_index is not None:
        open_kw["input_device_index"] = device_index
    try:
        stream = pa.open(**open_kw)
    except Exception:
        porcupine.delete()
        pa.terminate()
        return False, b""

    detected = False
    tail_frames: list[bytes] = []
    try:
        while True:
            try:
                chunk = stream.read(frame_length, exception_on_overflow=False)
            except Exception:
                break
            if len(chunk) < frame_bytes:
                break
            if detected:
                tail_frames.append(chunk)
                if len(tail_frames) * frame_bytes >= sample_rate * 2 * (tail_ms / 1000.0):
                    break
                continue
            pcm = list(struct.unpack_from(f"<{frame_length}h", chunk))
            keyword_index = porcupine.process(pcm)
            if keyword_index >= 0:
                detected = True
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()
        porcupine.delete()

    tail_audio = b"".join(tail_frames) if detected else b""
    return detected, tail_audio
