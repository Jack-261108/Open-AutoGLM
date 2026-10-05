"""Tests for fast streaming screenshot and fallback handling."""

from io import BytesIO
import subprocess
from unittest.mock import MagicMock
from PIL import Image
import pytest

from phone_agent.adb.screenshot import get_screenshot


def _make_dummy_png_bytes(width=100, height=200):
    img = Image.new("RGB", (width, height), color=(255, 0, 0))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_get_screenshot_streaming_success(monkeypatch):
    """Test fast streaming path via exec-out screencap -p without writing temp files."""
    dummy_png = _make_dummy_png_bytes(300, 600)
    mock_run = MagicMock(return_value=MagicMock(stdout=dummy_png, stderr=b"", returncode=0))
    monkeypatch.setattr(subprocess, "run", mock_run)

    shot = get_screenshot(device_id="dev1")

    assert shot.width == 300
    assert shot.height == 600
    assert shot.is_sensitive is False
    assert shot.is_fallback is False
    assert len(shot.base64_data) > 0

    # Ensure it invoked exec-out screencap -p
    first_cmd = mock_run.call_args_list[0][0][0]
    assert first_cmd == ["adb", "-s", "dev1", "exec-out", "screencap", "-p"]
    # Ensure it only called subprocess once (no pull, no shell)
    assert mock_run.call_count == 1


def test_get_screenshot_sensitive_screen(monkeypatch):
    """Test detection of sensitive screen indicator (e.g. payment page)."""
    mock_run = MagicMock(
        return_value=MagicMock(stdout=b"Status: -1\n", stderr=b"", returncode=1)
    )
    monkeypatch.setattr(subprocess, "run", mock_run)

    shot = get_screenshot(device_id="dev1")

    assert shot.is_sensitive is True
    assert shot.is_fallback is True
    assert shot.width == 1080
    assert shot.height == 2400


def test_get_screenshot_fallback_to_pull_on_streaming_failure(monkeypatch, tmp_path):
    """Test that if streaming fails, it falls back to pulling from /sdcard/tmp.png."""
    dummy_png = _make_dummy_png_bytes(400, 800)

    call_count = 0

    def mock_subprocess_run(cmd, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if "exec-out" in cmd:
            # Simulate streaming failure on older device
            return MagicMock(stdout=b"", stderr=b"unknown command exec-out", returncode=1)
        if "pull" in cmd:
            # cmd is [..., "pull", "/sdcard/tmp.png", local_temp]
            dest = cmd[-1]
            with open(dest, "wb") as f:
                f.write(dummy_png)
            return MagicMock(stdout="", stderr="", returncode=0)
        return MagicMock(stdout="screencap done", stderr="", returncode=0)

    monkeypatch.setattr(subprocess, "run", mock_subprocess_run)

    shot = get_screenshot(device_id="dev1")

    assert shot.width == 400
    assert shot.height == 800
    assert shot.is_sensitive is False
    assert shot.is_fallback is False
    assert call_count >= 2
