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


def speak(text: str) -> bool:
    """
    Synthesize text with Piper (cori high) and play via pygame.mixer.
    Returns True if played, False if TTS unavailable or playback failed.
    """
    if not text or not text.strip():
        return False
    voice = _get_voice()
    if voice is None:
        return False
    try:
        import wave
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = f.name
        try:
            with wave.open(wav_path, "wb") as wav_file:
                synth = getattr(voice, "synthesize_wav", None) or getattr(voice, "synthesize", None)
                if synth:
                    synth(text.strip(), wav_file)
            # Play with pygame.mixer (same as future face)
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
            sound = pygame.mixer.Sound(wav_path)
            sound.play()
            while pygame.mixer.get_busy():
                pygame.time.wait(50)
        finally:
            try:
                os.unlink(wav_path)
            except Exception:
                pass
        return True
    except Exception:
        return False


def is_available() -> bool:
    """True if Piper voice is installed and loadable."""
    return _get_voice() is not None
