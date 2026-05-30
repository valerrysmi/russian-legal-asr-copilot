"""In-memory vector store for Civil Code article retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from legal_copilot.rag.embeddings import (
    build_idf,
    cosine_similarity_sparse,
    embed_text,
    tokenize,
)

REPEALED_ARTICLE_RE = re.compile(r"\bутрат\w*\s+сил", re.IGNORECASE)


@dataclass
class ArticleDocument:
    article_number: str
    title: str
    summary: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def document_id(self) -> str:
        return self.article_number

    @property
    def searchable_text(self) -> str:
        structure = " ".join(
            str(value)
            for key, value in self.metadata.items()
            if key in {"part", "section", "subsection", "chapter"} and value
        )
        return f"{self.title}\n{self.title}\n{self.summary}\n{self.summary}\n{structure}\n{self.text}"


@dataclass
class VectorSearchHit:
    document: ArticleDocument
    score: float
    reasons: list[str] = field(default_factory=list)
    sparse_score: float = 0.0
    dense_score: float = 0.0


class InMemoryVectorStore:
    def __init__(
        self,
        documents: list[ArticleDocument],
        *,
        idf: dict[str, float],
        document_vectors: dict[str, dict[str, float]],
        document_tokens: dict[str, list[str]],
        dense_document_vectors: dict[str, list[float] | None],
    ) -> None:
        self.documents = {document.document_id: document for document in documents}
        self.idf = idf
        self.document_vectors = document_vectors
        self.document_tokens = document_tokens
        self.dense_document_vectors = dense_document_vectors
        self.use_dense_embeddings = False

    @classmethod
    def from_articles(cls, articles: list[dict[str, Any]]) -> "InMemoryVectorStore":
        documents = [
            ArticleDocument(
                article_number=str(article["article_number"]),
                title=article["title"],
                summary=article.get("summary", ""),
                text=article["text"],
                metadata={
                    "part": article.get("part"),
                    "section": article.get("section"),
                    "subsection": article.get("subsection"),
                    "chapter": article.get("chapter"),
                    "start_page": article.get("start_page"),
                    "end_page": article.get("end_page"),
                    "summary": article.get("summary", ""),
                },
            )
            for article in articles
            if not _is_repealed_article(article)
        ]
        tokenized_documents = [tokenize(document.searchable_text) for document in documents]
        idf = build_idf(tokenized_documents)
        document_vectors = {
            document.document_id: embed_text(document.searchable_text, idf)
            for document in documents
        }
        document_tokens = {
            document.document_id: tokenize(document.searchable_text)
            for document in documents
        }
        dense_document_vectors = {document.document_id: None for document in documents}
        return cls(
            documents,
            idf=idf,
            document_vectors=document_vectors,
            document_tokens=document_tokens,
            dense_document_vectors=dense_document_vectors,
        )

    @classmethod
    def from_article_file(cls, article_path: Path) -> "InMemoryVectorStore":
        import json

        articles = json.loads(article_path.read_text(encoding="utf-8"))
        return cls.from_articles(articles)

    def get_document(self, document_id: str) -> ArticleDocument | None:
        return self.documents.get(document_id)

    def search(self, query: str, *, top_k: int = 10) -> list[VectorSearchHit]:
        query_vector = embed_text(query, self.idf)
        if not query_vector:
            return []

        scored_hits = []
        for document_id, document_vector in self.document_vectors.items():
            sparse_score = cosine_similarity_sparse(query_vector, document_vector)
            dense_score = 0.0
            score = sparse_score

            if score <= 0:
                continue

            reasons = ["vector_similarity"]

            scored_hits.append(
                VectorSearchHit(
                    document=self.documents[document_id],
                    score=score,
                    reasons=reasons,
                    sparse_score=sparse_score,
                    dense_score=dense_score,
                )
            )

        scored_hits.sort(key=lambda hit: hit.score, reverse=True)
        return scored_hits[:top_k]


def _is_repealed_article(article: dict[str, Any]) -> bool:
    title = str(article.get("title", ""))
    summary = str(article.get("summary", ""))
    text = str(article.get("text", ""))
    searchable = f"{title}\n{summary}\n{text[:400]}"
    return bool(REPEALED_ARTICLE_RE.search(searchable))
