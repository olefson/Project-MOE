"""
Incremental sentence splitting for streaming LLM text → TTS chunks.
Uses . ! ? followed by whitespace (or end); best-effort (not a full NLP tokenizer).
"""
from __future__ import annotations

import re

# Sentence end: punctuation then space(s) or end of string. Avoid tiny fragments.
_MIN_SENTENCE_LEN = 4
_SPLIT = re.compile(r"^(.+?[.!?])(\s+|$)(.*)$", re.DOTALL)


def try_pop_sentence(buffer: str) -> tuple[str | None, str]:
    """
    If buffer starts with a complete sentence, return (sentence, rest).
    Otherwise (None, buffer).
    """
    if len(buffer.strip()) < _MIN_SENTENCE_LEN:
        return None, buffer
    m = _SPLIT.match(buffer)
    if not m:
        return None, buffer
    sentence = m.group(1).strip()
    rest = m.group(3)
    if len(sentence) < _MIN_SENTENCE_LEN:
        return None, buffer
    return sentence, rest


class SentenceAccumulator:
    """Feed streaming text; collect complete sentences via pop()."""

    def __init__(self) -> None:
        self._buf = ""

    def feed(self, chunk: str) -> list[str]:
        self._buf += chunk
        sentences: list[str] = []
        while True:
            sent, self._buf = try_pop_sentence(self._buf)
            if sent is None:
                break
            sentences.append(sent)
        return sentences

    def flush_remainder(self) -> str | None:
        """Call when the stream ended. Returns trailing text without sentence end, or None."""
        t = self._buf.strip()
        self._buf = ""
        return t if t else None
