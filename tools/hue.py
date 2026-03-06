"""
Philips Hue API v2 (local bridge). Control lights, rooms, and scenes.

Requires: HUE_BRIDGE_IP, HUE_APP_KEY in environment.
To create an app key: run scripts/setup_hue.py (press the bridge Link button when prompted).

Official getting started: https://developers.meethue.com/develop/hue-api-v2/getting-started/
"""

import os
import urllib.request
import urllib.error
import json
import ssl
from pathlib import Path
from typing import Any

# Project root (parent of tools/) – load .env first so Hue works regardless of process cwd
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv
    load_dotenv(_PROJECT_ROOT / ".env")
except Exception:
    pass

# Optional: disable TLS verify for bridges with self-signed certs (local network only)
HUE_VERIFY_SSL = os.getenv("HUE_VERIFY_SSL", "true").lower() in ("1", "true", "yes")


def _hue_config() -> tuple[str, str] | None:
    """Return (base_url, app_key) or None if not configured."""
    ip = os.getenv("HUE_BRIDGE_IP", "").strip() or os.getenv("PHILIPS_HUE_BRIDGE_IP", "").strip()
    key = os.getenv("HUE_APP_KEY", "").strip() or os.getenv("PHILIPS_HUE_APP_KEY", "").strip()
    if not ip or not key:
        return None
    base = f"https://{ip}"
    return (base, key)


def _request(
    method: str,
    path: str,
    app_key: str,
    base_url: str,
    body: dict | None = None,
) -> list[dict] | dict:
    """Send request to Hue bridge. path should start with / (e.g. /clip/v2/resource/light)."""
    url = base_url.rstrip("/") + path
    ctx = ssl.create_default_context()
    if not HUE_VERIFY_SSL:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "hue-application-key": app_key,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            out = json.loads(resp.read().decode())
            return out
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode()
            err_json = json.loads(err_body)
            errors = err_json.get("errors", [])
            if errors:
                msg = "; ".join(
                    str(x.get("description", x))
                    for x in errors
                )
                raise RuntimeError(f"Hue API error: {msg}") from e
        except (ValueError, KeyError):
            pass
        raise RuntimeError(f"Hue API HTTP {e.code}: {e.reason}") from e


def _get(path: str, base_url: str, app_key: str) -> list[dict]:
    """GET a resource and return the data array."""
    out = _request("GET", path, app_key, base_url)
    if isinstance(out, dict) and "data" in out:
        return out["data"]
    return []


def _put(path: str, body: dict, base_url: str, app_key: str) -> list[dict]:
    """PUT to a resource. Returns response data array if present."""
    out = _request("PUT", path, app_key, base_url, body=body)
    if isinstance(out, list):
        return out
    if isinstance(out, dict) and "data" in out:
        return out["data"]
    return []


def not_configured_message() -> str:
    return (
        "Philips Hue is not configured. Set HUE_BRIDGE_IP and HUE_APP_KEY in .env, "
        "then run scripts/setup_hue.py (press the Link button on the bridge when prompted)."
    )


# --- Public API ---


def list_lights() -> str:
    """List all lights (id, metadata.name, on, dimming). For discovery and targeting."""
    cfg = _hue_config()
    if not cfg:
        return not_configured_message()
    base_url, app_key = cfg
    try:
        data = _get("/clip/v2/resource/light", base_url, app_key)
        lines = []
        for item in data:
            mid = item.get("id", "?")
            meta = item.get("metadata", {}) or {}
            name = meta.get("name", "Light")
            on_val = item.get("on", {})
            on = on_val.get("on", False) if isinstance(on_val, dict) else False
            dim = item.get("dimming", {}) or {}
            bri = dim.get("brightness")
            bri_str = f", brightness {bri:.0f}%" if bri is not None else ""
            lines.append(f"- {name} (id: {mid}): on={on}{bri_str}")
        if not lines:
            return "No lights found on the bridge."
        return "Lights:\n" + "\n".join(lines)
    except Exception as e:
        return f"[ERROR] Hue: {e}"


def list_rooms() -> str:
    """List rooms and their grouped_light id (for controlling by room name)."""
    cfg = _hue_config()
    if not cfg:
        return not_configured_message()
    base_url, app_key = cfg
    try:
        rooms = _get("/clip/v2/resource/room", base_url, app_key)
        grouped = _get("/clip/v2/resource/grouped_light", base_url, app_key)
        # grouped_light has owner.rid = room id; room has services with rid = grouped_light id
        rid_to_group = {g["id"]: g for g in grouped if g.get("owner", {}).get("rtype") == "room"}
        room_id_to_group_id = {}
        for g in grouped:
            owner = g.get("owner", {})
            if owner.get("rtype") == "room":
                room_id_to_group_id[owner.get("rid")] = g["id"]
        lines = []
        for r in rooms:
            rid = r.get("id")
            name = (r.get("metadata") or {}).get("name", "Room")
            gid = room_id_to_group_id.get(rid)
            if gid:
                lines.append(f"- {name} (grouped_light_id: {gid})")
            else:
                lines.append(f"- {name} (id: {rid}, no grouped light)")
        if not lines:
            return "No rooms found."
        return "Rooms:\n" + "\n".join(lines)
    except Exception as e:
        return f"[ERROR] Hue: {e}"


