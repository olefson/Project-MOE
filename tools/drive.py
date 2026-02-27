"""
Google Drive API: list files (Docs, Sheets, or generic). Used by docs/sheets for listing.
"""
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from tools.google_auth import get_credentials, not_signed_in_message


def _get_drive_service():
    creds = get_credentials()
    if not creds:
        return None
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def list_files(
    mime_type: str = "",
    max_results: int = 10,
    query: str = "",
    type_label: str = "files",
) -> str:
    """
    List files from Drive. Optionally filter by mime_type (e.g. Google Docs, Google Sheets).
    Returns id, name, and link so BMO can reference them or pass id to get_doc_content/get_sheet_data.
    """
    service = _get_drive_service()
    if not service:
        return not_signed_in_message("Google Drive")
    try:
        q_parts = ["trashed = false"]
        if mime_type:
            q_parts.append(f"mimeType = '{mime_type}'")
        if query.strip():
            # Escape single quotes for Drive query
            q_esc = query.strip().replace("'", "\\'")
            q_parts.append(f"fullText contains '{q_esc}'")
        q = " and ".join(q_parts)
        result = service.files().list(
            q=q,
            pageSize=min(max_results, 50),
            fields="files(id, name, webViewLink, mimeType)",
            orderBy="modifiedTime desc",
        ).execute()
        files = result.get("files") or []
        if not files:
            return f"No {type_label} found."
        lines = []
        for f in files:
            name = f.get("name") or "Untitled"
            fid = f.get("id") or ""
            link = f.get("webViewLink") or ""
            lines.append(f"- ID: {fid} | Name: {name}\n  Link: {link}")
        return f"Recent {type_label}:\n" + "\n".join(lines)
    except HttpError as e:
        return f"Drive error: {e.reason or str(e)}"
    except Exception as e:
        return f"Failed to list files: {e}"
