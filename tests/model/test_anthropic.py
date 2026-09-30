"""Offline tests for the Anthropic Messages adapter."""

import sys
import traceback
from types import SimpleNamespace

import pytest

from phone_agent.model.anthropic import AnthropicAdapter
from phone_agent.model.base import (
    ContentDelta,
    ModelConnectionError,
    ModelRequestError,
    ModelResponseError,
    ModelStreamEvent,
    RawToolCall,
    ThinkingDelta,
    UnsupportedToolsError,
)
from phone_agent.model.client import ModelConfig


def assert_secret_not_chained(error, secret="api-secret"):
    formatted = "".join(
        traceback.format_exception(type(error), error, error.__traceback__)
    )
    assert error.__cause__ is None
    assert error.__context__ is None
    assert secret not in formatted


class FakeStatusError(Exception):
    def __init__(self, status_code, body, message="api-secret"):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class FakeMessages:
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
        self.messages = FakeMessages(*results)
        self.close_calls = 0
        self.close_error = close_error

    def close(self):
        self.close_calls += 1
        if self.close_error is not None:
            error = self.close_error
            self.close_error = None
            raise error


def event(event_type, **kwargs):
    return {"type": event_type, **kwargs}


def block_start(index, block_type, **kwargs):
    return event(
        "content_block_start",
        index=index,
        content_block={"type": block_type, **kwargs},
    )


def delta(index, delta_type, **kwargs):
    return event(
        "content_block_delta",
        index=index,
        delta={"type": delta_type, **kwargs},
    )


def block_stop(index):
    return event("content_block_stop", index=index)


def config(**kwargs):
    return ModelConfig(
        provider="anthropic",
        model_name="claude-test",
        api_key="secret",
        **kwargs,
    )


def test_default_client_uses_anthropic_sdk_configuration(monkeypatch):
    captured = {}
    marker = FakeClient([])

    def fake_anthropic(**kwargs):
        captured.update(kwargs)
        return marker

    monkeypatch.setitem(
        sys.modules,
        "anthropic",
        SimpleNamespace(Anthropic=fake_anthropic),
    )
    adapter = AnthropicAdapter(
        config(
            base_url="https://proxy.example.test/anthropic",
            timeout=17,
            extra_headers={"X-Proxy": "token"},
        ),
        verbose=False,
    )

    assert adapter.client is marker
    assert captured == {
        "api_key": "secret",
        "base_url": "https://proxy.example.test/anthropic",
        "timeout": 17,
        "default_headers": {"X-Proxy": "token"},
    }


def test_message_image_system_tools_and_sampling_mapping():
    client = FakeClient(
        [
            block_start(0, "text", text=""),
            delta(0, "text_delta", text="do(action='Back')"),
            block_stop(0),
            event("message_stop"),
        ]
    )
    adapter = AnthropicAdapter(
        config(
            top_p=0.7,
            extra_headers={"X-Proxy": "value"},
            extra_body={"metadata": {"source": "test"}},
        ),
        client=client,
    )
    messages = [
        {"role": "system", "content": "system one"},
        {"role": "system", "content": [{"type": "text", "text": "system two"}]},
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,abc123"},
                },
                {"type": "text", "text": "look"},
            ],
        },
    ]

    output = adapter.request(messages, use_tools=True)

    call = client.messages.calls[0]
    assert call["system"] == "system one\nsystem two"
    assert call["messages"] == [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": "abc123",
                    },
                },
                {"type": "text", "text": "look"},
            ],
        }
    ]
    assert call["temperature"] == 0.0
    assert call["top_p"] == 0.7
    assert "frequency_penalty" not in call
    assert call["extra_headers"] == {"X-Proxy": "value"}
    assert call["extra_body"] == {"metadata": {"source": "test"}}
    assert [tool["name"] for tool in call["tools"]] == ["phone_action", "finish"]
    assert output.final_text == "do(action='Back')"
    assert output.raw_content == "do(action='Back')"


def test_thinking_and_partial_tool_json_are_isolated_and_aggregated():
    client = FakeClient(
        [
            block_start(0, "thinking", thinking=""),
            delta(0, "thinking_delta", thinking="inspect "),
            delta(0, "thinking_delta", thinking="screen"),
            block_stop(0),
            block_start(2, "tool_use", name="phone_action", input={}),
            delta(2, "input_json_delta", partial_json='{"action":"Tap",'),
            delta(2, "input_json_delta", partial_json='"element":[10,20]}'),
            block_stop(2),
            event("message_delta", delta={"stop_reason": "tool_use"}),
            event("message_stop"),
        ]
    )
    adapter = AnthropicAdapter(config(), client=client)

    output = adapter.request([], use_tools=True)

    assert output.thinking == "inspect screen"
    assert output.final_text == ""
    assert output.tool_calls == [
        RawToolCall(
            name="phone_action",
            arguments={"action": "Tap", "element": [10, 20]},
        )
    ]
    assert output.raw_content == "inspect screen"
    assert output.time_to_first_token is not None
    assert output.time_to_thinking_end is not None


