import tempfile
import unittest
import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "env_install.py"
SPEC = importlib.util.spec_from_file_location("env_install_module", MODULE_PATH)
ENV_INSTALL_MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["env_install_module"] = ENV_INSTALL_MODULE
SPEC.loader.exec_module(ENV_INSTALL_MODULE)
install_secrets_to_env = ENV_INSTALL_MODULE.install_secrets_to_env


class EnvInstallTests(unittest.TestCase):
    def test_install_creates_file_and_writes_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            result = install_secrets_to_env(
                env_path=str(env_path),
                secrets={"DEMO_API_KEY": "abc123", "DEMO_CLIENT_ID": "id987"},
                allow_full_secret_logs=False,
            )
            self.assertTrue(env_path.exists())
            text = env_path.read_text(encoding="utf-8")
            self.assertIn("DEMO_API_KEY=abc123", text)
            self.assertIn("DEMO_CLIENT_ID=id987", text)
            self.assertTrue(result.created)

    def test_install_updates_existing_key_preserving_others(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("A=1\nDEMO_API_KEY=old\nB=2\n", encoding="utf-8")
            install_secrets_to_env(
                env_path=str(env_path),
                secrets={"DEMO_API_KEY": "new"},
                allow_full_secret_logs=False,
            )
            text = env_path.read_text(encoding="utf-8")
            self.assertIn("A=1", text)
            self.assertIn("B=2", text)
            self.assertIn("DEMO_API_KEY=new", text)
            self.assertNotIn("DEMO_API_KEY=old", text)


if __name__ == "__main__":
    unittest.main()

