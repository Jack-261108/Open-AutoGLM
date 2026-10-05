"""MCP server exposing Android device control to MCP clients (e.g. Claude Code).

Started via ``phone-agent mcp`` (stdio transport). All logs go to stderr —
stdout is reserved for the JSON-RPC protocol.

The 17 tools are thin wrappers over DeviceFactory / phone_agent.adb:

- Coordinates are in pixels, relative to the top-left corner of the image
  returned by the ``screenshot`` tool (no 0-999 rescaling).
- launch_app accepts either a mapped Chinese app name or a raw package name.
- type_text requires ADB Keyboard and verifies the IME switch actually
  happened (adb commands fail silently otherwise).
"""

import argparse
import base64
from io import BytesIO
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Any

from PIL import Image

# Pinned to mcp 1.x: the 2.x stdio transport does not respond to requests
# when spawned as a subprocess (verified with mcp 2.2.0), which breaks
# Claude Code / MCP Inspector integration.
from mcp.server.fastmcp import FastMCP
from mcp.types import ImageContent, TextContent

from phone_agent import adb
from phone_agent.config.apps import APP_PACKAGES
from phone_agent.config.timing import TIMING_CONFIG
from phone_agent.device_factory import DeviceType, set_device_type

ADB_IME = "com.android.adbkeyboard/.AdbIME"

ADB_KEYBOARD_HELP = (
    "ADB Keyboard 未安装或无法激活，无法输入文本（截图/点击不受影响）。\n"
    "安装步骤：\n"
    "  1. 下载 APK: https://github.com/senzhk/ADBKeyBoard/blob/master/ADBKeyboard.apk\n"
    "  2. 安装到设备: adb install ADBKeyboard.apk\n"
    "  3. 在 设置 > 系统 > 语言和输入法 > 虚拟键盘 中启用"
)

# Matches a bare Android package name like "com.tencent.mm" (used to decide
# Matches a bare Android package name like "com.tencent.mm" (used to decide
# whether launch_app received a package name instead of an app name).
_PACKAGE_NAME_PATTERN = re.compile(r"^[A-Za-z][\w]*(?:\.[\w]+)+$")

_DEVICE_ID_ENV = "PHONE_AGENT_DEVICE_ID"
_SCREENSHOT_MAX_DIM_ENV = "PHONE_AGENT_SCREENSHOT_MAX_DIM"

# Serialize all device-touching tools: the MCP SDK runs sync tools on worker
# threads, and concurrent adb commands would interleave input events.
# Uses RLock so batch_actions can hold the lock across multiple atomic actions.
_device_lock = threading.RLock()


def _downscale_and_compress(
    base64_data: str,
    orig_w: int,
    orig_h: int,
    max_dimension: int | None,
    quality: int = 80,
) -> tuple[str, str, int, int, tuple[float, float]]:
    """Downscale and compress screenshot to JPEG if requested.

    Returns (base64_data, mime_type, width, height, (scale_x, scale_y)).
    If processing fails (e.g. invalid test mock data), falls back to original.
    """
    if max_dimension is None:
        return base64_data, "image/png", orig_w, orig_h, (1.0, 1.0)

    try:
        raw_bytes = base64.b64decode(base64_data)
        img = Image.open(BytesIO(raw_bytes))
        cur_w, cur_h = img.size

        if max_dimension and max(cur_w, cur_h) > max_dimension:
            scale = max_dimension / max(cur_w, cur_h)
            new_w = max(1, int(round(cur_w * scale)))
            new_h = max(1, int(round(cur_h * scale)))
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        else:
            new_w, new_h = cur_w, cur_h

        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=max(10, min(quality, 100)))
        new_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        scale_x = orig_w / new_w if new_w > 0 else 1.0
        scale_y = orig_h / new_h if new_h > 0 else 1.0
        return new_b64, "image/jpeg", new_w, new_h, (scale_x, scale_y)
    except Exception:
        return base64_data, "image/png", orig_w, orig_h, (1.0, 1.0)


