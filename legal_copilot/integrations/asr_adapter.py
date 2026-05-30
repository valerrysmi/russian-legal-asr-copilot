"""Adapters for integrating external ASR transcripts with LegalCopilot.

This module is primarily intended for the `alena` legal ASR service.
It converts speaker-labeled ASR segments into normalized utterances and
streaming transcript chunks suitable for `legal_copilot`.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


def _normalize_speaker_label(label: str | None) -> str:
    normalized = (label or "").strip().upper()
    if normalized == "LAWYER":
        return "Lawyer"
    if normalized == "CLIENT":
        return "Client"
    return "Unknown"


def _normalize_text(text: str | None) -> str:
    return " ".join((text or "").split()).strip()


@dataclass(slots=True)
class ASRSegment:
    session_id: str
    segment_id: int
    start_time: float
    end_time: float
    speaker: str
    speaker_confidence: float | None
    speaker_similarity: float | None
    text: str
    asr_confidence: float | None = None
    source: str = "asr"
    finalized: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ASRSegmentBatch:
    session_id: str
    segments: list[ASRSegment]


@dataclass(slots=True)
class NormalizedUtterance:
    session_id: str
    utterance_id: str
    speaker: str
    start_time: float
    end_time: float
    text: str
    source_segment_ids: list[int]
    speaker_confidence: float | None = None
    low_confidence: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TranscriptChunk:
    session_id: str
    chunk_id: str
    chunk_start_time: float
    chunk_end_time: float
    utterances: list[NormalizedUtterance]
    is_final: bool = False


def load_alena_transcript(path: str | Path) -> ASRSegmentBatch:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    session_id = str(payload.get("session_id") or "unknown")
    segments_payload = payload.get("segments") or []
    segments: list[ASRSegment] = []
    for index, item in enumerate(segments_payload, start=1):
        segments.append(
            ASRSegment(
                session_id=session_id,
                segment_id=int(item.get("segment_id") or index),
                start_time=float(item.get("start_time") or 0.0),
                end_time=float(item.get("end_time") or 0.0),
                speaker=str(item.get("speaker") or "UNKNOWN"),
                speaker_confidence=_to_optional_float(item.get("speaker_confidence")),
                speaker_similarity=_to_optional_float(item.get("speaker_similarity")),
                text=_normalize_text(item.get("text")),
                asr_confidence=_to_optional_float(item.get("asr_confidence")),
                source=str(item.get("source") or "asr"),
                finalized=bool(item.get("finalized", True)),
                metadata=dict(item.get("metadata") or {}),
            )
        )
    return ASRSegmentBatch(session_id=session_id, segments=segments)


def _to_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def merge_asr_segments_to_utterances(
    batch: ASRSegmentBatch,
    *,
    max_pause_sec: float = 1.0,
    low_confidence_threshold: float = 0.45,
) -> list[NormalizedUtterance]:
    utterances: list[NormalizedUtterance] = []
    current: NormalizedUtterance | None = None

    for segment in batch.segments:
        text = _normalize_text(segment.text)
        if not text:
            continue

        speaker = _normalize_speaker_label(segment.speaker)
        low_confidence = (
            segment.speaker_confidence is not None
            and segment.speaker_confidence < low_confidence_threshold
        )

        if current is None:
            current = NormalizedUtterance(
                session_id=batch.session_id,
                utterance_id=f"utt_{len(utterances) + 1:04d}",
                speaker=speaker,
                start_time=segment.start_time,
                end_time=segment.end_time,
                text=text,
                source_segment_ids=[segment.segment_id],
                speaker_confidence=segment.speaker_confidence,
                low_confidence=low_confidence,
                metadata={"source": "alena_adapter"},
            )
            continue

        same_speaker = current.speaker == speaker
        small_pause = max(0.0, segment.start_time - current.end_time) <= max_pause_sec

        if same_speaker and small_pause:
            current.end_time = segment.end_time
            current.text = _normalize_text(f"{current.text} {text}")
            current.source_segment_ids.append(segment.segment_id)
            confidences = [
                value
                for value in (current.speaker_confidence, segment.speaker_confidence)
                if value is not None
            ]
            current.speaker_confidence = (
                sum(confidences) / len(confidences) if confidences else None
            )
            current.low_confidence = current.low_confidence or low_confidence
            continue

        utterances.append(current)
        current = NormalizedUtterance(
            session_id=batch.session_id,
            utterance_id=f"utt_{len(utterances) + 1:04d}",
            speaker=speaker,
            start_time=segment.start_time,
            end_time=segment.end_time,
            text=text,
            source_segment_ids=[segment.segment_id],
            speaker_confidence=segment.speaker_confidence,
            low_confidence=low_confidence,
            metadata={"source": "alena_adapter"},
        )

    if current is not None:
        utterances.append(current)

    return utterances


def build_transcript_chunks_from_utterances(
    utterances: list[NormalizedUtterance],
    *,
    window_size: int = 4,
    stride: int = 3,
) -> list[TranscriptChunk]:
    if not utterances:
        return []

    if len(utterances) <= window_size:
        return [
            TranscriptChunk(
                session_id=utterances[0].session_id,
                chunk_id="chunk_0001",
                chunk_start_time=utterances[0].start_time,
                chunk_end_time=utterances[-1].end_time,
                utterances=utterances,
                is_final=True,
            )
        ]

    chunks: list[TranscriptChunk] = []
    start = 0
    chunk_index = 1
    while start < len(utterances):
        chunk_utterances = utterances[start : start + window_size]
        if not chunk_utterances:
            break
        chunks.append(
            TranscriptChunk(
                session_id=utterances[0].session_id,
                chunk_id=f"chunk_{chunk_index:04d}",
                chunk_start_time=chunk_utterances[0].start_time,
                chunk_end_time=chunk_utterances[-1].end_time,
                utterances=chunk_utterances,
                is_final=start + window_size >= len(utterances),
            )
        )
        if start + window_size >= len(utterances):
            break
        start += stride
        chunk_index += 1

    if chunks and chunks[-1].utterances != utterances[-window_size:]:
        tail = utterances[-window_size:]
        chunks.append(
            TranscriptChunk(
                session_id=utterances[0].session_id,
                chunk_id=f"chunk_{len(chunks) + 1:04d}",
                chunk_start_time=tail[0].start_time,
                chunk_end_time=tail[-1].end_time,
                utterances=tail,
                is_final=True,
            )
        )

    return chunks


def render_utterances_as_transcript(utterances: list[NormalizedUtterance]) -> str:
    lines: list[str] = []
    for utterance in utterances:
        lines.append(f"{utterance.speaker}: {utterance.text}")
    return "\n".join(lines)


def render_chunk_as_transcript(chunk: TranscriptChunk) -> str:
    return render_utterances_as_transcript(chunk.utterances)


def convert_alena_transcript_to_utterances(
    path: str | Path,
    *,
    max_pause_sec: float = 1.0,
    low_confidence_threshold: float = 0.45,
) -> list[NormalizedUtterance]:
    batch = load_alena_transcript(path)
    return merge_asr_segments_to_utterances(
        batch,
        max_pause_sec=max_pause_sec,
        low_confidence_threshold=low_confidence_threshold,
    )


def convert_alena_transcript_to_chunks(
    path: str | Path,
    *,
    max_pause_sec: float = 1.0,
    low_confidence_threshold: float = 0.45,
    window_size: int = 4,
    stride: int = 3,
) -> list[TranscriptChunk]:
    utterances = convert_alena_transcript_to_utterances(
        path,
        max_pause_sec=max_pause_sec,
        low_confidence_threshold=low_confidence_threshold,
    )
    return build_transcript_chunks_from_utterances(
        utterances,
        window_size=window_size,
        stride=stride,
    )


def export_alena_transcript_as_text(
    input_path: str | Path,
    output_path: str | Path,
    *,
    max_pause_sec: float = 1.0,
    low_confidence_threshold: float = 0.45,
) -> Path:
    utterances = convert_alena_transcript_to_utterances(
        input_path,
        max_pause_sec=max_pause_sec,
        low_confidence_threshold=low_confidence_threshold,
    )
    output = Path(output_path)
    output.write_text(render_utterances_as_transcript(utterances), encoding="utf-8")
    return output


def asdict_chunk(chunk: TranscriptChunk) -> dict[str, Any]:
    return asdict(chunk)

