"""Strict parsing of provider-neutral model responses."""

from __future__ import annotations

import ast
import io
import json
import re
import tokenize
from dataclasses import dataclass
from typing import Any

from phone_agent.model.base import RawModelOutput, RawToolCall, ModelResponseError
from phone_agent.model.tool_schema import (
    decode_json_object,
    format_action,
    normalize_finish,
    normalize_phone_action,
    normalize_tool_call,
)

_DSL_ENTRY_RE = re.compile(r"(?<![\w.])(?:do|finish)\s*\(")
_JSON_FENCE_RE = re.compile(
    r"\A```(?:json)?[ \t]*\r?\n(?P<body>.*?)(?:\r?\n)?```\Z",
    re.DOTALL | re.IGNORECASE,
)
_FULL_THINK_RE = re.compile(r"\A<think>(?P<body>.*?)</think>\Z", re.DOTALL)
_THINK_BLOCK_RE = re.compile(r"<think>(?P<body>.*?)</think>", re.DOTALL)
_XML_RESPONSE_RE = re.compile(
    r"\A(?P<prefix>.*?)<answer>(?P<answer>.*?)</answer>\Z", re.DOTALL
)


@dataclass(frozen=True)
class ParsedResponse:
    """Validated response ready for the compatibility model facade."""

    thinking: str
    action: str
    parsed_action: dict[str, Any]
    raw_content: str


def _merge_thinking(provider_thinking: str, text_thinking: str) -> str:
    parts = [part.strip() for part in (provider_thinking, text_thinking) if part.strip()]
    return "\n".join(parts)


def _strip_action_field(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "action"}


def _literal_keywords(call: ast.Call) -> dict[str, Any]:
    if call.args:
        raise ModelResponseError("Action calls do not accept positional arguments or *args")

    values: dict[str, Any] = {}
    for keyword in call.keywords:
        if keyword.arg is None:
            raise ModelResponseError("Action calls do not accept **kwargs")
        if keyword.arg in values:
            raise ModelResponseError(f"Duplicate action field: {keyword.arg}")
        try:
            values[keyword.arg] = ast.literal_eval(keyword.value)
        except (TypeError, ValueError) as exc:
            raise ModelResponseError(
                f"Action field {keyword.arg!r} must be a Python literal"
            ) from exc
    return values


def parse_action_text(text: str) -> dict[str, Any]:
    """Parse one complete ``do(...)`` or ``finish(...)`` expression."""

    action_text = text.strip()
    if not action_text:
        raise ModelResponseError("Action text is empty")
    try:
        tokens = tokenize.generate_tokens(io.StringIO(action_text).readline)
        if any(token.type == tokenize.COMMENT for token in tokens):
            raise ModelResponseError("Comments are not allowed in action expressions")
    except tokenize.TokenError as exc:
        raise ModelResponseError(f"Invalid action tokenization: {exc}") from exc
    try:
        tree = ast.parse(action_text, mode="eval")
    except SyntaxError as exc:
        raise ModelResponseError(f"Invalid action syntax: {exc.msg}") from exc

    call = tree.body
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
        raise ModelResponseError("Expected one do(...) or finish(...) call")
    if call.func.id not in {"do", "finish"}:
        raise ModelResponseError(f"Unknown action function: {call.func.id!r}")

    values = _literal_keywords(call)
    if call.func.id == "do":
        if values.get("action") == "finish":
            return normalize_finish(_strip_action_field(values))
        return normalize_phone_action(values)
    return normalize_finish(values)


def _parse_json_action(text: str) -> dict[str, Any]:
    fenced = _JSON_FENCE_RE.fullmatch(text)
    if fenced:
        json_text = fenced.group("body")
    else:
        if "```" in text:
            raise ModelResponseError("JSON code fence must wrap the complete response")
        json_text = text

    payload = decode_json_object(json_text, context="response")
    if set(payload) == {"name", "arguments"}:
        name = payload["name"]
        if not isinstance(name, str):
            raise ModelResponseError("JSON tool name must be a string")
        return normalize_tool_call(name, payload["arguments"])

    if "name" in payload or "arguments" in payload:
        raise ModelResponseError("JSON tool wrapper requires only name and arguments")

    if "action" not in payload:
        raise ModelResponseError("JSON response requires an action or tool wrapper")
    if payload["action"] == "finish":
        return normalize_finish(_strip_action_field(payload))
    return normalize_phone_action(payload)


def _contains_json_action(text: str) -> bool:
    """Detect embedded JSON actions by decoding objects, not matching key text."""

    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if "action" in payload:
            return True
        if payload.get("name") in {"phone_action", "finish"}:
            return True
    return "```" in text


def _parse_action_payload(
    text: str, *, allow_thinking_prefix: bool
) -> tuple[str, dict[str, Any]]:
    payload = text.strip()
    if not payload:
        raise ModelResponseError("Model response contains no action")

    entry = _DSL_ENTRY_RE.search(payload)
    if entry:
        prefix = payload[: entry.start()]
        if prefix.strip() and not allow_thinking_prefix:
            raise ModelResponseError("Action payload must not contain a thinking prefix")
        if _contains_json_action(prefix):
            raise ModelResponseError("Thinking prefix contains an additional action")
        action = parse_action_text(payload[entry.start() :])
        return prefix.strip(), action

    action = _parse_json_action(payload)
    return "", action


