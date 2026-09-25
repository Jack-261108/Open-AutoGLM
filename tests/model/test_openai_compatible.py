"""Offline tests for the OpenAI-compatible adapter."""

import traceback
from types import SimpleNamespace

import pytest

from phone_agent.model.base import (
    ModelConnectionError,
    ModelRequestError,
    RawToolCall,
    UnsupportedToolsError,
)
from phone_agent.model.client import ModelConfig
from phone_agent.model.openai_compatible import OpenAICompatibleAdapter


def ns(**kwargs):
    return SimpleNamespace(**kwargs)


def assert_secret_not_chained(error, secret="api-secret"):
    formatted = "".join(
        traceback.format_exception(type(error), error, error.__traceback__)
    )
    assert error.__cause__ is None
    assert error.__context__ is None
    assert secret not in formatted


def chunk(*, content=None, reasoning=None, tool_calls=None):
    return ns(
        choices=[
            ns(
                delta=ns(
                    content=content,
                    reasoning_content=reasoning,
                    tool_calls=tool_calls,
                )
            )
        ]
    )


class FakeStatusError(Exception):
    def __init__(self, status_code, body, message="provider secret api-secret"):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class FakeCompletions:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


class FakeClient:
    def __init__(self, *results, close_error=None):
        self.completions = FakeCompletions(*results)
        self.chat = ns(completions=self.completions)
        self.close_calls = 0
        self.close_error = close_error

    def close(self):
        self.close_calls += 1
        if self.close_error is not None:
            error = self.close_error
            self.close_error = None
            raise error


def test_default_client_normalizes_empty_key_and_uses_same_configuration(monkeypatch):
    captured = {}
    marker = FakeClient([])

    def fake_openai(**kwargs):
        captured.update(kwargs)
        return marker

    import openai

    monkeypatch.setattr(openai, "OpenAI", fake_openai)
    config = ModelConfig(
        api_key=None,
        timeout=9,
        extra_headers={"X-Proxy": "token"},
    )
    adapter = OpenAICompatibleAdapter(config, verbose=False)

    assert adapter.client is marker
    assert captured == {
        "base_url": "http://localhost:8000/v1",
        "api_key": "EMPTY",
        "timeout": 9,
        "default_headers": {"X-Proxy": "token"},
    }


def test_text_stream_maps_defaults_headers_body_and_reasoning():
    client = FakeClient(
        [
            chunk(reasoning="inspect "),
            chunk(reasoning="screen"),
            chunk(content="do(action='Back')"),
        ]
    )
    config = ModelConfig(
        extra_headers={"X-Test": "value"},
        extra_body={"vendor_option": True},
    )
    adapter = OpenAICompatibleAdapter(config, client=client)

    output = adapter.request([{"role": "user", "content": "screen"}], use_tools=False)

    call = client.completions.calls[0]
    assert call["temperature"] == 0.0
    assert call["top_p"] == 0.85
    assert call["frequency_penalty"] == 0.2
    assert call["max_tokens"] == 2048
    assert call["stream"] is True
    assert call["extra_headers"] == {"X-Test": "value"}
    assert call["extra_body"] == {"vendor_option": True}
    assert "tools" not in call
    assert output.thinking == "inspect screen"
    assert output.final_text == "do(action='Back')"
    assert output.raw_content == "inspect screendo(action='Back')"
    assert output.time_to_first_token is not None
    assert output.time_to_thinking_end is not None
    assert output.total_time >= 0


def test_tool_schema_and_stream_fragments_are_aggregated_by_index():
    tool_first = ns(
        index=0,
        function=ns(name="phone_", arguments='{"action":"Tap",'),
    )
    tool_second = ns(
        index=0,
        function=ns(name="action", arguments='"element":[10,20]}'),
    )
    client = FakeClient([chunk(tool_calls=[tool_first]), chunk(tool_calls=[tool_second])])
    adapter = OpenAICompatibleAdapter(ModelConfig(), client=client)

    output = adapter.request([], use_tools=True)

    assert output.tool_calls == [
        RawToolCall(
            name="phone_action",
            arguments='{"action":"Tap","element":[10,20]}',
        )
    ]
    tools = client.completions.calls[0]["tools"]
    assert [tool["function"]["name"] for tool in tools] == [
        "phone_action",
        "finish",
    ]
    assert tools[0]["type"] == "function"
    assert tools[0]["function"]["parameters"]["oneOf"]


