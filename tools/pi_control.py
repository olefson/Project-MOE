"""Raspberry Pi device control: volume and reboot. Only active on Linux (e.g. Pi OS)."""

import os
import re
import subprocess
import sys


def _is_linux() -> bool:
    return sys.platform == "linux"


def _run(cmd: list[str], capture: bool = True) -> tuple[int, str, str]:
    try:
        r = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            timeout=10,
        )
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        return r.returncode, out, err
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return -1, "", str(e)


def get_volume() -> str:
    """Get current system volume (0-100). Only works on Linux (e.g. Raspberry Pi)."""
    if not _is_linux():
        return "Volume control is only available on Raspberry Pi (Linux)."
    code, out, err = _run(["amixer", "get", "Master"])
    if code != 0:
        return f"Could not get volume. Is ALSA available? {err or out}"
    # Examples include "Mono: Playback 50 [50%]" or "Front Left: Playback 384 [60%]".
    m = re.search(r"\[(\d+)%\]", out)
    if m:
        return f"Volume is at {m.group(1)}%."
    return "Could not parse volume level."


def set_volume(level: int) -> str:
    """Set system volume to a percentage (0-100). Only works on Linux (e.g. Raspberry Pi)."""
    if not _is_linux():
        return "Volume control is only available on Raspberry Pi (Linux)."
    level = max(0, min(100, int(level)))
    code, out, err = _run(["amixer", "set", "Master", f"{level}%"])
    if code != 0:
        return f"Could not set volume: {err or out}"
    return f"Volume set to {level}%."


def volume_up(step: int = 10) -> str:
    """Increase system volume by a percentage. Only works on Linux (e.g. Raspberry Pi)."""
    if not _is_linux():
        return "Volume control is only available on Raspberry Pi (Linux)."
    step = max(1, min(50, int(step)))
    code, out, err = _run(["amixer", "set", "Master", f"{step}%+"])
    if code != 0:
        return f"Could not increase volume: {err or out}"
    return f"Volume increased by {step}%."


def volume_down(step: int = 10) -> str:
    """Decrease system volume by a percentage. Only works on Linux (e.g. Raspberry Pi)."""
    if not _is_linux():
        return "Volume control is only available on Raspberry Pi (Linux)."
    step = max(1, min(50, int(step)))
    code, out, err = _run(["amixer", "set", "Master", f"{step}%-"])
    if code != 0:
        return f"Could not decrease volume: {err or out}"
    return f"Volume decreased by {step}%."


def set_mute(muted: bool) -> str:
    """Mute or unmute system audio. Only works on Linux (e.g. Raspberry Pi)."""
    if not _is_linux():
        return "Volume control is only available on Raspberry Pi (Linux)."
    arg = "mute" if muted else "unmute"
    code, out, err = _run(["amixer", "set", "Master", arg])
    if code != 0:
        return f"Could not set mute: {err or out}"
    return "Muted." if muted else "Unmuted."


def reboot_pi(confirm: bool) -> str:
    """Reboot the Raspberry Pi. Only runs when confirm is True and PMO_ALLOW_REBOOT=1."""
    if not _is_linux():
        return "Reboot is only available on Raspberry Pi (Linux)."
    if not confirm:
        return "Reboot cancelled. Say 'yes, reboot' to confirm."
    if os.getenv("PMO_ALLOW_REBOOT", "").strip().lower() not in ("1", "true", "yes"):
        return "Reboot is disabled. Set PMO_ALLOW_REBOOT=1 in .env and ask the user to confirm again."
    code, out, err = _run(["sudo", "reboot"], capture=False)
    # Reboot usually never returns; if it does, it's often a permission issue.
    if code != 0:
        return f"Reboot failed (is sudo reboot allowed?): {err or out}"
    return "Rebooting now."
