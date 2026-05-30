"""Transcript normalization and user-query extraction utilities."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

SPEAKER_ALIASES = {
    "user": "user",
    "client": "user",
    "lawyer_client": "user",
    "customer": "user",
    "human": "user",
    "speaker_1": "user",
    "speaker1": "user",
    "person_1": "user",
    "person1": "user",
    "customer_1": "user",
    "пользователь": "user",
    "клиент": "user",
    "заявитель": "user",
    "истец": "user",
    "ответчик": "user",
    "человек": "user",
    "assistant": "assistant",
    "agent": "assistant",
    "bot": "assistant",
    "copilot": "assistant",
    "lawyer": "assistant",
    "counsel": "assistant",
    "attorney": "assistant",
    "operator": "assistant",
    "support": "assistant",
    "speaker_2": "assistant",
    "speaker2": "assistant",
    "person_2": "assistant",
    "person2": "assistant",
    "юрист": "assistant",
    "оператор": "assistant",
    "ассистент": "assistant",
    "бот": "assistant",
    "система": "system",
    "system": "system",
    "unknown": "unknown",
}

TIMESTAMP_RE = re.compile(
    r"^\s*(?:\[\d{1,2}:\d{2}(?::\d{2})?\]|\d{1,2}:\d{2}(?::\d{2})?)\s*"
)
SPEAKER_LINE_RE = re.compile(
    r"^\s*(?:\[\d{1,2}:\d{2}(?::\d{2})?\]\s*)?"
    r"(?P<speaker>[A-Za-zА-Яа-яЁё0-9_ .-]{2,40})\s*(?P<separator>[:>\-])\s*(?P<text>.+?)\s*$"
)
BRACKETED_CHUNK_LINE_RE = re.compile(
    r"^\s*\[(?P<speaker>[A-Za-zА-Яа-яЁё0-9_ .-]{2,40})\]\s*"
    r"\((?P<chunk>[^)]*)\)\s*:\s*(?P<text>.+?)\s*$"
)
INLINE_SPACE_RE = re.compile(r"[ \t]+")


@dataclass
class TranscriptTurn:
    speaker: str
    text: str
    raw_speaker: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TranscriptParseResult:
    turns: list[TranscriptTurn]
    latest_user_query: str
    cleaned_user_query: str
    transcript_text: str
    metadata: dict[str, Any] = field(default_factory=dict)


def normalize_whitespace(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = INLINE_SPACE_RE.sub(" ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_utterance(text: str) -> str:
    text = TIMESTAMP_RE.sub("", text)
    text = normalize_whitespace(text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text.strip(" -\n\t")


def canonicalize_speaker(speaker: str | None) -> str:
    if not speaker:
        return "unknown"
    normalized = normalize_whitespace(speaker).lower().replace(" ", "_")
    return SPEAKER_ALIASES.get(normalized, normalized)


def _is_explicit_speaker_label(raw_speaker: str | None) -> bool:
    if not raw_speaker:
        return False
    normalized = normalize_whitespace(raw_speaker).lower().replace(" ", "_")
    return normalized in SPEAKER_ALIASES


def _extract_text_field(payload: dict[str, Any]) -> str | None:
    for key in ("text", "content", "message", "utterance", "query", "input"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _extract_speaker_field(payload: dict[str, Any]) -> str | None:
    for key in ("speaker", "role", "author", "participant", "source"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _iter_container_items(payload: Any) -> Iterable[Any]:
    if isinstance(payload, dict):
        for key in ("messages", "turns", "dialogue", "conversation", "transcript", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        nested_text = _extract_text_field(payload)
        if nested_text:
            return [payload]
    if isinstance(payload, list):
        return payload
    return []


def _parse_dict_turn(payload: dict[str, Any]) -> TranscriptTurn | None:
    text = _extract_text_field(payload)
    if not text:
        return None
    speaker = _extract_speaker_field(payload)
    metadata = {
        key: value
        for key, value in payload.items()
        if key
        not in {
            "text",
            "content",
            "message",
            "utterance",
            "query",
            "input",
            "speaker",
            "role",
            "author",
            "participant",
            "source",
        }
    }
    return TranscriptTurn(
        speaker=canonicalize_speaker(speaker),
        raw_speaker=speaker,
        text=clean_utterance(text),
        metadata=metadata,
    )


def _parse_string_lines(text: str) -> list[TranscriptTurn]:
    turns: list[TranscriptTurn] = []
    current_turn: TranscriptTurn | None = None

    for raw_line in text.splitlines():
        line = normalize_whitespace(raw_line)
        if not line:
            continue

        match = SPEAKER_LINE_RE.match(line)
        if match:
            raw_speaker = match.group("speaker")
            separator = match.group("separator")
            if separator != "-" or _is_explicit_speaker_label(raw_speaker):
                if current_turn and current_turn.text:
                    turns.append(current_turn)
                current_turn = TranscriptTurn(
                    speaker=canonicalize_speaker(raw_speaker),
                    raw_speaker=raw_speaker,
                    text=clean_utterance(match.group("text")),
                )
                continue

        bracketed_match = BRACKETED_CHUNK_LINE_RE.match(line)
        if bracketed_match:
            if current_turn and current_turn.text:
                turns.append(current_turn)
            raw_speaker = bracketed_match.group("speaker")
            current_turn = TranscriptTurn(
                speaker=canonicalize_speaker(raw_speaker),
                raw_speaker=raw_speaker,
                text=clean_utterance(bracketed_match.group("text")),
                metadata={"chunk": bracketed_match.group("chunk")},
            )
            continue

        cleaned = clean_utterance(line)
        if current_turn:
            current_turn.text = normalize_whitespace(f"{current_turn.text}\n{cleaned}")
        else:
            current_turn = TranscriptTurn(
                speaker="user",
                raw_speaker=None,
                text=cleaned,
                metadata={"inferred_speaker": True},
            )

    if current_turn and current_turn.text:
        turns.append(current_turn)

    return turns


def normalize_transcript(raw_transcript: Any) -> list[TranscriptTurn]:
    if isinstance(raw_transcript, Path):
        return normalize_transcript(raw_transcript.read_text(encoding="utf-8"))

    if isinstance(raw_transcript, str):
        possible_path = Path(raw_transcript)
        if "\n" not in raw_transcript and possible_path.exists() and possible_path.is_file():
            return normalize_transcript(possible_path)
        return _parse_string_lines(raw_transcript)

    if isinstance(raw_transcript, dict):
        container_items = _iter_container_items(raw_transcript)
        if container_items:
            return normalize_transcript(list(container_items))
        turn = _parse_dict_turn(raw_transcript)
        return [turn] if turn else []

    if isinstance(raw_transcript, list):
        turns: list[TranscriptTurn] = []
        for item in raw_transcript:
            if isinstance(item, dict):
                turn = _parse_dict_turn(item)
                if turn:
                    turns.append(turn)
            elif isinstance(item, str):
                turns.extend(_parse_string_lines(item))
        return [turn for turn in turns if turn.text]

    raise TypeError("Unsupported transcript format. Expected str, list, or dict.")


def merge_adjacent_turns(turns: list[TranscriptTurn]) -> list[TranscriptTurn]:
    if not turns:
        return []

    merged = [turns[0]]
    for turn in turns[1:]:
        previous = merged[-1]
        if turn.speaker == previous.speaker:
            previous.text = normalize_whitespace(f"{previous.text}\n{turn.text}")
            previous.metadata.update(turn.metadata)
            continue
        merged.append(turn)
    return merged


def extract_latest_user_query(turns: list[TranscriptTurn]) -> str:
    for turn in reversed(turns):
        if turn.speaker == "user" and turn.text:
            return turn.text
    if turns:
        return turns[-1].text
    return ""


def render_transcript(turns: list[TranscriptTurn]) -> str:
    lines = []
    for turn in turns:
        speaker = turn.raw_speaker or turn.speaker
        lines.append(f"{speaker}: {turn.text}")
    return "\n".join(lines)


def parse_transcript(raw_transcript: Any) -> TranscriptParseResult:
    return parse_transcript_with_options(raw_transcript)


def parse_transcript_with_options(
    raw_transcript: Any,
    *,
    merge_turns: bool = True,
) -> TranscriptParseResult:
    turns = normalize_transcript(raw_transcript)
    if merge_turns:
        turns = merge_adjacent_turns(turns)
    latest_user_query = extract_latest_user_query(turns)
    cleaned_user_query = clean_utterance(latest_user_query)
    return TranscriptParseResult(
        turns=turns,
        latest_user_query=latest_user_query,
        cleaned_user_query=cleaned_user_query,
        transcript_text=render_transcript(turns),
        metadata={"turn_count": len(turns)},
    )
