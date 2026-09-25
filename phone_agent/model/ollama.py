"""Ollama native HTTP transport adapter."""

from __future__ import annotations

import copy
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from phone_agent.model.base import (
    ModelConfigurationError,
    ModelConnectionError,
    ModelRequestError,
    ModelResponseError,
    RawModelOutput,
    RawToolCall,
)
from phone_agent.model.client import ModelConfig
from phone_agent.model.tool_schema import decode_json_object, get_tool_schemas

_DATA_IMAGE_RE = re.compile(
    r"\Adata:image/[a-zA-Z0-9.+-]+;base64,(?P<data>.+)\Z",
    re.DOTALL,
)


def _ollama_tools() -> list[dict[str, Any]]:
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


def _convert_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            raise ModelRequestError("Ollama messages must be objects")
        role = message.get("role")
        if not isinstance(role, str):
            raise ModelRequestError("Ollama message role must be a string")
        content = message.get("content", "")
        images: list[str] = []
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    raise ModelRequestError(
                        "Ollama message content blocks must be objects"
                    )
                block_type = item.get("type")
                if block_type == "text":
                    block_text = item.get("text")
                    if not isinstance(block_text, str):
                        raise ModelRequestError(
                            "Ollama text blocks require string text"
                        )
                    text_parts.append(block_text)
                    continue
                if block_type == "image_url":
                    image_url = item.get("image_url")
                    url = image_url.get("url") if isinstance(image_url, dict) else None
                    if not isinstance(url, str):
                        raise ModelRequestError(
                            "Ollama image_url block requires a URL"
                        )
                    match = _DATA_IMAGE_RE.fullmatch(url)
                    if not match:
                        raise ModelRequestError(
                            "Ollama images must use a base64 image data URI"
                        )
                    images.append(match.group("data"))
                    continue
                raise ModelRequestError(
                    f"Unsupported Ollama message block type: {block_type!r}"
                )
            text = "".join(text_parts)
        else:
            raise ModelRequestError("Ollama message content must be a string or list")

        converted_message: dict[str, Any] = {"role": role, "content": text}
        if images:
            converted_message["images"] = images
        converted.append(converted_message)
    return converted


@dataclass
class _ToolCallBuffer:
    name_parts: list[str] = field(default_factory=list)
    argument_parts: list[str] = field(default_factory=list)
    argument_object: dict[str, Any] | None = None

    def add_name(self, name: Any) -> bool:
        if name is None or name == "":
            return False
        if not isinstance(name, str):
            raise ModelResponseError("Ollama tool names must be strings")
        current = "".join(self.name_parts)
        if name == current:
            return True
        self.name_parts.append(name)
        return True

    def add_arguments(self, arguments: Any) -> bool:
        if arguments is None:
            return False
        if isinstance(arguments, dict):
            if self.argument_parts:
                raise ModelResponseError(
                    "Ollama tool arguments cannot mix object and string forms"
                )
            if self.argument_object is None:
                self.argument_object = arguments
            elif self.argument_object != arguments:
                raise ModelResponseError(
                    "Ollama tool argument objects changed across chunks"
                )
            return True
        if isinstance(arguments, str):
            if self.argument_object is not None:
                raise ModelResponseError(
                    "Ollama tool arguments cannot mix object and string forms"
                )
            self.argument_parts.append(arguments)
            return bool(arguments)
        raise ModelResponseError("Ollama tool arguments must be an object or string")

    def build(self) -> RawToolCall:
        name = "".join(self.name_parts)
        if not name:
            raise ModelResponseError("Ollama tool call is missing a function name")
        arguments: dict[str, Any] | str
        if self.argument_object is not None:
            arguments = self.argument_object
        else:
            arguments = "".join(self.argument_parts)
        return RawToolCall(name=name, arguments=arguments)


