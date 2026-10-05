"""Tests for adb module helper functions (package launch, app info, IME)."""

import subprocess
import time
from unittest.mock import MagicMock

from phone_agent.adb.device import (
    clear_app_data,
    force_stop_app,
    get_current_app_info,
    get_orientation,
    install_app,
    launch_app_by_package,
    set_orientation,
)
from phone_agent.adb.input import get_clipboard, get_current_ime, set_clipboard


def _patch_run(monkeypatch, stdout="", stderr=""):
    mock = MagicMock(return_value=MagicMock(stdout=stdout, stderr=stderr, returncode=0))
    monkeypatch.setattr(subprocess, "run", mock)
    return mock


def test_launch_app_by_package_command(monkeypatch):
    """Test that launch_app_by_package issues monkey -p with the given package."""
    monkeypatch.setattr(time, "sleep", MagicMock())
    mock_run = _patch_run(monkeypatch)

    launch_app_by_package("com.example.game", device_id="emulator-5554", delay=0)

    cmd = mock_run.call_args[0][0]
    assert cmd == [
        "adb",
        "-s",
        "emulator-5554",
        "shell",
        "monkey",
        "-p",
        "com.example.game",
        "-c",
        "android.intent.category.LAUNCHER",
        "1",
    ]


def test_get_current_app_info_known_app(monkeypatch):
    """Test parsing a known app (in APP_PACKAGES) from mCurrentFocus."""
    output = (
        "  mCurrentFocus=Window{a1b2c3 u0 com.tencent.mm/com.tencent.mm.ui.LauncherUI}"
    )
    _patch_run(monkeypatch, stdout=output)

    name, package = get_current_app_info()

    assert name == "微信"
    assert package == "com.tencent.mm"


def test_get_current_app_info_unknown_app(monkeypatch):
    """Test parsing an unknown app: package is still extracted and returned."""
    output = "  mCurrentFocus=Window{a1b2c3 u0 com.junqi.game.ui/com.junqi.game.MainActivity}"
    _patch_run(monkeypatch, stdout=output)

    name, package = get_current_app_info()

    assert name == "com.junqi.game.ui"
    assert package == "com.junqi.game.ui"


def test_get_current_app_info_no_focus_line(monkeypatch):
    """Test that missing focus lines returns System Home / unknown."""
    _patch_run(monkeypatch, stdout="some unrelated dumpsys output")

    name, package = get_current_app_info()

    assert name == "System Home"
    assert package == "unknown"


def test_get_current_app_info_focused_app_token(monkeypatch):
    """Test parsing from mFocusedApp line (no mCurrentFocus present)."""
    output = (
        "  mFocusedApp=AppWindowToken{abc token=Token{123 "
        "ActivityRecord{45 u0 com.taobao.taobao/tv.android.xyz t678}}}"
    )
    _patch_run(monkeypatch, stdout=output)

    name, package = get_current_app_info()

    assert name == "淘宝"
    assert package == "com.taobao.taobao"


def test_get_current_app_info_empty_output_raises(monkeypatch):
    """Test that empty dumpsys output raises ValueError (device disconnect signal)."""
    _patch_run(monkeypatch, stdout="", stderr="adb: device offline")

    try:
        get_current_app_info()
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "adb: device offline" in str(e)


def test_get_current_ime(monkeypatch):
    """Test reading the current IME from secure settings."""
    _patch_run(monkeypatch, stdout="com.android.adbkeyboard/.AdbIME\n")

    ime = get_current_ime(device_id="dev1")

    assert ime == "com.android.adbkeyboard/.AdbIME"
    cmd = subprocess.run.call_args[0][0]
    assert cmd[:4] == ["adb", "-s", "dev1", "shell"]
    assert cmd[4:] == ["settings", "get", "secure", "default_input_method"]


def test_get_clipboard_command(monkeypatch):
    """Test reading clipboard via cmd clipboard get."""
    _patch_run(monkeypatch, stdout="clipboard text content\n")

    clip = get_clipboard(device_id="dev1")

    assert clip == "clipboard text content"
    cmd = subprocess.run.call_args[0][0]
    assert cmd == ["adb", "-s", "dev1", "shell", "cmd", "clipboard", "get"]


def test_get_clipboard_error_raises(monkeypatch):
    """Test that failure in get_clipboard raises RuntimeError."""
    mock = MagicMock(return_value=MagicMock(stdout="", stderr="service not found", returncode=1))
    monkeypatch.setattr(subprocess, "run", mock)

    import pytest

    with pytest.raises(RuntimeError, match="读取剪贴板失败"):
        get_clipboard()


def test_set_clipboard_command(monkeypatch):
    """Test setting clipboard via base64 pipeline into cmd clipboard set text."""
    mock_run = _patch_run(monkeypatch)

    set_clipboard("hello 'world' & test\nline2", device_id="dev1")

    cmd = mock_run.call_args[0][0]
    assert cmd[:4] == ["adb", "-s", "dev1", "shell"]
    shell_cmd = cmd[4]
    assert "cmd clipboard set text" in shell_cmd
    assert "base64 -d" in shell_cmd


