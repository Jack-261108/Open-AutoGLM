"""Shared offline fakes for MCP server tests."""

from unittest.mock import MagicMock

import pytest

from phone_agent.mcp_server import DeviceToolkit

DEVICE_ID = "test-device-1"


@pytest.fixture
def fake_factory():
    """DeviceFactory mock that records all calls."""
    return MagicMock()


@pytest.fixture
def fake_adb():
    """phone_agent.adb module mock for the Android-specific helpers."""
    adb_mock = MagicMock()
    adb_mock.get_current_app_info.return_value = ("System Home", "unknown")
    adb_mock.get_current_ime.return_value = "com.android.adbkeyboard/.AdbIME"
    return adb_mock


@pytest.fixture
def toolkit(fake_factory, fake_adb):
    """DeviceToolkit with all device layers faked out."""
    return DeviceToolkit(DEVICE_ID, factory=fake_factory, adb_module=fake_adb)


@pytest.fixture
def no_sleep(monkeypatch):
    """Neutralize timing sleeps inside mcp_server."""
    monkeypatch.setattr("phone_agent.mcp_server.time.sleep", lambda seconds: None)
