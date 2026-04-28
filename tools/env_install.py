"""
Utilities for writing credential values into a project .env file.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class EnvInstallResult:
    """Result for a credential installation into .env."""

    env_path: str
    written: dict[str, str]
    created: bool


def _parse_lines(text: str) -> list[str]:
    return text.splitlines()


def _upsert_env_lines(lines: list[str], updates: dict[str, str]) -> list[str]:
    remaining = dict(updates)
    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            result.append(line)
            continue
        key, _value = line.split("=", 1)
        key = key.strip()
        if key in remaining:
            result.append(f"{key}={remaining.pop(key)}")
        else:
            result.append(line)
    if remaining:
        if result and result[-1].strip():
            result.append("")
        for key, value in remaining.items():
            result.append(f"{key}={value}")
    return result


def install_secrets_to_env(
    env_path: str,
    secrets: dict[str, str],
    allow_full_secret_logs: bool = False,
) -> EnvInstallResult:
    """
    Upsert secrets into env_path with atomic temp-file replacement.
    """
    path = Path(env_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    existed = path.exists()
    current = path.read_text(encoding="utf-8") if existed else ""
    updated_lines = _upsert_env_lines(_parse_lines(current), secrets)
    final_text = "\n".join(updated_lines) + "\n"

    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        tmp_path.write_text(final_text, encoding="utf-8")
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)

    for key, value in secrets.items():
        if allow_full_secret_logs:
            print(f"[PMO API ONBOARDING] Installed secret {key}={value}", flush=True)
        else:
            masked = value[:4] + "..." + value[-4:] if len(value) > 10 else "***"
            print(f"[PMO API ONBOARDING] Installed secret {key}={masked}", flush=True)

    return EnvInstallResult(env_path=str(path), written=secrets, created=not existed)

