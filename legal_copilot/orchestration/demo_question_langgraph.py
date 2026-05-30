"""Demo entrypoint for processing a standalone legal question via LangGraph."""

from __future__ import annotations

import argparse
import sys
from contextlib import redirect_stdout
from pathlib import Path

from legal_copilot.agents.context_manager import StreamingContextManager
from legal_copilot.orchestration.graph import run_legal_copilot_turn

DEFAULT_QUERY = "Нужно ли нотариальное удостоверение продажи доли в ООО?"


class Tee:
    def __init__(self, *streams) -> None:
        self.streams = streams

    def write(self, data: str) -> int:
        for stream in self.streams:
            stream.write(data)
        return len(data)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()


def shorten_text(text: str, limit: int = 320) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3].rstrip(' ,;:')}..."


def print_rule(char: str = "=") -> None:
    print(char * 88)


def print_section(title: str) -> None:
    print()
    print(title)


def print_box(title: str, text: str) -> None:
    lines = [line.rstrip() for line in (text or "").splitlines()] or [""]
    content_width = max(len(title), *(len(line) for line in lines))
    border = "+" + "-" * (content_width + 2) + "+"
    print(border)
    print(f"| {title.ljust(content_width)} |")
    print(border)
    for line in lines:
        print(f"| {line.ljust(content_width)} |")
    print(border)


def print_key_value(label: str, value: str) -> None:
    print(f"{label:<24} {value}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the LangGraph legal copilot on a standalone legal question."
    )
    parser.add_argument(
        "--query",
        default=DEFAULT_QUERY,
        help="A standalone legal question to process.",
    )
    parser.add_argument(
        "--session-id",
        default="question-demo",
        help="Session identifier used for the temporary context manager.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to a .txt file where demo output will also be saved.",
    )
    return parser


def print_retrieval_result(prefix: str, retrieved_context) -> None:
    retrieval_result = retrieved_context.result
    diagnostics = retrieval_result.diagnostics

    print_section(prefix)
    print_box("expanded_query", retrieval_result.expanded_query)

    if diagnostics:
        print("diagnostics:")
        for key in (
            "query_type",
            "detected_topics",
            "neural_embeddings_enabled",
            "llm_reranker_enabled",
            "llm_reranker_used",
            "llm_reranker_error",
        ):
            value = diagnostics.get(key)
            if value not in (None, [], ""):
                print_key_value(key, str(value))

    if retrieval_result.query_expansion.added_terms:
        print("added_terms:")
        for term in retrieval_result.query_expansion.added_terms:
            print(f"  - {term}")

    print()
    print("top_articles:")
    for index, hit in enumerate(retrieval_result.hits[:5], start=1):
        print()
        print(f"[{index}] ст. {hit.article_number} - {hit.title}")
        print_key_value("score", f"{hit.final_score:.3f}")
        print_key_value("vector_score", f"{hit.vector_score:.3f}")
        print_key_value("graph_score", f"{hit.graph_score:.3f}")
        chapter = hit.metadata.get("chapter")
        if chapter:
            print_key_value("chapter", chapter)
        if hit.reasons:
            print_key_value("reasons", ", ".join(hit.reasons))
        if hit.metadata.get("article_topics"):
            print_key_value("topics", ", ".join(hit.metadata["article_topics"]))
        if hit.metadata.get("llm_rerank_reason"):
            print_key_value("llm_rerank_reason", hit.metadata["llm_rerank_reason"])
        if hit.summary:
            print_key_value("summary", shorten_text(hit.summary, limit=260))
        if hit.text:
            print_key_value("article_text", shorten_text(hit.text, limit=420))


