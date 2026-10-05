"""Input utilities for Android device text input."""

import base64
import subprocess
from typing import Optional


def type_text(text: str, device_id: str | None = None) -> None:
    """
    Type text into the currently focused input field using ADB Keyboard.

    Args:
        text: The text to type.
        device_id: Optional ADB device ID for multi-device setups.

    Note:
        Requires ADB Keyboard to be installed on the device.
        See: https://github.com/nicnocquee/AdbKeyboard
    """
    adb_prefix = _get_adb_prefix(device_id)
    encoded_text = base64.b64encode(text.encode("utf-8")).decode("utf-8")

    subprocess.run(
        adb_prefix
        + [
            "shell",
            "am",
            "broadcast",
            "-a",
            "ADB_INPUT_B64",
            "--es",
            "msg",
            encoded_text,
        ],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )


def clear_text(device_id: str | None = None) -> None:
    """
    Clear text in the currently focused input field.

    Args:
        device_id: Optional ADB device ID for multi-device setups.
    """
    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix + ["shell", "am", "broadcast", "-a", "ADB_CLEAR_TEXT"],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )


def get_current_ime(device_id: str | None = None) -> str:
    """
    Get the currently active input method (IME) identifier.

    Args:
        device_id: Optional ADB device ID for multi-device setups.

    Returns:
        The IME identifier, e.g. "com.android.adbkeyboard/.AdbIME",
        or an empty string if it cannot be read.
    """
    adb_prefix = _get_adb_prefix(device_id)

    result = subprocess.run(
        adb_prefix + ["shell", "settings", "get", "secure", "default_input_method"],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    return (result.stdout + result.stderr).strip()


def detect_and_set_adb_keyboard(device_id: str | None = None) -> str:
    """
    Detect current keyboard and switch to ADB Keyboard if needed.

    Args:
        device_id: Optional ADB device ID for multi-device setups.

    Returns:
        The original keyboard IME identifier for later restoration.
    """
    adb_prefix = _get_adb_prefix(device_id)

    # Get current IME
    result = subprocess.run(
        adb_prefix + ["shell", "settings", "get", "secure", "default_input_method"],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    current_ime = (result.stdout + result.stderr).strip()

    # Switch to ADB Keyboard if not already set
    if "com.android.adbkeyboard/.AdbIME" not in current_ime:
        subprocess.run(
            adb_prefix + ["shell", "ime", "set", "com.android.adbkeyboard/.AdbIME"],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
        )

    # Warm up the keyboard
    type_text("", device_id)

    return current_ime


def restore_keyboard(ime: str, device_id: str | None = None) -> None:
    """
    Restore the original keyboard IME.

    Args:
        ime: The IME identifier to restore.
        device_id: Optional ADB device ID for multi-device setups.
    """
    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix + ["shell", "ime", "set", ime],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )


def get_clipboard(device_id: str | None = None) -> str:
    """
    Get the current system clipboard text.

    Args:
        device_id: Optional ADB device ID for multi-device setups.

    Returns:
        The text content of the clipboard.
    """
    adb_prefix = _get_adb_prefix(device_id)

    result = subprocess.run(
        adb_prefix + ["shell", "cmd", "clipboard", "get"],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"读取剪贴板失败: {err or 'unknown error'}")

    return result.stdout.rstrip("\r\n")


def set_clipboard(text: str, device_id: str | None = None) -> None:
    """
    Set the system clipboard text.

    Uses base64 encoding to safely transfer special characters, quotes,
    and newlines across the adb shell boundary.

    Args:
        text: The text to set into the clipboard.
        device_id: Optional ADB device ID for multi-device setups.
    """
    adb_prefix = _get_adb_prefix(device_id)
    encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
    cmd = f'cmd clipboard set text "$(echo \'{encoded}\' | base64 -d)"'

    result = subprocess.run(
        adb_prefix + ["shell", cmd],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"设置剪贴板失败: {err or 'unknown error'}")


def _get_adb_prefix(device_id: str | None) -> list:
    """Get ADB command prefix with optional device specifier."""
    if device_id:
        return ["adb", "-s", device_id]
    return ["adb"]
