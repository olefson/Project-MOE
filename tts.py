"""
Piper TTS – local, free. Voice: cori [high] (en_GB-cori-high).
Run scripts/download_piper_voice.py once to download the voice.
"""
import os
import tempfile
from pathlib import Path

# Project root and voices dir
ROOT = Path(__file__).resolve().parent
VOICES_DIR = ROOT / "voices"
VOICE_ID = "en_GB-cori-high"
VOICE_ONNX = VOICES_DIR / f"{VOICE_ID}.onnx"

_voice = None

# pygame.mixer (must match Piper WAV sample rate for this voice)
_MIXER_FREQ = 22050
_MIXER_BUFFER = 512


def _get_voice():
    """Load Piper voice (cori high). Returns None if not available."""
    global _voice
    if _voice is not None:
        return _voice
    if not VOICE_ONNX.is_file():
        return None
    try:
        try:
            from piper import PiperVoice
        except ImportError:
            from piper.voice import PiperVoice
        _voice = PiperVoice.load(str(VOICE_ONNX))
        return _voice
    except Exception:
        return None


def _ensure_mixer() -> bool:
    """Initialize pygame mixer once. Returns False if pygame unavailable."""
    try:
        import pygame
        if not pygame.mixer.get_init():
            pygame.mixer.init(
                frequency=_MIXER_FREQ, size=-16, channels=1, buffer=_MIXER_BUFFER
            )
        return True
    except Exception:
        return False


def synthesize_to_wav(text: str) -> str | None:
    """
    Synthesize text to a temp WAV file. Caller must delete the path when done.
    Returns None if TTS unavailable or synthesis failed.
    """
    if not text or not text.strip():
        return None
    voice = _get_voice()
    if voice is None:
        return None
    wav_path: str | None = None
    try:
        import wave

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = f.name
        with wave.open(wav_path, "wb") as wav_file:
            synth = getattr(voice, "synthesize_wav", None) or getattr(voice, "synthesize", None)
            if not synth:
                os.unlink(wav_path)
                return None
            synth(text.strip(), wav_file)
        return wav_path
    except Exception:
        if wav_path:
            try:
                os.unlink(wav_path)
            except Exception:
                pass
        return None


def play_wav(wav_path: str) -> bool:
    """
    Play a WAV file via pygame.mixer, then delete the file.
    Tighter busy-poll than legacy speak() for shorter gaps between clips.
    """
    if not wav_path:
        return False
    try:
        if not _ensure_mixer():
            return False
        import pygame

        sound = pygame.mixer.Sound(wav_path)
        sound.play()
        while pygame.mixer.get_busy():
            pygame.time.wait(10)
        return True
    except Exception:
        return False
    finally:
        try:
            os.unlink(wav_path)
        except Exception:
            pass


def speak(text: str) -> bool:
    """
    Synthesize text with Piper (cori high) and play via pygame.mixer.
    Returns True if played, False if TTS unavailable or playback failed.
    """
    path = synthesize_to_wav(text)
    if not path:
        return False
    return play_wav(path)


def is_available() -> bool:
    """True if Piper voice is installed and loadable."""
    return _get_voice() is not None
