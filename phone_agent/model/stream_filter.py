"""Streaming filter for extracting thinking and content deltas."""

from __future__ import annotations

from phone_agent.model.base import ContentDelta, StreamCallback, ThinkingDelta

_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"

_ACTION_STARTS = (
    "do(",
    "do (",
    "finish(",
    "finish (",
    "<answer>",
    "```json",
    "```\n{",
    "```\r\n{",
    '{"action"',
    '{"name"',
)


def _find_earliest_action_marker(text: str) -> tuple[int, str] | None:
    """Find the earliest occurrence of any action start marker."""
    earliest_pos = -1
    earliest_marker = ""
    for marker in _ACTION_STARTS:
        pos = text.find(marker)
        if pos != -1:
            if earliest_pos == -1 or pos < earliest_pos:
                earliest_pos = pos
                earliest_marker = marker
    if earliest_pos != -1:
        return earliest_pos, earliest_marker
    return None


def _find_partial_marker_length(text: str) -> int:
    """Find the length of the longest suffix matching a prefix of any marker."""
    max_check = min(len(text), 15)
    candidates = (_THINK_OPEN, _THINK_CLOSE, *_ACTION_STARTS)
    for length in range(max_check, 0, -1):
        suffix = text[-length:]
        if any(marker.startswith(suffix) for marker in candidates):
            return length
    return 0


class StreamingThinkingDetector:
    """Stream filter that separates thinking from action content.

    Supports:
    1. Explicit <think>...</think> tags.
    2. Implicit natural-language reasoning preceding do(...) / finish(...) / <answer> / JSON.
    """

    def __init__(self, on_event: StreamCallback | None = None) -> None:
        self._on_event = on_event
        self._in_explicit_think = False
        self._in_action = False
        self._buffer = ""

    def feed(self, delta: str) -> None:
        """Feed a text chunk and emit ThinkingDelta / ContentDelta events."""
        if self._on_event is None or not delta:
            return

        self._buffer += delta

        while self._buffer:
            if self._in_action:
                self._on_event(ContentDelta(self._buffer))
                self._buffer = ""
                break

            if self._in_explicit_think:
                if _THINK_CLOSE in self._buffer:
                    think_body, _, self._buffer = self._buffer.partition(_THINK_CLOSE)
                    if think_body:
                        self._on_event(ThinkingDelta(think_body))
                    self._in_explicit_think = False
                    continue

                # Buffer might end with a prefix of </think>
                partial_len = 0
                max_check = min(len(self._buffer), len(_THINK_CLOSE) - 1)
                for length in range(max_check, 0, -1):
                    if _THINK_CLOSE.startswith(self._buffer[-length:]):
                        partial_len = length
                        break

                if partial_len > 0:
                    emit_text = self._buffer[:-partial_len]
                    self._buffer = self._buffer[-partial_len:]
                    if emit_text:
                        self._on_event(ThinkingDelta(emit_text))
                    break

                self._on_event(ThinkingDelta(self._buffer))
                self._buffer = ""
                break

            # We are outside explicit think and not yet in action
            if _THINK_OPEN in self._buffer:
                prefix, _, self._buffer = self._buffer.partition(_THINK_OPEN)
                if prefix:
                    self._on_event(ThinkingDelta(prefix))
                self._in_explicit_think = True
                continue

            # Check for action start markers
            marker_match = _find_earliest_action_marker(self._buffer)
            if marker_match is not None:
                pos, _ = marker_match
                thinking_prefix = self._buffer[:pos]
                if thinking_prefix:
                    self._on_event(ThinkingDelta(thinking_prefix))
                self._in_action = True
                self._buffer = self._buffer[pos:]
                if self._buffer:
                    self._on_event(ContentDelta(self._buffer))
                    self._buffer = ""
                break

            # Check if buffer ends with a prefix of <think> or an action marker
            partial_len = _find_partial_marker_length(self._buffer)
            if partial_len > 0:
                emit_text = self._buffer[:-partial_len]
                self._buffer = self._buffer[-partial_len:]
                if emit_text:
                    self._on_event(ThinkingDelta(emit_text))
                break

            # Pure thinking text
            self._on_event(ThinkingDelta(self._buffer))
            self._buffer = ""
            break

    def flush(self) -> None:
        """Flush remaining buffered text."""
        if not self._buffer or self._on_event is None:
            return

        if self._in_action:
            self._on_event(ContentDelta(self._buffer))
        else:
            self._on_event(ThinkingDelta(self._buffer))
        self._buffer = ""
