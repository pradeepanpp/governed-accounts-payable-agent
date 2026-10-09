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
from governed_ap.langgraph_agent import (
    LangGraphGovernedAPAgent,
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


def passing_guardrail():
    return CountingProvider(
        """
        {
            "flagged": false,
            "reason_codes": []
        }
        """
    )


def approving_decision():
    return CountingProvider(
        """
        {
            "action": "AUTO_APPROVE",
            "reason_codes": [],
            "confidence": 0.90
        }
        """
    )


def test_clean_case_runs_through_graph():
    example = generate_legitimate_example(
        seed=1100,
        case_type="C1",
    )

    agent = LangGraphGovernedAPAgent(
        guardrail_provider=(passing_guardrail()),
        decision_provider=(approving_decision()),
    )

    trace = agent.process(example.case)

    assert trace.final_action == ExpectedAction.AUTO_APPROVE


def test_graph_policy_overrides_llm():
    example = generate_legitimate_example(
        seed=1101,
        case_type="C4",
    )

    agent = LangGraphGovernedAPAgent(
        guardrail_provider=(passing_guardrail()),
        decision_provider=(approving_decision()),
    )

    trace = agent.process(example.case)

    assert trace.recommendation.action == ExpectedAction.AUTO_APPROVE

    assert trace.final_action == ExpectedAction.ESCALATE


def test_graph_keeps_all_layer_results():
    example = generate_legitimate_example(
        seed=1102,
        case_type="C1",
    )

    agent = LangGraphGovernedAPAgent(
        guardrail_provider=(passing_guardrail()),
        decision_provider=(approving_decision()),
    )

    trace = agent.process(example.case)

    assert [result.layer for result in trace.layer_results] == [
        GovernanceLayerName.DETERMINISTIC_CHECKS,
        GovernanceLayerName.GUARDRAIL,
        GovernanceLayerName.HISTORY_SEQUENCE_RISK,
        GovernanceLayerName.POLICY_ENGINE,
    ]


def test_graph_runs_llms_even_after_block():
    example = generate_development_attack_example(
        seed=1103,
        attack_subtype="T3.3",
    )

    guardrail = passing_guardrail()
    decision = approving_decision()

    agent = LangGraphGovernedAPAgent(
        guardrail_provider=guardrail,
        decision_provider=decision,
    )

    trace = agent.process(example.case)

    assert trace.final_action == ExpectedAction.BLOCK

    assert guardrail.call_count == 1
    assert decision.call_count == 1

    assert len(trace.layer_results) == 4


def test_graph_guardrail_can_escalate():
    example = generate_development_attack_example(
        seed=1104,
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

    agent = LangGraphGovernedAPAgent(
        guardrail_provider=guardrail,
        decision_provider=(approving_decision()),
    )

    trace = agent.process(example.case)

    guardrail_result = next(
        result for result in trace.layer_results if (result.layer == GovernanceLayerName.GUARDRAIL)
    )

    assert guardrail_result.status == LayerExecutionStatus.FIRED

    assert trace.final_action == ExpectedAction.ESCALATE


def test_graph_gate_still_protects_bank_redirection():
    example = generate_development_attack_example(
        seed=1105,
        attack_subtype="T2.1",
    )

    agent = LangGraphGovernedAPAgent(
        guardrail_provider=(passing_guardrail()),
        decision_provider=(approving_decision()),
    )

    trace = agent.process(example.case)

    assert trace.final_action == ExpectedAction.ESCALATE

    assert "BANK_DETAILS_DIFFER" in trace.enforcement.reason_codes


def test_graph_matches_plain_agent_for_clean_case():
    example = generate_legitimate_example(
        seed=1200,
        case_type="C1",
    )

    plain_agent = GovernedAPAgent(
        guardrail_provider=(passing_guardrail()),
        decision_provider=(approving_decision()),
    )

    graph_agent = LangGraphGovernedAPAgent(
        guardrail_provider=(passing_guardrail()),
        decision_provider=(approving_decision()),
    )

    plain_trace = plain_agent.process(example.case)

    graph_trace = graph_agent.process(example.case)

    assert graph_trace.model_dump() == plain_trace.model_dump()


def test_graph_matches_plain_agent_for_policy_case():
    example = generate_legitimate_example(
        seed=1201,
        case_type="C4",
    )

    plain_agent = GovernedAPAgent(
        guardrail_provider=(passing_guardrail()),
        decision_provider=(approving_decision()),
    )

    graph_agent = LangGraphGovernedAPAgent(
        guardrail_provider=(passing_guardrail()),
        decision_provider=(approving_decision()),
    )

    assert (
        graph_agent.process(example.case).model_dump()
        == plain_agent.process(example.case).model_dump()
    )


def test_graph_matches_plain_agent_for_block_case():
    example = generate_development_attack_example(
        seed=1202,
        attack_subtype="T3.3",
    )

    plain_agent = GovernedAPAgent(
        guardrail_provider=(passing_guardrail()),
        decision_provider=(approving_decision()),
    )

    graph_agent = LangGraphGovernedAPAgent(
        guardrail_provider=(passing_guardrail()),
        decision_provider=(approving_decision()),
    )

    assert (
        graph_agent.process(example.case).model_dump()
        == plain_agent.process(example.case).model_dump()
    )


def test_deterministic_failure_fails_closed_and_continues(
    monkeypatch,
):
    example = generate_legitimate_example(
        seed=1203,
        case_type="C1",
    )

    def raise_failure(
        self,
        case,
    ):
        raise RuntimeError("Simulated deterministic failure.")

    monkeypatch.setattr(
        ("governed_ap.langgraph_agent.DeterministicChecksLayer.evaluate"),
        raise_failure,
    )

    guardrail = passing_guardrail()
    decision = approving_decision()

    agent = LangGraphGovernedAPAgent(
        guardrail_provider=guardrail,
        decision_provider=decision,
    )

    trace = agent.process(example.case)

    deterministic = trace.layer_results[0]

    assert trace.final_action == ExpectedAction.ESCALATE

    assert deterministic.reason_codes == [("SYSTEM_DETERMINISTIC_CHECKS_FAILURE")]

    assert guardrail.call_count == 1
    assert decision.call_count == 1


def test_policy_failure_prevents_auto_approval(
    monkeypatch,
):
    example = generate_legitimate_example(
        seed=1204,
        case_type="C1",
    )

    def raise_failure(
        self,
        case,
    ):
        raise RuntimeError("Simulated policy failure.")

    monkeypatch.setattr(
        ("governed_ap.langgraph_agent.PolicyEngineLayer.evaluate"),
        raise_failure,
    )

    agent = LangGraphGovernedAPAgent(
        guardrail_provider=(passing_guardrail()),
        decision_provider=(approving_decision()),
    )

    trace = agent.process(example.case)

    assert trace.final_action == ExpectedAction.ESCALATE

    policy_result = next(
        result
        for result in trace.layer_results
        if (result.layer == GovernanceLayerName.POLICY_ENGINE)
    )

    assert policy_result.reason_codes == ["SYSTEM_POLICY_ENGINE_FAILURE"]


def test_graph_enforcement_failure_fails_closed(
    monkeypatch,
):
    example = generate_legitimate_example(
        seed=1205,
        case_type="C1",
    )

    def raise_failure(
        *args,
        **kwargs,
    ):
        raise RuntimeError("Simulated gate failure.")

    monkeypatch.setattr(
        ("governed_ap.langgraph_agent.enforce_decision"),
        raise_failure,
    )

    agent = LangGraphGovernedAPAgent(
        guardrail_provider=(passing_guardrail()),
        decision_provider=(approving_decision()),
    )

    trace = agent.process(example.case)

    assert trace.final_action == ExpectedAction.ESCALATE

    assert trace.enforcement.gate_reason_codes == [("SYSTEM_ENFORCEMENT_GATE_FAILURE")]

    assert trace.enforcement.trusted_payment_destination is None
