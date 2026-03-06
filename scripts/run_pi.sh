#!/usr/bin/env bash
# Run the assistant on Raspberry Pi with face and TTS.
# Usage: from Project-MOE: ./scripts/run_pi.sh
# Or: bash scripts/run_pi.sh

set -e
cd "$(dirname "$0")/.."

# Optional: use framebuffer if no X11 (Pi OS Lite)
# export SDL_VIDEODRIVER=kmsdrm

if [ -d ".venv" ]; then
  source .venv/bin/activate
fi

export PMO_FACE=1
export PMO_TTS=1

exec python main.py
