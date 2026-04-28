"""
Weather via Open-Meteo (no API key). Optional: PMO_LAT, PMO_LON or PMO_WEATHER_LOCATION in .env.
"""
import os
import urllib.parse
import urllib.request
import json
from pathlib import Path

# Optional .env load so default location works without extra setup.
try:
    from dotenv import load_dotenv
    _root = Path(__file__).resolve().parent.parent
    load_dotenv(_root / ".env")
except Exception:
    pass

OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_GEO = "https://geocoding-api.open-meteo.com/v1/search"

# WMO weather codes mapped to short TTS-friendly descriptions.
_WEATHER_DESC = {
    0: "clear",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "foggy",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "drizzle",
    55: "dense drizzle",
    61: "slight rain",
    63: "rain",
    65: "heavy rain",
    71: "slight snow",
    73: "snow",
    75: "heavy snow",
    80: "slight rain showers",
    81: "rain showers",
    82: "heavy rain showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}


def _get_default_coords() -> tuple[float, float]:
    lat_s = os.getenv("PMO_LAT", "").strip()
    lon_s = os.getenv("PMO_LON", "").strip()
    if lat_s and lon_s:
        try:
            return float(lat_s), float(lon_s)
        except ValueError:
            pass
    # Fallback location is Tampa, Florida.
    return 27.9506, -82.4572


def _geocode(location: str) -> tuple[float, float] | None:
    if not location or not location.strip():
        return None
    q = urllib.parse.urlencode({"name": location.strip(), "count": "1"})
    url = f"{OPEN_METEO_GEO}?{q}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return None
    results = data.get("results") or []
    if not results:
        return None
    r = results[0]
    return float(r["latitude"]), float(r["longitude"])


def get_weather(location: str = "") -> str:
    """
    Get current weather. If location is empty, use PMO_LAT/PMO_LON or default (Tampa, Florida).
    Otherwise resolve location (e.g. city name) via geocoding and return current conditions.
    """
    if location and location.strip():
        coords = _geocode(location)
        if coords is None:
            return f"[ERROR] Could not find location: “{location}”. Try a city name or leave empty for default."
        lat, lon = coords
        label = location.strip()
    else:
        lat, lon = _get_default_coords()
        label = os.getenv("PMO_WEATHER_LOCATION", "").strip() or "Tampa, Florida"

    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,precipitation",
    }
    q = urllib.parse.urlencode(params)
    url = f"{OPEN_METEO_FORECAST}?{q}"
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        return f"[ERROR] Weather request failed: {e}"
    except Exception as e:
        return f"[ERROR] Weather: {e}"

    cur = data.get("current")
    if not cur:
        return "[ERROR] No current weather in response."

    temp = cur.get("temperature_2m")
    unit = (data.get("current_units") or {}).get("temperature_2m", "°C")
    humidity = cur.get("relative_humidity_2m")
    code = cur.get("weather_code", 0)
    wind = cur.get("wind_speed_10m")
    wind_unit = (data.get("current_units") or {}).get("wind_speed_10m", "km/h")
    precip = cur.get("precipitation", 0)

    desc = _WEATHER_DESC.get(int(code), "unknown")
    parts = [f"{label}: {desc}, {temp} {unit}"]
    if humidity is not None:
        parts.append(f"humidity {humidity}%")
    if wind is not None:
        parts.append(f"wind {wind} {wind_unit}")
    if precip and float(precip) > 0:
        parts.append(f"precipitation {precip} mm")
    return ". ".join(parts)
