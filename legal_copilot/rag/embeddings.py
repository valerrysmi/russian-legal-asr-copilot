"""Sparse and neural embeddings utilities for legal retrieval."""

from __future__ import annotations

import math
import os
import re
from collections import Counter
from functools import lru_cache
from typing import Any


TOKEN_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9]+(?:\.[0-9]+)?")

STOPWORDS = {
    "и",
    "в",
    "во",
    "не",
    "что",
    "он",
    "на",
    "я",
    "с",
    "со",
    "как",
    "а",
    "то",
    "все",
    "она",
    "так",
    "его",
    "но",
    "да",
    "ты",
    "к",
    "у",
    "же",
    "вы",
    "за",
    "бы",
    "по",
    "ее",
    "мне",
    "было",
    "вот",
    "от",
    "меня",
    "еще",
    "нет",
    "о",
    "из",
    "ему",
    "теперь",
    "когда",
    "даже",
    "ну",
    "ли",
    "если",
    "уже",
    "или",
    "ни",
    "быть",
    "был",
    "него",
    "до",
    "вас",
    "нибудь",
    "опять",
    "уж",
    "вам",
    "ведь",
    "там",
    "потом",
    "себя",
    "ничего",
    "ей",
    "может",
    "они",
    "тут",
    "где",
    "есть",
    "надо",
    "ней",
    "для",
    "мы",
    "тебя",
    "их",
    "чем",
    "была",
    "сам",
    "чтоб",
    "без",
    "будто",
    "чего",
    "раз",
    "тоже",
    "себе",
    "под",
    "будет",
    "ж",
    "тогда",
    "кто",
    "этот",
    "того",
    "потому",
    "этого",
    "какой",
    "совсем",
    "ним",
    "здесь",
    "этом",
    "один",
    "почти",
    "мой",
    "тем",
    "чтобы",
    "нее",
    "сейчас",
    "были",
    "куда",
    "зачем",
    "всех",
    "никогда",
    "можно",
    "при",
    "наконец",
    "два",
    "об",
    "другой",
    "хоть",
    "после",
    "над",
    "больше",
    "тот",
    "через",
    "эти",
    "нас",
    "про",
    "всего",
    "них",
    "какая",
    "много",
    "разве",
    "три",
    "эту",
    "моя",
    "впрочем",
    "хорошо",
    "свою",
    "этой",
    "перед",
    "иногда",
    "лучше",
    "чуть",
    "том",
    "нельзя",
    "такой",
    "им",
    "более",
    "всегда",
    "конечно",
    "всю",
    "между",
    "статья",
    "статьи",
    "пункт",
    "пункта",
    "пункте",
    "настоящего",
    "кодекса",
    "российской",
    "федерации",
}


def normalize_text(text: str) -> str:
    return text.lower().replace("ё", "е")


def tokenize(text: str) -> list[str]:
    tokens = [token for token in TOKEN_RE.findall(normalize_text(text))]
    return [token for token in tokens if token not in STOPWORDS and len(token) > 1]


def build_idf(tokenized_documents: list[list[str]]) -> dict[str, float]:
    doc_count = len(tokenized_documents)
    if doc_count == 0:
        return {}

    document_frequencies: Counter[str] = Counter()
    for tokens in tokenized_documents:
        document_frequencies.update(set(tokens))

    return {
        token: math.log((1 + doc_count) / (1 + frequency)) + 1.0
        for token, frequency in document_frequencies.items()
    }


def embed_tokens(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    if not tokens:
        return {}

    counts = Counter(tokens)
    max_tf = max(counts.values())
    vector = {}
    for token, count in counts.items():
        idf_weight = idf.get(token, 1.0)
        tf_weight = 0.5 + 0.5 * (count / max_tf)
        vector[token] = tf_weight * idf_weight

    norm = math.sqrt(sum(value * value for value in vector.values()))
    if norm == 0:
        return vector

    return {token: value / norm for token, value in vector.items()}


def embed_text(text: str, idf: dict[str, float]) -> dict[str, float]:
    return embed_tokens(tokenize(text), idf)


def cosine_similarity_sparse(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0

    smaller, larger = (left, right) if len(left) <= len(right) else (right, left)
    return sum(weight * larger.get(token, 0.0) for token, weight in smaller.items())


def keyword_overlap_ratio(query_tokens: list[str], document_tokens: list[str]) -> float:
    if not query_tokens or not document_tokens:
        return 0.0
    query_set = set(query_tokens)
    document_set = set(document_tokens)
    return len(query_set & document_set) / len(query_set)


def _neural_embeddings_enabled() -> bool:
    return os.getenv("LEGAL_COPILOT_DISABLE_NEURAL_EMBEDDINGS", "").strip().lower() not in {
        "1",
        "true",
        "yes",
    }


@lru_cache(maxsize=1)
def _load_sentence_transformer():
    if not _neural_embeddings_enabled():
        return None

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return None

    model_name = os.getenv(
        "LEGAL_COPILOT_EMBEDDING_MODEL",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    )
    try:
        return SentenceTransformer(model_name)
    except Exception:
        return None


def neural_embeddings_available() -> bool:
    return _load_sentence_transformer() is not None


def neural_embedding_model_name(purpose: str = "document") -> str | None:
    model = _load_sentence_transformer()
    if model is None:
        return None
    return getattr(model, "model_card_data", None) and getattr(model, "_model_card_text", None) or getattr(model, "model_name_or_path", None)

def embed_text_dense(text: str, purpose: str = "document") -> list[float] | None:
    model = _load_sentence_transformer()
    if model is None:
        return None

    try:
        vector = model.encode(
            text,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
    except Exception:
        return None
    return vector.tolist()


def cosine_similarity_dense(left: list[float] | None, right: list[float] | None) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return float(sum(l * r for l, r in zip(left, right)))
