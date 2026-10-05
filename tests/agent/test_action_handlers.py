"""Tests for ActionHandler and IOSActionHandler (Interact, Note, Call_API)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from phone_agent.actions.handler import ActionHandler
from phone_agent.actions.handler_ios import IOSActionHandler
from phone_agent.model import ModelResponse


def test_android_action_handler_interact_callback():
    interact_mock = MagicMock(return_value="Option B")
    handler = ActionHandler(interact_callback=interact_mock)

    action = {"_metadata": "do", "action": "Interact", "message": "Which coffee?"}
    result = handler.execute(action, 1080, 2400)

    assert result.success is True
    assert result.should_finish is False
    assert result.observation == "User choice: Option B"
    interact_mock.assert_called_once_with("Which coffee?")


def test_android_action_handler_interact_default(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: "Choice from terminal")
    handler = ActionHandler()

    action = {"_metadata": "do", "action": "Interact"}
    result = handler.execute(action, 1080, 2400)

    assert result.success is True
    assert result.observation == "User choice: Choice from terminal"


def test_android_action_handler_note_and_clear(monkeypatch):
    fake_screenshot = SimpleNamespace(base64_data="note-screenshot-data")
    fake_device = SimpleNamespace(
        get_screenshot=lambda device_id=None: fake_screenshot,
        get_current_app=lambda device_id=None: "DianpingApp",
    )
    monkeypatch.setattr(
        "phone_agent.actions.handler.get_device_factory", lambda: fake_device
    )

    handler = ActionHandler()
    assert len(handler.notes) == 0

    res1 = handler.execute(
        {"_metadata": "do", "action": "Note", "message": "First dish"},
        1080,
        2400,
    )
    assert res1.success is True
    assert "note #1 recorded" in (res1.observation or "")
    assert len(handler.notes) == 1
    assert handler.notes[0]["message"] == "First dish"
    assert handler.notes[0]["image_base64"] == "note-screenshot-data"
    assert handler.notes[0]["app"] == "DianpingApp"

    res2 = handler.execute(
        {"_metadata": "do", "action": "Note", "message": "Second dish"},
        1080,
        2400,
    )
    assert res2.success is True
    assert "note #2 recorded" in (res2.observation or "")
    assert len(handler.notes) == 2

    handler.clear_notes()
    assert len(handler.notes) == 0


def test_android_action_handler_call_api_with_callback():
    call_api_mock = MagicMock(return_value="Summary: 2 dishes recommended")
    handler = ActionHandler(call_api_callback=call_api_mock)
    handler.notes = [{"message": "dish 1"}]

    action = {"_metadata": "do", "action": "Call_API", "instruction": "Summarize dishes"}
    result = handler.execute(action, 1080, 2400)

    assert result.success is True
    assert "Summary: 2 dishes recommended" in (result.observation or "")
    call_api_mock.assert_called_once_with("Summarize dishes", handler.notes)


def test_android_action_handler_call_api_with_model_client():
    fake_client = MagicMock()
    fake_client.request.return_value = ModelResponse(
        thinking="synthesizing",
        action="finish",
        raw_content="LLM generated summary",
    )
    handler = ActionHandler(model_client=fake_client)
    handler.notes = [
        {"index": 1, "app": "AppA", "message": "first dish", "image_base64": "img-1"},
        {"index": 2, "app": "AppB", "message": "second dish", "image_base64": "img-2"},
    ]

    action = {"_metadata": "do", "action": "Call_API", "instruction": "Summarize"}
    result = handler.execute(action, 1080, 2400)

    assert result.success is True
    assert "LLM generated summary" in (result.observation or "")
    sent = str(fake_client.request.call_args.args[0])
    assert "first dish" in sent
    assert "second dish" in sent
    assert "img-1" in sent
    assert "img-2" in sent


def test_android_action_handler_call_api_fallback():
    handler = ActionHandler()
    handler.notes = [{"message": "note 1"}]

    action = {"_metadata": "do", "action": "Call_API", "instruction": "Compare"}
    result = handler.execute(action, 1080, 2400)

    assert result.success is True
    assert "Summarized 1 recorded notes" in (result.observation or "")


def test_ios_action_handler_interact_and_notes(monkeypatch):
    interact_mock = MagicMock(return_value="iOS Choice")
    handler = IOSActionHandler(interact_callback=interact_mock, verbose=False)

    res_interact = handler.execute(
        {"_metadata": "do", "action": "Interact", "message": "Select item"},
        1080,
        2400,
    )
    assert res_interact.success is True
    assert res_interact.observation == "User choice: iOS Choice"

    fake_screenshot = SimpleNamespace(base64_data="ios-screenshot")
    monkeypatch.setattr(
        "phone_agent.xctest.get_screenshot",
        lambda **kwargs: fake_screenshot,
    )
    monkeypatch.setattr(
        "phone_agent.xctest.get_current_app",
        lambda **kwargs: "Safari",
    )

    res_note = handler.execute(
        {"_metadata": "do", "action": "Note", "message": "Safari page"},
        1080,
        2400,
    )
    assert res_note.success is True
    assert "note #1 recorded" in (res_note.observation or "")
    assert len(handler.notes) == 1
    assert handler.notes[0]["app"] == "Safari"


def test_ios_action_handler_call_api():
    callback_mock = MagicMock(return_value="iOS Summary")
    handler = IOSActionHandler(call_api_callback=callback_mock, verbose=False)

    action = {"_metadata": "do", "action": "Call_API", "instruction": "Analyze"}
    result = handler.execute(action, 1080, 2400)

    assert result.success is True
    assert "iOS Summary" in (result.observation or "")


def test_android_action_handler_note_capture_failure(monkeypatch):
    def boom(device_id=None):
        raise RuntimeError("screenshot down")

    fake_device = SimpleNamespace(
        get_screenshot=boom,
        get_current_app=lambda device_id=None: "App",
    )
    monkeypatch.setattr(
        "phone_agent.actions.handler.get_device_factory", lambda: fake_device
    )
    handler = ActionHandler()

    result = handler.execute(
        {"_metadata": "do", "action": "Note", "message": "missed page"},
        1080,
        2400,
    )

    assert result.success is False
    assert handler.notes == []
    assert "screenshot down" in (result.observation or "")


def test_ios_type_skips_adb_keyboard_switch_delay(monkeypatch):
    from phone_agent.config.timing import TIMING_CONFIG

    sleeps: list[float] = []
    monkeypatch.setattr(
        "phone_agent.actions.handler.time.sleep", lambda delay: sleeps.append(delay)
    )
    monkeypatch.setattr("phone_agent.xctest.clear_text", lambda **kwargs: None)
    monkeypatch.setattr("phone_agent.xctest.type_text", lambda *args, **kwargs: None)
    monkeypatch.setattr("phone_agent.xctest.input.hide_keyboard", lambda **kwargs: None)

    handler = IOSActionHandler(wda_url="http://wda.invalid", session_id="s", verbose=False)
    result = handler.execute(
        {"_metadata": "do", "action": "Type", "text": "hi"},
        100,
        100,
    )

    assert result.success is True
    assert sleeps == [
        TIMING_CONFIG.action.text_clear_delay,
        TIMING_CONFIG.action.text_input_delay,
    ]


def test_ios_swipe_keeps_distance_based_duration(monkeypatch):
    mock_swipe = MagicMock()
    monkeypatch.setattr("phone_agent.xctest.swipe", mock_swipe)
    handler = IOSActionHandler(
        wda_url="http://wda.invalid", session_id="s", verbose=False
    )

    result = handler.execute(
        {
            "_metadata": "do",
            "action": "Swipe",
            "start": [0, 0],
            "end": [1000, 1000],
        },
        1000,
        1000,
    )

    assert result.success is True
    assert mock_swipe.call_args.kwargs["duration"] is None


def test_android_action_handler_clipboard_and_lifecycle():
    fake_device = MagicMock()
    fake_device.get_clipboard.return_value = "my clipboard text"

    handler = ActionHandler(device_factory=fake_device)

    # 1. Set_Clipboard
    res_set = handler.execute(
        {"_metadata": "do", "action": "Set_Clipboard", "text": "paste this"},
        1080,
        2400,
    )
    assert res_set.success is True
    fake_device.set_clipboard.assert_called_once_with("paste this", None)

    # 2. Get_Clipboard
    res_get = handler.execute(
        {"_metadata": "do", "action": "Get_Clipboard"},
        1080,
        2400,
    )
    assert res_get.success is True
    assert "my clipboard text" in (res_get.observation or "")
    fake_device.get_clipboard.assert_called_once_with(None)

    # 3. Force_Stop
    res_stop = handler.execute(
        {"_metadata": "do", "action": "Force_Stop", "app": "微信"},
        1080,
        2400,
    )
    assert res_stop.success is True
    fake_device.force_stop_app.assert_called_once_with("微信", None)

    # 4. Clear_Data
    res_clear = handler.execute(
        {"_metadata": "do", "action": "Clear_Data", "app": "com.tencent.mm"},
        1080,
        2400,
    )
    assert res_clear.success is True
    fake_device.clear_app_data.assert_called_once_with("com.tencent.mm", None)

    # 5. Set_Orientation
    res_orient = handler.execute(
        {"_metadata": "do", "action": "Set_Orientation", "orientation": "landscape"},
        1080,
        2400,
    )
    assert res_orient.success is True
    fake_device.set_orientation.assert_called_once_with("landscape", None)


