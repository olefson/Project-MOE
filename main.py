"""
BMO Agent – Phase 0 skeleton.
Loop: Input → Reason → Tool (stubs) → Memory (placeholder) → Output.
Run: python main.py
"""
import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from tools import get_tool_definitions, run_tool

load_dotenv()

SYSTEM_PROMPT = """You are BMO, a friendly AI from the world of Adventure Time. You're playful, helpful, and a little bit silly. You have access to tools (calendar, web search, notifications, and lights), but right now they are stubs—you can "use" them to show the user you understood, and they'll see a [STUB] message. Stay in character. Keep replies concise unless the user wants a story."""


def run_agent_turn(client: OpenAI, messages: list[dict], tools: list[dict]) -> tuple[str, list[dict]]:
    """
    One agent turn: send messages to the LLM; if it calls tools, run stubs and re-call until we get a final reply.
    Returns (final_assistant_text, updated_messages).
    """
    while True:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        msg = response.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None) or []
        messages.append({
            "role": "assistant",
            "content": msg.content or None,
            "tool_calls": [
                {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in tool_calls
            ],
        })

        if not tool_calls:
            return (msg.content or "").strip(), messages

        for tc in tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
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

        # Memory placeholder: in Phase 2 we'll inject retrieved long-term memory here.
        # memory_context = get_relevant_memories(user_input)  # future

        reply, messages = run_agent_turn(client, messages, tools)
        print(f"BMO: {reply}\n")


if __name__ == "__main__":
    main()
