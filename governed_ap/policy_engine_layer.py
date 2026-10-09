from decimal import Decimal

from governed_ap.governance_contracts import (
    GovernanceLayerName,
    GovernanceLayerResult,
    LayerExecutionStatus,
)
from governed_ap.identity_resolver import (
    resolve_vendor_identity,
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


def _check_invoice_limit(
    case: BenchmarkCase,
    reasons: list[str],
) -> None:
    limit = case.policy.invoice_limit

    if limit is None:
        return

    if case.invoice.total_amount > limit:
        _append_reason(
            reasons,
            "OVER_INVOICE_LIMIT",
        )


def _check_vendor_window_limit(
    case: BenchmarkCase,
    reasons: list[str],
) -> None:
    limit = case.policy.vendor_window_limit

    if limit is None:
        return

    resolution = resolve_vendor_identity(case)

    vendor_id = resolution.resolved_vendor_id

    if vendor_id is None:
        return

    invoice = case.invoice

    committed_statuses = {
        PaymentStatus.APPROVED,
        PaymentStatus.PAID,
    }

    previous_auto_approved = sum(
        (
            payment.amount
            for payment in case.payment_history
            if (
                payment.vendor_id == vendor_id
                and payment.currency == invoice.currency
                and payment.status in committed_statuses
                and payment.was_auto_approved
                and 0
                <= (invoice.invoice_date - payment.payment_date).days
                < case.policy.vendor_window_days
            )
        ),
        Decimal("0"),
    )

    if previous_auto_approved + invoice.total_amount > limit:
        _append_reason(
            reasons,
            "VENDOR_WINDOW_LIMIT",
        )


def _check_po_cumulative_limit(
    case: BenchmarkCase,
    reasons: list[str],
) -> None:
    limit = case.policy.po_cumulative_limit

    purchase_order = case.purchase_order

    if limit is None or purchase_order is None:
        return

    invoice = case.invoice

    committed_statuses = {
        PaymentStatus.APPROVED,
        PaymentStatus.PAID,
    }

    previous_auto_approved = sum(
        (
            payment.amount
            for payment in case.payment_history
            if (
                payment.po_id == purchase_order.po_id
                and payment.currency == invoice.currency
                and payment.status in committed_statuses
                and payment.was_auto_approved
            )
        ),
        Decimal("0"),
    )

    if previous_auto_approved + invoice.total_amount > limit:
        _append_reason(
            reasons,
            "PO_CUMULATIVE_LIMIT",
        )


def _check_new_vendor(
    case: BenchmarkCase,
    reasons: list[str],
) -> None:
    vendor = case.vendor

    if vendor is None or vendor.created_date is None:
        return

    resolution = resolve_vendor_identity(case)

    if resolution.resolved_vendor_id is None:
        return

    vendor_age_days = (case.invoice.invoice_date - vendor.created_date).days

    if vendor_age_days < case.policy.new_vendor_days:
        _append_reason(
            reasons,
            "NEW_VENDOR",
        )


class PolicyEngineLayer:
    def evaluate(
        self,
        case: BenchmarkCase,
    ) -> GovernanceLayerResult:
        reasons: list[str] = []

        _check_invoice_limit(
            case,
            reasons,
        )

        _check_vendor_window_limit(
            case,
            reasons,
        )

        _check_po_cumulative_limit(
            case,
            reasons,
        )

        _check_new_vendor(
            case,
            reasons,
        )

        if reasons:
            return GovernanceLayerResult(
                layer=(GovernanceLayerName.POLICY_ENGINE),
                status=(LayerExecutionStatus.FIRED),
                minimum_action=(ExpectedAction.ESCALATE),
                reason_codes=reasons,
            )

        return GovernanceLayerResult(
            layer=(GovernanceLayerName.POLICY_ENGINE),
            status=(LayerExecutionStatus.PASS),
        )
