"""Demo script for full and streaming transcript processing."""

from __future__ import annotations

from pathlib import Path

from legal_copilot.agents.context_manager import StreamingContextManager
from legal_copilot.orchestration.pipeline import (
    process_transcript_chunk,
    process_user_request,
)


TRANSCRIPT_PATH = Path("legal_copilot/data/transcript.txt")


def print_section(title: str) -> None:
    print(f"\n=== {title} ===")


def preview(text: str, limit: int = 220) -> str:
    single_line = text.replace("\n", " | ")
    return single_line[:limit] + ("..." if len(single_line) > limit else "")


def run_full_demo(transcript_path: Path) -> None:
    result = process_user_request(transcript_path)
    print_section("FULL TRANSCRIPT")
    print(f"turn_count: {len(result.normalized_turns)}")
    print(f"latest_user_query: {result.cleaned_user_query}")
    print(f"chunk_count: {len(result.query_chunks)}")


def run_streaming_demo(transcript_path: Path) -> None:
    lines = [line for line in transcript_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    session = StreamingContextManager(session_id="demo-stream")
    windows = [
        ("window_1", "\n".join(lines[1:5])),
        ("window_2", "\n".join(lines[4:9])),
        ("window_3", "\n".join(lines[8:13])),
        ("window_4", "\n".join(lines[12:17])),
    ]

    print_section("STREAMING WINDOWS")
    for name, window in windows:
        result = process_transcript_chunk(window, context_manager=session, chunk_size=140, overlap=20)
        print(
            f"[{name}] parsed={result.metadata['parsed_turn_count']} "
            f"appended={result.metadata['appended_turn_count']} "
            f"session_turns={result.metadata['session_turn_count']}"
        )
        print(f"active_user_query: {result.active_user_query}")
        if result.retrieval_request:
            print(f"retrieval_query: {preview(result.retrieval_request.query_text)}")
        print(f"recent_context: {preview(result.context_snapshot.recent_transcript, limit=180)}")
        print()


def run_dedup_demo(transcript_path: Path) -> None:
    lines = [line for line in transcript_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    repeat_window = "\n".join(lines[12:17])
    session = StreamingContextManager(session_id="dedup-check")

    first = process_transcript_chunk(repeat_window, context_manager=session)
    second = process_transcript_chunk(repeat_window, context_manager=session)

    print_section("OVERLAP / DEDUP")
    print(f"first_appended: {first.metadata['appended_turn_count']}")
    print(f"second_appended: {second.metadata['appended_turn_count']}")
    print(f"final_session_turns: {second.metadata['session_turn_count']}")


def main() -> None:
    if not TRANSCRIPT_PATH.exists():
        raise SystemExit(f"Transcript file not found: {TRANSCRIPT_PATH}")

    run_full_demo(TRANSCRIPT_PATH)
    run_streaming_demo(TRANSCRIPT_PATH)
    run_dedup_demo(TRANSCRIPT_PATH)


if __name__ == "__main__":
    main()
