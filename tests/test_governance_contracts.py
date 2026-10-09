from decimal import Decimal

import pytest
from pydantic import ValidationError

from governed_ap.governance_contracts import (
    DecisionAgentRecommendation,
    GovernanceLayerName,
    GovernanceLayerResult,
    LayerExecutionStatus,
    LayerTelemetry,
)
from governed_ap.schemas import (
    ExpectedAction,
)


def test_pass_result_is_valid():
    result = GovernanceLayerResult(
        layer=(GovernanceLayerName.DETERMINISTIC_CHECKS),
        status=LayerExecutionStatus.PASS,
    )

    assert result.status == LayerExecutionStatus.PASS

    assert result.minimum_action is None
    assert result.reason_codes == []


def test_escalation_result_is_valid():
    result = GovernanceLayerResult(
        layer=(GovernanceLayerName.POLICY_ENGINE),
        status=LayerExecutionStatus.FIRED,
        minimum_action=(ExpectedAction.ESCALATE),
        reason_codes=["OVER_INVOICE_LIMIT"],
    )

    assert result.minimum_action == ExpectedAction.ESCALATE


def test_block_result_is_valid():
    result = GovernanceLayerResult(
        layer=(GovernanceLayerName.DETERMINISTIC_CHECKS),
        status=LayerExecutionStatus.FIRED,
        minimum_action=(ExpectedAction.BLOCK),
        reason_codes=["EXACT_DUPLICATE"],
    )

    assert result.minimum_action == ExpectedAction.BLOCK


def test_fired_layer_requires_reason():
    with pytest.raises(
        ValidationError,
        match="at least one reason",
    ):
        GovernanceLayerResult(
            layer=(GovernanceLayerName.POLICY_ENGINE),
            status=(LayerExecutionStatus.FIRED),
            minimum_action=(ExpectedAction.ESCALATE),
        )


def test_fired_layer_cannot_auto_approve():
    with pytest.raises(
        ValidationError,
        match="ESCALATE or BLOCK",
    ):
        GovernanceLayerResult(
            layer=(GovernanceLayerName.POLICY_ENGINE),
            status=(LayerExecutionStatus.FIRED),
            minimum_action=(ExpectedAction.AUTO_APPROVE),
            reason_codes=["INVALID_TEST_REASON"],
        )


def test_pass_layer_cannot_require_action():
    with pytest.raises(
        ValidationError,
        match="cannot require an action",
    ):
        GovernanceLayerResult(
            layer=(GovernanceLayerName.POLICY_ENGINE),
            status=(LayerExecutionStatus.PASS),
            minimum_action=(ExpectedAction.ESCALATE),
        )


def test_pass_layer_cannot_have_reasons():
    with pytest.raises(
        ValidationError,
        match="cannot provide reason codes",
    ):
        GovernanceLayerResult(
            layer=(GovernanceLayerName.POLICY_ENGINE),
            status=(LayerExecutionStatus.PASS),
            reason_codes=["SHOULD_NOT_EXIST"],
        )


def test_not_evaluated_layer_is_empty():
    result = GovernanceLayerResult(
        layer=(GovernanceLayerName.GUARDRAIL),
        status=(LayerExecutionStatus.NOT_EVALUATED),
    )

    assert result.minimum_action is None
    assert result.reason_codes == []


def test_duplicate_reason_codes_are_rejected():
    with pytest.raises(
        ValidationError,
        match="must be unique",
    ):
        GovernanceLayerResult(
            layer=(GovernanceLayerName.POLICY_ENGINE),
            status=(LayerExecutionStatus.FIRED),
            minimum_action=(ExpectedAction.ESCALATE),
            reason_codes=[
                "NEW_VENDOR",
                "NEW_VENDOR",
            ],
        )


def test_telemetry_accepts_cost_data():
    telemetry = LayerTelemetry(
        latency_ms=125.4,
        input_tokens=500,
        output_tokens=80,
        estimated_cost_usd=(Decimal("0.0015")),
        provider="test-provider",
        model="test-model",
    )

    assert telemetry.latency_ms == 125.4
    assert telemetry.input_tokens == 500
    assert telemetry.output_tokens == 80

    assert telemetry.estimated_cost_usd == Decimal("0.0015")


def test_negative_telemetry_is_rejected():
    with pytest.raises(
        ValidationError,
    ):
        LayerTelemetry(
            latency_ms=-1,
        )


def test_decision_recommendation_accepts_confidence():
    recommendation = DecisionAgentRecommendation(
        action=(ExpectedAction.ESCALATE),
        reason_codes=["MODEL_UNCERTAIN"],
        confidence=0.72,
    )

    assert recommendation.action == ExpectedAction.ESCALATE

    assert recommendation.confidence == 0.72


def test_confidence_above_one_is_rejected():
    with pytest.raises(
        ValidationError,
    ):
        DecisionAgentRecommendation(
            action=(ExpectedAction.AUTO_APPROVE),
            confidence=1.5,
        )


def test_decision_reason_codes_must_be_unique():
    with pytest.raises(
        ValidationError,
        match="must be unique",
    ):
        DecisionAgentRecommendation(
            action=(ExpectedAction.ESCALATE),
            reason_codes=[
                "UNCERTAIN",
                "UNCERTAIN",
            ],
        )
