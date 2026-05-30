"""Demo runner for processing Alena ASR transcript.json with LegalCopilot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from legal_copilot.agents.context_manager import StreamingContextManager
from legal_copilot.integrations.asr_adapter import (
    asdict_chunk,
    convert_alena_transcript_to_chunks,
    render_chunk_as_transcript,
)
from legal_copilot.orchestration.graph import run_legal_copilot_turn


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run LegalCopilot directly on transcript.json produced by the Alena ASR service."
    )
    parser.add_argument(
        "--transcript-json",
        type=Path,
        required=True,
        help="Path to transcript.json produced by alena/legal_asr_service.",
    )
    parser.add_argument(
        "--window-size",
        type=int,
        default=4,
        help="Number of normalized utterances per chunk.",
    )
    parser.add_argument(
        "--stride",
        type=int,
        default=3,
        help="Step between neighboring chunks.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional limit on number of chunks to process. 0 means all chunks.",
    )
    parser.add_argument(
        "--dump-normalized",
        type=Path,
        default=None,
        help="Optional path to save normalized chunks as JSON.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    chunks = convert_alena_transcript_to_chunks(
        args.transcript_json,
        window_size=args.window_size,
        stride=args.stride,
    )
    if args.limit > 0:
        chunks = chunks[: args.limit]

    if args.dump_normalized:
        payload = [asdict_chunk(chunk) for chunk in chunks]
        args.dump_normalized.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    session = StreamingContextManager(session_id="alena-integration-demo")
    print("ALENA -> LEGAL_COPILOT DEMO")
    print(f"transcript_json: {args.transcript_json}")
    print(f"chunk_count: {len(chunks)}")

    for chunk in chunks:
        chunk_text = render_chunk_as_transcript(chunk)
        result = run_legal_copilot_turn(
            chunk_text,
            context_manager=session,
            session_id="alena-integration-demo",
        )
        print(f"\n=== {chunk.chunk_id} ===")
        print(chunk_text)
        print(f"route: {result.route}")
        if result.extracted_question:
            print(f"question: {result.extracted_question.normalized_question}")
        if result.answer_text:
            print(f"answer: {result.answer_text}")
        if result.fact_check:
            print(
                f"grounded: {result.fact_check.grounded}, "
                f"confidence={result.fact_check.confidence:.2f}"
            )


if __name__ == "__main__":
    main()
