"""
PMO Agent – Phase 0 skeleton.
Loop: Input → Reason → Tool (stubs) → Memory (placeholder) → Output.
Run: python main.py
With PMO_VOICE_ONLY=1: mic always on; speak then pause to submit (no keyboard).
"""
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path

# Set SDL env before any code can import pygame (required for face window on Windows)
if os.name == "nt":
    os.environ.setdefault("SDL_VIDEODRIVER", "windows")
    os.environ.setdefault("SDL_VIDEO_WINDOW_POS", "100,100")

from dotenv import load_dotenv
from openai import OpenAI

from memory import init_db, get_relevant, format_context, extract_and_store_memories
from tools import get_tool_definitions, run_tool
from tts import speak as tts_speak, is_available as tts_available
from face import (
    start_face as face_start,
    run_face_loop as face_run_loop,
    stop_face as face_stop,
    record_interaction as face_record_interaction,
    show_error as face_show_error,
)
from voice_input import record_until_silence, is_available as voice_input_available
from wake_word import is_available as wake_word_available, get_wake_phrase_display
from voice_conversation import open_conversation, get_next_utterance, close_conversation

load_dotenv(Path(__file__).resolve().parent / ".env")
init_db()

SYSTEM_PROMPT = """You are PMO, a friendly AI from the world of Adventure Time. You're playful, helpful, and a little bit silly. You have access to tools: calendar (add events), Gmail (list_emails, get_email, send_email), Google Docs (list_docs, get_doc_content, create_doc), Google Sheets (list_sheets, get_sheet_data), weather (get_weather), web search, notifications, Philips Hue lights, Pi device control (volume and reboot), and memory.

When the user says to remember something (e.g. "remember that my name is X", "don't forget I like LoL"), use store_memory to save it. When they say to forget (e.g. "forget that", "don't remember X"), use forget_memory. When they correct you (e.g. "actually my name is Z"), use update_memory. You can add calendar events, read and send Gmail (list_emails, get_email, send_email), read and create Google Docs (list_docs, get_doc_content, create_doc), and read Google Sheets (list_sheets, get_sheet_data). When the user asks about the weather (e.g. "how's the weather?", "what's the temperature in Seattle?"), use get_weather with an optional city name or leave location empty for their default location. When the user asks to read emails or summarize a doc/sheet, use the list tool first to find ids, then get_email/get_doc_content/get_sheet_data to fetch content, then summarize in your reply (e.g. for a voice assistant). For Philips Hue: use list_rooms to see room names, list_lights to see lights, list_scenes to see scenes; use set_lights with action on/off/color/scene and optional room_name (e.g. "Secondary Bathroom", "Living room") to control lights. On Raspberry Pi you can control device volume: use get_volume, set_volume, volume_up, volume_down, set_mute when the user asks to change volume or mute. Only call reboot_pi when the user explicitly confirms (e.g. "yes, reboot"); it requires PMO_ALLOW_REBOOT=1 in the environment. Web search and notifications are stubs for now. Stay in character. Keep replies concise unless the user wants a story. Do not use emojis—your replies are spoken by text-to-speech and emojis get read aloud. Do not use markdown formatting of any kind (no asterisks, bullet markers, backticks, or headings); answer in plain conversational text only so the TTS never says the word 'asterisk' or reads symbols aloud."""


def get_current_time_context() -> str:
    """Return current date and time for the system prompt so the LLM knows 'now' (e.g. for 'tomorrow', 'in an hour', alarms)."""
    now = datetime.now().astimezone()
    return f"[Current date and time: {now.strftime('%A, %B %d, %Y, %I:%M %p %Z')}. Use this for relative times like 'tomorrow', 'in an hour', 'next Friday'.]"


