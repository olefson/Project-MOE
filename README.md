# MOE / PMO – Personal Agentic Desktop Assistant

Agent loop: **Input → Reason → Tool (stubs) → Memory (placeholder) → Output.**

## Quick start

### 1. Backend (API)

From the **Project-MOE** root, with your Python venv activated:

```bash
pip install -r requirements.txt
uvicorn api:app --reload --port 8000
```

- API: **http://localhost:8000**
- Interactive docs: **http://localhost:8000/docs**

### 2. Frontend (Chat UI)

From **Project-MOE/Frontend**:

```bash
npm install
npm run dev
```

- App: **http://localhost:5173**

### 3. CLI (optional)

Terminal-only chat (no API):

```bash
python main.py
```

## Chat API

- **POST /chat**  
  - Body: `{ "message": "user text", "session_id"?: "uuid" }`  
  - Response: `{ "reply": "assistant text", "session_id": "uuid" }`  
- The UI stores `session_id` in `localStorage` (key: `moe_session_id`) and sends it with each request so conversation context is kept across refreshes.

## Voice input

- The app supports **Record** and **Submit** for voice: record with the microphone, then submit the audio. The backend transcribes with **OpenAI Whisper** and runs the same chat/session flow, so text and voice share one conversation.
- **POST /audio** (multipart): `file` (audio), optional `session_id`. Response: `{ "reply", "session_id", "transcript" }`.

## Raspberry Pi preparation

To run on a **Raspberry Pi** (e.g. Pi 5) with the 800×480 face and Piper TTS:

1. See **Documents/PI_PREP.md** for hardware, OS, display 800×480, and `.env` setup.
2. On the Pi: `pip install -r requirements.txt`, run `python scripts/download_piper_voice.py` once, then:
   - `python main.py` with `PMO_FACE=1` and `PMO_TTS=1` in `.env`, or
   - `./scripts/run_pi.sh` (enables face + TTS).

On the Pi, PMO can control **volume** (get/set/up/down/mute) and **reboot** (with confirmation and `PMO_ALLOW_REBOOT=1`). With **PMO_VOICE_ONLY=1** the mic is always on: speak then pause ~1 s to submit (VAD detects end-of-utterance). With **PMO_WAKE_WORD=1** and **PICOVOICE_ACCESS_KEY**, say "Bumblebee" then your question. See **Documents/PI_PREP.md** for device control and voice/wake-word setup.

Next (Stretch 3): wake word and boot-on-startup — see project plan.

---

## Layout

- **Backend:** `main.py` (CLI loop), `api.py` (FastAPI, POST /chat, POST /audio with Whisper, session store, memory hook), `tools/` (stub tools, Pi volume/reboot in `pi_control.py`), `tts.py` (Piper), `face.py` (Pygame face).
- **Frontend:** `Frontend/` – Vite + React + Tailwind + shadcn/ui; chat UI (text + voice Record/Submit) that calls the API.
