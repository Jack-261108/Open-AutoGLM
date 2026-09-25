"""Offline tests for CLI platform routing and early device commands."""

from types import SimpleNamespace

import pytest

import ios as ios_entry
import main as main_entry
from phone_agent.device_factory import DeviceType
import phone_agent.hdc as hdc_module


class FakeConnection:
    def connect(self, address):
        return False, "unused"

    def disconnect(self, address=None):
        return True, "unused"

    def enable_tcpip(self, port, device_id=None):
        return True, "unused"

    def get_device_ip(self, device_id=None):
        return None


class FakeFactory:
    def get_connection_class(self):
        return FakeConnection

    def list_devices(self):
        return []


class FakeClient:
    def __init__(self, config, verbose):
        self.config = config
        self.verbose = verbose

    def check_connection(self):
        pass

    def close(self):
        pass


class FakeAgent:
    def run(self, task):
        return "done"

    def reset(self):
        pass

    def close(self):
        pass


@pytest.mark.parametrize(
    "device_name, expected_type",
    [("adb", DeviceType.ADB), ("hdc", DeviceType.HDC)],
)
def test_android_device_list_uses_selected_factory_without_model(
    monkeypatch, device_name, expected_type
):
    selected = []
    monkeypatch.setattr(main_entry, "set_device_type", selected.append)
    monkeypatch.setattr(main_entry, "get_device_factory", lambda: FakeFactory())
    monkeypatch.setattr(hdc_module, "set_hdc_verbose", lambda verbose: None)
    monkeypatch.setattr(
        main_entry,
        "ModelClient",
        lambda *a, **k: pytest.fail("device list must not create a model client"),
    )

    main_entry.main(["--device-type", device_name, "--list-devices"])

    assert selected == [expected_type]


def test_main_ios_device_command_routes_without_android_factory_or_model(monkeypatch):
    routed = []
    monkeypatch.setattr(
        main_entry,
        "handle_ios_device_commands",
        lambda args: routed.append(args.device_type) or True,
    )
    monkeypatch.setattr(
        main_entry,
        "get_device_factory",
        lambda: pytest.fail("iOS command must not use Android/HDC factory"),
    )
    monkeypatch.setattr(
        main_entry,
        "set_device_type",
        lambda device_type: pytest.fail("iOS command must not set Android/HDC type"),
    )
    monkeypatch.setattr(
        main_entry,
        "ModelClient",
        lambda *a, **k: pytest.fail("device command must not create a model client"),
    )

    main_entry.main(["--device-type", "ios", "--list-devices"])

    assert routed == ["ios"]


def test_standalone_ios_device_list_returns_before_model_client(monkeypatch):
    monkeypatch.setattr(
        ios_entry,
        "XCTestConnection",
        lambda wda_url: SimpleNamespace(),
    )
    monkeypatch.setattr(ios_entry, "list_devices", lambda: [])
    monkeypatch.setattr(
        ios_entry,
        "ModelClient",
        lambda *a, **k: pytest.fail("device list must not create a model client"),
    )

    ios_entry.main(["--list-devices"])


@pytest.mark.parametrize("quiet, expected_verbose", [(False, True), (True, False)])
def test_hdc_verbose_follows_quiet_flag(monkeypatch, quiet, expected_verbose):
    verbose_values = []
    monkeypatch.setattr(main_entry, "set_device_type", lambda device_type: None)
    monkeypatch.setattr(hdc_module, "set_hdc_verbose", verbose_values.append)
    monkeypatch.setattr(main_entry, "list_harmonyos_apps", lambda: [])
    monkeypatch.setattr(
        main_entry,
        "ModelClient",
        lambda *a, **k: pytest.fail("list apps must not create a model client"),
    )
    args = ["--device-type", "hdc", "--list-apps"]
    if quiet:
        args.append("--quiet")

    main_entry.main(args)

    assert verbose_values == [expected_verbose]


@pytest.mark.parametrize(
    "device_name, expected_agent",
    [("adb", "android"), ("hdc", "android"), ("ios", "ios")],
)
def test_main_routes_formal_run_to_platform_agent(
    monkeypatch, device_name, expected_agent
):
    created_agents = []
    monkeypatch.setattr(main_entry, "set_device_type", lambda device_type: None)
    monkeypatch.setattr(main_entry, "handle_device_commands", lambda args: False)
    monkeypatch.setattr(
        main_entry, "check_system_requirements", lambda *args, **kwargs: True
    )
    monkeypatch.setattr(main_entry, "get_device_factory", lambda: FakeFactory())
    monkeypatch.setattr(main_entry, "list_ios_devices", lambda: [])
    monkeypatch.setattr(hdc_module, "set_hdc_verbose", lambda verbose: None)
    monkeypatch.setattr(main_entry, "ModelClient", FakeClient)

    def create_android_agent(**kwargs):
        created_agents.append("android")
        return FakeAgent()

    def create_ios_agent(**kwargs):
        created_agents.append("ios")
        return FakeAgent()

    monkeypatch.setattr(main_entry, "PhoneAgent", create_android_agent)
    monkeypatch.setattr(main_entry, "IOSPhoneAgent", create_ios_agent)

    main_entry.main(
        [
            "--device-type",
            device_name,
            "--base-url",
            "https://models.example/v1",
            "--model",
            "test-model",
            "test task",
        ]
    )

    assert created_agents == [expected_agent]


@pytest.mark.parametrize(
    "args",
    [
        ["--device-type", "ios", "--disconnect", "all", "task"],
        ["--device-type", "adb", "--pair", "task"],
        ["--device-type", "hdc", "--wda-status", "task"],
    ],
)
def test_cross_platform_device_options_are_rejected(args):
    with pytest.raises(SystemExit) as exc_info:
        main_entry.main(args)

    assert exc_info.value.code == 2


def test_invalid_device_type_environment_is_rejected(monkeypatch):
    monkeypatch.setenv("PHONE_AGENT_DEVICE_TYPE", "bogus")

    with pytest.raises(SystemExit) as exc_info:
        main_entry.parse_args([])

    assert exc_info.value.code == 2
