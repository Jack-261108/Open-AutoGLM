"""OpenAI-compatible transport adapter."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from phone_agent.model.base import (
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
from phone_agent.model.stream_filter import StreamingThinkingDetector
from phone_agent.model.tool_schema import get_tool_schemas


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _openai_tools() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"],
            },
        }
        for tool in get_tool_schemas()
    ]


@dataclass
class _ToolCallBuffer:
    name_parts: list[str] = field(default_factory=list)
    argument_parts: list[str] = field(default_factory=list)
    argument_object: dict[str, Any] | None = None

    def add(self, name: Any, arguments: Any) -> bool:
        emitted = False
        if name is not None:
            if not isinstance(name, str):
                raise ModelResponseError("OpenAI tool name fragments must be strings")
            self.name_parts.append(name)
            emitted = emitted or bool(name)
        if arguments is not None:
            if isinstance(arguments, str):
                if self.argument_object is not None:
                    raise ModelResponseError(
                        "OpenAI tool arguments cannot mix object and string fragments"
                    )
                self.argument_parts.append(arguments)
                emitted = emitted or bool(arguments)
            elif isinstance(arguments, dict):
                if self.argument_parts or self.argument_object is not None:
                    raise ModelResponseError(
                        "OpenAI tool arguments object must arrive exactly once"
                    )
                self.argument_object = arguments
                emitted = True
            else:
                raise ModelResponseError(
                    "OpenAI tool arguments must be a string or object"
                )
        return emitted

    def build(self) -> RawToolCall:
        name = "".join(self.name_parts)
        if not name:
            raise ModelResponseError("OpenAI tool call is missing a function name")
        arguments: dict[str, Any] | str
        if self.argument_object is not None:
            arguments = self.argument_object
        else:
            arguments = "".join(self.argument_parts)
        return RawToolCall(name=name, arguments=arguments)


class OpenAICompatibleAdapter:
    """Adapter for OpenAI Chat Completions compatible services."""

    def __init__(
        self,
        config: ModelConfig,
        verbose: bool = True,
        *,
        client: Any | None = None,
    ):
        if config.provider != "openai":
            raise ModelConfigurationError(
                "OpenAICompatibleAdapter requires provider='openai'"
            )
        self.config = config
        self.verbose = verbose
        self._closed = False
        if client is None:
            try:
                from openai import OpenAI
            except ImportError:
                raise ModelConfigurationError(
                    "openai>=2.9.0 is required for the OpenAI-compatible adapter"
                ) from None

            self.client = OpenAI(
                base_url=config.base_url,
                api_key=config.api_key or "EMPTY",
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
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.config.model_name,
            "messages": messages,
            "max_tokens": self.config.max_tokens if max_tokens is None else max_tokens,
            "temperature": (
                0.0 if self.config.temperature is None else self.config.temperature
            ),
            "top_p": 0.85 if self.config.top_p is None else self.config.top_p,
            "frequency_penalty": (
                0.2
                if self.config.frequency_penalty is None
                else self.config.frequency_penalty
            ),
            "stream": stream,
        }
        if self.config.extra_body:
            kwargs["extra_body"] = self.config.extra_body
        if self.config.extra_headers:
            kwargs["extra_headers"] = self.config.extra_headers
        if use_tools:
            kwargs["tools"] = _openai_tools()
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
            return UnsupportedToolsError(
                "OpenAI-compatible service does not support tools"
            )
        if connection_check:
            suffix = f" (HTTP {status_code})" if status_code is not None else ""
            return ModelConnectionError(
                f"OpenAI-compatible connection check failed{suffix}"
            )
        if status_code is not None:
            return ModelRequestError(
                f"OpenAI-compatible request failed (HTTP {status_code})"
            )
        error_name = type(error).__name__.lower()
        if "connection" in error_name or "timeout" in error_name:
            return ModelConnectionError("OpenAI-compatible service is unreachable")
        return ModelRequestError("OpenAI-compatible request failed")

    def request(
        self,
        messages: list[dict[str, Any]],
        *,
        use_tools: bool,
        on_event: StreamCallback | None = None,
    ) -> RawModelOutput:
        if self._closed:
            raise ModelRequestError("OpenAICompatibleAdapter is closed")

        started = time.monotonic()
        time_to_first_token: float | None = None
        time_to_thinking_end: float | None = None
        thinking_parts: list[str] = []
        final_parts: list[str] = []
        raw_parts: list[str] = []
        tool_buffers: dict[int, _ToolCallBuffer] = {}
        detector = StreamingThinkingDetector(on_event)
        emitted_output = False
        safe_error: BaseException | None = None

        try:
            stream = self.client.chat.completions.create(
                **self._request_kwargs(
                    messages,
                    use_tools=use_tools,
                    stream=True,
                )
            )
            for chunk in stream:
                choices = _get(chunk, "choices", [])
                if not choices:
                    continue
                delta = _get(choices[0], "delta")
                if delta is None:
                    continue

                reasoning = _get(delta, "reasoning_content")
                if reasoning is not None:
                    if not isinstance(reasoning, str):
                        raise ModelResponseError(
                            "OpenAI reasoning_content must be a string"
                        )
                    if reasoning:
                        thinking_parts.append(reasoning)
                        raw_parts.append(reasoning)
                        emitted_output = True
                        if on_event is not None:
                            on_event(ThinkingDelta(reasoning))

                content = _get(delta, "content")
                if content is not None:
                    if not isinstance(content, str):
                        raise ModelResponseError("OpenAI content must be a string")
                    if content:
                        if thinking_parts and time_to_thinking_end is None:
                            time_to_thinking_end = time.monotonic() - started
                        final_parts.append(content)
                        raw_parts.append(content)
                        emitted_output = True
                        detector.feed(content)

                tool_deltas = _get(delta, "tool_calls", []) or []
                if tool_deltas:
                    if thinking_parts and time_to_thinking_end is None:
                        time_to_thinking_end = time.monotonic() - started
                    emitted_output = True
                for position, tool_delta in enumerate(tool_deltas):
                    index = _get(tool_delta, "index", position)
                    if type(index) is not int or index < 0:
                        raise ModelResponseError(
                            "OpenAI tool call index must be a non-negative integer"
                        )
                    function = _get(tool_delta, "function")
                    if function is None:
                        continue
                    buffer = tool_buffers.setdefault(index, _ToolCallBuffer())
                    tool_name = _get(function, "name")
                    tool_args = _get(function, "arguments")
                    tool_emitted = buffer.add(tool_name, tool_args)
                    if tool_emitted:
                        if thinking_parts and time_to_thinking_end is None:
                            time_to_thinking_end = time.monotonic() - started
                        emitted_output = True
                        if on_event is not None:
                            arg_delta = tool_args if isinstance(tool_args, str) else ""
                            on_event(
                                ToolCallDelta(
                                    index=index,
                                    name=tool_name,
                                    arguments_delta=arg_delta,
                                )
                            )

                if emitted_output and time_to_first_token is None:
                    time_to_first_token = time.monotonic() - started
            detector.flush()
        except Exception as exc:
            normalized = self._normalize_error(exc, zero_output=not emitted_output)
            if normalized is exc:
                raise
            safe_error = normalized

        if safe_error is not None:
            raise safe_error from None

        total_time = time.monotonic() - started
        if thinking_parts and time_to_thinking_end is None:
            time_to_thinking_end = total_time
        return RawModelOutput(
            thinking="".join(thinking_parts),
            final_text="".join(final_parts),
            tool_calls=[tool_buffers[index].build() for index in sorted(tool_buffers)],
            raw_content="".join(raw_parts),
            time_to_first_token=time_to_first_token,
            time_to_thinking_end=time_to_thinking_end,
            total_time=total_time,
        )

    def check_connection(self) -> None:
        if self._closed:
            raise ModelConnectionError("OpenAICompatibleAdapter is closed")
        safe_error: BaseException | None = None
        try:
            self.client.chat.completions.create(
                **self._request_kwargs(
                    [{"role": "user", "content": "ping"}],
                    use_tools=False,
                    stream=False,
                    max_tokens=1,
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
