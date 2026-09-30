"""Provider-neutral model client facade and message helpers."""

from __future__ import annotations

import copy
import inspect
import json
import math
import time
from dataclasses import dataclass, field, replace
from urllib.parse import urlsplit
from typing import Any, Literal

from phone_agent.model.base import (
    ModelAdapter,
    ModelConfigurationError,
    ModelConnectionError,
    ModelRequestError,
    RawModelOutput,
    StreamCallback,
    StreamCompleted,
    UnsupportedToolsError,
)
from phone_agent.model.response_parser import parse_model_output

Provider = Literal["openai", "anthropic", "ollama"]
ToolMode = Literal["auto", "native", "text"]

_PROVIDER_DEFAULT_URLS: dict[str, str] = {
    "openai": "http://localhost:8000/v1",
    "anthropic": "https://api.anthropic.com",
    "ollama": "http://localhost:11434",
}
_OPENAI_DEFAULT_MODEL = "autoglm-phone-9b"
_ADAPTER_IMPORTS: dict[str, tuple[str, str]] = {
    "openai": (
        "phone_agent.model.openai_compatible",
        "OpenAICompatibleAdapter",
    ),
    "anthropic": ("phone_agent.model.anthropic", "AnthropicAdapter"),
    "ollama": ("phone_agent.model.ollama", "OllamaAdapter"),
}
_COMMON_RESERVED_BODY_FIELDS = frozenset(
    ("model", "messages", "tools", "tool_choice", "stream")
)
_PROVIDER_RESERVED_BODY_FIELDS: dict[str, frozenset[str]] = {
    "openai": frozenset(
        ("max_tokens", "temperature", "top_p", "frequency_penalty")
    ),
    "anthropic": frozenset(("max_tokens", "temperature", "top_p", "system")),
    "ollama": frozenset(),
}
_OLLAMA_RESERVED_OPTION_FIELDS = frozenset(
    ("num_predict", "temperature", "top_p")
)


def _validate_optional_number(name: str, value: float | None) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelConfigurationError(f"{name} must be a number or None")
    if not math.isfinite(value):
        raise ModelConfigurationError(f"{name} must be finite")


def validate_extra_body(provider: str, extra_body: object) -> None:
    """Reject provider request fields owned by the facade or adapter."""

    if provider not in _PROVIDER_DEFAULT_URLS:
        raise ModelConfigurationError(f"Unknown provider: {provider!r}")
    if not isinstance(extra_body, dict):
        raise ModelConfigurationError("extra_body must be a dictionary")
    if any(not isinstance(key, str) for key in extra_body):
        raise ModelConfigurationError("extra_body keys must be strings")

    reserved = _COMMON_RESERVED_BODY_FIELDS | _PROVIDER_RESERVED_BODY_FIELDS[provider]
    conflicts = set(extra_body) & reserved
    if conflicts:
        raise ModelConfigurationError(
            f"extra_body cannot override reserved fields: {sorted(conflicts)!r}"
        )

    if provider != "ollama":
        return
    if "options" not in extra_body:
        return
    options = extra_body["options"]
    if not isinstance(options, dict):
        raise ModelConfigurationError("Ollama extra_body.options must be a dictionary")
    if any(not isinstance(key, str) for key in options):
        raise ModelConfigurationError("Ollama extra_body.options keys must be strings")
    option_conflicts = set(options) & _OLLAMA_RESERVED_OPTION_FIELDS
    if option_conflicts:
        raise ModelConfigurationError(
            "Ollama extra_body.options cannot override generated fields: "
            f"{sorted(option_conflicts)!r}"
        )


