"""Offline tests for the Ollama native HTTP adapter."""

import json
import traceback

import httpx
import pytest

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
from phone_agent.model.client import ModelClient, ModelConfig
from phone_agent.model.ollama import OllamaAdapter


def config(**kwargs):
    return ModelConfig(provider="ollama", model_name="vision-model", **kwargs)


def assert_secret_not_chained(error, secret="secret-host-detail"):
    formatted = "".join(
        traceback.format_exception(type(error), error, error.__traceback__)
    )
    assert error.__cause__ is None
    assert error.__context__ is None
    assert secret not in formatted


def mock_client(handler, model_config):
    return httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url=model_config.base_url,
        timeout=model_config.timeout,
    )


def ndjson_response(*payloads, status_code=200):
    content = "".join(json.dumps(payload) + "\n" for payload in payloads)
    return httpx.Response(status_code, content=content.encode())


def test_default_client_uses_ollama_http_configuration(monkeypatch):
    captured = {}
    marker = object()

    def fake_client(**kwargs):
        captured.update(kwargs)
        return marker

    monkeypatch.setattr("phone_agent.model.ollama.httpx.Client", fake_client)
    adapter = OllamaAdapter(
        config(
            base_url="https://proxy.example.test/ollama",
            timeout=23,
            extra_headers={"X-Proxy": "token"},
        ),
        verbose=False,
    )

    assert adapter.client is marker
    assert captured == {
        "base_url": "https://proxy.example.test/ollama",
        "headers": {"X-Proxy": "token"},
        "timeout": 23,
    }


def test_message_image_options_extra_body_headers_and_tools_mapping():
    captured = {}
    model_config = config(
        extra_headers={"X-Proxy": "token"},
        extra_body={"options": {"seed": 7}, "keep_alive": "5m"},
    )

    def handler(request):
        captured["request"] = request
        return ndjson_response(
            {"message": {"thinking": "inspect ", "content": ""}, "done": False},
            {"message": {"thinking": "screen", "content": ""}, "done": False},
            {
                "message": {"content": "do(action='Back')"},
                "done": True,
            },
        )

    client = mock_client(handler, model_config)
    adapter = OllamaAdapter(model_config, client=client)
    messages = [
        {"role": "system", "content": "system"},
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

    request = captured["request"]
    body = json.loads(request.content)
    assert request.url.path == "/api/chat"
    assert request.headers["x-proxy"] == "token"
    assert body["model"] == "vision-model"
    assert body["messages"] == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "look", "images": ["abc123"]},
    ]
    assert body["options"] == {
        "seed": 7,
        "num_predict": 2048,
        "temperature": 0.0,
        "top_p": 0.85,
    }
    assert body["keep_alive"] == "5m"
    assert [tool["function"]["name"] for tool in body["tools"]] == [
        "phone_action",
        "finish",
    ]
    assert output.thinking == "inspect screen"
    assert output.final_text == "do(action='Back')"
    assert output.raw_content == "inspect screendo(action='Back')"
    assert output.time_to_first_token is not None
    assert output.time_to_thinking_end is not None


def test_tool_arguments_support_object_and_string_fragments():
    model_config = config()

    def handler(request):
        return ndjson_response(
            {
                "message": {
                    "tool_calls": [
                        {
                            "index": 0,
                            "function": {
                                "name": "phone_action",
                                "arguments": {"action": "Back"},
                            },
                        },
                        {
                            "index": 1,
                            "function": {
                                "name": "finish",
                                "arguments": '{"message":',
                            },
                        },
                    ]
                },
                "done": False,
            },
            {
                "message": {
                    "tool_calls": [
                        {
                            "index": 1,
                            "function": {
                                "name": "finish",
                                "arguments": '"done"}',
                            },
                        }
                    ]
                },
                "done": True,
            },
        )

    adapter = OllamaAdapter(model_config, client=mock_client(handler, model_config))

    output = adapter.request([], use_tools=True)

    assert output.tool_calls == [
        RawToolCall("phone_action", {"action": "Back"}),
        RawToolCall("finish", '{"message":"done"}'),
    ]


