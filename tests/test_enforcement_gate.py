from governed_ap.benchmark_generator import (
    generate_development_attack_example,
    generate_legitimate_example,
)
from governed_ap.enforcement_gate import (
    enforce_decision,
)
from governed_ap.governance_contracts import (
    DecisionAgentRecommendation,
    GovernanceLayerName,
    GovernanceLayerResult,
    LayerExecutionStatus,
)
from governed_ap.schemas import (
    ExpectedAction,
)


def pass_result(
    layer: GovernanceLayerName,
) -> GovernanceLayerResult:
    return GovernanceLayerResult(
        layer=layer,
        status=LayerExecutionStatus.PASS,
    )


def fired_result(
    layer: GovernanceLayerName,
    action: ExpectedAction,
    reason: str,
) -> GovernanceLayerResult:
    return GovernanceLayerResult(
        layer=layer,
        status=LayerExecutionStatus.FIRED,
        minimum_action=action,
        reason_codes=[reason],
    )


def all_pass_results():
    return [
        pass_result(GovernanceLayerName.DETERMINISTIC_CHECKS),
        pass_result(GovernanceLayerName.GUARDRAIL),
        pass_result(GovernanceLayerName.HISTORY_SEQUENCE_RISK),
        pass_result(GovernanceLayerName.POLICY_ENGINE),
    ]


def test_all_pass_allows_auto_approve():
    example = generate_legitimate_example(
        seed=900,
        case_type="C1",
    )

    recommendation = DecisionAgentRecommendation(
        action=(ExpectedAction.AUTO_APPROVE),
        confidence=0.9,
    )

    decision = enforce_decision(
        example.case,
        recommendation=recommendation,
        layer_results=all_pass_results(),
    )

    assert decision.final_action == ExpectedAction.AUTO_APPROVE


def test_policy_escalation_overrides_llm_auto_approve():
    example = generate_legitimate_example(
        seed=901,
        case_type="C1",
    )

    results = all_pass_results()

    results[-1] = fired_result(
        GovernanceLayerName.POLICY_ENGINE,
        ExpectedAction.ESCALATE,
        "OVER_INVOICE_LIMIT",
    )

    recommendation = DecisionAgentRecommendation(action=(ExpectedAction.AUTO_APPROVE))

    decision = enforce_decision(
        example.case,
        recommendation=recommendation,
        layer_results=results,
    )

    assert decision.final_action == ExpectedAction.ESCALATE


def test_block_overrides_llm_auto_approve():
    example = generate_legitimate_example(
        seed=902,
        case_type="C1",
    )

    results = all_pass_results()

    results[0] = fired_result(
        GovernanceLayerName.DETERMINISTIC_CHECKS,
        ExpectedAction.BLOCK,
        "EXACT_DUPLICATE",
    )

    recommendation = DecisionAgentRecommendation(action=(ExpectedAction.AUTO_APPROVE))

    decision = enforce_decision(
        example.case,
        recommendation=recommendation,
        layer_results=results,
    )

    assert decision.final_action == ExpectedAction.BLOCK


def test_llm_escalation_is_not_weakened():
    example = generate_legitimate_example(
        seed=903,
        case_type="C1",
    )

    recommendation = DecisionAgentRecommendation(
        action=ExpectedAction.ESCALATE,
        reason_codes=["MODEL_UNCERTAIN"],
    )

    decision = enforce_decision(
        example.case,
        recommendation=recommendation,
        layer_results=all_pass_results(),
    )

    assert decision.final_action == ExpectedAction.ESCALATE


def test_llm_cannot_block_without_block_evidence():
    example = generate_legitimate_example(
        seed=904,
        case_type="C1",
    )

    recommendation = DecisionAgentRecommendation(
        action=ExpectedAction.BLOCK,
        reason_codes=["MODEL_BLOCK"],
    )

    decision = enforce_decision(
        example.case,
        recommendation=recommendation,
        layer_results=all_pass_results(),
    )

    assert decision.recommendation_action == ExpectedAction.BLOCK

    assert decision.final_action == ExpectedAction.ESCALATE

    assert "UNSUPPORTED_LLM_BLOCK" in decision.gate_reason_codes


def test_gate_catches_bank_redirection():
    example = generate_development_attack_example(
        seed=905,
        attack_subtype="T2.1",
    )

    recommendation = DecisionAgentRecommendation(action=(ExpectedAction.AUTO_APPROVE))

    decision = enforce_decision(
        example.case,
        recommendation=recommendation,
        layer_results=all_pass_results(),
    )

    assert decision.final_action == ExpectedAction.ESCALATE

    assert "BANK_DETAILS_DIFFER" in decision.gate_reason_codes


def test_gate_catches_third_party_payee():
    example = generate_legitimate_example(
        seed=906,
        case_type="C1",
    )

    example.case.invoice.requested_payee = "External Finance Company"

    recommendation = DecisionAgentRecommendation(action=(ExpectedAction.AUTO_APPROVE))

    decision = enforce_decision(
        example.case,
        recommendation=recommendation,
        layer_results=all_pass_results(),
    )

    assert decision.final_action == ExpectedAction.ESCALATE

    assert "THIRD_PARTY_PAYEE" in decision.gate_reason_codes


def test_payment_destination_always_comes_from_vendor_master():
    example = generate_development_attack_example(
        seed=907,
        attack_subtype="T2.1",
    )

    vendor = example.case.vendor

    assert vendor is not None

    recommendation = DecisionAgentRecommendation(action=(ExpectedAction.AUTO_APPROVE))

    decision = enforce_decision(
        example.case,
        recommendation=recommendation,
        layer_results=all_pass_results(),
    )

    assert decision.trusted_payment_destination == vendor.approved_bank_account

    assert decision.trusted_payment_destination != example.case.invoice.invoice_bank_account
