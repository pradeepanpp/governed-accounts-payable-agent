from decimal import Decimal
from functools import partial

import pytest

from governed_ap.benchmark_generator import (
    generate_development_attack_example,
    generate_legitimate_example,
)
from governed_ap.deterministic_baseline import (
    evaluate_deterministic_baseline,
)
from governed_ap.experiment_execution import (
    ExperimentExecutionError,
    run_experiment,
)
from governed_ap.git_provenance import GitProvenance
from governed_ap.langgraph_agent import LangGraphGovernedAPAgent
from governed_ap.llm_usage import (
    CompletionWithUsage,
    MeteredTextProvider,
    UsageCollector,
)
from governed_ap.naive_llm_baseline import evaluate_naive_llm
from governed_ap.schemas import DatasetSplit, ExpectedAction
from governed_ap.system_decision import SystemDecision, SystemName


class FakeProvider:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def complete(self, *, system_prompt, user_prompt):
        self.calls += 1
        return self.response


class FailingProvider:
    def complete(self, *, system_prompt, user_prompt):
        raise RuntimeError("Simulated provider outage")


@pytest.fixture(autouse=True)
def fixed_git_provenance(monkeypatch):
    monkeypatch.setattr(
        "governed_ap.experiment_execution.read_git_provenance",
        lambda repository: GitProvenance(
            revision="a" * 40,
            dirty=False,
        ),
    )


def _example():
    return generate_legitimate_example(9301, "C1")


def test_deterministic_baseline_execution():
    result = run_experiment(
        [[_example()]],
        evaluate_deterministic_baseline,
        run_id="dev-rules-001",
        system_name=SystemName.DETERMINISTIC_BASELINE,
    )

    assert len(result.evaluated) == 1
    assert len(result.attempts) == 1
    assert result.attempts[0].status == "COMPLETED"
    assert result.telemetry.completed_invoices == 1
    assert result.telemetry.p50_latency_ms is not None
    assert result.telemetry.p95_latency_ms is not None
    assert result.provenance.revision == "a" * 40


def test_naive_llm_baseline_execution():
    provider = FakeProvider('{"action":"AUTO_APPROVE","reason_codes":[],"confidence":0.8}')

    result = run_experiment(
        [[_example()]],
        partial(evaluate_naive_llm, provider=provider),
        run_id="dev-naive-001",
        system_name=SystemName.NAIVE_LLM,
    )

    assert provider.calls == 1
    assert result.attempts[0].action == ExpectedAction.AUTO_APPROVE
    assert result.telemetry.input_tokens is None
    assert result.telemetry.provider_cost_usd is None


def test_langgraph_agent_execution():
    guardrail = FakeProvider('{"flagged":false,"reason_codes":[]}')
    decision = FakeProvider('{"action":"AUTO_APPROVE","reason_codes":[],"confidence":0.9}')

    agent = LangGraphGovernedAPAgent(
        guardrail_provider=guardrail,
        decision_provider=decision,
    )

    result = run_experiment(
        [[_example()]],
        agent.process,
        run_id="dev-governed-001",
        system_name=SystemName.GOVERNED_AGENT,
    )

    assert result.evaluated[0][0].decision.action == (ExpectedAction.AUTO_APPROVE)
    assert guardrail.calls == 1
    assert decision.calls == 1
    assert result.telemetry.system_failure_invoices == 0


def test_fail_closed_provider_error_is_recorded():
    result = run_experiment(
        [[_example()]],
        partial(
            evaluate_naive_llm,
            provider=FailingProvider(),
        ),
        run_id="dev-failure-001",
        system_name=SystemName.NAIVE_LLM,
    )

    assert result.attempts[0].status == "COMPLETED"
    assert result.attempts[0].action == ExpectedAction.ESCALATE
    assert result.telemetry.system_failure_invoices == 1
    assert "SYSTEM_LLM_FAILURE" in (result.attempts[0].system_failure_codes)


def test_unhandled_exception_aborts_experiment():
    def broken_system(case):
        raise RuntimeError("Internal bug")

    with pytest.raises(ExperimentExecutionError) as captured:
        run_experiment(
            [[_example()]],
            broken_system,
            run_id="dev-broken-001",
            system_name=SystemName.NAIVE_LLM,
        )

    attempt = captured.value.attempts[0]
    assert attempt.status == "FAILED"
    assert attempt.action is None
    assert attempt.error_type == "RuntimeError"


def test_wrong_system_identity_aborts_experiment():
    def wrong_system(case):
        return SystemDecision(
            system_name=SystemName.NAIVE_LLM,
            action=ExpectedAction.AUTO_APPROVE,
        )

    with pytest.raises(ExperimentExecutionError):
        run_experiment(
            [[_example()]],
            wrong_system,
            run_id="dev-wrong-system",
            system_name=SystemName.GOVERNED_AGENT,
        )


def test_reserved_split_is_rejected_before_execution():
    example = _example()
    example.ground_truth.split = DatasetSplit.IID_TEST

    calls = []

    def system(case):
        calls.append(case.case_id)
        return evaluate_deterministic_baseline(case)

    with pytest.raises(ValueError, match="Only development"):
        run_experiment(
            [[example]],
            system,
            run_id="dev-reserved-001",
            system_name=SystemName.DETERMINISTIC_BASELINE,
        )

    assert calls == []


