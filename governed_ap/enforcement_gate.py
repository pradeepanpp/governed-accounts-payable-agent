from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from governed_ap.governance_contracts import (
    DecisionAgentRecommendation,
    GovernanceLayerResult,
    LayerExecutionStatus,
)
from governed_ap.identity_resolver import (
    normalize_vendor_name,
    trusted_vendor_names,
)
from governed_ap.schemas import (
    BenchmarkCase,
    ExpectedAction,
)

ACTION_RANK = {
    ExpectedAction.AUTO_APPROVE: 0,
    ExpectedAction.ESCALATE: 1,
    ExpectedAction.BLOCK: 2,
}

AUTHORIZED_BLOCK_REASONS = {
    "EXACT_DUPLICATE",
    "NO_PO",
    "PO_FULLY_INVOICED",
}


class EnforcementGateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    final_action: ExpectedAction

    recommendation_action: ExpectedAction

    governance_floor: ExpectedAction

    reason_codes: list[str] = Field(default_factory=list)

    gate_reason_codes: list[str] = Field(default_factory=list)

    trusted_payment_destination: str | None = None


def _stricter_action(
    first: ExpectedAction,
    second: ExpectedAction,
) -> ExpectedAction:
    if ACTION_RANK[second] > ACTION_RANK[first]:
        return second

    return first


def _append_unique(
    target: list[str],
    values: list[str],
) -> None:
    for value in values:
        if value not in target:
            target.append(value)


def _governance_floor(
    layer_results: list[GovernanceLayerResult],
) -> ExpectedAction:
    floor = ExpectedAction.AUTO_APPROVE

    for result in layer_results:
        if result.status != LayerExecutionStatus.FIRED or result.minimum_action is None:
            continue

        floor = _stricter_action(
            floor,
            result.minimum_action,
        )

    return floor


def _gate_payment_risk_reasons(
    case: BenchmarkCase,
) -> list[str]:
    vendor = case.vendor

    if vendor is None:
        return []

    reasons: list[str] = []

    invoice_bank = case.invoice.invoice_bank_account

    if invoice_bank is not None and invoice_bank != vendor.approved_bank_account:
        reasons.append("BANK_DETAILS_DIFFER")

    requested_payee = case.invoice.requested_payee

    if requested_payee:
        trusted_names = trusted_vendor_names(case)

        normalized_payee = normalize_vendor_name(requested_payee)

        if normalized_payee not in trusted_names:
            reasons.append("THIRD_PARTY_PAYEE")

    return reasons


def _authorized_block_present(
    layer_results: list[GovernanceLayerResult],
) -> bool:
    for result in layer_results:
        if result.status != LayerExecutionStatus.FIRED:
            continue

        if result.minimum_action != ExpectedAction.BLOCK:
            continue

        if any(reason in AUTHORIZED_BLOCK_REASONS for reason in result.reason_codes):
            return True

    return False


def enforce_decision(
    case: BenchmarkCase,
    *,
    recommendation: (DecisionAgentRecommendation),
    layer_results: list[GovernanceLayerResult],
) -> EnforcementGateDecision:
    governance_floor = _governance_floor(layer_results)

    gate_reason_codes = _gate_payment_risk_reasons(case)

    if gate_reason_codes:
        governance_floor = _stricter_action(
            governance_floor,
            ExpectedAction.ESCALATE,
        )
    authorized_block = _authorized_block_present(layer_results)

    if governance_floor == ExpectedAction.BLOCK and not authorized_block:
        governance_floor = ExpectedAction.ESCALATE
        gate_reason_codes.append("UNSUPPORTED_GOVERNANCE_BLOCK")

    effective_recommendation = recommendation.action

    if recommendation.action == ExpectedAction.BLOCK and not authorized_block:
        effective_recommendation = ExpectedAction.ESCALATE
        gate_reason_codes.append("UNSUPPORTED_LLM_BLOCK")

    final_action = _stricter_action(
        effective_recommendation,
        governance_floor,
    )

    reason_codes: list[str] = []

    _append_unique(
        reason_codes,
        recommendation.reason_codes,
    )

    for result in layer_results:
        if result.status == LayerExecutionStatus.FIRED:
            _append_unique(
                reason_codes,
                result.reason_codes,
            )

    _append_unique(
        reason_codes,
        gate_reason_codes,
    )

    trusted_destination = None

    if case.vendor is not None:
        trusted_destination = case.vendor.approved_bank_account

    return EnforcementGateDecision(
        final_action=final_action,
        recommendation_action=(recommendation.action),
        governance_floor=(governance_floor),
        reason_codes=reason_codes,
        gate_reason_codes=(gate_reason_codes),
        trusted_payment_destination=(trusted_destination),
    )
