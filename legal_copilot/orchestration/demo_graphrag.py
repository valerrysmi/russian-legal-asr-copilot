"""Simple GraphRAG demo over Civil Code articles."""

from __future__ import annotations

import argparse

from legal_copilot.rag.hybrid_retriever import get_default_graphrag_retriever

SAMPLE_QUERIES = [
    "Нужно ли нотариальное удостоверение продажи доли в ООО и когда переходит право на долю?",
    "Какие риски для кредитора или должника возникают при смене участника общества?",
    "Что говорит ГК РФ про недействительность сделки и сроки исковой давности?",
]


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run GraphRAG retrieval over Civil Code articles."
    )
    parser.add_argument(
        "--query",
        type=str,
        help="Single ad-hoc legal question to search for.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="How many articles to return.",
    )
    return parser


def _print_box(title: str, text: str) -> None:
    lines = [line.rstrip() for line in text.splitlines()] or [""]
    content_width = max(len(title), *(len(line) for line in lines))
    border = "+" + "-" * (content_width + 2) + "+"
    print(border)
    print(f"| {title.ljust(content_width)} |")
    print(border)
    for line in lines:
        print(f"| {line.ljust(content_width)} |")
    print(border)


def print_result(query: str, *, top_k: int) -> None:
    retriever = get_default_graphrag_retriever()
    print(f"\n=== QUERY ===\n{query}")
    result = retriever.retrieve(query, top_k=top_k)
    diagnostics = result.diagnostics
    print(f"diagnostics: {diagnostics}")
    print(f"neural_embeddings_enabled: {retriever.vector_store.use_dense_embeddings}")
    print(
        "llm_reranker:",
        f"enabled={diagnostics.get('llm_reranker_enabled')}",
        f"used={diagnostics.get('llm_reranker_used')}",
        f"error={diagnostics.get('llm_reranker_error')}",
    )

    detected_topics = diagnostics.get("detected_topics") or []
    if detected_topics:
        print(f"detected_topics: {', '.join(detected_topics)}")

    query_type = diagnostics.get("query_type")
    if query_type:
        print(f"query_type: {query_type}")

    subqueries = diagnostics.get("subqueries") or []
    if subqueries:
        _print_box("subqueries", "\n".join(f"- {item}" for item in subqueries))

    if result.query_expansion.added_terms:
        _print_box("expanded_query", result.expanded_query)
        print(f"added_terms: {', '.join(result.query_expansion.added_terms)}")

    if result.query_expansion.llm_result and result.query_expansion.llm_result.used:
        print(f"llm_terms: {', '.join(result.query_expansion.llm_result.keywords)}")
    elif result.query_expansion.llm_result and result.query_expansion.llm_result.error:
        print(f"llm_expansion_status: {result.query_expansion.llm_result.error}")

    for hit in result.hits:
        chapter = hit.metadata.get("chapter") or "Без главы"
        summary_preview = (hit.summary or "")[:160].replace("\n", " ")
        preview = hit.text[:180].replace("\n", " ")
        print(
            f"- Статья {hit.article_number}: {hit.title} "
            f"(score={hit.final_score:.3f}, vector={hit.vector_score:.3f}, graph={hit.graph_score:.3f})"
        )
        print(f"  {chapter}")
        print(f"  reasons={', '.join(hit.reasons)}")
        if hit.metadata.get("article_topics"):
            print(f"  article_topics={', '.join(hit.metadata['article_topics'])}")
        if hit.metadata.get("llm_rerank_reason"):
            print(f"  llm_rerank_reason={hit.metadata['llm_rerank_reason']}")
        if summary_preview:
            print(f"  summary={summary_preview}...")
        print(f"  preview={preview}...")


def main() -> None:
    args = build_argument_parser().parse_args()
    if args.query:
        print_result(args.query, top_k=args.top_k)
        return

    for query in SAMPLE_QUERIES:
        print_result(query, top_k=args.top_k)


if __name__ == "__main__":
    main()
