"""Main pipeline orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from legal_copilot.agents.context_manager import (
    ContextSnapshot,
    StreamingContextManager,
)
from legal_copilot.agents.retriever import RetrievalRequest, build_retrieval_request
from legal_copilot.ingestion.chunker import TextChunk, chunk_text
from legal_copilot.ingestion.transcript_cleaner import (
    TranscriptTurn,
    parse_transcript,
    parse_transcript_with_options,
)


@dataclass
class ProcessedUserRequest:
    raw_input: Any
    normalized_turns: list[TranscriptTurn]
    normalized_transcript: str
    latest_user_query: str
    cleaned_user_query: str
    query_chunks: list[TextChunk]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StreamingPipelineResult:
    raw_input: Any
    parsed_turns: list[TranscriptTurn]
    appended_turns: list[TranscriptTurn]
    context_snapshot: ContextSnapshot
    active_user_query: str
    retrieval_request: RetrievalRequest | None
    metadata: dict[str, Any] = field(default_factory=dict)


def process_user_request(
    raw_transcript: Any,
    *,
    chunk_size: int = 500,
    overlap: int = 100,
) -> ProcessedUserRequest:
    """Normalize a transcript-like payload and extract the user's current request."""
    parsed = parse_transcript(raw_transcript)
    chunks = chunk_text(parsed.cleaned_user_query, chunk_size=chunk_size, overlap=overlap)

    return ProcessedUserRequest(
        raw_input=raw_transcript,
        normalized_turns=parsed.turns,
        normalized_transcript=parsed.transcript_text,
        latest_user_query=parsed.latest_user_query,
        cleaned_user_query=parsed.cleaned_user_query,
        query_chunks=chunks,
        metadata=parsed.metadata | {"chunk_count": len(chunks)},
    )


def process_transcript_chunk(
    raw_transcript_chunk: Any,
    *,
    context_manager: StreamingContextManager | None = None,
    chunk_size: int = 500,
    overlap: int = 100,
) -> StreamingPipelineResult:
    """Process a small transcript slice and update the live conversation state."""
    context_manager = context_manager or StreamingContextManager()
    parsed = parse_transcript_with_options(raw_transcript_chunk, merge_turns=False)
    appended_turns = context_manager.update(parsed.turns)
    snapshot = context_manager.build_context_snapshot()
    retrieval_request = build_retrieval_request(
        snapshot,
        chunk_size=chunk_size,
        overlap=overlap,
    )
    active_user_query = (
        snapshot.active_user_span_text
        if snapshot.active_user_span_text
        else parsed.cleaned_user_query
    )

    return StreamingPipelineResult(
        raw_input=raw_transcript_chunk,
        parsed_turns=parsed.turns,
        appended_turns=appended_turns,
        context_snapshot=snapshot,
        active_user_query=active_user_query,
        retrieval_request=retrieval_request,
        metadata={
            "parsed_turn_count": len(parsed.turns),
            "appended_turn_count": len(appended_turns),
            "session_turn_count": snapshot.turn_count,
        },
    )
