"""Tests for the provider-neutral ModelClient facade."""

import builtins
from collections import deque
from typing import Any, cast

import pytest

from phone_agent.model.base import (
    ModelConfigurationError,
    ModelConnectionError,
    ModelRequestError,
    ModelStreamEvent,
    RawModelOutput,
    StreamCompleted,
    ThinkingDelta,
    UnsupportedToolsError,
)
from phone_agent.model.client import ModelClient, ModelConfig


class FakeAdapter:
    def __init__(self, *results, close_error=None, emit_thinking=None):
        self.results = deque(results)
        self.requests = []
        self.connection_checks = 0
        self.close_calls = 0
        self.close_error = close_error
        self.emit_thinking = emit_thinking

    def request(self, messages, *, use_tools, on_event=None):
        self.requests.append((messages, use_tools))
        if on_event is not None and self.emit_thinking:
            on_event(ThinkingDelta(self.emit_thinking))
        result = self.results.popleft()
        if isinstance(result, BaseException):
            raise result
        return result

    def check_connection(self):
        self.connection_checks += 1

    def close(self):
        self.close_calls += 1
        if self.close_error is not None:
            error = self.close_error
            self.close_error = None
            raise error


def output(action="do(action='Back')"):
    return RawModelOutput(
        thinking="provider thinking",
        final_text=action,
        raw_content="raw provider payload",
        time_to_first_token=0.1,
        time_to_thinking_end=0.2,
        total_time=0.3,
    )


@pytest.mark.parametrize(
    ("tool_mode", "expected_use_tools"),
    [("native", True), ("text", False)],
)
def test_native_and_text_modes_make_one_request(tool_mode, expected_use_tools):
    adapter = FakeAdapter(output())
    client = ModelClient(ModelConfig(tool_mode=tool_mode), adapter=adapter)
    messages = [{"role": "user", "content": "screen"}]

    response = client.request(messages)

    assert adapter.requests == [(messages, expected_use_tools)]
    assert response.thinking == "provider thinking"
    assert response.action == "do(action='Back')"
    assert response.raw_content == "raw provider payload"
    assert response.time_to_first_token == 0.1
    assert response.time_to_thinking_end == 0.2
    assert response.total_time == 0.3
    assert response.parsed_action == {"_metadata": "do", "action": "Back"}


def test_auto_mode_uses_tools_without_retry_when_supported():
    adapter = FakeAdapter(output())
    client = ModelClient(ModelConfig(tool_mode="auto"), adapter=adapter)

    client.request([])

    assert [use_tools for _, use_tools in adapter.requests] == [True]


def test_auto_mode_retries_once_without_tools_only_for_unsupported_tools():
    adapter = FakeAdapter(UnsupportedToolsError("unsupported"), output())
    client = ModelClient(ModelConfig(tool_mode="auto"), adapter=adapter)

    response = client.request([])

    assert response.action == "do(action='Back')"
    assert [use_tools for _, use_tools in adapter.requests] == [True, False]


def test_auto_fallback_metrics_include_failed_first_attempt(monkeypatch):
    adapter = FakeAdapter(UnsupportedToolsError("unsupported"), output())
    client = ModelClient(ModelConfig(tool_mode="auto"), adapter=adapter)
    timestamps = iter((10.0, 12.0))
    monkeypatch.setattr(
        "phone_agent.model.client.time.monotonic",
        lambda: next(timestamps),
    )

    response = client.request([])

    assert response.time_to_first_token == pytest.approx(2.1)
    assert response.time_to_thinking_end == pytest.approx(2.2)
    assert response.total_time == pytest.approx(2.3)


def test_auto_mode_does_not_retry_other_request_errors():
    adapter = FakeAdapter(ModelRequestError("failed"), output())
    client = ModelClient(ModelConfig(tool_mode="auto"), adapter=adapter)

    with pytest.raises(ModelRequestError, match="failed"):
        client.request([])

    assert [use_tools for _, use_tools in adapter.requests] == [True]


def test_native_mode_does_not_fallback_when_tools_are_unsupported():
    adapter = FakeAdapter(UnsupportedToolsError("unsupported"), output())
    client = ModelClient(ModelConfig(tool_mode="native"), adapter=adapter)

    with pytest.raises(UnsupportedToolsError):
        client.request([])

    assert [use_tools for _, use_tools in adapter.requests] == [True]


def test_connection_check_and_close_are_delegated_and_close_is_idempotent():
    adapter = FakeAdapter(output())
    client = ModelClient(adapter=adapter)

    client.check_connection()
    client.close()
    client.close()

    assert adapter.connection_checks == 1
    assert adapter.close_calls == 1
    with pytest.raises(ModelRequestError, match="closed"):
        client.request([])
    with pytest.raises(ModelConnectionError, match="closed"):
        client.check_connection()


def test_close_can_be_retried_after_adapter_close_failure():
    adapter = FakeAdapter(output(), close_error=RuntimeError("close failed"))
    client = ModelClient(adapter=adapter)

    with pytest.raises(RuntimeError, match="close failed"):
        client.close()

    client.close()
    client.close()
    assert adapter.close_calls == 2


def test_default_factory_reports_missing_adapter_only_on_client_construction(
    monkeypatch,
):
    config = ModelConfig()
    original_import = builtins.__import__

    def import_without_openai_adapter(name, *args, **kwargs):
        if name == "phone_agent.model.openai_compatible":
            raise ImportError("adapter intentionally unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_openai_adapter)

    with pytest.raises(ModelConfigurationError, match="provider 'openai'.*not available"):
        ModelClient(config)


def test_model_client_emits_stream_events_and_completion():
    adapter = FakeAdapter(output(), emit_thinking="deep thoughts")
    client = ModelClient(adapter=adapter)
    events: list[ModelStreamEvent] = []

    response = client.request([{"role": "user", "content": "hello"}], on_event=events.append)

    assert response.action == "do(action='Back')"
    assert len(events) == 2
    assert events[0] == ThinkingDelta("deep thoughts")
    assert isinstance(events[1], StreamCompleted)
    assert events[1].time_to_first_token == 0.1
    assert events[1].total_time == 0.3


def test_model_client_adapter_with_kwargs_and_legacy_signature():
    class KwargsAdapter:
        def __init__(self):
            self.received_on_event = False

        def request(self, messages: Any, *, use_tools: bool = False, **kwargs: Any) -> RawModelOutput:
            _ = (messages, use_tools)
            if "on_event" in kwargs and kwargs["on_event"] is not None:
                self.received_on_event = True
                kwargs["on_event"](ThinkingDelta("from kwargs adapter"))
            return output()

        def check_connection(self):
            pass

        def close(self):
            pass

    kwargs_adapter = KwargsAdapter()
    client = ModelClient(adapter=cast(Any, kwargs_adapter))
    events: list[ModelStreamEvent] = []
    client.request([{"role": "user", "content": "hi"}], on_event=events.append)
    assert kwargs_adapter.received_on_event is True
    assert events[0] == ThinkingDelta("from kwargs adapter")

    class StrictLegacyAdapter:
        def request(self, messages: Any, *, use_tools: bool = False) -> RawModelOutput:
            _ = (messages, use_tools)
            return output()

        def check_connection(self):
            pass

        def close(self):
            pass

    legacy_adapter = StrictLegacyAdapter()
    client2 = ModelClient(adapter=cast(Any, legacy_adapter))
    events2: list[ModelStreamEvent] = []
    resp2 = client2.request([{"role": "user", "content": "hi"}], on_event=events2.append)
    assert resp2.action == "do(action='Back')"
    assert len(events2) == 1
    assert isinstance(events2[0], StreamCompleted)

