"""Generate concise summaries and keywords for Civil Code articles."""

from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter
from pathlib import Path

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency
    OpenAI = None

from legal_copilot.yandex_config import (
    get_yandex_api_key_path,
    load_yandex_api_key,
    load_yandex_base_url,
    load_yandex_folder_id,
    load_yandex_model,
)

DEFAULT_ARTICLE_PATH = Path("legal_copilot/data/civil_code/articles.json")
DEFAULT_CHECKPOINT_PATH = Path("legal_copilot/data/civil_code/article_summary_checkpoint.json")

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
LEADING_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)?[.)]?\s*")
WHITESPACE_RE = re.compile(r"\s+")
TOKEN_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9-]{3,}")

SUMMARY_SYSTEM_PROMPT = """Ты готовишь краткие summaries для поиска по статьям Гражданского кодекса РФ.

Верни только краткое резюме на русском языке.

Правила:
- 1-2 предложения.
- До 220 символов.
- Кратко опиши, какой вопрос регулирует статья и в чем основное правило.
- Не копируй длинные куски исходного текста.
- Не добавляй дисклеймеры, пояснения и служебный текст.
"""

KEYWORD_STOPWORDS = {
    "статья",
    "настоящий",
    "настоящего",
    "кодекс",
    "кодекса",
    "федерации",
    "СЂРѕСЃСЃРёР№СЃРєРѕР№",
    "РїСѓРЅРєС'",
    "пункта",
    "часть",
    "глава",
    "раздел",
    "подраздел",
    "лицо",
    "лица",
    "лиц",
    "закон",
    "закона",
    "законом",
    "которая",
    "который",
    "которые",
    "может",
    "должен",
    "должна",
    "также",
    "если",
    "либо",
    "только",
    "такой",
    "РёРЅРѕРµ",
    "РёРЅРѕР№",
    "иных",
    "этой",
    "этого",
    "этот",
    "быть",
    "является",
    "являются",
    "РїРѕСЂСЏРґРѕРє",
    "случай",
}

IMPORTANT_KEYWORDS = {
    "доля",
    "общество",
    "участник",
    "собственность",
    "обязательство",
    "РґРѕРіРѕРІРѕСЂ",
    "сделка",
    "регистрация",
    "нотариус",
    "кредитор",
    "должник",
    "залог",
    "убытки",
    "вред",
    "давность",
    "РёСЃРє",
    "акционер",
    "корпоративный",
}


def normalize_text(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text.replace("\n", " ")).strip()


def log_stage(message: str) -> None:
    print(f"[article_summarizer] {message}")


def strip_leading_number(text: str) -> str:
    return LEADING_NUMBER_RE.sub("", text).strip()


def split_sentences(text: str) -> list[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []
    sentences = [strip_leading_number(sentence) for sentence in SENTENCE_SPLIT_RE.split(normalized)]
    return [sentence for sentence in sentences if sentence]


def shorten_text(text: str, *, max_chars: int = 220) -> str:
    text = normalize_text(text)
    if len(text) <= max_chars:
        return text

    cut = text[:max_chars]
    last_break = max(cut.rfind(". "), cut.rfind("; "), cut.rfind(", "))
    if last_break >= max_chars // 2:
        cut = cut[:last_break].rstrip(" ,;")
    return cut.rstrip() + "..."


def summarize_article_heuristically(article: dict) -> str:
    title = normalize_text(article.get("title", ""))
    sentences = split_sentences(article.get("text", ""))
    if not title and not sentences:
        return ""

    summary_parts = []
    if title:
        summary_parts.append(f"Регулирует вопросы, связанные с {title.lower()}.")

    if sentences:
        first_sentence = shorten_text(sentences[0], max_chars=130)
        summary_parts.append(first_sentence)

    summary = normalize_text(" ".join(summary_parts))
    return shorten_text(summary, max_chars=220)


def _build_client():
    if OpenAI is None:
        return None
    api_key, _error = load_yandex_api_key()
    folder_id, _folder_error = load_yandex_folder_id()
    return OpenAI(
        api_key=api_key,
        base_url=load_yandex_base_url(),
        project=folder_id,
    )


def _llm_available() -> tuple[bool, str | None]:
    if OpenAI is None:
        return False, "Python package 'openai' is not installed for Yandex-compatible API client"
    api_key, error = load_yandex_api_key()
    if not api_key:
        return False, error or f"Yandex API key file not found: {get_yandex_api_key_path()}"
    folder_id, folder_error = load_yandex_folder_id()
    if not folder_id:
        return False, folder_error
    return True, None


def build_article_context(article: dict) -> str:
    path_parts = [
        article.get("part"),
        article.get("section"),
        article.get("subsection"),
        article.get("chapter"),
    ]
    hierarchy_path = " > ".join(str(part) for part in path_parts if part) or "Иерархия не указана"

    return (
        f"Статья {article.get('article_number', '')}. {article.get('title', '')}\n"
        f"Иерархия: {hierarchy_path}\n"
        f"Текст статьи:\n{article.get('text', '')[:4500]}"
    )


def summarize_article_with_llm(article: dict) -> tuple[str | None, str | None]:
    available, error = _llm_available()
    if not available:
        return None, error

    client = _build_client()
    model, model_error = load_yandex_model()
    if not model:
        return None, model_error

    try:
        response = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_article_context(article) + "\n\nПодготовь только краткий summary на русском языке.",
                },
            ],
            temperature=0.1,
            max_output_tokens=500
        )
        summary = normalize_text(response.output_text)
    except Exception as exc:  # pragma: no cover - external API path
        return None, str(exc)

    if not summary:
        return None, "empty LLM summary"
    return shorten_text(summary, max_chars=220), None