class DeviceToolkit:
    """Device operations backing the MCP tools.

    factory / adb_module are injectable so tests can pass fakes (same pattern
    as ActionHandler's device_factory injection).
    """

    def __init__(self, device_id: str | None, factory=None, adb_module=None):
        self.device_id = device_id
        self._factory = factory
        self._adb = adb_module
        # Screen size from the last screenshot, for out-of-range checks.
        self._screen_size: tuple[int, int] | None = None
        # Ratio of physical device resolution to returned image resolution (scale_x, scale_y)
        self._coordinate_scale: tuple[float, float] = (1.0, 1.0)

    @property
    def factory(self):
        if self._factory is None:
            from phone_agent.device_factory import get_device_factory

            self._factory = get_device_factory()
        return self._factory

    @property
    def adb_module(self):
        if self._adb is None:
            self._adb = adb
        return self._adb

    # ------------------------------------------------------------------
    # Coordinate validation
    # ------------------------------------------------------------------

    def _check_coordinates(self, *points: tuple[int, int]) -> None:
        """Raise if any coordinate is negative or outside the last screenshot."""
        for x, y in points:
            if x < 0 or y < 0:
                raise ValueError(f"坐标不能为负数: ({x}, {y})")
            if self._screen_size is not None:
                width, height = self._screen_size
                if x >= width or y >= height:
                    raise ValueError(
                        f"坐标 ({x}, {y}) 超出屏幕范围 {width}x{height}"
                        "（基于最近一次截图）。请重新调用 screenshot 核对。"
                    )

    def _to_device_coords(self, x: int, y: int) -> tuple[int, int]:
        """Convert returned screenshot coordinates to physical device coordinates."""
        scale_x, scale_y = self._coordinate_scale
        if scale_x == 1.0 and scale_y == 1.0:
            return x, y
        return int(round(x * scale_x)), int(round(y * scale_y))

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    def screenshot(
        self,
        max_dimension: int | None = None,
        quality: int = 80,
    ) -> list[TextContent | ImageContent]:
        """Capture a screenshot and report the current app."""
        if max_dimension is None:
            env_dim = os.getenv(_SCREENSHOT_MAX_DIM_ENV)
            if env_dim and env_dim.isdigit():
                max_dimension = int(env_dim)

        shot = self.factory.get_screenshot(self.device_id)

        try:
            name, package = self.adb_module.get_current_app_info(self.device_id)
            app_text = f"{name} ({package})"
        except Exception:
            app_text = "未知（无法读取，设备可能已断连）"

        b64_data, mime_type, disp_w, disp_h, scale = _downscale_and_compress(
            shot.base64_data,
            shot.width,
            shot.height,
            max_dimension,
            quality,
        )

        self._screen_size = (disp_w, disp_h)
        self._coordinate_scale = scale

        text = f"分辨率 {disp_w}x{disp_h} | 当前应用: {app_text}"
        if scale != (1.0, 1.0):
            text += f"（已按比例缩放，原物理分辨率 {shot.width}x{shot.height}，坐标会自动换算）"
        if shot.is_sensitive:
            text += "\n⚠️ 当前页面受系统安全策略保护（如支付页面），图像为黑图。请基于上下文操作，或使用 back 退出该页面。"
        elif shot.is_fallback:
            text += "\n⚠️ 截图失败，设备可能已断连。请检查 adb 连接后重试。"

        return [
            ImageContent(type="image", data=b64_data, mimeType=mime_type),
            TextContent(type="text", text=text),
        ]

    def get_current_app(self) -> str:
        """Get the focused app name and package."""
        try:
            name, package = self.adb_module.get_current_app_info(self.device_id)
        except ValueError as e:
            raise RuntimeError(
                f"无法读取当前应用，设备可能已断连，请检查 adb 连接: {e}"
            ) from e
        return f"{name} ({package})"

    def tap(self, x: int, y: int) -> str:
        """Tap at pixel coordinates."""
        self._check_coordinates((x, y))
        real_x, real_y = self._to_device_coords(x, y)
        with _device_lock:
            self.factory.tap(real_x, real_y, self.device_id)
        return f"已点击 ({x}, {y})"

    def double_tap(self, x: int, y: int) -> str:
        """Double tap at pixel coordinates."""
        self._check_coordinates((x, y))
        real_x, real_y = self._to_device_coords(x, y)
        with _device_lock:
            self.factory.double_tap(real_x, real_y, self.device_id)
        return f"已双击 ({x}, {y})"

    def long_press(self, x: int, y: int, duration_ms: int = 1000) -> str:
        """Long press at pixel coordinates."""
        self._check_coordinates((x, y))
        if duration_ms <= 0:
            raise ValueError("duration_ms 必须为正数")
        real_x, real_y = self._to_device_coords(x, y)
        with _device_lock:
            self.factory.long_press(real_x, real_y, duration_ms, self.device_id)
        return f"已长按 ({x}, {y}) {duration_ms}ms"

    def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int | None = None,
    ) -> str:
        """Swipe between two pixel coordinates."""
        self._check_coordinates((start_x, start_y), (end_x, end_y))
        if duration_ms is not None and duration_ms <= 0:
            raise ValueError("duration_ms 必须为正数")
        duration_text = f"{duration_ms}ms" if duration_ms is not None else "自动时长"
        real_sx, real_sy = self._to_device_coords(start_x, start_y)
        real_ex, real_ey = self._to_device_coords(end_x, end_y)
        with _device_lock:
            self.factory.swipe(
                real_sx, real_sy, real_ex, real_ey, duration_ms, self.device_id
            )
        return f"已滑动 ({start_x}, {start_y}) → ({end_x}, {end_y})，{duration_text}"

    def move_piece(
        self,
        from_x: int,
        from_y: int,
        to_x: int,
        to_y: int,
        interval_ms: int = 300,
    ) -> str:
        """Move a piece by tapping start position, waiting, then tapping destination.

        Compound action for board games / turn-based interactions where a move consists
        of selecting a piece and placing it, saving a full LLM turn roundtrip.
        """
        self._check_coordinates((from_x, from_y), (to_x, to_y))
        if interval_ms < 0:
            raise ValueError("interval_ms 不能为负数")
        real_fx, real_fy = self._to_device_coords(from_x, from_y)
        real_tx, real_ty = self._to_device_coords(to_x, to_y)
        with _device_lock:
            self.factory.tap(real_fx, real_fy, self.device_id)
            if interval_ms > 0:
                time.sleep(interval_ms / 1000.0)
            self.factory.tap(real_tx, real_ty, self.device_id)
        return f"已走子：从 ({from_x}, {from_y}) 移动到 ({to_x}, {to_y})"

    def type_text(self, text: str, clear: bool = False) -> str:
        """Type text into the focused input field (requires ADB Keyboard)."""
        with _device_lock:
            original_ime = self.factory.detect_and_set_adb_keyboard(self.device_id)
            try:
                # adb commands fail silently, so verify the IME switch happened.
                current_ime = self.adb_module.get_current_ime(self.device_id)
                if ADB_IME not in current_ime:
                    raise RuntimeError(ADB_KEYBOARD_HELP)

                if original_ime:
                    time.sleep(TIMING_CONFIG.action.keyboard_switch_delay)

                if clear:
                    self.factory.clear_text(self.device_id)
                    time.sleep(TIMING_CONFIG.action.text_clear_delay)

                self.factory.type_text(text, self.device_id)
                time.sleep(TIMING_CONFIG.action.text_input_delay)
            finally:
                # Restore the original keyboard; an empty IME string would clear
                # the active input method instead of restoring it.
                if original_ime:
                    try:
                        self.factory.restore_keyboard(original_ime, self.device_id)
                    except Exception:
                        pass
                    time.sleep(TIMING_CONFIG.action.keyboard_restore_delay)
        return f"已输入 {len(text)} 个字符" + ("（已先清空原文本）" if clear else "")

    def back(self) -> str:
        """Press the back button."""
        with _device_lock:
            self.factory.back(self.device_id)
        return "已按返回键"

    def home(self) -> str:
        """Press the home button."""
        with _device_lock:
            self.factory.home(self.device_id)
        return "已按主页键"

    def launch_app(self, app: str) -> str:
        """Launch an app by mapped name or raw package name."""
        if app in APP_PACKAGES:
            package = APP_PACKAGES[app]
            with _device_lock:
                self.factory.launch_app(app, self.device_id)
        elif _PACKAGE_NAME_PATTERN.match(app):
            package = app
            # Android-specific capability, not part of the DeviceFactory contract.
            with _device_lock:
                self.adb_module.launch_app_by_package(app, self.device_id)
        else:
            examples = "、".join(list(APP_PACKAGES)[:10])
            raise ValueError(
                f"未找到应用 '{app}'。请改用 Android 包名"
                f"（可通过 adb shell pm list packages 查询）。"
                f"已内置常见应用名: {examples} 等。"
            )

        # monkey fails silently for packages that are not installed, so verify
        # the foreground app and report honestly.
        try:
            _, foreground = self.adb_module.get_current_app_info(self.device_id)
        except Exception:
            foreground = "未知"
        if foreground == package:
            return f"已启动 {app} ({package})，当前前台: {package}"
        return (
            f"已发出启动 {app} ({package}) 的命令，但当前前台应用是 {foreground}。"
            "包名可能不正确或未安装，建议 screenshot 确认。"
        )

    def wait(self, seconds: float = 1.0) -> str:
        """Wait without touching the device."""
        seconds = max(0.1, min(seconds, 30.0))
        time.sleep(seconds)
        return f"已等待 {seconds} 秒"

    def get_clipboard(self) -> str:
        """Get current text from device clipboard."""
        with _device_lock:
            try:
                return self.factory.get_clipboard(self.device_id)
            except Exception as e:
                raise RuntimeError(f"获取剪贴板失败: {e}") from e

    def set_clipboard(self, text: str) -> str:
        """Set text into device clipboard."""
        with _device_lock:
            try:
                self.factory.set_clipboard(text, self.device_id)
            except Exception as e:
                raise RuntimeError(f"写入剪贴板失败: {e}") from e
        return f"已将文本复制到剪贴板（共 {len(text)} 字符）"

    def force_stop_app(self, app: str) -> str:
        """Force stop an application by name or package."""
        with _device_lock:
            try:
                self.factory.force_stop_app(app, self.device_id)
            except Exception as e:
                raise RuntimeError(f"停止应用失败: {e}") from e
        return f"已强制停止应用: {app}"

    def clear_app_data(self, app: str) -> str:
        """Clear all data and cache for an application."""
        with _device_lock:
            try:
                self.factory.clear_app_data(app, self.device_id)
            except Exception as e:
                raise RuntimeError(f"清理应用数据失败: {e}") from e
        return f"已清理应用数据与缓存: {app}"

    def install_app(self, path: str) -> str:
        """Install an APK file onto the device."""
        with _device_lock:
            try:
                self.factory.install_app(path, self.device_id)
            except Exception as e:
                raise RuntimeError(f"安装应用失败: {e}") from e
        return f"已成功安装应用: {path}"

    def batch_actions(self, actions: list[dict[str, Any]]) -> dict[str, Any]:
        """Execute a list of actions sequentially. Stops on first error."""
        if not actions:
            return {
                "success": True,
                "total": 0,
                "executed": 0,
                "results": [],
            }

        results: list[dict[str, Any]] = []
        with _device_lock:
            for idx, act in enumerate(actions):
                if not isinstance(act, dict):
                    err_msg = (
                        f"第 {idx + 1} 个动作格式错误: 期望 dict，实际获得 {type(act).__name__}"
                    )
                    return {
                        "success": False,
                        "total": len(actions),
                        "executed": idx,
                        "results": results,
                        "error": err_msg,
                    }

                action_name = act.get("action")
                if not action_name or not isinstance(action_name, str):
                    err_msg = f"第 {idx + 1} 个动作缺少有效的 'action' 字段"
                    return {
                        "success": False,
                        "total": len(actions),
                        "executed": idx,
                        "results": results,
                        "error": err_msg,
                    }

                try:
                    if action_name == "tap":
                        detail = self.tap(int(act["x"]), int(act["y"]))
                    elif action_name == "double_tap":
                        detail = self.double_tap(int(act["x"]), int(act["y"]))
                    elif action_name == "long_press":
                        detail = self.long_press(
                            int(act["x"]),
                            int(act["y"]),
                            int(act.get("duration_ms", 1000)),
                        )
                    elif action_name == "swipe":
                        duration = (
                            int(act["duration_ms"])
                            if "duration_ms" in act and act["duration_ms"] is not None
                            else None
                        )
                        detail = self.swipe(
                            int(act["start_x"]),
                            int(act["start_y"]),
                            int(act["end_x"]),
                            int(act["end_y"]),
                            duration,
                        )
                    elif action_name == "move_piece":
                        detail = self.move_piece(
                            int(act["from_x"]),
                            int(act["from_y"]),
                            int(act["to_x"]),
                            int(act["to_y"]),
                            int(act.get("interval_ms", 300)),
                        )
                    elif action_name == "type_text":
                        detail = self.type_text(
                            str(act["text"]),
                            bool(act.get("clear", False)),
                        )
                    elif action_name == "set_clipboard":
                        detail = self.set_clipboard(str(act["text"]))
                    elif action_name == "wait":
                        detail = self.wait(float(act.get("seconds", 1.0)))
                    elif action_name == "back":
                        detail = self.back()
                    elif action_name == "home":
                        detail = self.home()
                    elif action_name == "launch_app":
                        detail = self.launch_app(str(act["app"]))
                    elif action_name == "force_stop_app":
                        detail = self.force_stop_app(str(act["app"]))
                    else:
                        raise ValueError(f"不支持的动作类型: '{action_name}'")

                    results.append(
                        {
                            "index": idx,
                            "action": action_name,
                            "status": "success",
                            "detail": detail,
                        }
                    )
                except Exception as e:
                    results.append(
                        {
                            "index": idx,
                            "action": action_name,
                            "status": "failed",
                            "error": str(e),
                        }
                    )
                    return {
                        "success": False,
                        "total": len(actions),
                        "executed": idx,
                        "results": results,
                        "error": f"第 {idx + 1} 个动作 ({action_name}) 执行失败: {e}",
                    }

        return {
            "success": True,
            "total": len(actions),
            "executed": len(actions),
            "results": results,
        }


