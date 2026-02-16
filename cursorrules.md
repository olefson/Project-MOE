# Cursor rules – BMO Agentic AI Project

## Environment and secrets

- **A `.env` file exists** for this project. It holds API keys and other secrets (e.g. `OPENAI_API_KEY`). The file is not readable by Cursor for security reasons.
- **If you run into auth/API errors** (e.g. invalid API key, missing key, 401/403), do **not** assume the key is wrong or missing in code. Instead:
  1. **Prompt the user:** Ask them to double-check that the `.env` file exists in the expected location (project root or `Project-MOE` as used in this repo).
  2. **Ask them to verify contents:** Remind them to confirm the file contains the required variables (e.g. `OPENAI_API_KEY=sk-...`) with no typos, no extra quotes around the value, and no spaces around `=`.
  3. Only after the user has confirmed the file and its contents should you suggest code or path changes.

---

## Project context

- This is the **BMO Agentic AI** project (CIS 6930 – Introduction to Agentic AI). Goal: a voice-based, personality-driven agent that can reason, remember, and act using external tools.
- Follow the **phased plan** in `project_plan.md`: Phase 0 (setup/skeleton) → Phase 1 (voice) → Phase 2 (memory) → Phase 3+ (calendar, search, Telegram, Hue). Prefer implementing in that order unless the user asks otherwise.
- **Agent loop:** Input → Reason → Tool → Memory → Output. New features should plug into this pipeline; avoid one-off scripts that bypass it.
- **No model training.** Use API-based LLMs, STT, TTS, and external APIs only.

---

## Code and structure

- **Python 3.10+.** Prefer type hints for function signatures and public APIs.
- **Stub first, then implement.** When adding a new tool (calendar, search, etc.), add a stub interface that fits the agent loop, then wire the real API.
- **One main entry point** for the agent (e.g. `main.py` or `run.py`). Keep tool logic in separate modules (e.g. `tools/`, `memory/`) rather than one giant file.
- **Load config from environment.** Use `python-dotenv` and `os.getenv()` (or similar) for API keys and feature flags. No hardcoded secrets.
- **Dependencies:** Add new packages to `requirements.txt` when you introduce them; use the minimal set needed for the current phase.

---

## Security and repo hygiene

- **Never commit secrets.** Assume `.env` is in `.gitignore`. Do not suggest adding `.env` to the repo or inlining API keys.
- **Never read or request the contents of `.env`.** If you need to reference a variable name, use the documented name (e.g. `OPENAI_API_KEY`), not the value.
- When adding new services (Google, Telegram, Hue, etc.), remind the user to add the new keys to `.env` and to keep `.gitignore` up to date.

---

## APIs and tools

- **Handle failures gracefully.** Network and API calls can fail; use try/except, timeouts, and clear error messages. Prefer logging over silent failure.
- **Respect rate limits.** When suggesting or writing code that calls external APIs, consider throttling or backoff if the service is rate-limited.
- **Tool responses to the agent should be concise.** Return structured, short results (e.g. “Event added” or a one-line summary) so the LLM can reason and respond in natural language.

---

## Documentation and prompts

- **README.md** should explain how to set up the venv, install deps, and run the agent. Keep it in sync with actual commands and project structure.
- **BMO persona:** When editing system prompts or agent behavior, keep BMO’s tone playful, helpful, and story-aware (Finn & Jake, Adventure Time). Avoid generic assistant voice.
- **Comments:** Prefer clear names and short docstrings over long inline comments. Comment “why” for non-obvious logic (e.g. workarounds, API quirks).

---

## When suggesting changes

- Prefer **small, reviewable edits** over large refactors unless the user asks for a refactor.
- If a change touches the agent loop or tool interface, briefly say how it fits the Input → Reason → Tool → Memory → Output flow.
- If the user’s request is ambiguous (e.g. “make it better”), ask for clarification (e.g. performance, readability, or a specific bug) before changing code.
