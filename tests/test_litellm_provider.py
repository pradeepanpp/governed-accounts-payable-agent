import sys
from types import SimpleNamespace

import pytest

from governed_ap.litellm_provider import LiteLLMTextProvider


def fake_response(*, text="Hello", usage=True):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=(
            SimpleNamespace(
                prompt_tokens=20,
                completion_tokens=10,
            )
            if usage
            else None
        ),
    )


def test_litellm_adapter_extracts_usage_and_estimated_cost(monkeypatch):
    captured = {}

    def completion(**kwargs):
        captured.update(kwargs)
        return fake_response()

    monkeypatch.setitem(
        sys.modules,
        "litellm",
        SimpleNamespace(
            completion=completion,
            completion_cost=lambda **kwargs: 0.004,
        ),
    )

    provider = LiteLLMTextProvider("openai/test-model")
    result = provider.complete_with_usage(
        system_prompt="system",
        user_prompt="invoice",
    )

    assert result.text == "Hello"
    assert result.input_tokens == 20
    assert result.output_tokens == 10
    assert str(result.cost_usd) == "0.004"
    assert result.cost_basis == "estimated"
    assert captured["model"] == "openai/test-model"
    assert captured["messages"][0]["role"] == "system"


def test_unavailable_cost_remains_unknown(monkeypatch):
    def missing_price(**kwargs):
        raise ValueError("Price unavailable")

    monkeypatch.setitem(
        sys.modules,
        "litellm",
        SimpleNamespace(
            completion=lambda **kwargs: fake_response(),
            completion_cost=missing_price,
        ),
    )

    result = LiteLLMTextProvider("openai/test-model").complete_with_usage(
        system_prompt="s", user_prompt="u"
    )

    assert result.cost_usd is None
    assert result.cost_basis == "unknown"


def test_missing_token_usage_is_not_zero(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "litellm",
        SimpleNamespace(
            completion=lambda **kwargs: fake_response(usage=False),
        ),
    )

    result = LiteLLMTextProvider("openai/test-model").complete_with_usage(
        system_prompt="s", user_prompt="u"
    )

    assert result.input_tokens is None
    assert result.output_tokens is None
    assert result.cost_usd is None


def test_empty_provider_response_is_rejected(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "litellm",
        SimpleNamespace(
            completion=lambda **kwargs: fake_response(text=""),
        ),
    )

    with pytest.raises(ValueError, match="no textual completion"):
        LiteLLMTextProvider("openai/test-model").complete_with_usage(
            system_prompt="s", user_prompt="u"
        )