def run_agent_turn(client: OpenAI, messages: list[dict], tools: list[dict]) -> tuple[str, list[dict], list[dict]]:
    """
    One agent turn: send messages to the LLM; if it calls tools, run stubs and re-call until we get a final reply.
    Returns (final_assistant_text, updated_messages, tool_calls_made).
    """
    tool_calls_made: list[dict] = []
    while True:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        msg = response.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None) or []
        assistant_msg = {"role": "assistant", "content": msg.content or None}
        if tool_calls:
            assistant_msg["tool_calls"] = [
                {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in tool_calls
            ]
        messages.append(assistant_msg)

        if not tool_calls:
            return (msg.content or "").strip(), messages, tool_calls_made

        for tc in tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            tool_calls_made.append({"name": name, "arguments": args})
            result = run_tool(name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })


def agent_loop(
    client: OpenAI,
    tools: list,
    messages: list,
    voice_only: bool,
    use_wake_word: bool,
    picovoice_key: str,
    tts_ok: bool,
) -> None:
    """Run the input → reason → output loop. Runs in a background thread when the face is shown."""
    session = None
    open_fail_count = 0
    while True:
        try:
            if voice_only:
                if use_wake_word:
                    # Single-stream conversation: wake word once to start, then listen until silence each turn.
                    # Say "goodbye" to end conversation and go back to waiting for wake word.
                    session = open_conversation(picovoice_key)
                    if not session:
                        open_fail_count += 1
                        if open_fail_count >= 3:
                            print("Could not start conversation after 3 attempts. Check [Voice] errors above, PICOVOICE_ACCESS_KEY, and mic. Exiting voice loop.", flush=True)
                            break
                        print("(Could not start conversation, retrying)", flush=True)
                        time.sleep(2)
                        continue
                    open_fail_count = 0
                    print(f"Say '{get_wake_phrase_display()}' to start, then speak. Say 'goodbye' to end. Ctrl+C to exit.")
                    while True:
                        if not session.wake_done:
                            print("Waiting for wake word...", end=" ", flush=True)
                        else:
                            print("Listening...", end=" ", flush=True)
                        wav_path = get_next_utterance(session)
                        if not wav_path:
                            print("(no speech, try again)")
                            continue
                        try:
                            with open(wav_path, "rb") as f:
                                transcript_response = client.audio.transcriptions.create(model="whisper-1", file=f)
                            user_input = (transcript_response.text or "").strip()
                        finally:
                            try:
                                os.unlink(wav_path)
                            except OSError:
                                pass
                        print("Heard:", user_input or "(empty)")
                        if not user_input:
                            continue
                        if user_input.lower() in ("goodbye", "exit", "quit", "bye", "q"):
                            print("Ending conversation.")
                            break
                        messages.append({"role": "user", "content": user_input})
                        face_record_interaction()
                        time_block = get_current_time_context()
                        entries = get_relevant(client, user_input, top_k=7)
                        context_str = format_context(entries)
                        if context_str:
                            messages[0] = {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + time_block + "\n\n[Relevant memory]:\n" + context_str}
                        else:
                            messages[0] = {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + time_block}
                        try:
                            reply, messages, _ = run_agent_turn(client, messages, tools)
                        except Exception as e:
                            face_show_error()
                            print(f"PMO: Oops, something went wrong: {e}\n")
                            continue
                        try:
                            extract_and_store_memories(client, user_input, reply)
                        except Exception:
                            pass
                        print(f"PMO: {reply}\n")
                        face_record_interaction()
                        if reply and os.getenv("PMO_TTS", "1").strip().lower() not in ("0", "false", "no"):
                            try:
                                tts_speak(reply)
                            except Exception:
                                face_show_error()
                    close_conversation(session)
                    continue
                else:
                    print("Listening...", end=" ", flush=True)
                    wav_path = record_until_silence(silence_duration_ms=1200, min_utterance_ms=400, max_duration_ms=15000)
                if not wav_path:
                    print("(no speech, try again)")
                    continue
                try:
                    with open(wav_path, "rb") as f:
                        transcript_response = client.audio.transcriptions.create(model="whisper-1", file=f)
                    user_input = (transcript_response.text or "").strip()
                finally:
                    try:
                        os.unlink(wav_path)
                    except OSError:
                        pass
                print("Heard:", user_input or "(empty)")
                if not user_input:
                    continue
            else:
                user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            if session is not None:
                close_conversation(session)
                session = None
            print("\nBye!")
            face_stop()
            break
        if not voice_only and not user_input:
            continue
        if not voice_only and user_input.lower() in ("quit", "exit", "q"):
            print("PMO: Bye! Come back and play again!")
            face_stop()
            break

        messages.append({"role": "user", "content": user_input})
        face_record_interaction()

        time_block = get_current_time_context()
        entries = get_relevant(client, user_input, top_k=7)
        context_str = format_context(entries)
        if context_str:
            messages[0] = {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + time_block + "\n\n[Relevant memory]:\n" + context_str}
        else:
            messages[0] = {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + time_block}

        try:
            reply, messages, _ = run_agent_turn(client, messages, tools)
        except Exception as e:
            face_show_error()
            print(f"PMO: Oops, something went wrong: {e}\n")
            continue
        try:
            extract_and_store_memories(client, user_input, reply)
        except Exception:
            pass
        print(f"PMO: {reply}\n")
        face_record_interaction()
        if reply and os.getenv("PMO_TTS", "1").strip().lower() not in ("0", "false", "no"):
            try:
                tts_speak(reply)
            except Exception:
                face_show_error()


