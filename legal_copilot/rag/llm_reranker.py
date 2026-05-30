"""LLM-based reranking for legal article retrieval."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency
    OpenAI = None

from legal_copilot.rag.reranker import RerankCandidate
from legal_copilot.yandex_config import (
    get_yandex_api_key_path,
    load_yandex_api_key,
    load_yandex_base_url,
    load_yandex_folder_id,
    load_yandex_model,
)

SYSTEM_PROMPT = """You rerank Russian legal retrieval candidates for relevance to a user question.

Return only compact JSON with this schema:
{
  "scores": [
    {
      "article_number": "93",
      "score": 0.91,
      "reason": "short Russian reason"
    }
  ]
}

Rules:
- Score each candidate from 0.0 to 1.0 for how directly it helps answer the user question.
- Prefer articles that answer the exact legal issue, not only the broad topic.
- Consider title, summary, and excerpt together.
- Keep reasons very short and in Russian.
- Return only JSON.
"""

REQUEST_TIMEOUT_SECONDS = 20


@dataclass
class LLMRerankItem:
    article_number: str
    score: float
    reason: str = ""


@dataclass
class LLMRerankResult:
    enabled: bool
    used: bool
    error: str | None = None
    items: list[LLMRerankItem] = field(default_factory=list)


def _llm_enabled() -> tuple[bool, str | None]:
    if OpenAI is None:
        return False, "Python package 'openai' is not installed for Yandex-compatible API client"

    api_key, api_error = load_yandex_api_key()
    if not api_key:
        return False, api_error or f"Yandex API key file not found: {get_yandex_api_key_path()}"

    folder_id, folder_error = load_yandex_folder_id()
    if not folder_id:
        return False, folder_error

    return True, None


def _build_client():
    if OpenAI is None:
        return None

    api_key, _api_error = load_yandex_api_key()
    folder_id, _folder_error = load_yandex_folder_id()
    return OpenAI(
        api_key=api_key,
        base_url=load_yandex_base_url(),
        project=folder_id,
    )


def _normalize_json_text(raw_text: str) -> str:
    text = (raw_text or "").strip()
    if not text:
        return ""

    fenced_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced_match:
        text = fenced_match.group(1).strip()

    json_start = text.find("{")
    json_end = text.rfind("}")
    if json_start != -1 and json_end != -1 and json_end >= json_start:
        text = text[json_start : json_end + 1].strip()

    return text


def _parse_payload(response) -> tuple[dict | None, str | None]:
    raw_text = getattr(response, "output_text", "") or ""
    normalized_text = _normalize_json_text(raw_text)
    if not normalized_text:
        return None, "empty_or_non_json_llm_rerank_response"

    try:
        return json.loads(normalized_text), None
    except json.JSONDecodeError as exc:
        preview = normalized_text[:400].replace("\n", "\\n")
        return None, f"{exc}; raw_response={preview}"


def _clip_text(text: str, limit: int = 500) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3].rstrip(' ,;:')}..."


def rerank_with_llm(
    query: str,
    candidates: list[RerankCandidate],
    *,
    max_candidates: int = 12,
) -> LLMRerankResult:
    enabled, error = _llm_enabled()
    if not enabled:
        return LLMRerankResult(enabled=False, used=False, error=error)

    if not candidates:
        return LLMRerankResult(enabled=True, used=False, error="no_candidates_for_llm_rerank")

    model = os.getenv("YANDEX_CLOUD_RERANK_MODEL")
    if not model:
        model, error = load_yandex_model()
    if not model:
        return LLMRerankResult(enabled=False, used=False, error=error)

    client = _build_client()
    selected_candidates = candidates[:max_candidates]
    candidate_blocks = []
    for candidate in selected_candidates:
        candidate_blocks.append(
            "\n".join(
                [
                    f"article_number: {candidate.article_number}",
                    f"title: {candidate.title}",
                    f"summary: {_clip_text(candidate.summary, 320)}",
                    f"excerpt: {_clip_text(candidate.text, 700)}",
                ]
            )
        )

    user_prompt = (
        f"Вопрос пользователя:\n{query}\n\n"
        "Кандидаты для reranking:\n\n"
        + "\n\n---\n\n".join(candidate_blocks)
    )

    try:
        response = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
            max_output_tokens=1000,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # pragma: no cover - external API path
        return LLMRerankResult(enabled=True, used=False, error=str(exc))

    payload, parse_error = _parse_payload(response)
    if not payload:
        return LLMRerankResult(enabled=True, used=False, error=parse_error)

    raw_items = payload.get("scores", [])
    items: list[LLMRerankItem] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        article_number = str(raw_item.get("article_number", "")).strip()
        if not article_number:
            continue
        try:
            score = float(raw_item.get("score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        score = min(max(score, 0.0), 1.0)
        reason = str(raw_item.get("reason", "")).strip()
        items.append(LLMRerankItem(article_number=article_number, score=score, reason=reason))

    if not items:
        return LLMRerankResult(enabled=True, used=False, error="llm_rerank_returned_no_scores")

    return LLMRerankResult(enabled=True, used=True, error=None, items=items)