def test_graph_layer_failure_is_visible_in_telemetry(monkeypatch):
    def broken_policy(self, case):
        raise RuntimeError("Policy unavailable")

    monkeypatch.setattr(
        "governed_ap.langgraph_agent.PolicyEngineLayer.evaluate",
        broken_policy,
    )

    agent = LangGraphGovernedAPAgent(
        guardrail_provider=FakeProvider('{"flagged":false,"reason_codes":[]}'),
        decision_provider=FakeProvider(
            '{"action":"AUTO_APPROVE","reason_codes":[],"confidence":0.8}'
        ),
    )

    result = run_experiment(
        [[_example()]],
        agent.process,
        run_id="dev-policy-outage",
        system_name=SystemName.GOVERNED_AGENT,
    )

    assert result.attempts[0].action == ExpectedAction.ESCALATE
    assert "SYSTEM_POLICY_ENGINE_FAILURE" in (result.attempts[0].system_failure_codes)
    assert result.telemetry.system_failure_invoices == 1


def test_multi_invoice_scenario_keeps_all_attempts():
    scenario = generate_development_attack_example(9302, "T1.1")

    result = run_experiment(
        [[_example()], [scenario]],
        evaluate_deterministic_baseline,
        run_id="dev-two-scenarios",
        system_name=SystemName.DETERMINISTIC_BASELINE,
    )

    assert len(result.evaluated) == 2
    assert result.telemetry.attempted_invoices == 2
    assert len(result.attempts) == 2


def test_partial_experiment_failure_retains_previous_attempts():
    first = generate_legitimate_example(9401, "C1")
    second = generate_legitimate_example(9402, "C1")

    calls = 0

    def fails_on_second(case):
        nonlocal calls
        calls += 1

        if calls == 2:
            raise RuntimeError("Simulated second-invoice failure")

        return SystemDecision(
            system_name=SystemName.DETERMINISTIC_BASELINE,
            action=ExpectedAction.AUTO_APPROVE,
        )

    with pytest.raises(ExperimentExecutionError) as captured:
        run_experiment(
            [[first], [second]],
            fails_on_second,
            run_id="dev-partial-failure",
            system_name=SystemName.DETERMINISTIC_BASELINE,
        )

    attempts = captured.value.attempts

    assert len(attempts) == 2
    assert attempts[0].status == "COMPLETED"
    assert attempts[1].status == "FAILED"
    assert attempts[1].action is None
    assert attempts[1].error_type == "RuntimeError"


def test_experiment_runner_preserves_original_benchmark():
    example = generate_legitimate_example(9403, "C1")
    original = example.case.model_copy(deep=True)

    def mutating_system(case):
        case.invoice.raw_text = "Modified by system"

        return SystemDecision(
            system_name=SystemName.DETERMINISTIC_BASELINE,
            action=ExpectedAction.AUTO_APPROVE,
        )

    result = run_experiment(
        [[example]],
        mutating_system,
        run_id="dev-isolation",
        system_name=SystemName.DETERMINISTIC_BASELINE,
    )

    assert example.case == original
    assert result.evaluated[0][0].example.case == original


def test_t4_sequence_preserves_all_invoice_executions():
    from governed_ap.benchmark_generator import (
        generate_development_sequence_attack,
    )

    scenario = generate_development_sequence_attack(
        seed=9404,
        attack_subtype="T4.1",
    )

    result = run_experiment(
        [scenario],
        evaluate_deterministic_baseline,
        run_id="dev-t4-execution",
        system_name=SystemName.DETERMINISTIC_BASELINE,
    )

    assert len(result.evaluated) == 1
    assert len(result.evaluated[0]) == 3
    assert len(result.attempts) == 3
    assert result.telemetry.attempted_invoices == 3


def test_metered_naive_llm_usage_reaches_experiment_telemetry():
    class MeasuredNaiveProvider:
        def complete_with_usage(self, *, system_prompt, user_prompt):
            return CompletionWithUsage(
                text=('{"action":"AUTO_APPROVE","reason_codes":[],"confidence":0.8}'),
                input_tokens=120,
                output_tokens=30,
                cost_usd=Decimal("0.005"),
                cost_basis="estimated",
                provider="test-provider",
                model="test-model",
            )

    collector = UsageCollector()

    provider = MeteredTextProvider(
        MeasuredNaiveProvider(),
        collector,
        role="naive",
    )

    result = run_experiment(
        [[_example()]],
        partial(evaluate_naive_llm, provider=provider),
        run_id="dev-metered-naive",
        system_name=SystemName.NAIVE_LLM,
        usage_collector=collector,
    )

    telemetry = result.telemetry

    assert telemetry.observed_llm_calls == 1
    assert telemetry.input_tokens == 120
    assert telemetry.output_tokens == 30
    assert telemetry.provider_cost_usd == Decimal("0.005")
    assert telemetry.cost_covered_calls == 1
    assert result.attempts[0].llm_calls[0].role == "naive"