class OllamaAdapter:
    """Adapter for Ollama's native ``/api/chat`` protocol."""

    def __init__(
        self,
        config: ModelConfig,
        verbose: bool = True,
        *,
        client: httpx.Client | None = None,
    ):
        if config.provider != "ollama":
            raise ModelConfigurationError("OllamaAdapter requires provider='ollama'")
        self.config = config
        self.verbose = verbose
        self._closed = False
        if client is not None:
            self.client = client
        else:
            base_url = config.base_url
            if base_url is None:
                raise ModelConfigurationError("Ollama base_url was not normalized")
            self.client = httpx.Client(
                base_url=base_url,
                headers=config.extra_headers,
                timeout=config.timeout,
            )

    def _request_body(
        self, messages: list[dict[str, Any]], *, use_tools: bool
    ) -> dict[str, Any]:
        extra_body = copy.deepcopy(self.config.extra_body)
        extra_options = extra_body.pop("options", {})
        options = dict(extra_options)
        options.update(
            {
                "num_predict": self.config.max_tokens,
                "temperature": (
                    0.0 if self.config.temperature is None else self.config.temperature
                ),
                "top_p": 0.85 if self.config.top_p is None else self.config.top_p,
            }
        )
        body = {
            **extra_body,
            "model": self.config.model_name,
            "messages": _convert_messages(messages),
            "stream": True,
            "options": options,
        }
        if use_tools:
            body["tools"] = _ollama_tools()
        return body

    @staticmethod
    def _normalize_error(
        error: BaseException,
        *,
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
        if isinstance(error, (httpx.TimeoutException, httpx.TransportError)):
            return ModelConnectionError("Ollama service is unreachable")
        if isinstance(error, httpx.HTTPStatusError):
            status = error.response.status_code
            error_type = ModelConnectionError if connection_check else ModelRequestError
            return error_type(f"Ollama request failed (HTTP {status})")
        error_type = ModelConnectionError if connection_check else ModelRequestError
        return error_type("Ollama request failed")

    def request(
        self, messages: list[dict[str, Any]], *, use_tools: bool
    ) -> RawModelOutput:
        if self._closed:
            raise ModelRequestError("OllamaAdapter is closed")

        started = time.monotonic()
        time_to_first_token: float | None = None
        time_to_thinking_end: float | None = None
        thinking_parts: list[str] = []
        final_parts: list[str] = []
        raw_parts: list[str] = []
        indexed_tool_buffers: dict[int, _ToolCallBuffer] = {}
        tool_call_order: list[RawToolCall | int] = []
        emitted_output = False
        saw_done = False
        safe_error: BaseException | None = None

        def mark_output(*, ends_thinking: bool = False) -> None:
            nonlocal emitted_output, time_to_first_token, time_to_thinking_end
            emitted_output = True
            now = time.monotonic() - started
            if time_to_first_token is None:
                time_to_first_token = now
            if ends_thinking and thinking_parts and time_to_thinking_end is None:
                time_to_thinking_end = now

        try:
            with self.client.stream(
                "POST",
                "api/chat",
                json=self._request_body(messages, use_tools=use_tools),
                headers=self.config.extra_headers,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.strip():
                        continue
                    payload = decode_json_object(line, context="Ollama stream line")
                    if "error" in payload:
                        raise ModelRequestError("Ollama returned a stream error")
                    message = payload.get("message", {})
                    if not isinstance(message, dict):
                        raise ModelResponseError("Ollama message must be an object")

                    thinking = message.get("thinking", "")
                    if not isinstance(thinking, str):
                        raise ModelResponseError("Ollama thinking must be a string")
                    if thinking:
                        thinking_parts.append(thinking)
                        raw_parts.append(thinking)
                        mark_output()

                    content = message.get("content", "")
                    if not isinstance(content, str):
                        raise ModelResponseError("Ollama content must be a string")
                    if content:
                        final_parts.append(content)
                        raw_parts.append(content)
                        mark_output(ends_thinking=True)

                    tool_calls = message.get("tool_calls", payload.get("tool_calls", []))
                    if tool_calls is None:
                        tool_calls = []
                    if not isinstance(tool_calls, list):
                        raise ModelResponseError("Ollama tool_calls must be a list")
                    for tool_call in tool_calls:
                        if not isinstance(tool_call, dict):
                            raise ModelResponseError(
                                "Ollama tool call entries must be objects"
                            )
                        has_explicit_index = "index" in tool_call
                        if has_explicit_index:
                            index = tool_call["index"]
                            if type(index) is not int or index < 0:
                                raise ModelResponseError(
                                    "Ollama tool call index must be a non-negative integer"
                                )
                            if index not in indexed_tool_buffers:
                                indexed_tool_buffers[index] = _ToolCallBuffer()
                                tool_call_order.append(index)
                            buffer = indexed_tool_buffers[index]
                        else:
                            buffer = _ToolCallBuffer()

                        function = tool_call.get("function")
                        if not isinstance(function, dict):
                            raise ModelResponseError(
                                "Ollama tool call requires a function object"
                            )
                        emitted = buffer.add_name(function.get("name"))
                        emitted = buffer.add_arguments(
                            function.get("arguments")
                        ) or emitted
                        if not has_explicit_index:
                            tool_call_order.append(buffer.build())
                        if emitted:
                            mark_output(ends_thinking=True)

                    done = payload.get("done", False)
                    if not isinstance(done, bool):
                        raise ModelResponseError("Ollama done must be a boolean")
                    if done:
                        saw_done = True
                        break
        except Exception as exc:
            normalized = self._normalize_error(exc)
            if normalized is exc:
                raise
            safe_error = normalized

        if safe_error is not None:
            raise safe_error from None
        if not saw_done:
            raise ModelResponseError("Ollama stream ended before a done event")

        total_time = time.monotonic() - started
        if thinking_parts and time_to_thinking_end is None:
            time_to_thinking_end = total_time
        normalized_tool_calls = [
            indexed_tool_buffers[item].build()
            if isinstance(item, int)
            else item
            for item in tool_call_order
        ]
        return RawModelOutput(
            thinking="".join(thinking_parts),
            final_text="".join(final_parts),
            tool_calls=normalized_tool_calls,
            raw_content="".join(raw_parts),
            time_to_first_token=time_to_first_token,
            time_to_thinking_end=time_to_thinking_end,
            total_time=total_time,
        )

    def check_connection(self) -> None:
        if self._closed:
            raise ModelConnectionError("OllamaAdapter is closed")
        safe_error: BaseException | None = None
        try:
            response = self.client.get(
                "api/tags",
                headers=self.config.extra_headers,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(
                payload.get("models", []), list
            ):
                raise ModelConnectionError("Ollama /api/tags returned an invalid response")
            model_names = {
                model.get("name", model.get("model"))
                for model in payload.get("models", [])
                if isinstance(model, dict)
            }
            requested_model = self.config.model_name or ""
            model_available = requested_model in model_names or (
                ":" not in requested_model
                and f"{requested_model}:latest" in model_names
            )
            if not model_available:
                raise ModelConnectionError(
                    f"Ollama model {self.config.model_name!r} is not installed; "
                    f"run: ollama pull {self.config.model_name}"
                )
        except Exception as exc:
            normalized = self._normalize_error(exc, connection_check=True)
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
