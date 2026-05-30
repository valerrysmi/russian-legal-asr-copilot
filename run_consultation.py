"""Run ASR transcription and LegalCopilot processing as one command.

The ASR part expects its Redis/workers to be running separately. This wrapper
only coordinates the two existing project entry points and passes the generated
transcript from `russian-legal-asr` into `legal_copilot`.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
ASR_DIR = ROOT_DIR / "russian-legal-asr"
COPILOT_DIR = ROOT_DIR / "legal_copilot"
DEFAULT_ASR_DATA_DIR = ASR_DIR / "data"
DEFAULT_OUTPUT_ROOT = ROOT_DIR / "runs"
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
        description="Transcribe a consultation audio file and process the transcript with LegalCopilot."
    )
    parser.add_argument(
        "--audio",
        type=Path,
        help="Path to the source audio file. If omitted, ASR uses the existing ASR data directory.",
    )
    parser.add_argument(
        "--voices",
        type=Path,
        help="Optional directory with speaker enrollment files for ASR speaker identification.",
    )
    parser.add_argument(
        "--consultation",
        default="consultation1",
        help="Consultation id used under russian-legal-asr/data/input/<id>.",
    )
    parser.add_argument(
        "--asr-data-dir",
        type=Path,
        default=DEFAULT_ASR_DATA_DIR,
        help="ASR data directory containing input/ and output/ folders.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for generated transcript, timings, logs, and copilot output.",
    )
    parser.add_argument(
        "--skip-asr",
        action="store_true",
        help="Skip ASR and process an existing transcript.",
    )
    parser.add_argument(
        "--transcript",
        type=Path,
        help="Existing transcript path for --skip-asr, or override after ASR.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit LegalCopilot transcript windows. 0 means all windows.",
    )
    parser.add_argument(
        "--window-size",
        type=int,
        default=4,
        help="LegalCopilot transcript window size.",
    )
    parser.add_argument(
        "--stride",
        type=int,
        default=3,
        help="LegalCopilot transcript window stride.",
    )
    parser.add_argument(
        "--run-metrics",
        action="store_true",
        help="Run ASR metrics after transcription. Requires reference text in ASR data.",
    )
    return parser


def resolved(path: Path) -> Path:
    return path.expanduser().resolve()


def prepare_asr_input(audio: Path | None, voices: Path | None, consultation: str, data_dir: Path) -> str:
    input_dir = data_dir / "input" / consultation
    input_dir.mkdir(parents=True, exist_ok=True)

    audio_filename = "audio.mp3"
    if audio is not None:
        source_audio = resolved(audio)
        if not source_audio.exists():
            raise FileNotFoundError(f"Audio file not found: {source_audio}")
        audio_filename = source_audio.name
        target_audio = input_dir / audio_filename
        if source_audio != target_audio.resolve():
            shutil.copy2(source_audio, target_audio)
    else:
        audio_files = sorted(
            path
            for path in input_dir.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
        )
        if len(audio_files) == 1:
            audio_filename = audio_files[0].name
        elif not audio_files:
            raise FileNotFoundError(
                f"No audio file found in {input_dir}. Pass --audio with the audio path."
            )
        else:
            names = ", ".join(path.name for path in audio_files)
            raise ValueError(
                f"Multiple audio files found in {input_dir}: {names}. Pass --audio explicitly."
            )

    if voices is not None:
        source_voices = resolved(voices)
        if not source_voices.exists() or not source_voices.is_dir():
            raise FileNotFoundError(f"Voices directory not found: {source_voices}")
        target_voices = input_dir / "voices"
        if target_voices.exists():
            shutil.rmtree(target_voices)
        shutil.copytree(source_voices, target_voices)

    return audio_filename


def run_command(command: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    printable = " ".join(command)
    print(f"\n> {printable}", flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def run_asr(args: argparse.Namespace, output_dir: Path, audio_filename: str) -> Path:
    data_dir = resolved(args.asr_data_dir)
    transcript_path = output_dir / "transcript.txt"

    env = os.environ.copy()
    env.update(
        {
            "CONSULTATION": args.consultation,
            "DATA_DIR": str(data_dir),
            "OUTPUT_DIR": str(output_dir),
            "LOG_DIR": str(output_dir),
            "AUDIO_FILENAME": audio_filename,
            "RUN_METRICS": "true" if args.run_metrics else "false",
        }
    )

    run_command(
        [sys.executable, "-m", "gateway.gateway_simulator"],
        cwd=ASR_DIR,
        env=env,
    )

    if not transcript_path.exists():
        raise FileNotFoundError(f"ASR finished, but transcript was not created: {transcript_path}")
    return transcript_path


def run_copilot(args: argparse.Namespace, transcript_path: Path, output_dir: Path) -> Path:
    copilot_output = output_dir / "copilot_output.txt"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT_DIR)

    command = [
        sys.executable,
        "-m",
        "legal_copilot.orchestration.demo_langgraph",
        "--transcript",
        str(transcript_path),
        "--window-size",
        str(args.window_size),
        "--stride",
        str(args.stride),
        "--output",
        str(copilot_output),
    ]
    if args.limit > 0:
        command.extend(["--limit", str(args.limit)])

    run_command(command, cwd=ROOT_DIR, env=env)
    return copilot_output


def main() -> int:
    args = build_parser().parse_args()
    output_dir = resolved(args.output_dir or (DEFAULT_OUTPUT_ROOT / args.consultation))
    output_dir.mkdir(parents=True, exist_ok=True)

    transcript_path: Path
    if args.skip_asr:
        if args.transcript is None:
            raise SystemExit("--skip-asr requires --transcript")
        transcript_path = resolved(args.transcript)
        if not transcript_path.exists():
            raise FileNotFoundError(f"Transcript file not found: {transcript_path}")
    else:
        audio_filename = prepare_asr_input(
            args.audio,
            args.voices,
            args.consultation,
            resolved(args.asr_data_dir),
        )
        transcript_path = run_asr(args, output_dir, audio_filename)

    if args.transcript is not None and not args.skip_asr:
        transcript_path = resolved(args.transcript)

    copilot_output = run_copilot(args, transcript_path, output_dir)
    print("\nDone.")
    print(f"Transcript: {transcript_path}")
    print(f"Copilot output: {copilot_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
