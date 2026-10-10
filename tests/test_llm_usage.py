from decimal import Decimal

import pytest

from governed_ap.llm_usage import (
    CompletionWithUsage,
    MeteredTextProvider,
    UsageCollector,
)


class MeasuredProvider:
    def complete_with_usage(self, *, system_prompt, user_prompt):
        return CompletionWithUsage(
            text='{"action":"AUTO_APPROVE"}',
            input_tokens=12,
            output_tokens=6,
            cost_usd=Decimal("0.003"),
            cost_basis="estimated",
            provider="test-provider",
            model="test-model",
        )


class PlainProvider:
    def complete(self, *, system_prompt, user_prompt):
        return "plain response"


class FailingProvider:
    def complete(self, *, system_prompt, user_prompt):
        raise TimeoutError("Simulated outage")


def test_measured_usage_is_recorded():
    collector = UsageCollector()
    provider = MeteredTextProvider(MeasuredProvider(), collector, role="decision")

    assert (
        provider.complete(
            system_prompt="system",
            user_prompt="invoice",
        )
        == '{"action":"AUTO_APPROVE"}'
    )

    call = collector.since(0)[0]

    assert call.status == "COMPLETED"
    assert call.input_tokens == 12
    assert call.output_tokens == 6
    assert call.cost_usd == Decimal("0.003")
    assert call.cost_basis == "estimated"


def test_plain_provider_has_unknown_usage():
    collector = UsageCollector()
    provider = MeteredTextProvider(PlainProvider(), collector, role="guardrail")

    provider.complete(system_prompt="s", user_prompt="u")
    call = collector.since(0)[0]

    assert call.status == "COMPLETED"
    assert call.input_tokens is None
    assert call.cost_usd is None


def test_provider_error_is_recorded_and_propagated():
    collector = UsageCollector()
    provider = MeteredTextProvider(FailingProvider(), collector, role="decision")

    with pytest.raises(TimeoutError):
        provider.complete(system_prompt="s", user_prompt="u")

    call = collector.since(0)[0]

    assert call.status == "FAILED"
    assert call.error_type == "TimeoutError"


def test_usage_collector_separates_intervals():
    collector = UsageCollector()
    provider = MeteredTextProvider(PlainProvider(), collector, role="guardrail")

    provider.complete(system_prompt="a", user_prompt="b")
    mark = collector.mark()
    provider.complete(system_prompt="c", user_prompt="d")

    assert len(collector.since(0)) == 2
    assert len(collector.since(mark)) == 1


def test_negative_token_count_is_rejected():
    with pytest.raises(ValueError, match="Token counts"):
        CompletionWithUsage(text="x", input_tokens=-1)


def test_cost_requires_a_known_basis():
    with pytest.raises(ValueError, match="Cost and cost basis"):
        CompletionWithUsage(
            text="x",
            cost_usd=Decimal("0.01"),
        )
