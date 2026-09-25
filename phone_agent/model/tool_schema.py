"""Strict schemas and normalization for phone actions."""

from __future__ import annotations

import copy
import json
from typing import Any

from phone_agent.model.base import RawToolCall, ModelResponseError


_ACTION_FIELDS: dict[str, tuple[str, ...]] = {
    "Launch": ("app",),
    "Tap": ("element", "message"),
    "Type": ("text",),
    "Type_Name": ("text",),
    "Swipe": ("start", "end"),
    "Back": (),
    "Home": (),
    "Interact": ("message",),
    "Double Tap": ("element",),
    "Long Press": ("element",),
    "Wait": ("duration",),
    "Take_over": ("message",),
    "Note": ("message",),
    "Call_API": ("instruction",),
}

_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = dict(_ACTION_FIELDS)
_REQUIRED_FIELDS["Tap"] = ("element",)
_REQUIRED_FIELDS["Interact"] = ()

_COORDINATE_FIELDS = frozenset(("element", "start", "end"))
_STRING_FIELDS = frozenset(
    ("app", "message", "text", "duration", "instruction")
)


def _coordinate_schema() -> dict[str, Any]:
    return {
        "type": "array",
        "items": {"type": "integer", "minimum": 0, "maximum": 999},
        "minItems": 2,
        "maxItems": 2,
    }


def _field_schema(field: str) -> dict[str, Any]:
    if field in _COORDINATE_FIELDS:
        return _coordinate_schema()
    return {"type": "string"}


def _action_variant(action: str, fields: tuple[str, ...]) -> dict[str, Any]:
    properties = {"action": {"const": action}}
    properties.update({field: _field_schema(field) for field in fields})
    return {
        "type": "object",
        "properties": properties,
        "required": ["action", *_REQUIRED_FIELDS[action]],
        "additionalProperties": False,
    }


PHONE_ACTION_INPUT_SCHEMA: dict[str, Any] = {
    "oneOf": [
        _action_variant(action, fields) for action, fields in _ACTION_FIELDS.items()
    ]
}
FINISH_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"message": {"type": "string"}},
    "required": ["message"],
    "additionalProperties": False,
}

_PHONE_ACTION_TOOL_TEMPLATE: dict[str, Any] = {
    "name": "phone_action",
    "description": "Execute exactly one validated phone action.",
    "input_schema": PHONE_ACTION_INPUT_SCHEMA,
}
_FINISH_TOOL_TEMPLATE: dict[str, Any] = {
    "name": "finish",
    "description": "Finish the task with a final message.",
    "input_schema": FINISH_INPUT_SCHEMA,
}
_TOOL_SCHEMA_TEMPLATES: tuple[dict[str, Any], ...] = (
    _PHONE_ACTION_TOOL_TEMPLATE,
    _FINISH_TOOL_TEMPLATE,
)

# Module-level copies preserve direct imports without exposing internal templates.
PHONE_ACTION_TOOL = copy.deepcopy(_PHONE_ACTION_TOOL_TEMPLATE)
FINISH_TOOL = copy.deepcopy(_FINISH_TOOL_TEMPLATE)
PHONE_ACTION_SCHEMA = PHONE_ACTION_TOOL
FINISH_SCHEMA = FINISH_TOOL


def get_tool_schemas() -> list[dict[str, Any]]:
    """Return fresh copies of the provider-neutral tool definitions."""

    return copy.deepcopy(list(_TOOL_SCHEMA_TEMPLATES))


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON constant: {value}")


