"""Unified local web UI for the ASR + LegalCopilot pipeline."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


ROOT_DIR = Path(__file__).resolve().parent
ASR_INPUT_DIR = ROOT_DIR / "russian-legal-asr" / "data" / "input"
RUNS_DIR = ROOT_DIR / "runs"
UI_DIR = ROOT_DIR / "unified_ui"
SUPPORTED_AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".flac", ".ogg", ".opus", ".aac", ".wma"}


class JobState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.process: subprocess.Popen[str] | None = None
        self.running = False
        self.started_at: float | None = None
        self.finished_at: float | None = None
        self.return_code: int | None = None
        self.consultation = ""
        self.output_dir: Path | None = None
        self.lines: list[str] = []

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "running": self.running,
                "startedAt": self.started_at,
                "finishedAt": self.finished_at,
                "returnCode": self.return_code,
                "consultation": self.consultation,
                "outputDir": str(self.output_dir) if self.output_dir else "",
                "log": self.lines[-500:],
                "hasTranscript": bool(self.output_dir and (self.output_dir / "transcript.txt").exists()),
                "hasCopilotOutput": bool(self.output_dir and (self.output_dir / "copilot_output.txt").exists()),
            }

    def append(self, line: str) -> None:
        with self.lock:
            self.lines.append(line.rstrip())
            if len(self.lines) > 1000:
                self.lines = self.lines[-1000:]


JOB = JobState()


def list_consultations() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not ASR_INPUT_DIR.exists():
        return items
    for directory in sorted(path for path in ASR_INPUT_DIR.iterdir() if path.is_dir()):
        audio_files = [
            path.name
            for path in sorted(directory.iterdir())
            if path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
        ]
        items.append(
            {
                "name": directory.name,
                "audioFiles": audio_files,
                "hasAudio": bool(audio_files),
            }
        )
    return items


def _run_pipeline(payload: dict[str, Any]) -> None:
    consultation = str(payload.get("consultation") or "consultation1").strip()
    redis_host = str(payload.get("redisHost") or os.environ.get("REDIS_HOST") or "localhost").strip()
    redis_port = str(payload.get("redisPort") or os.environ.get("REDIS_PORT") or "6379").strip()
    limit = int(payload.get("limit") or 0)
    mode = str(payload.get("mode") or "batch").strip().lower()
    realtime_factor = float(payload.get("realtimeFactor") or 0.0)
    is_realtime = mode == "realtime"
    output_dir = RUNS_DIR / (f"{consultation}_realtime" if is_realtime else consultation)

    if is_realtime:
        command = [
            sys.executable,
            str(ROOT_DIR / "run_realtime_consultation.py"),
            "--consultation",
            consultation,
            "--output-dir",
            str(output_dir),
            "--redis-host",
            redis_host,
            "--redis-port",
            redis_port,
            "--realtime-factor",
            str(realtime_factor),
        ]
    else:
        command = [
            sys.executable,
            str(ROOT_DIR / "run_consultation.py"),
            "--consultation",
            consultation,
            "--output-dir",
            str(output_dir),
        ]
        if limit > 0:
            command.extend(["--limit", str(limit)])

    env = os.environ.copy()
    env["REDIS_HOST"] = redis_host
    env["REDIS_PORT"] = redis_port
    env["PYTHONIOENCODING"] = "utf-8"

    with JOB.lock:
        JOB.running = True
        JOB.started_at = time.time()
        JOB.finished_at = None
        JOB.return_code = None
        JOB.consultation = consultation
        JOB.output_dir = output_dir
        JOB.lines = [
            f"Starting: {' '.join(command)}",
            f"Redis: {redis_host}:{redis_port}",
            f"Mode: {mode}",
        ]

    try:
        process = subprocess.Popen(
            command,
            cwd=ROOT_DIR,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        with JOB.lock:
            JOB.process = process

        assert process.stdout is not None
        for line in process.stdout:
            JOB.append(line)
        return_code = process.wait()
    except Exception as exc:
        JOB.append(f"ERROR: {exc}")
        return_code = -1
    finally:
        with JOB.lock:
            JOB.running = False
            JOB.finished_at = time.time()
            JOB.return_code = return_code
            JOB.process = None
        JOB.append(f"Finished with code {return_code}")


def start_job(payload: dict[str, Any]) -> dict[str, Any]:
    with JOB.lock:
        if JOB.running:
            return {"ok": False, "error": "Pipeline is already running."}
    threading.Thread(target=_run_pipeline, args=(payload,), daemon=True, name="unified-pipeline").start()
    return {"ok": True}


def stop_job() -> dict[str, Any]:
    with JOB.lock:
        process = JOB.process
    if process is None or process.poll() is not None:
        return {"ok": False, "error": "No running pipeline."}
    process.terminate()
    return {"ok": True}


def read_result() -> dict[str, Any]:
    snapshot = JOB.snapshot()
    output_dir = Path(snapshot["outputDir"]) if snapshot["outputDir"] else None
    transcript = ""
    copilot = ""
    if output_dir:
        transcript_path = output_dir / "transcript.txt"
        copilot_path = output_dir / "copilot_output.txt"
        realtime_path = output_dir / "realtime_events.jsonl"
        if transcript_path.exists():
            transcript = transcript_path.read_text(encoding="utf-8", errors="replace")
        if copilot_path.exists():
            copilot = copilot_path.read_text(encoding="utf-8", errors="replace")
        realtime_events = []
        if realtime_path.exists():
            for line in realtime_path.read_text(encoding="utf-8", errors="replace").splitlines()[-250:]:
                try:
                    realtime_events.append(json.loads(line))
                except json.JSONDecodeError:
                    realtime_events.append({"type": "raw", "line": line})
    else:
        realtime_events = []
    return {
        "transcript": transcript,
        "copilotOutput": copilot,
        "realtimeEvents": realtime_events,
        **snapshot,
    }


def default_settings() -> dict[str, str]:
    redis_host = os.environ.get("REDIS_HOST") or "localhost"
    redis_port = os.environ.get("REDIS_PORT") or "6380"
    if redis_host == "localhost":
        try:
            output = subprocess.check_output(
                ["wsl", "hostname", "-I"],
                cwd=ROOT_DIR,
                text=True,
                timeout=3,
                stderr=subprocess.DEVNULL,
            )
            first_ip = output.strip().split()[0]
            if first_ip:
                redis_host = first_ip
        except Exception:
            pass
    return {"redisHost": redis_host, "redisPort": redis_port}


class UnifiedHandler(BaseHTTPRequestHandler):
    server_version = "UnifiedLegalASR/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/consultations":
            self._json({"items": list_consultations()})
            return
        if parsed.path == "/api/status":
            self._json(JOB.snapshot())
            return
        if parsed.path == "/api/result":
            self._json(read_result())
            return
        if parsed.path == "/api/defaults":
            self._json(default_settings())
            return
        self._static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        payload = self._read_json()
        if parsed.path == "/api/run":
            self._json(start_job(payload))
            return
        if parsed.path == "/api/stop":
            self._json(stop_job())
            return
        self._json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def _json(self, payload: dict[str, Any], *, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _static(self, request_path: str) -> None:
        relative = "index.html" if request_path in {"", "/"} else unquote(request_path.lstrip("/"))
        path = (UI_DIR / relative).resolve()
        if not str(path).startswith(str(UI_DIR.resolve())) or not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = "text/html; charset=utf-8"
        if path.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        elif path.suffix == ".js":
            content_type = "application/javascript; charset=utf-8"
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    host = os.environ.get("UNIFIED_HOST", "127.0.0.1")
    port = int(os.environ.get("UNIFIED_PORT", "8090"))
    server = ThreadingHTTPServer((host, port), UnifiedHandler)
    print(f"Unified ASR Copilot UI running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
