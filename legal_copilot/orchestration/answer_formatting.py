"""Helpers for formatting generated legal answers."""

from __future__ import annotations

import re

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def normalize_text(value: str | None) -> str:
    return (value or "").strip() or "—"


def build_short_answer(answer_text: str | None, *, max_sentences: int = 2, max_chars: int = 320) -> str:
    text = " ".join((answer_text or "").split()).strip()
    if not text:
        return "—"

    sentences = [sentence.strip() for sentence in SENTENCE_SPLIT_RE.split(text) if sentence.strip()]
    if not sentences:
        return _truncate_text(text, max_chars)

    short_sentences: list[str] = []
    for sentence in sentences:
        short_sentences.append(sentence)
        candidate = " ".join(short_sentences)
        if len(short_sentences) >= max_sentences or len(candidate) >= max_chars:
            break

    candidate = " ".join(short_sentences).strip()
    return _truncate_text(candidate, max_chars)


def _truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    shortened = text[: max_chars - 3].rstrip(" ,;:")
    return f"{shortened}..."
