"""
Stripe onboarding profile with better discovery and gmail query hints.
"""

from __future__ import annotations

from tools.api_key_extractors import CredentialCandidate
from tools.provider_profiles.base import ProviderProfile
from tools.web_automation import BrowserRunResult, DiscoveryResult


class StripeProviderProfile(ProviderProfile):
    name = "stripe"

    def discover(self, provider: str) -> DiscoveryResult:
        return DiscoveryResult(
            provider=provider.strip(),
            docs_url="https://stripe.com/docs",
            signup_url="https://stripe.com/signup",
            notes="Stripe static profile discovery",
        )

    def gmail_queries(self, provider: str) -> list[str]:
        return [
            'newer_than:7d (from:stripe.com OR from:mail.stripe.com) ("verify" OR "confirmation" OR "api key")',
            'newer_than:7d ("Stripe" AND ("verify" OR "api key"))',
        ]

    def select_install_credentials(self, candidates: list[CredentialCandidate]) -> dict[str, str]:
        ordered = sorted(candidates, key=lambda c: c.confidence, reverse=True)
        selected: dict[str, str] = {}
        for candidate in ordered:
            key = candidate.key_name
            if "STRIPE" in key and "SECRET" not in key and "API_KEY" in key:
                selected.setdefault("STRIPE_SECRET_KEY", candidate.key_value)
            elif "STRIPE" in key and "PUBLISHABLE" in key:
                selected.setdefault("STRIPE_PUBLISHABLE_KEY", candidate.key_value)
            else:
                selected.setdefault(key, candidate.key_value)
        return selected

    def extract_candidates_from_browser(
        self,
        provider: str,
        browser_result: BrowserRunResult,
    ) -> list[CredentialCandidate]:
        candidates = super().extract_candidates_from_browser(provider, browser_result)
        for artifact_name, artifact_value in browser_result.artifacts.items():
            lower = artifact_name.lower()
            if "secret" in lower:
                candidates.append(
                    CredentialCandidate(
                        key_name="STRIPE_SECRET_KEY",
                        key_value=artifact_value,
                        source="browser-artifact:stripe",
                        confidence=1.0,
                        reason="Stripe profile mapped secret artifact",
                    )
                )
            if "publishable" in lower:
                candidates.append(
                    CredentialCandidate(
                        key_name="STRIPE_PUBLISHABLE_KEY",
                        key_value=artifact_value,
                        source="browser-artifact:stripe",
                        confidence=1.0,
                        reason="Stripe profile mapped publishable artifact",
                    )
                )
        return candidates