def test_check_connection_uses_non_streaming_minimal_completion():
    client = FakeClient(ns(id="completion"))
    adapter = OpenAICompatibleAdapter(ModelConfig(), client=client)

    adapter.check_connection()

    call = client.completions.calls[0]
    assert call["stream"] is False
    assert call["max_tokens"] == 1
    assert call["messages"] == [{"role": "user", "content": "ping"}]
    assert "tools" not in call


@pytest.mark.parametrize(
    "body",
    [
        {"error": {"param": "tools", "message": "not supported"}},
        {
            "error": {
                "code": "unsupported_parameter",
                "message": "Unknown parameter: tools",
            }
        },
        {
            "error": {
                "parameter": "tool_choice",
                "code": "unsupported_value",
                "message": "tool_choice is unsupported",
            }
        },
    ],
)
def test_structured_zero_output_tools_rejection_is_downgradable(body):
    client = FakeClient(FakeStatusError(400, body))
    adapter = OpenAICompatibleAdapter(ModelConfig(), client=client)

    with pytest.raises(UnsupportedToolsError) as error:
        adapter.request([], use_tools=True)
    assert_secret_not_chained(error.value)


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (401, {"error": {"param": "tools"}}),
        (429, {"error": {"param": "tools"}}),
        (500, {"error": {"param": "tools"}}),
        (
            400,
            {
                "error": {
                    "param": "tools",
                    "code": "invalid_schema",
                    "message": "Invalid JSON schema",
                }
            },
        ),
        (400, {"error": {"param": "tools[0].function.parameters"}}),
        (400, {"error": {"param": "tools", "type": "invalid_tool_schema"}}),
        (400, {"error": {"code": "unsupported_parameter"}}),
    ],
)
def test_non_downgradable_openai_errors_remain_request_errors(status, body):
    client = FakeClient(FakeStatusError(status, body))
    adapter = OpenAICompatibleAdapter(ModelConfig(), client=client)

    with pytest.raises(ModelRequestError) as error:
        adapter.request([], use_tools=True)

    assert not isinstance(error.value, UnsupportedToolsError)
    assert "api-secret" not in str(error.value)
    assert_secret_not_chained(error.value)


def test_tools_error_after_stream_output_does_not_downgrade():
    def failing_stream():
        yield chunk(content="partial")
        raise FakeStatusError(400, {"error": {"param": "tools"}})

    client = FakeClient(failing_stream())
    adapter = OpenAICompatibleAdapter(ModelConfig(), client=client)

    with pytest.raises(ModelRequestError) as error:
        adapter.request([], use_tools=True)

    assert not isinstance(error.value, UnsupportedToolsError)


def test_connection_error_and_health_error_are_normalized_without_secrets():
    class APITimeoutError(Exception):
        pass

    request_adapter = OpenAICompatibleAdapter(
        ModelConfig(), client=FakeClient(APITimeoutError("api-secret"))
    )
    with pytest.raises(ModelConnectionError) as request_error:
        request_adapter.request([], use_tools=False)
    assert "api-secret" not in str(request_error.value)
    assert_secret_not_chained(request_error.value)

    health_adapter = OpenAICompatibleAdapter(
        ModelConfig(),
        client=FakeClient(FakeStatusError(401, {"error": {"message": "api-secret"}})),
    )
    with pytest.raises(ModelConnectionError) as health_error:
        health_adapter.check_connection()
    assert "api-secret" not in str(health_error.value)
    assert_secret_not_chained(health_error.value)


def test_close_is_idempotent_and_can_retry_after_close_failure():
    client = FakeClient([], close_error=RuntimeError("close failed"))
    adapter = OpenAICompatibleAdapter(ModelConfig(), client=client)

    with pytest.raises(RuntimeError, match="close failed"):
        adapter.close()
    adapter.close()
    adapter.close()

    assert client.close_calls == 2
    with pytest.raises(ModelRequestError, match="closed"):
        adapter.request([], use_tools=False)
