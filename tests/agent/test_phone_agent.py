"""Offline behavior tests for the Android PhoneAgent."""

from types import SimpleNamespace

import pytest

import phone_agent.agent as agent_module
from phone_agent.agent import AgentConfig, PhoneAgent
from phone_agent.device_factory import DeviceType


@pytest.fixture
def build_agent(monkeypatch, fake_action_handler, screenshot_factory):
    def build(
        client,
        *,
        screenshots=("screen-1",),
        apps=None,
        verbose=False,
        fallback=False,
    ):
        shots = []
        for value in screenshots:
            shot = screenshot_factory(value)
            shot.is_fallback = fallback
            shots.append(shot)
        screenshot_values = iter(shots)
        app_values = iter(apps or ["FakeApp"] * len(screenshots))
        device = SimpleNamespace(
            get_screenshot=lambda device_id=None: next(screenshot_values),
            get_current_app=lambda device_id=None: next(app_values),
        )
        monkeypatch.setattr(agent_module, "get_device_factory", lambda: device)
        monkeypatch.setattr(
            agent_module,
            "ActionHandler",
            lambda **kwargs: fake_action_handler,
        )
        agent = PhoneAgent(
            agent_config=AgentConfig(
                system_prompt="system prompt",
                verbose=verbose,
            ),
            model_client=client,
        )
        return agent, fake_action_handler

    return build


def test_parsed_action_has_priority_and_history_stays_xml(
    monkeypatch,
    build_agent,
    fake_model_client_factory,
    response_factory,
):
    parsed_action = {"_metadata": "do", "action": "Back"}
    client = fake_model_client_factory(
        response_factory(
            thinking="inspect screen",
            action="not valid legacy DSL",
            parsed_action=parsed_action,
        )
    )
    monkeypatch.setattr(
        agent_module,
        "parse_action",
        lambda action: pytest.fail("parsed_action must bypass string parsing"),
    )
    agent, handler = build_agent(client)

    result = agent.step("go back")

    assert result.success is True
    assert result.action == parsed_action
    assert handler.calls == [(parsed_action, 1080, 2400)]
    assert agent.context[-1] == {
        "role": "assistant",
        "content": (
            "<think>inspect screen</think>"
            "<answer>not valid legacy DSL</answer>"
        ),
    }


def test_legacy_response_without_parsed_action_uses_dsl_parser(
    monkeypatch,
    build_agent,
    fake_model_client_factory,
    response_factory,
):
    real_parse_action = agent_module.parse_action
    parsed_strings = []

    def parse_spy(action):
        parsed_strings.append(action)
        return real_parse_action(action)

    monkeypatch.setattr(agent_module, "parse_action", parse_spy)
    client = fake_model_client_factory(
        response_factory(
            thinking="legacy thinking",
            action="do(action='Home')",
            parsed_action=None,
        )
    )
    agent, handler = build_agent(client)

    result = agent.step("go home")

    assert parsed_strings == ["do(action='Home')"]
    assert result.action == {"_metadata": "do", "action": "Home"}
    assert handler.calls[0][0] == result.action
    assert agent.context[-1]["content"] == (
        "<think>legacy thinking</think><answer>do(action='Home')</answer>"
    )


def test_invalid_action_fails_before_handler_without_fake_finish(
    monkeypatch,
    build_agent,
    fake_model_client_factory,
    response_factory,
):
    monkeypatch.setattr(
        agent_module,
        "finish",
        lambda **kwargs: pytest.fail("invalid model actions must not become finish actions"),
    )
    client = fake_model_client_factory(
        response_factory(action="do(action='Unknown')", parsed_action=None)
    )
    agent, handler = build_agent(client)

    result = agent.step("invalid action")

    assert result.success is False
    assert result.finished is True
    assert result.action is None
    assert result.message.startswith("Model action parse error:")
    assert handler.calls == []
    assert all(message["role"] != "assistant" for message in agent.context)


def test_model_error_removes_image_and_next_request_has_only_latest_screenshot(
    build_agent,
    fake_model_client_factory,
    response_factory,
    image_urls,
):
    client = fake_model_client_factory(
        RuntimeError("model unavailable"),
        response_factory(parsed_action={"_metadata": "do", "action": "Back"}),
    )
    agent, handler = build_agent(client, screenshots=("old-image", "latest-image"))

    first_result = agent.step("try task")

    assert first_result.success is False
    assert first_result.message == "Model error: model unavailable"
    assert image_urls(agent.context) == []

    second_result = agent.step()

    assert second_result.success is True
    assert handler.calls[0][0] == {"_metadata": "do", "action": "Back"}
    assert image_urls(client.requests[0]) == [
        "data:image/png;base64,old-image"
    ]
    assert image_urls(client.requests[1]) == [
        "data:image/png;base64,latest-image"
    ]
    assert image_urls(agent.context) == []


