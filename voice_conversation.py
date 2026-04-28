"""
Single-stream voice conversation: wake word once to "start conversation", then listen until silence
for each turn. No stream handoff — one mic stream from wake through the whole conversation.
Exit conversation when user says goodbye/quit (caller checks transcript) or session is closed.

On platforms where webrtcvad cannot be built (e.g., Windows without C++ build tools) we fall back to a
simple RMS-based speech detector; wake word detection still uses Porcupine.
"""
import os
import struct
import sys
import tempfile
import wave

from voice_input import (
    FRAME_BYTES,
    FRAME_MS,
    FRAME_SAMPLES_48K,
    get_mic_sample_rate,
    HW_RATE_48K,
    SAMPLE_RATE,
    _input_device_index,
    _resample_to_16k,
    _rms_16bit,
)
from wake_word import _get_keyword_path, WAKE_KEYWORD

try:
    import pvporcupine
    _HAVE_PV = True
except ImportError:
    pvporcupine = None  # type: ignore[assignment]
    _HAVE_PV = False

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

_DEPS_AVAILABLE = _HAVE_PV and _HAVE_PYAUDIO

# VAD/recording params stay aligned with voice_input.
SILENCE_DURATION_MS = 1200
MIN_UTTERANCE_MS = 300  # lower = lock in to "speaking" sooner, fewer false "no speech"
MAX_DURATION_MS = 15000
VAD_AGGRESSIVENESS = 1  # 0=least aggressive, 3=most; lower = more sensitive to speech
# webrtcvad wants 10/20/30 ms; since I read 40 ms chunks, I split into 20 ms sub-frames.
VAD_FRAME_BYTES = 640  # 20 ms at 16 kHz 16-bit


def _create_porcupine(access_key: str):
    path = _get_keyword_path()
    if path is not None:
        return pvporcupine.create(
            access_key=access_key.strip(),
            keyword_paths=[str(path)],
            sensitivities=[0.5],
        )
    return pvporcupine.create(
        access_key=access_key.strip(),
        keywords=[WAKE_KEYWORD],
        sensitivities=[0.5],
    )


def open_conversation(access_key: str) -> "ConversationSession | None":
    """
    Open one mic stream and Porcupine for wake word. Returns a session object to pass to
    get_next_utterance() until the user says goodbye, then close_conversation(session).
    """
    if not _DEPS_AVAILABLE:
        print("[Voice] Missing deps: install pvporcupine and pyaudio (webrtcvad optional; without it we use a simple energy detector).", file=sys.stderr, flush=True)
        return None
    access_key = (access_key or "").strip()
    if not access_key:
        print("[Voice] PICOVOICE_ACCESS_KEY is empty. Set it in .env (free key at https://console.picovoice.ai/).", file=sys.stderr, flush=True)
        return None
    try:
        porcupine = _create_porcupine(access_key)
    except Exception as e:
        print(f"[Voice] Porcupine init failed: {e}", file=sys.stderr, flush=True)
        return None
    sample_rate = porcupine.sample_rate  # 16000 for Porcupine
    frame_length = porcupine.frame_length  # 512 samples

    hw_rate = get_mic_sample_rate()
    if hw_rate != SAMPLE_RATE:
        # Record at 48k then resample to 16k for Porcupine/Whisper (Pi USB mic reality).
        rate = hw_rate
        frames_per_buffer = FRAME_SAMPLES_48K  # 1920 = 40 ms at 48k
    else:
        rate = sample_rate
        frames_per_buffer = FRAME_BYTES  # 640 frames = 40 ms at 16k

    pa = pyaudio.PyAudio()
    device_index = _input_device_index()
    open_kw = {
        "format": pyaudio.paInt16,
        "channels": 1,
        "rate": rate,
        "input": True,
        "frames_per_buffer": frames_per_buffer,
    }
    if device_index is not None:
        open_kw["input_device_index"] = device_index
    try:
        stream = pa.open(**open_kw)
    except Exception as e:
        print(f"[Voice] Mic open failed: {e}", file=sys.stderr, flush=True)
        porcupine.delete()
        pa.terminate()
        return None

    return ConversationSession(
        stream=stream,
        pa=pa,
        porcupine=porcupine,
        frame_length=frame_length,
        wake_done=False,
        hw_sample_rate=hw_rate,
    )


class ConversationSession:
    """Holds the open mic stream and wake-word state. Opaque to caller."""
    __slots__ = ("stream", "pa", "porcupine", "frame_length", "wake_done", "hw_sample_rate")

    def __init__(self, stream, pa, porcupine, frame_length: int, wake_done: bool, hw_sample_rate: int = 16000):
        self.stream = stream
        self.pa = pa
        self.porcupine = porcupine
        self.frame_length = frame_length
        self.wake_done = wake_done
        self.hw_sample_rate = hw_sample_rate