@dataclass
class ModelConfig:
    """Configuration shared by all model providers.

    The first nine fields retain their historical order so existing positional
    construction keeps the same meaning. Provider-specific fields are appended.
    """

    base_url: str | None = None
    api_key: str | None = field(default=None, repr=False)
    model_name: str | None = None
    max_tokens: int = 2048
    temperature: float | None = None
    top_p: float | None = None
    frequency_penalty: float | None = None
    extra_body: dict[str, Any] = field(default_factory=dict)
    lang: str = "cn"  # Language for UI messages: 'cn' or 'en'
    provider: Provider = "openai"
    tool_mode: ToolMode = "auto"
    timeout: float = 120.0
    extra_headers: dict[str, str] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.provider, str) or self.provider not in _PROVIDER_DEFAULT_URLS:
            raise ModelConfigurationError(
                "provider must be one of: openai, anthropic, ollama"
            )
        if not isinstance(self.tool_mode, str) or self.tool_mode not in {
            "auto",
            "native",
            "text",
        }:
            raise ModelConfigurationError(
                "tool_mode must be one of: auto, native, text"
            )

        if self.base_url is None:
            self.base_url = _PROVIDER_DEFAULT_URLS[self.provider]
        elif not isinstance(self.base_url, str) or not self.base_url.strip():
            raise ModelConfigurationError("base_url must be a non-empty string or None")
        self.base_url = self.base_url.strip().rstrip("/")
        if not self.base_url:
            raise ModelConfigurationError("base_url must not contain only slashes")
        parsed_url = urlsplit(self.base_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
            raise ModelConfigurationError(
                "base_url must be an absolute http or https URL with a hostname"
            )
        if parsed_url.username is not None or parsed_url.password is not None:
            raise ModelConfigurationError(
                "base_url must not contain credentials; use api_key or extra_headers"
            )

        if self.model_name is None:
            if self.provider == "openai":
                self.model_name = _OPENAI_DEFAULT_MODEL
            else:
                raise ModelConfigurationError(
                    f"model_name is required for provider {self.provider!r}"
                )
        elif not isinstance(self.model_name, str) or not self.model_name.strip():
            raise ModelConfigurationError("model_name must be a non-empty string or None")
        else:
            self.model_name = self.model_name.strip()

        if self.api_key is not None and not isinstance(self.api_key, str):
            raise ModelConfigurationError("api_key must be a string or None")
        if self.provider == "anthropic":
            if (
                not self.api_key
                or not self.api_key.strip()
                or self.api_key.strip() == "EMPTY"
            ):
                raise ModelConfigurationError(
                    "Anthropic requires a non-empty api_key other than 'EMPTY'"
                )
        elif self.provider == "ollama" and self.api_key and self.api_key.strip():
            raise ModelConfigurationError(
                "Ollama does not use api_key; use extra_headers for proxy authentication"
            )

        if type(self.max_tokens) is not int or self.max_tokens <= 0:
            raise ModelConfigurationError("max_tokens must be a positive integer")
        _validate_optional_number("temperature", self.temperature)
        _validate_optional_number("top_p", self.top_p)
        _validate_optional_number("frequency_penalty", self.frequency_penalty)
        if self.temperature is not None and self.temperature < 0:
            raise ModelConfigurationError("temperature must be greater than or equal to 0")
        if self.top_p is not None and not 0 <= self.top_p <= 1:
            raise ModelConfigurationError("top_p must be between 0 and 1")
        if (
            self.provider in {"anthropic", "ollama"}
            and self.frequency_penalty not in {None, 0.0}
        ):
            raise ModelConfigurationError(
                f"frequency_penalty is not supported by provider {self.provider!r}"
            )

        if isinstance(self.timeout, bool) or not isinstance(self.timeout, (int, float)):
            raise ModelConfigurationError("timeout must be a positive number")
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ModelConfigurationError("timeout must be a positive finite number")

        if not isinstance(self.extra_body, dict):
            raise ModelConfigurationError("extra_body must be a dictionary")
        self.extra_body = copy.deepcopy(self.extra_body)
        validate_extra_body(self.provider, self.extra_body)

        if self.extra_headers is not None:
            if not isinstance(self.extra_headers, dict) or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in self.extra_headers.items()
            ):
                raise ModelConfigurationError(
                    "extra_headers must be a dictionary of string keys and values"
                )
            self.extra_headers = dict(self.extra_headers)


@dataclass
class ModelResponse:
    """Parsed response returned by the compatibility facade."""

    thinking: str
    action: str
    raw_content: str
    time_to_first_token: float | None = None
    time_to_thinking_end: float | None = None
    total_time: float | None = None
    parsed_action: dict[str, Any] | None = None


def _default_adapter_factory(config: ModelConfig, verbose: bool) -> ModelAdapter:
    module_name, class_name = _ADAPTER_IMPORTS[config.provider]
    try:
        module = __import__(module_name, fromlist=[class_name])
        adapter_class = getattr(module, class_name)
    except (ImportError, AttributeError) as exc:
        raise ModelConfigurationError(
            f"Adapter implementation for provider {config.provider!r} is not available"
        ) from exc
    return adapter_class(config, verbose=verbose)


def _request_accepts_on_event(request_fn: Any) -> bool:
    try:
        sig = inspect.signature(request_fn)
        return "on_event" in sig.parameters or any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        )
    except (ValueError, TypeError):
        return False


