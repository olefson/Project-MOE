"""
Shared Google OAuth credentials for Calendar, Gmail, Drive, Docs, Sheets.
Uses token.json from scripts/auth_google.py.
"""
import os
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TOKEN_PATH = ROOT / "token.json"


def get_token_path() -> Path:
    return Path(os.getenv("GOOGLE_TOKEN_PATH", DEFAULT_TOKEN_PATH))


def get_credentials() -> Credentials | None:
    """Load and refresh credentials from token.json. Returns None if file missing or invalid."""
    path = get_token_path()
    if not path.is_file():
        return None
    try:
        creds = Credentials.from_authorized_user_file(str(path), scopes=None)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(path, "w") as f:
                f.write(creds.to_json())
        return creds
    except Exception:
        return None


def not_signed_in_message(service_name: str = "Google") -> str:
    return (
        f"I couldn't connect to {service_name}. Run 'python scripts/auth_google.py' once to sign in, then try again."
    )
