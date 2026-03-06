"""
Gmail API: list, read, and send email. For voice: PMO can read emails and summarize.
"""
import base64
import re
from email.mime.text import MIMEText

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from tools.google_auth import get_credentials, not_signed_in_message


def _get_gmail_service():
    creds = get_credentials()
    if not creds:
        return None
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _decode_body(payload: dict) -> str:
    """Extract plain text body from Gmail message payload."""
    if payload.get("body", {}).get("data"):
        try:
            data = payload["body"]["data"]
            decoded = base64.urlsafe_b64decode(data.encode("ASCII"))
            return decoded.decode("utf-8", errors="replace").strip()
        except Exception:
            pass
    if payload.get("parts"):
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                try:
                    data = part["body"]["data"]
                    decoded = base64.urlsafe_b64decode(data.encode("ASCII"))
                    return decoded.decode("utf-8", errors="replace").strip()
                except Exception:
                    continue
            if part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
                try:
                    data = part["body"]["data"]
                    decoded = base64.urlsafe_b64decode(data.encode("ASCII"))
                    html = decoded.decode("utf-8", errors="replace")
                    # Crude strip tags for LLM
                    text = re.sub(r"<[^>]+>", " ", html)
                    text = re.sub(r"\s+", " ", text).strip()
                    if text:
                        return text
                except Exception:
                    continue
    return ""


def _get_header(headers: list[dict], name: str) -> str:
    for h in headers or []:
        if (h.get("name") or "").lower() == name.lower():
            return (h.get("value") or "").strip()
    return ""


def list_emails(max_results: int = 10, query: str = "") -> str:
    """
    List recent emails. Returns a summary (subject, from, date, snippet) so PMO can read/summarize.
    query: optional Gmail search (e.g. "is:unread", "from:someone@example.com").
    """
    service = _get_gmail_service()
    if not service:
        return not_signed_in_message("Gmail")
    try:
        result = service.users().messages().list(
            userId="me",
            maxResults=min(max_results, 50),
            q=query.strip() if query else None,
        ).execute()
        messages = result.get("messages") or []
        if not messages:
            return "No emails found."
        ids = [m["id"] for m in messages]
        lines = []
        for msg_id in ids:
            msg = service.users().messages().get(userId="me", id=msg_id, format="metadata", metadataHeaders=["Subject", "From", "Date"]).execute()
            payload = msg.get("payload") or {}
            headers = payload.get("headers") or []
            subject = _get_header(headers, "Subject")
            from_ = _get_header(headers, "From")
            date = _get_header(headers, "Date")
            snippet = (msg.get("snippet") or "").replace("\n", " ")[:200]
            lines.append(f"- ID: {msg_id} | From: {from_} | Date: {date} | Subject: {subject}\n  Snippet: {snippet}")
        return "Recent emails:\n" + "\n".join(lines)
    except HttpError as e:
        return f"Gmail error: {e.reason or str(e)}"
    except Exception as e:
        return f"Failed to list emails: {e}"


def get_email(message_id: str) -> str:
    """
    Get full content of one email by message ID. Returns subject, from, date, and body
    so PMO can read and summarize for the user (e.g. on a voice assistant).
    """
    service = _get_gmail_service()
    if not service:
        return not_signed_in_message("Gmail")
    try:
        msg = service.users().messages().get(userId="me", id=message_id.strip(), format="full").execute()
        payload = msg.get("payload") or {}
        headers = payload.get("headers") or []
        subject = _get_header(headers, "Subject")
        from_ = _get_header(headers, "From")
        date = _get_header(headers, "Date")
        body = _decode_body(payload)
        if not body:
            body = msg.get("snippet") or "(No body content)"
        return f"From: {from_}\nDate: {date}\nSubject: {subject}\n\n{body}"
    except HttpError as e:
        return f"Gmail error: {e.reason or str(e)}"
    except Exception as e:
        return f"Failed to get email: {e}"


def send_email(to: str, subject: str, body: str) -> str:
    """Send an email. to: recipient address; subject: subject line; body: plain text body."""
    service = _get_gmail_service()
    if not service:
        return not_signed_in_message("Gmail")
    try:
        message = MIMEText(body)
        message["to"] = to.strip()
        message["subject"] = subject.strip()
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ASCII")
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return f"Email sent to {to} with subject \"{subject[:50]}{'...' if len(subject) > 50 else ''}\"."
    except HttpError as e:
        return f"Gmail error: {e.reason or str(e)}"
    except Exception as e:
        return f"Failed to send email: {e}"
