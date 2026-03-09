"""
Always-on mic with Voice Activity Detection (VAD).
Records until the user stops speaking (silence after speech), then returns a WAV file path for Whisper.
For Pi / no-keyboard mode: set PMO_VOICE_ONLY=1 and run main.py; speak, then pause to submit.
On Windows, if webrtcvad is not available we fall back to a simple energy-based detector.
"""
import os
import struct
import tempfile
import wave

try:
    import pyaudio
    _HAVE_PYAUDIO = True
except ImportError:
    pyaudio = None  # type: ignore[assignment]
    _HAVE_PYAUDIO = False

try:
    import webrtcvad
    _HAVE_WEBRTCVAD = True
except ImportError:
    webrtcvad = None  # type: ignore[assignment]
    _HAVE_WEBRTCVAD = False

_DEPS_AVAILABLE = _HAVE_PYAUDIO

SAMPLE_RATE = 16000
# webrtcvad expects 10, 20, or 30 ms frames at 8/16/32 kHz
FRAME_MS = 20
FRAME_BYTES = int(SAMPLE_RATE * FRAME_MS / 1000 * 2)  # 16-bit = 2 bytes per sample

# When mic only supports 48k (e.g. Pi USB), record at 48k and resample to 16k
HW_RATE_48K = 48000
# 40 ms at 48k = 1920 samples (same duration as 640 samples at 16k)
FRAME_SAMPLES_48K = int(HW_RATE_48K * 40 / 1000)  # 1920


def get_mic_sample_rate() -> int:
    """Return hardware mic rate: 48000 if PMO_MIC_RATE=48000 (for Pi USB mics that don't support 16k), else 16000."""
    s = os.getenv("PMO_MIC_RATE", "").strip().lower()
    if s in ("48000", "48"):
        return HW_RATE_48K
    return SAMPLE_RATE


def _resample_to_16k(chunk_bytes: bytes, from_rate: int) -> bytes:
    """Resample 16-bit mono PCM from from_rate to 16000 Hz. Used when recording at 48k on Pi."""
    if from_rate == SAMPLE_RATE:
        return chunk_bytes
    if from_rate != HW_RATE_48K:
        return chunk_bytes  # no-op for unknown rate
    try:
        from scipy.signal import resample_poly
    except ImportError:
        # Fallback: decimate by 3 (take every 3rd sample); may alias but works for voice
        n = len(chunk_bytes) // 2
        samples = struct.unpack_from(f"<{n}h", chunk_bytes)
        out = struct.pack(f"<{n // 3}h", *samples[::3])
        return out
    n = len(chunk_bytes) // 2
    samples = struct.unpack_from(f"<{n}h", chunk_bytes)
    # 48k -> 16k: ratio 1/3
    out = resample_poly(samples, 1, 3)
    out_int = [int(round(x)) for x in out]
    return struct.pack(f"<{len(out_int)}h", *out_int)


def _rms_16bit(chunk: bytes) -> float:
    """RMS of 16-bit little-endian PCM (no audioop dependency; audioop removed in Python 3.13)."""
    n = len(chunk) // 2
    if n == 0:
        return 0.0
    samples = struct.unpack_from(f"<{n}h", chunk)
    return (sum(s * s for s in samples) / n) ** 0.5


def _input_device_index() -> int | None:
    """Optional mic device index from PMO_MIC_DEVICE_INDEX (e.g. for Pi USB mic)."""
    s = os.getenv("PMO_MIC_DEVICE_INDEX", "").strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def is_available() -> bool:
    """True if PyAudio is installed and the mic can be used (VAD may fall back to energy-based on some platforms)."""
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
    initial_audio: bytes = b"",
) -> str | None:
    """
    Listen to the microphone until the user stops speaking (silence for silence_duration_ms).
    If initial_audio is provided (e.g. tail from wake word), it is prepended so the full sentence is captured.
    Returns path to a temp WAV file (16 kHz mono 16-bit) ready for Whisper, or None if nothing recorded.
    """
    if not _DEPS_AVAILABLE:
        return None
    vad = webrtcvad.Vad(vad_aggressiveness) if _HAVE_WEBRTCVAD else None
    hw_rate = get_mic_sample_rate()
    if hw_rate != SAMPLE_RATE:
        rate = hw_rate
        read_frames = FRAME_SAMPLES_48K
    else:
        rate = SAMPLE_RATE
        read_frames = FRAME_BYTES  # 640 frames at 16k

    pa = pyaudio.PyAudio()
    device_index = _input_device_index()
    open_kw: dict = {
        "format": pyaudio.paInt16,
        "channels": 1,
        "rate": rate,
        "input": True,
        "frames_per_buffer": read_frames,
    }
    if device_index is not None:
        open_kw["input_device_index"] = device_index
    try:
        stream = pa.open(**open_kw)
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

    # Prepend wake-word tail so "bumblebee, how's the weather" is fully captured.
    # When we have tail, we're already mid-utterance: go straight to "speaking" and capture until silence.
    if initial_audio:
        n = len(initial_audio) // FRAME_BYTES
        for i in range(n):
            chunk = initial_audio[i * FRAME_BYTES : (i + 1) * FRAME_BYTES]
            buffer.append(chunk)
            frames_in_buffer += 1
            total_ms += FRAME_MS
        state = "speaking"
        silence_ms = 0

    try:
        while True:
            try:
                chunk = stream.read(read_frames, exception_on_overflow=False)
            except Exception:
                break
            if hw_rate != SAMPLE_RATE:
                chunk = _resample_to_16k(chunk, hw_rate)
            buffer.append(chunk)
            frames_in_buffer += 1
            chunk_ms = (len(chunk) // 2) * 1000 // SAMPLE_RATE
            total_ms += chunk_ms

            if len(chunk) < FRAME_BYTES:
                break
            if _HAVE_WEBRTCVAD:
                is_speech = vad.is_speech(chunk, SAMPLE_RATE)  # type: ignore[union-attr]
            else:
                # Simple RMS-based detector when webrtcvad is unavailable (e.g., Windows without build tools).
                rms = _rms_16bit(chunk)
                # Empirical threshold: treat as speech if above low noise floor.
                is_speech = rms > 400

            if state == "waiting":
                if is_speech:
                    speech_ms += chunk_ms
                    if speech_ms >= min_utterance_ms:
                        state = "speaking"
                    else:
                        # keep waiting for enough speech to avoid false triggers
                        pass
                else:
                    speech_ms = max(0, speech_ms - chunk_ms)
            else:  # speaking
                if is_speech:
                    silence_ms = 0
                else:
                    silence_ms += chunk_ms
                    if silence_ms >= silence_duration_ms:
                        # End of utterance
                        break

            if total_ms >= max_duration_ms:
                break
        stream.stop_stream()
        stream.close()
    finally:
        pa.terminate()

    min_frames = min_speech_frames if not initial_audio else 1
    if state != "speaking" or frames_in_buffer < min_frames:
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
