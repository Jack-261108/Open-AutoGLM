"""Tests for strict hybrid model response parsing."""

import json

import pytest

from phone_agent.actions.handler import parse_action
from phone_agent.model.base import RawModelOutput, RawToolCall, ModelResponseError
from phone_agent.model.response_parser import ModelResponseParser, parse_model_output


def raw(
    final_text="",
    *,
    thinking="",
    tool_calls=None,
    raw_content="",
):
    return RawModelOutput(
        thinking=thinking,
        final_text=final_text,
        tool_calls=tool_calls or [],
        raw_content=raw_content,
    )


def test_dsl_parses_thinking_and_merges_provider_thinking_in_order():
    parsed = parse_model_output(
        raw(
            "text reasoning\ndo(action='Tap', element=[100, 200])",
            thinking="provider reasoning",
            raw_content="original payload",
        )
    )

    assert parsed.thinking == "provider reasoning\ntext reasoning"
    assert parsed.action == "do(action='Tap', element=[100, 200])"
    assert parsed.parsed_action == {
        "_metadata": "do",
        "action": "Tap",
        "element": [100, 200],
    }
    assert parsed.raw_content == "original payload"


def test_finish_dsl_is_complete_and_deterministic():
    parsed = ModelResponseParser.parse(raw("finish(message='Task completed.')"))

    assert parsed.thinking == ""
    assert parsed.action == "finish(message='Task completed.')"
    assert parsed.parsed_action == {
        "_metadata": "finish",
        "message": "Task completed.",
    }


def test_identical_thinking_segments_are_not_deduplicated():
    parsed = parse_model_output(
        raw("same reasoning\ndo(action='Back')", thinking="same reasoning")
    )

    assert parsed.thinking == "same reasoning\nsame reasoning"


def test_type_dsl_preserves_quotes_backslashes_and_newlines():
    text = "line 1\nline 2\\path and 'quote'"
    parsed = parse_model_output(raw(f"do(action='Type', text={text!r})"))

    assert parsed.parsed_action["text"] == text
    assert parsed.action == f"do(action='Type', text={text!r})"


@pytest.mark.parametrize(
    ("final_text", "expected_thinking"),
    [
        (
            "<think>inspect screen</think><answer>do(action='Home')</answer>",
            "inspect screen",
        ),
        (
            "inspect screen<answer>do(action='Home')</answer>",
            "inspect screen",
        ),
        ("<answer>do(action='Home')</answer>", ""),
        ('<answer>{"action":"Home"}</answer>', ""),
        ('<answer>```json\n{"action":"Home"}\n```</answer>', ""),
    ],
)
def test_single_layer_xml_parsing(final_text, expected_thinking):
    parsed = parse_model_output(raw(final_text))

    assert parsed.thinking == expected_thinking
    assert parsed.action == "do(action='Home')"


@pytest.mark.parametrize(
    "final_text",
    [
        '{"action":"Tap","element":[10,20]}',
        '```json\n{"action":"Tap","element":[10,20]}\n```',
        '{"name":"phone_action","arguments":{"action":"Tap","element":[10,20]}}',
        '{"name":"phone_action","arguments":"{\\"action\\":\\"Tap\\",\\"element\\":[10,20]}"}',
    ],
)
def test_limited_json_forms_parse(final_text):
    parsed = parse_model_output(raw(final_text))

    assert parsed.action == "do(action='Tap', element=[10, 20])"
    assert parsed.parsed_action["element"] == [10, 20]


@pytest.mark.parametrize(
    "final_text",
    [
        '{"action":"finish","message":"done"}',
        '{"name":"finish","arguments":{"message":"done"}}',
        '{"name":"finish","arguments":"{\\"message\\":\\"done\\"}"}',
    ],
)
def test_json_finish_forms_parse(final_text):
    parsed = parse_model_output(raw(final_text))

    assert parsed.action == "finish(message='done')"
    assert parsed.parsed_action == {"_metadata": "finish", "message": "done"}


def test_native_tool_call_has_priority_and_plain_final_text_is_thinking():
    parsed = parse_model_output(
        raw(
            "I will tap the visible confirmation button.",
            thinking="provider reasoning",
            tool_calls=[
                RawToolCall(
                    "phone_action", {"action": "Tap", "element": [100, 200]}
                )
            ],
            raw_content="provider text payload",
        )
    )

    assert parsed.thinking == (
        "provider reasoning\nI will tap the visible confirmation button."
    )
    assert parsed.action == "do(action='Tap', element=[100, 200])"
    assert parsed.raw_content == "provider text payload"


def test_tool_call_accepts_text_think_block_without_nesting_history():
    parsed = parse_model_output(
        raw(
            "<think>text reasoning</think>",
            thinking="provider reasoning",
            tool_calls=[RawToolCall("finish", {"message": "done"})],
        )
    )

    assert parsed.thinking == "provider reasoning\ntext reasoning"


@pytest.mark.parametrize(
    "final_text",
    [
        '{"note":"still thinking"}',
        'The word "action": describes what happens next.',
        '<think>thinking</think>\nOpening the app...',
        '<think>I should do(action="Launch", app="粉笔")</think>\nOpening app...',
        '<think>thinking</think>\ndo(action="Launch", app="粉笔")',
        '<think>thinking</think>\n<answer>do(action="Launch", app="粉笔")</answer>',
        '<think>thinking</think>\n<answer>do(action="Launch", app="粉笔")',
    ],
)
def test_tool_call_with_thinking_and_echoed_actions_succeeds(final_text):
    parsed = parse_model_output(
        raw(
            final_text,
            tool_calls=[RawToolCall("phone_action", {"action": "Launch", "app": "粉笔"})],
        )
    )

    assert parsed.parsed_action == {
        "_metadata": "do",
        "action": "Launch",
        "app": "粉笔",
    }
    assert parsed.thinking


