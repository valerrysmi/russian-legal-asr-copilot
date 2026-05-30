"""Checks whether substantive lawyer phrases are supported by retrieved Civil Code sources."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from legal_copilot.agents.context_manager import ContextSnapshot
from legal_copilot.rag.hybrid_retriever import HybridRetrievalHit

TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]{4,}")

STOPWORDS = {
    "если",
    "или",
    "либо",
    "того",
    "когда",
    "тогда",
    "этого",
    "этой",
    "этот",
    "нужно",
    "можно",
    "также",
    "чтобы",
    "который",
    "которые",
    "после",
    "между",
    "будет",
    "такой",
    "такое",
    "такая",
    "пока",
    "просто",
    "очень",
    "сейчас",
    "потом",
    "через",
    "клиент",
    "клиенту",
    "сделка",
    "сделки",
}

META_MARKERS = (
    "понял",
    "смотрю",
    "проверю",
    "разбиваю запрос",
    "ищу",
    "поднимаю",
    "вижу общий контекст",
    "ориентируюсь",
)

LEGAL_MARKERS = (
    "статья",
    "гк",
    "доля",
    "доли",
    "нотари",
    "голос",
    "одобр",
    "соглас",
    "кредитор",
    "оспар",
    "недейств",
    "преимущ",
    "право",
    "обязан",
    "требует",
    "требуется",
    "может",
    "должен",
)


@dataclass
class LawyerPhraseCheckResult:
    status: Literal["no_statement", "supported", "partially_supported", "needs_review"]
    grounded: bool
    confidence: float
    reviewed_phrases: list[str] = field(default_factory=list)
    flagged_phrases: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    cited_articles: list[str] = field(default_factory=list)


def _normalize_text(text: str) -> str:
    return " ".join((text or "").lower().split())


def _extract_tokens(text: str) -> set[str]:
    tokens = set()
    for token in TOKEN_RE.findall(_normalize_text(text)):
        if token in STOPWORDS:
            continue
        tokens.add(token)
    return tokens


def _is_meta_phrase(text: str) -> bool:
    normalized = _normalize_text(text)
    if any(marker in normalized for marker in META_MARKERS) and not any(
        marker in normalized for marker in LEGAL_MARKERS
    ):
        return True
    return False


def _collect_substantive_lawyer_phrases(
    snapshot: ContextSnapshot,
    max_turns: int = 3,
) -> list[str]:
    phrases: list[str] = []
    for turn in reversed(snapshot.recent_turns):
        if turn.speaker != "assistant":
            continue
        text = turn.text.strip()
        if not text or _is_meta_phrase(text):
            continue
        phrases.append(text)
        if len(phrases) >= max_turns:
            break
    phrases.reverse()
    return phrases


def _build_source_token_pool(retrieved_hits: list[HybridRetrievalHit]) -> set[str]:
    source_tokens: set[str] = set()
    for hit in retrieved_hits[:5]:
        source_tokens.update(_extract_tokens(hit.title))
        source_tokens.update(_extract_tokens(hit.summary or ""))
        source_tokens.update(_extract_tokens(hit.text or ""))
    return source_tokens


def check_lawyer_phrases_grounding(
    snapshot: ContextSnapshot,
    retrieved_hits: list[HybridRetrievalHit],
) -> LawyerPhraseCheckResult:
    phrases = _collect_substantive_lawyer_phrases(snapshot)
    if not phrases:
        return LawyerPhraseCheckResult(
            status="no_statement",
            grounded=True,
            confidence=0.0,
            notes=["no_substantive_lawyer_phrases_in_recent_context"],
            cited_articles=[],
        )

    if not retrieved_hits:
        return LawyerPhraseCheckResult(
            status="needs_review",
            grounded=False,
            confidence=0.2,
            reviewed_phrases=phrases,
            flagged_phrases=list(phrases),
            notes=["lawyer_phrases_present_but_no_retrieved_sources"],
            cited_articles=[],
        )

    source_tokens = _build_source_token_pool(retrieved_hits)
    top_hits = retrieved_hits[:3]
    cited_articles = [hit.article_number for hit in top_hits]
    avg_score = sum(hit.final_score for hit in top_hits) / len(top_hits)
    reviewed_phrases: list[str] = []
    flagged_phrases: list[str] = []
    phrase_coverages: list[float] = []

    for phrase in phrases:
        phrase_tokens = _extract_tokens(phrase)
        if not phrase_tokens:
            continue
        overlap = len(phrase_tokens & source_tokens)
        coverage = overlap / max(len(phrase_tokens), 1)
        phrase_coverages.append(coverage)
        reviewed_phrases.append(phrase)
        if coverage < 0.12 and avg_score < 0.18:
            flagged_phrases.append(phrase)

    if not reviewed_phrases:
        return LawyerPhraseCheckResult(
            status="no_statement",
            grounded=True,
            confidence=0.0,
            notes=["recent_lawyer_turns_are_too_short_for_grounding_check"],
            cited_articles=cited_articles,
        )

    avg_coverage = sum(phrase_coverages) / len(phrase_coverages)
    confidence = min(max((avg_score * 0.65) + (avg_coverage * 0.9), 0.0), 0.95)

    if not flagged_phrases and (avg_coverage >= 0.2 or avg_score >= 0.22):
        status = "supported"
        grounded = True
        notes = ["lawyer_phrases_consistent_with_retrieved_sources"]
    elif len(flagged_phrases) < len(reviewed_phrases) and (avg_coverage >= 0.12 or avg_score >= 0.14):
        status = "partially_supported"
        grounded = True
        notes = ["lawyer_phrases_only_partially_supported_by_retrieved_sources"]
    else:
        status = "needs_review"
        grounded = False
        notes = ["lawyer_phrases_need_manual_legal_review"]

    if flagged_phrases:
        notes.append(f"flagged_phrases={len(flagged_phrases)}")

    return LawyerPhraseCheckResult(
        status=status,
        grounded=grounded,
        confidence=confidence,
        reviewed_phrases=reviewed_phrases,
        flagged_phrases=flagged_phrases,
        notes=notes,
        cited_articles=cited_articles,
    )