def test_signature_and_redacted_thinking_blocks_are_safely_ignored():
    client = FakeClient(
        [
            block_start(0, "thinking", thinking="reasoning"),
            delta(0, "signature_delta", signature="signed-value"),
            block_stop(0),
            block_start(1, "redacted_thinking", data="redacted-secret"),
            block_stop(1),
            event("message_stop"),
        ]
    )
    adapter = AnthropicAdapter(config(), client=client)

    output = adapter.request([], use_tools=False)

    assert output.thinking == "reasoning"
    assert output.raw_content == "reasoning"
    assert "signed-value" not in output.raw_content
    assert "redacted-secret" not in output.raw_content


def test_signature_delta_requires_a_string():
    client = FakeClient(
        [
            block_start(0, "thinking", thinking="reasoning"),
            delta(0, "signature_delta", signature=123),
            block_stop(0),
            event("message_stop"),
        ]
    )

    with pytest.raises(ModelResponseError, match="signature_delta"):
        AnthropicAdapter(config(), client=client).request([], use_tools=False)


@pytest.mark.parametrize(
    "events",
    [
        [block_start(0, "text", text="done"), block_stop(0)],
        [event("message_stop"), event("message_stop")],
        [event("message_stop"), event("ping")],
    ],
)
def test_message_stop_must_appear_once_and_be_the_final_event(events):
    with pytest.raises(ModelResponseError):
        AnthropicAdapter(config(), client=FakeClient(events)).request(
            [], use_tools=False
        )


def test_initial_tool_input_without_partial_json_is_used_and_sorted_by_index():
    client = FakeClient(
        [
            block_start(3, "tool_use", name="finish", input={"message": "done"}),
            block_stop(3),
            block_start(1, "tool_use", name="phone_action", input={"action": "Back"}),
            block_stop(1),
            event("message_stop"),
        ]
    )
    adapter = AnthropicAdapter(config(), client=client)

    output = adapter.request([], use_tools=True)

    assert output.tool_calls == [
        RawToolCall("phone_action", {"action": "Back"}),
        RawToolCall("finish", {"message": "done"}),
    ]


@pytest.mark.parametrize(
    "events",
    [
        [block_start(0, "text", text=""), block_start(0, "text", text="")],
        [delta(0, "text_delta", text="orphan")],
        [block_start(0, "text", text=""), delta(0, "thinking_delta", thinking="bad")],
        [block_start(0, "text", text="")],
        [
            block_start(0, "tool_use", name="phone_action", input={"action": "Back"}),
            delta(0, "input_json_delta", partial_json='{"action":"Home"}'),
            block_stop(0),
        ],
        [
            block_start(0, "tool_use", name="phone_action", input={}),
            delta(0, "input_json_delta", partial_json='{"action":'),
            block_stop(0),
        ],
    ],
)
def test_invalid_anthropic_event_sequences_fail_closed(events):
    adapter = AnthropicAdapter(config(), client=FakeClient(events))

    with pytest.raises(ModelResponseError):
        adapter.request([], use_tools=True)


def test_check_connection_is_non_streaming_and_uses_same_client():
    client = FakeClient(SimpleNamespace(id="message"))
    model_config = config(
        extra_body={
            "thinking": {"type": "enabled", "budget_tokens": 1024},
            "metadata": {"source": "health"},
        }
    )
    adapter = AnthropicAdapter(model_config, client=client)

    adapter.check_connection()

    call = client.messages.calls[0]
    assert call["stream"] is False
    assert call["max_tokens"] == 1
    assert call["messages"] == [{"role": "user", "content": "ping"}]
    assert call["extra_body"] == {"metadata": {"source": "health"}}
    assert model_config.extra_body["thinking"]["budget_tokens"] == 1024
    assert "tools" not in call


