"""Public model-layer API."""

from phone_agent.model.base import (
    ContentDelta,
    ModelAdapter,
    ModelClientProtocol,
    ModelConfigurationError,
    ModelConnectionError,
    ModelRequestError,
    ModelResponseError,
    ModelStreamEvent,
    RawModelOutput,
    RawToolCall,
    StreamCallback,
    StreamCompleted,
    ThinkingDelta,
    ToolCallDelta,
    UnsupportedToolsError,
)
from phone_agent.model.client import (
    MessageBuilder,
    ModelClient,
    ModelConfig,
    ModelResponse,
    validate_extra_body,
)
from phone_agent.model.response_parser import ModelResponseParser, ParsedResponse
from phone_agent.model.spinner import InferenceSpinner
from phone_agent.model.tool_schema import get_tool_schemas

__all__ = [
    "ContentDelta",
    "InferenceSpinner",
    "MessageBuilder",
    "ModelAdapter",
    "ModelClient",
    "ModelClientProtocol",
    "ModelConfig",
    "ModelConfigurationError",
    "ModelConnectionError",
    "ModelRequestError",
    "ModelResponse",
    "ModelResponseError",
    "ModelResponseParser",
    "ModelStreamEvent",
    "ParsedResponse",
    "RawModelOutput",
    "RawToolCall",
    "StreamCallback",
    "StreamCompleted",
    "ThinkingDelta",
    "ToolCallDelta",
    "UnsupportedToolsError",
    "get_tool_schemas",
    "validate_extra_body",
]
