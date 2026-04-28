import unittest
import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "api_key_extractors.py"
SPEC = importlib.util.spec_from_file_location("api_key_extractors_module", MODULE_PATH)
EXTRACTORS_MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["api_key_extractors_module"] = EXTRACTORS_MODULE
SPEC.loader.exec_module(EXTRACTORS_MODULE)
default_env_name = EXTRACTORS_MODULE.default_env_name
extract_credential_candidates = EXTRACTORS_MODULE.extract_credential_candidates
extract_verification_links = EXTRACTORS_MODULE.extract_verification_links


class ApiKeyExtractorTests(unittest.TestCase):
    def test_extract_explicit_api_key_and_token(self):
        text = """
        Your API key: mySecretApiKey123456
        access_token = token_abcdef1234567890
        """
        candidates = extract_credential_candidates([text], provider="demo", source="test")
        names = {c.key_name for c in candidates}
        self.assertIn("DEMO_API_KEY", names)
        self.assertIn("DEMO_ACCESS_TOKEN", names)

    def test_extract_verification_links(self):
        text = "Click https://example.com/verify?token=abc and then https://example.com/signup?ok=1"
        links = extract_verification_links(text)
        self.assertGreaterEqual(len(links), 2)

    def test_default_env_name_mapping(self):
        self.assertEqual(default_env_name("Acme API", "api_key"), "ACME_API_API_KEY")
        self.assertEqual(default_env_name("Acme API", "client_id"), "ACME_API_CLIENT_ID")


if __name__ == "__main__":
    unittest.main()