def _object_from_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def decode_json_object(value: str, *, context: str = "arguments") -> dict[str, Any]:
    """Decode one strict JSON object, rejecting constants and duplicate fields."""

    try:
        decoded = json.loads(
            value,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_object_from_pairs,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ModelResponseError(f"Invalid {context} JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise ModelResponseError(f"{context} must be a JSON object")
    return decoded


def _validate_coordinate(value: Any, field: str) -> list[int]:
    if not isinstance(value, list) or len(value) != 2:
        raise ModelResponseError(f"{field} must be a list of exactly two integers")
    if any(type(item) is not int for item in value):
        raise ModelResponseError(f"{field} values must be integers, not booleans")
    if any(item < 0 or item > 999 for item in value):
        raise ModelResponseError(f"{field} values must be between 0 and 999")
    return value


def _validate_string(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ModelResponseError(f"{field} must be a string")
    return value


def normalize_phone_action(arguments: object) -> dict[str, Any]:
    """Validate and normalize arguments for the ``phone_action`` tool."""

    if not isinstance(arguments, dict):
        raise ModelResponseError("phone_action arguments must be an object")

    action = arguments.get("action")
    if not isinstance(action, str):
        raise ModelResponseError("phone_action requires one string action field")
    if action not in _ACTION_FIELDS:
        raise ModelResponseError(f"Unknown phone action: {action!r}")

    allowed = {"action", *_ACTION_FIELDS[action]}
    extra = set(arguments) - allowed
    if extra:
        raise ModelResponseError(f"Unexpected fields for {action}: {sorted(extra, key=repr)!r}")

    missing = set(_REQUIRED_FIELDS[action]) - set(arguments)
    if missing:
        raise ModelResponseError(f"Missing fields for {action}: {sorted(missing)!r}")

    normalized: dict[str, Any] = {"_metadata": "do", "action": action}
    for field in _ACTION_FIELDS[action]:
        if field not in arguments:
            continue
        value = arguments[field]
        if field in _COORDINATE_FIELDS:
            normalized[field] = _validate_coordinate(value, field)
        elif field in _STRING_FIELDS:
            normalized[field] = _validate_string(value, field)
        else:
            raise ModelResponseError(f"No validator for field: {field}")
    return normalized


def normalize_finish(arguments: object) -> dict[str, Any]:
    """Validate and normalize arguments for the ``finish`` tool."""

    if not isinstance(arguments, dict):
        raise ModelResponseError("finish arguments must be an object")
    if set(arguments) != {"message"}:
        missing = {"message"} - set(arguments)
        if missing:
            raise ModelResponseError("finish requires the message field")
        extra = set(arguments) - {"message"}
        raise ModelResponseError(f"Unexpected finish fields: {sorted(extra, key=repr)!r}")
    return {
        "_metadata": "finish",
        "message": _validate_string(arguments["message"], "message"),
    }


def normalize_tool_call(
    tool_call: RawToolCall | str,
    arguments: dict[str, Any] | str | None = None,
) -> dict[str, Any]:
    """Normalize one provider tool call into the device execution dictionary."""

    if isinstance(tool_call, RawToolCall):
        if arguments is not None:
            raise ModelResponseError("arguments must not be supplied with RawToolCall")
        name = tool_call.name
        raw_arguments = tool_call.arguments
    else:
        name = tool_call
        if arguments is None:
            raise ModelResponseError("Tool arguments are required")
        raw_arguments = arguments

    if not isinstance(name, str):
        raise ModelResponseError("Tool name must be a string")
    if isinstance(raw_arguments, str):
        parsed_arguments = decode_json_object(raw_arguments, context="tool arguments")
    elif isinstance(raw_arguments, dict):
        parsed_arguments = raw_arguments
    else:
        raise ModelResponseError("Tool arguments must be an object or JSON object string")

    if name == "phone_action":
        return normalize_phone_action(parsed_arguments)
    if name == "finish":
        return normalize_finish(parsed_arguments)
    raise ModelResponseError(f"Unknown tool: {name!r}")


def validate_action(action: object) -> dict[str, Any]:
    """Validate an already normalized action and return a canonical copy."""

    if not isinstance(action, dict):
        raise ModelResponseError("Action must be an object")
    metadata = action.get("_metadata")
    if metadata == "do":
        return normalize_phone_action(
            {key: value for key, value in action.items() if key != "_metadata"}
        )
    if metadata == "finish":
        return normalize_finish(
            {key: value for key, value in action.items() if key != "_metadata"}
        )
    raise ModelResponseError("Action metadata must be 'do' or 'finish'")


def format_action(action: dict[str, Any]) -> str:
    """Format a validated action deterministically using Python ``repr`` values."""

    normalized = validate_action(action)
    if normalized["_metadata"] == "finish":
        return f"finish(message={normalized['message']!r})"

    action_name = normalized["action"]
    parts = [f"action={action_name!r}"]
    for field in _ACTION_FIELDS[action_name]:
        if field in normalized:
            parts.append(f"{field}={normalized[field]!r}")
    return f"do({', '.join(parts)})"
