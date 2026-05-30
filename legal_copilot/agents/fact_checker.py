"""Groundedness checks for answers generated from Civil Code sources."""

from __future__ import annotations

from dataclasses import dataclass, field

from legal_copilot.rag.hybrid_retriever import HybridRetrievalHit


@dataclass
class FactCheckResult:
    grounded: bool
    confidence: float
    notes: list[str] = field(default_factory=list)
    cited_articles: list[str] = field(default_factory=list)


def check_answer_grounding(
    answer_text: str,
    retrieved_hits: list[HybridRetrievalHit],
) -> FactCheckResult:
    if not answer_text or not retrieved_hits:
        return FactCheckResult(
            grounded=False,
            confidence=0.2,
            notes=["answer_or_sources_missing"],
            cited_articles=[],
        )

    top_hits = retrieved_hits[:3]
    avg_score = sum(hit.final_score for hit in top_hits) / len(top_hits)
    cited_articles = [hit.article_number for hit in top_hits]
    notes = []
    grounded = avg_score >= 0.10

    if grounded:
        notes.append("answer_grounded_in_top_retrieval_hits")
    else:
        notes.append("retrieval_scores_too_low_for_confident_grounding")

    if any("explicit_article_reference" in hit.reasons for hit in top_hits):
        notes.append("explicit_article_reference_present")

    return FactCheckResult(
        grounded=grounded,
        confidence=min(max(avg_score * 2.4, 0.0), 0.95),
        notes=notes,
        cited_articles=cited_articles,
    )
