"""Tests for the MCP server: tool registration, startup validation, CLI args."""

import asyncio
from unittest.mock import MagicMock

import pytest

import phone_agent.mcp_server as mcp_server
from phone_agent.adb.connection import ConnectionType, DeviceInfo
from phone_agent.mcp_server import (
    DeviceToolkit,
    _resolve_device_id,
    _validate_environment,
    create_server,
)

EXPECTED_TOOLS = {
    "screenshot",
    "get_current_app",
    "tap",
    "double_tap",
    "long_press",
    "swipe",
    "move_piece",
    "type_text",
    "back",
    "home",
    "launch_app",
    "wait",
    "get_clipboard",
    "set_clipboard",
    "batch_actions",
    "force_stop_app",
    "clear_app_data",
    "install_app",
    "get_orientation",
    "set_orientation",
}


def _device(device_id="dev1", status="device"):
    return DeviceInfo(
        device_id=device_id,
        status=status,
        connection_type=ConnectionType.USB,
    )


def _schema(tool):
    """Read a tool's input schema across mcp 1.x (inputSchema) / 2.x (input_schema)."""
    return getattr(tool, "input_schema", None) or tool.inputSchema


# ----------------------------------------------------------------------
# Tool registration
# ----------------------------------------------------------------------


def test_all_tools_registered():
    server = create_server(DeviceToolkit(None))
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert names == EXPECTED_TOOLS


def test_tap_tool_schema_requires_integer_coordinates():
    server = create_server(DeviceToolkit(None))
    tools = {t.name: t for t in asyncio.run(server.list_tools())}

    schema = _schema(tools["tap"])
    assert schema["type"] == "object"
    assert set(schema["required"]) == {"x", "y"}
    assert schema["properties"]["x"]["type"] == "integer"
    assert schema["properties"]["y"]["type"] == "integer"


def test_tool_descriptions_mention_pixel_coordinates():
    server = create_server(DeviceToolkit(None))
    tools = {t.name: t for t in asyncio.run(server.list_tools())}

    assert "pixel" in tools["tap"].description
    assert (
        "screenshot" in tools["screenshot"].description.lower()
        or "screen" in tools["screenshot"].description.lower()
    )


def test_clipboard_and_batch_tools_schema():
    server = create_server(DeviceToolkit(None))
    tools = {t.name: t for t in asyncio.run(server.list_tools())}

    # set_clipboard requires text
    set_clip_schema = _schema(tools["set_clipboard"])
    assert set_clip_schema["type"] == "object"
    assert "text" in set_clip_schema["required"]
    assert set_clip_schema["properties"]["text"]["type"] == "string"

    # batch_actions requires actions
    batch_schema = _schema(tools["batch_actions"])
    assert batch_schema["type"] == "object"
    assert "actions" in batch_schema["required"]
    assert batch_schema["properties"]["actions"]["type"] == "array"


def test_lifecycle_tools_schema():
    server = create_server(DeviceToolkit(None), host="0.0.0.0", port=9000)
    tools = {t.name: t for t in asyncio.run(server.list_tools())}

    # force_stop_app requires app
    stop_schema = _schema(tools["force_stop_app"])
    assert "app" in stop_schema["required"]
    assert stop_schema["properties"]["app"]["type"] == "string"

    # clear_app_data requires app
    clear_schema = _schema(tools["clear_app_data"])
    assert "app" in clear_schema["required"]
    assert clear_schema["properties"]["app"]["type"] == "string"

    # install_app requires path
    install_schema = _schema(tools["install_app"])
    assert "path" in install_schema["required"]
    assert install_schema["properties"]["path"]["type"] == "string"


def test_orientation_tools_schema():
    server = create_server(DeviceToolkit(None))
    tools = {t.name: t for t in asyncio.run(server.list_tools())}

    # set_orientation requires orientation
    orient_schema = _schema(tools["set_orientation"])
    assert "orientation" in orient_schema["required"]
    assert orient_schema["properties"]["orientation"]["type"] == "string"

    # get_orientation has tool definition
    assert "get_orientation" in tools




# ----------------------------------------------------------------------
# Startup validation
# ----------------------------------------------------------------------


def test_validate_environment_missing_adb(monkeypatch, capsys):
    monkeypatch.setattr(mcp_server.shutil, "which", lambda name: None)

    with pytest.raises(SystemExit) as exc:
        _validate_environment(None)
    assert exc.value.code == 2
    assert "adb" in capsys.readouterr().err


