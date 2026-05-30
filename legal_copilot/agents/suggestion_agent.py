"""Suggestion agent for next steps, clarifications, and nonlinear branches."""

from __future__ import annotations

from dataclasses import dataclass, field

from legal_copilot.agents.fact_checker import FactCheckResult
from legal_copilot.agents.statement_extractor import ExtractedQuestion
from legal_copilot.rag.hybrid_retriever import HybridRetrievalResult


@dataclass
class SuggestionBundle:
    clarification_question: str | None = None
    next_actions: list[str] = field(default_factory=list)
    branch_recommendations: list[str] = field(default_factory=list)


def build_suggestions(
    extracted_question: ExtractedQuestion,
    retrieval_result: HybridRetrievalResult | None,
    fact_check_result: FactCheckResult | None,
) -> SuggestionBundle:
    next_actions: list[str] = []
    branch_recommendations: list[str] = []
    clarification_question: str | None = None

    if extracted_question.needs_clarification:
        clarification_question = (
            "Уточните, пожалуйста, какой именно аспект важен: порядок сделки, корпоративное одобрение, "
            "нотариальная форма или риски для кредиторов?"
        )
        branch_recommendations.append("clarification_branch")

    if retrieval_result and retrieval_result.hits:
        next_actions.append("Показать клиенту 3-5 наиболее релевантных статей ГК РФ.")
        next_actions.append("Сформировать краткий ответ с привязкой к статьям и практическим шагам.")
        branch_recommendations.append("grounded_answer_branch")

    if fact_check_result and not fact_check_result.grounded:
        next_actions.append("Попросить дополнительный контекст или уточняющие факты до финального ответа.")
        branch_recommendations.append("low_confidence_review_branch")

    if extracted_question.extracted_facts:
        next_actions.append("Сохранить факты клиента в рабочем контексте для следующих live-реплик.")

    return SuggestionBundle(
        clarification_question=clarification_question,
        next_actions=next_actions,
        branch_recommendations=sorted(set(branch_recommendations)),
    )
