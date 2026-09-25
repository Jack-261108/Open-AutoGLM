"""Offline tests for CLI entrypoint model-client lifecycle."""

from pathlib import Path
from types import SimpleNamespace

import pytest

import ios as ios_entry
import main as main_entry
from phone_agent.model import ModelConfigurationError


MODEL_ENVIRONMENT = (
    "PHONE_AGENT_PROVIDER",
    "PHONE_AGENT_TOOL_MODE",
    "PHONE_AGENT_BASE_URL",
    "PHONE_AGENT_MODEL",
    "PHONE_AGENT_API_KEY",
)


@pytest.fixture(autouse=True)
def clear_model_environment(monkeypatch):
    for name in MODEL_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)


class FakeModelClient:
    def __init__(self, config, verbose, events, check_error=None):
        self.config = config
        self.verbose = verbose
        self.events = events
        self.check_error = check_error
        events.append("client.create")

    def check_connection(self):
        self.events.append("client.check")
        if self.check_error is not None:
            raise self.check_error

    def close(self):
        self.events.append("client.close")


class FakeAgent:
    def __init__(self, events, run_error=None):
        self.events = events
        self.run_error = run_error

    def run(self, task):
        self.events.append(("agent.run", task))
        if self.run_error is not None:
            raise self.run_error
        return "done"

    def reset(self):
        self.events.append("agent.reset")

    def close(self):
        self.events.append("agent.close")


def prepare_entrypoint(
    monkeypatch,
    entrypoint,
    *,
    check_error=None,
    constructor_error=None,
    run_error=None,
):
    events = []
    created = {}

    monkeypatch.setattr(entrypoint, "check_system_requirements", lambda *a, **k: True)
    monkeypatch.setattr(entrypoint, "handle_device_commands", lambda args: False)

    if entrypoint is main_entry:
        monkeypatch.setattr(entrypoint, "set_device_type", lambda device_type: None)
        monkeypatch.setattr(
            entrypoint,
            "get_device_factory",
            lambda: SimpleNamespace(list_devices=lambda: []),
        )
        agent_name = "PhoneAgent"
    else:
        monkeypatch.setattr(entrypoint, "list_devices", lambda: [])
        agent_name = "IOSPhoneAgent"

    def create_client(config, verbose):
        client = FakeModelClient(config, verbose, events, check_error=check_error)
        created["client"] = client
        return client

    def create_agent(*, model_config, agent_config, model_client):
        events.append("agent.create")
        created["agent_kwargs"] = {
            "model_config": model_config,
            "agent_config": agent_config,
            "model_client": model_client,
        }
        if constructor_error is not None:
            raise constructor_error
        agent = FakeAgent(events, run_error=run_error)
        created["agent"] = agent
        return agent

    monkeypatch.setattr(entrypoint, "ModelClient", create_client)
    monkeypatch.setattr(entrypoint, agent_name, create_agent)
    return events, created


def run_entrypoint(entrypoint, extra_args=None):
    args = [
        "--base-url",
        "https://models.example/v1",
        "--model",
        "test-model",
    ]
    if extra_args is None:
        args.append("test task")
    else:
        args.extend(extra_args)
    entrypoint.main(args)


@pytest.mark.parametrize("entrypoint", [main_entry, ios_entry])
def test_normal_run_injects_the_same_client_and_closes_in_order(
    monkeypatch, entrypoint
):
    events, created = prepare_entrypoint(monkeypatch, entrypoint)

    run_entrypoint(entrypoint)

    assert created["agent_kwargs"]["model_client"] is created["client"]
    assert created["agent_kwargs"]["model_config"] is created["client"].config
    assert created["client"].verbose is True
    assert events == [
        "client.create",
        "client.check",
        "agent.create",
        ("agent.run", "test task"),
        "agent.close",
        "client.close",
    ]


@pytest.mark.parametrize("entrypoint", [main_entry, ios_entry])
def test_health_check_failure_closes_client(monkeypatch, entrypoint):
    events, _ = prepare_entrypoint(
        monkeypatch,
        entrypoint,
        check_error=RuntimeError("health failed"),
    )

    with pytest.raises(RuntimeError, match="health failed"):
        run_entrypoint(entrypoint)

    assert events == ["client.create", "client.check", "client.close"]


@pytest.mark.parametrize("entrypoint", [main_entry, ios_entry])
def test_agent_construction_failure_closes_client(monkeypatch, entrypoint):
    events, _ = prepare_entrypoint(
        monkeypatch,
        entrypoint,
        constructor_error=RuntimeError("agent failed"),
    )

    with pytest.raises(RuntimeError, match="agent failed"):
        run_entrypoint(entrypoint)

    assert events == [
        "client.create",
        "client.check",
        "agent.create",
        "client.close",
    ]


@pytest.mark.parametrize("entrypoint", [main_entry, ios_entry])
def test_run_failure_closes_agent_before_client(monkeypatch, entrypoint):
    events, _ = prepare_entrypoint(
        monkeypatch,
        entrypoint,
        run_error=RuntimeError("run failed"),
    )

    with pytest.raises(RuntimeError, match="run failed"):
        run_entrypoint(entrypoint)

    assert events[-3:] == [
        ("agent.run", "test task"),
        "agent.close",
        "client.close",
    ]


