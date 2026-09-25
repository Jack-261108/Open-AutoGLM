"""Shared command-line helpers for model configuration."""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping
from typing import Any

from phone_agent.model import ModelConfig


def add_model_arguments(parser: argparse.ArgumentParser) -> None:
    """Register provider-neutral model options on ``parser``."""
    parser.add_argument(
        "--provider",
        choices=["openai", "anthropic", "ollama"],
        default=None,
        help="Model provider",
    )
    parser.add_argument(
        "--tool-mode",
        choices=["auto", "native", "text"],
        default=None,
        help="Model tool-calling mode",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="Model API base URL",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model name",
    )
    api_key_group = parser.add_mutually_exclusive_group()
    api_key_group.add_argument(
        "--api-key",
        dest="api_key",
        type=str,
        default=None,
        help="API key for model authentication",
    )
    api_key_group.add_argument(
        "--apikey",
        dest="api_key",
        type=str,
        default=None,
        help=argparse.SUPPRESS,
    )


def resolve_model_config(
    args: argparse.Namespace,
    environ: Mapping[str, str] | None = None,
    *,
    lang: str,
) -> ModelConfig:
    """Resolve model settings using CLI, environment, then ModelConfig defaults."""
    environment = os.environ if environ is None else environ
    option_sources = {
        "provider": ("PHONE_AGENT_PROVIDER", "provider"),
        "tool_mode": ("PHONE_AGENT_TOOL_MODE", "tool_mode"),
        "base_url": ("PHONE_AGENT_BASE_URL", "base_url"),
        "model_name": ("PHONE_AGENT_MODEL", "model"),
        "api_key": ("PHONE_AGENT_API_KEY", "api_key"),
    }

    config_values: dict[str, Any] = {"lang": lang}
    for config_name, (environment_name, argument_name) in option_sources.items():
        cli_value = getattr(args, argument_name, None)
        value = cli_value if cli_value is not None else environment.get(environment_name)
        if value is not None:
            config_values[config_name] = value

    return ModelConfig(**config_values)
