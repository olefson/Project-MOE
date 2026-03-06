"""Stub tool implementations. Replace with real APIs in later phases."""

import os
from typing import Any

from openai import OpenAI

from memory import store_memory as memory_store, forget_memory as memory_forget, update_memory as memory_update

from tools.calendar import create_event as calendar_create_event
from tools.gmail import list_emails as gmail_list_emails, get_email as gmail_get_email, send_email as gmail_send_email
from tools.docs import list_docs as docs_list_docs, get_doc_content as docs_get_doc_content, create_doc as docs_create_doc
from tools.sheets import list_sheets as sheets_list_sheets, get_sheet_data as sheets_get_sheet_data
from tools.hue import (
    set_lights as hue_set_lights,
    list_lights as hue_list_lights,
    list_rooms as hue_list_rooms,
    list_scenes as hue_list_scenes,
)


def add_calendar_event(title: str, when: str, description: str = "") -> str:
    """Add an event to the user's Google Calendar."""
    return calendar_create_event(title=title, when=when, description=description or "")


def list_emails(max_results: int = 10, query: str = "") -> str:
    """List recent Gmail emails (subject, from, date, snippet). Use get_email to read one and summarize."""
    return gmail_list_emails(max_results=max_results, query=query or "")


def get_email(message_id: str) -> str:
    """Get full content of one email by its message ID. Use to read and summarize for the user (e.g. voice)."""
    return gmail_get_email(message_id=message_id)


def send_email(to: str, subject: str, body: str) -> str:
    """Send an email via Gmail."""
    return gmail_send_email(to=to, subject=subject, body=body)


def list_docs(max_results: int = 10, query: str = "") -> str:
    """List recent Google Docs. Use get_doc_content to read one and summarize."""
    return docs_list_docs(max_results=max_results, query=query or "")


def get_doc_content(doc_id: str) -> str:
    """Get full text of a Google Doc. Use to read and summarize for the user (e.g. voice)."""
    return docs_get_doc_content(doc_id=doc_id)


def create_doc(title: str, body: str = "") -> str:
    """Create a new Google Doc with optional initial text."""
    return docs_create_doc(title=title, body=body or "")


def list_sheets(max_results: int = 10, query: str = "") -> str:
    """List recent Google Sheets. Use get_sheet_data to read one and summarize."""
    return sheets_list_sheets(max_results=max_results, query=query or "")


def get_sheet_data(spreadsheet_id: str, range_notation: str = "") -> str:
    """Get cell data from a Google Sheet (A1 notation range). Use to read and summarize for the user (e.g. voice)."""
    return sheets_get_sheet_data(spreadsheet_id=spreadsheet_id, range_notation=range_notation or "")


def web_search(query: str) -> str:
    """Stub: search the web. Real impl in Phase 4 (SerpAPI)."""
    return f"[STUB] Would search for: “{query}”. No real results yet."


def send_notification(message: str) -> str:
    """Stub: send text notification. Real impl in Phase 5 (Telegram)."""
    return f"[STUB] Would send notification: “{message}”."


def set_lights(
    action: str,
    room_name: str | None = None,
    scene_name: str | None = None,
    color: str | None = None,
    brightness: float | None = None,
    **kwargs: Any,
) -> str:
    """Control Philips Hue lights: on/off, color, or scene (e.g. cozy, bright)."""
    return hue_set_lights(
        action=action,
        room_name=room_name,
        scene_name=scene_name,
        color=color,
        brightness=brightness,
        **kwargs,
    )


def list_lights() -> str:
    """List Philips Hue lights (name and id). Use before controlling a specific light."""
    return hue_list_lights()


def list_rooms() -> str:
    """List Philips Hue rooms. Use to target a room by name when controlling lights."""
    return hue_list_rooms()


def list_scenes() -> str:
    """List Philips Hue scenes (e.g. Cozy, Bright). Use to activate a scene by name."""
    return hue_list_scenes()


def _memory_client() -> OpenAI | None:
    key = os.getenv("OPENAI_API_KEY")
    return OpenAI(api_key=key) if key else None


def remember(content: str, source: str = "explicit") -> str:
    """Store a memory (when user says 'remember X' or similar)."""
    client = _memory_client()
    if not client:
        return "[ERROR] OPENAI_API_KEY not set; cannot store memory."
    try:
        memory_store(client, content, source)
        return "I'll remember that."
    except Exception as e:
        return f"[ERROR] Failed to store memory: {e}"


