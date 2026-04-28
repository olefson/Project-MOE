"""
Provider profile interface for API onboarding.
"""

from __future__ import annotations

from tools.api_key_extractors import CredentialCandidate, default_env_name, extract_credential_candidates
from tools.web_automation import BrowserRunResult, DiscoveryResult, discover_provider_urls, run_signup_automation


class ProviderProfile:
    """Pluggable provider behavior for onboarding stages."""

    name: str = "generic"

    def discover(self, provider: str) -> DiscoveryResult:
        return discover_provider_urls(provider)

    def run_signup(
        self,
        provider: str,
        account_email: str,
        signup_url: str,
        headless: bool,
        timeout_ms: int,
    ) -> BrowserRunResult:
        return run_signup_automation(
            provider=provider,
            account_email=account_email,
            signup_url=signup_url,
            headless=headless,
            timeout_ms=timeout_ms,
        )

    def gmail_queries(self, provider: str) -> list[str]:
        return [f'newer_than:7d ("{provider}" OR "api key" OR "verify")']

    def extract_candidates_from_browser(
        self,
        provider: str,
        browser_result: BrowserRunResult,
    ) -> list[CredentialCandidate]:
        candidates = extract_credential_candidates(
            browser_result.extracted_text,
            provider=provider,
            source=f"browser:{self.name}",
        )
        for artifact_name, artifact_value in browser_result.artifacts.items():
            candidates.append(
                CredentialCandidate(
                    key_name=default_env_name(provider, artifact_name),
                    key_value=artifact_value,
                    source=f"browser-artifact:{self.name}",
                    confidence=0.99,
                    reason=f"Explicit dashboard artifact: {artifact_name}",
                )
            )
        return candidates

    def extract_candidates_from_email(
        self,
        provider: str,
        email_body: str,
    ) -> list[CredentialCandidate]:
        return extract_credential_candidates(
            [email_body],
            provider=provider,
            source=f"gmail:{self.name}",
        )

    def select_install_credentials(self, candidates: list[CredentialCandidate]) -> dict[str, str]:
        best_by_key: dict[str, CredentialCandidate] = {}
        for candidate in candidates:
            if candidate.key_name not in best_by_key:
                best_by_key[candidate.key_name] = candidate
        return {k: v.key_value for k, v in best_by_key.items()}

    def validate_installed(self, env_text: str, installed: dict[str, str]) -> tuple[bool, str]:
        missing = [k for k in installed if f"{k}=" not in env_text]
        if missing:
            return False, f"Missing env entries after install: {missing}"
        return True, "Validation passed: installed secrets present in .env"