class ModelClient:
    """Compatibility facade that selects tools and parses adapter output."""

    def __init__(
        self,
        config: ModelConfig | None = None,
        verbose: bool = True,
        *,
        adapter: ModelAdapter | None = None,
    ):
        self.config = config or ModelConfig()
        self.verbose = verbose
        self.adapter = (
            adapter
            if adapter is not None
            else _default_adapter_factory(self.config, verbose)
        )
        self._closed = False
        self._adapter_accepts_on_event = _request_accepts_on_event(
            self.adapter.request
        )

    def _ensure_open_for_request(self) -> None:
        if self._closed:
            raise ModelRequestError("ModelClient is closed")

    def _request_adapter(
        self,
        messages: list[dict[str, Any]],
        *,
        use_tools: bool,
        on_event: StreamCallback | None,
    ) -> RawModelOutput:
        if self._adapter_accepts_on_event:
            return self.adapter.request(
                messages, use_tools=use_tools, on_event=on_event
            )
        return self.adapter.request(messages, use_tools=use_tools)

    def request(
        self,
        messages: list[dict[str, Any]],
        *,
        on_event: StreamCallback | None = None,
    ) -> ModelResponse:
        """Request one action, applying the configured tool fallback policy."""

        self._ensure_open_for_request()
        if self.config.tool_mode == "text":
            raw_output = self._request_adapter(
                messages, use_tools=False, on_event=on_event
            )
        elif self.config.tool_mode == "native":
            raw_output = self._request_adapter(
                messages, use_tools=True, on_event=on_event
            )
        else:
            first_attempt_started = time.monotonic()
            try:
                raw_output = self._request_adapter(
                    messages, use_tools=True, on_event=on_event
                )
            except UnsupportedToolsError:
                first_attempt_time = time.monotonic() - first_attempt_started
                fallback_output = self._request_adapter(
                    messages, use_tools=False, on_event=on_event
                )
                raw_output = replace(
                    fallback_output,
                    time_to_first_token=(
                        None
                        if fallback_output.time_to_first_token is None
                        else first_attempt_time + fallback_output.time_to_first_token
                    ),
                    time_to_thinking_end=(
                        None
                        if fallback_output.time_to_thinking_end is None
                        else first_attempt_time + fallback_output.time_to_thinking_end
                    ),
                    total_time=first_attempt_time + fallback_output.total_time,
                )

        if on_event is not None:
            on_event(
                StreamCompleted(
                    time_to_first_token=raw_output.time_to_first_token,
                    time_to_thinking_end=raw_output.time_to_thinking_end,
                    total_time=raw_output.total_time,
                )
            )

        parsed = parse_model_output(raw_output)
        return ModelResponse(
            thinking=parsed.thinking,
            action=parsed.action,
            raw_content=parsed.raw_content,
            time_to_first_token=raw_output.time_to_first_token,
            time_to_thinking_end=raw_output.time_to_thinking_end,
            total_time=raw_output.total_time,
            parsed_action=parsed.parsed_action,
        )

    def check_connection(self) -> None:
        """Delegate the provider-specific connection check."""

        if self._closed:
            raise ModelConnectionError("ModelClient is closed")
        self.adapter.check_connection()

    def close(self) -> None:
        """Close the adapter exactly once."""

        if self._closed:
            return
        self.adapter.close()
        self._closed = True


class MessageBuilder:
    """Helper class for building conversation messages."""

    @staticmethod
    def create_system_message(content: str) -> dict[str, Any]:
        """Create a system message."""
        return {"role": "system", "content": content}

    @staticmethod
    def create_user_message(
        text: str, image_base64: str | None = None
    ) -> dict[str, Any]:
        """
        Create a user message with optional image.

        Args:
            text: Text content.
            image_base64: Optional base64-encoded image.

        Returns:
            Message dictionary.
        """
        content = []

        if image_base64:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                }
            )

        content.append({"type": "text", "text": text})

        return {"role": "user", "content": content}

    @staticmethod
    def create_assistant_message(content: str) -> dict[str, Any]:
        """Create an assistant message."""
        return {"role": "assistant", "content": content}

    @staticmethod
    def remove_images_from_message(message: dict[str, Any]) -> dict[str, Any]:
        """
        Remove image content from a message to save context space.

        Args:
            message: Message dictionary.

        Returns:
            Message with images removed.
        """
        if isinstance(message.get("content"), list):
            message["content"] = [
                item for item in message["content"] if item.get("type") == "text"
            ]
        return message

    @staticmethod
    def build_screen_info(current_app: str, **extra_info) -> str:
        """
        Build screen info string for the model.

        Args:
            current_app: Current app name.
            **extra_info: Additional info to include.

        Returns:
            JSON string with screen info.
        """
        info = {"current_app": current_app, **extra_info}
        return json.dumps(info, ensure_ascii=False)
