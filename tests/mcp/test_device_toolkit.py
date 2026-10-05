"""Tests for DeviceToolkit — the device layer behind the MCP tools."""

import pytest
from mcp.types import ImageContent, TextContent

from phone_agent.adb.screenshot import Screenshot
from phone_agent.config.apps import APP_PACKAGES

DEVICE_ID = "test-device-1"


def _make_screenshot(
    base64_data="aGVsbG8=",
    width=1080,
    height=2400,
    is_sensitive=False,
    is_fallback=False,
):
    return Screenshot(
        base64_data=base64_data,
        width=width,
        height=height,
        is_sensitive=is_sensitive,
        is_fallback=is_fallback,
    )


# ----------------------------------------------------------------------
# Coordinate tools
# ----------------------------------------------------------------------


def test_tap_passes_pixel_coordinates(toolkit, fake_factory):
    result = toolkit.tap(540, 1200)

    fake_factory.tap.assert_called_once_with(540, 1200, DEVICE_ID)
    assert result == "已点击 (540, 1200)"


def test_tap_rejects_negative_coordinates(toolkit, fake_factory):
    with pytest.raises(ValueError, match="负数"):
        toolkit.tap(-1, 100)
    fake_factory.tap.assert_not_called()


def test_tap_rejects_out_of_range_after_screenshot(toolkit, fake_factory):
    fake_factory.get_screenshot.return_value = _make_screenshot()
    toolkit.screenshot()

    with pytest.raises(ValueError, match="1080x2400"):
        toolkit.tap(2000, 100)
    fake_factory.tap.assert_not_called()


def test_double_tap_passes_coordinates(toolkit, fake_factory):
    result = toolkit.double_tap(100, 200)

    fake_factory.double_tap.assert_called_once_with(100, 200, DEVICE_ID)
    assert "已双击 (100, 200)" in result


def test_long_press_defaults_to_1000ms(toolkit, fake_factory):
    result = toolkit.long_press(300, 400)

    fake_factory.long_press.assert_called_once_with(300, 400, 1000, DEVICE_ID)
    assert "1000ms" in result


def test_long_press_rejects_non_positive_duration(toolkit, fake_factory):
    with pytest.raises(ValueError, match="正数"):
        toolkit.long_press(300, 400, 0)
    fake_factory.long_press.assert_not_called()


def test_swipe_passes_none_duration_for_auto(toolkit, fake_factory):
    result = toolkit.swipe(100, 200, 300, 400)

    fake_factory.swipe.assert_called_once_with(100, 200, 300, 400, None, DEVICE_ID)
    assert "自动时长" in result


def test_swipe_with_explicit_duration(toolkit, fake_factory):
    toolkit.swipe(100, 200, 300, 400, 500)

    fake_factory.swipe.assert_called_once_with(100, 200, 300, 400, 500, DEVICE_ID)


def test_move_piece_performs_two_taps(toolkit, fake_factory, monkeypatch):
    sleeps = []
    monkeypatch.setattr("phone_agent.mcp_server.time.sleep", sleeps.append)

    result = toolkit.move_piece(100, 200, 300, 400, interval_ms=250)

    assert fake_factory.tap.call_count == 2
    assert fake_factory.tap.call_args_list[0].args == (100, 200, DEVICE_ID)
    assert fake_factory.tap.call_args_list[1].args == (300, 400, DEVICE_ID)
    assert sleeps == [0.25]
    assert "从 (100, 200) 移动到 (300, 400)" in result


def test_move_piece_rejects_negative_interval(toolkit):
    with pytest.raises(ValueError, match="负数"):
        toolkit.move_piece(10, 20, 30, 40, interval_ms=-1)


def test_back_and_home(toolkit, fake_factory):
    assert "返回键" in toolkit.back()
    fake_factory.back.assert_called_once_with(DEVICE_ID)

    assert "主页键" in toolkit.home()
    fake_factory.home.assert_called_once_with(DEVICE_ID)


# ----------------------------------------------------------------------
# screenshot / get_current_app
# ----------------------------------------------------------------------