def test_set_clipboard_error_raises(monkeypatch):
    """Test that failure in set_clipboard raises RuntimeError."""
    mock = MagicMock(return_value=MagicMock(stdout="", stderr="failed", returncode=1))
    monkeypatch.setattr(subprocess, "run", mock)

    import pytest

    with pytest.raises(RuntimeError, match="设置剪贴板失败"):
        set_clipboard("test")


def test_force_stop_app_command(monkeypatch):
    """Test force_stop_app with both mapped name and direct package."""
    mock_run = _patch_run(monkeypatch)

    # 1. Mapped name "微信" -> "com.tencent.mm"
    force_stop_app("微信", device_id="dev1")
    cmd = mock_run.call_args[0][0]
    assert cmd == ["adb", "-s", "dev1", "shell", "am", "force-stop", "com.tencent.mm"]

    # 2. Package name directly
    force_stop_app("com.other.app", device_id="dev1")
    cmd = mock_run.call_args[0][0]
    assert cmd == ["adb", "-s", "dev1", "shell", "am", "force-stop", "com.other.app"]


def test_clear_app_data_success_and_error(monkeypatch):
    """Test clear_app_data executes pm clear and validates output."""
    import pytest

    # Success case: returns Success
    _patch_run(monkeypatch, stdout="Success\n")
    clear_app_data("微信", device_id="dev1")
    cmd = subprocess.run.call_args[0][0]
    assert cmd == ["adb", "-s", "dev1", "shell", "pm", "clear", "com.tencent.mm"]

    # Failure case
    _patch_run(monkeypatch, stdout="Failed\n")
    with pytest.raises(RuntimeError, match="清理应用数据失败"):
        clear_app_data("微信", device_id="dev1")


def test_install_app_command(monkeypatch, tmp_path):
    """Test install_app validates file extension and executes adb install -r."""
    import pytest

    # 1. Non-existent file
    with pytest.raises(FileNotFoundError):
        install_app(str(tmp_path / "not_found.apk"))

    # 2. Non-apk file
    txt_file = tmp_path / "test.txt"
    txt_file.write_text("hello")
    with pytest.raises(ValueError, match="不是 APK"):
        install_app(str(txt_file))

    # 3. Valid APK success
    apk_file = tmp_path / "app.apk"
    apk_file.write_text("dummy apk")
    mock_run = _patch_run(monkeypatch, stdout="Success\n")
    install_app(str(apk_file), device_id="dev1")
    cmd = mock_run.call_args[0][0]
    assert cmd == ["adb", "-s", "dev1", "install", "-r", str(apk_file)]

    # 4. Valid APK failure
    _patch_run(monkeypatch, stdout="Failure [INSTALL_FAILED_ALREADY_EXISTS]\n", stderr="")
    with pytest.raises(RuntimeError, match="安装 APK 失败"):
        install_app(str(apk_file), device_id="dev1")


def test_get_orientation_command_dumpsys_input(monkeypatch):
    """Test get_orientation parses SurfaceOrientation from dumpsys input."""
    output = "  SurfaceOrientation: 1\n"
    _patch_run(monkeypatch, stdout=output)

    res = get_orientation(device_id="dev1")

    assert res["orientation"] == "landscape"
    assert res["rotation"] == 1
    assert res["is_landscape"] is True
    cmd = subprocess.run.call_args[0][0]
    assert cmd == ["adb", "-s", "dev1", "shell", "dumpsys", "input"]


def test_get_orientation_command_dumpsys_window_fallback(monkeypatch):
    """Test get_orientation falls back to dumpsys window if dumpsys input has no SurfaceOrientation."""
    def mock_run(cmd, *args, **kwargs):
        if "input" in cmd:
            return MagicMock(stdout="no orientation info\n", stderr="", returncode=0)
        if "window" in cmd:
            return MagicMock(stdout="  mCurrentRotation=0\n", stderr="", returncode=0)
        return MagicMock(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(subprocess, "run", mock_run)

    res = get_orientation(device_id="dev1")
    assert res["orientation"] == "portrait"
    assert res["rotation"] == 0
    assert res["is_landscape"] is False


def test_set_orientation_commands(monkeypatch):
    """Test set_orientation commands for portrait, landscape, and auto."""
    mock_run = _patch_run(monkeypatch)

    # 1. portrait
    set_orientation("portrait", device_id="dev1")
    assert mock_run.call_count == 2
    assert mock_run.call_args_list[0][0][0] == [
        "adb", "-s", "dev1", "shell", "settings", "put", "system", "accelerometer_rotation", "0"
    ]
    assert mock_run.call_args_list[1][0][0] == [
        "adb", "-s", "dev1", "shell", "settings", "put", "system", "user_rotation", "0"
    ]

    # 2. landscape
    mock_run.reset_mock()
    set_orientation("landscape", device_id="dev1")
    assert mock_run.call_count == 2
    assert mock_run.call_args_list[1][0][0] == [
        "adb", "-s", "dev1", "shell", "settings", "put", "system", "user_rotation", "1"
    ]

    # 3. auto
    mock_run.reset_mock()
    set_orientation("auto", device_id="dev1")
    assert mock_run.call_count == 1
    assert mock_run.call_args_list[0][0][0] == [
        "adb", "-s", "dev1", "shell", "settings", "put", "system", "accelerometer_rotation", "1"
    ]

    # 4. invalid
    import pytest
    with pytest.raises(ValueError, match="不支持的屏幕方向"):
        set_orientation("invalid_mode")



