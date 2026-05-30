"""Helpers for building retrieval inputs from a live dialogue."""

from __future__ import annotations

from dataclasses import dataclass, field

from legal_copilot.agents.context_manager import ContextSnapshot
from legal_copilot.agents.statement_extractor import ExtractedQuestion
from legal_copilot.ingestion.chunker import TextChunk, chunk_text
from legal_copilot.ingestion.transcript_cleaner import clean_utterance
from legal_copilot.rag.hybrid_retriever import (
    GraphRAGRetriever,
    HybridRetrievalResult,
    get_default_graphrag_retriever,
)


@dataclass
class RetrievalRequest:
    query_text: str
    query_chunks: list[TextChunk]
    context_text: str
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, str | int] = field(default_factory=dict)


@dataclass
class RetrievedLegalContext:
    request: RetrievalRequest
    result: HybridRetrievalResult


def _compress_context_lines(lines: list[str], limit: int = 4) -> list[str]:
    trimmed = [clean_utterance(line) for line in lines if clean_utterance(line)]
    return trimmed[-limit:]


def build_retrieval_request(
    snapshot: ContextSnapshot,
    *,
    chunk_size: int = 500,
    overlap: int = 100,
) -> RetrievalRequest | None:
    active_turn = snapshot.active_user_turn or snapshot.latest_user_turn
    active_query_text = snapshot.active_user_span_text or (active_turn.text if active_turn else "")
    if not active_turn or not active_query_text:
        return None

    context_lines = []
    if snapshot.latest_assistant_turn and snapshot.latest_assistant_turn.text:
        context_lines.append(f"assistant: {snapshot.latest_assistant_turn.text}")
    context_lines.extend(f"user_fact: {fact}" for fact in snapshot.accumulated_user_facts[-3:])

    context_text = "\n".join(_compress_context_lines(context_lines))
    query_text = clean_utterance(active_query_text)
    if context_text:
        enriched_query = f"{query_text}\n\nContext:\n{context_text}"
        reasons = ["new_user_turn", "recent_dialogue_context"]
    else:
        enriched_query = query_text
        reasons = ["new_user_turn"]

    return RetrievalRequest(
        query_text=enriched_query,
        query_chunks=chunk_text(enriched_query, chunk_size=chunk_size, overlap=overlap),
        context_text=context_text,
        reasons=reasons,
        metadata={
            "session_id": snapshot.session_id,
            "turn_count": snapshot.turn_count,
        },
    )


def build_retrieval_request_from_extracted_question(
    extracted_question: ExtractedQuestion,
    snapshot: ContextSnapshot,
    *,
    chunk_size: int = 500,
    overlap: int = 100,
) -> RetrievalRequest | None:
    if not extracted_question.normalized_question:
        return None

    context_lines = []
    if snapshot.latest_assistant_turn and snapshot.latest_assistant_turn.text:
        context_lines.append(f"assistant: {snapshot.latest_assistant_turn.text}")
    context_lines.extend(f"user_fact: {fact}" for fact in extracted_question.extracted_facts[-3:])

    context_text = "\n".join(_compress_context_lines(context_lines))
    query_lines = extracted_question.detected_questions or [extracted_question.normalized_question]
    base_query = "\n".join(f"- {question}" for question in query_lines) if len(query_lines) > 1 else query_lines[0]

    if context_text:
        enriched_query = f"{base_query}\n\nContext:\n{context_text}"
        reasons = ["chunk_question_extraction", "recent_dialogue_context"]
    else:
        enriched_query = base_query
        reasons = ["chunk_question_extraction"]

    return RetrievalRequest(
        query_text=enriched_query,
        query_chunks=chunk_text(enriched_query, chunk_size=chunk_size, overlap=overlap),
        context_text=context_text,
        reasons=reasons,
        metadata={
            "session_id": snapshot.session_id,
            "turn_count": snapshot.turn_count,
            "detected_question_count": len(query_lines),
        },
    )


def retrieve_legal_context(
    request: RetrievalRequest,
    *,
    retriever: GraphRAGRetriever | None = None,
    top_k: int = 6,
) -> RetrievedLegalContext:
    retriever = retriever or get_default_graphrag_retriever()
    result = retriever.retrieve(request.query_text, top_k=top_k)
    return RetrievedLegalContext(request=request, result=result)