def test_no_index_calls_in_different_chunks_remain_independent_when_identical():
    model_config = config()

    def handler(request):
        call = {
            "function": {
                "name": "phone_action",
                "arguments": {"action": "Back"},
            }
        }
        return ndjson_response(
            {"message": {"tool_calls": [call]}, "done": False},
            {"message": {"tool_calls": [call]}, "done": True},
        )

    adapter = OllamaAdapter(model_config, client=mock_client(handler, model_config))

    output = adapter.request([], use_tools=True)

    assert output.tool_calls == [
        RawToolCall("phone_action", {"action": "Back"}),
        RawToolCall("phone_action", {"action": "Back"}),
    ]


def test_no_index_calls_in_different_chunks_remain_independent_when_different():
    model_config = config()

    def handler(request):
        return ndjson_response(
            {
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "phone_action",
                                "arguments": {"action": "Back"},
                            }
                        }
                    ]
                },
                "done": False,
            },
            {
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "finish",
                                "arguments": {"message": "done"},
                            }
                        }
                    ]
                },
                "done": True,
            },
        )

    adapter = OllamaAdapter(model_config, client=mock_client(handler, model_config))

    output = adapter.request([], use_tools=True)

    assert output.tool_calls == [
        RawToolCall("phone_action", {"action": "Back"}),
        RawToolCall("finish", {"message": "done"}),
    ]


def test_multiple_no_index_calls_in_one_chunk_preserve_arrival_order():
    model_config = config()

    def handler(request):
        return ndjson_response(
            {
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "phone_action",
                                "arguments": {"action": "Home"},
                            }
                        },
                        {
                            "function": {
                                "name": "finish",
                                "arguments": {"message": "done"},
                            }
                        },
                    ]
                },
                "done": True,
            }
        )

    adapter = OllamaAdapter(model_config, client=mock_client(handler, model_config))

    output = adapter.request([], use_tools=True)

    assert output.tool_calls == [
        RawToolCall("phone_action", {"action": "Home"}),
        RawToolCall("finish", {"message": "done"}),
    ]


def test_text_mode_omits_tools_and_uses_explicit_sampling_values():
    captured = {}
    model_config = config(temperature=0.4, top_p=0.6)

    def handler(request):
        captured["body"] = json.loads(request.content)
        return ndjson_response(
            {"message": {"content": "finish(message='done')"}, "done": True}
        )

    adapter = OllamaAdapter(model_config, client=mock_client(handler, model_config))
    adapter.request([], use_tools=False)

    assert "tools" not in captured["body"]
    assert captured["body"]["options"]["temperature"] == 0.4
    assert captured["body"]["options"]["top_p"] == 0.6


def test_http_tools_error_never_becomes_unsupported_tools_error():
    model_config = config()

    def handler(request):
        return httpx.Response(400, json={"error": "tools are unsupported"})

    adapter = OllamaAdapter(model_config, client=mock_client(handler, model_config))

    with pytest.raises(ModelRequestError) as error:
        adapter.request([], use_tools=True)

    assert not isinstance(error.value, UnsupportedToolsError)
    assert "tools are unsupported" not in str(error.value)


def test_auto_mode_does_not_fallback_when_tools_rejected_at_facade():
    """Freeze the asymmetric auto-mode behavior: Ollama never raises
    UnsupportedToolsError, so ModelClient cannot fall back to text."""

    model_config = config(tool_mode="auto")
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(400, json={"error": "tools are unsupported"})

    adapter = OllamaAdapter(model_config, client=mock_client(handler, model_config))
    client = ModelClient(model_config, adapter=adapter)

    with pytest.raises(ModelRequestError) as error:
        client.request([])

    assert not isinstance(error.value, UnsupportedToolsError)
    # Exactly one request (with tools); no text-mode retry occurred.
    assert len(requests) == 1
    assert requests[0]["tools"] is not None


