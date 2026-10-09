from governed_ap.benchmark_generator import (
    generate_development_attack_example,
    generate_legitimate_example,
)
from governed_ap.governance_contracts import (
    GovernanceLayerName,
    LayerExecutionStatus,
)
from governed_ap.governed_agent import (
    GovernedAPAgent,
)
from governed_ap.schemas import (
    ExpectedAction,
)


class CountingProvider:
    def __init__(
        self,
        response: str,
    ) -> None:
        self.response = response
        self.call_count = 0

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        self.call_count += 1

        return self.response


def passing_guardrail_provider():
    return CountingProvider(
        """
        {
            "flagged": false,
            "reason_codes": []
        }
        """
    )


def auto_approve_decision_provider():
    return CountingProvider(
        """
        {
            "action": "AUTO_APPROVE",
            "reason_codes": [],
            "confidence": 0.90
        }
        """
    )


def test_clean_invoice_can_auto_approve():
    example = generate_legitimate_example(
        seed=1000,
        case_type="C1",
    )

    agent = GovernedAPAgent(
        guardrail_provider=(passing_guardrail_provider()),
        decision_provider=(auto_approve_decision_provider()),
    )

    trace = agent.process(example.case)

    assert trace.final_action == ExpectedAction.AUTO_APPROVE

    assert all(result.status == LayerExecutionStatus.PASS for result in trace.layer_results)


def test_policy_can_override_llm():
    example = generate_legitimate_example(
        seed=1001,
        case_type="C4",
    )

    agent = GovernedAPAgent(
        guardrail_provider=(passing_guardrail_provider()),
        decision_provider=(auto_approve_decision_provider()),
    )

    trace = agent.process(example.case)

    assert trace.recommendation.action == ExpectedAction.AUTO_APPROVE

    assert trace.final_action == ExpectedAction.ESCALATE

    policy_result = next(
        result
        for result in trace.layer_results
        if (result.layer == GovernanceLayerName.POLICY_ENGINE)
    )

    assert "OVER_INVOICE_LIMIT" in policy_result.reason_codes


def test_guardrail_can_override_llm():
    example = generate_development_attack_example(
        seed=1002,
        attack_subtype="T1.1",
    )

    guardrail = CountingProvider(
        """
        {
            "flagged": true,
            "reason_codes": [
                "INSTRUCTION_TEXT"
            ]
        }
        """
    )

    decision = auto_approve_decision_provider()

    agent = GovernedAPAgent(
        guardrail_provider=guardrail,
        decision_provider=decision,
    )

    trace = agent.process(example.case)

    assert trace.recommendation.action == ExpectedAction.AUTO_APPROVE

    assert trace.final_action == ExpectedAction.ESCALATE


def test_exact_duplicate_is_blocked():
    example = generate_development_attack_example(
        seed=1003,
        attack_subtype="T3.3",
    )

    agent = GovernedAPAgent(
        guardrail_provider=(passing_guardrail_provider()),
        decision_provider=(auto_approve_decision_provider()),
    )

    trace = agent.process(example.case)

    assert trace.final_action == ExpectedAction.BLOCK


def test_all_layers_still_run_after_block():
    example = generate_development_attack_example(
        seed=1004,
        attack_subtype="T3.3",
    )

    guardrail = passing_guardrail_provider()

    decision = auto_approve_decision_provider()

    agent = GovernedAPAgent(
        guardrail_provider=guardrail,
        decision_provider=decision,
    )

    trace = agent.process(example.case)

    assert trace.final_action == ExpectedAction.BLOCK

    assert len(trace.layer_results) == 4

    assert guardrail.call_count == 1
    assert decision.call_count == 1


def test_trace_contains_each_governance_layer_once():
    example = generate_legitimate_example(
        seed=1005,
        case_type="C1",
    )

    agent = GovernedAPAgent(
        guardrail_provider=(passing_guardrail_provider()),
        decision_provider=(auto_approve_decision_provider()),
    )

    trace = agent.process(example.case)

    layers = [result.layer for result in trace.layer_results]

    assert layers == [
        GovernanceLayerName.DETERMINISTIC_CHECKS,
        GovernanceLayerName.GUARDRAIL,
        GovernanceLayerName.HISTORY_SEQUENCE_RISK,
        GovernanceLayerName.POLICY_ENGINE,
    ]


def test_bank_redirection_cannot_auto_approve():
    example = generate_development_attack_example(
        seed=1006,
        attack_subtype="T2.1",
    )

    agent = GovernedAPAgent(
        guardrail_provider=(passing_guardrail_provider()),
        decision_provider=(auto_approve_decision_provider()),
    )

    trace = agent.process(example.case)

    assert trace.final_action == ExpectedAction.ESCALATE

    assert "BANK_DETAILS_DIFFER" in trace.enforcement.reason_codes


def test_trace_keeps_llm_confidence():
    example = generate_legitimate_example(
        seed=1007,
        case_type="C1",
    )

    decision = CountingProvider(
        """
        {
            "action": "AUTO_APPROVE",
            "reason_codes": [],
            "confidence": 0.73
        }
        """
    )

    agent = GovernedAPAgent(
        guardrail_provider=(passing_guardrail_provider()),
        decision_provider=decision,
    )

    trace = agent.process(example.case)

    assert trace.recommendation.confidence == 0.73
