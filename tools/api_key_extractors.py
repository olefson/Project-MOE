"""
Helpers for extracting API credential artifacts from text/html.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


@dataclass
class CredentialCandidate:
    """A candidate credential artifact with confidence metadata."""

    key_name: str
    key_value: str
    source: str
    confidence: float
    reason: str


_KEY_VALUE_PATTERNS = [
    re.compile(r"(?i)\b(api[_\-\s]?key)\b\s*[:=]\s*([A-Za-z0-9_\-\.]{12,})"),
    re.compile(r"(?i)\b(access[_\-\s]?token)\b\s*[:=]\s*([A-Za-z0-9_\-\.]{12,})"),
    re.compile(r"(?i)\b(secret[_\-\s]?key)\b\s*[:=]\s*([A-Za-z0-9_\-\.]{12,})"),
    re.compile(r"(?i)\b(client[_\-\s]?id)\b\s*[:=]\s*([A-Za-z0-9_\-\.]{8,})"),
    re.compile(r"(?i)\b(client[_\-\s]?secret)\b\s*[:=]\s*([A-Za-z0-9_\-\.]{12,})"),
]

_GENERIC_TOKEN_PATTERNS = [
    re.compile(r"\b(sk-[A-Za-z0-9]{16,})\b"),
    re.compile(r"\b(Bearer\s+[A-Za-z0-9_\-\.]{16,})\b"),
    re.compile(r"\b([A-Fa-f0-9]{32,})\b"),
]

_VERIFY_LINK_PATTERN = re.compile(
    r"""(?ix)
    \bhttps?://
    [^\s"'<>]+
    (?:verify|verification|confirm|activate|signup|token|api[-_]?key)
    [^\s"'<>]*
    """
)


def provider_prefix(provider: str) -> str:
    """Normalize provider to uppercase env-var-friendly prefix."""
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", provider.strip().upper()).strip("_")
    return normalized or "API"


def default_env_name(provider: str, semantic_name: str) -> str:
    """Map semantic credential name to env var name."""
    prefix = provider_prefix(provider)
    semantic = re.sub(r"[^A-Za-z0-9]+", "_", semantic_name.strip().upper()).strip("_")
    mapping = {
        "API_KEY": f"{prefix}_API_KEY",
        "ACCESS_TOKEN": f"{prefix}_ACCESS_TOKEN",
        "CLIENT_ID": f"{prefix}_CLIENT_ID",
        "CLIENT_SECRET": f"{prefix}_CLIENT_SECRET",
        "SECRET_KEY": f"{prefix}_SECRET_KEY",
    }
    return mapping.get(semantic, f"{prefix}_{semantic or 'CREDENTIAL'}")


def _semantic_name(raw_label: str) -> str:
    label = raw_label.lower().strip().replace(" ", "_").replace("-", "_")
    if "api" in label and "key" in label:
        return "API_KEY"
    if "access" in label and "token" in label:
        return "ACCESS_TOKEN"
    if "client" in label and "secret" in label:
        return "CLIENT_SECRET"
    if "client" in label and "id" in label:
        return "CLIENT_ID"
    if "secret" in label and "key" in label:
        return "SECRET_KEY"
    return "CREDENTIAL"


def extract_credential_candidates(
    text_blocks: Iterable[str],
    provider: str,
    source: str = "unknown",
) -> list[CredentialCandidate]:
    """Extract credential candidates from one or more text blocks."""
    candidates: list[CredentialCandidate] = []
    for block in text_blocks:
        if not block:
            continue
        for pattern in _KEY_VALUE_PATTERNS:
            for match in pattern.finditer(block):
                semantic = _semantic_name(match.group(1))
                value = match.group(2).strip()
                candidates.append(
                    CredentialCandidate(
                        key_name=default_env_name(provider, semantic),
                        key_value=value,
                        source=source,
                        confidence=0.95,
                        reason=f"Matched explicit {semantic.lower()} pattern",
                    )
                )
        for pattern in _GENERIC_TOKEN_PATTERNS:
            for match in pattern.finditer(block):
                value = match.group(1).strip()
                candidates.append(
                    CredentialCandidate(
                        key_name=default_env_name(provider, "API_KEY"),
                        key_value=value,
                        source=source,
                        confidence=0.65,
                        reason="Matched generic token pattern",
                    )
                )
    return dedupe_candidates(candidates)


def extract_verification_links(text: str) -> list[str]:
    """Return verification/onboarding links from email text."""
    if not text:
        return []
    links = [m.group(0).rstrip(").,;") for m in _VERIFY_LINK_PATTERN.finditer(text)]
    unique: list[str] = []
    seen = set()
    for link in links:
        if link in seen:
            continue
        seen.add(link)
        unique.append(link)
    return unique


def dedupe_candidates(candidates: Iterable[CredentialCandidate]) -> list[CredentialCandidate]:
    """Deduplicate candidates by env var and value, keeping highest confidence."""
    best: dict[tuple[str, str], CredentialCandidate] = {}
    for cand in candidates:
        key = (cand.key_name, cand.key_value)
        existing = best.get(key)
        if not existing or cand.confidence > existing.confidence:
            best[key] = cand
    ordered = sorted(best.values(), key=lambda c: c.confidence, reverse=True)
    return ordered