def test_validate_environment_no_devices(monkeypatch, capsys):
    monkeypatch.setattr(mcp_server.adb, "list_devices", lambda: [])
    monkeypatch.setattr(mcp_server.shutil, "which", lambda name: "/usr/bin/adb")

    with pytest.raises(SystemExit) as exc:
        _validate_environment(None)
    assert exc.value.code == 2
    assert "设备" in capsys.readouterr().err


def test_validate_environment_device_not_online(monkeypatch, capsys):
    monkeypatch.setattr(mcp_server.adb, "list_devices", lambda: [_device()])
    monkeypatch.setattr(mcp_server.shutil, "which", lambda name: "/usr/bin/adb")

    with pytest.raises(SystemExit) as exc:
        _validate_environment("other-device")
    assert exc.value.code == 2
    assert "other-device" in capsys.readouterr().err


def test_validate_environment_passes_with_ime(monkeypatch, capsys):
    monkeypatch.setattr(mcp_server.adb, "list_devices", lambda: [_device("dev1")])
    monkeypatch.setattr(mcp_server.shutil, "which", lambda name: "/usr/bin/adb")
    monkeypatch.setattr(
        mcp_server, "_run_ime_list", lambda device_id: "com.android.adbkeyboard/.AdbIME"
    )

    assert _validate_environment("dev1") == "dev1"
    err = capsys.readouterr().err
    assert "ADB Keyboard 可用" in err
    assert "环境检查通过" in err


def test_validate_environment_missing_ime_is_only_warning(monkeypatch, capsys):
    monkeypatch.setattr(mcp_server.adb, "list_devices", lambda: [_device("dev1")])
    monkeypatch.setattr(mcp_server.shutil, "which", lambda name: "/usr/bin/adb")
    monkeypatch.setattr(mcp_server, "_run_ime_list", lambda device_id: "other.ime/.IME")

    assert _validate_environment("dev1") == "dev1"
    assert "type_text 工具将不可用" in capsys.readouterr().err


def test_validate_environment_outputs_only_to_stderr(monkeypatch, capsys):
    """stdout must stay clean: it carries the JSON-RPC protocol."""
    monkeypatch.setattr(mcp_server.adb, "list_devices", lambda: [_device("dev1")])
    monkeypatch.setattr(mcp_server.shutil, "which", lambda name: "/usr/bin/adb")
    monkeypatch.setattr(mcp_server, "_run_ime_list", lambda device_id: "")

    _validate_environment("dev1")

    captured = capsys.readouterr()
    assert captured.out == ""


# ----------------------------------------------------------------------
# Device id resolution
# ----------------------------------------------------------------------


def test_resolve_device_id_explicit_wins(monkeypatch):
    monkeypatch.setenv("PHONE_AGENT_DEVICE_ID", "env-device")
    monkeypatch.setattr(mcp_server.adb, "list_devices", lambda: [_device("usb1")])

    assert _resolve_device_id("cli-device") == "cli-device"


def test_resolve_device_id_from_env(monkeypatch):
    monkeypatch.setenv("PHONE_AGENT_DEVICE_ID", "env-device")
    monkeypatch.setattr(mcp_server.adb, "list_devices", lambda: [_device("usb1")])

    assert _resolve_device_id(None) == "env-device"


def test_resolve_device_id_first_online(monkeypatch):
    monkeypatch.delenv("PHONE_AGENT_DEVICE_ID", raising=False)
    monkeypatch.setattr(
        mcp_server.adb, "list_devices", lambda: [_device("usb1"), _device("usb2")]
    )

    assert _resolve_device_id(None) == "usb1"


def test_resolve_device_id_none_when_offline_only(monkeypatch):
    monkeypatch.delenv("PHONE_AGENT_DEVICE_ID", raising=False)
    monkeypatch.setattr(
        mcp_server.adb, "list_devices", lambda: [_device("usb1", status="offline")]
    )

    assert _resolve_device_id(None) is None


# ----------------------------------------------------------------------
# run_mcp_command
# ----------------------------------------------------------------------


def test_run_mcp_command_starts_server(monkeypatch):
    monkeypatch.setattr(mcp_server, "_validate_environment", lambda device_id: "dev1")
    monkeypatch.setattr(mcp_server, "set_device_type", MagicMock())
    fake_server = MagicMock()
    created = MagicMock(return_value=fake_server)
    monkeypatch.setattr(mcp_server, "create_server", created)

    code = mcp_server.run_mcp_command(["--device-id", "dev1"])

    assert code == 0
    fake_server.run.assert_called_once()
    toolkit = created.call_args[0][0]
    assert toolkit.device_id == "dev1"
