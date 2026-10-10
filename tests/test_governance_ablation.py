from pathlib import Path

import pytest

from governed_ap.benchmark_generator import (
    generate_development_attack_example,
    generate_legitimate_example,
)
from governed_ap.evaluation_integrity import find_system_label_access
from governed_ap.governance_ablation import (
    ALL_LAYERS,
    AblationConfig,
    AblationLangGraphAgent,
    ablation_plan,
)
from governed_ap.governance_contracts import (
    GovernanceLayerName,
    LayerExecutionStatus,
)
from governed_ap.langgraph_agent import LangGraphGovernedAPAgent
from governed_ap.schemas import ExpectedAction


class FakeProvider:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def complete(self, *, system_prompt, user_prompt):
        self.calls += 1
        return self.response


def guardrail():
    return FakeProvider('{"flagged":false,"reason_codes":[]}')


def decision():
    return FakeProvider('{"action":"AUTO_APPROVE","reason_codes":[],"confidence":0.9}')


def agent(enabled_layers, guardrail_provider=None):
    return AblationLangGraphAgent(
        config=AblationConfig(
            "test_configuration",
            frozenset(enabled_layers),
        ),
        guardrail_provider=guardrail_provider or guardrail(),
        decision_provider=decision(),
    )


def test_ablation_plan_has_expected_conditions():
    plan = ablation_plan()

    assert len(plan) == 9
    assert plan[0].enabled_layers == frozenset()
    assert plan[4].enabled_layers == ALL_LAYERS
    assert len({item.name for item in plan}) == 9


def test_full_configuration_matches_original_graph():
    case = generate_legitimate_example(10101, "C1").case

    original = LangGraphGovernedAPAgent(
        guardrail_provider=guardrail(),
        decision_provider=decision(),
    )

    ablated = agent(ALL_LAYERS)

    assert original.process(case).model_dump() == ablated.process(case).model_dump()


def test_disabled_guardrail_is_not_called():
    case = generate_development_attack_example(10102, "T1.1").case

    provider = guardrail()

    ablated = agent(
        ALL_LAYERS - {GovernanceLayerName.GUARDRAIL},
        guardrail_provider=provider,
    )

    trace = ablated.process(case)

    assert provider.calls == 0
    assert trace.layer_results[1].status == (LayerExecutionStatus.NOT_EVALUATED)


def test_removing_policy_changes_large_invoice_decision():
    case = generate_legitimate_example(10103, "C4").case

    full = agent(ALL_LAYERS).process(case)

    without_policy = agent(ALL_LAYERS - {GovernanceLayerName.POLICY_ENGINE}).process(case)

    assert full.final_action == ExpectedAction.ESCALATE
    assert without_policy.final_action == ExpectedAction.AUTO_APPROVE


def test_removed_deterministic_check_cannot_authorize_block():
    case = generate_development_attack_example(10104, "T3.3").case

    full = agent(ALL_LAYERS).process(case)

    without_checks = agent(ALL_LAYERS - {GovernanceLayerName.DETERMINISTIC_CHECKS}).process(case)

    assert full.final_action == ExpectedAction.BLOCK
    assert without_checks.final_action != ExpectedAction.BLOCK


def test_gate_still_protects_bank_redirection():
    case = generate_development_attack_example(10105, "T2.1").case

    trace = agent(frozenset()).process(case)

    assert trace.final_action == ExpectedAction.ESCALATE
    assert trace.enforcement.trusted_payment_destination == (case.vendor.approved_bank_account)


def test_enabled_policy_failure_still_fails_closed(monkeypatch):
    def broken_policy(self, case):
        raise RuntimeError("Simulated policy failure")

    monkeypatch.setattr(
        "governed_ap.langgraph_agent.PolicyEngineLayer.evaluate",
        broken_policy,
    )

    case = generate_legitimate_example(10106, "C1").case

    trace = agent(ALL_LAYERS).process(case)

    assert trace.final_action == ExpectedAction.ESCALATE
    assert "SYSTEM_POLICY_ENGINE_FAILURE" in (trace.layer_results[3].reason_codes)


def test_disabled_policy_is_not_executed(monkeypatch):
    def broken_policy(self, case):
        raise RuntimeError("Should not execute")

    monkeypatch.setattr(
        "governed_ap.langgraph_agent.PolicyEngineLayer.evaluate",
        broken_policy,
    )

    case = generate_legitimate_example(10107, "C1").case

    trace = agent(ALL_LAYERS - {GovernanceLayerName.POLICY_ENGINE}).process(case)

    assert trace.layer_results[3].status == (LayerExecutionStatus.NOT_EVALUATED)
    assert trace.final_action == ExpectedAction.AUTO_APPROVE


def test_invalid_configuration_is_rejected():
    with pytest.raises(ValueError, match="Unknown governance layer"):
        AblationConfig(
            "invalid",
            frozenset({"not_a_real_layer"}),
        )


def test_ablation_module_does_not_access_hidden_labels():
    package = Path(__file__).resolve().parents[1] / "governed_ap"

    findings = find_system_label_access(
        package,
        filenames=("governance_ablation.py",),
    )

    assert findings == []
