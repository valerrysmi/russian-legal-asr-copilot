"""Heuristics for legal query classification and decomposition."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from legal_copilot.rag.embeddings import normalize_text

TOPIC_RULES = {
    "notary": {
        "label": "Нотариальная форма",
        "triggers": ["нотари", "удостовер", "нотариальн"],
    },
    "share_transfer": {
        "label": "Переход доли",
        "triggers": ["доля", "ооо", "участник", "продаж", "отчуждени", "переход доли"],
    },
    "registration": {
        "label": "Регистрация прав",
        "triggers": ["егрюл", "егрн", "реестр", "регистрац", "запись"],
    },
    "invalidity": {
        "label": "Недействительность сделок",
        "triggers": ["недействител", "ничтожн", "оспорим", "сделк"],
    },
    "limitation": {
        "label": "Исковая давность",
        "triggers": ["исков", "давност", "срок"],
    },
    "corporate_approval": {
        "label": "Корпоративное одобрение",
        "triggers": ["собрани", "голос", "одобрени", "кворум", "решение"],
    },
    "creditor_risk": {
        "label": "Риски кредиторов",
        "triggers": ["кредитор", "досроч", "обязательств", "должник", "ковенант"],
    },
    "loan_credit": {
        "label": "Заем и кредит",
        "triggers": ["заем", "займ", "кредит", "займодав", "заемщик"],
    },
    "pledge_security": {
        "label": "Обеспечение обязательств",
        "triggers": ["залог", "неустойк", "поручител", "гарант", "обеспеч"],
    },
}

INTERROGATIVE_CUES = (
    "нужно ли",
    "можно ли",
    "как",
    "какие",
    "какой",
    "РєРѕРіРґР°",
    "почему",
    "есть ли",
    "достаточно ли",
    "обязательно ли",
    "требуется ли",
    "что делать",
    "что будет",
)

ENUMERATION_SPLIT_RE = re.compile(
    r"(?:^|[\s,;:.-])(?:во-?первых|во-?вторых|в-?третьих|в-?четвертых|первое|второе|третье|четвертое)\b",
    re.IGNORECASE,
)
SOFT_SPLIT_RE = re.compile(r"\s+(?:и|а также|либо|или)\s+", re.IGNORECASE)
SENTENCE_SPLIT_RE = re.compile(r"[!?]+|\.\s+")


@dataclass
class QueryUnderstanding:
    original_query: str
    normalized_query: str
    detected_topics: list[str] = field(default_factory=list)
    topic_labels: list[str] = field(default_factory=list)
    subqueries: list[str] = field(default_factory=list)
    query_type: str = "general"


def classify_legal_query(query: str) -> QueryUnderstanding:
    normalized_query = normalize_text(query)
    detected_topics: list[str] = []
    topic_labels: list[str] = []

    for topic_id, rule in TOPIC_RULES.items():
        if any(trigger in normalized_query for trigger in rule["triggers"]):
            detected_topics.append(topic_id)
            topic_labels.append(rule["label"])

    subqueries = decompose_legal_query(query)
    query_type = _detect_query_type(normalized_query, len(subqueries))

    return QueryUnderstanding(
        original_query=query,
        normalized_query=normalized_query,
        detected_topics=detected_topics,
        topic_labels=topic_labels,
        subqueries=subqueries,
        query_type=query_type,
    )


def decompose_legal_query(query: str) -> list[str]:
    normalized = " ".join(query.split())
    if not normalized:
        return []

    chunks = [normalized]
    if ENUMERATION_SPLIT_RE.search(normalized):
        marked = ENUMERATION_SPLIT_RE.sub(" ||| ", normalized)
        chunks = [part.strip(" ,;:-") for part in marked.split("|||") if part.strip(" ,;:-")]
    else:
        sentence_parts = [part.strip(" ,;:-") for part in SENTENCE_SPLIT_RE.split(normalized) if part.strip(" ,;:-")]
        if len(sentence_parts) > 1:
            chunks = sentence_parts

    expanded_chunks: list[str] = []
    for chunk in chunks:
        soft_parts = [part.strip(" ,;:-") for part in SOFT_SPLIT_RE.split(chunk) if part.strip(" ,;:-")]
        interrogative_parts = [part for part in soft_parts if _looks_like_subquery(part)]
        if len(interrogative_parts) >= 2:
            expanded_chunks.extend(interrogative_parts)
        else:
            expanded_chunks.append(chunk)

    deduped: list[str] = []
    seen: set[str] = set()
    for chunk in expanded_chunks:
        cleaned = " ".join(chunk.split())
        lowered = cleaned.lower()
        if not cleaned or lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(cleaned)

    return deduped[:5]


def build_search_queries(query: str) -> QueryUnderstanding:
    understanding = classify_legal_query(query)
    if not understanding.subqueries:
        understanding.subqueries = [query]
    return understanding


def _looks_like_subquery(text: str) -> bool:
    lowered = text.lower()
    return text.endswith("?") or any(cue in lowered for cue in INTERROGATIVE_CUES)


def _detect_query_type(normalized_query: str, subquery_count: int) -> str:
    if subquery_count > 1:
        return "multi_issue"
    if any(cue in normalized_query for cue in ("нужно ли", "обязательно ли", "требуется ли")):
        return "requirement_check"
    if any(cue in normalized_query for cue in ("как", "какие", "какой", "когда")):
        return "procedural"
    if any(cue in normalized_query for cue in ("риски", "последствия", "что будет")):
        return "risk_assessment"
    return "general"
