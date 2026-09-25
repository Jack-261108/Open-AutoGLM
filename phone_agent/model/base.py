"""Provider-neutral model contracts and errors."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from phone_agent.model.client import ModelResponse


@dataclass
class RawToolCall:
    """A provider tool call before action normalization."""

    name: str
    arguments: dict[str, Any] | str


@dataclass
class RawModelOutput:
    """Provider-neutral raw output consumed by the response parser."""

    thinking: str = ""
    final_text: str = ""
    tool_calls: list[RawToolCall] = field(default_factory=list)
    raw_content: str = ""
    time_to_first_token: float | None = None
    time_to_thinking_end: float | None = None
    total_time: float = 0.0


class ModelAdapter(Protocol):
    """Complete transport adapter contract used by the model facade."""

    def request(
        self, messages: list[dict[str, Any]], *, use_tools: bool
    ) -> RawModelOutput:
        """Send messages and return normalized provider output."""
        ...

    def check_connection(self) -> None:
        """Validate provider connectivity and configuration."""
        ...

    def close(self) -> None:
        """Release transport resources."""
        ...


class ModelClientProtocol(Protocol):
    """Minimal model client contract required by agents."""

    def request(self, messages: list[dict[str, Any]]) -> ModelResponse:
        """Send messages and return a parsed model response."""
        ...


class ModelConfigurationError(ValueError):
    """Raised when model configuration is invalid."""


class ModelConnectionError(RuntimeError):
    """Raised when a provider cannot be reached."""


class ModelRequestError(RuntimeError):
    """Raised when a provider rejects or cannot complete a request."""


class ModelResponseError(ValueError):
    """Raised when provider output violates the response contract."""


class UnsupportedToolsError(ModelRequestError):
    """Raised when a provider explicitly rejects tool parameters."""


_UNSUPPORTED_TOOL_CODES = frozenset(("unsupported_parameter", "unsupported_value"))
_TOOL_PARAMETERS = frozenset(("tools", "tool_choice"))
_SCHEMA_ERROR_TERMS = (
    "schema",
    "json schema",
    "properties",
    "required field",
    "function definition",
)


def get_error_status_code(error: BaseException) -> int | None:
    """Extract an HTTP status code without depending on a provider SDK type."""

    status = getattr(error, "status_code", None)
    if isinstance(status, int):
        return status
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def get_error_body(error: BaseException) -> Any:
    """Extract a structured provider error body when one is available."""

    body = getattr(error, "body", None)
    if body is not None:
        return body
    response = getattr(error, "response", None)
    if response is None:
        return None
    try:
        return response.json()
    except Exception:
        return None


def _error_mapping(body: Any) -> Mapping[str, Any] | None:
    if isinstance(body, Mapping):
        nested = body.get("error")
        if nested is not None:
            return _error_mapping(nested) or body
        return body
    model_dump = getattr(body, "model_dump", None)
    if callable(model_dump):
        return _error_mapping(model_dump())
    return None


def is_unsupported_tools_error_response(
    status_code: int | None,
    body: Any,
    *,
    zero_output: bool,
) -> bool:
    """Conservatively classify a structured zero-output tools rejection."""

    if not zero_output or status_code not in {400, 422}:
        return False
    error = _error_mapping(body)
    if error is None:
        return False

    parameter = error.get("param", error.get("parameter"))
    code = error.get("code")
    error_type = error.get("type")
    message = error.get("message")
    normalized_parameter = parameter.strip().lower() if isinstance(parameter, str) else ""
    normalized_code = code.strip().lower() if isinstance(code, str) else ""
    normalized_type = error_type.strip().lower() if isinstance(error_type, str) else ""
    normalized_message = message.lower() if isinstance(message, str) else ""

    if normalized_parameter and normalized_parameter not in _TOOL_PARAMETERS:
        return False
    if any(
        term in normalized_code
        or term in normalized_type
        or term in normalized_message
        for term in _SCHEMA_ERROR_TERMS
    ):
        return False
    if normalized_parameter in _TOOL_PARAMETERS:
        return True
    if normalized_code not in _UNSUPPORTED_TOOL_CODES:
        return False
    return any(
        re.search(rf"\b{re.escape(parameter_name)}\b", normalized_message)
        for parameter_name in _TOOL_PARAMETERS
    )
