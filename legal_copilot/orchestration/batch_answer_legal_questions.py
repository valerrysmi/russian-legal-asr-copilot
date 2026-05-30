"""Batch-generate answers for questions stored in a DOCX table."""

from __future__ import annotations

import argparse
import csv
import sys
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path

from legal_copilot.agents.context_manager import StreamingContextManager
from legal_copilot.orchestration.answer_formatting import build_short_answer
from legal_copilot.orchestration.graph import run_legal_copilot_turn

WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
DEFAULT_INPUT = Path("Юридические вопросы.docx")
DEFAULT_OUTPUT = Path("Юридические вопросы - результаты.csv")


@dataclass
class SourceQuestionRow:
    table_index: int
    row_index: int
    source_header_question: str
    source_header_answer: str
    source_header_articles: str
    question: str
    reference_answer: str
    reference_articles: str


def parse_docx_tables(docx_path: Path) -> list[SourceQuestionRow]:
    with zipfile.ZipFile(docx_path) as archive:
        document_xml = archive.read("word/document.xml")

    root = ET.fromstring(document_xml)
    body = root.find("w:body", WORD_NS)
    if body is None:
        return []

    rows: list[SourceQuestionRow] = []
    for table_index, table in enumerate(body.findall("w:tbl", WORD_NS), start=1):
        tr_nodes = table.findall("w:tr", WORD_NS)
        if len(tr_nodes) < 2:
            continue

        extracted_rows = [_extract_row_cells(tr_node) for tr_node in tr_nodes]
        first_row = extracted_rows[0]
        if len(first_row) < 3:
            continue

        if _looks_like_header_row(first_row):
            header = first_row
            data_rows = extracted_rows[1:]
        else:
            header = ["Вопрос", "Короткий ответ", "Нормы/статьи"]
            data_rows = extracted_rows

        for row_index, cells in enumerate(data_rows, start=1):
            if len(cells) < 3:
                continue
            question = cells[0].strip()
            reference_answer = cells[1].strip()
            reference_articles = cells[2].strip()
            if not question:
                continue

            rows.append(
                SourceQuestionRow(
                    table_index=table_index,
                    row_index=row_index,
                    source_header_question=header[0].strip(),
                    source_header_answer=header[1].strip(),
                    source_header_articles=header[2].strip(),
                    question=question,
                    reference_answer=reference_answer,
                    reference_articles=reference_articles,
                )
            )

    return rows


def _extract_row_cells(tr_node: ET.Element) -> list[str]:
    cells: list[str] = []
    for tc_node in tr_node.findall("w:tc", WORD_NS):
        text_fragments = [text_node.text or "" for text_node in tc_node.findall(".//w:t", WORD_NS)]
        cell_text = " ".join("".join(text_fragments).split())
        cells.append(cell_text)
    return cells


def _looks_like_header_row(cells: list[str]) -> bool:
    first_cell = (cells[0] if cells else "").strip().lower()
    if "?" in first_cell:
        return False
    if first_cell[:3].isdigit() or first_cell[:2].isdigit() or first_cell[:1].isdigit():
        return False

    sample = " ".join(cell.lower() for cell in cells[:3])
    header_markers = (
        "вопрос",
        "короткий ответ",
        "нормы",
        "где смотреть",
        "ориентир по ответу",
    )
    return any(marker in sample for marker in header_markers)


def collect_used_articles(turn_result) -> str:
    if not turn_result.retrieved_context:
        return ""

    used_articles: list[str] = []
    for hit in turn_result.retrieved_context.result.hits[:5]:
        used_articles.append(f"ст. {hit.article_number} ГК РФ - {hit.title}")
    return "; ".join(used_articles)


def generate_batch_answers(
    input_path: Path,
    output_path: Path,
    *,
    limit: int | None = None,
) -> int:
    rows = parse_docx_tables(input_path)
    if limit is not None:
        rows = rows[:limit]

    if not rows:
        print(f"[batch] no question rows found in {input_path}")
        return 0

    print(f"[batch] loaded {len(rows)} questions from {input_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "table_index",
                "row_index",
                "source_header_question",
                "source_header_answer",
                "source_header_articles",
                "question",
                "reference_answer",
                "reference_articles",
                "short_generated_answer",
                "generated_answer",
                "used_articles",
                "route",
                "answer_source",
                "answer_generation_error",
            ],
        )
        writer.writeheader()

        for index, row in enumerate(rows, start=1):
            print(f"[batch] ({index}/{len(rows)}) processing: {row.question}")
            session = StreamingContextManager(session_id=f"batch-{index}")
            result = run_legal_copilot_turn(
                row.question,
                context_manager=session,
                session_id=f"batch-{index}",
            )
            generated_answer = (result.answer_text or "").strip()
            short_generated_answer = build_short_answer(generated_answer)
            used_articles = collect_used_articles(result)

            writer.writerow(
                {
                    "table_index": row.table_index,
                    "row_index": row.row_index,
                    "source_header_question": row.source_header_question,
                    "source_header_answer": row.source_header_answer,
                    "source_header_articles": row.source_header_articles,
                    "question": row.question,
                    "reference_answer": row.reference_answer,
                    "reference_articles": row.reference_articles,
                    "short_generated_answer": short_generated_answer,
                    "generated_answer": generated_answer,
                    "used_articles": used_articles,
                    "route": result.route,
                    "answer_source": result.answer_source or "",
                    "answer_generation_error": result.answer_generation_error or "",
                }
            )

    print(f"[batch] saved results to {output_path}")
    return len(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate answers for all questions from a DOCX file with legal question tables."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Path to the source DOCX file with questions.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path to the output CSV file.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional limit for the number of processed questions.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    input_path = args.input.resolve()
    output_path = args.output.resolve()

    if not input_path.exists():
        print(f"[batch] input file not found: {input_path}", file=sys.stderr)
        return 1

    generate_batch_answers(input_path, output_path, limit=args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
