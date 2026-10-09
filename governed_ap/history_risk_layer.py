from governed_ap.governance_contracts import (
    GovernanceLayerName,
    GovernanceLayerResult,
    LayerExecutionStatus,
)
from governed_ap.identity_resolver import (
    normalize_vendor_name,
    resolve_vendor_identity,
    trusted_vendor_names,
)
from governed_ap.schemas import (
    BenchmarkCase,
    ExpectedAction,
    PaymentStatus,
)


def _append_reason(
    reasons: list[str],
    reason: str,
) -> None:
    if reason not in reasons:
        reasons.append(reason)


def _check_vendor_identity(
    case: BenchmarkCase,
    reasons: list[str],
) -> None:
    resolution = resolve_vendor_identity(case)

    if not resolution.matches_po_vendor:
        _append_reason(
            reasons,
            "VENDOR_PO_MISMATCH",
        )


def _check_bank_details(
    case: BenchmarkCase,
    reasons: list[str],
) -> None:
    vendor = case.vendor

    if vendor is None:
        return

    if case.invoice.invoice_bank_account != vendor.approved_bank_account:
        _append_reason(
            reasons,
            "BANK_DETAILS_DIFFER",
        )


def _check_requested_payee(
    case: BenchmarkCase,
    reasons: list[str],
) -> None:
    requested_payee = case.invoice.requested_payee

    if not requested_payee:
        return

    trusted_names = trusted_vendor_names(case)

    normalized_payee = normalize_vendor_name(requested_payee)

    if normalized_payee not in trusted_names:
        _append_reason(
            reasons,
            "THIRD_PARTY_PAYEE",
        )


def _check_possible_duplicate(
    case: BenchmarkCase,
    reasons: list[str],
) -> None:
    purchase_order = case.purchase_order

    if purchase_order is None:
        return

    resolution = resolve_vendor_identity(case)

    vendor_id = resolution.resolved_vendor_id

    if vendor_id is None:
        return

    invoice = case.invoice

    for payment in case.payment_history:
        if payment.status != PaymentStatus.PAID:
            continue

        if (
            payment.vendor_id != vendor_id
            or payment.po_id != purchase_order.po_id
            or payment.amount != invoice.total_amount
            or payment.currency != invoice.currency
            or payment.invoice_id == invoice.invoice_id
        ):
            continue

        age_days = (invoice.invoice_date - payment.payment_date).days

        if 0 <= age_days <= case.policy.duplicate_lookback_days:
            _append_reason(
                reasons,
                "POSSIBLE_DUPLICATE",
            )


class HistorySequenceRiskLayer:
    def evaluate(
        self,
        case: BenchmarkCase,
    ) -> GovernanceLayerResult:
        reasons: list[str] = []

        _check_vendor_identity(
            case,
            reasons,
        )

        _check_bank_details(
            case,
            reasons,
        )

        _check_requested_payee(
            case,
            reasons,
        )

        _check_possible_duplicate(
            case,
            reasons,
        )

        if reasons:
            return GovernanceLayerResult(
                layer=(GovernanceLayerName.HISTORY_SEQUENCE_RISK),
                status=(LayerExecutionStatus.FIRED),
                minimum_action=(ExpectedAction.ESCALATE),
                reason_codes=reasons,
            )

        return GovernanceLayerResult(
            layer=(GovernanceLayerName.HISTORY_SEQUENCE_RISK),
            status=(LayerExecutionStatus.PASS),
        )
