"""Tests for stable public model package imports."""

import inspect

from phone_agent.model import (
    MessageBuilder,
    ModelAdapter,
    ModelClient,
    ModelClientProtocol,
    ModelConfig,
    ModelConfigurationError,
    ModelResponse,
    ModelResponseParser,
    ParsedResponse,
    RawModelOutput,
    RawToolCall,
    UnsupportedToolsError,
    get_tool_schemas,
)
from phone_agent.model.client import ModelClient as DirectModelClient
from phone_agent.model.client import ModelConfig as DirectModelConfig
from phone_agent.model.tool_schema import FINISH_TOOL, PHONE_ACTION_TOOL


def test_legacy_client_and_config_imports_remain_stable():
    assert ModelClient is DirectModelClient
    assert ModelConfig is DirectModelConfig


def test_model_response_keeps_old_positional_fields_and_appends_parsed_action():
    response = ModelResponse("thinking", "action", "raw", 0.1, 0.2, 0.3)

    assert response.thinking == "thinking"
    assert response.action == "action"
    assert response.raw_content == "raw"
    assert response.time_to_first_token == 0.1
    assert response.time_to_thinking_end == 0.2
    assert response.total_time == 0.3
    assert response.parsed_action is None


def test_model_adapter_protocol_has_keyword_tool_selection():
    signature = inspect.signature(ModelAdapter.request)

    assert "use_tools" in signature.parameters
    assert signature.parameters["use_tools"].kind is inspect.Parameter.KEYWORD_ONLY


def test_model_client_protocol_remains_request_only():
    methods = {
        name
        for name, value in ModelClientProtocol.__dict__.items()
        if callable(value) and not name.startswith("_")
    }

    assert methods == {"request"}


def test_public_types_and_tool_schemas_are_importable():
    assert RawToolCall("finish", {"message": "done"}).name == "finish"
    assert isinstance(RawModelOutput(), RawModelOutput)
    assert ModelResponseParser is not None
    assert ParsedResponse is not None
    assert issubclass(UnsupportedToolsError, Exception)
    assert issubclass(ModelConfigurationError, ValueError)
    assert PHONE_ACTION_TOOL["name"] == "phone_action"
    assert FINISH_TOOL["name"] == "finish"
    assert [tool["name"] for tool in get_tool_schemas()] == [
        "phone_action",
        "finish",
    ]


def test_message_builder_behavior_is_unchanged():
    assert MessageBuilder.create_system_message("system") == {
        "role": "system",
        "content": "system",
    }
    assert MessageBuilder.create_user_message("look", "abc") == {
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64,abc"},
            },
            {"type": "text", "text": "look"},
        ],
    }
    assert MessageBuilder.create_assistant_message("done") == {
        "role": "assistant",
        "content": "done",
    }
    assert MessageBuilder.build_screen_info("Settings", width=100) == (
        '{"current_app": "Settings", "width": 100}'
    )