def extract_keywords(article: dict, summary: str, *, max_keywords: int = 7) -> list[str]:
    source_text = normalize_text(
        f"{article.get('title', '')} {summary} {article.get('chapter', '')} {article.get('text', '')[:1200]}"
    ).lower().replace("С'", "Рµ")

    tokens = TOKEN_RE.findall(source_text)
    counts = Counter(
        token for token in tokens
        if token not in KEYWORD_STOPWORDS and not token.isdigit()
    )

    scored = []
    for token, count in counts.most_common(50):
        score = count + (5 if token in IMPORTANT_KEYWORDS else 0)
        scored.append((token, score))
    scored.sort(key=lambda item: item[1], reverse=True)

    keywords: list[str] = []
    seen: set[str] = set()
    for token, _score in scored:
        if token in seen:
            continue
        seen.add(token)
        keywords.append(token)
        if len(keywords) >= max_keywords:
            break
    return keywords


def summarize_article(article: dict, *, mode: str = "heuristic") -> tuple[str, str, str | None]:
    if mode == "heuristic":
        return summarize_article_heuristically(article), "heuristic", None

    if mode == "llm":
        summary, error = summarize_article_with_llm(article)
        if summary:
            return summary, "llm", None
        return "", "llm", error

    if mode == "hybrid":
        summary, error = summarize_article_with_llm(article)
        if summary:
            return summary, "llm", None
        return summarize_article_heuristically(article), "heuristic", error

    raise ValueError(f"Unsupported summary mode: {mode}")


