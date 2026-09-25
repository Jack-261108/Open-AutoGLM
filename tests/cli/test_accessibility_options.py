"""Tests for the accessibility command-line option."""

import pytest

import ios as ios_entry
import main as main_entry


@pytest.fixture(autouse=True)
def clear_accessibility_environment(monkeypatch):
    monkeypatch.delenv("PHONE_AGENT_ACCESSIBILITY", raising=False)


@pytest.mark.parametrize("parse_args", [main_entry.parse_args, ios_entry.parse_args])
def test_accessibility_defaults_to_auto(parse_args):
    assert parse_args([]).accessibility == "auto"


@pytest.mark.parametrize("parse_args", [main_entry.parse_args, ios_entry.parse_args])
@pytest.mark.parametrize("value", ["auto", "on", "off"])
def test_accessibility_flag(parse_args, value):
    assert parse_args(["--accessibility", value]).accessibility == value


@pytest.mark.parametrize("parse_args", [main_entry.parse_args, ios_entry.parse_args])
@pytest.mark.parametrize("value,expected", [("AUTO", "auto"), ("On", "on"), ("OFF", "off")])
def test_accessibility_flag_case_insensitive(parse_args, value, expected):
    assert parse_args(["--accessibility", value]).accessibility == expected


@pytest.mark.parametrize("parse_args", [main_entry.parse_args, ios_entry.parse_args])
def test_accessibility_reads_environment(parse_args, monkeypatch):
    monkeypatch.setenv("PHONE_AGENT_ACCESSIBILITY", "off")

    assert parse_args([]).accessibility == "off"


@pytest.mark.parametrize("parse_args", [main_entry.parse_args, ios_entry.parse_args])
@pytest.mark.parametrize("value,expected", [("AUTO", "auto"), ("ON", "on"), ("Off", "off")])
def test_accessibility_reads_environment_case_insensitive(parse_args, monkeypatch, value, expected):
    monkeypatch.setenv("PHONE_AGENT_ACCESSIBILITY", value)

    assert parse_args([]).accessibility == expected


@pytest.mark.parametrize("parse_args", [main_entry.parse_args, ios_entry.parse_args])
def test_accessibility_flag_overrides_environment(parse_args, monkeypatch):
    monkeypatch.setenv("PHONE_AGENT_ACCESSIBILITY", "off")

    assert parse_args(["--accessibility", "on"]).accessibility == "on"


@pytest.mark.parametrize("parse_args", [main_entry.parse_args, ios_entry.parse_args])
def test_accessibility_rejects_unknown_value(parse_args):
    with pytest.raises(SystemExit):
        parse_args(["--accessibility", "sometimes"])


@pytest.mark.parametrize("parse_args", [main_entry.parse_args, ios_entry.parse_args])
def test_accessibility_rejects_unknown_environment(parse_args, monkeypatch):
    monkeypatch.setenv("PHONE_AGENT_ACCESSIBILITY", "invalid")

    with pytest.raises(SystemExit):
        parse_args([])
