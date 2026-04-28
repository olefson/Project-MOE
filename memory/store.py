"""
Long-term memory: SQLite + OpenAI text-embedding-3-large (3072 dims).
Fallback: when embedding API fails, get_relevant returns last N by created_at.
"""
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import OpenAI

EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMS = 3072
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "memory.db"
FALLBACK_LAST_N = 10


def _get_conn(path: Path | str | None = None) -> sqlite3.Connection:
    p = path or DEFAULT_DB_PATH
    return sqlite3.connect(str(p), check_same_thread=False)


def init_db(path: Path | str | None = None) -> None:
    """Create memories table if not exists."""
    conn = _get_conn(path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                type TEXT DEFAULT 'fact',
                source TEXT NOT NULL,
                created_at TEXT NOT NULL,
                embedding TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()


def embed(client: OpenAI, text: str) -> list[float]:
    """Return 3072-dim embedding for text. Raises on API error."""
    if not text or not text.strip():
        return [0.0] * EMBEDDING_DIMS
    r = client.embeddings.create(input=[text.strip()], model=EMBEDDING_MODEL)
    return r.data[0].embedding


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or len(a) == 0:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def store_memory(
    client: OpenAI,
    content: str,
    source: str,
    type: str = "fact",
    path: Path | str | None = None,
) -> int:
    """Embed content, insert row. Returns id."""
    init_db(path)
    content = (content or "").strip()
    if not content:
        raise ValueError("content cannot be empty")
    try:
        vec = embed(client, content)
    except Exception:
        vec = []
    created_at = datetime.now(timezone.utc).isoformat()
    embedding_json = json.dumps(vec) if vec else None
    conn = _get_conn(path)
    try:
        cur = conn.execute(
            "INSERT INTO memories (content, type, source, created_at, embedding) VALUES (?, ?, ?, ?, ?)",
            (content, type, source, created_at, embedding_json),
        )
        conn.commit()
        return cur.lastrowid or 0
    finally:
        conn.close()


def get_relevant(
    client: OpenAI,
    query: str,
    top_k: int = 5,
    path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """
    Embed query, similarity search over memories, return top-k entries.
    Fallback: if embedding API fails, return last FALLBACK_LAST_N by created_at.
    """
    init_db(path)
    conn = _get_conn(path)
    try:
        rows = conn.execute(
            "SELECT id, content, type, source, created_at, embedding FROM memories ORDER BY created_at DESC"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    # Try embedding the query for similarity search first.
    try:
        query_vec = embed(client, query or " ") if query else [0.0] * EMBEDDING_DIMS
    except Exception:
        # Fallback is recency-only last N when embedding is unavailable.
        return [
            {"id": r[0], "content": r[1], "type": r[2], "source": r[3], "created_at": r[4]}
            for r in rows[:FALLBACK_LAST_N]
        ]

    # Parse stored embeddings and compute similarity scores.
    scored: list[tuple[float, dict]] = []
    for r in rows:
        row_id, content, type_, source, created_at, emb_json = r
        entry = {"id": row_id, "content": content, "type": type_, "source": source, "created_at": created_at}
        if emb_json:
            try:
                vec = json.loads(emb_json)
                if len(vec) == len(query_vec):
                    sim = _cosine_similarity(query_vec, vec)
                    scored.append((sim, entry))
                else:
                    scored.append((0.0, entry))
            except (json.JSONDecodeError, TypeError):
                scored.append((0.0, entry))
        else:
            scored.append((0.0, entry))

    scored.sort(key=lambda x: -x[0])
    return [entry for _, entry in scored[:top_k]]


def format_context(entries: list[dict]) -> str:
    """Turn list of memory entries into string for [Relevant memory]: block."""
    if not entries:
        return ""
    lines = []
    for e in entries:
        content = e.get("content", "").strip()
        if content:
            lines.append(f"- {content}")
    return "\n".join(lines) if lines else ""


def forget_memory(
    client: OpenAI,
    description_or_id: str,
    path: Path | str | None = None,
) -> None:
    """Delete by id if numeric, else find closest by similarity and delete."""
    init_db(path)
    # First try numeric id lookup.
    s = (description_or_id or "").strip()
    if s.isdigit():
        conn = _get_conn(path)
        try:
            conn.execute("DELETE FROM memories WHERE id = ?", (int(s),))
            conn.commit()
        finally:
            conn.close()
        return

    # Otherwise hunt by similarity.
    entries = get_relevant(client, s, top_k=1, path=path)
    if not entries:
        return
    row_id = entries[0]["id"]
    conn = _get_conn(path)
    try:
        conn.execute("DELETE FROM memories WHERE id = ?", (row_id,))
        conn.commit()
    finally:
        conn.close()


def update_memory(
    client: OpenAI,
    description_or_id: str,
    new_content: str,
    path: Path | str | None = None,
) -> None:
    """Find memory (by id or similarity), update content and re-embed."""
    init_db(path)
    s = (description_or_id or "").strip()
    new_content = (new_content or "").strip()
    if not new_content:
        return

    row_id = None
    if s.isdigit():
        row_id = int(s)
    else:
        entries = get_relevant(client, s, top_k=1, path=path)
        if entries:
            row_id = entries[0]["id"]

    if row_id is None:
        return

    try:
        vec = embed(client, new_content)
        embedding_json = json.dumps(vec)
    except Exception:
        embedding_json = None

    conn = _get_conn(path)
    try:
        conn.execute(
            "UPDATE memories SET content = ?, embedding = ?, created_at = ? WHERE id = ?",
            (new_content, embedding_json, datetime.now(timezone.utc).isoformat(), row_id),
        )
        conn.commit()
    finally:
        conn.close()


def extract_and_store_memories(
    client: OpenAI,
    last_user_message: str,
    last_assistant_reply: str,
    path: Path | str | None = None,
) -> None:
    """
    One LLM call to extract factual claims about the user; store each as inferred memory.
    """
    if not last_user_message.strip() and not last_assistant_reply.strip():
        return
    prompt = f"""From this exchange, list factual claims about the user (preferences, name, important facts). One short sentence per line. If nothing to store, output NOTHING.

User: {last_user_message}
Assistant: {last_assistant_reply}

Facts (one per line, or NOTHING):"""
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
        )
        text = (r.choices[0].message.content or "").strip()
    except Exception:
        return
    if not text or "NOTHING" in text.upper():
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.upper() == "NOTHING" or len(line) < 3:
            continue
        # Strip leading bullets/dashes.
        if line.startswith("- ") or line.startswith("* "):
            line = line[2:].strip()
        try:
            store_memory(client, line, "inferred", path=path)
        except Exception:
            pass
