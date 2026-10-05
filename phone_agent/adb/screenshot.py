"""Screenshot utilities for capturing Android device screen."""

import base64
import os
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from io import BytesIO
from typing import Tuple

from PIL import Image


@dataclass
class Screenshot:
    """Represents a captured screenshot."""

    base64_data: str
    width: int
    height: int
    is_sensitive: bool = False
    is_fallback: bool = False


def get_screenshot(device_id: str | None = None, timeout: int = 10) -> Screenshot:
    """
    Capture a screenshot from the connected Android device.

    Uses `adb exec-out screencap -p` for fast streaming directly into memory,
    avoiding on-device file writing and local disk I/O. Automatically falls back
    to `screencap -p /sdcard/...` with `adb pull` on older or restricted devices.

    Args:
        device_id: Optional ADB device ID for multi-device setups.
        timeout: Timeout in seconds for screenshot operations.

    Returns:
        Screenshot object containing base64 data and dimensions.

    Note:
        If the screenshot fails (e.g., on sensitive screens like payment pages),
        a black fallback image is returned with is_sensitive=True.
    """
    adb_prefix = _get_adb_prefix(device_id)

    # 1. Fast path: stream PNG directly via adb exec-out into memory (zero tempfile, zero pull)
    try:
        result = subprocess.run(
            adb_prefix + ["exec-out", "screencap", "-p"],
            capture_output=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )

        stdout = result.stdout or b""
        stderr = result.stderr or b""

        # Check for sensitive screen indicator
        if b"Status: -1" in stdout or b"Status: -1" in stderr or b"Failed" in stdout:
            return _create_fallback_screenshot(is_sensitive=True)

        if result.returncode == 0 and stdout.startswith(b"\x89PNG\r\n\x1a\n"):
            img = Image.open(BytesIO(stdout))
            width, height = img.size
            base64_data = base64.b64encode(stdout).decode("ascii")
            return Screenshot(
                base64_data=base64_data,
                width=width,
                height=height,
                is_sensitive=False,
            )
    except Exception as e:
        print(f"Streaming screenshot failed, falling back: {e}", file=sys.stderr)

    # 2. Fallback path: write to /sdcard/tmp.png and pull (for older/non-exec-out environments)
    temp_path = os.path.join(tempfile.gettempdir(), f"screenshot_{uuid.uuid4()}.png")
    try:
        result = subprocess.run(
            adb_prefix + ["shell", "screencap", "-p", "/sdcard/tmp.png"],
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )

        output = (result.stdout or "") + (result.stderr or "")
        if "Status: -1" in output or "Failed" in output:
            return _create_fallback_screenshot(is_sensitive=True)

        subprocess.run(
            adb_prefix + ["pull", "/sdcard/tmp.png", temp_path],
            capture_output=True,
            text=True,
            timeout=5,
            stdin=subprocess.DEVNULL,
        )

        if not os.path.exists(temp_path):
            return _create_fallback_screenshot(is_sensitive=False)

        img = Image.open(temp_path)
        width, height = img.size

        buffered = BytesIO()
        img.save(buffered, format="PNG")
        base64_data = base64.b64encode(buffered.getvalue()).decode("utf-8")

        os.remove(temp_path)

        return Screenshot(
            base64_data=base64_data, width=width, height=height, is_sensitive=False
        )
    except Exception as e:
        print(f"Fallback screenshot error: {e}", file=sys.stderr)
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        return _create_fallback_screenshot(is_sensitive=False)


def _get_adb_prefix(device_id: str | None) -> list:
    """Get ADB command prefix with optional device specifier."""
    if device_id:
        return ["adb", "-s", device_id]
    return ["adb"]


def _create_fallback_screenshot(is_sensitive: bool) -> Screenshot:
    """Create a black fallback image when screenshot fails."""
    default_width, default_height = 1080, 2400

    black_img = Image.new("RGB", (default_width, default_height), color="black")
    buffered = BytesIO()
    black_img.save(buffered, format="PNG")
    base64_data = base64.b64encode(buffered.getvalue()).decode("utf-8")

    return Screenshot(
        base64_data=base64_data,
        width=default_width,
        height=default_height,
        is_sensitive=is_sensitive,
        is_fallback=True,
    )
