"""
BMO Agent – Phase 0 skeleton.
Loop: Input → Reason → Tool (stubs) → Memory (placeholder) → Output.
Run: python main.py
"""
import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from memory import init_db, get_relevant, format_context, extract_and_store_memories
from tools import get_tool_definitions, run_tool

load_dotenv()
init_db()

SYSTEM_PROMPT = """You are BMO, a friendly AI from the world of Adventure Time. You're playful, helpful, and a little bit silly. You have access to tools (calendar, web search, notifications, lights, and memory).

When the user says to remember something (e.g. "remember that my name is X", "don't forget I like LoL"), use store_memory to save it. When they say to forget (e.g. "forget that", "don't remember X"), use forget_memory. When they correct you (e.g. "actually my name is Z"), use update_memory. Calendar, search, notifications, and lights are stubs for now—you can use them to show you understood; the user will see [STUB] messages. Stay in character. Keep replies concise unless the user wants a story."""


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

def main() -> None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Missing OPENAI_API_KEY. Check your .env file.")
        return

    client = OpenAI(api_key=api_key)
    tools = get_tool_definitions()
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    print("BMO (Phase 0 skeleton). Say something! Type 'quit' to exit.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break
        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("BMO: Bye! Come back and play again!")
            break

        messages.append({"role": "user", "content": user_input})

        # Inject relevant long-term memory into system message
        entries = get_relevant(client, user_input, top_k=7)
        context_str = format_context(entries)
        if context_str:
            messages[0] = {"role": "system", "content": SYSTEM_PROMPT + "\n\n[Relevant memory]:\n" + context_str}
        else:
            messages[0] = {"role": "system", "content": SYSTEM_PROMPT}

        reply, messages, _ = run_agent_turn(client, messages, tools)
        try:
            extract_and_store_memories(client, user_input, reply)
        except Exception:
            pass
        print(f"BMO: {reply}\n")


if __name__ == "__main__":
    main()
