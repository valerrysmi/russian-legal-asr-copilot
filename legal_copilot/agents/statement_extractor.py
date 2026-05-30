"""Agent utilities for extracting one or more client questions from a chunk."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from legal_copilot.agents.context_manager import ContextSnapshot
from legal_copilot.ingestion.transcript_cleaner import (
    TranscriptTurn,
    clean_utterance,
    normalize_transcript,
)

QUESTION_CUES = (
    "нужно ли",
    "можно ли",
    "как",
    "какие",
    "какой",
    "что делать",
    "что будет",
    "когда",
    "почему",
    "есть ли",
    "достаточно ли",
    "обязательно ли",
    "требуется ли",
)

ENUMERATION_PREFIX_RE = re.compile(
    r"^(?:первое|во-первых|второе|во-вторых|третье|в-третьих|четвертое|в-четвертых)\b[,:-]?\s*",
    re.IGNORECASE,
)
NOISE_PREFIX_RE = re.compile(
    r"^(?:угу|ага|окей|ок|ну|слушай|смотри|то есть|так)\b[,.!?\s-]*",
    re.IGNORECASE,
)


@dataclass
class ExtractedQuestion:
    question_text: str
    normalized_question: str
    confidence: float
    is_question: bool
    needs_clarification: bool
    extracted_facts: list[str] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)
    detected_questions: list[str] = field(default_factory=list)


def _normalize_question_text(text: str) -> str:
    normalized = clean_utterance(text)
    normalized = ENUMERATION_PREFIX_RE.sub("", normalized).strip()
    normalized = NOISE_PREFIX_RE.sub("", normalized).strip()
    return normalized[:1].upper() + normalized[1:] if normalized else normalized


def _looks_like_question(text: str) -> bool:
    lowered = text.lower()
    return text.endswith("?") or any(cue in lowered for cue in QUESTION_CUES)


def _looks_incomplete(text: str) -> bool:
    lowered = text.lower().rstrip(".!?")
    if text.strip().endswith("?") and len(re.findall(r"\w+", lowered, flags=re.UNICODE)) >= 3:
        return False

    if len(lowered) < 18:
        return True

    words = re.findall(r"\w+|\S", lowered, flags=re.UNICODE)
    if not words:
        return True

    return words[-1] in {"по", "про", "о", "об", "обо", "из-за", "для"}


def _extract_supporting_facts(snapshot: ContextSnapshot | None) -> list[str]:
    if not snapshot:
        return []
    facts = []
    for fact in snapshot.accumulated_user_facts[-4:]:
        cleaned = _normalize_question_text(fact)
        if cleaned and cleaned not in facts:
            facts.append(cleaned)
    return facts


def _turns_from_chunk(raw_chunk: Any) -> list[TranscriptTurn]:
    turns = normalize_transcript(raw_chunk)
    return [turn for turn in turns if turn.text]


def _expand_with_unknown_suffix(turns: list[TranscriptTurn], start_index: int, text: str) -> str:
    parts = [text]
    if not _looks_incomplete(text):
        return text

    for next_turn in turns[start_index + 1 :]:
        if next_turn.speaker in {"user", "assistant"}:
            break
        if next_turn.speaker == "unknown" and next_turn.text:
            parts.append(next_turn.text)

    return clean_utterance(" ".join(parts))


def extract_client_questions_from_chunk(
    raw_chunk: Any,
    *,
    snapshot: ContextSnapshot | None = None,
) -> list[ExtractedQuestion]:
    turns = _turns_from_chunk(raw_chunk)
    supporting_facts = _extract_supporting_facts(snapshot)
    extracted: list[ExtractedQuestion] = []

    for index, turn in enumerate(turns):
        if turn.speaker != "user":
            continue

        candidate = _expand_with_unknown_suffix(turns, index, turn.text)
        normalized_question = _normalize_question_text(candidate)
        if not normalized_question:
            continue

        is_question = _looks_like_question(normalized_question) or bool(
            ENUMERATION_PREFIX_RE.match(turn.text)
        )
        needs_clarification = _looks_incomplete(normalized_question)
        confidence = 0.9 if is_question else 0.45
        reasoning = ["question_cues_detected" if is_question else "statement_like_user_turn"]
        if ENUMERATION_PREFIX_RE.match(turn.text):
            reasoning.append("enumeration_detected")
        if needs_clarification:
            confidence = min(confidence, 0.4)
            reasoning.append("query_looks_incomplete")

        extracted.append(
            ExtractedQuestion(
                question_text=candidate,
                normalized_question=normalized_question,
                confidence=confidence,
                is_question=is_question,
                needs_clarification=needs_clarification,
                extracted_facts=supporting_facts,
                reasoning=reasoning,
            )
        )

    return extracted


def extract_client_question(
    snapshot: ContextSnapshot,
    raw_chunk: Any | None = None,
) -> ExtractedQuestion:
    if raw_chunk is not None:
        questions = extract_client_questions_from_chunk(raw_chunk, snapshot=snapshot)
        if questions:
            primary = next(
                (question for question in questions if question.is_question and not question.needs_clarification),
                questions[0],
            )
            primary.detected_questions = [question.normalized_question for question in questions]
            return primary

    candidate = snapshot.active_user_span_text or (
        snapshot.latest_user_turn.text if snapshot.latest_user_turn else ""
    )
    normalized_question = _normalize_question_text(candidate)
    supporting_facts = _extract_supporting_facts(snapshot)

    if not normalized_question:
        return ExtractedQuestion(
            question_text="",
            normalized_question="",
            confidence=0.0,
            is_question=False,
            needs_clarification=False,
            extracted_facts=supporting_facts,
            reasoning=["no_user_question_in_context"],
            detected_questions=[],
        )

    is_question = _looks_like_question(normalized_question)
    confidence = 0.9 if is_question else 0.45
    needs_clarification = _looks_incomplete(normalized_question)
    reasoning = ["question_cues_detected" if is_question else "statement_like_user_turn"]
    if needs_clarification:
        confidence = min(confidence, 0.4)
        reasoning.append("query_looks_incomplete")

    return ExtractedQuestion(
        question_text=candidate,
        normalized_question=normalized_question,
        confidence=confidence,
        is_question=is_question,
        needs_clarification=needs_clarification,
        extracted_facts=supporting_facts,
        reasoning=reasoning,
        detected_questions=[normalized_question],
    )
