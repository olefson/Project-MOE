"""
Google Sheets API: list spreadsheets and read sheet data. For voice: PMO can read sheets and summarize.
"""
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from tools.google_auth import get_credentials, not_signed_in_message
from tools.drive import _get_drive_service, list_files

SHEETS_MIME = "application/vnd.google-apps.spreadsheet"


def _get_sheets_service():
    creds = get_credentials()
    if not creds:
        return None
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def list_sheets(max_results: int = 10, query: str = "") -> str:
    """List recent Google Sheets. Returns id, name, and link so PMO can reference them."""
    return list_files(
        mime_type=SHEETS_MIME,
        max_results=max_results,
        query=query,
        type_label="Google Sheets",
    )


def get_sheet_data(spreadsheet_id: str, range_notation: str = "") -> str:
    """
    Get cell data from a Google Sheet. range_notation is A1 notation (e.g. "Sheet1!A1:D10" or "A1:D10").
    Returns tab-separated text so PMO can read and summarize for the user (e.g. on a voice assistant).
    """
    service = _get_sheets_service()
    if not service:
        return not_signed_in_message("Google Sheets")
    try:
        r = range_notation.strip() or "Sheet1"  # default first sheet, all used range
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id.strip(),
            range=r,
        ).execute()
        values = result.get("values") or []
        if not values:
            return "Sheet is empty or range has no data."
        # Format as readable text (tab-separated rows, one per line).
        lines = []
        for row in values:
            lines.append("\t".join(str(c) for c in row))
        return "Sheet data:\n" + "\n".join(lines)
    except HttpError as e:
        return f"Google Sheets error: {e.reason or str(e)}"
    except Exception as e:
        return f"Failed to get sheet data: {e}"
