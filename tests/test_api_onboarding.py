import tempfile
import unittest
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import patch

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"


def _load_submodule(module_name: str, file_name: str):
    spec = importlib.util.spec_from_file_location(module_name, TOOLS_DIR / file_name)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


tools_pkg = types.ModuleType("tools")
tools_pkg.__path__ = [str(TOOLS_DIR)]
sys.modules.setdefault("tools", tools_pkg)

fake_google_auth = types.ModuleType("tools.google_auth")
fake_google_auth.get_credentials = lambda: None
sys.modules["tools.google_auth"] = fake_google_auth

_load_submodule("tools.api_key_extractors", "api_key_extractors.py")
_load_submodule("tools.env_install", "env_install.py")
web_automation_module = _load_submodule("tools.web_automation", "web_automation.py")
api_onboarding_module = _load_submodule("tools.api_onboarding", "api_onboarding.py")
api_key_extractors_module = sys.modules["tools.api_key_extractors"]

onboard_api_integration = api_onboarding_module.onboard_api_integration
BrowserRunResult = web_automation_module.BrowserRunResult
DiscoveryResult = web_automation_module.DiscoveryResult


class _FakeProfile:
    name = "fake"

    def discover(self, provider):
        return DiscoveryResult(
            provider=provider,
            docs_url="https://demo.dev/docs",
            signup_url="https://demo.dev/signup",
            notes="test",
        )

    def run_signup(self, provider, account_email, signup_url, headless, timeout_ms):
        return BrowserRunResult(
            status="ok",
            visited_urls=[signup_url],
            blockers=[],
            extracted_text=["api_key: testkey_1234567890"],
            artifacts={},
        )

    def gmail_queries(self, provider):
        return ['newer_than:7d ("demo" OR "api key")']

    def extract_candidates_from_browser(self, provider, browser_result):
        return api_key_extractors_module.extract_credential_candidates(
            browser_result.extracted_text, provider=provider, source="browser"
        )

    def extract_candidates_from_email(self, provider, email_body):
        return api_key_extractors_module.extract_credential_candidates(
            [email_body], provider=provider, source="gmail"
        )

    def select_install_credentials(self, candidates):
        best = {}
        for candidate in candidates:
            best.setdefault(candidate.key_name, candidate.key_value)
        return best

    def validate_installed(self, env_text, installed):
        missing = [k for k in installed if f"{k}=" not in env_text]
        if missing:
            return False, f"Missing env entries after install: {missing}"
        return True, "Validation passed: installed secrets present in .env"


class ApiOnboardingTests(unittest.TestCase):
    @patch("tools.api_onboarding.resolve_provider_profile")
    @patch("tools.api_onboarding._poll_gmail_for_provider")
    def test_onboarding_happy_path_installs_secret(
        self,
        mock_poll_mail,
        mock_resolve_profile,
    ):
        mock_resolve_profile.return_value = _FakeProfile()
        mock_poll_mail.return_value = []

        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            report = onboard_api_integration(
                provider="demo",
                account_email="me@example.com",
                project_env_path=str(env_path),
                allow_full_secret_logs=True,
                dry_run=False,
            )
            self.assertIn("Status: success", report)
            self.assertTrue(env_path.exists())
            text = env_path.read_text(encoding="utf-8")
            self.assertIn("DEMO_API_KEY=testkey_1234567890", text)

    @patch("tools.api_onboarding.resolve_provider_profile")
    @patch("tools.api_onboarding._poll_gmail_for_provider")
    def test_onboarding_dry_run_no_install(
        self,
        mock_poll_mail,
        mock_resolve_profile,
    ):
        class _DryRunFakeProfile(_FakeProfile):
            def run_signup(self, provider, account_email, signup_url, headless, timeout_ms):
                return BrowserRunResult(
                    status="ok",
                    visited_urls=[signup_url],
                    blockers=[],
                    extracted_text=["api_key: dryrun_1234567890"],
                    artifacts={},
                )

        mock_resolve_profile.return_value = _DryRunFakeProfile()
        mock_poll_mail.return_value = []

        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            report = onboard_api_integration(
                provider="demo",
                account_email="me@example.com",
                project_env_path=str(env_path),
                allow_full_secret_logs=True,
                dry_run=True,
            )
            self.assertIn("Status: success", report)
            self.assertFalse(env_path.exists())


if __name__ == "__main__":
    unittest.main()

