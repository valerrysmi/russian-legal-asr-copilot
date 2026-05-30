"""Precompute cached demo payloads for the live transcript site."""

from __future__ import annotations

import argparse

from legal_copilot.api.server import (
    _list_transcript_paths,
    _log_demo,
    get_demo_payload,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Precompute demo payload JSON files for transcript demos."
    )
    parser.add_argument(
        "--transcript",
        action="append",
        dest="transcripts",
        help="Specific transcript filename to precompute. Can be passed multiple times.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Ignore cached JSON and rebuild payloads from scratch.",
    )
    return parser


def main() -> None:
    args = build_argument_parser().parse_args()
    transcript_names = (
        args.transcripts
        if args.transcripts
        else [path.name for path in _list_transcript_paths()]
    )

    _log_demo(
        "precompute.start",
        transcripts=len(transcript_names),
        refresh=args.refresh,
    )

    for transcript_name in transcript_names:
        _log_demo("precompute.transcript_start", transcript=transcript_name)
        payload = get_demo_payload(
            transcript_name,
            use_cache=not args.refresh,
            save_cache=True,
        )
        _log_demo(
            "precompute.transcript_done",
            transcript=transcript_name,
            steps=len(payload.get("steps", [])),
        )

    _log_demo("precompute.done", transcripts=len(transcript_names))


if __name__ == "__main__":
    main()
