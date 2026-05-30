"""Run ASR and LegalCopilot in a near-real-time bridge.

Unlike `run_consultation.py`, this script does not wait for the full
transcript before calling LegalCopilot. Each completed ASR+speaker line is
sent to the LegalCopilot streaming pipeline as soon as the ASR gateway emits it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import redis


ROOT_DIR = Path(__file__).resolve().parent
ASR_DIR = ROOT_DIR / "russian-legal-asr"

sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ASR_DIR))

from gateway.pipeline import StreamingPipeline  # noqa: E402
from gateway.sources.file_source import FileAudioSource  # noqa: E402
from legal_copilot.agents.context_manager import StreamingContextManager  # noqa: E402
from legal_copilot.orchestration.graph import run_legal_copilot_turn  # noqa: E402
from legal_copilot.orchestration.pipeline import process_transcript_chunk  # noqa: E402


SUPPORTED_AUDIO_EXTENSIONS = {
    ".mp3",
    ".m4a",
    ".wav",
    ".flac",
    ".ogg",
    ".opus",
    ".aac",
    ".wma",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Stream ASR transcript lines into LegalCopilot as they arrive."
    )
    parser.add_argument("--consultation", default="consultation1")
    parser.add_argument("--audio", type=Path)
    parser.add_argument("--asr-data-dir", type=Path, default=ASR_DIR / "data")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--redis-host", default=os.getenv("REDIS_HOST", "localhost"))
    parser.add_argument("--redis-port", type=int, default=int(os.getenv("REDIS_PORT", "6379")))
    parser.add_argument("--vad-mode", choices=["none", "batched", "streaming"], default="streaming")
    parser.add_argument("--realtime-factor", type=float, default=0.0)
    parser.add_argument("--window-size", type=int, default=4)
    parser.add_argument("--stride", type=int, default=3)
    return parser


def find_audio(args: argparse.Namespace) -> Path:
    if args.audio:
        path = args.audio.expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path}")
        return path

    input_dir = args.asr_data_dir / "input" / args.consultation
    audio_files = sorted(
        path
        for path in input_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
    )
    if len(audio_files) == 1:
        return audio_files[0]
    if not audio_files:
        raise FileNotFoundError(f"No audio file found in {input_dir}")
    names = ", ".join(path.name for path in audio_files)
    raise ValueError(f"Multiple audio files found in {input_dir}: {names}. Pass --audio.")


def json_default(value: Any) -> Any:
    if hasattr(value, "__dict__"):
        return value.__dict__
    return str(value)


def main() -> int:
    args = build_parser().parse_args()
    audio_path = find_audio(args)
    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else ROOT_DIR / "runs" / f"{args.consultation}_realtime"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    transcript_path = output_dir / "transcript.txt"
    timings_path = output_dir / "timings.json"
    events_path = output_dir / "realtime_events.jsonl"

    redis_client = redis.Redis(
        host=args.redis_host,
        port=args.redis_port,
        decode_responses=True,
    )
    redis_client.ping()
    redis_client.delete("tasks:asr", "tasks:speaker", "results:asr", "results:speaker")

    copilot_pipeline_session = StreamingContextManager(
        session_id=f"realtime-pipeline-{args.consultation}"
    )
    copilot_graph_session = StreamingContextManager(
        session_id=f"realtime-graph-{args.consultation}"
    )

    recent_lines: list[str] = []

    def emit_event(payload: dict[str, Any]) -> None:
        with events_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False, default=json_default) + "\n")

    def on_line(payload: dict[str, Any]) -> None:
        speaker = payload.get("speaker") or "Unknown"
        chunk_id = payload.get("chunk_id") or ""
        text = payload.get("text") or ""
        if not text.strip():
            return

        transcript_line = f"[{speaker}] ({chunk_id}): {text}".strip()
        recent_lines.append(transcript_line)
        del recent_lines[:-args.window_size]
        chunk_text = "\n".join(recent_lines[-args.window_size :])

        started_at = time.perf_counter()
        pipeline_result = process_transcript_chunk(
            chunk_text,
            context_manager=copilot_pipeline_session,
            chunk_size=140,
            overlap=20,
        )
        graph_result = run_legal_copilot_turn(
            chunk_text,
            context_manager=copilot_graph_session,
            session_id=f"realtime-graph-{args.consultation}",
        )
        elapsed = time.perf_counter() - started_at

        event = {
            "type": "copilot_update",
            "seq": payload.get("seq"),
            "chunk_id": chunk_id,
            "speaker": speaker,
            "text": text,
            "window": chunk_text,
            "active_user_query": pipeline_result.active_user_query,
            "route": graph_result.route,
            "answer_text": graph_result.answer_text,
            "answer_source": graph_result.answer_source,
            "elapsed_s": round(elapsed, 4),
        }
        emit_event(event)
        print(
            f"[copilot] seq={payload.get('seq')} route={graph_result.route} "
            f"query={pipeline_result.active_user_query[:80]!r}",
            flush=True,
        )
        if graph_result.answer_text:
            print(f"[answer] {graph_result.answer_text}", flush=True)

    source = FileAudioSource(str(audio_path), realtime_factor=args.realtime_factor)
    pipeline = StreamingPipeline(
        source=source,
        redis_client=redis_client,
        output_path=str(transcript_path),
        timings_path=str(timings_path),
        vad_mode=args.vad_mode,
        on_line=on_line,
        meta={
            "consultation": args.consultation,
            "audio": str(audio_path),
            "mode": "realtime_bridge",
        },
    )

    emit_event(
        {
            "type": "start",
            "consultation": args.consultation,
            "audio": str(audio_path),
            "output_dir": str(output_dir),
        }
    )
    pipeline.run()
    emit_event({"type": "done", "transcript": str(transcript_path)})
    print(f"Done. Transcript: {transcript_path}")
    print(f"Realtime events: {events_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
