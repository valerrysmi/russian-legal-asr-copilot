"""Console demo for the LangGraph-based legal copilot on transcript chunks."""

from __future__ import annotations

import argparse
import sys
from contextlib import redirect_stdout
from pathlib import Path

from legal_copilot.agents.context_manager import StreamingContextManager
from legal_copilot.api.server import _build_windows
from legal_copilot.ingestion.transcript_cleaner import parse_transcript_with_options
from legal_copilot.orchestration.graph import run_legal_copilot_turn

DEFAULT_TRANSCRIPT_PATH = Path("legal_copilot/data/transcript_1.txt")


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


def shorten(text: str, limit: int = 220) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3].rstrip(' ,;:')}..."


def render_chunk(turns) -> str:
    lines = []
    for turn in turns:
        speaker = turn.raw_speaker or turn.speaker
        chunk = turn.metadata.get("chunk")
        if chunk:
            lines.append(f"[{speaker}] ({chunk}): {turn.text}")
        else:
            lines.append(f"{speaker}: {turn.text}")
    return "\n".join(lines)


def print_hit(indent: str, hit) -> None:
    print(f"{indent}- art. {hit.article_number}: {hit.title} ({hit.final_score:.3f})")
    if hit.summary:
        print(f"{indent}  summary: {shorten(hit.summary, limit=140)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the LangGraph legal copilot over transcript windows."
    )
    parser.add_argument(
        "--transcript",
        type=Path,
        default=DEFAULT_TRANSCRIPT_PATH,
        help="Path to transcript file.",
    )
    parser.add_argument(
        "--window-size",
        type=int,
        default=4,
        help="Number of transcript turns per window.",
    )
    parser.add_argument(
        "--stride",
        type=int,
        default=3,
        help="Step between neighboring windows.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional limit for the number of printed windows. 0 means all windows.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to a .txt file where demo output will also be saved.",
    )
    return parser


def run_demo(args: argparse.Namespace) -> None:
    if not args.transcript.exists():
        raise SystemExit(f"Transcript file not found: {args.transcript}")

    parsed = parse_transcript_with_options(args.transcript, merge_turns=False)
    windows = _build_windows(parsed.turns, window_size=args.window_size, stride=args.stride)
    if args.limit > 0:
        windows = windows[: args.limit]

    session = StreamingContextManager(session_id="langgraph-demo")

    print("LANGGRAPH TRANSCRIPT DEMO")
    print(f"transcript_path: {args.transcript}")
    print(f"turn_count: {len(parsed.turns)}")
    print(f"window_count: {len(windows)}")

    for name, chunk_turns in windows:
        chunk = render_chunk(chunk_turns)
        result = run_legal_copilot_turn(chunk, context_manager=session, session_id="langgraph-demo")

        print(f"\n=== {name} ===")
        print("chunk:")
        print(chunk)
        print(f"route: {result.route}")

        if result.extracted_question:
            print(f"primary_question: {result.extracted_question.normalized_question}")
            print(f"confidence: {result.extracted_question.confidence:.2f}")
            if result.extracted_question.detected_questions:
                print("detected_questions:")
                for question in result.extracted_question.detected_questions:
                    print(f"  - {question}")

        if result.extracted_questions and len(result.extracted_questions) > 1:
            print("extracted_questions:")
            for index, question in enumerate(result.extracted_questions, start=1):
                print(
                    f"  {index}. {question.normalized_question}"
                    f" | is_question={question.is_question}"
                    f" | clarify={question.needs_clarification}"
                )

        if result.retrieval_requests and len(result.retrieval_requests) > 1:
            print("retrieval_requests:")
            for index, request in enumerate(result.retrieval_requests, start=1):
                print(f"  {index}. {request.query_text}")
        elif result.retrieval_request:
            print("retrieval_request:")
            print(result.retrieval_request.query_text)

        if result.retrieved_contexts and len(result.retrieved_contexts) > 1:
            print("per_question_articles:")
            for index, retrieved_context in enumerate(result.retrieved_contexts, start=1):
                print(f"  query_{index}:")
                if result.retrieval_requests and index - 1 < len(result.retrieval_requests):
                    print(f"    request: {shorten(result.retrieval_requests[index - 1].query_text)}")
                for hit in retrieved_context.result.hits[:2]:
                    print_hit("    ", hit)
        elif result.retrieved_context:
            print("top_articles:")
            for hit in result.retrieved_context.result.hits[:3]:
                print_hit("  ", hit)

        if result.answer_text:
            print(f"answer: {result.answer_text}")

        if result.fact_check:
            print(
                "fact_check:",
                result.fact_check.grounded,
                f"confidence={result.fact_check.confidence:.2f}",
                f"citations={result.fact_check.cited_articles}",
            )

        if result.lawyer_phrase_check:
            print(
                "lawyer_phrase_check:",
                result.lawyer_phrase_check.status,
                f"grounded={result.lawyer_phrase_check.grounded}",
                f"confidence={result.lawyer_phrase_check.confidence:.2f}",
            )
            if result.lawyer_phrase_check.flagged_phrases:
                print("flagged_lawyer_phrases:")
                for phrase in result.lawyer_phrase_check.flagged_phrases:
                    print(f"  - {shorten(phrase, limit=180)}")

        if result.suggestions:
            if result.suggestions.clarification_question:
                print("clarification:", result.suggestions.clarification_question)
            print("branches:", ", ".join(result.suggestions.branch_recommendations))
            print("next_actions:", "; ".join(result.suggestions.next_actions))


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
