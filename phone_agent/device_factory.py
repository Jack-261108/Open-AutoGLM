"""Device factory for selecting ADB or HDC based on device type."""

from enum import Enum
from typing import Any

from phone_agent.config.timing import TIMING_CONFIG


class DeviceType(Enum):
    """Type of device connection tool."""

    ADB = "adb"
    HDC = "hdc"
    IOS = "ios"


class DeviceFactory:
    """
    Factory class for getting device-specific implementations.

    This allows the system to work with Android (ADB), HarmonyOS (HDC), and iOS devices.
    """

    def __init__(
        self,
        device_type: DeviceType = DeviceType.ADB,
        wda_url: str = "http://localhost:8100",
        session_id: str | None = None,
    ):
        """
        Initialize the device factory.

        Args:
            device_type: The type of device to use (ADB, HDC, or IOS).
            wda_url: WebDriverAgent URL for iOS devices.
            session_id: Optional WDA session ID for iOS devices.
        """
        self.device_type = device_type
        self.wda_url = wda_url
        self.session_id = session_id
        self._module: Any = None

    @property
    def module(self) -> Any:
        """Get the appropriate device module (adb, hdc, or xctest)."""
        if self._module is None:
            mod: Any
            if self.device_type == DeviceType.ADB:
                from phone_agent import adb

                mod = adb
            elif self.device_type == DeviceType.HDC:
                from phone_agent import hdc

                mod = hdc
            elif self.device_type == DeviceType.IOS:
                from phone_agent import xctest

                mod = xctest
            else:
                raise ValueError(f"Unknown device type: {self.device_type}")
            self._module = mod
        result: Any = self._module
        return result

    @staticmethod
    def _delay(delay: float | None, default: float) -> float:
        """Use the caller delay, otherwise the shared timing config."""
        return default if delay is None else delay

    def get_screenshot(self, device_id: str | None = None, timeout: int = 10):
        """Get screenshot from device."""
        if self.device_type == DeviceType.IOS:
            from phone_agent import xctest

            return xctest.get_screenshot(
                wda_url=self.wda_url or "http://localhost:8100",
                session_id=self.session_id,
                device_id=device_id,
                timeout=timeout,
            )
        return self.module.get_screenshot(device_id, timeout)

    def get_current_app(self, device_id: str | None = None) -> str:
        """Get current app name."""
        if self.device_type == DeviceType.IOS:
            from phone_agent import xctest

            return xctest.get_current_app(
                wda_url=self.wda_url or "http://localhost:8100",
                session_id=self.session_id,
            )
        return self.module.get_current_app(device_id)

    def get_ui_tree(self, device_id: str | None = None):
        """Get a compact accessibility tree, or None if the platform dump fails."""
        if self.device_type == DeviceType.IOS:
            from phone_agent import xctest

            return xctest.get_ui_tree(
                wda_url=self.wda_url or "http://localhost:8100",
                session_id=self.session_id,
            )
        return self.module.get_ui_tree(device_id)

    def tap(
        self, x: int, y: int, device_id: str | None = None, delay: float | None = None
    ):
        """Tap at coordinates."""
        if self.device_type == DeviceType.IOS:
            from phone_agent import xctest

            return xctest.tap(
                x,
                y,
                wda_url=self.wda_url or "http://localhost:8100",
                session_id=self.session_id,
                delay=self._delay(delay, TIMING_CONFIG.device.default_tap_delay),
            )
        return self.module.tap(x, y, device_id, delay)

    def double_tap(
        self, x: int, y: int, device_id: str | None = None, delay: float | None = None
    ):
        """Double tap at coordinates."""
        if self.device_type == DeviceType.IOS:
            from phone_agent import xctest

            return xctest.double_tap(
                x,
                y,
                wda_url=self.wda_url or "http://localhost:8100",
                session_id=self.session_id,
                delay=self._delay(
                    delay, TIMING_CONFIG.device.default_double_tap_delay
                ),
            )
        return self.module.double_tap(x, y, device_id, delay)

    def long_press(
        self,
        x: int,
        y: int,
        duration_ms: int = 3000,
        device_id: str | None = None,
        delay: float | None = None,
    ):
        """Long press at coordinates."""
        if self.device_type == DeviceType.IOS:
            from phone_agent import xctest

            return xctest.long_press(
                x,
                y,
                duration=duration_ms / 1000.0,
                wda_url=self.wda_url or "http://localhost:8100",
                session_id=self.session_id,
                delay=self._delay(
                    delay, TIMING_CONFIG.device.default_long_press_delay
                ),
            )
        return self.module.long_press(x, y, duration_ms, device_id, delay)

    def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int | None = None,
        device_id: str | None = None,
        delay: float | None = None,
    ):
        """Swipe from start to end."""
        if self.device_type == DeviceType.IOS:
            from phone_agent import xctest

            duration = None if duration_ms is None else duration_ms / 1000.0
            return xctest.swipe(
                start_x,
                start_y,
                end_x,
                end_y,
                duration=duration,
                wda_url=self.wda_url or "http://localhost:8100",
                session_id=self.session_id,
                delay=self._delay(delay, TIMING_CONFIG.device.default_swipe_delay),
            )
        return self.module.swipe(
            start_x, start_y, end_x, end_y, duration_ms, device_id, delay
        )

    def back(self, device_id: str | None = None, delay: float | None = None):
        """Press back button."""
        if self.device_type == DeviceType.IOS:
            from phone_agent import xctest

            return xctest.back(
                wda_url=self.wda_url or "http://localhost:8100",
                session_id=self.session_id,
                delay=self._delay(delay, TIMING_CONFIG.device.default_back_delay),
            )
        return self.module.back(device_id, delay)

    def home(self, device_id: str | None = None, delay: float | None = None):
        """Press home button."""
        if self.device_type == DeviceType.IOS:
            from phone_agent import xctest

            return xctest.home(
                wda_url=self.wda_url or "http://localhost:8100",
                session_id=self.session_id,
                delay=self._delay(delay, TIMING_CONFIG.device.default_home_delay),
            )
        return self.module.home(device_id, delay)

    def launch_app(
        self, app_name: str, device_id: str | None = None, delay: float | None = None
    ) -> bool:
        """Launch an app."""
        if self.device_type == DeviceType.IOS:
            from phone_agent import xctest

            return xctest.launch_app(
                app_name,
                wda_url=self.wda_url or "http://localhost:8100",
                session_id=self.session_id,
                delay=self._delay(delay, TIMING_CONFIG.device.default_launch_delay),
            )
        return self.module.launch_app(app_name, device_id, delay)

    def type_text(self, text: str, device_id: str | None = None):
        """Type text."""
        if self.device_type == DeviceType.IOS:
            from phone_agent import xctest

            return xctest.type_text(
                text,
                wda_url=self.wda_url or "http://localhost:8100",
                session_id=self.session_id,
            )
        return self.module.type_text(text, device_id)

    def clear_text(self, device_id: str | None = None):
        """Clear text."""
        if self.device_type == DeviceType.IOS:
            from phone_agent import xctest

            return xctest.clear_text(
                wda_url=self.wda_url or "http://localhost:8100",
                session_id=self.session_id,
            )
        return self.module.clear_text(device_id)

    def hide_keyboard(self, device_id: str | None = None):
        """Hide keyboard if platform requires it."""
        if self.device_type == DeviceType.IOS:
            from phone_agent.xctest.input import hide_keyboard

            return hide_keyboard(
                wda_url=self.wda_url or "http://localhost:8100",
                session_id=self.session_id,
            )
        return None

    def detect_and_set_adb_keyboard(self, device_id: str | None = None) -> str:
        """Detect and set keyboard."""
        if self.device_type == DeviceType.IOS:
            return ""
        return self.module.detect_and_set_adb_keyboard(device_id)

    def restore_keyboard(self, ime: str, device_id: str | None = None):
        """Restore keyboard."""
        if self.device_type == DeviceType.IOS:
            return None
        return self.module.restore_keyboard(ime, device_id)

    def list_devices(self):
        """List connected devices."""
        return self.module.list_devices()

    def get_connection_class(self):
        """Get the connection class (ADBConnection, HDCConnection, or XCTestConnection)."""
        if self.device_type == DeviceType.ADB:
            from phone_agent.adb import ADBConnection

            return ADBConnection
        elif self.device_type == DeviceType.HDC:
            from phone_agent.hdc import HDCConnection

            return HDCConnection
        elif self.device_type == DeviceType.IOS:
            from phone_agent.xctest import XCTestConnection

            return XCTestConnection
        else:
            raise ValueError(f"Unknown device type: {self.device_type}")


# Global device factory instance
_device_factory: DeviceFactory | None = None


def set_device_type(
    device_type: DeviceType,
    wda_url: str = "http://localhost:8100",
    session_id: str | None = None,
):
    """
    Set the global device type.

    Args:
        device_type: The device type to use (ADB, HDC, or IOS).
        wda_url: Optional WDA URL for iOS devices.
        session_id: Optional WDA session ID for iOS devices.
    """
    global _device_factory
    _device_factory = DeviceFactory(
        device_type, wda_url=wda_url, session_id=session_id
    )


def get_device_factory() -> DeviceFactory:
    """
    Get the global device factory instance.

    Returns:
        The device factory instance.
    """
    global _device_factory
    if _device_factory is None:
        _device_factory = DeviceFactory(DeviceType.ADB)  # Default to ADB
    return _device_factory
