"""Device control utilities for Android automation."""

import os
import re
import subprocess
import time
from typing import List, Optional, Tuple

from phone_agent.config.apps import APP_PACKAGES
from phone_agent.config.timing import TIMING_CONFIG

# Matches a package name followed by "/" (package/activity) in window focus lines,
# e.g. "com.tencent.mm/com.tencent.mm.ui.LauncherUI".
_PACKAGE_PATTERN = re.compile(r"\b([A-Za-z][\w]*(?:\.[\w]+)+)/")


def get_current_app(device_id: str | None = None) -> str:
    """
    Get the currently focused app name.

    Args:
        device_id: Optional ADB device ID for multi-device setups.

    Returns:
        The app name if recognized, otherwise "System Home".
    """
    adb_prefix = _get_adb_prefix(device_id)

    result = subprocess.run(
        adb_prefix + ["shell", "dumpsys", "window"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
    )
    output = result.stdout
    if not output:
        error_detail = result.stderr.strip() if result.stderr else "Empty output"
        raise ValueError(f"No output from dumpsys window: {error_detail}")

    # Parse window focus info
    for line in output.split("\n"):
        if "mCurrentFocus" in line or "mFocusedApp" in line:
            for app_name, package in APP_PACKAGES.items():
                if package in line:
                    return app_name

    return "System Home"


def get_current_app_info(device_id: str | None = None) -> tuple[str, str]:
    """
    Get the currently focused app name and package name.

    Unlike get_current_app, this also extracts the raw package name, so
    unknown apps (not in APP_PACKAGES) are still reported with their package.

    Args:
        device_id: Optional ADB device ID for multi-device setups.

    Returns:
        Tuple of (display_name, package_name). display_name is the mapped
        Chinese name if recognized, the package name itself for unknown apps,
        or ("System Home", "unknown") when no focus package can be parsed.
    """
    adb_prefix = _get_adb_prefix(device_id)

    result = subprocess.run(
        adb_prefix + ["shell", "dumpsys", "window"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
    )
    output = result.stdout
    if not output:
        error_detail = result.stderr.strip() if result.stderr else "Empty output"
        raise ValueError(f"No output from dumpsys window: {error_detail}")

    for line in output.split("\n"):
        if "mCurrentFocus" in line or "mFocusedApp" in line:
            match = _PACKAGE_PATTERN.search(line)
            if match:
                package = match.group(1)
                for app_name, mapped_package in APP_PACKAGES.items():
                    if mapped_package == package:
                        return app_name, package
                return package, package

    return "System Home", "unknown"


def tap(
    x: int, y: int, device_id: str | None = None, delay: float | None = None
) -> None:
    """
    Tap at the specified coordinates.

    Args:
        x: X coordinate.
        y: Y coordinate.
        device_id: Optional ADB device ID.
        delay: Delay in seconds after tap. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_tap_delay

    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix + ["shell", "input", "tap", str(x), str(y)],
        capture_output=True,
        stdin=subprocess.DEVNULL,
    )
    time.sleep(delay)


def double_tap(
    x: int, y: int, device_id: str | None = None, delay: float | None = None
) -> None:
    """
    Double tap at the specified coordinates.

    Args:
        x: X coordinate.
        y: Y coordinate.
        device_id: Optional ADB device ID.
        delay: Delay in seconds after double tap. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_double_tap_delay

    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix + ["shell", "input", "tap", str(x), str(y)],
        capture_output=True,
        stdin=subprocess.DEVNULL,
    )
    time.sleep(TIMING_CONFIG.device.double_tap_interval)
    subprocess.run(
        adb_prefix + ["shell", "input", "tap", str(x), str(y)],
        capture_output=True,
        stdin=subprocess.DEVNULL,
    )
    time.sleep(delay)


def long_press(
    x: int,
    y: int,
    duration_ms: int = 3000,
    device_id: str | None = None,
    delay: float | None = None,
) -> None:
    """
    Long press at the specified coordinates.

    Args:
        x: X coordinate.
        y: Y coordinate.
        duration_ms: Duration of press in milliseconds.
        device_id: Optional ADB device ID.
        delay: Delay in seconds after long press. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_long_press_delay

    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix
        + ["shell", "input", "swipe", str(x), str(y), str(x), str(y), str(duration_ms)],
        capture_output=True,
        stdin=subprocess.DEVNULL,
    )
    time.sleep(delay)


def swipe(
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    duration_ms: int | None = None,
    device_id: str | None = None,
    delay: float | None = None,
) -> None:
    """
    Swipe from start to end coordinates.

    Args:
        start_x: Starting X coordinate.
        start_y: Starting Y coordinate.
        end_x: Ending X coordinate.
        end_y: Ending Y coordinate.
        duration_ms: Duration of swipe in milliseconds (auto-calculated if None).
        device_id: Optional ADB device ID.
        delay: Delay in seconds after swipe. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_swipe_delay

    adb_prefix = _get_adb_prefix(device_id)

    if duration_ms is None:
        # Calculate duration based on distance
        dist_sq = (start_x - end_x) ** 2 + (start_y - end_y) ** 2
        duration_ms = int(dist_sq / 1000)
        duration_ms = max(1000, min(duration_ms, 2000))  # Clamp between 1000-2000ms

    subprocess.run(
        adb_prefix
        + [
            "shell",
            "input",
            "swipe",
            str(start_x),
            str(start_y),
            str(end_x),
            str(end_y),
            str(duration_ms),
        ],
        capture_output=True,
        stdin=subprocess.DEVNULL,
    )
    time.sleep(delay)


def back(device_id: str | None = None, delay: float | None = None) -> None:
    """
    Press the back button.

    Args:
        device_id: Optional ADB device ID.
        delay: Delay in seconds after pressing back. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_back_delay

    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix + ["shell", "input", "keyevent", "4"],
        capture_output=True,
        stdin=subprocess.DEVNULL,
    )
    time.sleep(delay)


def home(device_id: str | None = None, delay: float | None = None) -> None:
    """
    Press the home button.

    Args:
        device_id: Optional ADB device ID.
        delay: Delay in seconds after pressing home. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_home_delay

    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix + ["shell", "input", "keyevent", "KEYCODE_HOME"],
        capture_output=True,
        stdin=subprocess.DEVNULL,
    )
    time.sleep(delay)


