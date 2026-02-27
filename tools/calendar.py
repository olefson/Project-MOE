"""
Google Calendar API: create events. Uses token.json from scripts/auth_google.py.
"""
import os
from datetime import datetime, timedelta
from pathlib import Path

from dateutil import parser as dateutil_parser
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from tools.google_auth import get_credentials, not_signed_in_message

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CALENDAR_ID = "primary"


def get_calendar_service():
    """Build Calendar API v3 service. Returns None if not authenticated."""
    creds = get_credentials()
    if not creds:
        return None
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _ensure_tz(dt: datetime) -> datetime:
    """If naive, assume local timezone."""
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=datetime.now().astimezone().tzinfo)


def parse_when(when_str: str, default_duration_hours: float = 1.0) -> tuple[datetime, datetime] | None:
    """
    Parse natural language or ISO when into (start, end) in local time.
    Uses current date/time as reference so "tomorrow", "in an hour", "next Friday" resolve correctly.
    If only a date is given, start is 9:00 local and end is start + default_duration_hours.
    """
    if not (when_str or when_str.strip()):
        return None
    try:
        now = datetime.now().astimezone()
        parsed = dateutil_parser.parse(when_str.strip(), default=now)
        start = _ensure_tz(parsed)
        # If no time was specified (midnight), assume 9:00
        if start.hour == 0 and start.minute == 0:
            start = start.replace(hour=9, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=default_duration_hours)
        return (start, end)
    except (ValueError, TypeError):
        return None


def create_event(
    title: str,
    when: str,
    description: str = "",
    calendar_id: str | None = None,
) -> str:
    """
    Add an event to Google Calendar. Returns a human-readable success or error message.
    """
    service = get_calendar_service()
    if not service:
        return not_signed_in_message("Google Calendar")

    start_end = parse_when(when)
    if not start_end:
        return f"I couldn't understand the time '{when}'. Try something like 'tomorrow at 2pm' or 'March 15 at 10:00'."

    start_dt, end_dt = start_end
    cal_id = calendar_id or os.getenv("GOOGLE_CALENDAR_ID", DEFAULT_CALENDAR_ID)

    event_body = {
        "summary": title,
        "description": description or "",
        "start": {"dateTime": start_dt.isoformat()},
        "end": {"dateTime": end_dt.isoformat()},
    }

    try:
        event = service.events().insert(calendarId=cal_id, body=event_body).execute()
        link = event.get("htmlLink", "")
        start_readable = start_dt.strftime("%A, %B %d at %I:%M %p")
        msg = f"Added “{title}” on {start_readable}."
        if link:
            msg += f" You can open it here: {link}"
        return msg
    except HttpError as e:
        return f"Google Calendar error: {e.reason or str(e)}"
    except Exception as e:
        return f"Failed to add event: {e}"