def test_screenshot_returns_image_and_text(toolkit, fake_factory, fake_adb):
    fake_factory.get_screenshot.return_value = _make_screenshot()
    fake_adb.get_current_app_info.return_value = ("微信", "com.tencent.mm")

    result = toolkit.screenshot()

    assert len(result) == 2
    image, text = result
    assert isinstance(image, ImageContent)
    assert image.data == "aGVsbG8="
    dumped = image.model_dump()
    assert (dumped.get("mime_type") or dumped.get("mimeType")) == "image/png"
    assert isinstance(text, TextContent)
    assert "1080x2400" in text.text
    assert "微信 (com.tencent.mm)" in text.text
    assert "⚠️" not in text.text


def test_screenshot_sensitive_warning(toolkit, fake_factory, fake_adb):
    fake_factory.get_screenshot.return_value = _make_screenshot(
        is_sensitive=True, is_fallback=True
    )

    text = toolkit.screenshot()[1]

    assert "安全策略" in text.text


def test_screenshot_fallback_warning(toolkit, fake_factory, fake_adb):
    fake_factory.get_screenshot.return_value = _make_screenshot(is_fallback=True)

    text = toolkit.screenshot()[1]

    assert "截图失败" in text.text


def test_screenshot_records_screen_size(toolkit, fake_factory, fake_adb):
    fake_factory.get_screenshot.return_value = _make_screenshot(width=720, height=1600)
    toolkit.screenshot()

    # In-range for 720x1600 but out of range for the default 1080x2400.
    toolkit.tap(700, 1500)
    with pytest.raises(ValueError):
        toolkit.tap(719, 1600)


def test_screenshot_app_info_failure_is_reported_not_raised(
    toolkit, fake_factory, fake_adb
):
    fake_factory.get_screenshot.return_value = _make_screenshot()
    fake_adb.get_current_app_info.side_effect = ValueError("dumpsys empty")

    text = toolkit.screenshot()[1]

    assert "断连" in text.text


def test_screenshot_downscale_and_coordinate_mapping(toolkit, fake_factory, fake_adb):
    import base64
    from io import BytesIO
    from PIL import Image

    img = Image.new("RGB", (1000, 2000), color=(255, 0, 0))
    buf = BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    fake_factory.get_screenshot.return_value = _make_screenshot(
        base64_data=b64, width=1000, height=2000
    )
    fake_adb.get_current_app_info.return_value = ("桌面", "com.launcher")

    result = toolkit.screenshot(max_dimension=500)
    image, text = result

    assert "250x500" in text.text
    assert "已按比例缩放" in text.text
    dumped = image.model_dump()
    assert (dumped.get("mime_type") or dumped.get("mimeType")) == "image/jpeg"

    # Tap using scaled coordinates (50, 100) -> should map to (200, 400)
    toolkit.tap(50, 100)
    fake_factory.tap.assert_called_once_with(200, 400, DEVICE_ID)


def test_screenshot_env_max_dimension(toolkit, fake_factory, fake_adb, monkeypatch):
    import base64
    from io import BytesIO
    from PIL import Image

    monkeypatch.setenv("PHONE_AGENT_SCREENSHOT_MAX_DIM", "500")
    img = Image.new("RGB", (1000, 2000), color=(255, 0, 0))
    buf = BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    fake_factory.get_screenshot.return_value = _make_screenshot(
        base64_data=b64, width=1000, height=2000
    )
    fake_adb.get_current_app_info.return_value = ("桌面", "com.launcher")

    result = toolkit.screenshot()
    assert "250x500" in result[1].text


def test_get_current_app_success(toolkit, fake_adb):
    fake_adb.get_current_app_info.return_value = ("微信", "com.tencent.mm")

    assert toolkit.get_current_app() == "微信 (com.tencent.mm)"


def test_get_current_app_disconnected(toolkit, fake_adb):
    fake_adb.get_current_app_info.side_effect = ValueError("No output")

    with pytest.raises(RuntimeError, match="断连"):
        toolkit.get_current_app()


# ----------------------------------------------------------------------
# type_text
# ----------------------------------------------------------------------


