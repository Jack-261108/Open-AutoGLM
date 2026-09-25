"""Offline model-client ownership tests shared by Android and iOS agents."""

from types import SimpleNamespace

import pytest

import phone_agent.agent as android_module
import phone_agent.agent_ios as ios_module
from phone_agent.agent import AgentConfig, PhoneAgent
from phone_agent.agent_ios import IOSAgentConfig, IOSPhoneAgent


_MISSING = object()


class OwnedClient:
    def __init__(self, response=None, close_error=None):
        self.response = response
        self.close_error = close_error
        self.request_calls = 0
        self.close_calls = 0

    def request(self, messages):
        self.request_calls += 1
        return self.response

    def close(self):
        self.close_calls += 1
        if self.close_error is not None:
            error = self.close_error
            self.close_error = None
            raise error


class InjectedClosableClient(OwnedClient):
    pass


class RequestOnlyClient:
    def __init__(self, response):
        self.response = response
        self.request_calls = 0

    def request(self, messages):
        self.request_calls += 1
        return self.response


@pytest.fixture(params=("android", "ios"))
def platform(request):
    return request.param


@pytest.fixture
def build_agent(monkeypatch, screenshot_factory, fake_action_handler):
    def build(platform, *, injected=_MISSING, owned=None):
        if platform == "android":
            screenshot = screenshot_factory("offline-image")
            device = SimpleNamespace(
                get_screenshot=lambda device_id=None: screenshot,
                get_current_app=lambda device_id=None: "FakeApp",
            )
            monkeypatch.setattr(android_module, "get_device_factory", lambda: device)
            monkeypatch.setattr(
                android_module,
                "ActionHandler",
                lambda **kwargs: fake_action_handler,
            )
            if owned is not None:
                monkeypatch.setattr(
                    android_module,
                    "ModelClient",
                    lambda config, verbose: owned,
                )
            kwargs = {}
            if injected is not _MISSING:
                kwargs["model_client"] = injected
            return PhoneAgent(
                agent_config=AgentConfig(
                    system_prompt="system prompt",
                    verbose=False,
                ),
                **kwargs,
            )

        screenshot = screenshot_factory("offline-image")
        connection = SimpleNamespace(
            start_wda_session=lambda: pytest.fail(
                "existing session_id must avoid creating a WDA session"
            )
        )
        monkeypatch.setattr(ios_module, "get_screenshot", lambda **kwargs: screenshot)
        monkeypatch.setattr(
            ios_module,
            "get_current_app",
            lambda **kwargs: "FakeIOSApp",
        )
        monkeypatch.setattr(
            ios_module,
            "XCTestConnection",
            lambda wda_url: connection,
        )
        monkeypatch.setattr(
            ios_module,
            "IOSActionHandler",
            lambda **kwargs: fake_action_handler,
        )
        if owned is not None:
            monkeypatch.setattr(
                ios_module,
                "ModelClient",
                lambda config, verbose: owned,
            )
        kwargs = {}
        if injected is not _MISSING:
            kwargs["model_client"] = injected
        return IOSPhoneAgent(
            agent_config=IOSAgentConfig(
                wda_url="http://wda.invalid",
                session_id="existing-session",
                system_prompt="system prompt",
                verbose=False,
            ),
            **kwargs,
        )

    return build


def test_internally_created_model_client_is_closed_once(
    platform,
    build_agent,
):
    client = OwnedClient()
    agent = build_agent(platform, owned=client)

    agent.close()
    agent.close()

    assert client.close_calls == 1


def test_owned_model_client_close_failure_can_be_retried(
    platform,
    build_agent,
):
    client = OwnedClient(close_error=RuntimeError("close failed"))
    agent = build_agent(platform, owned=client)

    with pytest.raises(RuntimeError, match="close failed"):
        agent.close()

    agent.close()
    agent.close()
    assert client.close_calls == 2


def test_injected_client_is_never_closed_even_when_it_has_close(
    platform,
    build_agent,
):
    client = InjectedClosableClient()
    agent = build_agent(platform, injected=client)

    agent.close()
    agent.close()

    assert client.close_calls == 0


def test_request_only_injected_client_is_usable(
    platform,
    build_agent,
    response_factory,
    fake_action_handler,
):
    client = RequestOnlyClient(
        response_factory(parsed_action={"_metadata": "do", "action": "Back"})
    )
    agent = build_agent(platform, injected=client)

    result = agent.step("offline task")
    agent.close()

    assert result.success is True
    assert client.request_calls == 1
    assert fake_action_handler.calls[0][0] == {
        "_metadata": "do",
        "action": "Back",
    }


@pytest.mark.parametrize("config_class", [AgentConfig, IOSAgentConfig])
@pytest.mark.parametrize("max_steps", [0, -1, True])
def test_agent_config_rejects_non_positive_max_steps(config_class, max_steps):
    with pytest.raises(ValueError, match="max_steps must be a positive integer"):
        config_class(max_steps=max_steps)


def test_ios_initialization_failure_does_not_create_or_close_model_client(monkeypatch):
    created_clients = []
    injected = InjectedClosableClient()

    def fail_connection(wda_url):
        raise RuntimeError("WDA init failed")

    monkeypatch.setattr(ios_module, "XCTestConnection", fail_connection)
    monkeypatch.setattr(
        ios_module,
        "ModelClient",
        lambda config, verbose: created_clients.append((config, verbose)),
    )

    with pytest.raises(RuntimeError, match="WDA init failed"):
        IOSPhoneAgent(
            agent_config=IOSAgentConfig(
                session_id="existing-session",
                system_prompt="system prompt",
            )
        )
    assert created_clients == []

    with pytest.raises(RuntimeError, match="WDA init failed"):
        IOSPhoneAgent(
            agent_config=IOSAgentConfig(
                session_id="existing-session",
                system_prompt="system prompt",
            ),
            model_client=injected,
        )
    assert injected.close_calls == 0
