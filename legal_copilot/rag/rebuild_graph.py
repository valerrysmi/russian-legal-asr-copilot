"""CLI entrypoint for rebuilding the Civil Code graph index."""

from __future__ import annotations

import argparse
from pathlib import Path

from legal_copilot.rag.graph_builder import (
    DEFAULT_ARTICLE_PATH,
    DEFAULT_GRAPH_PATH,
    build_and_save_graph,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rebuild the GraphRAG graph index from Civil Code articles."
    )
    parser.add_argument(
        "--articles",
        type=Path,
        default=DEFAULT_ARTICLE_PATH,
        help="Path to articles.json.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_GRAPH_PATH,
        help="Path to graph_index.json.",
    )
    return parser


def main() -> None:
    args = build_argument_parser().parse_args()
    graph = build_and_save_graph(args.articles, args.output)
    print(f"Graph rebuilt: {args.output}")
    print(f"Nodes: {len(graph.nodes)}")
    print(f"Adjacency entries: {len(graph.adjacency)}")


if __name__ == "__main__":
    main()