def test_type_text_success_flow(toolkit, fake_factory, no_sleep):
    fake_factory.detect_and_set_adb_keyboard.return_value = "original.ime/.IME"

    result = toolkit.type_text("你好世界")

    assert "4 个字符" in result
    fake_factory.clear_text.assert_not_called()
    fake_factory.type_text.assert_called_once_with("你好世界", DEVICE_ID)
    fake_factory.restore_keyboard.assert_called_once_with(
        "original.ime/.IME", DEVICE_ID
    )


def test_type_text_with_clear(toolkit, fake_factory, no_sleep):
    fake_factory.detect_and_set_adb_keyboard.return_value = ""

    toolkit.type_text("abc", clear=True)

    fake_factory.clear_text.assert_called_once_with(DEVICE_ID)
    fake_factory.type_text.assert_called_once_with("abc", DEVICE_ID)
    # Empty original IME means nothing to restore.
    fake_factory.restore_keyboard.assert_not_called()


def test_type_text_ime_verification_failure(toolkit, fake_factory, fake_adb, no_sleep):
    fake_factory.detect_and_set_adb_keyboard.return_value = "original.ime/.IME"
    fake_adb.get_current_ime.return_value = "original.ime/.IME"  # switch did not stick

    with pytest.raises(RuntimeError, match="ADB Keyboard"):
        toolkit.type_text("abc")

    fake_factory.type_text.assert_not_called()
    # finally-branch must still restore the keyboard.
    fake_factory.restore_keyboard.assert_called_once_with(
        "original.ime/.IME", DEVICE_ID
    )


# ----------------------------------------------------------------------
# launch_app
# ----------------------------------------------------------------------


def test_launch_app_by_mapped_name(toolkit, fake_factory, fake_adb):
    fake_adb.get_current_app_info.return_value = ("微信", APP_PACKAGES["微信"])

    result = toolkit.launch_app("微信")

    fake_factory.launch_app.assert_called_once_with("微信", DEVICE_ID)
    assert "已启动 微信" in result
    assert "当前前台: com.tencent.mm" in result


def test_launch_app_by_package_name(toolkit, fake_factory, fake_adb):
    fake_adb.get_current_app_info.return_value = ("com.junqi.game", "com.junqi.game")

    result = toolkit.launch_app("com.junqi.game")

    fake_adb.launch_app_by_package.assert_called_once_with("com.junqi.game", DEVICE_ID)
    fake_factory.launch_app.assert_not_called()
    assert "已启动 com.junqi.game" in result


def test_launch_app_unknown_name_raises_with_examples(toolkit):
    with pytest.raises(ValueError, match="pm list packages") as excinfo:
        toolkit.launch_app("不存在的应用")

    # Error message lists built-in app names as examples.
    assert "微信" in str(excinfo.value)
    assert "淘宝" in str(excinfo.value)


def test_launch_app_foreground_mismatch_reported(toolkit, fake_factory, fake_adb):
    fake_adb.get_current_app_info.return_value = ("System Home", "unknown")

    result = toolkit.launch_app("微信")

    assert "当前前台应用是 unknown" in result
    assert "建议 screenshot" in result


# ----------------------------------------------------------------------
# wait
# ----------------------------------------------------------------------


def test_wait_clamps_seconds(toolkit, monkeypatch):
    sleeps = []
    monkeypatch.setattr("phone_agent.mcp_server.time.sleep", sleeps.append)

    toolkit.wait(0.01)
    toolkit.wait(60)
    toolkit.wait(2)

    assert sleeps == [0.1, 30.0, 2]


# ----------------------------------------------------------------------
# Concurrency
# ----------------------------------------------------------------------