def get_next_utterance(session: "ConversationSession") -> str | None:
    """
    Block until one full utterance (speech then silence_duration_ms of silence).
    First call: wait for wake word on the same stream, then record until silence.
    Subsequent calls: just record until silence (conversation mode, no wake word).
    Returns path to a temp WAV (16 kHz mono 16-bit) for Whisper, or None on error / no speech.
    Caller should unlink the path after use.
    """
    if not _DEPS_AVAILABLE or session is None:
        return None
    vad = webrtcvad.Vad(VAD_AGGRESSIVENESS) if _HAVE_WEBRTCVAD else None
    stream = session.stream
    porcupine = session.porcupine
    frame_length = session.frame_length
    # PyAudio read(num_frames) math: 16k->640 frames (1280 B), 48k->1920 frames (3840 B), then resample back to 1280 B.
    read_frames = FRAME_SAMPLES_48K if session.hw_sample_rate == HW_RATE_48K else FRAME_BYTES
    porcupine_buffer: list[int] = []

    buffer: list[bytes] = []
    state = "waiting"  # waiting (for speech) | speaking
    speech_ms = 0
    silence_ms = 0
    total_ms = 0
    min_speech_frames = MIN_UTTERANCE_MS // FRAME_MS
    max_frames = MAX_DURATION_MS // FRAME_MS

    try:
        while True:
            try:
                chunk = stream.read(read_frames, exception_on_overflow=False)
            except Exception:
                break
            if session.hw_sample_rate == HW_RATE_48K:
                chunk = _resample_to_16k(chunk, session.hw_sample_rate)
            expected_bytes = 1280  # 40 ms at 16k
            if len(chunk) < expected_bytes:
                break
            total_ms += (len(chunk) // 2) * 1000 // SAMPLE_RATE

            if not session.wake_done:
                # Feed Porcupine exactly what it wants (frame_length samples), using full chunk.
                num_samples = len(chunk) // 2
                pcm = list(struct.unpack_from(f"<{num_samples}h", chunk))
                porcupine_buffer.extend(pcm)
                while len(porcupine_buffer) >= frame_length:
                    feed = porcupine_buffer[:frame_length]
                    porcupine_buffer = porcupine_buffer[frame_length:]
                    idx = porcupine.process(feed)
                    if idx >= 0:
                        session.wake_done = True
                        # Prepend leftovers so I don't chop off "how is the weather".
                        if porcupine_buffer:
                            leftover = struct.pack(
                                f"<{len(porcupine_buffer)}h",
                                *porcupine_buffer,
                            )
                            buffer.append(leftover)
                        porcupine_buffer.clear()
                        break
                if not session.wake_done:
                    continue
                # Wake just fired, so keep this chunk and continue until silence.
                buffer.append(chunk)
                state = "speaking"
                silence_ms = 0
                continue

            # In conversation mode I only rely on VAD (or RMS fallback).
            buffer.append(chunk)
            chunk_ms = (len(chunk) // 2) * 1000 // SAMPLE_RATE
            if _HAVE_WEBRTCVAD:
                # Split 40 ms chunk into 20 ms sub-frames for webrtcvad compatibility.
                is_speech = any(
                    vad.is_speech(chunk[i : i + VAD_FRAME_BYTES], SAMPLE_RATE)  # type: ignore[union-attr]
                    for i in range(0, len(chunk), VAD_FRAME_BYTES)
                )
            else:
                rms = _rms_16bit(chunk)
                is_speech = rms > 280  # lower = pick up quieter speech (was 400)
            if state == "waiting":
                if is_speech:
                    speech_ms += chunk_ms
                    if speech_ms >= MIN_UTTERANCE_MS:
                        state = "speaking"
                else:
                    speech_ms = max(0, speech_ms - chunk_ms)
            else:
                if is_speech:
                    silence_ms = 0
                else:
                    silence_ms += chunk_ms
                    if silence_ms >= SILENCE_DURATION_MS:
                        break
            if total_ms >= MAX_DURATION_MS:
                break
    except Exception:
        pass

    total_bytes = sum(len(b) for b in buffer)
    frames_in_buffer = total_bytes // FRAME_BYTES
    if state != "speaking" or frames_in_buffer < min_speech_frames:
        return None

    fd, path = tempfile.mkstemp(suffix=".wav")
    try:
        with os.fdopen(fd, "wb") as f:
            with wave.open(f, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(SAMPLE_RATE)
                wav.writeframes(b"".join(buffer))
        return path
    except Exception:
        try:
            os.unlink(path)
        except Exception:
            pass
        return None


def close_conversation(session: "ConversationSession | None") -> None:
    if session is None:
        return
    try:
        session.stream.stop_stream()
        session.stream.close()
    except Exception:
        pass
    try:
        session.porcupine.delete()
    except Exception:
        pass
    try:
        session.pa.terminate()
    except Exception:
        pass