def main() -> None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Missing OPENAI_API_KEY. Check your .env file.")
        return

    client = OpenAI(api_key=api_key)
    tools = get_tool_definitions()
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    tts_ok = tts_available()
    show_face = os.getenv("PMO_FACE", "0").strip().lower() in ("1", "true", "yes")
    voice_only = os.getenv("PMO_VOICE_ONLY", "0").strip().lower() in ("1", "true", "yes")
    use_wake_word = os.getenv("PMO_WAKE_WORD", "0").strip().lower() in ("1", "true", "yes")
    if use_wake_word:
        voice_only = True  # wake word implies voice-only (no keyboard)
    picovoice_key = os.getenv("PICOVOICE_ACCESS_KEY", "").strip()

    if show_face:
        print("(Face enabled: PMO_FACE=1)", flush=True)
        face_start()
    if use_wake_word:
        if not picovoice_key:
            print("PMO_WAKE_WORD=1 but PICOVOICE_ACCESS_KEY is missing. Get a free key at https://console.picovoice.ai/ and add to .env")
            return
        if not wake_word_available(picovoice_key):
            print("Wake word not available. Install: pip install pvporcupine pyaudio. On Pi: sudo apt install portaudio19-dev")
            print("Continuing without wake word (voice-only or keyboard).")
            use_wake_word = False
        else:
            print(f"PMO – wake word on. Say '{get_wake_phrase_display()}' to start a conversation; then just speak (no wake word between turns). Say 'goodbye' to end. Ctrl+C to exit.")
    elif not use_wake_word and voice_only:
        if not voice_input_available():
            print("PMO_VOICE_ONLY=1 but mic not available. Install: pip install pyaudio webrtcvad (on Pi: sudo apt install portaudio19-dev first).")
            return
        print("PMO – voice only (mic always on). Speak, then pause ~1s when done. Ctrl+C to exit.")
    elif not use_wake_word:
        print("PMO (Phase 0 skeleton). Say something! Type 'quit' to exit.")
    if not tts_ok:
        print("(TTS: run 'python scripts/download_piper_voice.py' to enable voice.)")
    if show_face:
        print("(Face window: 800x480)")
    print()

    agent_thread = threading.Thread(
        target=agent_loop,
        args=(client, tools, messages, voice_only, use_wake_word, picovoice_key, tts_ok),
        daemon=True,
    )
    agent_thread.start()

    if show_face:
        face_run_loop()
    agent_thread.join()


if __name__ == "__main__":
    main()
