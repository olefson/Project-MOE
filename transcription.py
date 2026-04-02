"""
Speech-to-text for PMO: OpenAI Whisper (default) or Hailo Whisper on Raspberry Pi AI HAT+ 2.

Set PMO_STT=hailo and PMO_HAILO_PYTHON to the hailo-apps venv interpreter (see Documents/PI_FILE_STRUCTURE.md).
"""
from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from openai import OpenAI

SEP_LINE_RE = re.compile(r"^-{20,}\s*$")


def _want_hailo() -> bool:
    v = os.getenv("PMO_STT", "openai").strip().lower()
    return v in ("hailo", "hailo10h", "hailo-10h")


def _hailo_python() -> str | None:
    p = os.getenv("PMO_HAILO_PYTHON", "").strip()
    if p:
        expanded = os.path.expanduser(p)
        if os.path.isfile(expanded) and os.access(expanded, os.X_OK):
            return expanded
        return None
    home = Path.home()
    for name in ("python3", "python"):
        c = home / "hailo-apps" / "venv_hailo_apps" / "bin" / name
        if c.is_file() and os.access(c, os.X_OK):
            return str(c)
    return None


def _parse_hailo_whisper_output(text: str) -> str:
    """Extract transcript between separator lines printed by simple_whisper_chat."""
    lines = text.replace("\r\n", "\n").split("\n")
    for i, line in enumerate(lines):
        if not SEP_LINE_RE.match(line.strip() or ""):
            continue
        parts: list[str] = []
        j = i + 1
        while j < len(lines):
            s = lines[j]
            if SEP_LINE_RE.match(s.strip() or ""):
                break
            if s.strip():
                parts.append(s.strip())
            j += 1
        if parts and j < len(lines) and SEP_LINE_RE.match(lines[j].strip() or ""):
            return " ".join(parts)
    return ""


def transcribe_with_hailo(wav_path: str, timeout: int = 180) -> str:
    py = _hailo_python()
    if not py:
        raise RuntimeError("PMO_STT=hailo but PMO_HAILO_PYTHON is unset and ~/hailo-apps/venv_hailo_apps/bin/python not found")
    wav_abs = str(Path(wav_path).resolve())
    cmd = [
        py,
        "-m",
        "hailo_apps.python.gen_ai_apps.simple_whisper_chat.simple_whisper_chat",
        "--audio",
        wav_abs,
    ]
    env = os.environ.copy()
    apps_root = os.getenv("PMO_HAILO_APPS_ROOT", "").strip()
    cwd: str | None = None
    if apps_root:
        cwd = str(Path(apps_root).expanduser().resolve())
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        cwd=cwd,
    )
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-1500:]
        raise RuntimeError(f"Hailo Whisper exited {proc.returncode}: {tail!r}")
    out = _parse_hailo_whisper_output(combined)
    if not out.strip():
        raise RuntimeError("Hailo Whisper produced empty transcript (unexpected stdout format)")
    return out.strip()


def transcribe_with_openai_file(client: OpenAI, wav_path: str) -> str:
    with open(wav_path, "rb") as f:
        tr = client.audio.transcriptions.create(model="whisper-1", file=f)
    return (tr.text or "").strip()


def transcribe_with_openai_bytes(client: OpenAI, data: bytes, filename: str) -> str:
    buf = io.BytesIO(data)
    buf.name = filename
    tr = client.audio.transcriptions.create(model="whisper-1", file=buf)
    return (tr.text or "").strip()


def transcribe_wav_file(wav_path: str, client: OpenAI) -> str:
    """
    Transcribe a WAV file (e.g. 16 kHz mono from voice_input).
    Hailo when PMO_STT=hailo; otherwise OpenAI. Falls back to OpenAI if Hailo fails.
    """
    if _want_hailo():
        try:
            return transcribe_with_hailo(wav_path)
        except Exception as e:
            print(f"[STT] Hailo Whisper failed ({e}); falling back to OpenAI.", flush=True)
    return transcribe_with_openai_file(client, wav_path)


def transcribe_upload(client: OpenAI, content: bytes, filename: str | None) -> str:
    """
    FastAPI /audio: same STT policy as transcribe_wav_file.
    WebM/Opus (browser) requires ffmpeg to convert to WAV for Hailo; if ffmpeg is missing, uses OpenAI on original bytes.
    """
    if not _want_hailo():
        return transcribe_with_openai_bytes(client, content, filename or "audio.webm")

    suffix = Path(filename or "audio.bin").suffix.lower()
    if suffix not in (".wav", ".wave"):
        if not shutil.which("ffmpeg"):
            print("[STT] Hailo requested but upload is not WAV and ffmpeg not found; using OpenAI Whisper.", flush=True)
            return transcribe_with_openai_bytes(client, content, filename or "audio.webm")
        with tempfile.NamedTemporaryFile(suffix=suffix or ".webm", delete=False) as f_in:
            f_in.write(content)
            in_path = f_in.name
        wav_path = in_path + ".pmo16k.wav"
        try:
            r = subprocess.run(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-y",
                    "-i",
                    in_path,
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    "-c:a",
                    "pcm_s16le",
                    wav_path,
                ],
                capture_output=True,
                timeout=120,
            )
            if r.returncode != 0:
                err = (r.stderr or b"").decode(errors="replace")[-800:]
                print(f"[STT] ffmpeg convert failed ({err!r}); using OpenAI Whisper.", flush=True)
                return transcribe_with_openai_bytes(client, content, filename or "audio.webm")
            try:
                return transcribe_wav_file(wav_path, client)
            finally:
                Path(wav_path).unlink(missing_ok=True)
        finally:
            Path(in_path).unlink(missing_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(content)
        wav_path = f.name
    try:
        return transcribe_wav_file(wav_path, client)
    finally:
        Path(wav_path).unlink(missing_ok=True)