def test_text_mode_accepts_think_block_without_answer_tags():
    parsed = parse_model_output(
        raw("<think>thinking</think>\ndo(action='Launch', app='粉笔')")
    )

    assert parsed.thinking == "thinking"
    assert parsed.parsed_action == {
        "_metadata": "do",
        "action": "Launch",
        "app": "粉笔",
    }


def test_tool_call_conflicting_action_outside_think_is_rejected():
    with pytest.raises(ModelResponseError):
        parse_model_output(
            raw(
                "<think>reasoning</think>\n<answer>do(action='Home')</answer>",
                tool_calls=[RawToolCall("phone_action", {"action": "Back"})],
            )
        )


@pytest.mark.parametrize(
    "final_text",
    [
        '{"note":"still thinking"}',
        'The word "action": describes what happens next.',
    ],
)
def test_tool_call_treats_non_action_text_as_thinking(final_text):
    parsed = parse_model_output(
        raw(
            final_text,
            tool_calls=[RawToolCall("finish", {"message": "done"})],
        )
    )

    assert parsed.thinking == final_text


def test_tool_only_response_gets_canonical_json_raw_content():
    tool_call = RawToolCall(
        "phone_action", {"element": [100, 200], "action": "Tap"}
    )
    parsed = parse_model_output(raw(tool_calls=[tool_call]))

    assert parsed.raw_content == json.dumps(
        [
            {
                "name": "phone_action",
                "arguments": {"element": [100, 200], "action": "Tap"},
            }
        ],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


@pytest.mark.parametrize(
    "final_text",
    [
        "do(action='Back')",
        "thinking finish(message='done')",
        '{"action":"Home"}',
        '{"message":"extra","action":"Home"}',
        "<answer>do(action='Home')</answer>",
    ],
)
def test_tool_call_plus_text_action_is_rejected(final_text):
    with pytest.raises(ModelResponseError):
        parse_model_output(
            raw(
                final_text,
                tool_calls=[RawToolCall("phone_action", {"action": "Back"})],
            )
        )


@pytest.mark.parametrize(
    "final_text",
    [
        '{"\\u0061ction":"Home"}',
        '{"\\u0061ction":"Home"}\ndo(action="Back")',
        '{"\\u0061ction":"Home"}<answer>do(action="Back")</answer>',
    ],
)
def test_unicode_escaped_json_action_cannot_hide_a_second_action(final_text):
    tool_calls = []
    if "<answer>" not in final_text and "do(action" not in final_text:
        tool_calls = [RawToolCall("phone_action", {"action": "Back"})]

    with pytest.raises(ModelResponseError):
        parse_model_output(raw(final_text, tool_calls=tool_calls))


def test_multiple_tool_calls_are_rejected_without_selecting_one():
    with pytest.raises(ModelResponseError, match="Only one tool call"):
        parse_model_output(
            raw(
                tool_calls=[
                    RawToolCall("phone_action", {"action": "Back"}),
                    RawToolCall("finish", {"message": "done"}),
                ]
            )
        )


@pytest.mark.parametrize(
    "final_text",
    [
        "ordinary text without an action",
        "",
        "do(action='Back') trailing text",
        "do(action='Back') # trailing comment",
        "do(action='Back')\nfinish(message='done')",
        "do('Back')",
        "do(*[]) ",
        "do(**{'action': 'Back'})",
        "do(action=get_action())",
        "do(action='Back', action='Home')",
        "do(action='Back', extra=True)",
        "undo(action='Back')",
        "finish(message='done', extra=True)",
        "finish('done')",
        '{"action":"Tap","element":[10,20]',
        '{"action":"Tap","element":[10,20]} trailing',
        '[{"action":"Back"}]',
        '```json\n{"action":"Back"}\n``` trailing',
        '{"name":"phone_action","arguments":{"action":"Back"},"extra":1}',
        '{"action":"Back","action":"Home"}',
    ],
)
def test_invalid_text_responses_fail_closed(final_text):
    with pytest.raises(ModelResponseError):
        parse_model_output(raw(final_text))


@pytest.mark.parametrize(
    "final_text",
    [
        "<answer>do(action='Back')",
        "<answer>do(action='Back')</answer> trailing",
        "<answer>do(action='Back')</answer><answer>do(action='Home')</answer>",
        "<answer><answer>do(action='Back')</answer></answer>",
        "<think>one</think><think>two</think><answer>do(action='Back')</answer>",
        "prefix<think>one</think><answer>do(action='Back')</answer>",
        "<think><think>nested</think></think><answer>do(action='Back')</answer>",
        "do(action='Home')<answer>do(action='Back')</answer>",
        "<answer>reasoning do(action='Back')</answer>",
        "<answer>```json\n{\"action\":\"Back\"}\n``` trailing</answer>",
    ],
)
def test_invalid_xml_responses_fail_closed(final_text):
    with pytest.raises(ModelResponseError):
        parse_model_output(raw(final_text))


def test_parse_action_helper_delegates_to_strict_parser_without_output(capsys):
    action = parse_action("do(action='Type', text='a\\nb')")

    assert action == {"_metadata": "do", "action": "Type", "text": "a\nb"}
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "action_text",
    [
        "do(action='Tap', element=[True, 2])",
        "do(action='Tap', element=[1, 1000])",
        "do(action='Unknown')",
        "finish(message=1)",
    ],
)
def test_parse_action_helper_applies_action_schema(action_text):
    with pytest.raises(ValueError):
        parse_action(action_text)
