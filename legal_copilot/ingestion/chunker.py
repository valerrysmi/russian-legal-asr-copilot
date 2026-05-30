"""Text chunking utilities."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TextChunk:
    chunk_id: int
    text: str
    start_char: int
    end_char: int


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> list[TextChunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive.")
    if overlap < 0:
        raise ValueError("overlap must be non-negative.")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size.")

    normalized = text.strip()
    if not normalized:
        return []

    chunks: list[TextChunk] = []
    start = 0
    chunk_id = 0

    while start < len(normalized):
        target_end = min(start + chunk_size, len(normalized))
        end = target_end

        if target_end < len(normalized):
            boundary = max(
                normalized.rfind("\n", start, target_end),
                normalized.rfind(". ", start, target_end),
                normalized.rfind("? ", start, target_end),
                normalized.rfind("! ", start, target_end),
                normalized.rfind("; ", start, target_end),
            )
            if boundary > start + (chunk_size // 2):
                end = boundary + 1

        chunk_text_value = normalized[start:end].strip()
        if chunk_text_value:
            chunks.append(
                TextChunk(
                    chunk_id=chunk_id,
                    text=chunk_text_value,
                    start_char=start,
                    end_char=end,
                )
            )
            chunk_id += 1

        if end >= len(normalized):
            break

        start = max(end - overlap, 0)

    return chunks
