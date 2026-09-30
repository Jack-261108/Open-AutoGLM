"""Anthropic Messages transport adapter."""

from __future__ import annotations

import copy
import re
import time
from dataclasses import dataclass, field
from typing import Any

from phone_agent.model.base import (
    ContentDelta,
    ModelConfigurationError,
    ModelConnectionError,
    ModelRequestError,
    ModelResponseError,
    RawModelOutput,
    RawToolCall,
    StreamCallback,
    ThinkingDelta,
    ToolCallDelta,
    UnsupportedToolsError,
    get_error_body,
    get_error_status_code,
    is_unsupported_tools_error_response,
)
from phone_agent.model.client import ModelConfig
from phone_agent.model.tool_schema import decode_json_object, get_tool_schemas

_DATA_IMAGE_RE = re.compile(
    r"\Adata:(?P<media_type>image/[a-zA-Z0-9.+-]+);base64,(?P<data>.+)\Z",
    re.DOTALL,
)


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _convert_content(content: Any) -> str | list[dict[str, Any]]:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        raise ModelRequestError("Anthropic message content must be a string or list")

    blocks: list[dict[str, Any]] = []
    for item in content:
        if not isinstance(item, dict):
            raise ModelRequestError("Anthropic message content blocks must be objects")
        block_type = item.get("type")
        if block_type == "text":
            text = item.get("text")
            if not isinstance(text, str):
                raise ModelRequestError("Anthropic text blocks require string text")
            blocks.append({"type": "text", "text": text})
            continue
        if block_type == "image_url":
            image_url = item.get("image_url")
            url = image_url.get("url") if isinstance(image_url, dict) else None
            if not isinstance(url, str):
                raise ModelRequestError("Anthropic image_url block requires a URL")
            match = _DATA_IMAGE_RE.fullmatch(url)
            if not match:
                raise ModelRequestError(
                    "Anthropic images must use a base64 image data URI"
                )
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": match.group("media_type"),
                        "data": match.group("data"),
                    },
                }
            )
            continue
        raise ModelRequestError(
            f"Unsupported Anthropic message block type: {block_type!r}"
        )
    return blocks


def _system_text(content: Any) -> str:
    converted = _convert_content(content)
    if isinstance(converted, str):
        return converted
    texts: list[str] = []
    for block in converted:
        if block["type"] != "text":
            raise ModelRequestError("Anthropic system messages cannot contain images")
        texts.append(block["text"])
    return "".join(texts)


def _convert_messages(
    messages: list[dict[str, Any]],
) -> tuple[str | None, list[dict[str, Any]]]:
    systems: list[str] = []
    converted: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            raise ModelRequestError("Anthropic messages must be objects")
        role = message.get("role")
        if role == "system":
            systems.append(_system_text(message.get("content", "")))
            continue
        if role not in {"user", "assistant"}:
            raise ModelRequestError(f"Unsupported Anthropic message role: {role!r}")
        converted.append(
            {"role": role, "content": _convert_content(message.get("content", ""))}
        )
    system = "\n".join(systems) if systems else None
    return system, converted


def _thinking_enabled(extra_body: dict[str, Any]) -> bool:
    thinking = extra_body.get("thinking")
    return isinstance(thinking, dict) and thinking.get("type") == "enabled"


@dataclass
class _BlockState:
    kind: str
    text_parts: list[str] = field(default_factory=list)
    name: str | None = None
    initial_input: dict[str, Any] | None = None
    partial_json: list[str] = field(default_factory=list)
    saw_partial_json: bool = False
    stopped: bool = False