def launch_app(
    app_name: str, device_id: str | None = None, delay: float | None = None
) -> bool:
    """
    Launch an app by name.

    Args:
        app_name: The app name (must be in APP_PACKAGES).
        device_id: Optional ADB device ID.
        delay: Delay in seconds after launching. If None, uses configured default.

    Returns:
        True if app was launched, False if app not found.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_launch_delay

    if app_name not in APP_PACKAGES:
        return False

    adb_prefix = _get_adb_prefix(device_id)
    package = APP_PACKAGES[app_name]

    subprocess.run(
        adb_prefix
        + [
            "shell",
            "monkey",
            "-p",
            package,
            "-c",
            "android.intent.category.LAUNCHER",
            "1",
        ],
        capture_output=True,
        stdin=subprocess.DEVNULL,
    )
    time.sleep(delay)
    return True


def launch_app_by_package(
    package: str, device_id: str | None = None, delay: float | None = None
) -> None:
    """
    Launch an app by its Android package name directly.

    Unlike launch_app, no APP_PACKAGES lookup is performed, so any installed
    app can be started (useful for apps not in the built-in mapping).

    Args:
        package: Android package name, e.g. "com.tencent.mm".
        device_id: Optional ADB device ID.
        delay: Delay in seconds after launching. If None, uses configured default.

    Note:
        The monkey command fails silently if the package is not installed;
        callers should verify the foreground app afterwards.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_launch_delay

    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix
        + [
            "shell",
            "monkey",
            "-p",
            package,
            "-c",
            "android.intent.category.LAUNCHER",
            "1",
        ],
        capture_output=True,
        stdin=subprocess.DEVNULL,
    )
    time.sleep(delay)


def _resolve_package(app: str) -> str:
    """Resolve an app name or package string to a canonical package name."""
    if app in APP_PACKAGES:
        return APP_PACKAGES[app]
    if re.match(r"^[A-Za-z][\w]*(?:\.[\w]+)+$", app):
        return app
    examples = "、".join(list(APP_PACKAGES)[:10])
    raise ValueError(
        f"未找到应用 '{app}'。请改用 Android 包名（如 com.tencent.mm）。"
        f"内置常见应用名: {examples} 等。"
    )


def force_stop_app(app: str, device_id: str | None = None) -> None:
    """
    Force stop an application by name or package.

    Args:
        app: App name (e.g. '微信') or raw package name (e.g. 'com.tencent.mm').
        device_id: Optional ADB device ID.
    """
    package = _resolve_package(app)
    adb_prefix = _get_adb_prefix(device_id)

    subprocess.run(
        adb_prefix + ["shell", "am", "force-stop", package],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )


def clear_app_data(app: str, device_id: str | None = None) -> None:
    """
    Clear all data and cache for an application.

    Args:
        app: App name (e.g. '微信') or raw package name (e.g. 'com.tencent.mm').
        device_id: Optional ADB device ID.
    """
    package = _resolve_package(app)
    adb_prefix = _get_adb_prefix(device_id)

    result = subprocess.run(
        adb_prefix + ["shell", "pm", "clear", package],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    output = (result.stdout or "") + (result.stderr or "")
    if "Success" not in output:
        raise RuntimeError(f"清理应用数据失败: {output.strip() or 'unknown error'}")


def install_app(apk_path: str, device_id: str | None = None) -> None:
    """
    Install an APK file onto the device.

    Args:
        apk_path: Local path to the .apk file.
        device_id: Optional ADB device ID.
    """
    if not os.path.exists(apk_path):
        raise FileNotFoundError(f"APK 文件不存在: {apk_path}")
    if not apk_path.lower().endswith(".apk"):
        raise ValueError(f"指定文件不是 APK: {apk_path}")

    adb_prefix = _get_adb_prefix(device_id)

    result = subprocess.run(
        adb_prefix + ["install", "-r", apk_path],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0 or "Failure" in output:
        raise RuntimeError(f"安装 APK 失败: {output.strip() or 'unknown error'}")


def _get_adb_prefix(device_id: str | None) -> list:
    """Get ADB command prefix with optional device specifier."""
    if device_id:
        return ["adb", "-s", device_id]
    return ["adb"]
