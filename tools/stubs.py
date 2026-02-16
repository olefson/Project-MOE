"""Stub tool implementations. Replace with real APIs in later phases."""

from typing import Any


def add_calendar_event(title: str, when: str, description: str = "") -> str:
    """Stub: add event to calendar. Real impl in Phase 3 (Google Calendar)."""
    return f"[STUB] Would add calendar event: “{title}” at {when}. Description: {description or '(none)'}"


def web_search(query: str) -> str:
    """Stub: search the web. Real impl in Phase 4 (SerpAPI)."""
    return f"[STUB] Would search for: “{query}”. No real results yet."


def send_notification(message: str) -> str:
    """Stub: send text notification. Real impl in Phase 5 (Telegram)."""
    return f"[STUB] Would send notification: “{message}”."


def set_lights(action: str, **kwargs: Any) -> str:
    """Stub: control Philips Hue lights. Real impl in Phase 6."""
    opts = ", ".join(f"{k}={v}" for k, v in kwargs.items()) if kwargs else "none"
    return f"[STUB] Would set lights: action={action}, options=({opts})"


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
                "description": "Control Philips Hue lights (on/off, color, scene).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "description": "e.g. on, off, color, scene, cozy, bright"},
                        "options": {"type": "object", "description": "Optional extra options"},
                    },
                    "required": ["action"],
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
            action = arguments.get("action", "")
            opts = arguments.get("options") or {}
            return fn(action=action, **opts)
        # Pass only arguments the stub expects; ignore extra keys from the LLM.
        return fn(**{k: v for k, v in arguments.items() if k in _TOOLS[name]["definition"]["function"]["parameters"].get("properties", {})})
    except TypeError as e:
        return f"[ERROR] Tool {name} bad args: {e}"
    except Exception as e:
        return f"[ERROR] Tool {name} failed: {e}"