def save_checkpoint(checkpoint: dict, checkpoint_path: Path) -> None:
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(
        json.dumps(checkpoint, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_checkpoint(checkpoint_path: Path) -> dict:
    if not checkpoint_path.exists():
        return {}
    return json.loads(checkpoint_path.read_text(encoding="utf-8"))


def add_summaries_to_articles(
    articles: list[dict],
    *,
    mode: str = "heuristic",
    overwrite: bool = False,
    only_missing: bool = False,
    limit: int | None = None,
    show_progress: bool = True,
    checkpoint_path: Path | None = None,
    save_every: int = 25,
) -> tuple[list[dict], dict[str, int]]:
    enriched_articles = []
    checkpoint = load_checkpoint(checkpoint_path) if checkpoint_path else {}
    stats = {
        "processed": 0,
        "llm": 0,
        "heuristic": 0,
        "skipped": 0,
        "errors": 0,
        "restored_from_checkpoint": 0,
    }

    start_time = time.time()

    for index, article in enumerate(articles):
        enriched_article = dict(article)
        article_number = str(enriched_article.get("article_number", f"#{index + 1}"))

        if limit is not None and index >= limit:
            enriched_articles.append(enriched_article)
            stats["skipped"] += 1
            continue

        if article_number in checkpoint and not overwrite:
            enriched_article.update(checkpoint[article_number])
            enriched_articles.append(enriched_article)
            stats["restored_from_checkpoint"] += 1
            continue

        has_summary = bool(enriched_article.get("summary"))
        if only_missing and has_summary:
            enriched_articles.append(enriched_article)
            stats["skipped"] += 1
            continue
        if not overwrite and has_summary and not only_missing:
            enriched_articles.append(enriched_article)
            stats["skipped"] += 1
            continue

        if show_progress:
            log_stage(f"processing article {article_number} ({index + 1}/{len(articles)}) mode={mode}")

        summary, source, error = summarize_article(enriched_article, mode=mode)
        if summary:
            enriched_article["summary"] = summary
            enriched_article["summary_source"] = source
            enriched_article["summary_error"] = error
            stats[source] += 1
            if show_progress:
                log_stage(f"article {article_number}: summary generated via {source}")
                log_stage(f"article {article_number}: summary -> {summary}")
                if error:
                    log_stage(f"article {article_number}: summary_error -> {error}")
        else:
            summary = summarize_article_heuristically(enriched_article)
            enriched_article["summary"] = summary
            enriched_article["summary_source"] = "heuristic"
            enriched_article["summary_error"] = error or "summary generation failed"
            stats["heuristic"] += 1
            stats["errors"] += 1
            if show_progress:
                log_stage(
                    f"article {article_number}: fallback to heuristic summary because "
                    f"{enriched_article['summary_error']}"
                )
                log_stage(f"article {article_number}: summary -> {summary}")
                log_stage(
                    f"article {article_number}: summary_error -> "
                    f"{enriched_article['summary_error']}"
                )

        keywords = extract_keywords(enriched_article, enriched_article["summary"])
        enriched_article["keywords"] = keywords
        if show_progress:
            log_stage(f"article {article_number}: keywords -> {', '.join(keywords)}")

        if checkpoint_path:
            checkpoint[article_number] = {
                "summary": enriched_article["summary"],
                "summary_source": enriched_article.get("summary_source"),
                "summary_error": enriched_article.get("summary_error"),
                "keywords": enriched_article.get("keywords", []),
            }
            if (stats["processed"] + 1) % save_every == 0:
                save_checkpoint(checkpoint, checkpoint_path)
                if show_progress:
                    elapsed = time.time() - start_time
                    log_stage(
                        f"checkpoint saved after {stats['processed'] + 1} processed articles; elapsed={elapsed:.1f}s"
                    )

        stats["processed"] += 1
        enriched_articles.append(enriched_article)

    if checkpoint_path:
        save_checkpoint(checkpoint, checkpoint_path)

    return enriched_articles, stats


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate summaries for Civil Code articles.")
    parser.add_argument("--input", type=Path, default=DEFAULT_ARTICLE_PATH, help="Path to articles.json")
    parser.add_argument("--output", type=Path, default=DEFAULT_ARTICLE_PATH, help="Where to write enriched articles.json")
    parser.add_argument("--mode", choices=("heuristic", "llm", "hybrid"), default="heuristic", help="How to generate summaries.")
    parser.add_argument("--limit", type=int, help="Only process the first N articles.")
    parser.add_argument("--overwrite", action="store_true", help="Rewrite summaries even if they already exist.")
    parser.add_argument("--only-missing", action="store_true", help="Only generate summaries for articles without summary.")
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT_PATH, help="Checkpoint file for resuming processing.")
    parser.add_argument("--save-every", type=int, default=25, help="Save checkpoint every N processed articles.")
    parser.add_argument("--no-checkpoint", action="store_true", help="Disable checkpointing.")
    return parser


def main() -> None:
    args = build_argument_parser().parse_args()
    checkpoint_path = None if args.no_checkpoint else args.checkpoint

    log_stage(f"loading articles from {args.input}")
    articles = json.loads(args.input.read_text(encoding="utf-8"))
    log_stage(
        f"loaded {len(articles)} articles; mode={args.mode}; overwrite={args.overwrite}; "
        f"only_missing={args.only_missing}; limit={args.limit}"
    )
    if checkpoint_path:
        log_stage(f"checkpoint file: {checkpoint_path}")

    enriched_articles, stats = add_summaries_to_articles(
        articles,
        mode=args.mode,
        overwrite=args.overwrite,
        only_missing=args.only_missing,
        limit=args.limit,
        show_progress=True,
        checkpoint_path=checkpoint_path,
        save_every=args.save_every,
    )

    log_stage(f"writing summaries to {args.output}")
    args.output.write_text(
        json.dumps(enriched_articles, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log_stage("done")
    print(f"Summaries generated -> {args.output}")
    print(
        f"processed={stats['processed']} heuristic={stats['heuristic']} llm={stats['llm']} "
        f"errors={stats['errors']} skipped={stats['skipped']} restored_from_checkpoint={stats['restored_from_checkpoint']}"
    )


if __name__ == "__main__":
    main()
