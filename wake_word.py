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

# Default custom wake word file name (place in Project-MOE/ or set PICOVOICE_KEYWORD_PATH)
DEFAULT_PPN_NAME = "Hey-pee-moe_en_raspberry-pi_v4_0_0.ppn"


def _get_keyword_path() -> Path | None:
    """Resolve custom .ppn path from env or default file in project root. On non-Linux we only use env (Pi .ppn is platform-specific)."""
    env_path = os.getenv("PICOVOICE_KEYWORD_PATH", "").strip()
    if env_path:
        p = Path(env_path)
        if not p.is_absolute():
            p = _PROJECT_ROOT / p
        return p if p.exists() else None
    # Default .ppn is for Raspberry Pi; only use on Linux so Windows/Mac keep using built-in Bumblebee
    if sys.platform != "linux":
        return None
    default = _PROJECT_ROOT / DEFAULT_PPN_NAME
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


def listen_for_wake_word(access_key: str, sensitivity: float = 0.5) -> bool:
    """
    Block until the wake word is detected. Returns True when heard (or False on error/cleanup).
    Uses the same mic as voice_input (16 kHz mono 16-bit). Caller should then run record_until_silence().
    """
    if not _DEPS_AVAILABLE:
        return False
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
        return False

    sample_rate = porcupine.sample_rate
    frame_length = porcupine.frame_length
    frame_bytes = frame_length * 2  # 16-bit

    pa = pyaudio.PyAudio()
    try:
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=sample_rate,
            input=True,
            frames_per_buffer=frame_length,
        )
    except Exception:
        porcupine.delete()
        pa.terminate()
        return False

    try:
        while True:
            try:
                chunk = stream.read(frame_length, exception_on_overflow=False)
            except Exception:
                break
            if len(chunk) < frame_bytes:
                break
            # Porcupine expects list of int (16-bit PCM)
            pcm = list(struct.unpack_from(f"<{frame_length}h", chunk))
            keyword_index = porcupine.process(pcm)
            if keyword_index >= 0:
                break
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()
        porcupine.delete()

    return True
