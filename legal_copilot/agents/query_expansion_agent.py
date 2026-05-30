"""LLM agent for semantic legal query expansion."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency
    OpenAI = None

from legal_copilot.yandex_config import (
    get_yandex_api_key_path,
    load_yandex_api_key,
    load_yandex_base_url,
    load_yandex_folder_id,
    load_yandex_model,
)


SYSTEM_PROMPT = """You expand Russian legal search queries for retrieval over Civil Code articles.

Return only compact JSON with this schema:
{
  "keywords": ["term 1", "term 2"],
  "rationale": ["short reason 1", "short reason 2"]
}

Rules:
- Output 3 to 8 short Russian legal terms or phrases.
- Add only retrieval-helpful legal terminology, synonyms, legal formulations, and nearby doctrinal wording.
- Do not answer the question.
- Do not include explanations outside JSON.
- Prefer terms that improve search in codes, statutes, and legal articles.
"""

REQUEST_TIMEOUT_SECONDS = 20


@dataclass
class LLMExpansionResult:
    keywords: list[str] = field(default_factory=list)
    rationale: list[str] = field(default_factory=list)
    enabled: bool = False
    used: bool = False
    error: str | None = None


def _dedupe_terms(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for term in terms:
        cleaned = " ".join(term.strip().split())
        lowered = cleaned.lower()
        if not cleaned or lowered in seen:
            continue
        seen.add(lowered)
        result.append(cleaned)
    return result


def _llm_enabled() -> bool:
    api_key, _api_error = load_yandex_api_key()
    folder_id, _folder_error = load_yandex_folder_id()
    return bool(api_key and folder_id)


def _build_client():
    if OpenAI is None:
        return None
    api_key, _error = load_yandex_api_key()
    folder_id, _folder_error = load_yandex_folder_id()
    return OpenAI(
        api_key=api_key,
        base_url=load_yandex_base_url(),
        project=folder_id,
    )


def _normalize_llm_json_text(raw_text: str) -> str:
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


def _parse_llm_payload(response) -> tuple[dict | None, str | None]:
    raw_text = getattr(response, "output_text", "") or ""
    normalized_text = _normalize_llm_json_text(raw_text)
    if not normalized_text:
        return None, "empty_or_non_json_llm_response"

    try:
        return json.loads(normalized_text), None
    except json.JSONDecodeError as exc:
        preview = normalized_text[:300].replace("\n", "\\n")
        return None, f"{exc}; raw_response={preview}"


def expand_query_with_llm(query: str) -> LLMExpansionResult:
    if OpenAI is None:
        return LLMExpansionResult(
            enabled=False,
            used=False,
            error="Python package 'openai' is not installed for Yandex-compatible API client",
        )

    api_key, api_error = load_yandex_api_key()
    folder_id, folder_error = load_yandex_folder_id()
    model, model_error = load_yandex_model()
    if not api_key:
        return LLMExpansionResult(
            enabled=False,
            used=False,
            error=api_error or f"Yandex API key file not found: {get_yandex_api_key_path()}",
        )
    if not folder_id:
        return LLMExpansionResult(enabled=False, used=False, error=folder_error)
    if not model:
        return LLMExpansionResult(enabled=False, used=False, error=model_error)

    client = _build_client()

    try:
        response = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Исходный запрос:\n{query}\n\nВерни только JSON.",
                },
            ],
            temperature=0,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # pragma: no cover - external API path
        return LLMExpansionResult(enabled=True, used=False, error=str(exc))

    payload, parse_error = _parse_llm_payload(response)
    if not payload:
        return LLMExpansionResult(enabled=True, used=False, error=parse_error)

    keywords = _dedupe_terms(payload.get("keywords", []))
    rationale = [str(item).strip() for item in payload.get("rationale", []) if str(item).strip()]
    return LLMExpansionResult(
        keywords=keywords[:8],
        rationale=rationale[:8],
        enabled=True,
        used=True,
        error=None,
    )
