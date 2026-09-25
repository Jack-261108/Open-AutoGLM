"""Tests for DeviceFactory iOS integration and unified PhoneAgent iOS support."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from phone_agent.agent import AgentConfig, PhoneAgent
from phone_agent.config.timing import TIMING_CONFIG
from phone_agent.device_factory import DeviceFactory, DeviceType, set_device_type, get_device_factory


def test_device_factory_ios_delegation(monkeypatch):
    import phone_agent.xctest as xctest_pkg
    import phone_agent.xctest.input as xctest_input

    mock_screenshot = MagicMock(return_value=SimpleNamespace(base64_data="ios-shot", width=1170, height=2532))
    mock_get_current_app = MagicMock(return_value="Safari")
    mock_tap = MagicMock()
    mock_double_tap = MagicMock()
    mock_long_press = MagicMock()
    mock_swipe = MagicMock()
    mock_back = MagicMock()
    mock_home = MagicMock()
    mock_launch_app = MagicMock(return_value=True)
    mock_type_text = MagicMock()
    mock_clear_text = MagicMock()
    mock_hide_keyboard = MagicMock()
    mock_list_devices = MagicMock(return_value=["device-udid"])

    monkeypatch.setattr(xctest_pkg, "get_screenshot", mock_screenshot)
    monkeypatch.setattr(xctest_pkg, "get_current_app", mock_get_current_app)
    monkeypatch.setattr(xctest_pkg, "tap", mock_tap)
    monkeypatch.setattr(xctest_pkg, "double_tap", mock_double_tap)
    monkeypatch.setattr(xctest_pkg, "long_press", mock_long_press)
    monkeypatch.setattr(xctest_pkg, "swipe", mock_swipe)
    monkeypatch.setattr(xctest_pkg, "back", mock_back)
    monkeypatch.setattr(xctest_pkg, "home", mock_home)
    monkeypatch.setattr(xctest_pkg, "launch_app", mock_launch_app)
    monkeypatch.setattr(xctest_pkg, "type_text", mock_type_text)
    monkeypatch.setattr(xctest_pkg, "clear_text", mock_clear_text)
    monkeypatch.setattr(xctest_pkg, "list_devices", mock_list_devices)
    monkeypatch.setattr(xctest_input, "hide_keyboard", mock_hide_keyboard)

    factory = DeviceFactory(
        DeviceType.IOS,
        wda_url="http://wda.custom:8100",
        session_id="session-123",
    )

    shot = factory.get_screenshot()
    assert shot.base64_data == "ios-shot"
    mock_screenshot.assert_called_once_with(
        wda_url="http://wda.custom:8100",
        session_id="session-123",
        device_id=None,
        timeout=10,
    )

    assert factory.get_current_app() == "Safari"
    mock_get_current_app.assert_called_once_with(
        wda_url="http://wda.custom:8100",
        session_id="session-123",
    )

    factory.tap(100, 200)
    mock_tap.assert_called_once_with(
        100,
        200,
        wda_url="http://wda.custom:8100",
        session_id="session-123",
        delay=1.0,
    )

    factory.double_tap(150, 250)
    mock_double_tap.assert_called_once_with(
        150,
        250,
        wda_url="http://wda.custom:8100",
        session_id="session-123",
        delay=1.0,
    )

    factory.long_press(300, 400, duration_ms=2000)
    mock_long_press.assert_called_once_with(
        300,
        400,
        duration=2.0,
        wda_url="http://wda.custom:8100",
        session_id="session-123",
        delay=1.0,
    )

    factory.swipe(10, 20, 30, 40, duration_ms=800)
    mock_swipe.assert_called_once_with(
        10,
        20,
        30,
        40,
        duration=0.8,
        wda_url="http://wda.custom:8100",
        session_id="session-123",
        delay=TIMING_CONFIG.device.default_swipe_delay,
    )

    mock_swipe.reset_mock()
    factory.swipe(1, 2, 3, 4)
    mock_swipe.assert_called_once_with(
        1,
        2,
        3,
        4,
        duration=None,
        wda_url="http://wda.custom:8100",
        session_id="session-123",
        delay=TIMING_CONFIG.device.default_swipe_delay,
    )

    factory.back()
    mock_back.assert_called_once_with(
        wda_url="http://wda.custom:8100",
        session_id="session-123",
        delay=1.0,
    )

    factory.home()
    mock_home.assert_called_once_with(
        wda_url="http://wda.custom:8100",
        session_id="session-123",
        delay=1.0,
    )

    assert factory.launch_app("Settings") is True
    mock_launch_app.assert_called_once_with(
        "Settings",
        wda_url="http://wda.custom:8100",
        session_id="session-123",
        delay=TIMING_CONFIG.device.default_launch_delay,
    )

    factory.type_text("hello ios")
    mock_type_text.assert_called_once_with(
        "hello ios",
        wda_url="http://wda.custom:8100",
        session_id="session-123",
    )

    factory.clear_text()
    mock_clear_text.assert_called_once_with(
        wda_url="http://wda.custom:8100",
        session_id="session-123",
    )

    factory.hide_keyboard()
    mock_hide_keyboard.assert_called_once_with(
        wda_url="http://wda.custom:8100",
        session_id="session-123",
    )

    assert factory.detect_and_set_adb_keyboard() == ""
    assert factory.restore_keyboard("dummy") is None

    assert factory.list_devices() == ["device-udid"]
    from phone_agent.xctest import XCTestConnection
    assert factory.get_connection_class() is XCTestConnection


def test_set_device_type_ios():
    import phone_agent.device_factory as device_factory_module

    previous = device_factory_module._device_factory
    try:
        set_device_type(
            DeviceType.IOS, wda_url="http://test-wda:8100", session_id="test-session"
        )
        factory = get_device_factory()
        assert factory.device_type == DeviceType.IOS
        assert factory.wda_url == "http://test-wda:8100"
        assert factory.session_id == "test-session"
    finally:
        device_factory_module._device_factory = previous


def test_universal_phone_agent_direct_ios(monkeypatch, fake_model_client_factory, response_factory):
    fake_screenshot = SimpleNamespace(base64_data="shot", width=1170, height=2532)
    fake_ios_factory = SimpleNamespace(
        get_screenshot=MagicMock(return_value=fake_screenshot),
        get_current_app=MagicMock(return_value="Maps"),
        tap=MagicMock(),
        launch_app=MagicMock(return_value=True),
        hide_keyboard=MagicMock(),
    )
    monkeypatch.setattr(
        "phone_agent.agent.DeviceFactory",
        lambda *_args, **_kwargs: fake_ios_factory,
    )

    client = fake_model_client_factory(
        response_factory(parsed_action={"_metadata": "do", "action": "Tap", "element": [500, 500]}),
        response_factory(parsed_action={"_metadata": "finish", "message": "done"}),
    )

    config = AgentConfig(
        device_type=DeviceType.IOS,
        wda_url="http://custom:8100",
        session_id="my-session",
        verbose=False,
    )
    agent = PhoneAgent(agent_config=config, model_client=client)

    result = agent.step("open maps and tap")
    assert result.success is True
    assert result.action == {"_metadata": "do", "action": "Tap", "element": [500, 500]}
    fake_ios_factory.get_screenshot.assert_called_once()
    fake_ios_factory.get_current_app.assert_called_once()
