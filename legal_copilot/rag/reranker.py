"""Reranking logic for hybrid GraphRAG retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from legal_copilot.rag.embeddings import keyword_overlap_ratio, tokenize
from legal_copilot.rag.query_understanding import QueryUnderstanding

ARTICLE_REFERENCE_RE = re.compile(
    r"\bст(?:атья|атьи|атье|атью|\.?)\s+(\d+(?:\.\d+)*)",
    re.IGNORECASE,
)


@dataclass
class RerankCandidate:
    article_number: str
    title: str
    summary: str
    text: str
    metadata: dict[str, Any]
    vector_score: float = 0.0
    graph_score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    final_score: float = 0.0


def _query_article_mentions(query: str) -> set[str]:
    return {match.group(1) for match in ARTICLE_REFERENCE_RE.finditer(query)}


def _topic_match_score(query_topics: list[str], article_topics: list[str]) -> float:
    if not query_topics or not article_topics:
        return 0.0
    query_set = set(query_topics)
    article_set = set(article_topics)
    return len(query_set & article_set) / len(query_set)


def _subquery_coverage_score(subqueries: list[str], candidate: RerankCandidate) -> float:
    if len(subqueries) <= 1:
        return 0.0

    coverage_hits = 0
    candidate_title_tokens = tokenize(candidate.title)
    candidate_summary_tokens = tokenize(candidate.summary)
    candidate_text_tokens = tokenize(candidate.text[:2000])
    for subquery in subqueries:
        subquery_tokens = tokenize(subquery)
        title_overlap = keyword_overlap_ratio(subquery_tokens, candidate_title_tokens)
        summary_overlap = keyword_overlap_ratio(subquery_tokens, candidate_summary_tokens)
        text_overlap = keyword_overlap_ratio(subquery_tokens, candidate_text_tokens)
        if max(title_overlap, summary_overlap, text_overlap) >= 0.18:
            coverage_hits += 1
    return coverage_hits / len(subqueries)


def rerank_candidates(
    query: str,
    candidates: list[RerankCandidate],
    *,
    top_k: int = 10,
    query_understanding: QueryUnderstanding | None = None,
) -> list[RerankCandidate]:
    query_tokens = tokenize(query)
    query_article_mentions = _query_article_mentions(query)
    query_topics = query_understanding.detected_topics if query_understanding else []
    subqueries = query_understanding.subqueries if query_understanding else [query]

    for candidate in candidates:
        title_tokens = tokenize(candidate.title)
        summary_tokens = tokenize(candidate.summary)
        text_tokens = tokenize(candidate.text[:2000])
        title_overlap = keyword_overlap_ratio(query_tokens, title_tokens)
        summary_overlap = keyword_overlap_ratio(query_tokens, summary_tokens)
        text_overlap = keyword_overlap_ratio(query_tokens, text_tokens)
        exact_article_boost = 0.35 if candidate.article_number in query_article_mentions else 0.0
        topic_match = _topic_match_score(query_topics, candidate.metadata.get("article_topics", []))
        subquery_coverage = _subquery_coverage_score(subqueries, candidate)

        candidate.final_score = (
            0.48 * candidate.vector_score
            + 0.23 * candidate.graph_score
            + 0.10 * title_overlap
            + 0.08 * summary_overlap
            + 0.04 * text_overlap
            + 0.04 * topic_match
            + 0.03 * subquery_coverage
            + exact_article_boost
        )

        if title_overlap:
            candidate.reasons.append("title_overlap")
        if summary_overlap:
            candidate.reasons.append("summary_overlap")
        if text_overlap:
            candidate.reasons.append("text_overlap")
        if exact_article_boost:
            candidate.reasons.append("explicit_article_reference")
        if topic_match:
            candidate.reasons.append("topic_match")
        if subquery_coverage:
            candidate.reasons.append("subquery_coverage")

    unique_candidates = {}
    for candidate in candidates:
        existing = unique_candidates.get(candidate.article_number)
        if not existing or candidate.final_score > existing.final_score:
            unique_candidates[candidate.article_number] = candidate

    ranked = sorted(
        unique_candidates.values(),
        key=lambda candidate: candidate.final_score,
        reverse=True,
    )
    return ranked[:top_k]