class AnthropicAdapter:
    """Adapter for the Anthropic Messages protocol."""

    def __init__(
        self,
        config: ModelConfig,
        verbose: bool = True,
        *,
        client: Any | None = None,
    ):
        if config.provider != "anthropic":
            raise ModelConfigurationError(
                "AnthropicAdapter requires provider='anthropic'"
            )
        self.config = config
        self.verbose = verbose
        self._closed = False
        if client is None:
            try:
                from anthropic import Anthropic
            except ImportError:
                raise ModelConfigurationError(
                    "anthropic>=0.117.1 is required for the Anthropic adapter"
                ) from None

            self.client = Anthropic(
                api_key=config.api_key,
                base_url=config.base_url,
                timeout=config.timeout,
                default_headers=config.extra_headers,
            )
        else:
            self.client = client

    def _request_kwargs(
        self,
        messages: list[dict[str, Any]],
        *,
        use_tools: bool,
        stream: bool,
        max_tokens: int | None = None,
        connection_check: bool = False,
    ) -> dict[str, Any]:
        system, converted_messages = _convert_messages(messages)
        extra_body = copy.deepcopy(self.config.extra_body) if self.config.extra_body else {}
        if connection_check:
            extra_body.pop("thinking", None)
        kwargs: dict[str, Any] = {
            "model": self.config.model_name,
            "messages": converted_messages,
            "max_tokens": self.config.max_tokens if max_tokens is None else max_tokens,
            "stream": stream,
        }
        # Anthropic rejects temperature while extended thinking is enabled.
        if not _thinking_enabled(extra_body):
            kwargs["temperature"] = (
                0.0 if self.config.temperature is None else self.config.temperature
            )
        if system is not None:
            kwargs["system"] = system
        if self.config.top_p is not None:
            kwargs["top_p"] = self.config.top_p
        if extra_body:
            kwargs["extra_body"] = extra_body
        if self.config.extra_headers:
            kwargs["extra_headers"] = self.config.extra_headers
        if use_tools:
            kwargs["tools"] = get_tool_schemas()
        return kwargs

    @staticmethod
    def _normalize_error(
        error: BaseException,
        *,
        zero_output: bool,
        connection_check: bool = False,
    ) -> BaseException:
        if isinstance(
            error,
            (
                ModelConfigurationError,
                ModelConnectionError,
                ModelRequestError,
                ModelResponseError,
            ),
        ):
            return error
        status_code = get_error_status_code(error)
        body = get_error_body(error)
        if is_unsupported_tools_error_response(
            status_code, body, zero_output=zero_output
        ):
            return UnsupportedToolsError("Anthropic service does not support tools")
        if connection_check:
            suffix = f" (HTTP {status_code})" if status_code is not None else ""
            return ModelConnectionError(f"Anthropic connection check failed{suffix}")
        if status_code is not None:
            return ModelRequestError(f"Anthropic request failed (HTTP {status_code})")
        error_name = type(error).__name__.lower()
        if "connection" in error_name or "timeout" in error_name:
            return ModelConnectionError("Anthropic service is unreachable")
        return ModelRequestError("Anthropic request failed")

    @staticmethod
    def _block_index(event: Any) -> int:
        index = _get(event, "index")
        if type(index) is not int or index < 0:
            raise ModelResponseError(
                "Anthropic content block index must be a non-negative integer"
            )
        return index

    def request(
        self,
        messages: list[dict[str, Any]],
        *,
        use_tools: bool,
        on_event: StreamCallback | None = None,
    ) -> RawModelOutput:
        if self._closed:
            raise ModelRequestError("AnthropicAdapter is closed")

        started = time.monotonic()
        time_to_first_token: float | None = None
        time_to_thinking_end: float | None = None
        thinking_parts: list[str] = []
        final_parts: list[str] = []
        raw_parts: list[str] = []
        blocks: dict[int, _BlockState] = {}
        tool_calls: dict[int, RawToolCall] = {}
        emitted_output = False
        saw_message_stop = False
        safe_error: BaseException | None = None

        def mark_output(*, ends_thinking: bool = False) -> None:
            nonlocal emitted_output, time_to_first_token, time_to_thinking_end
            emitted_output = True
            now = time.monotonic() - started
            if time_to_first_token is None:
                time_to_first_token = now
            if ends_thinking and thinking_parts and time_to_thinking_end is None:
                time_to_thinking_end = now

        events: Any = None
        try:
            events = self.client.messages.create(
                **self._request_kwargs(
                    messages,
                    use_tools=use_tools,
                    stream=True,
                )
            )
            for event in events:
                event_type = _get(event, "type")
                if saw_message_stop:
                    raise ModelResponseError(
                        "Anthropic stream emitted an event after message_stop"
                    )
                if event_type == "content_block_start":
                    index = self._block_index(event)
                    if index in blocks:
                        raise ModelResponseError(
                            f"Duplicate Anthropic content block index: {index}"
                        )
                    content_block = _get(event, "content_block")
                    block_type = _get(content_block, "type")
                    if block_type == "text":
                        state = _BlockState(kind="text")
                        initial = _get(content_block, "text", "")
                        if not isinstance(initial, str):
                            raise ModelResponseError(
                                "Anthropic initial text must be a string"
                            )
                        if initial:
                            state.text_parts.append(initial)
                            final_parts.append(initial)
                            raw_parts.append(initial)
                            mark_output(ends_thinking=True)
                            if on_event is not None:
                                on_event(ContentDelta(initial))
                    elif block_type == "thinking":
                        state = _BlockState(kind="thinking")
                        initial = _get(content_block, "thinking", "")
                        if not isinstance(initial, str):
                            raise ModelResponseError(
                                "Anthropic initial thinking must be a string"
                            )
                        if initial:
                            state.text_parts.append(initial)
                            thinking_parts.append(initial)
                            raw_parts.append(initial)
                            mark_output()
                            if on_event is not None:
                                on_event(ThinkingDelta(initial))
                    elif block_type == "redacted_thinking":
                        state = _BlockState(kind="redacted_thinking")
                    elif block_type == "tool_use":
                        name = _get(content_block, "name")
                        initial_input = _get(content_block, "input")
                        if not isinstance(name, str) or not name:
                            raise ModelResponseError(
                                "Anthropic tool_use requires a string name"
                            )
                        if not isinstance(initial_input, dict):
                            raise ModelResponseError(
                                "Anthropic tool_use initial input must be an object"
                            )
                        state = _BlockState(
                            kind="tool_use",
                            name=name,
                            initial_input=initial_input,
                        )
                        mark_output(ends_thinking=True)
                    else:
                        raise ModelResponseError(
                            f"Unsupported Anthropic content block type: {block_type!r}"
                        )
                    blocks[index] = state
                    continue

                if event_type == "content_block_delta":
                    index = self._block_index(event)
                    state = blocks.get(index)
                    if state is None or state.stopped:
                        raise ModelResponseError(
                            f"Anthropic delta references inactive block: {index}"
                        )
                    delta = _get(event, "delta")
                    delta_type = _get(delta, "type")
                    if delta_type == "text_delta" and state.kind == "text":
                        text = _get(delta, "text")
                        if not isinstance(text, str):
                            raise ModelResponseError(
                                "Anthropic text_delta text must be a string"
                            )
                        state.text_parts.append(text)
                        final_parts.append(text)
                        raw_parts.append(text)
                        if text:
                            mark_output(ends_thinking=True)
                            if on_event is not None:
                                on_event(ContentDelta(text))
                    elif delta_type == "thinking_delta" and state.kind == "thinking":
                        thinking = _get(delta, "thinking")
                        if not isinstance(thinking, str):
                            raise ModelResponseError(
                                "Anthropic thinking_delta must be a string"
                            )
                        state.text_parts.append(thinking)
                        thinking_parts.append(thinking)
                        raw_parts.append(thinking)
                        if thinking:
                            mark_output()
                            if on_event is not None:
                                on_event(ThinkingDelta(thinking))
                    elif delta_type == "signature_delta" and state.kind == "thinking":
                        signature = _get(delta, "signature")
                        if not isinstance(signature, str):
                            raise ModelResponseError(
                                "Anthropic signature_delta must contain a string"
                            )
                    elif delta_type == "input_json_delta" and state.kind == "tool_use":
                        partial = _get(delta, "partial_json")
                        if not isinstance(partial, str):
                            raise ModelResponseError(
                                "Anthropic input_json_delta must be a string"
                            )
                        state.saw_partial_json = True
                        state.partial_json.append(partial)
                        if partial:
                            mark_output(ends_thinking=True)
                            if on_event is not None:
                                on_event(
                                    ToolCallDelta(
                                        index=index,
                                        name=state.name,
                                        arguments_delta=partial,
                                    )
                                )
                    else:
                        raise ModelResponseError(
                            "Anthropic delta type does not match its content block"
                        )
                    continue

                if event_type == "content_block_stop":
                    index = self._block_index(event)
                    state = blocks.get(index)
                    if state is None or state.stopped:
                        raise ModelResponseError(
                            f"Anthropic stop references inactive block: {index}"
                        )
                    state.stopped = True
                    if state.kind == "tool_use":
                        initial_input = state.initial_input or {}
                        if state.saw_partial_json:
                            if initial_input:
                                raise ModelResponseError(
                                    "Anthropic tool input cannot mix initial input and partial JSON"
                                )
                            arguments = decode_json_object(
                                "".join(state.partial_json),
                                context="Anthropic tool input",
                            )
                        else:
                            arguments = initial_input
                        tool_calls[index] = RawToolCall(
                            name=state.name or "",
                            arguments=arguments,
                        )
                    continue

                if event_type == "message_stop":
                    saw_message_stop = True
                    continue
                if event_type in {"message_start", "message_delta", "ping"}:
                    continue
                raise ModelResponseError(
                    f"Unsupported Anthropic stream event: {event_type!r}"
                )
        except Exception as exc:
            normalized = self._normalize_error(exc, zero_output=not emitted_output)
            if normalized is exc:
                raise
            safe_error = normalized
        finally:
            # Anthropic MessageStream.__stream__ has no finally clause, so an
            # exception raised inside the for loop (e.g. our ModelResponseError
            # for "event after message_stop") leaves the underlying httpx
            # response open until GC. Close best-effort; swallow close errors so
            # the original safe_error path is not replaced. Test fakes return a
            # plain iterable without close(), which we skip via getattr.
            if events is not None:
                close = getattr(events, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:
                        pass

        if safe_error is not None:
            raise safe_error from None
        if not saw_message_stop:
            raise ModelResponseError(
                "Anthropic stream ended without exactly one message_stop"
            )

        incomplete = [index for index, state in blocks.items() if not state.stopped]
        if incomplete:
            raise ModelResponseError(
                f"Anthropic stream ended with incomplete blocks: {sorted(incomplete)!r}"
            )

        total_time = time.monotonic() - started
        if thinking_parts and time_to_thinking_end is None:
            time_to_thinking_end = total_time
        return RawModelOutput(
            thinking="".join(thinking_parts),
            final_text="".join(final_parts),
            tool_calls=[tool_calls[index] for index in sorted(tool_calls)],
            raw_content="".join(raw_parts),
            time_to_first_token=time_to_first_token,
            time_to_thinking_end=time_to_thinking_end,
            total_time=total_time,
        )

    def check_connection(self) -> None:
        if self._closed:
            raise ModelConnectionError("AnthropicAdapter is closed")
        safe_error: BaseException | None = None
        try:
            self.client.messages.create(
                **self._request_kwargs(
                    [{"role": "user", "content": "ping"}],
                    use_tools=False,
                    stream=False,
                    max_tokens=1,
                    connection_check=True,
                )
            )
        except Exception as exc:
            normalized = self._normalize_error(
                exc,
                zero_output=True,
                connection_check=True,
            )
            if normalized is exc:
                raise
            safe_error = normalized

        if safe_error is not None:
            raise safe_error from None

    def close(self) -> None:
        if self._closed:
            return
        self.client.close()
        self._closed = True