def test_verbose_false_prints_no_thinking_action_or_debug_response(
    build_agent,
    fake_model_client_factory,
    response_factory,
    capsys,
):
    client = fake_model_client_factory(
        response_factory(
            thinking="SECRET THINKING",
            action="do(action='Back')",
            parsed_action={"_metadata": "do", "action": "Back"},
            raw_content="SECRET DEBUG RESPONSE",
        )
    )
    agent, _ = build_agent(client, verbose=False)

    agent.step("quiet task")

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_observation_injected_into_next_turn_and_cleared_afterwards(
    build_agent,
    fake_model_client_factory,
    response_factory,
):
    client = fake_model_client_factory(
        response_factory(
            parsed_action={"_metadata": "do", "action": "Interact", "message": "Choose option"},
        ),
        response_factory(
            parsed_action={"_metadata": "do", "action": "Back"},
        ),
        response_factory(
            parsed_action={"_metadata": "finish", "message": "Done"},
        ),
    )
    agent, handler = build_agent(
        client, screenshots=("screen-1", "screen-2", "screen-3")
    )
    handler.result = SimpleNamespace(
        success=True,
        should_finish=False,
        message="Interact handled",
        observation="User choice: Option A",
    )

    step1 = agent.step("choose something")
    assert step1.observation == "User choice: Option A"

    # For step 2, handler produces no observation
    handler.result = SimpleNamespace(
        success=True,
        should_finish=False,
        message=None,
        observation=None,
    )
    step2 = agent.step()
    assert step2.observation is None

    # Verify that in step 2 request, observation is present in text content
    step2_user_msg = client.requests[1][-1]
    step2_text = [
        item["text"] for item in step2_user_msg["content"] if item.get("type") == "text"
    ][0]
    assert "** Previous Action Observation **\nUser choice: Option A" in step2_text

    # In step 3, observation should have been consumed/cleared and not injected again
    step3 = agent.step()
    assert step3.finished is True
    step3_user_msg = client.requests[2][-1]
    step3_text = [
        item["text"] for item in step3_user_msg["content"] if item.get("type") == "text"
    ][0]
    assert "** Previous Action Observation **" not in step3_text


def test_reset_clears_observation_and_notes(
    build_agent,
    fake_model_client_factory,
    response_factory,
):
    client = fake_model_client_factory(
        response_factory(parsed_action={"_metadata": "do", "action": "Interact"}),
        response_factory(parsed_action={"_metadata": "do", "action": "Back"}),
    )
    agent, handler = build_agent(client, screenshots=("screen-1", "screen-2"))
    handler.result = SimpleNamespace(
        success=True,
        should_finish=False,
        message=None,
        observation="User choice: 1",
    )

    agent.step("first step")
    assert agent._last_observation == "User choice: 1"

    agent.reset()
    assert agent._last_observation is None
    assert agent.context == []


def test_run_drops_previous_observation_and_notes(
    build_agent,
    fake_model_client_factory,
    response_factory,
):
    client = fake_model_client_factory(
        response_factory(parsed_action={"_metadata": "do", "action": "Back"}),
        response_factory(parsed_action={"_metadata": "finish", "message": "done"}),
    )
    agent, handler = build_agent(client, screenshots=("screen-1", "screen-2"))
    agent._last_observation = "stale observation"
    handler.notes = [{"message": "stale note"}]
    handler.clear_notes = handler.notes.clear

    result = agent.run("fresh task")

    assert result == "done"
    assert handler.notes == []
    step2_user_msg = client.requests[1][-1]
    step2_text = [
        item["text"] for item in step2_user_msg["content"] if item.get("type") == "text"
    ][0]
    assert "stale observation" not in step2_text
    assert "** Previous Action Observation **" not in step2_text


def _user_text(message):
    return [
        item["text"] for item in message["content"] if item.get("type") == "text"
    ][0]


def test_hdc_agent_config_does_not_use_global_factory(
    monkeypatch, fake_model_client_factory
):
    monkeypatch.setattr(
        agent_module,
        "get_device_factory",
        lambda: pytest.fail("HDC config must not use the global factory"),
    )
    agent = PhoneAgent(
        agent_config=AgentConfig(
            device_type=DeviceType.HDC,
            system_prompt="system prompt",
            verbose=False,
        ),
        model_client=fake_model_client_factory(),
    )

    assert agent.device_factory.device_type == DeviceType.HDC


def test_phone_agent_ios_creates_wda_session_when_missing(
    monkeypatch, fake_model_client_factory
):
    created: dict[str, object] = {}

    class FakeConn:
        def __init__(self, wda_url):
            created["url"] = wda_url

        def start_wda_session(self):
            created["started"] = True
            return True, "session-created"

    monkeypatch.setattr("phone_agent.xctest.XCTestConnection", FakeConn)
    agent = PhoneAgent(
        agent_config=AgentConfig(
            device_type=DeviceType.IOS,
            wda_url="http://wda.example:8100",
            system_prompt="system prompt",
            verbose=False,
        ),
        model_client=fake_model_client_factory(),
    )

    assert created["url"] == "http://wda.example:8100"
    assert created["started"] is True
    assert agent.agent_config.session_id == "session-created"
    assert agent.device_factory.session_id == "session-created"

