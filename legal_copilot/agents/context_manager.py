"""Shared context manager for streaming dialogue coordination."""

from __future__ import annotations

from dataclasses import dataclass, field

from legal_copilot.ingestion.transcript_cleaner import (
    TranscriptTurn,
    clean_utterance,
    render_transcript,
)


def _turn_signature(turn: TranscriptTurn) -> tuple[str, str, str | None]:
    chunk = turn.metadata.get("chunk") if turn.metadata else None
    return (turn.speaker, clean_utterance(turn.text), chunk)


def _copy_turn(turn: TranscriptTurn) -> TranscriptTurn:
    return TranscriptTurn(
        speaker=turn.speaker,
        text=turn.text,
        raw_speaker=turn.raw_speaker,
        metadata=dict(turn.metadata),
    )


def _compute_overlap(existing: list[TranscriptTurn], incoming: list[TranscriptTurn]) -> int:
    max_size = min(len(existing), len(incoming))
    for size in range(max_size, 0, -1):
        existing_suffix = [_turn_signature(turn) for turn in existing[-size:]]
        incoming_prefix = [_turn_signature(turn) for turn in incoming[:size]]
        if existing_suffix == incoming_prefix:
            return size
    return 0


@dataclass
class ContextSnapshot:
    session_id: str
    turn_count: int
    recent_turns: list[TranscriptTurn]
    recent_transcript: str
    latest_user_turn: TranscriptTurn | None
    active_user_turn: TranscriptTurn | None
    active_user_span_text: str
    latest_assistant_turn: TranscriptTurn | None
    accumulated_user_facts: list[str]


@dataclass
class StreamingContextManager:
    session_id: str = "default"
    max_turns: int = 200
    recent_context_turns: int = 8
    turns: list[TranscriptTurn] = field(default_factory=list)
    latest_user_turn: TranscriptTurn | None = None
    latest_assistant_turn: TranscriptTurn | None = None
    active_user_turn: TranscriptTurn | None = None
    accumulated_user_facts: list[str] = field(default_factory=list)

    def update(self, incoming_turns: list[TranscriptTurn]) -> list[TranscriptTurn]:
        if not incoming_turns:
            return []

        copied_turns = [_copy_turn(turn) for turn in incoming_turns if turn.text]
        if not copied_turns:
            return []

        overlap = _compute_overlap(self.turns, copied_turns)
        appended_turns = copied_turns[overlap:]

        for turn in appended_turns:
            self._append_turn(turn)

        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns :]

        return appended_turns

    def _append_turn(self, turn: TranscriptTurn) -> None:
        previous_turn = self.turns[-1] if self.turns else None
        if previous_turn and _turn_signature(previous_turn) == _turn_signature(turn):
            return

        self.turns.append(turn)
        if turn.speaker == "user":
            self.latest_user_turn = turn
            self.active_user_turn = turn
            if len(turn.text) > 20:
                self.accumulated_user_facts.append(turn.text)
                self.accumulated_user_facts = self.accumulated_user_facts[-20:]
        elif turn.speaker == "assistant":
            self.latest_assistant_turn = turn

    def recent_turn_window(self, limit: int | None = None) -> list[TranscriptTurn]:
        limit = limit or self.recent_context_turns
        return self.turns[-limit:]

    def build_context_snapshot(self) -> ContextSnapshot:
        recent_turns = self.recent_turn_window()
        active_user_span_text = self._build_active_user_span_text()
        return ContextSnapshot(
            session_id=self.session_id,
            turn_count=len(self.turns),
            recent_turns=recent_turns,
            recent_transcript=render_transcript(recent_turns),
            latest_user_turn=self.latest_user_turn,
            active_user_turn=self.active_user_turn,
            active_user_span_text=active_user_span_text,
            latest_assistant_turn=self.latest_assistant_turn,
            accumulated_user_facts=list(self.accumulated_user_facts),
        )

    def _build_active_user_span_text(self) -> str:
        if not self.active_user_turn:
            return ""

        active_index = None
        active_signature = _turn_signature(self.active_user_turn)
        for index in range(len(self.turns) - 1, -1, -1):
            if _turn_signature(self.turns[index]) == active_signature:
                active_index = index
                break

        if active_index is None:
            return self.active_user_turn.text

        parts = [self.turns[active_index].text]
        for turn in self.turns[active_index + 1 :]:
            if turn.speaker in {"user", "assistant"}:
                break
            if turn.speaker == "unknown":
                parts.append(turn.text)

        return clean_utterance(" ".join(part for part in parts if part))
