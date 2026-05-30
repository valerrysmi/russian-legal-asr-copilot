"""Step-by-step console demo for streaming transcript processing."""

from __future__ import annotations

import argparse
import sys
from contextlib import redirect_stdout
from pathlib import Path

from legal_copilot.agents.context_manager import StreamingContextManager
from legal_copilot.api.server import _build_windows
from legal_copilot.ingestion.transcript_cleaner import parse_transcript_with_options
from legal_copilot.orchestration.graph import run_legal_copilot_turn
from legal_copilot.orchestration.pipeline import process_transcript_chunk

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


def shorten(text: str, limit: int = 180) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3].rstrip(' ,;:')}..."


def print_rule(char: str = "=") -> None:
    print(char * 96)


def print_section(title: str) -> None:
    print()
    print(title)
    print_rule("-")


def format_turn(index: int, speaker: str, text: str) -> str:
    return f"[{index}] {speaker}: {text}"


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


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Show how streaming transcript chunks are processed step by step."
    )
    parser.add_argument(
        "--transcript",
        type=Path,
        default=DEFAULT_TRANSCRIPT_PATH,
        help="Path to transcript file.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=140,
        help="Chunk size for retrieval request building.",
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=20,
        help="Chunk overlap for retrieval request building.",
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
        help="Optional limit for the number of windows. 0 means all windows.",
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

    pipeline_session = StreamingContextManager(session_id="streaming-demo-pipeline")
    graph_session = StreamingContextManager(session_id="streaming-demo-graph")

    print("STREAMING TRANSCRIPT DEMO")
    print_rule("=")
    print(f"transcript_path: {args.transcript}")
    print(f"turn_count: {len(parsed.turns)}")
    print(f"window_count: {len(windows)}")

    for step_index, (name, window_turns) in enumerate(windows, start=1):
        chunk_text = render_chunk(window_turns)
        pipeline_result = process_transcript_chunk(
            chunk_text,
            context_manager=pipeline_session,
            chunk_size=args.chunk_size,
            overlap=args.overlap,
        )
        graph_result = run_legal_copilot_turn(
            chunk_text,
            context_manager=graph_session,
            session_id="streaming-demo-graph",
        )

        print_section(f"Step {step_index}. {name}")

        print("incoming_chunk:")
        print(chunk_text)

        print()
        print("parsed_turns:")
        for index, turn in enumerate(pipeline_result.parsed_turns, start=1):
            print(format_turn(index, turn.speaker, shorten(turn.text, limit=160)))

        print()
        print("appended_turns:")
        if pipeline_result.appended_turns:
            for index, turn in enumerate(pipeline_result.appended_turns, start=1):
                print(format_turn(index, turn.speaker, shorten(turn.text, limit=160)))
        else:
            print("<no new turns appended>")

        print()
        print("session_state:")
        print(f"parsed_turn_count: {pipeline_result.metadata['parsed_turn_count']}")
        print(f"appended_turn_count: {pipeline_result.metadata['appended_turn_count']}")
        print(f"session_turn_count: {pipeline_result.metadata['session_turn_count']}")
        print(f"active_user_query: {pipeline_result.active_user_query or '<empty>'}")
        print(
            "recent_context:"
            f" {shorten(pipeline_result.context_snapshot.recent_transcript, limit=260) or '<empty>'}"
        )

        if pipeline_result.context_snapshot.accumulated_user_facts:
            print("accumulated_user_facts:")
            for fact in pipeline_result.context_snapshot.accumulated_user_facts[-3:]:
                print(f"  - {shorten(fact, limit=140)}")

        if graph_result.extracted_questions:
            print()
            print("extracted_questions:")
            for index, question in enumerate(graph_result.extracted_questions, start=1):
                print(
                    f"  {index}. {question.normalized_question}"
                    f" | is_question={question.is_question}"
                    f" | clarify={question.needs_clarification}"
                )

        print()
        print("retrieval_requests:")
        if graph_result.retrieval_requests:
            for index, request in enumerate(graph_result.retrieval_requests, start=1):
                print(f"  {index}. {shorten(request.query_text, limit=320)}")
                if request.reasons:
                    print(f"     reasons: {', '.join(request.reasons)}")
                print(f"     query_chunk_count: {len(request.query_chunks)}")
        else:
            print("<not created>")
            continue

        print()
        print("article_search:")
        print("  status: started")
        retrieved_contexts = graph_result.retrieved_contexts or (
            [graph_result.retrieved_context] if graph_result.retrieved_context else []
        )
        print("  status: finished")
        print(f"  retrieval_count: {len(retrieved_contexts)}")

        for retrieval_index, retrieved_context in enumerate(retrieved_contexts, start=1):
            request = (
                graph_result.retrieval_requests[retrieval_index - 1]
                if graph_result.retrieval_requests and retrieval_index - 1 < len(graph_result.retrieval_requests)
                else None
            )
            hits = retrieved_context.result.hits
            diagnostics = retrieved_context.result.diagnostics
            print(f"  retrieval_{retrieval_index}:")
            if request:
                print(f"    query: {shorten(request.query_text, limit=220)}")
            print(f"    found_articles: {len(hits)}")
            if diagnostics.get("detected_topics"):
                print(f"    detected_topics: {diagnostics.get('detected_topics')}")
            if diagnostics.get("query_type"):
                print(f"    query_type: {diagnostics.get('query_type')}")
            if hits:
                print("    top_articles:")
                for index, hit in enumerate(hits[:2], start=1):
                    print(
                        f"      [{index}] art. {hit.article_number} - {shorten(hit.title, limit=90)} "
                        f"(score={hit.final_score:.3f})"
                    )
                    if hit.summary:
                        print(f"           summary: {shorten(hit.summary, limit=120)}")
            else:
                print("    <no articles found>")

        print()
        print("answer_generation:")
        print("  status: finished")
        print(f"  source: {graph_result.answer_source or '<unknown>'}")
        if graph_result.answer_generation_error:
            print(f"  error: {graph_result.answer_generation_error}")
        if graph_result.answer_text:
            print(f"  answer: {shorten(graph_result.answer_text, limit=320)}")
        else:
            print("  <no answer generated>")

        if graph_result.fact_check:
            print(
                "  fact_check:"
                f" grounded={graph_result.fact_check.grounded},"
                f" confidence={graph_result.fact_check.confidence:.2f},"
                f" cited_articles={graph_result.fact_check.cited_articles}"
            )

        if graph_result.lawyer_phrase_check:
            print("lawyer_phrase_check:")
            print(f"  status: {graph_result.lawyer_phrase_check.status}")
            print(f"  grounded: {graph_result.lawyer_phrase_check.grounded}")
            print(f"  confidence: {graph_result.lawyer_phrase_check.confidence:.2f}")
            if graph_result.lawyer_phrase_check.reviewed_phrases:
                print("  reviewed_phrases:")
                for phrase in graph_result.lawyer_phrase_check.reviewed_phrases:
                    print(f"    - {shorten(phrase, limit=220)}")
            if graph_result.lawyer_phrase_check.flagged_phrases:
                print("  flagged_phrases:")
                for phrase in graph_result.lawyer_phrase_check.flagged_phrases:
                    print(f"    - {shorten(phrase, limit=220)}")

    print()
    print_rule("=")
    print("Demo complete.")


def main() -> None:
    args = build_argument_parser().parse_args()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8") as output_file:
            with redirect_stdout(Tee(sys.stdout, output_file)):
                run_demo(args)
        return
    run_demo(args)


if __name__ == "__main__":
    main()
