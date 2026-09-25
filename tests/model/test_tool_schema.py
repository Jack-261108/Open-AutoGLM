"""Tests for strict phone action schemas and normalization."""

import pytest

from phone_agent.model.base import RawToolCall, ModelResponseError
from phone_agent.model.tool_schema import (
    FINISH_TOOL,
    PHONE_ACTION_TOOL,
    format_action,
    get_tool_schemas,
    normalize_finish,
    normalize_phone_action,
    normalize_tool_call,
)


@pytest.mark.parametrize(
    ("arguments", "expected_action"),
    [
        ({"action": "Launch", "app": "Settings"}, "do(action='Launch', app='Settings')"),
        ({"action": "Tap", "element": [0, 999]}, "do(action='Tap', element=[0, 999])"),
        (
            {"action": "Tap", "element": [100, 200], "message": "Confirm"},
            "do(action='Tap', element=[100, 200], message='Confirm')",
        ),
        ({"action": "Type", "text": "hello"}, "do(action='Type', text='hello')"),
        (
            {"action": "Type_Name", "text": "Jack"},
            "do(action='Type_Name', text='Jack')",
        ),
        (
            {"action": "Swipe", "start": [1, 2], "end": [998, 999]},
            "do(action='Swipe', start=[1, 2], end=[998, 999])",
        ),
        ({"action": "Back"}, "do(action='Back')"),
        ({"action": "Home"}, "do(action='Home')"),
        ({"action": "Interact"}, "do(action='Interact')"),
        (
            {"action": "Interact", "message": "Choose option"},
            "do(action='Interact', message='Choose option')",
        ),
        (
            {"action": "Double Tap", "element": [10, 20]},
            "do(action='Double Tap', element=[10, 20])",
        ),
        (
            {"action": "Long Press", "element": [10, 20]},
            "do(action='Long Press', element=[10, 20])",
        ),
        ({"action": "Wait", "duration": "2 seconds"}, "do(action='Wait', duration='2 seconds')"),
        (
            {"action": "Take_over", "message": "Log in"},
            "do(action='Take_over', message='Log in')",
        ),
        ({"action": "Note", "message": "Saved"}, "do(action='Note', message='Saved')"),
        (
            {"action": "Call_API", "instruction": "Summarize"},
            "do(action='Call_API', instruction='Summarize')",
        ),
    ],
)
def test_normalize_and_format_all_supported_actions(arguments, expected_action):
    normalized = normalize_phone_action(arguments)

    assert normalized["_metadata"] == "do"
    assert format_action(normalized) == expected_action


def test_finish_normalization_and_formatting():
    normalized = normalize_finish({"message": "Task completed."})

    assert normalized == {"_metadata": "finish", "message": "Task completed."}
    assert format_action(normalized) == "finish(message='Task completed.')"


def test_type_format_uses_repr_without_losing_escapes():
    text = "line 1\nline 2\\path and 'quote'"
    normalized = normalize_phone_action({"action": "Type", "text": text})

    assert format_action(normalized) == f"do(action='Type', text={text!r})"


def test_provider_neutral_schemas_are_strict_and_independent(monkeypatch):
    assert PHONE_ACTION_TOOL["name"] == "phone_action"
    assert FINISH_TOOL["name"] == "finish"
    assert all(
        variant["additionalProperties"] is False
        for variant in PHONE_ACTION_TOOL["input_schema"]["oneOf"]
    )
    assert FINISH_TOOL["input_schema"]["additionalProperties"] is False

    schemas = get_tool_schemas()
    schemas[0]["name"] = "changed"
    assert PHONE_ACTION_TOOL["name"] == "phone_action"

    monkeypatch.setitem(PHONE_ACTION_TOOL, "name", "mutated")
    assert get_tool_schemas()[0]["name"] == "phone_action"


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"action": 1},
        {"action": "Unknown"},
        {"action": "Launch"},
        {"action": "Back", "message": "extra"},
        {"action": "Tap"},
        {"action": "Tap", "element": (1, 2)},
        {"action": "Tap", "element": [1]},
        {"action": "Tap", "element": [1, 2, 3]},
        {"action": "Tap", "element": [True, 2]},
        {"action": "Tap", "element": [1.0, 2]},
        {"action": "Tap", "element": [-1, 2]},
        {"action": "Tap", "element": [1, 1000]},
        {"action": "Tap", "element": [1, 2], "message": False},
        {"action": "Swipe", "start": [1, 2]},
        {"action": "Type", "text": 123},
        {"action": "Wait", "duration": 2},
    ],
)
def test_invalid_phone_actions_are_rejected(arguments):
    with pytest.raises(ModelResponseError):
        normalize_phone_action(arguments)


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"message": 1},
        {"message": "done", "extra": True},
    ],
)
def test_invalid_finish_actions_are_rejected(arguments):
    with pytest.raises(ModelResponseError):
        normalize_finish(arguments)


def test_normalize_tool_call_accepts_dict_and_strict_json_string():
    expected = {"_metadata": "do", "action": "Tap", "element": [10, 20]}

    assert normalize_tool_call("phone_action", {"action": "Tap", "element": [10, 20]}) == expected
    assert normalize_tool_call(
        RawToolCall("phone_action", '{"action":"Tap","element":[10,20]}')
    ) == expected


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("unknown", {}),
        ("phone_action", "{"),
        ("phone_action", "[]"),
        ("phone_action", '{"action":"Back","action":"Home"}'),
        ("finish", {"message": "done", "extra": 1}),
    ],
)
def test_invalid_tool_calls_are_rejected(name, arguments):
    with pytest.raises(ModelResponseError):
        normalize_tool_call(name, arguments)
