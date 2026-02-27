"""
One-time Google OAuth: open browser, sign in, save token.json.
Run from Project-MOE: python scripts/auth_google.py
Uses credentials.json; writes token.json in the same folder as credentials.
"""
import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

# Project-MOE root (parent of scripts/)
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CREDENTIALS = ROOT / "credentials.json"
DEFAULT_TOKEN = ROOT / "token.json"

# Scopes matching your Data Access setup (Calendar, Drive, Docs, Sheets, Gmail)
# Include openid so returned scope matches (Google adds it when using userinfo.email)
SCOPES = [
    "https://www.googleapis.com/auth/calendar",  # calendars + events
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]


def main() -> None:
    credentials_path = Path(os.getenv("GOOGLE_CREDENTIALS_PATH", DEFAULT_CREDENTIALS))
    token_path = Path(os.getenv("GOOGLE_TOKEN_PATH", DEFAULT_TOKEN))

    if not credentials_path.is_file():
        print(f"Missing credentials file: {credentials_path}")
        print("Download OAuth client JSON from Google Cloud Console and save as credentials.json")
        return

    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
    creds = flow.run_local_server(port=0)

    with open(token_path, "w") as f:
        f.write(creds.to_json())

    print(f"Saved token to {token_path}")
    print("You can now run the API; the backend will use this token for Google APIs.")


if __name__ == "__main__":
    main()
