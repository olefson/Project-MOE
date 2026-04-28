"""
Twilio onboarding profile with discovery and credential mapping hints.
"""

from __future__ import annotations

from tools.api_key_extractors import CredentialCandidate
from tools.provider_profiles.base import ProviderProfile
from tools.web_automation import BrowserRunResult, DiscoveryResult


class TwilioProviderProfile(ProviderProfile):
    name = "twilio"

    def discover(self, provider: str) -> DiscoveryResult:
        return DiscoveryResult(
            provider=provider.strip(),
            docs_url="https://www.twilio.com/docs",
            signup_url="https://www.twilio.com/try-twilio",
            notes="Twilio static profile discovery",
        )

    def gmail_queries(self, provider: str) -> list[str]:
        return [
            'newer_than:7d (from:twilio.com OR from:email.twilio.com) ("verify" OR "confirm" OR "auth token" OR "api key")',
            'newer_than:7d ("Twilio" AND ("verify" OR "account sid" OR "auth token" OR "api key"))',
        ]

    def extract_candidates_from_browser(
        self,
        provider: str,
        browser_result: BrowserRunResult,
    ) -> list[CredentialCandidate]:
        candidates = super().extract_candidates_from_browser(provider, browser_result)
        for artifact_name, artifact_value in browser_result.artifacts.items():
            lower = artifact_name.lower()
            if "account" in lower and "sid" in lower:
                candidates.append(
                    CredentialCandidate(
                        key_name="TWILIO_ACCOUNT_SID",
                        key_value=artifact_value,
                        source="browser-artifact:twilio",
                        confidence=1.0,
                        reason="Twilio profile mapped account SID artifact",
                    )
                )
            if "auth" in lower and "token" in lower:
                candidates.append(
                    CredentialCandidate(
                        key_name="TWILIO_AUTH_TOKEN",
                        key_value=artifact_value,
                        source="browser-artifact:twilio",
                        confidence=1.0,
                        reason="Twilio profile mapped auth token artifact",
                    )
                )
            if lower == "api_key" or ("api" in lower and "key" in lower):
                candidates.append(
                    CredentialCandidate(
                        key_name="TWILIO_API_KEY",
                        key_value=artifact_value,
                        source="browser-artifact:twilio",
                        confidence=1.0,
                        reason="Twilio profile mapped API key artifact",
                    )
                )
            if "api" in lower and "secret" in lower:
                candidates.append(
                    CredentialCandidate(
                        key_name="TWILIO_API_SECRET",
                        key_value=artifact_value,
                        source="browser-artifact:twilio",
                        confidence=1.0,
                        reason="Twilio profile mapped API secret artifact",
                    )
                )
        return candidates

    def select_install_credentials(self, candidates: list[CredentialCandidate]) -> dict[str, str]:
        ordered = sorted(candidates, key=lambda c: c.confidence, reverse=True)
        selected: dict[str, str] = {}
        for candidate in ordered:
            key = candidate.key_name
            upper = key.upper()
            if "TWILIO" in upper and "ACCOUNT" in upper and "SID" in upper:
                selected.setdefault("TWILIO_ACCOUNT_SID", candidate.key_value)
            elif "TWILIO" in upper and "AUTH" in upper and "TOKEN" in upper:
                selected.setdefault("TWILIO_AUTH_TOKEN", candidate.key_value)
            elif "TWILIO" in upper and "API" in upper and "SECRET" in upper:
                selected.setdefault("TWILIO_API_SECRET", candidate.key_value)
            elif "TWILIO" in upper and "API" in upper and "KEY" in upper:
                selected.setdefault("TWILIO_API_KEY", candidate.key_value)
            else:
                selected.setdefault(key, candidate.key_value)
        return selected