def test_temperature_is_omitted_only_while_extended_thinking_is_enabled():
    enabled = FakeClient([event("message_stop")])
    AnthropicAdapter(
        config(extra_body={"thinking": {"type": "enabled", "budget_tokens": 1024}}),
        client=enabled,
    ).request([], use_tools=False)
    assert "temperature" not in enabled.messages.calls[0]

    for extra_body in (
        {},
        {"thinking": {"type": "disabled"}},
        {"thinking": "enabled"},
        {"thinking": {"budget_tokens": 1024}},
    ):
        client = FakeClient([event("message_stop")])
        AnthropicAdapter(config(extra_body=extra_body), client=client).request(
            [], use_tools=False
        )
        assert client.messages.calls[0]["temperature"] == 0.0


def test_zero_output_structured_tools_error_can_downgrade():
    client = FakeClient(
        FakeStatusError(
            422,
            {
                "error": {
                    "code": "unsupported_parameter",
                    "parameter": "tools",
                    "message": "tools unsupported",
                }
            },
        )
    )
    adapter = AnthropicAdapter(config(), client=client)

    with pytest.raises(UnsupportedToolsError) as error:
        adapter.request([], use_tools=True)
    assert_secret_not_chained(error.value)


def test_schema_auth_and_post_output_errors_do_not_downgrade_or_leak_secrets():
    schema_client = FakeClient(
        FakeStatusError(
            400,
            {
                "error": {
                    "param": "tools",
                    "code": "invalid_schema",
                    "message": "schema api-secret",
                }
            },
        )
    )
    with pytest.raises(ModelRequestError) as schema_error:
        AnthropicAdapter(config(), client=schema_client).request([], use_tools=True)
    assert not isinstance(schema_error.value, UnsupportedToolsError)
    assert "api-secret" not in str(schema_error.value)
    assert_secret_not_chained(schema_error.value)

    auth_client = FakeClient(FakeStatusError(401, {"error": {"param": "tools"}}))
    with pytest.raises(ModelRequestError) as auth_error:
        AnthropicAdapter(config(), client=auth_client).request([], use_tools=True)
    assert not isinstance(auth_error.value, UnsupportedToolsError)

    def failing_events():
        yield block_start(0, "text", text="partial")
        raise FakeStatusError(400, {"error": {"param": "tools"}})

    with pytest.raises(ModelRequestError) as streamed_error:
        AnthropicAdapter(config(), client=FakeClient(failing_events())).request(
            [], use_tools=True
        )
    assert not isinstance(streamed_error.value, UnsupportedToolsError)


def test_connection_and_health_errors_are_normalized():
    class APIConnectionError(Exception):
        pass

    adapter = AnthropicAdapter(
        config(), client=FakeClient(APIConnectionError("api-secret"))
    )
    with pytest.raises(ModelConnectionError) as request_error:
        adapter.request([], use_tools=False)
    assert "api-secret" not in str(request_error.value)
    assert_secret_not_chained(request_error.value)

    health = AnthropicAdapter(
        config(), client=FakeClient(FakeStatusError(403, {"error": {}}))
    )
    with pytest.raises(ModelConnectionError) as health_error:
        health.check_connection()
    assert_secret_not_chained(health_error.value)


def test_close_is_idempotent_and_retryable_after_failure():
    client = FakeClient([], close_error=RuntimeError("close failed"))
    adapter = AnthropicAdapter(config(), client=client)

    with pytest.raises(RuntimeError, match="close failed"):
        adapter.close()
    adapter.close()
    adapter.close()

    assert client.close_calls == 2
    with pytest.raises(ModelRequestError, match="closed"):
        adapter.request([], use_tools=False)


def test_anthropic_streaming_events():
    stream_events = [
        event("message_start"),
        block_start(0, "thinking"),
        delta(0, "thinking_delta", thinking="step 1 thinking "),
        delta(0, "thinking_delta", thinking="step 2 thinking"),
        block_stop(0),
        block_start(1, "text"),
        delta(1, "text_delta", text="do(action="),
        delta(1, "text_delta", text="'Back')"),
        block_stop(1),
        event("message_delta"),
        event("message_stop"),
    ]
    client = FakeClient(stream_events)
    adapter = AnthropicAdapter(config(), client=client)
    emitted: list[ModelStreamEvent] = []

    output = adapter.request([], use_tools=False, on_event=emitted.append)

    assert output.thinking == "step 1 thinking step 2 thinking"
    assert output.final_text == "do(action='Back')"
    assert emitted == [
        ThinkingDelta("step 1 thinking "),
        ThinkingDelta("step 2 thinking"),
        ContentDelta("do(action="),
        ContentDelta("'Back')"),
    ]

