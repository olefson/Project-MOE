import importlib.util
import sys
import types
import unittest
from pathlib import Path

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

_load_submodule("tools.api_key_extractors", "api_key_extractors.py")
_load_submodule("tools.web_automation", "web_automation.py")
_load_submodule("tools.provider_profiles.base", "provider_profiles/base.py")
_load_submodule("tools.provider_profiles.generic", "provider_profiles/generic.py")
_load_submodule("tools.provider_profiles.stripe", "provider_profiles/stripe.py")
_load_submodule("tools.provider_profiles.twilio", "provider_profiles/twilio.py")
registry_module = _load_submodule("tools.provider_profiles.registry", "provider_profiles/registry.py")


class ProviderProfileRegistryTests(unittest.TestCase):
    def test_resolve_twilio_profile(self):
        profile = registry_module.resolve_provider_profile("twilio")
        self.assertEqual(profile.name, "twilio")
        discovery = profile.discover("twilio")
        self.assertIn("twilio.com/docs", discovery.docs_url)
        self.assertIn("twilio.com/try-twilio", discovery.signup_url)

    def test_resolve_unknown_uses_generic(self):
        profile = registry_module.resolve_provider_profile("some-random-provider")
        self.assertEqual(profile.name, "generic")


if __name__ == "__main__":
    unittest.main()

