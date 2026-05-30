"""Live backend for the LegalCopilot transcript demo site."""

from __future__ import annotations

import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from legal_copilot.agents.context_manager import StreamingContextManager
from legal_copilot.ingestion.transcript_cleaner import TranscriptTurn, parse_transcript_with_options
from legal_copilot.orchestration.graph import run_legal_copilot_turn
from legal_copilot.orchestration.pipeline import process_transcript_chunk

ROOT_DIR = Path(__file__).resolve().parents[1]
UI_DIR = ROOT_DIR / "ui"
DATA_DIR = ROOT_DIR / "data"
DEMO_PAYLOAD_DIR = DATA_DIR / "demo_payloads"


def _log_demo(event: str, **details: Any) -> None:
    timestamp = __import__("datetime").datetime.now().strftime("%H:%M:%S")
    suffix = ""
    if details:
        pairs = ", ".join(f"{key}={value}" for key, value in details.items())
        suffix = f" | {pairs}"
    print(f"[legal_copilot demo {timestamp}] {event}{suffix}", flush=True)


def _list_transcript_paths() -> list[Path]:
    return sorted(DATA_DIR.glob("transcript_*.txt"))


def _payload_cache_path(transcript_name: str) -> Path:
    return DEMO_PAYLOAD_DIR / f"{Path(transcript_name).stem}.json"


def load_cached_demo_payload(transcript_name: str) -> dict[str, Any] | None:
    cache_path = _payload_cache_path(transcript_name)
    if not cache_path.exists():
        return None

    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive cache read
        _log_demo("cache.read_error", transcript=transcript_name, error=exc)
        return None

    _log_demo(
        "cache.hit",
        transcript=transcript_name,
        path=cache_path.name,
        steps=len(payload.get("steps", [])),
    )
    return payload


def save_demo_payload(payload: dict[str, Any], transcript_name: str) -> Path:
    DEMO_PAYLOAD_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = _payload_cache_path(transcript_name)
    cache_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _log_demo(
        "cache.saved",
        transcript=transcript_name,
        path=cache_path.name,
        steps=len(payload.get("steps", [])),
    )
    return cache_path