def list_scenes() -> str:
    """List scenes (name and id) for activating by name (e.g. cozy, bright)."""
    cfg = _hue_config()
    if not cfg:
        return not_configured_message()
    base_url, app_key = cfg
    try:
        data = _get("/clip/v2/resource/scene", base_url, app_key)
        lines = []
        for item in data:
            mid = item.get("id", "?")
            meta = item.get("metadata", {}) or {}
            name = meta.get("name", "Scene")
            group_rid = (item.get("group", {}) or {}).get("rid")
            lines.append(f"- {name} (id: {mid})")
        if not lines:
            return "No scenes found."
        return "Scenes:\n" + "\n".join(lines)
    except Exception as e:
        return f"[ERROR] Hue: {e}"


def set_light_state(
    light_id: str,
    on: bool | None = None,
    brightness: float | None = None,
    xy: tuple[float, float] | None = None,
) -> str:
    """Set a single light by id. brightness 0-100, xy is (x, y) in 0-1."""
    cfg = _hue_config()
    if not cfg:
        return not_configured_message()
    base_url, app_key = cfg
    body: dict[str, Any] = {}
    if on is not None:
        body["on"] = {"on": on}
    if brightness is not None:
        body["dimming"] = {"brightness": max(1.0, min(100.0, float(brightness)))}
    if xy is not None:
        body["color"] = {"xy": {"x": float(xy[0]), "y": float(xy[1])}}
    if not body:
        return "No state to set (use on, brightness, or color)."
    try:
        _put(f"/clip/v2/resource/light/{light_id}", body, base_url, app_key)
        return f"Light {light_id} updated."
    except Exception as e:
        return f"[ERROR] Hue: {e}"


def set_room_state(
    grouped_light_id: str,
    on: bool | None = None,
    brightness: float | None = None,
    xy: tuple[float, float] | None = None,
) -> str:
    """Set all lights in a room (use grouped_light id from list_rooms)."""
    cfg = _hue_config()
    if not cfg:
        return not_configured_message()
    base_url, app_key = cfg
    body: dict[str, Any] = {"type": "grouped_light"}
    if on is not None:
        body["on"] = {"on": on}
    if brightness is not None:
        body["dimming"] = {"brightness": max(1.0, min(100.0, float(brightness)))}
    if xy is not None:
        body["color"] = {"xy": {"x": float(xy[0]), "y": float(xy[1])}}
    if not body or body == {"type": "grouped_light"}:
        return "No state to set (use on, brightness, or color)."
    try:
        _put(f"/clip/v2/resource/grouped_light/{grouped_light_id}", body, base_url, app_key)
        return f"Room (grouped light {grouped_light_id}) updated."
    except Exception as e:
        return f"[ERROR] Hue: {e}"


def activate_scene(scene_id: str) -> str:
    """Activate a scene by id (from list_scenes)."""
    cfg = _hue_config()
    if not cfg:
        return not_configured_message()
    base_url, app_key = cfg
    try:
        _put(
            f"/clip/v2/resource/scene/{scene_id}",
            {"recall": {"action": "active"}},
            base_url,
            app_key,
        )
        return f"Scene {scene_id} activated."
    except Exception as e:
        return f"[ERROR] Hue: {e}"


# Named colors in CIE xy (approximate)
COLORS: dict[str, tuple[float, float]] = {
    "red": (0.7, 0.3),
    "orange": (0.6, 0.4),
    "yellow": (0.5, 0.5),
    "green": (0.2, 0.7),
    "cyan": (0.15, 0.35),
    "blue": (0.15, 0.05),
    "purple": (0.25, 0.15),
    "pink": (0.4, 0.25),
    "white": (0.32, 0.33),
    "warm": (0.46, 0.41),
    "cozy": (0.5, 0.42),
}


