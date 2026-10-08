from enum import Enum

from governed_ap.schemas import (
    BenchmarkCase,
    ExpectedAction,
    GoodsReceiptStatus,
    PaymentStatus,
    PurchaseOrderStatus,
)


class BlockReason(str, Enum):
    NO_MATCHING_PO = "NO_MATCHING_PO"
    EXACT_DUPLICATE = "EXACT_DUPLICATE"
    PO_FULLY_INVOICED = "PO_FULLY_INVOICED"


def check_block_rules(case: BenchmarkCase) -> list[BlockReason]:
    reasons = []

    purchase_order = case.purchase_order

    if purchase_order is None or case.invoice.po_id != purchase_order.po_id:
        reasons.append(BlockReason.NO_MATCHING_PO)
        return reasons

    committed_statuses = {
        PaymentStatus.APPROVED,
        PaymentStatus.PAID,
    }

    for payment in case.payment_history:
        if (
            payment.invoice_id == case.invoice.invoice_id
            and payment.po_id == purchase_order.po_id
            and payment.status in committed_statuses
        ):
            reasons.append(BlockReason.EXACT_DUPLICATE)
            break

    committed_amount = sum(
        payment.amount
        for payment in case.payment_history
        if payment.po_id == purchase_order.po_id
        and payment.currency == purchase_order.currency
        and payment.status in committed_statuses
    )

    if committed_amount >= purchase_order.total_amount:
        reasons.append(BlockReason.PO_FULLY_INVOICED)

    return reasons


class EscalateReason(str, Enum):
    NO_MATCHING_VENDOR = "NO_MATCHING_VENDOR"
    INACTIVE_VENDOR = "INACTIVE_VENDOR"
    VENDOR_ID_MISMATCH = "VENDOR_ID_MISMATCH"
    VENDOR_NAME_MISMATCH = "VENDOR_NAME_MISMATCH"
    PO_VENDOR_MISMATCH = "PO_VENDOR_MISMATCH"
    BANK_ACCOUNT_MISMATCH = "BANK_ACCOUNT_MISMATCH"
    PO_NOT_OPEN = "PO_NOT_OPEN"
    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
    NO_GOODS_RECEIPT = "NO_GOODS_RECEIPT"
    QUANTITY_EXCEEDS_ORDERED = "QUANTITY_EXCEEDS_ORDERED"
    QUANTITY_EXCEEDS_RECEIVED = "QUANTITY_EXCEEDS_RECEIVED"
    UNIT_PRICE_EXCEEDS_PO = "UNIT_PRICE_EXCEEDS_PO"
    PO_AMOUNT_EXCEEDED = "PO_AMOUNT_EXCEEDED"
    INVOICE_TOTAL_MISMATCH = "INVOICE_TOTAL_MISMATCH"


class OracleDecision:
    def __init__(self, action: ExpectedAction, reason_codes: list[str]):
        self.action = action
        self.reason_codes = reason_codes


def normalize_name(value: str) -> str:
    return " ".join(value.split()).casefold()


def check_escalate_rules(case: BenchmarkCase) -> list[EscalateReason]:
    reasons = []

    vendor = case.vendor
    purchase_order = case.purchase_order
    invoice = case.invoice

    if vendor is None:
        reasons.append(EscalateReason.NO_MATCHING_VENDOR)
    else:
        if not vendor.is_active:
            reasons.append(EscalateReason.INACTIVE_VENDOR)

        if invoice.vendor_id_claim != vendor.vendor_id:
            reasons.append(EscalateReason.VENDOR_ID_MISMATCH)

        trusted_names = {
            normalize_name(vendor.legal_name),
            *(normalize_name(alias) for alias in vendor.aliases),
        }

        if normalize_name(invoice.vendor_name) not in trusted_names:
            reasons.append(EscalateReason.VENDOR_NAME_MISMATCH)

        if invoice.invoice_bank_account != vendor.approved_bank_account:
            reasons.append(EscalateReason.BANK_ACCOUNT_MISMATCH)

    if purchase_order is not None:
        if vendor is not None and purchase_order.vendor_id != vendor.vendor_id:
            reasons.append(EscalateReason.PO_VENDOR_MISMATCH)

        if purchase_order.status != PurchaseOrderStatus.OPEN:
            reasons.append(EscalateReason.PO_NOT_OPEN)

        currencies_match = invoice.currency == purchase_order.currency

        if not currencies_match:
            reasons.append(EscalateReason.CURRENCY_MISMATCH)

        accepted_receipt_statuses = {
            GoodsReceiptStatus.RECEIVED,
            GoodsReceiptStatus.PARTIAL,
        }

        accepted_receipts = [
            receipt
            for receipt in case.goods_receipts
            if receipt.po_id == purchase_order.po_id and receipt.status in accepted_receipt_statuses
        ]

        if not accepted_receipts:
            reasons.append(EscalateReason.NO_GOODS_RECEIPT)
        else:
            received_quantity = sum(receipt.quantity_received for receipt in accepted_receipts)

            if invoice.quantity > received_quantity:
                reasons.append(EscalateReason.QUANTITY_EXCEEDS_RECEIVED)

        if invoice.quantity > purchase_order.quantity_ordered:
            reasons.append(EscalateReason.QUANTITY_EXCEEDS_ORDERED)

        if currencies_match:
            if invoice.unit_price > purchase_order.unit_price:
                reasons.append(EscalateReason.UNIT_PRICE_EXCEEDS_PO)

            committed_statuses = {
                PaymentStatus.APPROVED,
                PaymentStatus.PAID,
            }

            committed_amount = sum(
                payment.amount
                for payment in case.payment_history
                if payment.po_id == purchase_order.po_id
                and payment.currency == purchase_order.currency
                and payment.status in committed_statuses
            )

            if committed_amount + invoice.total_amount > purchase_order.total_amount:
                reasons.append(EscalateReason.PO_AMOUNT_EXCEEDED)

    expected_subtotal = invoice.quantity * invoice.unit_price
    expected_total = invoice.subtotal + invoice.tax_amount

    if invoice.subtotal != expected_subtotal or invoice.total_amount != expected_total:
        reasons.append(EscalateReason.INVOICE_TOTAL_MISMATCH)

    return reasons


def evaluate_case(case: BenchmarkCase) -> OracleDecision:
    block_reasons = check_block_rules(case)

    if block_reasons:
        return OracleDecision(
            action=ExpectedAction.BLOCK,
            reason_codes=[reason.value for reason in block_reasons],
        )

    escalate_reasons = check_escalate_rules(case)

    if escalate_reasons:
        return OracleDecision(
            action=ExpectedAction.ESCALATE,
            reason_codes=[reason.value for reason in escalate_reasons],
        )

    return OracleDecision(
        action=ExpectedAction.AUTO_APPROVE,
        reason_codes=[],
    )
