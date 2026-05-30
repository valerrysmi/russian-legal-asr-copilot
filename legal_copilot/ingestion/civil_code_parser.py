"""Parse the Russian Civil Code PDF into structured JSON articles."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    from pypdf import PdfReader
except ImportError as exc:  # pragma: no cover - import error is environment-specific
    raise SystemExit(
        "pypdf is required to parse civil_code.pdf. Install it with `pip install pypdf`."
    ) from exc


DEFAULT_INPUT = Path("legal_copilot/data/civil_code/civil_code.pdf")
DEFAULT_OUTPUT = Path("legal_copilot/data/civil_code/articles.json")

HEADER_PATTERNS = (
    re.compile(r"^Дата актуализации:"),
    re.compile(r"^Актуальную версию смотрите на сайте$"),
    re.compile(r"^WWW\.GARANT\.RU$"),
    re.compile(r'^© ООО "НПП "ГАР АНТ-СЕРВИС-УНИВЕРСИТЕТ", \d{4}\.$'),
    re.compile(r"^Система ГАР АНТ выпускается с 1990г\.$"),
)

PART_RE = re.compile(r"^Часть\s+.+$")
SECTION_RE = re.compile(r"^Раздел\s+[IVXLCDM]+(?:\.\s*.*)?$")
SUBSECTION_RE = re.compile(r"^Подраздел\s+\d+(?:\.\s*.*)?$")
CHAPTER_RE = re.compile(r"^Глава\s+\d+(?:\.\d+)?\.\s*.*$")
ARTICLE_RE = re.compile(r"^Статья\s+(\d+(?:\.\d+)*)\.\s*(.*)$")
NUMBERED_BODY_RE = re.compile(r"^\d+(?:\.\d+)?[.)]")
STRUCTURE_START_RE = re.compile(
    r"^(?:Часть\s+|Раздел\s+|Подраздел\s+|Глава\s+|Статья\s+)"
)
LOWERCASE_START_RE = re.compile(r"^[a-zа-яё]")


@dataclass
class Context:
    part: str | None = None
    section: str | None = None
    subsection: str | None = None
    chapter: str | None = None


def normalize_spaces(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def is_header_line(line: str) -> bool:
    return any(pattern.match(line) for pattern in HEADER_PATTERNS)


def extract_page_lines(pdf_path: Path) -> list[list[str]]:
    reader = PdfReader(str(pdf_path))
    pages: list[list[str]] = []

    for page in reader.pages:
        raw_text = page.extract_text() or ""
        cleaned_lines = []
        for raw_line in raw_text.splitlines():
            line = normalize_spaces(raw_line)
            if not line or is_header_line(line):
                continue
            cleaned_lines.append(line)
        pages.append(cleaned_lines)

    return pages


def consume_multiline_heading(lines: list[str], start: int) -> tuple[str, int]:
    heading = lines[start]
    index = start + 1

    while index < len(lines):
        candidate = lines[index]
        if STRUCTURE_START_RE.match(candidate):
            break
        if re.match(r"^\d+(?:\.\d+)?[.)]", candidate):
            break
        if candidate[:1].isupper():
            break
        heading = f"{heading} {candidate}"
        index += 1

    return normalize_spaces(heading), index


def clean_article_text(lines: Iterable[str]) -> str:
    text = "\n".join(line.strip() for line in lines if line.strip())
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_articles(pages: list[list[str]]) -> list[dict]:
    flat_lines: list[tuple[int, str]] = []
    for page_number, page_lines in enumerate(pages, start=1):
        flat_lines.extend((page_number, line) for line in page_lines)

    context = Context()
    articles: list[dict] = []
    current_article: dict | None = None

    index = 0
    while index < len(flat_lines):
        page_number, line = flat_lines[index]

        if PART_RE.match(line):
            context.part, index = consume_context_heading(flat_lines, index)
            continue

        if SECTION_RE.match(line):
            context.section, index = consume_context_heading(flat_lines, index)
            continue

        if SUBSECTION_RE.match(line):
            context.subsection, index = consume_context_heading(flat_lines, index)
            continue

        if CHAPTER_RE.match(line):
            context.chapter, index = consume_context_heading(flat_lines, index)
            continue

        article_match = ARTICLE_RE.match(line)
        if article_match:
            if current_article:
                current_article["text"] = clean_article_text(current_article["text_lines"])
                del current_article["text_lines"]
                articles.append(current_article)

            article_number = article_match.group(1)
            raw_title = article_match.group(2).strip()
            title_lines = [raw_title] if raw_title else []
            index += 1

            while index < len(flat_lines):
                _, candidate = flat_lines[index]
                if STRUCTURE_START_RE.match(candidate):
                    break
                if NUMBERED_BODY_RE.match(candidate):
                    break
                if LOWERCASE_START_RE.match(candidate):
                    title_lines.append(candidate)
                    index += 1
                    continue
                if title_lines:
                    break
                title_lines.append(candidate)
                index += 1

            current_article = {
                "article_number": article_number,
                "title": normalize_spaces(" ".join(title_lines)),
                "part": context.part,
                "section": context.section,
                "subsection": context.subsection,
                "chapter": context.chapter,
                "start_page": page_number,
                "text_lines": [],
            }
            continue

        if current_article:
            current_article["text_lines"].append(line)
            current_article["end_page"] = page_number

        index += 1

    if current_article:
        current_article["text"] = clean_article_text(current_article["text_lines"])
        del current_article["text_lines"]
        current_article.setdefault("end_page", current_article["start_page"])
        articles.append(current_article)

    return articles


def consume_context_heading(
    flat_lines: list[tuple[int, str]], start: int
) -> tuple[str, int]:
    page_lines: list[str] = []
    page_number = flat_lines[start][0]
    index = start

    while index < len(flat_lines):
        current_page, line = flat_lines[index]
        if index > start and STRUCTURE_START_RE.match(line):
            break
        if index > start and current_page != page_number and line[:1].isupper():
            break
        page_lines.append(line)
        if line.endswith("."):
            index += 1
            break
        index += 1
        if len(page_lines) >= 3:
            break

    heading, _ = consume_multiline_heading(page_lines, 0)
    return heading, index


def save_articles(articles: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(articles, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parse civil_code.pdf into a JSON file with structured articles."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Path to source PDF.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path to output JSON file.",
    )
    return parser


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    pages = extract_page_lines(args.input)
    articles = parse_articles(pages)
    save_articles(articles, args.output)
    print(f"Parsed {len(articles)} articles into {args.output}")


if __name__ == "__main__":
    main()
