"""ADB utilities for Android device interaction."""

from phone_agent.adb.connection import (
    ADBConnection,
    ConnectionType,
    DeviceInfo,
    list_devices,
    quick_connect,
)
from phone_agent.adb.device import (
    back,
    clear_app_data,
    double_tap,
    force_stop_app,
    get_current_app,
    get_current_app_info,
    get_orientation,
    home,
    install_app,
    launch_app,
    launch_app_by_package,
    long_press,
    set_orientation,
    swipe,
    tap,
)
from phone_agent.adb.input import (
    clear_text,
    detect_and_set_adb_keyboard,
    get_clipboard,
    get_current_ime,
    restore_keyboard,
    set_clipboard,
    type_text,
)
from phone_agent.adb.screenshot import get_screenshot

__all__ = [
    # Screenshot
    "get_screenshot",
    # Input
    "type_text",
    "clear_text",
    "get_clipboard",
    "set_clipboard",
    "detect_and_set_adb_keyboard",
    "get_current_ime",
    "restore_keyboard",
    # Device control
    "get_current_app",
    "get_current_app_info",
    "tap",
    "swipe",
    "back",
    "home",
    "double_tap",
    "long_press",
    "launch_app",
    "launch_app_by_package",
    "force_stop_app",
    "clear_app_data",
    "install_app",
    "get_orientation",
    "set_orientation",
    # Connection management
    "ADBConnection",
    "DeviceInfo",
    "ConnectionType",
    "quick_connect",
    "list_devices",
]
