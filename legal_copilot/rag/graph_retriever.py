"""Graph-based expansion over Civil Code articles."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from legal_copilot.rag.graph_builder import GraphIndex

EDGE_DECAY = {
    "refers_to": 0.90,
    "referenced_by": 0.82,
    "mentions_concept": 0.72,
    "concept_in_article": 0.68,
    "mentions_keyword": 0.76,
    "keyword_in_article": 0.74,
    "part_of": 0.58,
    "contains": 0.58,
}


@dataclass
class GraphSearchHit:
    article_number: str
    score: float
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class GraphRetriever:
    def __init__(self, graph_index: GraphIndex) -> None:
        self.graph_index = graph_index

    def expand_from_seeds(
        self,
        seed_scores: dict[str, float],
        *,
        max_hops: int = 2,
        limit: int = 30,
    ) -> list[GraphSearchHit]:
        article_scores: dict[str, float] = defaultdict(float)
        reasons: dict[str, list[str]] = defaultdict(list)
        best_node_scores: dict[tuple[str, int], float] = {}
        queue = deque()

        for article_number, seed_score in seed_scores.items():
            node_id = f"article:{article_number}"
            queue.append((node_id, seed_score, 0))
            article_scores[article_number] = max(article_scores[article_number], seed_score)
            reasons[article_number].append("seed_article")
            best_node_scores[(node_id, 0)] = seed_score

        while queue:
            node_id, current_score, depth = queue.popleft()
            if depth >= max_hops:
                continue

            for connection in self.graph_index.neighbors(node_id):
                if connection.edge_type == "semantic_similar_to":
                    continue
                edge_decay = EDGE_DECAY.get(connection.edge_type, 0.5)
                next_score = current_score * edge_decay * connection.weight
                if next_score < 0.03:
                    continue

                state_key = (connection.target, depth + 1)
                if best_node_scores.get(state_key, 0.0) >= next_score:
                    continue

                best_node_scores[state_key] = next_score
                queue.append((connection.target, next_score, depth + 1))

                target_node = self.graph_index.nodes.get(connection.target, {})
                if target_node.get("node_type") == "article":
                    article_number = str(target_node["article_number"])
                    if next_score > article_scores[article_number]:
                        article_scores[article_number] = next_score
                    reasons[article_number].append(connection.edge_type)

        hits = [
            GraphSearchHit(
                article_number=article_number,
                score=score,
                reasons=sorted(set(reasons[article_number])),
            )
            for article_number, score in article_scores.items()
        ]
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return hits[:limit]