def set_lights(
    action: str,
    room_name: str | None = None,
    scene_name: str | None = None,
    color: str | None = None,
    brightness: float | None = None,
    **kwargs: Any,
) -> str:
    """
    High-level control: on, off, color, scene, or mood (e.g. cozy, bright).
    - action: on | off | color | scene
    - room_name: optional room to target (e.g. Living room); if omitted, first room is used for scene.
    - scene_name: for action=scene, the scene name (e.g. Cozy, Bright)
    - color: for action=color, named color (red, blue, warm, white, etc.) or leave for current
    - brightness: 0-100 optional
    """
    cfg = _hue_config()
    if not cfg:
        return not_configured_message()
    base_url, app_key = cfg
    action = (action or "").strip().lower()

    try:
        # Scene by name: list scenes, find match, activate
        if action in ("scene", "mood", "cozy", "bright", "relax", "focus", "read", "energize"):
            scenes = _get("/clip/v2/resource/scene", base_url, app_key)
            name_to_id: dict[str, str] = {}
            for s in scenes:
                meta = (s.get("metadata") or {})
                n = (meta.get("name") or "").strip()
                if n:
                    name_to_id[n.lower()] = s["id"]
            # Map common words to possible scene names
            scene_lookup = scene_name or action
            scene_id = None
            for key, sid in name_to_id.items():
                if scene_lookup.lower() in key or key in scene_lookup.lower():
                    scene_id = sid
                    break
            if not scene_id and name_to_id:
                scene_id = name_to_id.get(scene_lookup.lower()) or next(iter(name_to_id.values()))
            if scene_id:
                _put(
                    f"/clip/v2/resource/scene/{scene_id}",
                    {"recall": {"action": "active"}},
                    base_url,
                    app_key,
                )
                return f"Activated scene '{scene_lookup or action}'."
            # Fallback: no scene found, try on + brightness/color
            action = "on"

        # On/off by room or all
        if action in ("on", "off"):
            on_val = action == "on"
            body: dict[str, Any] = {"type": "grouped_light", "on": {"on": on_val}}
            if brightness is not None and on_val:
                body["dimming"] = {"brightness": max(1.0, min(100.0, float(brightness)))}
            if color and on_val and color.lower() in COLORS:
                body["color"] = {"xy": {"x": COLORS[color.lower()][0], "y": COLORS[color.lower()][1]}}

            if room_name:
                rooms = _get("/clip/v2/resource/room", base_url, app_key)
                grouped = _get("/clip/v2/resource/grouped_light", base_url, app_key)
                room_id_to_group_id = {}
                for g in grouped:
                    if (g.get("owner") or {}).get("rtype") == "room":
                        room_id_to_group_id[g["owner"]["rid"]] = g["id"]
                group_id = None
                for r in rooms:
                    if (r.get("metadata") or {}).get("name", "").lower() == room_name.lower():
                        group_id = room_id_to_group_id.get(r["id"])
                        break
                if group_id:
                    _put(f"/clip/v2/resource/grouped_light/{group_id}", body, base_url, app_key)
                    return f"Turned {action} in {room_name}."
            # All: use bridge_home grouped_light if available
            grouped = _get("/clip/v2/resource/grouped_light", base_url, app_key)
            bridge_home = next((g for g in grouped if (g.get("owner") or {}).get("rtype") == "bridge_home"), None)
            if bridge_home:
                _put(f"/clip/v2/resource/grouped_light/{bridge_home['id']}", body, base_url, app_key)
                return f"Turned {action} all lights."
            # Fallback: first grouped_light
            if grouped:
                _put(f"/clip/v2/resource/grouped_light/{grouped[0]['id']}", body, base_url, app_key)
                return f"Turned {action} lights."
            return "No grouped lights found to turn on/off."

        # Color only (by room or all)
        if action == "color" and color and color.lower() in COLORS:
            xy = COLORS[color.lower()]
            body = {"type": "grouped_light", "on": {"on": True}, "color": {"xy": {"x": xy[0], "y": xy[1]}}}
            if brightness is not None:
                body["dimming"] = {"brightness": max(1.0, min(100.0, float(brightness)))}
            if room_name:
                rooms = _get("/clip/v2/resource/room", base_url, app_key)
                grouped = _get("/clip/v2/resource/grouped_light", base_url, app_key)
                room_id_to_group_id = {}
                for g in grouped:
                    if (g.get("owner") or {}).get("rtype") == "room":
                        room_id_to_group_id[g["owner"]["rid"]] = g["id"]
                for r in rooms:
                    if (r.get("metadata") or {}).get("name", "").lower() == room_name.lower():
                        gid = room_id_to_group_id.get(r["id"])
                        if gid:
                            _put(f"/clip/v2/resource/grouped_light/{gid}", body, base_url, app_key)
                            return f"Set color to {color} in {room_name}."
            grouped = _get("/clip/v2/resource/grouped_light", base_url, app_key)
            bridge_home = next((g for g in grouped if (g.get("owner") or {}).get("rtype") == "bridge_home"), None)
            target = bridge_home or (grouped[0] if grouped else None)
            if target:
                _put(f"/clip/v2/resource/grouped_light/{target['id']}", body, base_url, app_key)
                return f"Set color to {color}."
            return "No grouped lights found."

        return "Use action: on, off, scene/mood (e.g. cozy, bright), or color (with color name)."
    except Exception as e:
        return f"[ERROR] Hue: {e}"