def test_device_calls_are_serialized(toolkit, fake_factory):
    """Two device-touching calls from different threads must not interleave."""
    import threading as threading_mod
    import time as time_mod

    active = 0
    max_active = 0
    guard = threading_mod.Lock()

    def slow_tap(x, y, device_id):
        nonlocal active, max_active
        with guard:
            active += 1
            max_active = max(max_active, active)
        time_mod.sleep(0.05)  # give other threads a chance to interleave
        with guard:
            active -= 1

    fake_factory.tap.side_effect = slow_tap

    threads = [threading_mod.Thread(target=toolkit.tap, args=(i, i)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert max_active == 1


# ----------------------------------------------------------------------
# Clipboard tools
# ----------------------------------------------------------------------


def test_get_clipboard_success(toolkit, fake_factory):
    fake_factory.get_clipboard.return_value = "hello from clipboard"

    result = toolkit.get_clipboard()

    assert result == "hello from clipboard"
    fake_factory.get_clipboard.assert_called_once_with(DEVICE_ID)


def test_get_clipboard_failure_raises(toolkit, fake_factory):
    fake_factory.get_clipboard.side_effect = RuntimeError("ADB error")

    with pytest.raises(RuntimeError, match="获取剪贴板失败"):
        toolkit.get_clipboard()


def test_set_clipboard_success(toolkit, fake_factory):
    result = toolkit.set_clipboard("my-token-123")

    fake_factory.set_clipboard.assert_called_once_with("my-token-123", DEVICE_ID)
    assert "12 字符" in result


def test_set_clipboard_failure_raises(toolkit, fake_factory):
    fake_factory.set_clipboard.side_effect = RuntimeError("ADB error")

    with pytest.raises(RuntimeError, match="写入剪贴板失败"):
        toolkit.set_clipboard("test")


# ----------------------------------------------------------------------
# batch_actions
# ----------------------------------------------------------------------


def test_batch_actions_empty(toolkit):
    result = toolkit.batch_actions([])
    assert result["success"] is True
    assert result["total"] == 0
    assert result["executed"] == 0
    assert result["results"] == []


def test_batch_actions_success_sequence(toolkit, fake_factory, no_sleep):
    actions = [
        {"action": "tap", "x": 100, "y": 200},
        {"action": "wait", "seconds": 0.5},
        {"action": "set_clipboard", "text": "paste me"},
        {"action": "back"},
    ]

    result = toolkit.batch_actions(actions)

    assert result["success"] is True
    assert result["total"] == 4
    assert result["executed"] == 4
    assert len(result["results"]) == 4

    fake_factory.tap.assert_called_once_with(100, 200, DEVICE_ID)
    fake_factory.set_clipboard.assert_called_once_with("paste me", DEVICE_ID)
    fake_factory.back.assert_called_once_with(DEVICE_ID)


def test_batch_actions_stops_on_first_error(toolkit, fake_factory):
    actions = [
        {"action": "tap", "x": 100, "y": 200},
        {"action": "tap", "x": -10, "y": 200},  # will fail coordinate check
        {"action": "back"},                     # should not be reached
    ]

    result = toolkit.batch_actions(actions)

    assert result["success"] is False
    assert result["total"] == 3
    assert result["executed"] == 1
    assert "负数" in result["error"]
    assert len(result["results"]) == 2
    assert result["results"][0]["status"] == "success"
    assert result["results"][1]["status"] == "failed"

    fake_factory.tap.assert_called_once_with(100, 200, DEVICE_ID)
    fake_factory.back.assert_not_called()


def test_batch_actions_invalid_structure(toolkit):
    res1 = toolkit.batch_actions(["not a dict"])
    assert res1["success"] is False
    assert "格式错误" in res1["error"]

    res2 = toolkit.batch_actions([{}])
    assert res2["success"] is False
    assert "缺少有效" in res2["error"]


def test_batch_actions_unsupported_action(toolkit):
    result = toolkit.batch_actions([{"action": "unsupported_command"}])
    assert result["success"] is False
    assert "不支持的动作类型" in result["error"]


# ----------------------------------------------------------------------
# App lifecycle tools
# ----------------------------------------------------------------------


def test_force_stop_app_success(toolkit, fake_factory):
    result = toolkit.force_stop_app("微信")
    fake_factory.force_stop_app.assert_called_once_with("微信", DEVICE_ID)
    assert "已强制停止应用: 微信" in result


def test_force_stop_app_failure(toolkit, fake_factory):
    fake_factory.force_stop_app.side_effect = RuntimeError("failed to stop")
    with pytest.raises(RuntimeError, match="停止应用失败"):
        toolkit.force_stop_app("微信")


def test_clear_app_data_success(toolkit, fake_factory):
    result = toolkit.clear_app_data("com.tencent.mm")
    fake_factory.clear_app_data.assert_called_once_with("com.tencent.mm", DEVICE_ID)
    assert "已清理应用数据与缓存" in result


def test_clear_app_data_failure(toolkit, fake_factory):
    fake_factory.clear_app_data.side_effect = RuntimeError("pm clear error")
    with pytest.raises(RuntimeError, match="清理应用数据失败"):
        toolkit.clear_app_data("com.tencent.mm")


def test_install_app_success(toolkit, fake_factory):
    result = toolkit.install_app("/path/to/test.apk")
    fake_factory.install_app.assert_called_once_with("/path/to/test.apk", DEVICE_ID)
    assert "已成功安装应用" in result


def test_install_app_failure(toolkit, fake_factory):
    fake_factory.install_app.side_effect = RuntimeError("install failed")
    with pytest.raises(RuntimeError, match="安装应用失败"):
        toolkit.install_app("/path/to/test.apk")


def test_batch_actions_with_force_stop(toolkit, fake_factory):
    actions = [
        {"action": "force_stop_app", "app": "微信"},
        {"action": "launch_app", "app": "微信"},
    ]
    result = toolkit.batch_actions(actions)
    assert result["success"] is True
    assert result["total"] == 2
    fake_factory.force_stop_app.assert_called_once_with("微信", DEVICE_ID)


# ----------------------------------------------------------------------
# Orientation tools
# ----------------------------------------------------------------------


def test_get_orientation_success(toolkit, fake_factory):
    fake_factory.get_orientation.return_value = {
        "orientation": "landscape",
        "rotation": 1,
        "is_landscape": True,
    }
    res = toolkit.get_orientation()
    assert res["orientation"] == "landscape"
    assert res["is_landscape"] is True
    fake_factory.get_orientation.assert_called_once_with(DEVICE_ID)


def test_get_orientation_failure(toolkit, fake_factory):
    fake_factory.get_orientation.side_effect = RuntimeError("failed to read orientation")
    with pytest.raises(RuntimeError, match="获取屏幕方向失败"):
        toolkit.get_orientation()


def test_set_orientation_success(toolkit, fake_factory):
    res = toolkit.set_orientation("landscape")
    fake_factory.set_orientation.assert_called_once_with("landscape", DEVICE_ID)
    assert "已将屏幕方向设置为: landscape" in res


def test_set_orientation_failure(toolkit, fake_factory):
    fake_factory.set_orientation.side_effect = RuntimeError("failed to set orientation")
    with pytest.raises(RuntimeError, match="设置屏幕方向失败"):
        toolkit.set_orientation("portrait")


def test_screenshot_landscape_text_and_coordinates(toolkit, fake_factory, fake_adb):
    import base64
    from io import BytesIO
    from PIL import Image

    # Create landscape image: 2400 x 1080 (width > height)
    img = Image.new("RGB", (2400, 1080), color=(0, 255, 0))
    buf = BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    fake_factory.get_screenshot.return_value = _make_screenshot(
        base64_data=b64, width=2400, height=1080
    )
    fake_adb.get_current_app_info.return_value = ("军旗手游", "com.junqi.game")

    _, text = toolkit.screenshot()
    assert "横屏 (landscape)" in text.text
    assert "2400x1080" in text.text

    # Tap within landscape boundary: (2000, 500) must succeed without out-of-range error
    tap_res = toolkit.tap(2000, 500)
    assert "已点击 (2000, 500)" in tap_res
    fake_factory.tap.assert_called_once_with(2000, 500, DEVICE_ID)


def test_batch_actions_with_set_orientation(toolkit, fake_factory):
    actions = [
        {"action": "set_orientation", "orientation": "landscape"},
        {"action": "wait", "seconds": 0.5},
    ]
    result = toolkit.batch_actions(actions)
    assert result["success"] is True
    fake_factory.set_orientation.assert_called_once_with("landscape", DEVICE_ID)



