"""
Download Piper voice: en_GB-cori-high (cori [high]).
Run once from Project-MOE: python scripts/download_piper_voice.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VOICES_DIR = ROOT / "voices"
VOICE_ID = "en_GB-cori-high"
BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/cori/high"


def main() -> None:
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    onnx_path = VOICES_DIR / f"{VOICE_ID}.onnx"
    json_path = VOICES_DIR / f"{VOICE_ID}.onnx.json"
    if onnx_path.is_file():
        print(f"Voice already present: {onnx_path}")
        return

    try:
        import urllib.request
        onnx_url = f"{BASE_URL}/{VOICE_ID}.onnx"
        json_url = f"{BASE_URL}/{VOICE_ID}.onnx.json"
        print(f"Downloading {VOICE_ID} from Hugging Face...")
        urllib.request.urlretrieve(onnx_url, onnx_path)
        urllib.request.urlretrieve(json_url, json_path)
        print(f"Saved to {VOICES_DIR}")
    except Exception as e:
        print(f"Download failed: {e}", file=sys.stderr)
        print("You can download manually from:", file=sys.stderr)
        print(f"  {BASE_URL}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
