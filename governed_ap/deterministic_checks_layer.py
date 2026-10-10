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
    GoodsReceiptStatus,
    PaymentStatus,
)


def _append_reason(
    reasons: list[str],
    reason: str,
) -> None:
    if reason not in reasons:
        reasons.append(reason)


def _check_block_rules(
    case: BenchmarkCase,
) -> list[str]:
    reasons: list[str] = []

    purchase_order = case.purchase_order
    invoice = case.invoice

    if purchase_order is None:
        return ["NO_PO"]

    exact_duplicate = any(
        payment.status == PaymentStatus.PAID
        and payment.vendor_id == purchase_order.vendor_id
        and payment.invoice_id == invoice.invoice_id
        and payment.amount == invoice.total_amount
        and payment.currency == invoice.currency
        and payment.payment_date <= invoice.invoice_date
        for payment in case.payment_history
    )

    if exact_duplicate:
        _append_reason(
            reasons,
            "EXACT_DUPLICATE",
        )

    committed_statuses = {
        PaymentStatus.APPROVED,
        PaymentStatus.PAID,
    }

    committed_po_amount = sum(
        (
            payment.amount
            for payment in case.payment_history
            if (
                payment.po_id == purchase_order.po_id
                and payment.currency == purchase_order.currency
                and payment.status in committed_statuses
            )
        ),
        Decimal("0"),
    )

    if committed_po_amount >= purchase_order.total_amount:
        _append_reason(
            reasons,
            "PO_FULLY_INVOICED",
        )

    return reasons


def _check_vendor_po_match(
    case: BenchmarkCase,
    reasons: list[str],
) -> None:
    resolution = resolve_vendor_identity(case)

    if not resolution.matches_po_vendor:
        _append_reason(
            reasons,
            "VENDOR_PO_MISMATCH",
        )


def _check_price(
    case: BenchmarkCase,
    reasons: list[str],
) -> None:
    purchase_order = case.purchase_order

    if purchase_order is None:
        return

    invoice = case.invoice

    difference = abs(invoice.unit_price - purchase_order.unit_price)

    allowed_difference = purchase_order.unit_price * case.policy.price_tolerance

    if difference > allowed_difference:
        _append_reason(
            reasons,
            "PRICE_MISMATCH",
        )


def _check_quantity(
    case: BenchmarkCase,
    reasons: list[str],
) -> None:
    purchase_order = case.purchase_order

    if purchase_order is None:
        return

    invoice = case.invoice

    accepted_receipts = [
        receipt
        for receipt in case.goods_receipts
        if (
            receipt.po_id == purchase_order.po_id
            and receipt.status
            in {
                GoodsReceiptStatus.RECEIVED,
                GoodsReceiptStatus.PARTIAL,
            }
        )
    ]

    received_quantity = sum(
        (receipt.quantity_received for receipt in accepted_receipts),
        Decimal("0"),
    )

    quantity_limit = received_quantity + case.policy.quantity_tolerance

    if invoice.quantity > quantity_limit:
        _append_reason(
            reasons,
            "QUANTITY_MISMATCH",
        )

    ordered_limit = purchase_order.quantity_ordered + case.policy.quantity_tolerance

    if invoice.quantity > ordered_limit:
        _append_reason(
            reasons,
            "QUANTITY_MISMATCH",
        )


def _check_tax(
    case: BenchmarkCase,
    reasons: list[str],
) -> None:
    tax_rate = case.policy.tax_rate

    if tax_rate is None:
        return

    invoice = case.invoice

    expected_tax = (invoice.subtotal * tax_rate).quantize(Decimal("0.01"))

    if abs(invoice.tax_amount - expected_tax) > Decimal("0.01"):
        _append_reason(
            reasons,
            "TAX_MISMATCH",
        )


def _check_conflicting_values(
    case: BenchmarkCase,
    reasons: list[str],
) -> None:
    invoice = case.invoice

    calculated_subtotal = invoice.quantity * invoice.unit_price

    if calculated_subtotal != invoice.subtotal:
        _append_reason(
            reasons,
            "CONFLICTING_VALUES",
        )

    calculated_total = invoice.subtotal + invoice.tax_amount

    if calculated_total != invoice.total_amount:
        _append_reason(
            reasons,
            "CONFLICTING_VALUES",
        )

    if len(set(invoice.stated_totals)) > 1:
        _append_reason(
            reasons,
            "CONFLICTING_VALUES",
        )


def _check_scope(
    case: BenchmarkCase,
    reasons: list[str],
) -> None:
    purchase_order = case.purchase_order

    if purchase_order is None:
        return

    invoice = case.invoice

    if not invoice.line_items or not purchase_order.line_items:
        return

    ordered_items = {item.casefold().strip() for item in purchase_order.line_items}

    billed_items = {item.casefold().strip() for item in invoice.line_items}

    if not billed_items.issubset(ordered_items):
        _append_reason(
            reasons,
            "UNORDERED_ITEMS",
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


class DeterministicChecksLayer:
    def evaluate(
        self,
        case: BenchmarkCase,
    ) -> GovernanceLayerResult:
        block_reasons = _check_block_rules(case)

        if block_reasons:
            return GovernanceLayerResult(
                layer=(GovernanceLayerName.DETERMINISTIC_CHECKS),
                status=(LayerExecutionStatus.FIRED),
                minimum_action=(ExpectedAction.BLOCK),
                reason_codes=block_reasons,
            )

        reasons: list[str] = []

        _check_vendor_po_match(
            case,
            reasons,
        )

        _check_price(
            case,
            reasons,
        )

        _check_quantity(
            case,
            reasons,
        )

        _check_tax(
            case,
            reasons,
        )

        _check_conflicting_values(
            case,
            reasons,
        )

        _check_scope(
            case,
            reasons,
        )

        _check_possible_duplicate(
            case,
            reasons,
        )

        if reasons:
            return GovernanceLayerResult(
                layer=(GovernanceLayerName.DETERMINISTIC_CHECKS),
                status=(LayerExecutionStatus.FIRED),
                minimum_action=(ExpectedAction.ESCALATE),
                reason_codes=reasons,
            )

        return GovernanceLayerResult(
            layer=(GovernanceLayerName.DETERMINISTIC_CHECKS),
            status=(LayerExecutionStatus.PASS),
        )
