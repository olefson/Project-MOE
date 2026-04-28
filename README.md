# MOE / PMO - Personal Agentic Desktop Assistant

PMO is a local-first assistant with this loop:
**Input -> Reason -> Tool -> Memory -> Output**

This README focuses on one thing: getting the app running cleanly.

## Run Paths

- **Web app (recommended):** FastAPI backend + Vite frontend chat UI
- **CLI mode (optional):** terminal-only chat loop via `main.py`
- **Pi mode (optional):** face + TTS + voice-first setup on Raspberry Pi

## Prerequisites

- Python 3.10+
- Node.js 18+ and npm
- An OpenAI API key

## 1) Project Setup

From the `Project-MOE` root:

```bash
pip install -r requirements.txt
```

Create your env file:

```bash
cp .env.example .env
```

Then set at least:

- `OPENAI_API_KEY=...`

If you're on Windows PowerShell and `cp` doesn't work, use:

```powershell
Copy-Item .env.example .env
```

## 2) Start the Backend API

From `Project-MOE`:

```bash
uvicorn api:app --reload --port 8000
```

Backend URLs:

- API base: `http://localhost:8000`
- Swagger docs: `http://localhost:8000/docs`

## 3) Start the Frontend

Open a second terminal, then:

```bash
cd Frontend
npm install
npm run dev
```

Frontend URL:

- App: `http://localhost:5173`

## 4) Verify the App

1. Open `http://localhost:5173`
2. Send a text message
3. Confirm you receive a reply
4. (Optional) Try voice `Record` + `Submit`

The UI stores a `session_id` in `localStorage` (`moe_session_id`) so chat context survives refreshes.

## CLI Mode (Optional)

If you want terminal-only chat (no web UI), run:

```bash
python main.py
```

## Voice Input (Web/API)

- The web app supports **Record** and **Submit**.
- Backend transcription uses OpenAI Whisper and shares the same session flow as text chat.

Endpoint:

- `POST /audio` (multipart)
  - Input: `file` (audio), optional `session_id`
  - Output: `{ "reply", "session_id", "transcript" }`

## Chat API Reference

- `POST /chat`
  - Body: `{ "message": "user text", "session_id"?: "uuid" }`
  - Response: `{ "reply": "assistant text", "session_id": "uuid" }`

## API Onboarding Automation (Optional)

PMO can run provider onboarding flows (discover docs, attempt signup, poll Gmail, extract keys, update `.env`).

Extra setup:

```bash
python -m playwright install chromium
```

Required env flags:

- `PMO_API_ONBOARDING_ENABLED=1`
- `PMO_API_ONBOARDING_EMAIL=<your signup email>`
- Optional verbose secret logs: `PMO_API_ONBOARDING_FULL_SECRET_LOGS=1`

Use via chat:

- `Sign up for <provider> API and install the key`

Or endpoint:

- `POST /onboard-api`
  - Response: `{ "report": "stage-by-stage onboarding report" }`
  - Default log path: `logs/api_onboarding.log` (override with `PMO_API_ONBOARDING_LOG_PATH`)

## Raspberry Pi Mode (Optional)

For Pi-specific setup (display, audio, wake word, device config), use:

- `Documents/PI_PREP.md`

Quick Pi run notes:

- Install deps: `pip install -r requirements.txt`
- Ensure Piper voice file exists: `voices/en_GB-cori-high.onnx`
- Run with face + TTS using either:
  - `python main.py` with `PMO_FACE=1` and `PMO_TTS=1`, or
  - `./scripts/run_pi.sh`

On Pi, PMO supports:

- Volume controls (get/set/up/down/mute)
- Reboot flow (with confirmation + `PMO_ALLOW_REBOOT=1`)
- Voice-only mode: `PMO_VOICE_ONLY=1`
- Wake word mode: `PMO_WAKE_WORD=1` + `PICOVOICE_ACCESS_KEY`

## Code Source Declaration

This project was developed by me, and I used Cursor (AI coding assistant) to help with targeted refactors and some implementation cleanup where needed.

## Project Layout

- **Backend:** `main.py`, `api.py`, `tools/`, `memory/`, `tts.py`, `face.py`
- **Frontend:** `Frontend/` (Vite + React chat UI)