@pytest.mark.parametrize("entrypoint", [main_entry, ios_entry])
def test_keyboard_interrupt_closes_agent_before_client(monkeypatch, entrypoint):
    events, _ = prepare_entrypoint(
        monkeypatch,
        entrypoint,
        run_error=KeyboardInterrupt(),
    )

    with pytest.raises(KeyboardInterrupt):
        run_entrypoint(entrypoint)

    assert events[-3:] == [
        ("agent.run", "test task"),
        "agent.close",
        "client.close",
    ]


@pytest.mark.parametrize("entrypoint", [main_entry, ios_entry])
def test_no_task_enters_interactive_mode(monkeypatch, entrypoint, capsys):
    events, _ = prepare_entrypoint(monkeypatch, entrypoint)
    monkeypatch.setattr("builtins.input", lambda prompt: "quit")

    run_entrypoint(entrypoint, extra_args=[])

    assert "Entering interactive mode" in capsys.readouterr().out
    assert not any(isinstance(event, tuple) and event[0] == "agent.run" for event in events)
    assert events[-2:] == ["agent.close", "client.close"]


@pytest.mark.parametrize("entrypoint", [main_entry, ios_entry])
def test_interactive_eof_exits_and_closes_resources(monkeypatch, entrypoint):
    events, _ = prepare_entrypoint(monkeypatch, entrypoint)

    def end_of_input(prompt):
        raise EOFError

    monkeypatch.setattr("builtins.input", end_of_input)
    run_entrypoint(entrypoint, extra_args=[])

    assert events[-2:] == ["agent.close", "client.close"]


@pytest.mark.parametrize("entrypoint", [main_entry, ios_entry])
def test_interactive_run_error_propagates_after_cleanup(monkeypatch, entrypoint):
    events, _ = prepare_entrypoint(
        monkeypatch,
        entrypoint,
        run_error=RuntimeError("interactive run failed"),
    )
    monkeypatch.setattr("builtins.input", lambda prompt: "test task")

    with pytest.raises(RuntimeError, match="interactive run failed"):
        run_entrypoint(entrypoint, extra_args=[])

    assert events[-3:] == [
        ("agent.run", "test task"),
        "agent.close",
        "client.close",
    ]


@pytest.mark.parametrize("entrypoint", [main_entry, ios_entry])
def test_model_config_is_validated_before_device_checks(monkeypatch, entrypoint):
    monkeypatch.setattr(
        entrypoint,
        "check_system_requirements",
        lambda *args, **kwargs: pytest.fail("device checks must not run first"),
    )
    if entrypoint is main_entry:
        monkeypatch.setattr(entrypoint, "set_device_type", lambda device_type: None)
        monkeypatch.setattr(entrypoint, "handle_device_commands", lambda args: False)
    else:
        monkeypatch.setattr(entrypoint, "handle_device_commands", lambda args: False)

    with pytest.raises(ModelConfigurationError, match="api_key"):
        entrypoint.main(
            ["--provider", "anthropic", "--model", "claude-test", "task"]
        )


@pytest.mark.parametrize("entrypoint", [main_entry, ios_entry])
def test_header_shows_model_routing_without_secret(monkeypatch, entrypoint, capsys):
    prepare_entrypoint(monkeypatch, entrypoint)

    run_entrypoint(
        entrypoint,
        extra_args=[
            "--provider",
            "openai",
            "--tool-mode",
            "text",
            "--api-key",
            "do-not-print-this",
            "test task",
        ],
    )

    output = capsys.readouterr().out
    assert "Provider: openai" in output
    assert "Tool Mode: text" in output
    assert "Model: test-model" in output
    assert "Base URL: https://models.example/v1" in output
    assert "do-not-print-this" not in output


@pytest.mark.parametrize("entrypoint", [main_entry, ios_entry])
def test_list_apps_returns_before_model_client_creation(monkeypatch, entrypoint):
    monkeypatch.setattr(
        entrypoint,
        "ModelClient",
        lambda *a, **k: pytest.fail("list command must not create a model client"),
    )
    monkeypatch.setattr(entrypoint, "list_supported_apps", lambda: [])
    if entrypoint is main_entry:
        monkeypatch.setattr(entrypoint, "set_device_type", lambda device_type: None)

    entrypoint.main(["--list-apps"])


@pytest.mark.parametrize("entrypoint", [main_entry, ios_entry])
def test_help_does_not_connect_to_device_or_model(monkeypatch, entrypoint):
    monkeypatch.setattr(
        entrypoint,
        "ModelClient",
        lambda *a, **k: pytest.fail("help must not create a model client"),
    )
    monkeypatch.setattr(
        entrypoint,
        "check_system_requirements",
        lambda *a, **k: pytest.fail("help must not check devices"),
    )

    with pytest.raises(SystemExit) as exc_info:
        entrypoint.main(["--help"])

    assert exc_info.value.code == 0


def test_entrypoints_do_not_contain_direct_openai_or_user_hardcoding():
    for path in (Path(main_entry.__file__), Path(ios_entry.__file__)):
        source = path.read_text()
        assert "from openai import OpenAI" not in source
        assert "OpenAI(" not in source
        assert "check_model_api" not in source
        assert "dashscope.aliyuncs.com" not in source
        assert "gui-plus" not in source
        assert "sk-3708c8a6e86b4e819c6b0e51404c0ca3" not in source
        assert "打开美团搜索附近的火锅店" not in source
