"""
One-time Philips Hue bridge setup: create an application key.
Run from Project-MOE: python scripts/setup_hue.py

Official guide (developer login): https://developers.meethue.com/develop/hue-api-v2/getting-started/

1. Ensure your computer is on the same Wi‑Fi as the Hue bridge.
2. Get the bridge IP (Philips Hue app → Settings → Bridge → Network, or use discovery).
3. Run this script with HUE_BRIDGE_IP set, or enter it when prompted.
4. When prompted, press the physical LINK button on the bridge (within ~30 seconds).
5. The script prints HUE_APP_KEY; add it to your .env file.
"""
import os
import sys
import json
import urllib.request
import ssl
from pathlib import Path

# Project-MOE root
ROOT = Path(__file__).resolve().parent.parent


def discover_bridge() -> str | None:
    """Try to find bridge IP via discovery.meethue.com."""
    try:
        req = urllib.request.Request(
            "https://discovery.meethue.com/",
            headers={"Accept": "application/json"},
        )
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
            data = json.loads(resp.read().decode())
            if data and isinstance(data, list) and len(data) > 0:
                return data[0].get("internalipaddress")
    except Exception:
        pass
    return None


def create_app_key(bridge_ip: str, devicetype: str = "bmo_agent#project_moe") -> str | None:
    """POST to bridge /api to create application key. User must press Link button first."""
    url = f"https://{bridge_ip}/api"
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    body = json.dumps({"devicetype": devicetype}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            out = json.loads(resp.read().decode())
            if isinstance(out, list) and len(out) > 0:
                first = out[0]
                if "success" in first and "username" in first["success"]:
                    return first["success"]["username"]
                if "error" in first:
                    desc = first["error"].get("description", first["error"])
                    print(f"Bridge returned error: {desc}")
    except Exception as e:
        print(f"Request failed: {e}")
    return None


def main() -> None:
    load_dotenv = getattr(__import__("dotenv", fromlist=["load_dotenv"]), "load_dotenv", None)
    if load_dotenv:
        load_dotenv(ROOT / ".env")

    ip = os.getenv("HUE_BRIDGE_IP", "").strip() or os.getenv("PHILIPS_HUE_BRIDGE_IP", "").strip()
    if not ip:
        print("Trying to discover bridge...")
        ip = discover_bridge()
    if not ip:
        ip = input("Enter your Hue bridge IP (e.g. 192.168.1.42): ").strip()
    if not ip:
        print("No bridge IP provided. Set HUE_BRIDGE_IP in .env or run again and enter it.")
        sys.exit(1)

    print("\n>>> Press the LINK button on your Hue bridge now (you have ~30 seconds). <<<\n")
    key = create_app_key(ip)
    if not key:
        print("Could not get application key. Make sure you pressed the Link button and try again.")
        sys.exit(1)

    print("Success! Add these to your .env file:\n")
    print(f"HUE_BRIDGE_IP={ip}")
    print(f"HUE_APP_KEY={key}")
    print("\nOptional: set HUE_VERIFY_SSL=false if you get SSL errors (local network only).")


if __name__ == "__main__":
    main()