def _parse_xml_response(text: str) -> tuple[str, dict[str, Any]]:
    if text.count("<answer>") != 1 or text.count("</answer>") != 1:
        raise ModelResponseError("XML response requires exactly one complete answer block")

    match = _XML_RESPONSE_RE.fullmatch(text)
    if not match:
        raise ModelResponseError("XML answer must cover the end of the response")

    prefix = match.group("prefix").strip()
    answer = match.group("answer")
    if "<answer>" in answer or "</answer>" in answer:
        raise ModelResponseError("Nested answer blocks are not allowed")

    if "<think>" in prefix or "</think>" in prefix:
        if prefix.count("<think>") != 1 or prefix.count("</think>") != 1:
            raise ModelResponseError("XML response requires at most one complete think block")
        think_match = _FULL_THINK_RE.fullmatch(prefix)
        if not think_match:
            raise ModelResponseError("Text outside the XML think block is not allowed")
        thinking = think_match.group("body")
        if "<think>" in thinking or "</think>" in thinking:
            raise ModelResponseError("Nested think blocks are not allowed")
    else:
        if _DSL_ENTRY_RE.search(prefix) or _contains_json_action(prefix):
            raise ModelResponseError("Text before answer contains an additional action")
        thinking = prefix

    _, action = _parse_action_payload(answer, allow_thinking_prefix=False)
    return thinking.strip(), action


def _parse_text_response(text: str) -> tuple[str, dict[str, Any]]:
    stripped = text.strip()
    if not stripped:
        raise ModelResponseError("Model response is empty")

    if any(tag in stripped for tag in ("<answer>", "</answer>")):
        return _parse_xml_response(stripped)

    if (
        "<think>" in stripped
        and "</think>" in stripped
        and stripped.count("<think>") == 1
        and stripped.count("</think>") == 1
    ):
        think_match = _THINK_BLOCK_RE.search(stripped)
        if think_match:
            body = think_match.group("body")
            if "<think>" not in body and "</think>" not in body:
                prefix = stripped[: think_match.start()].strip()
                suffix = stripped[think_match.end() :].strip()
                if not prefix and suffix:
                    _, action = _parse_action_payload(suffix, allow_thinking_prefix=False)
                    return body.strip(), action

    if any(tag in stripped for tag in ("<think>", "</think>")):
        return _parse_xml_response(stripped)
    return _parse_action_payload(stripped, allow_thinking_prefix=True)


def _tool_text_thinking(text: str, parsed_action: dict[str, Any] | None = None) -> str:
    stripped = text.strip()
    if not stripped:
        return ""

    think_match = _THINK_BLOCK_RE.search(stripped)
    if think_match:
        body = think_match.group("body")
        if "<think>" in body or "</think>" in body:
            raise ModelResponseError("Nested think blocks are not allowed")
        prefix = stripped[: think_match.start()].strip()
        suffix = stripped[think_match.end() :].strip()
        if any(tag in prefix or tag in suffix for tag in ("<think>", "</think>")):
            raise ModelResponseError("Malformed think block in tool-call response")

        thinking = body.strip()
        outside = f"{prefix}\n{suffix}".strip() if prefix and suffix else (prefix or suffix)
        if not outside:
            return thinking

        action_like = bool(
            _DSL_ENTRY_RE.search(outside)
            or any(tag in outside for tag in ("<answer>", "</answer>"))
            or _contains_json_action(outside)
        )
        if action_like:
            try:
                _, text_action = _parse_text_response(outside)
                if parsed_action is None or text_action != parsed_action:
                    raise ModelResponseError("Response contains both a tool call and a text action")
                return thinking
            except ModelResponseError as exc:
                if "Response contains both a tool call" in str(exc):
                    raise
                if parsed_action is None:
                    raise ModelResponseError("Response contains both a tool call and a text action") from exc
                return thinking

        return f"{thinking}\n{outside}".strip()

    action_like = bool(
        _DSL_ENTRY_RE.search(stripped)
        or any(tag in stripped for tag in ("<answer>", "</answer>"))
        or _contains_json_action(stripped)
    )
    if action_like:
        try:
            _, text_action = _parse_text_response(stripped)
            if parsed_action is not None and text_action != parsed_action:
                raise ModelResponseError("Response contains both a tool call and a text action")
        except ModelResponseError:
            pass
        raise ModelResponseError("Response contains both a tool call and a text action")

    if "<think>" in stripped or "</think>" in stripped:
        raise ModelResponseError("Malformed think block in tool-call response")
    return stripped


def _canonical_tool_raw_content(tool_calls: list[RawToolCall]) -> str:
    payload = [
        {"name": tool_call.name, "arguments": tool_call.arguments}
        for tool_call in tool_calls
    ]
    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ModelResponseError(f"Tool call is not JSON serializable: {exc}") from exc


class ModelResponseParser:
    """Convert ``RawModelOutput`` into one strict, normalized action."""

    @staticmethod
    def parse(output: RawModelOutput) -> ParsedResponse:
        if len(output.tool_calls) > 1:
            raise ModelResponseError("Only one tool call is allowed per response")

        if output.tool_calls:
            parsed_action = normalize_tool_call(output.tool_calls[0])
            text_thinking = _tool_text_thinking(output.final_text, parsed_action)
            raw_content = output.raw_content
            if not raw_content and not output.final_text.strip():
                raw_content = _canonical_tool_raw_content(output.tool_calls)
        else:
            text_thinking, parsed_action = _parse_text_response(output.final_text)
            raw_content = output.raw_content

        return ParsedResponse(
            thinking=_merge_thinking(output.thinking, text_thinking),
            action=format_action(parsed_action),
            parsed_action=parsed_action,
            raw_content=raw_content,
        )


def parse_model_output(output: RawModelOutput) -> ParsedResponse:
    """Functional entry point for strict model response parsing."""

    return ModelResponseParser.parse(output)
