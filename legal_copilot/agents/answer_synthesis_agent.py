"""LLM-backed answer synthesis grounded in retrieved Civil Code articles."""

from __future__ import annotations

from dataclasses import dataclass

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency
    OpenAI = None

from legal_copilot.rag.hybrid_retriever import HybridRetrievalHit
from legal_copilot.yandex_config import (
    get_yandex_api_key_path,
    load_yandex_api_key,
    load_yandex_base_url,
    load_yandex_folder_id,
    load_yandex_model,
)


SYSTEM_PROMPT = """Ты юридический ассистент по российскому гражданскому праву.

Тебе передают:
- вопрос клиента на русском языке;
- несколько найденных статей ГК РФ с заголовками, краткими summary, фрагментами текста и пояснениями к релевантности.

Сформируй ответ так, как это мог бы устно сказать юрист клиенту: ясно, уверенно, по делу и без канцелярита.

Обязательные правила:
- Опирайся только на переданные статьи и их текст.
- Не придумывай нормы, которых нет в материалах.
- В первой или второй фразе дай прямой ответ на вопрос клиента.
- Прямо называй номера статей, когда на них опираешься.
- Основной вывод строй на наиболее релевантных статьях; вспомогательные упоминай только если они реально уточняют вывод.
- Если материалов недостаточно для окончательного вывода, честно скажи, каких фактов, документов или условий сделки не хватает.
- Не пиши общих фраз вроде "нужно обратиться к юристу", "нужно дополнительно изучить законодательство" или "лучше проверить документы", если не можешь конкретно объяснить, что именно нужно проверить и почему.
- Не пересказывай статьи подряд. Синтезируй из них практический вывод применительно к вопросу клиента.

Структура ответа:
1. Короткий прямой вывод.
2. Обоснование: какие нормы на это указывают и как именно они применяются к вопросу.
3. Если это реально нужно, один конкретный next step: какой факт, документ или параметр сделки надо проверить для окончательного вывода.

Стиль:
- русский язык;
- естественная устная формулировка;
- 2-4 коротких абзаца;
- примерно 170-320 слов;
- без markdown, списков и заголовков;
- верни только сам текст ответа.
"""

REQUEST_TIMEOUT_SECONDS = 30


@dataclass
class SynthesizedAnswerResult:
    answer_text: str | None
    source: str
    enabled: bool
    used: bool
    error: str | None = None


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


def _compact_text(text: str, limit: int = 1200) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3].rstrip(' ,;:')}..."


def _build_article_block(hit: HybridRetrievalHit) -> str:
    article_topics = hit.metadata.get("article_topics") or []
    topic_line = f"Темы: {', '.join(article_topics)}" if article_topics else "Темы: не определены"
    rerank_reason = hit.metadata.get("llm_rerank_reason")
    rerank_line = (
        f"Причина выбора: {rerank_reason}"
        if rerank_reason
        else f"Причины retrieval: {', '.join(hit.reasons)}"
    )
    chapter = hit.metadata.get("chapter") or "Без главы"
    return "\n".join(
        [
            f"Статья: {hit.article_number}",
            f"Заголовок: {hit.title}",
            f"Глава: {chapter}",
            topic_line,
            rerank_line,
            f"Summary: {_compact_text(hit.summary, 400)}",
            f"Текст статьи: {_compact_text(hit.text, 1500)}",
        ]
    )


def synthesize_answer_with_llm(
    question: str,
    retrieved_hits: list[HybridRetrievalHit],
) -> SynthesizedAnswerResult:
    if not _llm_enabled():
        _api_key, api_error = load_yandex_api_key()
        _folder_id, folder_error = load_yandex_folder_id()
        return SynthesizedAnswerResult(
            answer_text=None,
            source="disabled",
            enabled=False,
            used=False,
            error=api_error or folder_error or f"Yandex API key file not found: {get_yandex_api_key_path()}",
        )
    if OpenAI is None:
        return SynthesizedAnswerResult(
            answer_text=None,
            source="disabled",
            enabled=True,
            used=False,
            error="Python package 'openai' is not installed for Yandex-compatible API client",
        )
    if not retrieved_hits:
        return SynthesizedAnswerResult(
            answer_text=None,
            source="disabled",
            enabled=True,
            used=False,
            error="no_retrieved_hits",
        )

    client = _build_client()
    model, model_error = load_yandex_model()
    if not model:
        return SynthesizedAnswerResult(
            answer_text=None,
            source="disabled",
            enabled=False,
            used=False,
            error=model_error,
        )

    article_blocks = [_build_article_block(hit) for hit in retrieved_hits[:4]]
    user_prompt = (
        f"Вопрос клиента:\n{question}\n\n"
        "Материалы для ответа:\n\n"
        + "\n\n---\n\n".join(article_blocks)
        + "\n\nСначала ответь на вопрос по существу. Затем кратко объясни, какие именно статьи и почему ведут к этому выводу. "
        + "Если нужен caveat, он должен быть конкретным: какой факт, документ или условие нужно проверить."
    )

    try:
        response = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.15,
            max_output_tokens=1400,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        answer_text = (response.output_text or "").strip()
    except Exception as exc:  # pragma: no cover - external API path
        return SynthesizedAnswerResult(
            answer_text=None,
            source="error",
            enabled=True,
            used=False,
            error=str(exc),
        )

    if not answer_text:
        return SynthesizedAnswerResult(
            answer_text=None,
            source="empty",
            enabled=True,
            used=False,
            error="empty_answer",
        )

    return SynthesizedAnswerResult(
        answer_text=answer_text,
        source="llm",
        enabled=True,
        used=True,
        error=None,
    )