def run_demo(args: argparse.Namespace) -> None:
    session = StreamingContextManager(session_id=args.session_id)
    result = run_legal_copilot_turn(
        args.query,
        context_manager=session,
        session_id=args.session_id,
    )

    print("STANDALONE QUESTION DEMO")
    print_rule("=")
    print_key_value("session_id", args.session_id)
    print_key_value("route", result.route)
    if result.answer_source:
        print_key_value("answer_source", result.answer_source)
    if result.fact_check:
        print_key_value(
            "fact_check",
            f"grounded={result.fact_check.grounded}, confidence={result.fact_check.confidence:.2f}",
        )

    print_section("1. Input")
    print(args.query)

    if result.extracted_question:
        print_section("2. Question Extraction")
        extracted = result.extracted_question
        print_key_value("normalized_question", extracted.normalized_question or "<empty>")
        print_key_value("confidence", f"{extracted.confidence:.2f}")
        print_key_value("is_question", str(extracted.is_question))
        print_key_value("needs_clarification", str(extracted.needs_clarification))
        if extracted.reasoning:
            print_key_value("reasoning", ", ".join(extracted.reasoning))
        if extracted.detected_questions:
            print("detected_questions:")
            for question in extracted.detected_questions:
                print(f"  - {question}")

    if result.extracted_questions and len(result.extracted_questions) > 1:
        print_section("3. Extracted Questions")
        for index, question in enumerate(result.extracted_questions, start=1):
            print(
                f"{index}. {question.normalized_question}"
                f" | is_question={question.is_question}"
                f" | needs_clarification={question.needs_clarification}"
            )

    if result.retrieval_requests and len(result.retrieval_requests) > 1:
        print_section("4. Retrieval Requests")
        for index, request in enumerate(result.retrieval_requests, start=1):
            print(f"{index}. {request.query_text}")
            if request.reasons:
                print(f"   reasons: {', '.join(request.reasons)}")
    elif result.retrieval_request:
        print_section("4. Retrieval Request")
        print(result.retrieval_request.query_text)
        if result.retrieval_request.reasons:
            print("retrieval_reasons:")
            for reason in result.retrieval_request.reasons:
                print(f"  - {reason}")

    if result.retrieved_contexts and len(result.retrieved_contexts) > 1:
        for index, retrieved_context in enumerate(result.retrieved_contexts, start=1):
            prefix = f"5.{index} Per-Question Retrieval"
            if result.retrieval_requests and index - 1 < len(result.retrieval_requests):
                print_section(f"5.{index} Retrieval Query")
                print(result.retrieval_requests[index - 1].query_text)
            print_retrieval_result(prefix, retrieved_context)
    elif result.retrieved_context:
        print_retrieval_result("5. Retrieval Result", result.retrieved_context)

    if result.answer_text:
        print_section("6. Answer")
        if result.answer_generation_error:
            print_key_value("answer_generation_error", result.answer_generation_error)
        print_box("answer_text", result.answer_text)

    if result.fact_check:
        print_section("7. Fact Check")
        print_key_value("grounded", str(result.fact_check.grounded))
        print_key_value("confidence", f"{result.fact_check.confidence:.2f}")
        if result.fact_check.cited_articles:
            print_key_value("cited_articles", ", ".join(result.fact_check.cited_articles))

    if result.lawyer_phrase_check:
        print_section("8. Lawyer Phrase Check")
        print_key_value("status", result.lawyer_phrase_check.status)
        print_key_value("grounded", str(result.lawyer_phrase_check.grounded))
        print_key_value("confidence", f"{result.lawyer_phrase_check.confidence:.2f}")
        if result.lawyer_phrase_check.reviewed_phrases:
            print("reviewed_phrases:")
            for phrase in result.lawyer_phrase_check.reviewed_phrases:
                print(f"  - {shorten_text(phrase, limit=220)}")
        if result.lawyer_phrase_check.flagged_phrases:
            print("flagged_phrases:")
            for phrase in result.lawyer_phrase_check.flagged_phrases:
                print(f"  - {shorten_text(phrase, limit=220)}")

    if result.suggestions:
        print_section("9. Next Actions")
        if result.suggestions.clarification_question:
            print_box("clarification", result.suggestions.clarification_question)
        if result.suggestions.branch_recommendations:
            print("branches:")
            for branch in result.suggestions.branch_recommendations:
                print(f"  - {branch}")
        if result.suggestions.next_actions:
            print("next_actions:")
            for action in result.suggestions.next_actions:
                print(f"  - {action}")

    if result.errors:
        print_section("10. Errors")
        for error in result.errors:
            print(f"  - {error}")


def main() -> None:
    args = build_parser().parse_args()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8") as output_file:
            with redirect_stdout(Tee(sys.stdout, output_file)):
                run_demo(args)
        return
    run_demo(args)


if __name__ == "__main__":
    main()