def _collect_completed_answers(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    answers: list[dict[str, Any]] = []
    for step in steps:
        answer_text = str(step.get("answerText") or "").strip()
        if not answer_text:
            continue
        answers.append(
            {
                "chunkId": step.get("id"),
                "question": step.get("activeQuestion") or "",
                "answer": answer_text,
                "route": step.get("route") or "unknown",
                "answerSource": step.get("answerSource") or "unknown",
            }
        )
    return answers


def _collect_review_comments(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    comments: list[dict[str, Any]] = []
    for step in steps:
        review = step.get("lawyerPhraseCheck") or {}
        flagged_items = list(review.get("flaggedItems") or [])
        summary = str(review.get("summary") or "").strip()
        if not flagged_items and not summary:
            continue
        comments.append(
            {
                "chunkId": step.get("id"),
                "status": review.get("status") or "no_statement",
                "summary": summary,
                "flaggedItems": flagged_items,
            }
        )
    return comments


def _build_payload_metadata(
    transcript_name: str,
    steps: list[dict[str, Any]],
    *,
    status: str,
) -> dict[str, Any]:
    return {
        "transcript": transcript_name,
        "label": transcript_name,
        "session": f"live-{transcript_name}",
        "status": status,
        "steps": steps,
        "savedAnswers": _collect_completed_answers(steps),
        "savedReviewComments": _collect_review_comments(steps),
    }


def _turn_display_name(turn: TranscriptTurn) -> str:
    return turn.raw_speaker or turn.speaker


def _render_chunk(turns: list[TranscriptTurn]) -> str:
    lines: list[str] = []
    for turn in turns:
        speaker = _turn_display_name(turn)
        chunk = turn.metadata.get("chunk")
        if chunk:
            lines.append(f"[{speaker}] ({chunk}): {turn.text}")
        else:
            lines.append(f"{speaker}: {turn.text}")
    return "\n".join(lines)


def _build_windows(turns: list[TranscriptTurn], *, window_size: int = 4, stride: int = 3) -> list[tuple[str, list[TranscriptTurn]]]:
    if not turns:
        return []

    if len(turns) <= window_size:
        return [("chunk_1", turns)]

    windows: list[tuple[str, list[TranscriptTurn]]] = []
    start = 0
    chunk_index = 1

    while start < len(turns):
        chunk_turns = turns[start : start + window_size]
        if not chunk_turns:
            break
        windows.append((f"chunk_{chunk_index}", chunk_turns))
        if start + window_size >= len(turns):
            break
        start += stride
        chunk_index += 1

    if windows and windows[-1][1] != turns[-window_size:]:
        windows.append((f"chunk_{len(windows) + 1}", turns[-window_size:]))

    return windows


def _map_conversation_turn(turn: TranscriptTurn) -> dict[str, str] | None:
    if turn.speaker == "user":
        role = "client"
    elif turn.speaker == "assistant":
        role = "assistant"
    elif turn.speaker == "system":
        role = "system"
    else:
        role = "transcript"
    return {
        "role": role,
        "text": turn.text,
        "label": _turn_display_name(turn),
    }


def _question_to_dict(question: Any) -> dict[str, Any]:
    return {
        "text": question.normalized_question,
        "status": "clarify" if question.needs_clarification else ("ready" if question.is_question else "context"),
        "note": ", ".join(question.reasoning) if question.reasoning else "",
    }


def _format_fact_check(fact_check: Any) -> str:
    if not fact_check:
        return "Grounded: false. Confidence: 0.00."
    citations = ", ".join(fact_check.cited_articles) if fact_check.cited_articles else "нет"
    return (
        f"Grounded: {str(fact_check.grounded).lower()}. "
        f"Confidence: {fact_check.confidence:.2f}. "
        f"Использованные статьи: {citations}."
    )


def _summarize_lawyer_phrase_check(check: Any) -> str:
    if not check:
        return "Проверка фраз юриста не проводилась."
    status = getattr(check, "status", "no_statement")
    if status == "supported":
        return "Содержательные фразы юриста в текущем окне подтверждаются найденными статьями."
    if status == "partially_supported":
        return "Большая часть фраз юриста подтверждается найденными статьями, но отдельные утверждения лучше перепроверить."
    if status == "needs_review":
        return "Часть фраз юриста не получила достаточной опоры в найденных статьях и требует ручной проверки."
    return "В текущем окне нет содержательных правовых утверждений юриста для отдельной проверки."


def _lawyer_phrase_check_to_dict(check: Any) -> dict[str, Any]:
    if not check:
        return {
            "status": "no_statement",
            "grounded": True,
            "confidence": 0.0,
            "summary": "Lawyer phrase check was not run.",
            "reviewedPhrases": [],
            "flaggedPhrases": [],
            "flaggedItems": [],
        }

    cited_articles = list(getattr(check, "cited_articles", []) or [])
    cited_suffix = (
        f" Review this statement against articles {', '.join(cited_articles)}."
        if cited_articles
        else " No reliable support for this phrase was found in the retrieved sources."
    )
    flagged_items = [
        {
            "phrase": phrase,
            "comment": f'This lawyer statement needs manual review: "{phrase}".{cited_suffix}',
        }
        for phrase in list(check.flagged_phrases)
    ]

    return {
        "status": check.status,
        "grounded": check.grounded,
        "confidence": round(check.confidence, 2),
        "summary": _summarize_lawyer_phrase_check(check),
        "reviewedPhrases": list(check.reviewed_phrases),
        "flaggedPhrases": list(check.flagged_phrases),
        "flaggedItems": flagged_items,
    }


def _extract_topics(result: Any) -> str:
    contexts = result.retrieved_contexts or ([result.retrieved_context] if result.retrieved_context else [])
    topics: list[str] = []
    for context in contexts:
        for topic in context.result.diagnostics.get("detected_topics", []):
            if topic not in topics:
                topics.append(topic)
    return ", ".join(topics) if topics else "Не выделены"


def _build_stage_summaries(result: Any, parsed_turn_count: int) -> list[dict[str, str]]:
    return [
        {
            "name": "ingest_chunk",
            "status": "done",
            "text": f"Система получила и разобрала {parsed_turn_count} реплик(и) в текущем окне.",
        },
        {
            "name": "question_extraction",
            "status": "done",
            "text": "Из текущего окна извлечены вопросы клиента и они переданы в retrieval.",
        },
        {
            "name": "retrieval",
            "status": "done",
            "text": "По каждому вопросу выполнен поиск релевантных статей и построен контекст ответа.",
        },
        {
            "name": "answer_generation",
            "status": "done",
            "text": f"Сформирован ответ по маршруту {result.route}.",
        },
    ]


def _build_demo_step(
    name: str,
    chunk_text: str,
    pipeline_result: Any,
    graph_result: Any,
) -> dict[str, Any]:
    extracted_questions = graph_result.extracted_questions or (
        [graph_result.extracted_question] if graph_result.extracted_question else []
    )
    retrieval_requests = graph_result.retrieval_requests or (
        [graph_result.retrieval_request] if graph_result.retrieval_request else []
    )
    retrieved_contexts = graph_result.retrieved_contexts or (
        [graph_result.retrieved_context] if graph_result.retrieved_context else []
    )

    retrieval_branches: list[dict[str, Any]] = []
    for index, context in enumerate(retrieved_contexts, start=1):
        request = retrieval_requests[index - 1] if index - 1 < len(retrieval_requests) else None
        retrieval_branches.append(
            {
                "label": f"Ветка {index}",
                "query": request.query_text if request else "retrieval_request unavailable",
                "reasons": request.reasons if request else [],
                "articles": [
                    {
                        "number": hit.article_number,
                        "title": hit.title,
                        "score": f"{hit.final_score:.3f}",
                        "summary": hit.summary or "",
                    }
                    for hit in context.result.hits[:5]
                ],
            }
        )

    conversation = [
        mapped
        for turn in pipeline_result.appended_turns
        if (mapped := _map_conversation_turn(turn)) is not None
    ]

    primary_question = (
        graph_result.extracted_question.normalized_question
        if graph_result.extracted_question and graph_result.extracted_question.normalized_question
        else pipeline_result.active_user_query
    )

    return {
        "id": name,
        "title": f"Чанк {name.split('_')[-1]}",
        "subtitle": "Live-результат пайплайна по текущему окну транскрипции.",
        "incomingChunk": chunk_text,
        "processingTurns": [
            mapped
            for turn in pipeline_result.parsed_turns
            if (mapped := _map_conversation_turn(turn)) is not None
        ],
        "appendedTurns": [
            {"role": turn.speaker, "text": turn.text}
            for turn in pipeline_result.appended_turns
        ],
        "conversation": conversation,
        "activeQuestion": primary_question or "Вопрос пока не выделен",
        "extractedQuestions": [_question_to_dict(question) for question in extracted_questions],
        "retrievalCount": len(retrieval_branches),
        "grounding": (
            f"{graph_result.fact_check.confidence:.2f} / "
            f"{'grounded' if graph_result.fact_check.grounded else 'needs_review'}"
            if graph_result.fact_check
            else "—"
        ),
        "topics": _extract_topics(graph_result),
        "stages": _build_stage_summaries(graph_result, pipeline_result.metadata["parsed_turn_count"]),
        "retrievalBranches": retrieval_branches,
        "route": graph_result.route or "unknown",
        "answerSource": graph_result.answer_source or "unknown",
        "answerText": graph_result.answer_text or "",
        "factCheck": _format_fact_check(graph_result.fact_check),
        "lawyerPhraseCheck": _lawyer_phrase_check_to_dict(graph_result.lawyer_phrase_check),
    }


def build_demo_payload(transcript_name: str) -> dict[str, Any]:
    started_at = perf_counter()
    _log_demo("build_demo_payload.start", transcript=transcript_name)
    transcript_path = (DATA_DIR / transcript_name).resolve()
    if transcript_path.parent != DATA_DIR.resolve() or not transcript_path.exists():
        _log_demo("build_demo_payload.not_found", transcript=transcript_name)
        raise FileNotFoundError(transcript_name)

    parse_started_at = perf_counter()
    parsed = parse_transcript_with_options(transcript_path, merge_turns=False)
    _log_demo(
        "build_demo_payload.parsed",
        transcript=transcript_name,
        turns=len(parsed.turns),
        seconds=f"{perf_counter() - parse_started_at:.2f}",
    )

    window_started_at = perf_counter()
    windows = _build_windows(parsed.turns)
    _log_demo(
        "build_demo_payload.windows_ready",
        transcript=transcript_name,
        windows=len(windows),
        seconds=f"{perf_counter() - window_started_at:.2f}",
    )

    pipeline_session = StreamingContextManager(session_id=f"pipeline-{transcript_name}")
    graph_session = StreamingContextManager(session_id=f"graph-{transcript_name}")

    steps: list[dict[str, Any]] = []
    for index, (name, window_turns) in enumerate(windows, start=1):
        chunk_started_at = perf_counter()
        _log_demo(
            "build_demo_payload.chunk_start",
            transcript=transcript_name,
            chunk=name,
            index=f"{index}/{len(windows)}",
            turns=len(window_turns),
        )
        chunk_text = _render_chunk(window_turns)
        pipeline_result = process_transcript_chunk(
            chunk_text,
            context_manager=pipeline_session,
            chunk_size=140,
            overlap=20,
        )
        graph_result = run_legal_copilot_turn(
            chunk_text,
            context_manager=graph_session,
            session_id=f"graph-{transcript_name}",
        )
        step = _build_demo_step(name, chunk_text, pipeline_result, graph_result)
        steps.append(step)
        save_demo_payload(
            _build_payload_metadata(
                transcript_name,
                steps,
                status="processing",
            ),
            transcript_name,
        )
        _log_demo(
            "build_demo_payload.chunk_done",
            transcript=transcript_name,
            chunk=name,
            route=step.get("route"),
            questions=len(step.get("extractedQuestions", [])),
            retrievals=len(step.get("retrievalBranches", [])),
            saved_answers=len(_collect_completed_answers(steps)),
            saved_reviews=len(_collect_review_comments(steps)),
            seconds=f"{perf_counter() - chunk_started_at:.2f}",
        )

    payload = _build_payload_metadata(
        transcript_name,
        steps,
        status="completed",
    )
    _log_demo(
        "build_demo_payload.done",
        transcript=transcript_name,
        steps=len(steps),
        saved_answers=len(payload.get("savedAnswers", [])),
        saved_reviews=len(payload.get("savedReviewComments", [])),
        seconds=f"{perf_counter() - started_at:.2f}",
    )
    return payload


def get_demo_payload(
    transcript_name: str,
    *,
    use_cache: bool = True,
    save_cache: bool = True,
) -> dict[str, Any]:
    if use_cache:
        cached_payload = load_cached_demo_payload(transcript_name)
        if cached_payload is not None:
            return cached_payload

    payload = build_demo_payload(transcript_name)
    if save_cache:
        save_demo_payload(payload, transcript_name)
    return payload


class DemoRequestHandler(BaseHTTPRequestHandler):
    server_version = "LegalCopilotDemo/1.0"

    def do_GET(self) -> None:
        parsed_url = urlparse(self.path)
        if parsed_url.path == "/api/transcripts":
            self._send_json(
                {
                    "items": [
                        {"name": path.name, "label": path.name}
                        for path in _list_transcript_paths()
                    ]
                }
            )
            return

        if parsed_url.path == "/api/demo":
            params = parse_qs(parsed_url.query)
            transcript = params.get("transcript", ["transcript_1.txt"])[0]
            refresh = params.get("refresh", ["0"])[0] in {"1", "true", "yes"}
            try:
                payload = get_demo_payload(
                    transcript,
                    use_cache=not refresh,
                    save_cache=True,
                )
            except FileNotFoundError:
                self._send_json({"error": f"Transcript not found: {transcript}"}, status=HTTPStatus.NOT_FOUND)
                return
            except Exception as exc:  # pragma: no cover - defensive handler for demo server
                self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            self._send_json(payload)
            return

        self._serve_static(parsed_url.path)

    def _serve_static(self, request_path: str) -> None:
        normalized = "/" if request_path in {"", "/"} else request_path
        relative = "index.html" if normalized == "/" else unquote(normalized.lstrip("/"))
        file_path = (UI_DIR / relative).resolve()
        if not str(file_path).startswith(str(UI_DIR.resolve())) or not file_path.exists() or not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        content = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, payload: dict[str, Any], *, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # pragma: no cover - keep console quiet
        return


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the live backend for the LegalCopilot demo site.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind.")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind.")
    return parser


def main() -> None:
    args = build_argument_parser().parse_args()
    server = ThreadingHTTPServer((args.host, args.port), DemoRequestHandler)
    print(f"LegalCopilot demo server running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
