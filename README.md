# MOE / BMO – Personal Agentic Desktop Assistant

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

## Layout

- **Backend:** `main.py` (CLI loop), `api.py` (FastAPI, POST /chat, POST /audio with Whisper, session store, memory hook), `tools/` (stub tools).
- **Frontend:** `Frontend/` – Vite + React + Tailwind + shadcn/ui; chat UI (text + voice Record/Submit) that calls the API.
