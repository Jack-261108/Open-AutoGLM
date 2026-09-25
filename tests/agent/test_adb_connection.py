"""Tests for ADB connection device listing and parsing."""

import subprocess
from unittest.mock import MagicMock

from phone_agent.adb.connection import ADBConnection, ConnectionType
from phone_agent.adb.device import get_current_app


def test_list_devices_mdns_with_spaces(monkeypatch):
    """Test parsing mDNS wireless debugging device with collision number (e.g. ' (2)')."""
    mock_output = (
        "List of devices attached\n"
        "adb-10AE942CBM001DJ-E5Zu7M (2)._adb-tls-connect._tcp device product:PD2339M model:V2339FA device:PD2339 transport_id:18\n"
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        MagicMock(return_value=MagicMock(stdout=mock_output, returncode=0)),
    )

    conn = ADBConnection()
    devices = conn.list_devices()

    assert len(devices) == 1
    device = devices[0]
    assert device.device_id == "adb-10AE942CBM001DJ-E5Zu7M (2)._adb-tls-connect._tcp"
    assert device.status == "device"
    assert device.connection_type == ConnectionType.REMOTE
    assert device.model == "V2339FA"


def test_list_devices_various_formats(monkeypatch):
    """Test parsing standard USB, emulator, tcpip, offline, and unauthorized devices."""
    mock_output = (
        "List of devices attached\n"
        "192.168.1.100:5555      device product:sdk_gphone64_arm64 model:sdk_gphone64_arm64 device:emu64a transport_id:2\n"
        "emulator-5554          offline transport_id:3\n"
        "0123456789ABCDEF       unauthorized transport_id:4\n"
        "R58M34ABCD1            device usb:337641472X product:star2qltezc model:SM_G9650 device:star2qlte transport_id:1\n"
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        MagicMock(return_value=MagicMock(stdout=mock_output, returncode=0)),
    )

    conn = ADBConnection()
    devices = conn.list_devices()

    assert len(devices) == 4

    assert devices[0].device_id == "192.168.1.100:5555"
    assert devices[0].status == "device"
    assert devices[0].connection_type == ConnectionType.REMOTE
    assert devices[0].model == "sdk_gphone64_arm64"

    assert devices[1].device_id == "emulator-5554"
    assert devices[1].status == "offline"
    assert devices[1].connection_type == ConnectionType.USB

    assert devices[2].device_id == "0123456789ABCDEF"
    assert devices[2].status == "unauthorized"
    assert devices[2].connection_type == ConnectionType.USB

    assert devices[3].device_id == "R58M34ABCD1"
    assert devices[3].status == "device"
    assert devices[3].connection_type == ConnectionType.USB
    assert devices[3].model == "SM_G9650"


def test_get_current_app_error_message(monkeypatch):
    """Test that get_current_app includes stderr when dumpsys window fails."""
    monkeypatch.setattr(
        subprocess,
        "run",
        MagicMock(return_value=MagicMock(stdout="", stderr="adb: device 'foo' not found", returncode=1)),
    )

    try:
        get_current_app("foo")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "adb: device 'foo' not found" in str(e)
