"""
Google Docs API: list, read, and create documents. For voice: BMO can read docs and summarize.
"""
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from tools.google_auth import get_credentials, not_signed_in_message
from tools.drive import _get_drive_service, list_files

DOCS_MIME = "application/vnd.google-apps.document"


def _get_docs_service():
    creds = get_credentials()
    if not creds:
        return None
    return build("docs", "v1", credentials=creds, cache_discovery=False)


def _extract_text_from_doc(doc: dict) -> str:
    """Traverse document body and concatenate all text from textRun elements."""
    body = doc.get("body") or {}
    content = body.get("content") or []
    parts = []

    def extract_from_element(el: dict) -> None:
        if "paragraph" in el:
            for elem in el["paragraph"].get("elements") or []:
                if "textRun" in elem and elem["textRun"].get("content"):
                    parts.append(elem["textRun"]["content"])
        if "table" in el:
            for row in el["table"].get("tableRows") or []:
                for cell in row.get("tableCells") or []:
                    for c in cell.get("content") or []:
                        extract_from_element(c)
        if "tableOfContents" in el:
            for elem in (el["tableOfContents"].get("content") or []):
                extract_from_element(elem)

    for el in content:
        extract_from_element(el)

    return "".join(parts).strip().replace("\n", "\n") or "(Empty document)"


def list_docs(max_results: int = 10, query: str = "") -> str:
    """List recent Google Docs. Returns id, name, and link so BMO can reference them."""
    return list_files(
        mime_type=DOCS_MIME,
        max_results=max_results,
        query=query,
        type_label="Google Docs",
    )


def get_doc_content(doc_id: str) -> str:
    """
    Get full text content of a Google Doc. Returns the document body so BMO can read and summarize
    for the user (e.g. on a voice assistant).
    """
    service = _get_docs_service()
    if not service:
        return not_signed_in_message("Google Docs")
    try:
        doc = service.documents().get(documentId=doc_id.strip()).execute()
        title = doc.get("title") or "Untitled"
        text = _extract_text_from_doc(doc)
        return f"Document: {title}\n\n{text}"
    except HttpError as e:
        return f"Google Docs error: {e.reason or str(e)}"
    except Exception as e:
        return f"Failed to get document: {e}"


def create_doc(title: str, body: str = "") -> str:
    """Create a new Google Doc with optional initial text. Returns the doc link."""
    drive = _get_drive_service()
    if not drive:
        return not_signed_in_message("Google Drive")
    docs_service = _get_docs_service()
    if not docs_service:
        return not_signed_in_message("Google Docs")
    try:
        metadata = {"name": title.strip() or "Untitled", "mimeType": DOCS_MIME}
        file = drive.files().create(body=metadata, fields="id, webViewLink").execute()
        doc_id = file.get("id")
        link = file.get("webViewLink") or ""
        if body.strip():
            docs_service.documents().batchUpdate(
                documentId=doc_id,
                body={
                    "requests": [
                        {
                            "insertText": {
                                "location": {"index": 1},
                                "text": body.strip(),
                            }
                        }
                    ]
                },
            ).execute()
        return f"Created document \"{title or 'Untitled'}\". You can open it here: {link}"
    except HttpError as e:
        return f"Google Docs/Drive error: {e.reason or str(e)}"
    except Exception as e:
        return f"Failed to create document: {e}"
