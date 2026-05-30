"""LangGraph multi-agent orchestration for live legal copilot processing."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from legal_copilot.agents.answer_synthesis_agent import synthesize_answer_with_llm
from legal_copilot.agents.context_manager import ContextSnapshot, StreamingContextManager
from legal_copilot.agents.fact_checker import FactCheckResult, check_answer_grounding
from legal_copilot.agents.legal_domain_agent import LegalDomainAssessment, assess_legal_domain
from legal_copilot.agents.lawyer_phrase_checker import (
    LawyerPhraseCheckResult,
    check_lawyer_phrases_grounding,
)
from legal_copilot.agents.retriever import (
    RetrievalRequest,
    RetrievedLegalContext,
    build_retrieval_request,
    build_retrieval_request_from_extracted_question,
    retrieve_legal_context,
)
from legal_copilot.agents.statement_extractor import (
    ExtractedQuestion,
    extract_client_question,
    extract_client_questions_from_chunk,
)
from legal_copilot.agents.suggestion_agent import SuggestionBundle, build_suggestions
from legal_copilot.orchestration.pipeline import StreamingPipelineResult, process_transcript_chunk


class LegalCopilotGraphState(TypedDict, total=False):
    session_id: str
    raw_chunk: Any
    context_manager: StreamingContextManager
    streaming_result: StreamingPipelineResult
    context_snapshot: ContextSnapshot
    extracted_question: ExtractedQuestion
    extracted_questions: list[ExtractedQuestion]
    legal_domain_assessment: LegalDomainAssessment
    retrieval_request: RetrievalRequest
    retrieval_requests: list[RetrievalRequest]
    retrieved_context: RetrievedLegalContext
    retrieved_contexts: list[RetrievedLegalContext]
    answer_text: str
    answer_source: str
    answer_generation_error: str | None
    fact_check: FactCheckResult
    lawyer_phrase_check: LawyerPhraseCheckResult
    suggestions: SuggestionBundle
    route: str
    errors: list[str]


@dataclass
class LegalCopilotTurnResult:
    session_id: str
    context_snapshot: ContextSnapshot
    extracted_question: ExtractedQuestion | None
    extracted_questions: list[ExtractedQuestion] | None
    legal_domain_assessment: LegalDomainAssessment | None
    retrieval_request: RetrievalRequest | None
    retrieval_requests: list[RetrievalRequest] | None
    retrieved_context: RetrievedLegalContext | None
    retrieved_contexts: list[RetrievedLegalContext] | None
    answer_text: str | None
    answer_source: str | None
    answer_generation_error: str | None
    fact_check: FactCheckResult | None
    lawyer_phrase_check: LawyerPhraseCheckResult | None
    suggestions: SuggestionBundle | None
    route: str
    errors: list[str] = field(default_factory=list)


def ingest_chunk_node(state: LegalCopilotGraphState) -> LegalCopilotGraphState:
    context_manager = state.get("context_manager") or StreamingContextManager(
        session_id=state.get("session_id", "default")
    )
    streaming_result = process_transcript_chunk(
        state["raw_chunk"],
        context_manager=context_manager,
    )
    return {
        "context_manager": context_manager,
        "streaming_result": streaming_result,
        "context_snapshot": streaming_result.context_snapshot,
        "errors": [],
    }


def question_extractor_node(state: LegalCopilotGraphState) -> LegalCopilotGraphState:
    extracted_questions = extract_client_questions_from_chunk(
        state.get("raw_chunk"),
        snapshot=state["context_snapshot"],
    )
    extracted_question = extract_client_question(
        state["context_snapshot"],
        raw_chunk=state.get("raw_chunk"),
    )
    return {
        "extracted_question": extracted_question,
        "extracted_questions": extracted_questions,
    }


def legal_domain_node(state: LegalCopilotGraphState) -> LegalCopilotGraphState:
    extracted_question = state["extracted_question"]
    assessment = assess_legal_domain(extracted_question.normalized_question)
    result: LegalCopilotGraphState = {"legal_domain_assessment": assessment}

    if assessment and not assessment.can_answer_from_civil_code:
        warning = (
            "domain_warning: вопрос может регулироваться не только ГК РФ; "
            "для точного ответа полезно свериться с более специальным законодательством."
        )
        result["errors"] = [*state.get("errors", []), warning]

    return result


def route_after_domain(
    state: LegalCopilotGraphState,
) -> Literal["retrieve", "clarify", "idle", "out_of_scope"]:
    extracted_question = state["extracted_question"]
    if not extracted_question.normalized_question:
        return "idle"
    if extracted_question.needs_clarification or not extracted_question.is_question:
        return "clarify"
    return "retrieve"


def retrieval_node(state: LegalCopilotGraphState) -> LegalCopilotGraphState:
    extracted_questions = state.get("extracted_questions") or []
    candidate_questions = [
        question
        for question in extracted_questions
        if question.is_question
        and (
            not question.needs_clarification
            or question.normalized_question.strip().endswith("?")
        )
    ]
    if not candidate_questions:
        candidate_questions = extracted_questions

    requests: list[RetrievalRequest] = []
    seen_queries: set[str] = set()
    for question in candidate_questions:
        request = build_retrieval_request_from_extracted_question(
            question,
            state["context_snapshot"],
        )
        if not request:
            continue
        key = request.query_text.strip().lower()
        if not key or key in seen_queries:
            continue
        seen_queries.add(key)
        requests.append(request)

    if not requests:
        fallback_request = build_retrieval_request_from_extracted_question(
            state["extracted_question"],
            state["context_snapshot"],
        )
        if fallback_request:
            requests.append(fallback_request)

    if not requests:
        fallback_request = build_retrieval_request(state["context_snapshot"])
        if fallback_request:
            requests.append(fallback_request)

    if not requests:
        return {
            "route": "idle",
            "errors": ["retrieval_request_not_created"],
        }

    retrieved_contexts = [retrieve_legal_context(request, top_k=5) for request in requests]
    retrieval_request = requests[0]
    retrieved_context = retrieved_contexts[0]
    return {
        "retrieval_request": retrieval_request,
        "retrieval_requests": requests,
        "retrieved_context": retrieved_context,
        "retrieved_contexts": retrieved_contexts,
        "route": "retrieve",
    }


def _compress_text_for_answer(text: str, limit: int = 280) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    truncated = compact[: limit - 3].rstrip(" ,;:")
    return f"{truncated}..."


def _normalize_basis_text(text: str) -> str:
    normalized = " ".join((text or "").split())
    prefixes = (
        "Регулирует вопросы, связанные с ",
        "Регулирует вопросы, связанные со ",
    )
    for prefix in prefixes:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    return normalized[:1].lower() + normalized[1:] if normalized else normalized


def _build_article_basis(hit: Any) -> str:
    basis_text = _normalize_basis_text(hit.summary or hit.text)
    basis_text = _compress_text_for_answer(basis_text, limit=220)
    return f"Статья {hit.article_number} ГК РФ ({hit.title}) указывает, что {basis_text}"


def _build_article_relevance_note(hit: Any) -> str:
    rerank_reason = hit.metadata.get("llm_rerank_reason")
    if rerank_reason:
        return rerank_reason
    if hit.reasons:
        return f"Статья попала в выборку по причинам: {', '.join(hit.reasons[:5])}."
    return ""


def _build_multi_question_template_answer(
    extracted_questions: list[ExtractedQuestion],
    retrieved_contexts: list[RetrievedLegalContext],
) -> str:
    sections: list[str] = []
    for index, (question, retrieved_context) in enumerate(
        zip(extracted_questions, retrieved_contexts),
        start=1,
    ):
        hits = retrieved_context.result.hits[:3]
        if not hits:
            sections.append(
                f"{index}. По вопросу «{question.normalized_question}» пока не нашлось достаточно релевантных статей для уверенного предварительного вывода."
            )
            continue

        primary_hit = hits[0]
        text = (
            f"{index}. По вопросу «{question.normalized_question}» в первую очередь стоит ориентироваться на ст. "
            f"{primary_hit.article_number} ГК РФ «{primary_hit.title}». "
            f"{_normalize_basis_text(_compress_text_for_answer(primary_hit.summary or primary_hit.text, limit=190))}."
        )
        if len(hits) > 1:
            supporting_refs = ", ".join(f"ст. {hit.article_number}" for hit in hits[1:])
            text += f" Дополнительно контекст уточняют {supporting_refs}."
        sections.append(text)

    intro = "В этом фрагменте вижу несколько отдельных вопросов клиента, поэтому предварительный ответ лучше разбить по пунктам."
    return intro + "\n\n" + "\n\n".join(sections)


def answer_synthesis_node(state: LegalCopilotGraphState) -> LegalCopilotGraphState:
    extracted_question = state["extracted_question"]
    extracted_questions = state.get("extracted_questions") or []
    retrieved_context = state.get("retrieved_context")
    retrieved_contexts = state.get("retrieved_contexts") or (
        [retrieved_context] if retrieved_context else []
    )
    if not retrieved_context or not retrieved_context.result.hits:
        answer_text = (
            f"Сейчас вижу вопрос клиента: {extracted_question.normalized_question}. "
            "Пока не нашлось достаточно релевантных статей, чтобы уверенно дать содержательный правовой ответ. "
            "Лучше уточнить факты сделки и сузить запрос, после чего повторить поиск."
        )
        return {
            "answer_text": answer_text,
            "answer_source": "template_fallback",
            "answer_generation_error": "no_retrieved_hits",
        }

    if len(extracted_questions) > 1 and retrieved_contexts:
        aggregated_hits: list[Any] = []
        seen_articles: set[str] = set()
        for context in retrieved_contexts:
            for hit in context.result.hits:
                if hit.article_number in seen_articles:
                    continue
                seen_articles.add(hit.article_number)
                aggregated_hits.append(hit)
        top_hits = aggregated_hits[:6]
        combined_question = "\n".join(
            f"{index}. {question.normalized_question}"
            for index, question in enumerate(extracted_questions, start=1)
            if question.normalized_question
        )
        llm_answer = synthesize_answer_with_llm(
            combined_question,
            top_hits[:4],
        )
        if llm_answer.answer_text:
            return {
                "answer_text": llm_answer.answer_text,
                "answer_source": llm_answer.source,
                "answer_generation_error": llm_answer.error,
            }
        return {
            "answer_text": _build_multi_question_template_answer(
                extracted_questions,
                retrieved_contexts,
            ),
            "answer_source": "multi_question_template",
            "answer_generation_error": llm_answer.error,
        }

    top_hits = retrieved_context.result.hits[:4]
    llm_answer = synthesize_answer_with_llm(
        extracted_question.normalized_question,
        top_hits,
    )
    if llm_answer.answer_text:
        return {
            "answer_text": llm_answer.answer_text,
            "answer_source": llm_answer.source,
            "answer_generation_error": llm_answer.error,
        }

    primary_hit = top_hits[0]
    supporting_hits = top_hits[1:]
    citations = ", ".join(
        f"ст. {hit.article_number} ГК РФ ({hit.title})" for hit in top_hits
    )
    primary_basis = _build_article_basis(primary_hit)
    primary_note = _build_article_relevance_note(primary_hit)
    supporting_basis = " ".join(_build_article_basis(hit) for hit in supporting_hits)
    supporting_notes = " ".join(
        note for note in (_build_article_relevance_note(hit) for hit in supporting_hits) if note
    )
    answer_text = (
        f"По этому вопросу я бы предварительно ориентировался прежде всего на {citations}. "
        f"Если отвечать клиенту вслух, базовый ответ можно сформулировать так: в первую очередь нужно смотреть норму статьи «{primary_hit.title}», "
        "поэтому вывод нужно строить от текста конкретных статей, а не от общего представления о сделке. "
        f"{primary_basis}. "
        f"{primary_note} "
        f"{supporting_basis} "
        f"{supporting_notes} "
        "Предварительный практический вывод: сначала нужно проверить, подпадает ли конкретная сделка под требования о форме и порядке перехода права, "
        "а затем отдельно оценить последствия несоблюдения этих требований и специальные ограничения из устава, корпоративных решений и документов по сделке."
    )
    return {
        "answer_text": answer_text,
        "answer_source": "template_fallback",
        "answer_generation_error": llm_answer.error,
    }


def fact_check_node(state: LegalCopilotGraphState) -> LegalCopilotGraphState:
    retrieved_context = state.get("retrieved_context")
    retrieved_contexts = state.get("retrieved_contexts") or (
        [retrieved_context] if retrieved_context else []
    )
    aggregated_hits: list[Any] = []
    seen_articles: set[str] = set()
    for context in retrieved_contexts:
        if not context:
            continue
        for hit in context.result.hits:
            if hit.article_number in seen_articles:
                continue
            seen_articles.add(hit.article_number)
            aggregated_hits.append(hit)
    fact_check = check_answer_grounding(
        state.get("answer_text", ""),
        aggregated_hits,
    )
    return {"fact_check": fact_check}


def lawyer_phrase_check_node(state: LegalCopilotGraphState) -> LegalCopilotGraphState:
    retrieved_context = state.get("retrieved_context")
    retrieved_contexts = state.get("retrieved_contexts") or (
        [retrieved_context] if retrieved_context else []
    )
    aggregated_hits: list[Any] = []
    seen_articles: set[str] = set()
    for context in retrieved_contexts:
        if not context:
            continue
        for hit in context.result.hits:
            if hit.article_number in seen_articles:
                continue
            seen_articles.add(hit.article_number)
            aggregated_hits.append(hit)

    lawyer_phrase_check = check_lawyer_phrases_grounding(
        state["context_snapshot"],
        aggregated_hits,
    )
    return {"lawyer_phrase_check": lawyer_phrase_check}


def route_after_fact_check(state: LegalCopilotGraphState) -> Literal["suggest", "low_confidence_review"]:
    fact_check = state.get("fact_check")
    if fact_check and not fact_check.grounded:
        return "low_confidence_review"
    return "suggest"


def low_confidence_review_node(state: LegalCopilotGraphState) -> LegalCopilotGraphState:
    answer_text = (
        f"{state.get('answer_text', '')} "
        "Но текущая подборка норм покрывает вопрос только частично, поэтому ответ стоит считать предварительным "
        "и лучше дополнительно проверить специальные нормы, уставные ограничения и фактические документы по сделке."
    ).strip()
    return {
        "route": "low_confidence_review",
        "answer_text": answer_text,
    }


def clarify_node(state: LegalCopilotGraphState) -> LegalCopilotGraphState:
    extracted_question = state["extracted_question"]
    answer_text = (
        "Текущий кусок транскрипции выглядит как неполный или еще не до конца сформулированный вопрос. "
        "Нужна короткая уточняющая реплика, прежде чем отдавать финальный правовой ответ."
    )
    suggestions = build_suggestions(extracted_question, None, None)
    return {
        "route": "clarify",
        "answer_text": answer_text,
        "suggestions": suggestions,
    }


def out_of_scope_node(state: LegalCopilotGraphState) -> LegalCopilotGraphState:
    extracted_question = state["extracted_question"]
    assessment = state.get("legal_domain_assessment")
    if assessment:
        domain_label = assessment.primary_domain_label
        if assessment.gk_coverage == "partial":
            answer_text = (
                f"Вопрос клиента: {extracted_question.normalized_question}. "
                f"По предварительной классификации это в первую очередь {domain_label}. "
                "ГК РФ здесь может помочь только частично, но полного и надежного ответа только по гражданскому кодексу дать нельзя. "
                "Нужны специальные нормы профильного закона или кодекса."
            )
        else:
            answer_text = (
                f"Вопрос клиента: {extracted_question.normalized_question}. "
                f"По предварительной классификации это {domain_label}, а не гражданское право. "
                "Поэтому корректный ответ нельзя строить только на базе ГК РФ: нужно обращаться к профильному кодексу или специальному закону."
            )
    else:
        answer_text = (
            "Текущий вопрос не выглядит как вопрос, на который можно корректно отвечать только по ГК РФ. "
            "Нужна проверка профильной отрасли права и специального закона."
        )

    suggestions = SuggestionBundle(
        next_actions=[
            "Определить профильный кодекс или специальный закон для этого вопроса.",
            "Не использовать ответ только по ГК РФ как окончательный.",
            "Собрать нормы профильной отрасли и перезапустить поиск по ним.",
        ],
        branch_recommendations=["non_gk_scope_branch"],
    )
    return {
        "route": "out_of_scope",
        "answer_text": answer_text,
        "suggestions": suggestions,
    }


def idle_node(state: LegalCopilotGraphState) -> LegalCopilotGraphState:
    return {
        "route": "idle",
        "answer_text": "Новый юридический вопрос клиента в этом окне пока не обнаружен; контекст просто обновлен.",
        "suggestions": SuggestionBundle(
            next_actions=["Продолжать накапливать контекст до появления следующего вопроса клиента."],
            branch_recommendations=["context_accumulation_branch"],
        ),
    }


def suggestion_node(state: LegalCopilotGraphState) -> LegalCopilotGraphState:
    suggestions = build_suggestions(
        state["extracted_question"],
        state.get("retrieved_context").result if state.get("retrieved_context") else None,
        state.get("fact_check"),
    )
    lawyer_phrase_check = state.get("lawyer_phrase_check")
    if lawyer_phrase_check and lawyer_phrase_check.status == "needs_review":
        suggestions.next_actions.append(
            "Проверить содержательные фразы юриста: часть утверждений не получила достаточной опоры в найденных статьях."
        )
        suggestions.branch_recommendations = sorted(
            set([*suggestions.branch_recommendations, "lawyer_phrase_review_branch"])
        )
    return {"suggestions": suggestions}


def build_legal_copilot_graph():
    graph = StateGraph(LegalCopilotGraphState)
    graph.add_node("ingest_chunk", ingest_chunk_node)
    graph.add_node("extract_question", question_extractor_node)
    graph.add_node("assess_legal_domain", legal_domain_node)
    graph.add_node("retrieve", retrieval_node)
    graph.add_node("synthesize_answer", answer_synthesis_node)
    graph.add_node("fact_check", fact_check_node)
    graph.add_node("review_lawyer_phrases", lawyer_phrase_check_node)
    graph.add_node("low_confidence_review", low_confidence_review_node)
    graph.add_node("clarify", clarify_node)
    graph.add_node("out_of_scope", out_of_scope_node)
    graph.add_node("idle", idle_node)
    graph.add_node("suggest", suggestion_node)

    graph.add_edge(START, "ingest_chunk")
    graph.add_edge("ingest_chunk", "extract_question")
    graph.add_edge("extract_question", "assess_legal_domain")
    graph.add_conditional_edges(
        "assess_legal_domain",
        route_after_domain,
        {
            "retrieve": "retrieve",
            "clarify": "clarify",
            "idle": "idle",
            "out_of_scope": "out_of_scope",
        },
    )
    graph.add_edge("retrieve", "synthesize_answer")
    graph.add_edge("synthesize_answer", "fact_check")
    graph.add_edge("fact_check", "review_lawyer_phrases")
    graph.add_conditional_edges(
        "review_lawyer_phrases",
        route_after_fact_check,
        {
            "suggest": "suggest",
            "low_confidence_review": "low_confidence_review",
        },
    )
    graph.add_edge("low_confidence_review", "suggest")
    graph.add_edge("clarify", END)
    graph.add_edge("out_of_scope", END)
    graph.add_edge("idle", END)
    graph.add_edge("suggest", END)
    return graph.compile()


def run_legal_copilot_turn(
    raw_chunk: Any,
    *,
    context_manager: StreamingContextManager | None = None,
    session_id: str = "default",
):
    compiled_graph = build_legal_copilot_graph()
    initial_state: LegalCopilotGraphState = {
        "session_id": session_id,
        "raw_chunk": raw_chunk,
        "context_manager": context_manager or StreamingContextManager(session_id=session_id),
    }
    final_state = compiled_graph.invoke(initial_state)
    return LegalCopilotTurnResult(
        session_id=session_id,
        context_snapshot=final_state["context_snapshot"],
        extracted_question=final_state.get("extracted_question"),
        extracted_questions=final_state.get("extracted_questions"),
        legal_domain_assessment=final_state.get("legal_domain_assessment"),
        retrieval_request=final_state.get("retrieval_request"),
        retrieval_requests=final_state.get("retrieval_requests"),
        retrieved_context=final_state.get("retrieved_context"),
        retrieved_contexts=final_state.get("retrieved_contexts"),
        answer_text=final_state.get("answer_text"),
        answer_source=final_state.get("answer_source"),
        answer_generation_error=final_state.get("answer_generation_error"),
        fact_check=final_state.get("fact_check"),
        lawyer_phrase_check=final_state.get("lawyer_phrase_check"),
        suggestions=final_state.get("suggestions"),
        route=final_state.get("route", "unknown"),
        errors=final_state.get("errors", []),
    )


def demo_graph_on_transcript(
    transcript_path: Path = Path("legal_copilot/data/transcript.txt"),
    *,
    line_start: int = 40,
    line_end: int = 50,
) -> LegalCopilotTurnResult:
    lines = [line for line in transcript_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    window = "\n".join(lines[line_start:line_end])
    session = StreamingContextManager(session_id="langgraph-demo")
    return run_legal_copilot_turn(window, context_manager=session, session_id="langgraph-demo")
