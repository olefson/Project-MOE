"""
MOE/BMO HTTP API – session-aware chat endpoint + voice (Whisper).
Run: uvicorn api:app --reload --port 8000
"""
import io
import os
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pydantic import BaseModel, Field

from main import SYSTEM_PROMPT, run_agent_turn
from memory import init_db, get_relevant, format_context, extract_and_store_memories, store_memory
from tools import get_tool_definitions

load_dotenv()

# Ensure memory DB exists at startup
init_db()

SESSION_SUMMARY_INTERVAL = 10  # Every N messages, store a session summary

app = FastAPI(title="MOE API", description="Chat with BMO agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session store: session_id -> list of messages (same shape as main.py)
session_store: dict[str, list[dict]] = {}


def _run_session_summary(client, messages: list[dict]) -> None:
    """Summarize last 5–10 user/assistant pairs and store as one memory."""
    pairs = []
    for i, m in enumerate(messages):
        if m.get("role") == "user" and m.get("content"):
            pairs.append(("user", m["content"]))
        elif m.get("role") == "assistant" and m.get("content"):
            pairs.append(("assistant", m["content"]))
    if len(pairs) < 2:
        return
    # Last 10 messages (5 exchanges) or fewer
    recent = pairs[-10:] if len(pairs) >= 10 else pairs
    block = "\n".join(f"{r}: {c[:200]}" for r, c in recent)
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": f"Summarize this conversation in 1–2 sentences for future context.\n\n{block}"}
            ],
            max_tokens=150,
        )
        summary = (r.choices[0].message.content or "").strip()
        if summary:
            store_memory(client, summary, "summary")
    except Exception:
        pass


def get_memory_context(client, session_id: str, user_message: str, top_k: int = 7):
    """
    Retrieve relevant long-term memories for this message; return (context_string, used_entries).
    used_entries: list of dicts with id, content, source for reasoning_used.
    """
    entries = get_relevant(client, user_message, top_k=top_k)
    context_str = format_context(entries)
    used = [{"id": e.get("id"), "content": e.get("content", ""), "source": e.get("source", "")} for e in entries]
    return context_str, used


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    reasoning_used: dict | None = None


class AudioResponse(BaseModel):
    reply: str
    session_id: str
    transcript: str | None = None
    reasoning_used: dict | None = None


class ErrorResponse(BaseModel):
    detail: str


@app.post("/chat", response_model=ChatResponse, responses={500: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
def chat(request: ChatRequest) -> ChatResponse:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")

    session_id = request.session_id or str(uuid.uuid4())
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message cannot be empty")

    # Load or create conversation
    messages = session_store.get(session_id)
    if not messages:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    client = OpenAI(api_key=api_key)
    context_str, used_entries = get_memory_context(client, session_id, message)
    if context_str:
        messages[0] = {
            "role": "system",
            "content": SYSTEM_PROMPT + "\n\n[Relevant memory]:\n" + context_str,
        }
    else:
        messages[0] = {"role": "system", "content": SYSTEM_PROMPT}

    messages.append({"role": "user", "content": message})

    try:
        tools = get_tool_definitions()
        reply, updated_messages, tool_calls_made = run_agent_turn(client, messages, tools)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}") from e

    session_store[session_id] = updated_messages
    try:
        extract_and_store_memories(client, message, reply)
    except Exception:
        pass
    if len(updated_messages) >= 11 and (len(updated_messages) - 1) % SESSION_SUMMARY_INTERVAL == 0:
        try:
            _run_session_summary(client, updated_messages)
        except Exception:
            pass
    reasoning = {"memories": used_entries, "tool_calls": tool_calls_made}
    return ChatResponse(reply=reply, session_id=session_id, reasoning_used=reasoning)


@app.post(
    "/audio",
    response_model=AudioResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
async def audio(
    file: UploadFile = File(...),
    session_id: str | None = Form(None),
) -> AudioResponse:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="No audio file or empty file")

    session_id = session_id or str(uuid.uuid4())

    # Whisper transcription
    try:
        client = OpenAI(api_key=api_key)
        f = io.BytesIO(content)
        f.name = file.filename or "audio.webm"
        transcript_response = client.audio.transcriptions.create(model="whisper-1", file=f)
        transcript = (transcript_response.text or "").strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription error: {str(e)}") from e

    if not transcript:
        raise HTTPException(status_code=400, detail="No speech detected in audio")

    # Same session/agent flow as /chat
    messages = session_store.get(session_id)
    if not messages:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    context_str, used_entries = get_memory_context(client, session_id, transcript)
    if context_str:
        messages[0] = {
            "role": "system",
            "content": SYSTEM_PROMPT + "\n\n[Relevant memory]:\n" + context_str,
        }
    else:
        messages[0] = {"role": "system", "content": SYSTEM_PROMPT}

    messages.append({"role": "user", "content": transcript})

    try:
        tools = get_tool_definitions()
        reply, updated_messages, tool_calls_made = run_agent_turn(client, messages, tools)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}") from e

    session_store[session_id] = updated_messages
    try:
        extract_and_store_memories(client, transcript, reply)
    except Exception:
        pass
    if len(updated_messages) >= 11 and (len(updated_messages) - 1) % SESSION_SUMMARY_INTERVAL == 0:
        try:
            _run_session_summary(client, updated_messages)
        except Exception:
            pass
    reasoning = {"memories": used_entries, "tool_calls": tool_calls_made}
    return AudioResponse(reply=reply, session_id=session_id, transcript=transcript, reasoning_used=reasoning)