def create_server(
    toolkit: DeviceToolkit,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> FastMCP:
    """Create the MCP server with all device tools registered."""
    server = FastMCP(
        "phone-agent",
        instructions=(
            "Control an Android device step by step. Workflow: call screenshot "
            "to see the screen, decide the next action, then call tap/swipe/type_text. "
            "All coordinates are in pixels relative to the top-left corner of the "
            "screenshot image. If a black image is returned, read the warning text. "
            "When unsure whether an action took effect, take another screenshot."
        ),
        host=host,
        port=port,
    )

    @server.tool()
    def screenshot(
        max_dimension: int | None = None,
        quality: int = 80,
    ) -> list[TextContent | ImageContent]:
        """Capture a screenshot of the device screen and report the current app.

        Returns image data plus screen resolution and the focused app.
        Always call this first to see the current state before acting.

        For fast turn-based games (like chess), set max_dimension=1080 or 800
        to significantly reduce transfer size and model inference latency.
        Coordinates are automatically mapped back to physical screen pixels.
        """
        return toolkit.screenshot(max_dimension=max_dimension, quality=quality)

    @server.tool()
    def get_current_app() -> str:
        """Get the currently focused app (display name and package name)."""
        return toolkit.get_current_app()

    @server.tool()
    def tap(x: int, y: int) -> str:
        """Tap at pixel coordinates (origin: top-left of the screenshot)."""
        return toolkit.tap(x, y)

    @server.tool()
    def double_tap(x: int, y: int) -> str:
        """Double tap at pixel coordinates (origin: top-left of the screenshot)."""
        return toolkit.double_tap(x, y)

    @server.tool()
    def long_press(x: int, y: int, duration_ms: int = 1000) -> str:
        """Long press at pixel coordinates (origin: top-left of the screenshot)."""
        return toolkit.long_press(x, y, duration_ms)

    @server.tool()
    def swipe(
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration_ms: int | None = None,
    ) -> str:
        """Swipe from start to end pixel coordinates. duration_ms is optional
        (auto-calculated from distance when omitted)."""
        return toolkit.swipe(start_x, start_y, end_x, end_y, duration_ms)

    @server.tool()
    def move_piece(
        from_x: int,
        from_y: int,
        to_x: int,
        to_y: int,
        interval_ms: int = 300,
    ) -> str:
        """Move a piece by tapping start coordinates and then destination coordinates.

        Compound action designed for board games / turn-based UIs where moving a piece
        requires selecting it and then clicking the target. Performs both taps in a
        single tool call, saving an entire LLM reasoning turn.
        """
        return toolkit.move_piece(from_x, from_y, to_x, to_y, interval_ms)

    @server.tool()
    def type_text(text: str, clear: bool = False) -> str:
        """Type text into the focused input field. Requires a focused text box
        and ADB Keyboard installed. Set clear=True to empty the field first."""
        return toolkit.type_text(text, clear)

    @server.tool()
    def back() -> str:
        """Press the Android back button."""
        return toolkit.back()

    @server.tool()
    def home() -> str:
        """Press the Android home button."""
        return toolkit.home()

    @server.tool()
    def launch_app(app: str) -> str:
        """Launch an app by name (e.g. "微信") or Android package name
        (e.g. "com.tencent.mm"). Unknown games usually need the package name,
        query it with: adb shell pm list packages."""
        return toolkit.launch_app(app)

    @server.tool()
    def wait(seconds: float = 1.0) -> str:
        """Wait for screen content to change (loading, opponent's move, etc.).
        Clamped to 0.1-30 seconds."""
        return toolkit.wait(seconds)

    @server.tool()
    def get_clipboard() -> str:
        """Get the current text content from the device clipboard."""
        return toolkit.get_clipboard()

    @server.tool()
    def set_clipboard(text: str) -> str:
        """Set text into the device clipboard (for pasting long text, tokens, or URLs)."""
        return toolkit.set_clipboard(text)

    @server.tool()
    def batch_actions(actions: list[dict[str, Any]]) -> dict[str, Any]:
        """Execute a batch of sequential device actions in a single roundtrip.

        Supported actions in the list:
        - tap: {"action": "tap", "x": 100, "y": 200}
        - double_tap: {"action": "double_tap", "x": 100, "y": 200}
        - long_press: {"action": "long_press", "x": 100, "y": 200, "duration_ms": 1000}
        - swipe: {"action": "swipe", "start_x": 100, "start_y": 200, "end_x": 300, "end_y": 400, "duration_ms": 500}
        - move_piece: {"action": "move_piece", "from_x": 100, "from_y": 200, "to_x": 300, "to_y": 400, "interval_ms": 300}
        - type_text: {"action": "type_text", "text": "hello", "clear": false}
        - set_clipboard: {"action": "set_clipboard", "text": "hello"}
        - wait: {"action": "wait", "seconds": 0.5}
        - back: {"action": "back"}
        - home: {"action": "home"}
        - launch_app: {"action": "launch_app", "app": "微信"}
        - force_stop_app: {"action": "force_stop_app", "app": "微信"}

        Executes sequentially under device lock and stops immediately on first failure.
        """
        return toolkit.batch_actions(actions)

    @server.tool()
    def force_stop_app(app: str) -> str:
        """Force stop a running app by name (e.g. "微信") or package name (e.g. "com.tencent.mm")."""
        return toolkit.force_stop_app(app)

    @server.tool()
    def clear_app_data(app: str) -> str:
        """Clear all user data and caches for an app (resets it to initial state)."""
        return toolkit.clear_app_data(app)

    @server.tool()
    def install_app(path: str) -> str:
        """Install an APK file onto the device from a local file path."""
        return toolkit.install_app(path)

    return server


def _resolve_device_id(explicit: str | None) -> str | None:
    """Resolve the target device: CLI arg > env var > first online device."""
    if explicit:
        return explicit
    env_device = os.getenv(_DEVICE_ID_ENV)
    if env_device:
        return env_device
    online = [d for d in adb.list_devices() if d.status == "device"]
    if not online:
        return None
    if len(online) > 1:
        print(
            f"ℹ️ 检测到多台设备，已自动选择: {online[0].device_id}"
            f"（可用 --device-id 指定）",
            file=sys.stderr,
        )
    return online[0].device_id


def _validate_environment(device_id: str | None) -> str:
    """Check adb availability, device connection and ADB Keyboard.

    All output goes to stderr (stdout is the JSON-RPC channel).
    Returns the resolved device_id. Exits with code 2 on fatal problems.
    """
    print("🔍 检查系统环境...", file=sys.stderr)

    if shutil.which("adb") is None:
        print("❌ 未找到 adb 命令，请先安装 Android Platform Tools:", file=sys.stderr)
        print("  macOS:   brew install android-platform-tools", file=sys.stderr)
        print("  Linux:   sudo apt install adb", file=sys.stderr)
        print(
            "  Windows: https://developer.android.com/tools/releases/platform-tools",
            file=sys.stderr,
        )
        raise SystemExit(2)

    devices = adb.list_devices()
    online = [d for d in devices if d.status == "device"]
    if not online:
        print(
            "❌ 没有已连接的 Android 设备。请用 usb 连接并在设备上授权调试，",
            file=sys.stderr,
        )
        print("   或用 adb connect <ip:port> 连接无线设备。", file=sys.stderr)
        raise SystemExit(2)

    if device_id is None:
        device_id = _resolve_device_id(None)
        if device_id is None:
            print("❌ 无法确定目标设备。", file=sys.stderr)
            raise SystemExit(2)

    if device_id not in {d.device_id for d in online}:
        print(f"❌ 设备 {device_id} 不在线。当前在线设备:", file=sys.stderr)
        for d in online:
            print(f"   - {d.device_id}", file=sys.stderr)
        raise SystemExit(2)

    # ADB Keyboard is optional: only type_text needs it.
    try:
        result = _run_ime_list(device_id)
        if ADB_IME in result:
            print("✅ ADB Keyboard 可用", file=sys.stderr)
        else:
            print(
                "⚠️ 未检测到 ADB Keyboard，type_text 工具将不可用（截图/点击不受影响）",
                file=sys.stderr,
            )
    except Exception as e:
        print(f"⚠️ 无法检查 ADB Keyboard: {e}", file=sys.stderr)

    print(f"✅ 环境检查通过，目标设备: {device_id}", file=sys.stderr)
    return device_id


def _run_ime_list(device_id: str) -> str:
    """Run `adb shell ime list -s` and return its output."""
    result = subprocess.run(
        ["adb", "-s", device_id, "shell", "ime", "list", "-s"],
        capture_output=True,
        text=True,
        timeout=10,
        stdin=subprocess.DEVNULL,
    )
    return (result.stdout or "") + (result.stderr or "")


def run_mcp_command(argv: list[str]) -> int:
    """Entry point for the `phone-agent mcp` subcommand."""
    parser = argparse.ArgumentParser(
        prog="phone-agent mcp",
        description="启动 MCP server，向 Claude Code 等 MCP 客户端暴露 Android 设备控制工具",
    )
    parser.add_argument(
        "--device-id",
        "-d",
        default=None,
        help=f"ADB 设备 ID（缺省读取环境变量 {_DEVICE_ID_ENV}，再缺省取第一台在线设备）",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http", "sse"],
        default="stdio",
        help="传输协议: stdio (默认，本地启动) / streamable-http / sse (网络服务)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="网络模式下监听主机 (默认: 127.0.0.1，设为 0.0.0.0 可供局域网/公网访问)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="网络模式下监听端口 (默认: 8000)",
    )
    parser.add_argument(
        "--listen",
        default=None,
        help="快捷网络监听参数，格式为 [host:]port (如 0.0.0.0:8000 或 8000)，自动选择 streamable-http 模式",
    )
    args = parser.parse_args(argv)

    device_id = _validate_environment(_resolve_device_id(args.device_id))

    transport = args.transport
    host = args.host
    port = args.port

    if args.listen:
        listen_str = args.listen.strip()
        if ":" in listen_str:
            h_part, p_part = listen_str.split(":", 1)
            host = h_part if h_part else "0.0.0.0"
            port = int(p_part)
        elif listen_str.isdigit():
            host = "0.0.0.0"
            port = int(listen_str)
        else:
            host = listen_str
        if "--transport" not in argv:
            transport = "streamable-http"

    set_device_type(DeviceType.ADB)
    toolkit = DeviceToolkit(device_id)
    server = create_server(toolkit, host=host, port=port)
    if transport != "stdio":
        endpoint = "/mcp" if transport == "streamable-http" else "/sse"
        print(
            f"🌐 MCP 服务器已启动 [{transport}]，监听地址: http://{host}:{port}{endpoint}",
            file=sys.stderr,
        )
    server.run(transport=transport)
    return 0
