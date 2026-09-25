"""Tests for provider-aware model configuration."""

from dataclasses import fields

import pytest

from phone_agent.model.base import ModelConfigurationError
from phone_agent.model.client import ModelConfig, validate_extra_body


def test_historical_fields_keep_order_and_positional_meaning():
    assert [field.name for field in fields(ModelConfig)][:9] == [
        "base_url",
        "api_key",
        "model_name",
        "max_tokens",
        "temperature",
        "top_p",
        "frequency_penalty",
        "extra_body",
        "lang",
    ]

    config = ModelConfig(
        "https://example.test/v1/",
        "secret",
        "legacy-model",
        321,
        0.1,
        0.7,
        0.2,
        {"vendor_option": True},
        "en",
    )

    assert config.base_url == "https://example.test/v1"
    assert config.api_key == "secret"
    assert config.model_name == "legacy-model"
    assert config.max_tokens == 321
    assert config.temperature == 0.1
    assert config.top_p == 0.7
    assert config.frequency_penalty == 0.2
    assert config.extra_body == {"vendor_option": True}
    assert config.lang == "en"
    assert config.provider == "openai"


def test_openai_defaults_and_optional_sampling_fields():
    config = ModelConfig()

    assert config.provider == "openai"
    assert config.tool_mode == "auto"
    assert config.base_url == "http://localhost:8000/v1"
    assert config.api_key is None
    assert config.model_name == "autoglm-phone-9b"
    assert config.max_tokens == 2048
    assert config.temperature is None
    assert config.top_p is None
    assert config.frequency_penalty is None
    assert config.timeout == 120.0


@pytest.mark.parametrize("api_key", [None, "", "EMPTY", "real-key"])
def test_openai_accepts_local_or_remote_api_key(api_key):
    assert ModelConfig(api_key=api_key).api_key == api_key


def test_anthropic_defaults_and_validation():
    config = ModelConfig(
        provider="anthropic", model_name="claude-model", api_key="secret"
    )

    assert config.base_url == "https://api.anthropic.com"
    assert config.model_name == "claude-model"

    with pytest.raises(ModelConfigurationError, match="model_name"):
        ModelConfig(provider="anthropic", api_key="secret")
    with pytest.raises(ModelConfigurationError, match="api_key"):
        ModelConfig(provider="anthropic", model_name="claude-model")
    with pytest.raises(ModelConfigurationError, match="api_key"):
        ModelConfig(
            provider="anthropic", model_name="claude-model", api_key="EMPTY"
        )
    with pytest.raises(ModelConfigurationError, match="api_key"):
        ModelConfig(
            provider="anthropic", model_name="claude-model", api_key=" EMPTY "
        )


def test_ollama_defaults_and_validation():
    config = ModelConfig(provider="ollama", model_name="vision-model")

    assert config.base_url == "http://localhost:11434"
    assert config.api_key is None

    with pytest.raises(ModelConfigurationError, match="model_name"):
        ModelConfig(provider="ollama")
    with pytest.raises(ModelConfigurationError, match="does not use api_key"):
        ModelConfig(
            provider="ollama", model_name="vision-model", api_key="secret"
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"provider": "unknown"},
        {"provider": []},
        {"tool_mode": "unknown"},
        {"tool_mode": {}},
        {"base_url": ""},
        {"base_url": "///"},
        {"base_url": "https://"},
        {"base_url": "http:///v1"},
        {"base_url": "https://user:secret@example.test/v1"},
        {"model_name": ""},
        {"max_tokens": 0},
        {"max_tokens": True},
        {"temperature": True},
        {"temperature": -0.1},
        {"top_p": 1.1},
        {"frequency_penalty": float("inf")},
        {"timeout": 0},
        {"timeout": True},
        {"extra_body": []},
        {"extra_headers": {"Authorization": 1}},
    ],
)
def test_invalid_common_configuration_is_rejected(kwargs):
    with pytest.raises(ModelConfigurationError):
        ModelConfig(**kwargs)


@pytest.mark.parametrize("provider", ["anthropic", "ollama"])
def test_non_openai_frequency_penalty_only_accepts_disabled_values(provider):
    common = {"provider": provider, "model_name": "model"}
    if provider == "anthropic":
        common["api_key"] = "secret"

    assert ModelConfig(**common, frequency_penalty=None).frequency_penalty is None
    assert ModelConfig(**common, frequency_penalty=0.0).frequency_penalty == 0.0
    with pytest.raises(ModelConfigurationError, match="frequency_penalty"):
        ModelConfig(**common, frequency_penalty=0.1)


@pytest.mark.parametrize(
    "provider, extra_body",
    [
        ("openai", {"model": "other"}),
        ("openai", {"temperature": 1}),
        ("anthropic", {"system": "override"}),
        ("ollama", {"messages": []}),
        ("ollama", {"options": {"num_predict": 10}}),
        ("ollama", {"options": {"temperature": 1}}),
    ],
)
def test_reserved_extra_body_fields_are_rejected(provider, extra_body):
    kwargs = {"provider": provider, "extra_body": extra_body}
    if provider == "anthropic":
        kwargs.update(model_name="model", api_key="secret")
    elif provider == "ollama":
        kwargs.update(model_name="model")

    with pytest.raises(ModelConfigurationError):
        ModelConfig(**kwargs)


@pytest.mark.parametrize("options", [None, "seed=7", 7, [("seed", 7)]])
def test_ollama_non_dict_extra_options_are_rejected(options):
    with pytest.raises(ModelConfigurationError, match="options must be a dictionary"):
        ModelConfig(
            provider="ollama", model_name="model", extra_body={"options": options}
        )


def test_ollama_extra_options_allow_non_generated_values_and_are_copied():
    extra_body = {"options": {"seed": 7}, "keep_alive": "5m"}
    config = ModelConfig(
        provider="ollama", model_name="model", extra_body=extra_body
    )
    extra_body["options"]["seed"] = 8

    assert config.extra_body == {"options": {"seed": 7}, "keep_alive": "5m"}
    validate_extra_body("ollama", config.extra_body)


def test_secrets_are_excluded_from_config_repr():
    config = ModelConfig(
        api_key="api-secret",
        extra_headers={"Authorization": "header-secret"},
    )

    representation = repr(config)
    assert "api-secret" not in representation
    assert "header-secret" not in representation
    assert "api_key=" not in representation
    assert "extra_headers=" not in representation
