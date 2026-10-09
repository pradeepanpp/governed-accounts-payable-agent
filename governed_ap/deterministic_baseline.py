from datetime import timedelta
from decimal import Decimal

from governed_ap.schemas import (
    BenchmarkCase,
    ExpectedAction,
    GoodsReceiptStatus,
    PaymentStatus,
)
from governed_ap.system_decision import (
    SystemDecision,
    SystemName,
)

BLOCK_REASONS = {
    "NO_PO",
    "EXACT_DUPLICATE",
    "PO_FULLY_INVOICED",
}


def _normalize_name(
    value: str,
) -> str:
    return " ".join(value.casefold().split())


def _append_reason(
    reasons: list[str],
    reason: str,
) -> None:
    if reason not in reasons:
        reasons.append(reason)


def _trusted_vendor_names(
    case: BenchmarkCase,
) -> set[str]:
    if case.vendor is None:
        return set()

    names = {_normalize_name(case.vendor.legal_name)}

    names.update(_normalize_name(alias) for alias in case.vendor.aliases)

    return names


def _check_block_rules(
    case: BenchmarkCase,
) -> list[str]:
    reasons: list[str] = []

    invoice = case.invoice
    purchase_order = case.purchase_order

    if purchase_order is None:
        _append_reason(
            reasons,
            "NO_PO",
        )

        return reasons

    committed_statuses = {
        PaymentStatus.APPROVED,
        PaymentStatus.PAID,
    }

    vendor_id = purchase_order.vendor_id

    exact_duplicate = any(
        payment.status == PaymentStatus.PAID
        and payment.vendor_id == vendor_id
        and payment.invoice_id == invoice.invoice_id
        and payment.amount == invoice.total_amount
        and payment.currency == invoice.currency
        for payment in case.payment_history
    )

    if exact_duplicate:
        _append_reason(
            reasons,
            "EXACT_DUPLICATE",
        )

    committed_po_amount = sum(
        (
            payment.amount
            for payment in case.payment_history
            if (
                payment.status in committed_statuses
                and payment.po_id == purchase_order.po_id
                and payment.currency == purchase_order.currency
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


def _check_vendor_rules(
    case: BenchmarkCase,
    reasons: list[str],
) -> None:
    vendor = case.vendor
    purchase_order = case.purchase_order
    invoice = case.invoice
    policy = case.policy

    if purchase_order is None:
        return

    if vendor is None:
        _append_reason(
            reasons,
            "VENDOR_PO_MISMATCH",
        )
        return

    trusted_names = _trusted_vendor_names(case)

    claimed_name = _normalize_name(invoice.vendor_name)

    if vendor.vendor_id != purchase_order.vendor_id:
        _append_reason(
            reasons,
            "VENDOR_PO_MISMATCH",
        )

    if invoice.vendor_id_claim is not None and invoice.vendor_id_claim != purchase_order.vendor_id:
        _append_reason(
            reasons,
            "VENDOR_PO_MISMATCH",
        )

    if claimed_name not in trusted_names:
        _append_reason(
            reasons,
            "VENDOR_PO_MISMATCH",
        )

    if invoice.invoice_bank_account != vendor.approved_bank_account:
        _append_reason(
            reasons,
            "BANK_DETAILS_DIFFER",
        )

    if invoice.requested_payee:
        requested_payee = _normalize_name(invoice.requested_payee)

        if requested_payee not in trusted_names:
            _append_reason(
                reasons,
                "THIRD_PARTY_PAYEE",
            )

    if (
        vendor.created_date is not None
        and (invoice.invoice_date - vendor.created_date).days < policy.new_vendor_days
    ):
        _append_reason(
            reasons,
            "NEW_VENDOR",
        )


def _check_invoice_policy(
    case: BenchmarkCase,
    reasons: list[str],
) -> None:
    invoice = case.invoice
    policy = case.policy

    if policy.invoice_limit is not None and invoice.total_amount > policy.invoice_limit:
        _append_reason(
            reasons,
            "OVER_INVOICE_LIMIT",
        )


def _check_three_way_match(
    case: BenchmarkCase,
    reasons: list[str],
) -> None:
    purchase_order = case.purchase_order

    if purchase_order is None:
        return

    invoice = case.invoice
    policy = case.policy

    price_difference = abs(invoice.unit_price - purchase_order.unit_price)

    allowed_difference = purchase_order.unit_price * policy.price_tolerance

    if price_difference > allowed_difference:
        _append_reason(
            reasons,
            "PRICE_MISMATCH",
        )

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

    if invoice.quantity > received_quantity + policy.quantity_tolerance:
        _append_reason(
            reasons,
            "QUANTITY_MISMATCH",
        )

    if invoice.quantity > purchase_order.quantity_ordered + policy.quantity_tolerance:
        _append_reason(
            reasons,
            "QUANTITY_MISMATCH",
        )


def _check_invoice_integrity(
    case: BenchmarkCase,
    reasons: list[str],
) -> None:
    invoice = case.invoice
    policy = case.policy

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

    if policy.tax_rate is not None:
        expected_tax = (invoice.subtotal * policy.tax_rate).quantize(Decimal("0.01"))

        if abs(invoice.tax_amount - expected_tax) > Decimal("0.01"):
            _append_reason(
                reasons,
                "TAX_MISMATCH",
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

    allowed_items = {item.casefold().strip() for item in purchase_order.line_items}

    invoice_items = {item.casefold().strip() for item in invoice.line_items}

    if not invoice_items.issubset(allowed_items):
        _append_reason(
            reasons,
            "UNORDERED_ITEMS",
        )


def _check_possible_duplicate(
    case: BenchmarkCase,
    reasons: list[str],
) -> None:
    vendor = case.vendor
    purchase_order = case.purchase_order

    if vendor is None or purchase_order is None:
        return

    invoice = case.invoice
    policy = case.policy

    for payment in case.payment_history:
        if payment.status != PaymentStatus.PAID:
            continue

        if (
            payment.vendor_id != vendor.vendor_id
            or payment.po_id != purchase_order.po_id
            or payment.currency != invoice.currency
            or payment.amount != invoice.total_amount
            or payment.invoice_id == invoice.invoice_id
        ):
            continue

        age = invoice.invoice_date - payment.payment_date

        if timedelta(0) <= age <= timedelta(days=(policy.duplicate_lookback_days)):
            _append_reason(
                reasons,
                "POSSIBLE_DUPLICATE",
            )


def _check_stateful_policy(
    case: BenchmarkCase,
    reasons: list[str],
) -> None:
    vendor = case.vendor
    purchase_order = case.purchase_order
    invoice = case.invoice
    policy = case.policy

    committed_statuses = {
        PaymentStatus.APPROVED,
        PaymentStatus.PAID,
    }

    if vendor is not None and policy.vendor_window_limit is not None:
        recent_auto_approved = sum(
            (
                payment.amount
                for payment in case.payment_history
                if (
                    payment.vendor_id == vendor.vendor_id
                    and payment.currency == invoice.currency
                    and payment.status in committed_statuses
                    and payment.was_auto_approved
                    and 0
                    <= (invoice.invoice_date - payment.payment_date).days
                    < policy.vendor_window_days
                )
            ),
            Decimal("0"),
        )

        if recent_auto_approved + invoice.total_amount > policy.vendor_window_limit:
            _append_reason(
                reasons,
                "VENDOR_WINDOW_LIMIT",
            )

    if purchase_order is not None and policy.po_cumulative_limit is not None:
        po_auto_approved = sum(
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

        if po_auto_approved + invoice.total_amount > policy.po_cumulative_limit:
            _append_reason(
                reasons,
                "PO_CUMULATIVE_LIMIT",
            )


def evaluate_deterministic_baseline(
    case: BenchmarkCase,
) -> SystemDecision:
    block_reasons = _check_block_rules(case)

    if block_reasons:
        return SystemDecision(
            system_name=(SystemName.DETERMINISTIC_BASELINE),
            action=ExpectedAction.BLOCK,
            reason_codes=block_reasons,
        )

    reasons: list[str] = []

    _check_vendor_rules(
        case,
        reasons,
    )

    _check_invoice_policy(
        case,
        reasons,
    )

    _check_three_way_match(
        case,
        reasons,
    )

    _check_invoice_integrity(
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

    _check_stateful_policy(
        case,
        reasons,
    )

    action = ExpectedAction.ESCALATE if reasons else ExpectedAction.AUTO_APPROVE

    return SystemDecision(
        system_name=(SystemName.DETERMINISTIC_BASELINE),
        action=action,
        reason_codes=reasons,
    )
