"""Hybrid GraphRAG retrieval over Civil Code articles."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from legal_copilot.rag.graph_builder import (
    DEFAULT_ARTICLE_PATH,
    DEFAULT_GRAPH_PATH,
    GraphIndex,
    build_and_save_graph,
)
from legal_copilot.rag.graph_retriever import GraphRetriever
from legal_copilot.rag.llm_reranker import rerank_with_llm
from legal_copilot.rag.query_expander import ExpandedQuery, expand_legal_query
from legal_copilot.rag.query_understanding import build_search_queries, classify_legal_query
from legal_copilot.rag.reranker import RerankCandidate, rerank_candidates
from legal_copilot.rag.vector_store import InMemoryVectorStore

ARTICLE_REFERENCE_RE = re.compile(
    r"\bст(?:атья|атьи|атье|атью|\.?)\s+(\d+(?:\.\d+)*)",
    re.IGNORECASE,
)
REPEALED_ARTICLE_RE = re.compile(r"\bутрат\w*\s+сил", re.IGNORECASE)


@dataclass
class HybridRetrievalHit:
    article_number: str
    title: str
    summary: str
    text: str
    metadata: dict[str, Any]
    vector_score: float
    graph_score: float
    final_score: float
    reasons: list[str] = field(default_factory=list)


@dataclass
class HybridRetrievalResult:
    query: str
    expanded_query: str
    hits: list[HybridRetrievalHit]
    query_expansion: ExpandedQuery
    diagnostics: dict[str, Any] = field(default_factory=dict)


class GraphRAGRetriever:
    def __init__(
        self,
        *,
        articles: list[dict[str, Any]],
        vector_store: InMemoryVectorStore,
        graph_index: GraphIndex,
    ) -> None:
        self.articles = {
            str(article["article_number"]): article
            for article in articles
            if not self._is_repealed_article(article)
        }
        self.vector_store = vector_store
        self.graph_index = graph_index
        self.graph_retriever = GraphRetriever(graph_index)

    @classmethod
    def from_files(
        cls,
        *,
        article_path: Path = DEFAULT_ARTICLE_PATH,
        graph_path: Path = DEFAULT_GRAPH_PATH,
    ) -> "GraphRAGRetriever":
        articles = json.loads(article_path.read_text(encoding="utf-8"))
        if graph_path.exists():
            graph_index = GraphIndex.load(graph_path)
        else:
            graph_index = build_and_save_graph(article_path, graph_path)
        vector_store = InMemoryVectorStore.from_articles(articles)
        return cls(articles=articles, vector_store=vector_store, graph_index=graph_index)

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 8,
        seed_k: int = 8,
        max_hops: int = 2,
    ) -> HybridRetrievalResult:
        query_understanding = build_search_queries(query)
        query_expansion = expand_legal_query(query)
        search_query = query_expansion.expanded_query

        search_variants = [search_query]
        for subquery in query_understanding.subqueries:
            if subquery and subquery not in search_variants:
                search_variants.append(subquery)

        vector_hit_map = {}
        for search_variant in search_variants:
            for hit in self.vector_store.search(search_variant, top_k=seed_k):
                existing = vector_hit_map.get(hit.document.article_number)
                if not existing or hit.score > existing.score:
                    vector_hit_map[hit.document.article_number] = hit

        seed_scores = {article_number: hit.score for article_number, hit in vector_hit_map.items()}

        for article_number in self._explicit_article_mentions(query):
            if article_number in self.articles:
                seed_scores[article_number] = max(seed_scores.get(article_number, 0.0), 1.0)

        graph_hits = self.graph_retriever.expand_from_seeds(
            seed_scores,
            max_hops=max_hops,
            limit=max(top_k * 4, seed_k * max(1, len(search_variants))),
        )
        graph_hit_map = {hit.article_number: hit for hit in graph_hits}

        candidate_article_numbers = set(vector_hit_map) | set(graph_hit_map)
        candidates = []
        for article_number in candidate_article_numbers:
            if article_number not in self.articles:
                continue

            article = self.articles[article_number]
            vector_hit = vector_hit_map.get(article_number)
            graph_hit = graph_hit_map.get(article_number)
            reasons: list[str] = []
            if vector_hit:
                reasons.extend(vector_hit.reasons)
            if graph_hit:
                reasons.extend(graph_hit.reasons)

            article_understanding = classify_legal_query(
                " ".join(
                    [
                        article.get("title", ""),
                        article.get("summary", ""),
                        " ".join(article.get("keywords", [])),
                    ]
                )
            )
            candidates.append(
                RerankCandidate(
                    article_number=article_number,
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
                        "article_topics": article_understanding.detected_topics,
                    },
                    vector_score=vector_hit.score if vector_hit else 0.0,
                    graph_score=graph_hit.score if graph_hit else 0.0,
                    reasons=reasons,
                )
            )

        ranked_candidates = rerank_candidates(
            search_query,
            candidates,
            top_k=max(top_k * 2, 12),
            query_understanding=query_understanding,
        )
        llm_rerank_result = rerank_with_llm(search_query, ranked_candidates)
        if llm_rerank_result.used:
            llm_score_map = {item.article_number: item for item in llm_rerank_result.items}
            for candidate in ranked_candidates:
                rerank_item = llm_score_map.get(candidate.article_number)
                if not rerank_item:
                    continue
                candidate.final_score = 0.72 * candidate.final_score + 0.28 * rerank_item.score
                candidate.reasons.append("llm_rerank")
                if rerank_item.reason:
                    candidate.metadata["llm_rerank_reason"] = rerank_item.reason

            ranked_candidates = sorted(
                ranked_candidates,
                key=lambda candidate: candidate.final_score,
                reverse=True,
            )

        ranked_candidates = ranked_candidates[:top_k]
        hits = [
            HybridRetrievalHit(
                article_number=candidate.article_number,
                title=candidate.title,
                summary=candidate.summary,
                text=candidate.text,
                metadata=candidate.metadata,
                vector_score=candidate.vector_score,
                graph_score=candidate.graph_score,
                final_score=candidate.final_score,
                reasons=sorted(set(candidate.reasons)),
            )
            for candidate in ranked_candidates
        ]
        return HybridRetrievalResult(
            query=query,
            expanded_query=search_query,
            hits=hits,
            query_expansion=query_expansion,
            diagnostics={
                "vector_seed_count": len(vector_hit_map),
                "graph_candidate_count": len(graph_hits),
                "final_hit_count": len(hits),
                "neural_embeddings_enabled": self.vector_store.use_dense_embeddings,
                "search_variant_count": len(search_variants),
                "subqueries": query_understanding.subqueries,
                "query_type": query_understanding.query_type,
                "detected_topics": query_understanding.topic_labels,
                "llm_reranker_enabled": llm_rerank_result.enabled,
                "llm_reranker_used": llm_rerank_result.used,
                "llm_reranker_error": llm_rerank_result.error,
                "llm_reranker_candidate_count": len(llm_rerank_result.items),
                "expansion_term_count": len(query_expansion.added_terms),
                "expansion_rules": query_expansion.triggered_rules,
                "llm_expansion_enabled": query_expansion.llm_result.enabled if query_expansion.llm_result else False,
                "llm_expansion_used": query_expansion.llm_result.used if query_expansion.llm_result else False,
                "llm_expansion_error": query_expansion.llm_result.error if query_expansion.llm_result else None,
            },
        )

    @staticmethod
    def _explicit_article_mentions(query: str) -> set[str]:
        return {match.group(1) for match in ARTICLE_REFERENCE_RE.finditer(query)}

    @staticmethod
    def _is_repealed_article(article: dict[str, Any]) -> bool:
        title = str(article.get("title", ""))
        summary = str(article.get("summary", ""))
        text = str(article.get("text", ""))
        searchable = f"{title}\n{summary}\n{text[:400]}"
        return bool(REPEALED_ARTICLE_RE.search(searchable))


@lru_cache(maxsize=1)
def get_default_graphrag_retriever() -> GraphRAGRetriever:
    return GraphRAGRetriever.from_files()
