"""Format batch-generated legal answers into a readable Markdown report."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from legal_copilot.orchestration.answer_formatting import build_short_answer, normalize_text

DEFAULT_INPUT = Path("Юридические вопросы - результаты.csv")
DEFAULT_OUTPUT = Path("Юридические вопросы - результаты.md")


def load_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def build_markdown(rows: list[dict[str, str]]) -> str:
    lines: list[str] = []
    lines.append("# Результаты генерации юридических ответов")
    lines.append("")
    lines.append(f"Всего вопросов: {len(rows)}")
    lines.append("")

    for index, row in enumerate(rows, start=1):
        short_generated_answer = row.get("short_generated_answer") or build_short_answer(row.get("generated_answer"))
        sheet_name = normalize_text(row.get("sheet_name"))
        legal_domain = normalize_text(row.get("legal_domain"))
        gk_coverage = normalize_text(row.get("gk_coverage"))
        can_answer = normalize_text(row.get("can_answer_from_civil_code"))

        lines.append(f"## {index}. {normalize_text(row.get('question'))}")
        lines.append("")
        if sheet_name != "—":
            lines.append("**Лист / источник**")
            lines.append("")
            lines.append(sheet_name)
            lines.append("")
        if legal_domain != "—":
            lines.append("**Отрасль права**")
            lines.append("")
            lines.append(legal_domain)
            lines.append("")
        if gk_coverage != "—" or can_answer != "—":
            lines.append("**Оценка применимости ГК РФ**")
            lines.append("")
            lines.append(f"Покрытие ГК РФ: {gk_coverage}; можно ответить только по ГК РФ: {can_answer}")
            lines.append("")
        lines.append("**Референсный ответ**")
        lines.append("")
        lines.append(normalize_text(row.get("reference_answer")))
        lines.append("")
        lines.append("**Референсные статьи**")
        lines.append("")
        lines.append(normalize_text(row.get("reference_articles")))
        lines.append("")
        lines.append("**Краткий ответ модели**")
        lines.append("")
        lines.append(normalize_text(short_generated_answer))
        lines.append("")
        lines.append("**Ответ модели**")
        lines.append("")
        lines.append(normalize_text(row.get("generated_answer")))
        lines.append("")
        lines.append("**Статьи модели**")
        lines.append("")
        lines.append(normalize_text(row.get("used_articles")))
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def format_batch_answers(input_path: Path, output_path: Path) -> int:
    rows = load_rows(input_path)
    if not rows:
        print(f"[format] no rows found in {input_path}")
        return 0

    markdown = build_markdown(rows)
    output_path.write_text(markdown, encoding="utf-8")
    print(f"[format] saved readable report to {output_path}")
    return len(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert batch answer CSV into a readable Markdown report."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Path to the batch CSV file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path to the Markdown report.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    input_path = args.input.resolve()
    output_path = args.output.resolve()

    if not input_path.exists():
        print(f"[format] input file not found: {input_path}", file=sys.stderr)
        return 1

    format_batch_answers(input_path, output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
