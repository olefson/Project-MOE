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
from tools import get_tool_definitions

load_dotenv()

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


def get_memory_context(session_id: str, user_message: str) -> str:
    """
    Placeholder for Phase 2 long-term memory. Returns empty string for now.
    Inject retrieved context into the system prompt when this returns non-empty.
    """
    return ""


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str


class AudioResponse(BaseModel):
    reply: str
    session_id: str
    transcript: str | None = None


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

    # Inject memory context into system message (Phase 2 hook)
    memory_context = get_memory_context(session_id, message)
    if memory_context:
        messages[0] = {
            "role": "system",
            "content": SYSTEM_PROMPT + "\n\n[Relevant memory]:\n" + memory_context,
        }
    else:
        messages[0] = {"role": "system", "content": SYSTEM_PROMPT}

    messages.append({"role": "user", "content": message})

    try:
        client = OpenAI(api_key=api_key)
        tools = get_tool_definitions()
        reply, updated_messages = run_agent_turn(client, messages, tools)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}") from e

    session_store[session_id] = updated_messages
    return ChatResponse(reply=reply, session_id=session_id)


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

    memory_context = get_memory_context(session_id, transcript)
    if memory_context:
        messages[0] = {
            "role": "system",
            "content": SYSTEM_PROMPT + "\n\n[Relevant memory]:\n" + memory_context,
        }
    else:
        messages[0] = {"role": "system", "content": SYSTEM_PROMPT}

    messages.append({"role": "user", "content": transcript})

    try:
        tools = get_tool_definitions()
        reply, updated_messages = run_agent_turn(client, messages, tools)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}") from e

    session_store[session_id] = updated_messages
    return AudioResponse(reply=reply, session_id=session_id, transcript=transcript)
