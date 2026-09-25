"""Tests for shared model command-line options."""

import argparse

import pytest

import ios as ios_entry
import main as main_entry
from phone_agent.cli import resolve_model_config
from phone_agent.model import ModelConfig


MODEL_FIELDS = ("provider", "tool_mode", "base_url", "model", "api_key")
MODEL_ENVIRONMENT = (
    "PHONE_AGENT_PROVIDER",
    "PHONE_AGENT_TOOL_MODE",
    "PHONE_AGENT_BASE_URL",
    "PHONE_AGENT_MODEL",
    "PHONE_AGENT_API_KEY",
)


@pytest.fixture(autouse=True)
def clear_model_environment(monkeypatch):
    for name in MODEL_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("parse_args", [main_entry.parse_args, ios_entry.parse_args])
def test_model_argument_defaults_are_none(parse_args):
    args = parse_args([])

    assert {name: getattr(args, name) for name in MODEL_FIELDS} == {
        "provider": None,
        "tool_mode": None,
        "base_url": None,
        "model": None,
        "api_key": None,
    }


@pytest.mark.parametrize("parse_args", [main_entry.parse_args, ios_entry.parse_args])
def test_entrypoints_accept_the_same_model_options(parse_args):
    args = parse_args(
        [
            "--provider",
            "anthropic",
            "--tool-mode",
            "native",
            "--base-url",
            "https://models.example/v1",
            "--model",
            "vision-model",
            "--api-key",
            "secret",
        ]
    )

    assert {name: getattr(args, name) for name in MODEL_FIELDS} == {
        "provider": "anthropic",
        "tool_mode": "native",
        "base_url": "https://models.example/v1",
        "model": "vision-model",
        "api_key": "secret",
    }


@pytest.mark.parametrize("parse_args", [main_entry.parse_args, ios_entry.parse_args])
@pytest.mark.parametrize("alias", ["--api-key", "--apikey"])
def test_api_key_aliases_share_one_destination(parse_args, alias):
    assert parse_args([alias, "secret"]).api_key == "secret"


@pytest.mark.parametrize("parse_args", [main_entry.parse_args, ios_entry.parse_args])
def test_api_key_aliases_are_mutually_exclusive(parse_args):
    with pytest.raises(SystemExit):
        parse_args(["--api-key", "first", "--apikey", "second"])


def test_resolve_model_config_uses_cli_over_environment():
    args = argparse.Namespace(
        provider="anthropic",
        tool_mode="native",
        base_url="https://cli.example/v1",
        model="cli-model",
        api_key="cli-key",
    )
    environment = {
        "PHONE_AGENT_PROVIDER": "openai",
        "PHONE_AGENT_TOOL_MODE": "text",
        "PHONE_AGENT_BASE_URL": "https://env.example/v1",
        "PHONE_AGENT_MODEL": "env-model",
        "PHONE_AGENT_API_KEY": "env-key",
    }

    config = resolve_model_config(args, environment, lang="en")

    assert config.provider == "anthropic"
    assert config.tool_mode == "native"
    assert config.base_url == "https://cli.example/v1"
    assert config.model_name == "cli-model"
    assert config.api_key == "cli-key"
    assert config.lang == "en"


def test_resolve_model_config_uses_environment_when_cli_is_absent():
    args = argparse.Namespace(**dict.fromkeys(MODEL_FIELDS))
    environment = {
        "PHONE_AGENT_PROVIDER": "ollama",
        "PHONE_AGENT_TOOL_MODE": "text",
        "PHONE_AGENT_BASE_URL": "https://ollama.example",
        "PHONE_AGENT_MODEL": "env-model",
    }

    config = resolve_model_config(args, environment, lang="cn")

    assert config.provider == "ollama"
    assert config.tool_mode == "text"
    assert config.base_url == "https://ollama.example"
    assert config.model_name == "env-model"
    assert config.api_key is None


def test_resolve_model_config_delegates_defaults_to_model_config():
    args = argparse.Namespace(**dict.fromkeys(MODEL_FIELDS))

    resolved = resolve_model_config(args, {}, lang="cn")
    default = ModelConfig(lang="cn")

    assert resolved == default