@pytest.mark.parametrize(
    "content",
    [
        b'{"message":{"content":"truncated"}\n',
        b'[]\n',
        b'{"message":[],"done":true}\n',
        b'{"message":{"tool_calls":{}},"done":true}\n',
        b'{"message":{},"done":"yes"}\n',
        b'{"message":{"content":"partial"},"done":false}\n',
    ],
)
def test_invalid_ndjson_stream_fails_closed(content):
    model_config = config()

    def handler(request):
        return httpx.Response(200, content=content)

    adapter = OllamaAdapter(model_config, client=mock_client(handler, model_config))

    with pytest.raises(ModelResponseError):
        adapter.request([], use_tools=True)


def test_transport_error_is_normalized_without_leaking_details():
    model_config = config()

    def handler(request):
        raise httpx.ConnectError("secret-host-detail", request=request)

    adapter = OllamaAdapter(model_config, client=mock_client(handler, model_config))

    with pytest.raises(ModelConnectionError) as error:
        adapter.request([], use_tools=False)

    assert "secret-host-detail" not in str(error.value)
    assert_secret_not_chained(error.value)


def test_health_check_finds_model_and_uses_tags_endpoint():
    captured = {}
    model_config = config(extra_headers={"X-Proxy": "token"})

    def handler(request):
        captured["request"] = request
        return httpx.Response(
            200,
            json={"models": [{"name": "other"}, {"model": "vision-model"}]},
        )

    adapter = OllamaAdapter(model_config, client=mock_client(handler, model_config))

    adapter.check_connection()

    assert captured["request"].url.path == "/api/tags"
    assert captured["request"].headers["x-proxy"] == "token"


def test_health_check_missing_model_suggests_ollama_pull():
    model_config = config()

    def handler(request):
        return httpx.Response(200, json={"models": [{"name": "other"}]})

    adapter = OllamaAdapter(model_config, client=mock_client(handler, model_config))

    with pytest.raises(ModelConnectionError) as error:
        adapter.check_connection()

    assert "vision-model" in str(error.value)
    assert "ollama pull vision-model" in str(error.value)


def test_health_transport_error_suppresses_original_exception_chain():
    model_config = config()

    def handler(request):
        raise httpx.ConnectError("secret-host-detail", request=request)

    adapter = OllamaAdapter(model_config, client=mock_client(handler, model_config))

    with pytest.raises(ModelConnectionError) as error:
        adapter.check_connection()

    assert_secret_not_chained(error.value)


def test_health_http_error_is_connection_error():
    model_config = config()

    def handler(request):
        return httpx.Response(503, json={"error": "unavailable"})

    adapter = OllamaAdapter(model_config, client=mock_client(handler, model_config))

    with pytest.raises(ModelConnectionError, match="HTTP 503"):
        adapter.check_connection()


def test_close_is_idempotent_and_closed_adapter_rejects_operations():
    model_config = config()
    client = mock_client(lambda request: ndjson_response(), model_config)
    adapter = OllamaAdapter(model_config, client=client)

    adapter.close()
    adapter.close()

    assert client.is_closed
    with pytest.raises(ModelRequestError, match="closed"):
        adapter.request([], use_tools=False)
    with pytest.raises(ModelConnectionError, match="closed"):
        adapter.check_connection()


def test_ollama_streaming_events():
    model_config = config()
    response = ndjson_response(
        {"message": {"thinking": "ollama thinking 1 "}},
        {"message": {"thinking": "ollama thinking 2"}},
        {"message": {"content": "do(action="}},
        {"message": {"content": "'Back')"}},
        {"done": True},
    )
    client = mock_client(lambda request: response, model_config)
    adapter = OllamaAdapter(model_config, client=client)
    events: list[ModelStreamEvent] = []

    output = adapter.request([], use_tools=False, on_event=events.append)

    assert output.thinking == "ollama thinking 1 ollama thinking 2"
    assert output.final_text == "do(action='Back')"
    assert events == [
        ThinkingDelta("ollama thinking 1 "),
        ThinkingDelta("ollama thinking 2"),
        ContentDelta("do(action="),
        ContentDelta("'Back')"),
    ]