def forget_memory(description_or_id: str) -> str:
    """Forget a memory (when user says 'forget that' or similar)."""
    client = _memory_client()
    if not client:
        return "[ERROR] OPENAI_API_KEY not set; cannot forget memory."
    try:
        memory_forget(client, description_or_id)
        return "I've forgotten that."
    except Exception as e:
        return f"[ERROR] Failed to forget: {e}"


def update_memory(description_or_id: str, new_content: str) -> str:
    """Update a memory (when user says 'actually, it's Y' or similar)."""
    client = _memory_client()
    if not client:
        return "[ERROR] OPENAI_API_KEY not set; cannot update memory."
    try:
        memory_update(client, description_or_id, new_content)
        return "I've updated that."
    except Exception as e:
        return f"[ERROR] Failed to update: {e}"


# Map tool names (as used by the LLM) to functions and their JSON schema for OpenAI.
_TOOLS = {
    "add_calendar_event": {
        "function": add_calendar_event,
        "definition": {
            "type": "function",
            "function": {
                "name": "add_calendar_event",
                "description": "Add an event or reminder to the user's calendar.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Title of the event"},
                        "when": {"type": "string", "description": "When the event occurs (e.g. date/time or natural language)"},
                        "description": {"type": "string", "description": "Optional longer description"},
                    },
                    "required": ["title", "when"],
                },
            },
        },
    },
    "web_search": {
        "function": web_search,
        "definition": {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the web for up-to-date information.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                    },
                    "required": ["query"],
                },
            },
        },
    },
    "send_notification": {
        "function": send_notification,
        "definition": {
            "type": "function",
            "function": {
                "name": "send_notification",
                "description": "Send a text notification to the user (e.g. reminder).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "Message to send"},
                    },
                    "required": ["message"],
                },
            },
        },
    },
    "set_lights": {
        "function": set_lights,
        "definition": {
            "type": "function",
            "function": {
                "name": "set_lights",
                "description": "Control Philips Hue lights: on/off, set color, or activate a scene (e.g. cozy, bright). Use list_rooms or list_scenes to discover names.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "description": "on, off, color, scene, or a mood like cozy, bright, relax, focus"},
                        "room_name": {"type": "string", "description": "Optional room name (e.g. Living room) to target"},
                        "scene_name": {"type": "string", "description": "For action=scene: scene name (e.g. Cozy, Bright)"},
                        "color": {"type": "string", "description": "For on/color: red, blue, green, warm, white, purple, etc."},
                        "brightness": {"type": "number", "description": "Optional brightness 0-100"},
                    },
                    "required": ["action"],
                },
            },
        },
    },
    "list_lights": {
        "function": list_lights,
        "definition": {
            "type": "function",
            "function": {
                "name": "list_lights",
                "description": "List all Philips Hue lights (name and id). Use to see what lights are available.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    },
    "list_rooms": {
        "function": list_rooms,
        "definition": {
            "type": "function",
            "function": {
                "name": "list_rooms",
                "description": "List Philips Hue rooms. Use to target a room by name when controlling lights.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    },
    "list_scenes": {
        "function": list_scenes,
        "definition": {
            "type": "function",
            "function": {
                "name": "list_scenes",
                "description": "List Philips Hue scenes (e.g. Cozy, Bright). Use to activate a scene by name with set_lights.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    },
    "store_memory": {
        "function": remember,
        "definition": {
            "type": "function",
            "function": {
                "name": "store_memory",
                "description": "Store something the user asked you to remember (e.g. 'remember that my name is X', 'don't forget I like Y').",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "The fact or content to remember"},
                        "source": {"type": "string", "description": "Usually 'explicit' when user asked to remember"},
                    },
                    "required": ["content"],
                },
            },
        },
    },
    "forget_memory": {
        "function": forget_memory,
        "definition": {
            "type": "function",
            "function": {
                "name": "forget_memory",
                "description": "Forget a memory when the user says 'forget that', 'don't remember X', or similar.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "description_or_id": {"type": "string", "description": "What to forget (description or memory id)"},
                    },
                    "required": ["description_or_id"],
                },
            },
        },
    },
    "update_memory": {
        "function": update_memory,
        "definition": {
            "type": "function",
            "function": {
                "name": "update_memory",
                "description": "Update a memory when the user corrects you (e.g. 'actually my name is Z', 'change that to Y').",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "description_or_id": {"type": "string", "description": "Which memory to update (description or id)"},
                        "new_content": {"type": "string", "description": "The corrected or new content"},
                    },
                    "required": ["description_or_id", "new_content"],
                },
            },
        },
    },
    "list_emails": {
        "function": list_emails,
        "definition": {
            "type": "function",
            "function": {
                "name": "list_emails",
                "description": "List recent Gmail emails (subject, from, date, snippet). Use to find emails; then use get_email to read one and summarize for the user.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "max_results": {"type": "integer", "description": "Max number of emails to list (default 10)"},
                        "query": {"type": "string", "description": "Optional Gmail search (e.g. is:unread, from:someone)"},
                    },
                    "required": [],
                },
            },
        },
    },
    "get_email": {
        "function": get_email,
        "definition": {
            "type": "function",
            "function": {
                "name": "get_email",
                "description": "Get full content of one email by message ID. Use to read the email and summarize it for the user (e.g. on voice).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message_id": {"type": "string", "description": "Gmail message ID from list_emails"},
                    },
                    "required": ["message_id"],
                },
            },
        },
    },
    "send_email": {
        "function": send_email,
        "definition": {
            "type": "function",
            "function": {
                "name": "send_email",
                "description": "Send an email via Gmail.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "description": "Recipient email address"},
                        "subject": {"type": "string", "description": "Subject line"},
                        "body": {"type": "string", "description": "Plain text body"},
                    },
                    "required": ["to", "subject", "body"],
                },
            },
        },
    },
    "list_docs": {
        "function": list_docs,
        "definition": {
            "type": "function",
            "function": {
                "name": "list_docs",
                "description": "List recent Google Docs. Use get_doc_content to read one and summarize for the user.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "max_results": {"type": "integer", "description": "Max number of docs to list (default 10)"},
                        "query": {"type": "string", "description": "Optional search text in doc name/content"},
                    },
                    "required": [],
                },
            },
        },
    },
    "get_doc_content": {
        "function": get_doc_content,
        "definition": {
            "type": "function",
            "function": {
                "name": "get_doc_content",
                "description": "Get full text of a Google Doc by id. Use to read the doc and summarize for the user (e.g. on voice).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "doc_id": {"type": "string", "description": "Google Doc ID from list_docs"},
                    },
                    "required": ["doc_id"],
                },
            },
        },
    },
    "create_doc": {
        "function": create_doc,
        "definition": {
            "type": "function",
            "function": {
                "name": "create_doc",
                "description": "Create a new Google Doc with optional initial text.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Document title"},
                        "body": {"type": "string", "description": "Optional initial text"},
                    },
                    "required": ["title"],
                },
            },
        },
    },
    "list_sheets": {
        "function": list_sheets,
        "definition": {
            "type": "function",
            "function": {
                "name": "list_sheets",
                "description": "List recent Google Sheets. Use get_sheet_data to read one and summarize for the user.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "max_results": {"type": "integer", "description": "Max number of sheets to list (default 10)"},
                        "query": {"type": "string", "description": "Optional search text"},
                    },
                    "required": [],
                },
            },
        },
    },
    "get_sheet_data": {
        "function": get_sheet_data,
        "definition": {
            "type": "function",
            "function": {
                "name": "get_sheet_data",
                "description": "Get cell data from a Google Sheet by id and optional range (A1 notation). Use to read and summarize for the user (e.g. on voice).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "spreadsheet_id": {"type": "string", "description": "Google Sheet ID from list_sheets"},
                        "range_notation": {"type": "string", "description": "Optional A1 range (e.g. Sheet1!A1:D10)"},
                    },
                    "required": ["spreadsheet_id"],
                },
            },
        },
    },
}


def get_tool_definitions() -> list[dict]:
    """Return OpenAI-compatible tool definitions for chat completion."""
    return [t["definition"] for t in _TOOLS.values()]


def run_tool(name: str, arguments: dict) -> str:
    """Execute a tool by name with the given arguments. Returns result string."""
    if name not in _TOOLS:
        return f"[ERROR] Unknown tool: {name}"
    fn = _TOOLS[name]["function"]
    try:
        if name == "set_lights":
            return fn(
                action=arguments.get("action", ""),
                room_name=arguments.get("room_name"),
                scene_name=arguments.get("scene_name"),
                color=arguments.get("color"),
                brightness=arguments.get("brightness"),
            )
        # Pass only arguments the stub expects; ignore extra keys from the LLM.
        return fn(**{k: v for k, v in arguments.items() if k in _TOOLS[name]["definition"]["function"]["parameters"].get("properties", {})})
    except TypeError as e:
        return f"[ERROR] Tool {name} bad args: {e}"
    except Exception as e:
        return f"[ERROR] Tool {name} failed: {e}"
