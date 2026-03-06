"""
Always-on mic with Voice Activity Detection (VAD).
Records until the user stops speaking (silence after speech), then returns a WAV file path for Whisper.
For Pi / no-keyboard mode: set PMO_VOICE_ONLY=1 and run main.py; speak, then pause to submit.
"""
import os
import tempfile
import wave

try:
    import pyaudio
    import webrtcvad
    _DEPS_AVAILABLE = True
except ImportError:
    _DEPS_AVAILABLE = False

SAMPLE_RATE = 16000
# webrtcvad expects 10, 20, or 30 ms frames at 8/16/32 kHz
FRAME_MS = 20
FRAME_BYTES = int(SAMPLE_RATE * FRAME_MS / 1000 * 2)  # 16-bit = 2 bytes per sample


def is_available() -> bool:
    """True if pyaudio and webrtcvad are installed and mic can be used."""
    if not _DEPS_AVAILABLE:
        return False
    try:
        p = pyaudio.PyAudio()
        p.get_default_input_device_info()
        p.terminate()
        return True
    except Exception:
        return False


def record_until_silence(
    silence_duration_ms: int = 1200,
    min_utterance_ms: int = 400,
    max_duration_ms: int = 15000,
    vad_aggressiveness: int = 2,
) -> str | None:
    """
    Listen to the microphone until the user stops speaking (silence for silence_duration_ms).
    Returns path to a temp WAV file (16 kHz mono 16-bit) ready for Whisper, or None if nothing recorded.
    """
    if not _DEPS_AVAILABLE:
        return None
    vad = webrtcvad.Vad(vad_aggressiveness)
    pa = pyaudio.PyAudio()
    try:
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=FRAME_BYTES,
        )
    except Exception:
        pa.terminate()
        return None

    buffer: list[bytes] = []
    state = "waiting"  # waiting | speaking
    speech_ms = 0
    silence_ms = 0
    total_ms = 0
    max_frames = max_duration_ms // FRAME_MS
    min_speech_frames = min_utterance_ms // FRAME_MS
    silence_frames_needed = silence_duration_ms // FRAME_MS
    frames_in_buffer = 0

    try:
        while True:
            try:
                chunk = stream.read(FRAME_BYTES, exception_on_overflow=False)
            except Exception:
                break
            buffer.append(chunk)
            frames_in_buffer += 1
            total_ms += FRAME_MS

            if len(chunk) < FRAME_BYTES:
                break
            is_speech = vad.is_speech(chunk, SAMPLE_RATE)

            if state == "waiting":
                if is_speech:
                    speech_ms += FRAME_MS
                    if speech_ms >= min_utterance_ms:
                        state = "speaking"
                    else:
                        # keep waiting for enough speech to avoid false triggers
                        pass
                else:
                    speech_ms = max(0, speech_ms - FRAME_MS)
            else:  # speaking
                if is_speech:
                    silence_ms = 0
                else:
                    silence_ms += FRAME_MS
                    if silence_ms >= silence_duration_ms:
                        # End of utterance
                        break

            if total_ms >= max_duration_ms:
                break
        stream.stop_stream()
        stream.close()
    finally:
        pa.terminate()

    if state != "speaking" or frames_in_buffer < min_speech_frames:
        return None

    # Write WAV to temp file
    fd, path = tempfile.mkstemp(suffix=".wav")
    try:
        with os.fdopen(fd, "wb") as f:
            with wave.open(f, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)  # 16-bit
                wav.setframerate(SAMPLE_RATE)
                wav.writeframes(b"".join(buffer))
        return path
    except Exception:
        try:
            os.unlink(path)
        except Exception:
            pass
        return None
